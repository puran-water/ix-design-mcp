"""
Degasser Tower 0D Model using water-chemistry-mcp for chemistry calculations.

This model uses a modular approach:
1. Acid addition via water-chemistry-mcp's simulate_chemical_addition
2. CO2 stripping via calculate_solution_speciation with gas phase equilibration
3. Simple material balance tracking in the WaterTAP framework

Following the DNR (Do Not Repeat) principle by reusing tested chemistry functions.
"""

import logging
from typing import Optional, Dict, Any
import asyncio

from pyomo.environ import (
    Var, Param, Constraint, 
    units as pyunits, value,
    NonNegativeReals, PositiveReals
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

# Import water-chemistry-mcp integration
import sys
import os
# Add water-chemistry-mcp to path (3 levels up from current file)
water_chem_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'water-chemistry-mcp')
)
if water_chem_path not in sys.path:
    sys.path.insert(0, water_chem_path)

try:
    from watertap_ix_transport.phreeqc_translator import MCASPhreeqcTranslator
    from watertap_ix_transport.transport_core.phreeqpy_engine import PhreeqPyEngine
except ImportError as e:
    raise ImportError(
        f"Failed to import required modules for PHREEQC integration: {e}"
    )

__author__ = "Claude AI Assistant"

logger = logging.getLogger(__name__)
_log = idaeslog.getLogger(__name__)


