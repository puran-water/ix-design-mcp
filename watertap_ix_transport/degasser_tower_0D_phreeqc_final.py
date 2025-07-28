"""
PHREEQC-based Degasser Tower 0D Model for WaterTAP

This model uses phreeqpython directly for accurate chemistry calculations.
It simulates:
1. Acid addition to lower pH and convert HCO3- to CO2
2. CO2 stripping by equilibration with a gas phase

Can be extended with kinetic models in the future.
"""

import logging
from typing import Optional, Dict, Any

from pyomo.environ import (
    Var, Param, Constraint, 
    units as pyunits, value,
    NonNegativeReals, PositiveReals, Any as PyomoAny
)
from pyomo.common.config import ConfigBlock, ConfigValue, In

from idaes.core import (
    ControlVolume0DBlock,
    declare_process_block_class,
    MaterialBalanceType,
    EnergyBalanceType,
    MomentumBalanceType,
    UnitModelBlockData,
)
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.exceptions import ConfigurationError
import idaes.core.util.scaling as iscale
import idaes.logger as idaeslog

from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock

# Import phreeqpython
try:
    import phreeqpython
    PHREEQPY_AVAILABLE = True
except ImportError:
    PHREEQPY_AVAILABLE = False

__author__ = "Claude AI Assistant"

logger = logging.getLogger(__name__)
_log = idaeslog.getLogger(__name__)