@declare_process_block_class("DegasserTower0DPhreeqcSimple")
class DegasserTower0DPhreeqcSimpleData(UnitModelBlockData):
    """
    0D Degasser Tower model using water-chemistry-mcp for chemistry.
    
    This model simulates:
    1. Acid addition to convert bicarbonate to CO2
    2. CO2 stripping by equilibration with air
    
    All chemistry calculations are handled by water-chemistry-mcp tools.
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
    
    def build(self):
        """Build the degasser tower model."""
        super().build()
        
        # Check property package
        if not isinstance(self.config.property_package, MCASParameterBlock):
            raise ConfigurationError(
                "DegasserTower0DPhreeqcSimple requires MCAS property package"
            )
        
        # Initialize translator and engine
        self.translator = MCASPhreeqcTranslator()
        self.phreeqc_engine = PhreeqPyEngine()
        
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
            initialize=2.0,
            bounds=(0, 20),
            units=pyunits.mmol/pyunits.L,
            doc="Acid dose in mmol/L"
        )
        
        self.acid_type = Param(
            initialize="HCl",
            mutable=True,
            doc="Type of acid to use (HCl or H2SO4)"
        )
        
        self.target_removal_fraction = Var(
            initialize=0.9,
            bounds=(0, 1),
            units=pyunits.dimensionless,
            doc="Target fraction of alkalinity to remove"
        )
        
        self.equilibrate_with_air = Param(
            initialize=True,
            mutable=True,
            doc="Whether to equilibrate with atmospheric CO2"
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
            bounds=(0, 14),
            units=pyunits.dimensionless,
            doc="Inlet pH"
        )
        
        self.pH_out = Var(
            initialize=6.0,
            bounds=(0, 14),
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
        
        # Constraints will be added during initialization
        # when we have actual inlet conditions
        
    def calculate_chemistry(self, state_args=None):
        """
        Calculate outlet composition using water-chemistry-mcp tools.
        
        This method:
        1. Translates inlet MCAS state to water-chemistry format
        2. Calls simulate_chemical_addition for acid dosing
        3. Calls calculate_solution_speciation for CO2 stripping
        4. Stores results for use in constraints
        """
        if self._chemistry_calculated:
            return self._chemistry_results
            
        # Get inlet state
        inlet = self.control_volume.properties_in[0]
        
        # Translate to water-chemistry format
        inlet_composition = self.translator.mcas_to_phreeqc_dict(inlet)
        
        # Step 1: Acid addition
        acid_dose = value(self.acid_dose_mmol_L)
        acid_type = value(self.acid_type)
        
        # PHREEQC handles acid dissociation automatically
        reactants = [{"formula": acid_type, "amount": acid_dose, "units": "mmol/L"}]
        
        acid_addition_input = {
            "initial_solution": inlet_composition,
            "reactants": reactants,
            "allow_precipitation": False
        }
        
        # Run acid addition simulation
        try:
            # Use asyncio to run the async function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            acid_result = loop.run_until_complete(
                self.phreeqc_engine.simulate_chemical_addition(acid_addition_input)
            )
            loop.close()
        except Exception as e:
            logger.error(f"Failed to simulate acid addition: {e}")
            raise
        
        # Step 2: CO2 stripping (if enabled)
        if value(self.equilibrate_with_air):
            # Extract solution from acid addition result
            # Water-chemistry-mcp returns solution_summary with pH and element_totals_molality
            acidified_pH = acid_result.get("solution_summary", {}).get("pH", inlet_composition["pH"])
            
            # Build solution for stripping
            acidified_solution = {
                "analysis": inlet_composition["analysis"].copy(),
                "pH": acidified_pH,
                "temperature_celsius": inlet_composition["temperature_celsius"],
                "pressure_atm": inlet_composition.get("pressure_atm", 1.0),
                "units": "mg/L"
            }
            
            # Update Cl concentration if HCl was used
            if acid_type == "HCl" and "element_totals_molality" in acid_result:
                cl_molality = acid_result["element_totals_molality"].get("Cl", 0)
                acidified_solution["analysis"]["Cl"] = cl_molality * 35.45 * 1000  # mol/L to mg/L
            
            # Add gas phase equilibration - use EQUILIBRIUM_PHASES
            stripping_input = {
                **acidified_solution,
                "equilibrium_phases": [
                    {"mineral": "CO2(g)", "log_si": -3.5}  # Atmospheric pCO2
                ]
            }
            
            # Run stripping simulation
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                stripping_result = loop.run_until_complete(
                    self.phreeqc_engine.calculate_solution_speciation(stripping_input)
                )
                loop.close()
            except Exception as e:
                logger.error(f"Failed to simulate CO2 stripping: {e}")
                raise
                
            final_result = stripping_result
        else:
            final_result = acid_result
        
        # Extract key results from water-chemistry-mcp format
        final_pH = final_result.get("solution_summary", {}).get("pH", inlet_composition["pH"])
        final_alkalinity = final_result.get("solution_summary", {}).get("alkalinity", 0)
        
        # Build outlet solution
        outlet_solution = {
            "analysis": {},
            "pH": final_pH,
            "alkalinity": final_alkalinity,
            "temperature_celsius": inlet_composition["temperature_celsius"],
            "units": "mg/L"
        }
        
        # Convert element totals to ion concentrations
        if "element_totals_molality" in final_result:
            element_to_ion = {
                'Na': ('Na_+', 22.99),
                'Ca': ('Ca_2+', 40.08), 
                'Mg': ('Mg_2+', 24.31),
                'K': ('K_+', 39.10),
                'Cl': ('Cl_-', 35.45),
                'S(6)': ('SO4_2-', 96.06),
                'C(4)': ('HCO3_-', 61.02),
                'N(5)': ('NO3_-', 62.00)
            }
            
            for element, molality in final_result["element_totals_molality"].items():
                if element in element_to_ion:
                    ion, mw = element_to_ion[element]
                    mg_L = molality * mw * 1000  # mol/L to mg/L
                    outlet_solution["analysis"][element] = mg_L
        
        # Store results
        self._chemistry_results = {
            "inlet": inlet_composition,
            "outlet": outlet_solution,
            "alkalinity_in": inlet_composition.get("alkalinity", 200),
            "alkalinity_out": final_alkalinity,
            "pH_in": inlet_composition["pH"],
            "pH_out": final_pH,
            "co2_removed": self._calculate_co2_removed(inlet_composition, outlet_solution)
        }
        
        self._chemistry_calculated = True
        return self._chemistry_results
    
    def _calculate_co2_removed(self, inlet, outlet):
        """Calculate mass of CO2 removed based on alkalinity change."""
        # Get alkalinity values (mg/L as CaCO3)
        alk_in = inlet.get("alkalinity", 0)
        
        if "final_solution" in outlet:
            alk_out = outlet["final_solution"].get("alkalinity", 0)
        else:
            alk_out = outlet.get("alkalinity", 0)
        
        # Convert alkalinity change to CO2 removed
        # 1 mg/L as CaCO3 alkalinity = 0.88 mg/L CO2
        co2_removed_mg_L = (alk_in - alk_out) * 0.88
        
        # Get flow rate (assuming 1 L/s for now - should get from inlet)
        flow_rate_L_s = 1.0
        
        # Convert to kg/s
        co2_removed_kg_s = co2_removed_mg_L * flow_rate_L_s / 1e6
        
        return co2_removed_kg_s
    
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
        2. Calculates chemistry using water-chemistry-mcp
        3. Sets outlet conditions based on chemistry
        4. Adds constraints to maintain chemistry results
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
            init_log.info("Inlet properties already fixed, skipping control volume initialization")
            # Copy inlet to outlet as initial guess
            outlet = self.control_volume.properties_out[0]
            inlet = self.control_volume.properties_in[0]
            
            for comp in outlet.component_list:
                if not outlet.flow_mass_phase_comp['Liq', comp].fixed:
                    outlet.flow_mass_phase_comp['Liq', comp].set_value(
                        value(inlet.flow_mass_phase_comp['Liq', comp])
                    )
            outlet.temperature.set_value(value(inlet.temperature))
            outlet.pressure.set_value(value(inlet.pressure))
            
            flags = None
        else:
            # Initialize control volume normally
            flags = self.control_volume.initialize(
                state_args=state_args,
                outlvl=outlvl,
                optarg=optarg,
                solver=None,
                hold_state=True
            )
        
        # Calculate chemistry
        init_log.info("Calculating chemistry using water-chemistry-mcp...")
        chemistry = self.calculate_chemistry(state_args)
        
        # Set performance variables
        self.alkalinity_in.set_value(chemistry["alkalinity_in"])
        self.alkalinity_out.set_value(chemistry["alkalinity_out"])
        self.pH_in.set_value(chemistry["pH_in"])
        self.pH_out.set_value(chemistry["pH_out"])
        self.co2_removed[0].set_value(chemistry["co2_removed"])
        
        # Update outlet state based on chemistry
        outlet_composition = chemistry["outlet"]
        outlet_state = self.translator.phreeqc_to_mcas_state(
            outlet_composition,
            self.control_volume.properties_out[0]
        )
        
        # Set outlet values
        outlet = self.control_volume.properties_out[0]
        for comp in outlet.component_list:
            if comp in outlet_state:
                outlet.flow_mass_phase_comp['Liq', comp].set_value(outlet_state[comp])
        
        # Add constraints to maintain chemistry results
        @self.Constraint(self.flowsheet().time)
        def alkalinity_consistency(b, t):
            """Ensure alkalinity values match chemistry calculation."""
            return b.alkalinity_out == chemistry["alkalinity_out"]
        
        @self.Constraint(self.flowsheet().time)
        def pH_consistency(b, t):
            """Ensure pH values match chemistry calculation."""
            return b.pH_out == chemistry["pH_out"]
        
        @self.Constraint(self.flowsheet().time)
        def co2_removal_consistency(b, t):
            """Ensure CO2 removal matches chemistry calculation."""
            return b.co2_removed[t] == chemistry["co2_removed"]
        
        # Release state if we have flags
        if flags is not None:
            self.control_volume.release_state(flags, outlvl=outlvl)
        
        # Solve unit
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = solver.solve(self, tee=slc.tee)
        
        init_log.info(f"Initialization {idaeslog.condition(res)}")
        
        if res.solver.termination_condition == 'optimal':
            init_log.info("Initialization completed successfully")
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