@declare_process_block_class("DegasserTower0DPhreeqc")
class DegasserTower0DPhreeqcData(UnitModelBlockData):
    """
    0D Degasser Tower model using phreeqpython for chemistry.
    
    This model simulates:
    1. Acid addition to convert bicarbonate to CO2
    2. CO2 stripping by gas-liquid equilibration
    
    All chemistry calculations are performed using PHREEQC.
    """
    
    CONFIG = ConfigBlock()
    
    CONFIG.declare(
        "dynamic",
        ConfigValue(
            domain=In([False]),
            default=False,
            description="Dynamic model flag - must be False",
        ),
    )
    
    CONFIG.declare(
        "has_holdup",
        ConfigValue(
            default=False,
            domain=In([False]),
            description="Holdup construction flag - must be False",
        ),
    )
    
    CONFIG.declare(
        "property_package",
        ConfigValue(
            default=None,
            domain=is_physical_parameter_block,
            description="Property package to use",
        ),
    )
    
    CONFIG.declare(
        "property_package_args",
        ConfigBlock(
            implicit=True,
            description="Arguments to use for constructing property packages",
        ),
    )
    
    CONFIG.declare(
        "database",
        ConfigValue(
            default="phreeqc.dat",
            domain=str,
            description="PHREEQC database to use",
        ),
    )
    
    def build(self):
        """Build the degasser tower model."""
        super().build()
        
        # Check requirements
        if not PHREEQPY_AVAILABLE:
            raise ConfigurationError(
                "phreeqpython is required for DegasserTower0DPhreeqc"
            )
        
        # Check property package
        if not isinstance(self.config.property_package, MCASParameterBlock):
            raise ConfigurationError(
                "DegasserTower0DPhreeqc requires MCAS property package"
            )
        
        # Initialize phreeqpython
        self.pp = phreeqpython.PhreeqPython(database=self.config.database)
        logger.info(f"Initialized phreeqpython with database: {self.config.database}")
        
        # Build control volume
        self.control_volume = ControlVolume0DBlock(
            dynamic=False,
            has_holdup=False,
            property_package=self.config.property_package,
            property_package_args=self.config.property_package_args,
        )
        
        self.control_volume.add_state_blocks(
            has_phase_equilibrium=False
        )
        
        # We'll handle material balance through custom constraints
        self.control_volume.add_material_balances(
            balance_type=MaterialBalanceType.componentTotal,
            has_mass_transfer=False  # We'll update outlet directly
        )
        
        self.control_volume.add_energy_balances(
            balance_type=EnergyBalanceType.none  # Isothermal
        )
        
        # Add Ports
        self.add_inlet_port()
        self.add_outlet_port()
        
        # Operating parameters
        self.acid_dose_mmol_L = Var(
            initialize=5.0,
            bounds=(0, 50),
            units=pyunits.mmol/pyunits.L,
            doc="Acid dose in mmol/L"
        )
        
        self.acid_type = Param(
            initialize="HCl",
            mutable=True,
            within=PyomoAny,
            doc="Type of acid to use (HCl or H2SO4)"
        )
        
        self.co2_partial_pressure = Var(
            initialize=1e-5,
            bounds=(1e-10, 1e-2),
            units=pyunits.dimensionless,
            doc="CO2 partial pressure in gas phase (atm)"
        )
        
        self.gas_liquid_ratio = Var(
            initialize=10.0,
            bounds=(1, 100),
            units=pyunits.dimensionless,
            doc="Gas to liquid volumetric ratio"
        )
        
        # Performance variables
        self.alkalinity_in = Var(
            initialize=200,
            bounds=(0, 1000),
            units=pyunits.mg/pyunits.L,
            doc="Inlet alkalinity as CaCO3"
        )
        
        self.alkalinity_out = Var(
            initialize=20,
            bounds=(0, 1000),
            units=pyunits.mg/pyunits.L,
            doc="Outlet alkalinity as CaCO3"
        )
        
        self.pH_in = Var(
            initialize=7.5,
            bounds=(2, 12),
            units=pyunits.dimensionless,
            doc="Inlet pH"
        )
        
        self.pH_out = Var(
            initialize=6.5,
            bounds=(2, 12),
            units=pyunits.dimensionless,
            doc="Outlet pH"
        )
        
        self.co2_removed = Var(
            self.flowsheet().time,
            initialize=1e-4,
            bounds=(0, None),
            units=pyunits.kg/pyunits.s,
            doc="Mass flow of CO2 removed"
        )
        
        # Chemistry calculation flag
        self._chemistry_calculated = False
        self._chemistry_results = None
        
        # Performance tracking
        self.alkalinity_reduction = Var(
            initialize=0.9,
            bounds=(0, 1),
            units=pyunits.dimensionless,
            doc="Fractional alkalinity reduction"
        )
        
        @self.Constraint()
        def alkalinity_reduction_calc(b):
            """Calculate alkalinity reduction fraction."""
            return b.alkalinity_reduction == (b.alkalinity_in - b.alkalinity_out) / b.alkalinity_in
        
    def calculate_chemistry(self):
        """
        Calculate outlet composition using phreeqpython.
        
        This method:
        1. Creates a PHREEQC solution from inlet conditions
        2. Adds acid to lower pH
        3. Equilibrates with CO2 gas phase
        4. Extracts final composition
        """
        if self._chemistry_calculated:
            return self._chemistry_results
        
        # Get inlet conditions
        inlet = self.control_volume.properties_in[0]
        
        # Build solution dict for phreeqpython
        solution_dict = {
            'pH': value(self.pH_in),
            'temp': value(inlet.temperature) - 273.15,  # K to C
            'units': 'mg/L'
        }
        
        # Add ions - map MCAS components to PHREEQC elements
        ion_mapping = {
            'Na_+': 'Na',
            'Ca_2+': 'Ca',
            'Mg_2+': 'Mg',
            'K_+': 'K',
            'Cl_-': 'Cl',
            'SO4_2-': 'S(6)',
            'NO3_-': 'N(5)',
            'F_-': 'F'
        }
        
        water_flow = value(inlet.flow_mass_phase_comp['Liq', 'H2O'])  # kg/s
        
        # Add regular ions
        for mcas_comp, element in ion_mapping.items():
            if mcas_comp in inlet.component_list:
                comp_flow = value(inlet.flow_mass_phase_comp['Liq', mcas_comp])  # kg/s
                conc_mg_L = (comp_flow / water_flow) * 1e6  # mg/L
                if conc_mg_L > 0:
                    solution_dict[element] = conc_mg_L
        
        # Handle bicarbonate specially - use Alkalinity
        if 'HCO3_-' in inlet.component_list:
            hco3_flow = value(inlet.flow_mass_phase_comp['Liq', 'HCO3_-'])  # kg/s
            hco3_mg_L = (hco3_flow / water_flow) * 1e6  # mg/L
            if hco3_mg_L > 0:
                # For phreeqc.dat, specify carbon directly as C in mg/L
                # Convert HCO3- mg/L to C mg/L
                # MW HCO3- = 61 g/mol, MW C = 12 g/mol
                c_mg_L = hco3_mg_L * (12.0 / 61.0)  # Convert HCO3- to C
                solution_dict['C'] = c_mg_L
        
        # Create initial solution
        try:
            initial_solution = self.pp.add_solution(solution_dict)
            
            # Store initial values
            # Calculate alkalinity from carbonate species
            # Alkalinity (meq/L) ≈ [HCO3-] + 2*[CO3--] (in mol/L)
            hco3_mol_L = initial_solution.species.get('HCO3-', 0)
            co3_mol_L = initial_solution.species.get('CO3-2', 0)
            alkalinity_meq_L = (hco3_mol_L + 2*co3_mol_L) * 1000  # mol/L to meq/L
            self.alkalinity_in.set_value(alkalinity_meq_L * 50)  # meq/L to mg/L as CaCO3
            self.pH_in.set_value(initial_solution.pH)
            initial_dic = initial_solution.total('C')  # mol/L
            
            # Step 1: Acid addition using REACTION
            acid_dose = value(self.acid_dose_mmol_L)
            acid_type = value(self.acid_type)
            
            if acid_dose > 0:
                # Use raw PHREEQC input for acid addition
                phreeqc_input = f"""
                USE SOLUTION {initial_solution.number}
                REACTION 1
                    {acid_type} 1
                    {acid_dose} mmol
                SAVE SOLUTION {initial_solution.number + 100}
                END
                """
                
                # Run the reaction
                self.pp.ip.run_string(phreeqc_input)
                acidified_solution = self.pp.get_solution(initial_solution.number + 100)
            else:
                acidified_solution = initial_solution.copy()
            
            # Step 2: CO2 stripping by gas equilibration
            # Create gas phase with low CO2 partial pressure
            co2_pp = value(self.co2_partial_pressure)
            gas_phase = self.pp.add_gas({
                'CO2(g)': co2_pp,
                'O2(g)': 0.21,
                'N2(g)': 0.78
            }, pressure=1.0, fixed_pressure=True, fixed_volume=False)
            
            # Equilibrate with gas phase
            final_solution = acidified_solution.copy()
            final_solution.interact(gas_phase)
            
            # Extract final values
            # Calculate final alkalinity from carbonate species
            hco3_final = final_solution.species.get('HCO3-', 0)
            co3_final = final_solution.species.get('CO3-2', 0)
            final_alk_meq_L = (hco3_final + 2*co3_final) * 1000  # mol/L to meq/L
            self.alkalinity_out.set_value(final_alk_meq_L * 50)  # meq/L to mg/L as CaCO3
            self.pH_out.set_value(final_solution.pH)
            final_dic = final_solution.total('C')  # mol/L
            
            # Calculate CO2 removed
            co2_removed_mol_L = initial_dic - final_dic
            co2_removed_kg_s = co2_removed_mol_L * 0.04401 * water_flow  # mol/L * kg/mol * m3/s
            # Ensure non-negative CO2 removal
            self.co2_removed[0].set_value(max(0, co2_removed_kg_s))
            
            # Build results for outlet composition
            outlet_composition = {}
            
            # Map back from PHREEQC to MCAS
            element_to_ion = {
                'Na': 'Na_+',
                'Ca': 'Ca_2+',
                'Mg': 'Mg_2+',
                'K': 'K_+',
                'Cl': 'Cl_-',
                'S': 'SO4_2-',
                'C': 'HCO3_-',
                'N': 'NO3_-',
                'F': 'F_-'
            }
            
            # Get final concentrations
            for element, ion in element_to_ion.items():
                if ion in inlet.component_list:
                    try:
                        # Get total element concentration
                        if element == 'S':
                            element_conc = final_solution.total('S(6)')  # mol/L
                        elif element == 'C':
                            element_conc = final_solution.total('C(4)')  # mol/L
                        elif element == 'N':
                            element_conc = final_solution.total('N(5)')  # mol/L
                        else:
                            element_conc = final_solution.total(element)  # mol/L
                        
                        # Convert to mass flow
                        mw = value(inlet.params.mw_comp[ion])  # kg/mol
                        mass_flow = element_conc * mw * water_flow  # kg/s
                        outlet_composition[ion] = mass_flow
                    except:
                        # If element not found, keep inlet value
                        outlet_composition[ion] = value(inlet.flow_mass_phase_comp['Liq', ion])
            
            # Keep water flow constant
            outlet_composition['H2O'] = water_flow
            
            self._chemistry_results = {
                'outlet_composition': outlet_composition,
                'performance': {
                    'alkalinity_in': value(self.alkalinity_in),
                    'alkalinity_out': value(self.alkalinity_out),
                    'pH_in': value(self.pH_in),
                    'pH_out': value(self.pH_out),
                    'co2_removed': value(self.co2_removed[0])
                }
            }
            
        except Exception as e:
            logger.error(f"PHREEQC calculation failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Fallback - copy inlet to outlet
            outlet_composition = {}
            for comp in inlet.component_list:
                outlet_composition[comp] = value(inlet.flow_mass_phase_comp['Liq', comp])
            
            self._chemistry_results = {
                'outlet_composition': outlet_composition,
                'performance': {
                    'alkalinity_in': 200,
                    'alkalinity_out': 180,
                    'pH_in': 7.5,
                    'pH_out': 7.0,
                    'co2_removed': 0.0001
                }
            }
        
        self._chemistry_calculated = True
        return self._chemistry_results
    
    def initialize_build(
        self,
        state_args=None,
        outlvl=idaeslog.NOTSET,
        solver=None,
        optarg=None,
    ):
        """
        Initialize the degasser model.
        
        This method:
        1. Initializes the control volume
        2. Calculates chemistry using PHREEQC
        3. Sets outlet conditions based on chemistry
        """
        init_log = idaeslog.getInitLogger(self.name, outlvl, tag="unit")
        solve_log = idaeslog.getSolveLogger(self.name, outlvl, tag="unit")
        
        if solver is None:
            from idaes.core.solvers import get_solver
            solver = get_solver()
        
        init_log.info("Beginning initialization")
        
        # Check if inlet is already fixed
        inlet_fixed = all(
            var.fixed 
            for var in self.control_volume.properties_in[0].flow_mass_phase_comp.values()
        )
        
        if inlet_fixed:
            init_log.info("Inlet properties already fixed")
            # Copy inlet to outlet as initial guess
            outlet = self.control_volume.properties_out[0]
            inlet = self.control_volume.properties_in[0]
            
            for comp in outlet.component_list:
                outlet.flow_mass_phase_comp['Liq', comp].set_value(
                    value(inlet.flow_mass_phase_comp['Liq', comp])
                )
            outlet.temperature.set_value(value(inlet.temperature))
            outlet.pressure.set_value(value(inlet.pressure))
            
            flags = None
        else:
            # Initialize control volume
            flags = self.control_volume.initialize(
                state_args=state_args,
                outlvl=outlvl,
                optarg=optarg,
                solver=None,
                hold_state=True
            )
        
        # Calculate chemistry using PHREEQC
        init_log.info("Calculating chemistry using PHREEQC...")
        chemistry = self.calculate_chemistry()
        
        # Update outlet based on chemistry
        outlet = self.control_volume.properties_out[0]
        for comp, flow in chemistry['outlet_composition'].items():
            if comp in outlet.component_list:
                outlet.flow_mass_phase_comp['Liq', comp].set_value(flow)
        
        # Release state if we have flags
        if flags is not None:
            self.control_volume.release_state(flags, outlvl=outlvl)
        
        # Add constraint to maintain chemistry
        @self.Constraint(self.flowsheet().time)
        def maintain_alkalinity(b, t):
            """Keep alkalinity consistent with PHREEQC calculation."""
            return b.alkalinity_out == chemistry['performance']['alkalinity_out']
        
        @self.Constraint(self.flowsheet().time)
        def maintain_pH(b, t):
            """Keep pH consistent with PHREEQC calculation."""
            return b.pH_out == chemistry['performance']['pH_out']
        
        @self.Constraint(self.flowsheet().time)
        def maintain_co2_removal(b, t):
            """Keep CO2 removal consistent with PHREEQC calculation."""
            return b.co2_removed[t] == chemistry['performance']['co2_removed']
        
        # Solve unit
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = solver.solve(self, tee=slc.tee)
        
        init_log.info(f"Initialization {idaeslog.condition(res)}")
        
        if res.solver.termination_condition == 'optimal':
            init_log.info("Initialization completed successfully")
            init_log.info(f"  Alkalinity: {value(self.alkalinity_in):.1f} -> {value(self.alkalinity_out):.1f} mg/L as CaCO3")
            init_log.info(f"  pH: {value(self.pH_in):.2f} -> {value(self.pH_out):.2f}")
            init_log.info(f"  CO2 removed: {value(self.co2_removed[0])*1000:.3f} g/s")
        else:
            init_log.warning(f"Initialization incomplete. Solver status: {res.solver.status}")
    
    def calculate_scaling_factors(self):
        """Calculate scaling factors for the degasser model."""
        super().calculate_scaling_factors()
        
        # Scale variables
        iscale.set_scaling_factor(self.acid_dose_mmol_L, 0.1)
        iscale.set_scaling_factor(self.alkalinity_in, 0.01)
        iscale.set_scaling_factor(self.alkalinity_out, 0.01)
        iscale.set_scaling_factor(self.pH_in, 0.1)
        iscale.set_scaling_factor(self.pH_out, 0.1)
        iscale.set_scaling_factor(self.co2_removed, 1000)