"""
Degasser Tower 0D Model with PHREEQC Integration

This model uses PHREEQC for acid dosing calculations and CO2 stripping simulation.
"""

import logging
from typing import Optional, Dict, Any

from pyomo.environ import (
    Var, Param, Constraint, Expression, Reference,
    units as pyunits, exp, log, log10,
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
from idaes.core.util.config import (
    is_physical_parameter_block,
)
from idaes.core.util.exceptions import ConfigurationError
import idaes.core.util.scaling as iscale
import idaes.logger as idaeslog
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.initialization import propagate_state

from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock
from .transport_core.phreeqpy_engine import PhreeqPyEngine
from .phreeqc_translator import MCASPhreeqcTranslator

__author__ = "Kurban Sitterley, WaterTAP Team"

logger = logging.getLogger(__name__)
_log = idaeslog.getLogger(__name__)


class AcidType:
    """Enumeration of acid types for dosing."""
    HCl = "HCl"
    H2SO4 = "H2SO4"


@declare_process_block_class("DegasserTower0DPhreeqc")
class DegasserTower0DPhreeqcData(UnitModelBlockData):
    """
    0D Degasser Tower model with PHREEQC integration.
    
    This model simulates:
    1. PHREEQC-based acid dosing calculations
    2. CO2 stripping based on Henry's law
    3. pH and alkalinity tracking
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
        "acid_type",
        ConfigValue(
            default=AcidType.HCl,
            domain=In([AcidType.HCl, AcidType.H2SO4]),
            description="Type of acid for dosing",
        ),
    )
    
    CONFIG.declare(
        "has_pressure_drop",
        ConfigValue(
            default=False,
            domain=In([True, False]),
            description="Include pressure drop through packed tower",
        ),
    )
    
    CONFIG.declare(
        "use_phreeqc_for_dosing",
        ConfigValue(
            default=True,
            domain=In([True, False]),
            description="Use PHREEQC engine for acid dosing calculations",
        ),
    )
    
    def build(self):
        """Build the degasser tower model."""
        super().build()
        
        # Initialize PHREEQC engine if requested
        if self.config.use_phreeqc_for_dosing:
            self._phreeqc_engine = PhreeqPyEngine()
            self._translator = MCASPhreeqcTranslator()
        
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
        
        self.control_volume.add_material_balances(
            balance_type=MaterialBalanceType.componentTotal,
            has_mass_transfer=True
        )
        
        self.control_volume.add_energy_balances(
            balance_type=EnergyBalanceType.none
        )
        
        if self.config.has_pressure_drop:
            self.control_volume.add_momentum_balances(
                balance_type=MomentumBalanceType.pressureTotal,
                has_pressure_change=True
            )
        
        # Add Ports
        self.add_inlet_port()
        self.add_outlet_port()
        
        # Tower geometry
        self.tower_diameter = Var(
            initialize=2.0,
            bounds=(0.1, 10),
            units=pyunits.m,
            doc="Tower diameter"
        )
        
        self.packing_height = Var(
            initialize=3.0,
            bounds=(0.5, 20),
            units=pyunits.m,
            doc="Height of packing"
        )
        
        # Operating parameters
        self.air_to_water_ratio = Var(
            initialize=50,
            bounds=(10, 200),
            units=pyunits.dimensionless,
            doc="Air to water volumetric ratio"
        )
        
        self.stripping_efficiency = Param(
            default=0.95,
            mutable=True,
            doc="CO2 stripping efficiency (0-1)"
        )
        
        # Acid dosing
        self.acid_dose_mol_L = Var(
            initialize=0.001,
            bounds=(0, 0.1),
            units=pyunits.dimensionless,  # mol/L units handled internally
            doc="Acid dose in mol/L"
        )
        
        self.target_pH = Var(
            initialize=4.5,
            bounds=(3, 7),
            units=pyunits.dimensionless,
            doc="Target pH after acid addition"
        )
        
        # pH tracking variables
        self.pH_in = Var(
            initialize=7,
            bounds=(2, 12),
            units=pyunits.dimensionless,
            doc="Inlet pH"
        )
        
        self.pH_out = Var(
            initialize=5,
            bounds=(2, 12),
            units=pyunits.dimensionless,
            doc="Outlet pH"
        )
        
        # Alkalinity tracking (carbonate alkalinity per PHREEQC convention)
        self.alkalinity_in = Var(
            initialize=100,
            bounds=(0, 1000),
            units=pyunits.dimensionless,  # mg/L as CaCO3
            doc="Inlet carbonate alkalinity as CaCO3 (mg/L) - [HCO3-] + 2*[CO3-2]"
        )
        
        self.alkalinity_out = Var(
            initialize=10,
            bounds=(0, 1000),
            units=pyunits.dimensionless,  # mg/L as CaCO3
            doc="Outlet carbonate alkalinity as CaCO3 (mg/L) - [HCO3-] + 2*[CO3-2]"
        )
        
        # CO2 removal
        self.co2_removed = Var(
            self.flowsheet().time,
            initialize=0.001,
            bounds=(0, None),
            units=pyunits.mol/pyunits.s,
            doc="Molar flow of CO2 stripped"
        )
        
        # Calculate carbonate alkalinity from species (PHREEQC convention)
        @self.Constraint(self.flowsheet().time)
        def eq_alkalinity_in(b, t):
            props_in = b.control_volume.properties_in[t]
            
            # Build carbonate alkalinity expression based on available components
            # Following water-chemistry-mcp convention: Alkalinity = [HCO3-] + 2*[CO3-2]
            alk_expr = 0
            comp_list = b.config.property_package.component_list
            
            # HCO3- contributes 1 eq/mol
            if 'HCO3_-' in comp_list:
                hco3_mol_L = pyunits.convert(
                    props_in.conc_mol_phase_comp['Liq', 'HCO3_-'],
                    to_units=pyunits.mol/pyunits.L
                )
                alk_expr += hco3_mol_L
            
            # CO3_2- contributes 2 eq/mol
            if 'CO3_2-' in comp_list:
                co3_mol_L = pyunits.convert(
                    props_in.conc_mol_phase_comp['Liq', 'CO3_2-'],
                    to_units=pyunits.mol/pyunits.L
                )
                alk_expr += 2 * co3_mol_L
            
            # Note: OH- and H+ are NOT included in carbonate alkalinity
            # This matches PHREEQC convention for degasser applications
            
            # Convert to mg/L as CaCO3 (MW = 100, eq.wt = 50) and make dimensionless
            alk_mg_L = alk_expr * 50000 / (pyunits.mol/pyunits.L)
            
            return b.alkalinity_in == alk_mg_L
        
        # Acid reaction - H+ addition
        @self.Constraint(self.flowsheet().time)
        def eq_acid_reaction(b, t):
            props_in = b.control_volume.properties_in[t]
            flow_vol_L_s = pyunits.convert(
                props_in.flow_vol,
                to_units=pyunits.L/pyunits.s
            )
            
            # H+ addition rate in mol/s
            h_added_mol_s = b.acid_dose_mol_L * flow_vol_L_s * (pyunits.mol/pyunits.L)
            
            # Convert to kg/s if mass basis
            if hasattr(b.config.property_package, 'material_flow_basis'):
                from watertap.property_models.multicomp_aq_sol_prop_pack import MaterialFlowBasis
                if b.config.property_package.material_flow_basis == MaterialFlowBasis.mass:
                    # Convert mol/s to kg/s using MW of H+ (1 g/mol = 0.001 kg/mol)
                    h_added_kg_s = h_added_mol_s * 0.001 * pyunits.kg/pyunits.mol
                    # Positive mass transfer = addition to control volume
                    return b.control_volume.mass_transfer_term[t, 'Liq', 'H_+'] == h_added_kg_s
            
            # Default to mol/s (positive = addition)
            return b.control_volume.mass_transfer_term[t, 'Liq', 'H_+'] == h_added_mol_s
        
        # CO2 stripping based on acid dose
        @self.Constraint(self.flowsheet().time)
        def eq_co2_stripping(b, t):
            props_in = b.control_volume.properties_in[t]
            flow_vol_L_s = pyunits.convert(
                props_in.flow_vol,
                to_units=pyunits.L/pyunits.s
            )
            
            # CO2 formed from alkalinity destruction (mol/s)
            co2_formed = b.acid_dose_mol_L * flow_vol_L_s * (pyunits.mol/pyunits.L)
            
            # Actual removal with stripping efficiency
            return b.co2_removed[t] == b.stripping_efficiency * co2_formed
        
        # Mass transfer for CO2 removal (based on HCO3- consumption)
        @self.Constraint(self.flowsheet().time)
        def eq_co2_mass_transfer(b, t):
            # Remove CO2 by reducing HCO3-
            # HCO3- + H+ → H2O + CO2 (gas, stripped out)
            # Negative mass transfer = removal from control volume
            if hasattr(b.config.property_package, 'material_flow_basis'):
                from watertap.property_models.multicomp_aq_sol_prop_pack import MaterialFlowBasis
                if b.config.property_package.material_flow_basis == MaterialFlowBasis.mass:
                    # Convert mol/s to kg/s using MW of HCO3- (61.02 g/mol = 0.06102 kg/mol)
                    co2_removed_kg_s = b.co2_removed[t] * 0.06102 * pyunits.kg/pyunits.mol
                    return b.control_volume.mass_transfer_term[t, 'Liq', 'HCO3_-'] == -co2_removed_kg_s
            
            # Default to mol/s (negative = removal)
            return b.control_volume.mass_transfer_term[t, 'Liq', 'HCO3_-'] == -b.co2_removed[t]
        
        # pH calculations from H+ concentration
        @self.Constraint(self.flowsheet().time)
        def eq_pH_in(b, t):
            if 'H_+' in b.config.property_package.component_list:
                # pH = -log10([H+]) where [H+] is in mol/L
                h_conc_mol_L = pyunits.convert(
                    b.control_volume.properties_in[t].conc_mol_phase_comp['Liq', 'H_+'],
                    to_units=pyunits.mol/pyunits.L
                )
                # Need to divide by units to make dimensionless for log10
                h_conc_dimensionless = h_conc_mol_L / (pyunits.mol/pyunits.L)
                # Use Pyomo's log10 function
                from pyomo.environ import log10
                return b.pH_in == -log10(h_conc_dimensionless)
            else:
                # If no H+, assume neutral pH
                return b.pH_in == 7.0
        
        @self.Constraint(self.flowsheet().time)
        def eq_pH_out(b, t):
            if 'H_+' in b.config.property_package.component_list:
                h_conc_mol_L = pyunits.convert(
                    b.control_volume.properties_out[t].conc_mol_phase_comp['Liq', 'H_+'],
                    to_units=pyunits.mol/pyunits.L
                )
                # Need to divide by units to make dimensionless for log10
                h_conc_dimensionless = h_conc_mol_L / (pyunits.mol/pyunits.L)
                from pyomo.environ import log10
                return b.pH_out == -log10(h_conc_dimensionless)
            else:
                # If no H+, assume neutral pH
                return b.pH_out == 7.0
        
        # Outlet carbonate alkalinity (PHREEQC convention)
        @self.Constraint(self.flowsheet().time)
        def eq_alkalinity_out(b, t):
            props_out = b.control_volume.properties_out[t]
            
            # Build carbonate alkalinity expression based on available components
            # Following water-chemistry-mcp convention: Alkalinity = [HCO3-] + 2*[CO3-2]
            alk_expr = 0
            comp_list = b.config.property_package.component_list
            
            # HCO3- contributes 1 eq/mol
            if 'HCO3_-' in comp_list:
                hco3_mol_L = pyunits.convert(
                    props_out.conc_mol_phase_comp['Liq', 'HCO3_-'],
                    to_units=pyunits.mol/pyunits.L
                )
                alk_expr += hco3_mol_L
            
            # CO3_2- contributes 2 eq/mol
            if 'CO3_2-' in comp_list:
                co3_mol_L = pyunits.convert(
                    props_out.conc_mol_phase_comp['Liq', 'CO3_2-'],
                    to_units=pyunits.mol/pyunits.L
                )
                alk_expr += 2 * co3_mol_L
            
            # Note: OH- and H+ are NOT included in carbonate alkalinity
            # This matches PHREEQC convention for degasser applications
            
            # Convert to mg/L as CaCO3 and make dimensionless
            alk_mg_L = alk_expr * 50000 / (pyunits.mol/pyunits.L)
            
            return b.alkalinity_out == alk_mg_L
        
        # Pressure drop if enabled
        if self.config.has_pressure_drop:
            self.pressure_drop_per_m = Param(
                default=1000,  # Pa/m
                mutable=True,
                units=pyunits.Pa/pyunits.m,
                doc="Pressure drop per meter of packing"
            )
            
            @self.Constraint(self.flowsheet().time)
            def eq_pressure_drop(b, t):
                return b.control_volume.deltaP[t] == -b.pressure_drop_per_m * b.packing_height
        
        # Initialize variables
        self._set_initial_values()
        
        # Set scaling factors
        self._set_scaling_factors()
    
    def _set_initial_values(self):
        """Set initial values for key variables."""
        self.tower_diameter.set_value(2.0)
        self.packing_height.set_value(3.0)
        self.air_to_water_ratio.set_value(50)
        self.acid_dose_mol_L.set_value(0.002)  # 2 mmol/L
        self.target_pH.set_value(4.5)
    
    def _set_scaling_factors(self):
        """Set scaling factors for variables."""
        iscale.set_scaling_factor(self.tower_diameter, 1)
        iscale.set_scaling_factor(self.packing_height, 0.5)
        iscale.set_scaling_factor(self.acid_dose_mol_L, 1000)
        iscale.set_scaling_factor(self.co2_removed, 1000)
        iscale.set_scaling_factor(self.alkalinity_in, 0.01)
        iscale.set_scaling_factor(self.alkalinity_out, 0.01)
    
    def calculate_acid_dose_phreeqc(self, state_args: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Calculate acid dose using PHREEQC engine.
        
        Args:
            state_args: Dictionary with inlet water composition
            
        Returns:
            Dictionary with acid dosing results
        """
        if not self.config.use_phreeqc_for_dosing:
            return {}
        
        # Get inlet composition
        if state_args is None:
            # Extract from inlet state
            props_in = self.control_volume.properties_in[0]
            
            # Convert MCAS state to PHREEQC format
            mcas_state = {
                'temperature': props_in.temperature.value - 273.15,  # K to C
                'pressure': props_in.pressure.value,
                'pH': props_in.pH.value if hasattr(props_in, 'pH') else 7.0,
                'flow_mass_phase_comp': {}
            }
            
            # Get mass flows
            for comp in self.config.property_package.component_list:
                mcas_state['flow_mass_phase_comp'][('Liq', comp)] = \
                    props_in.flow_mass_phase_comp['Liq', comp].value
            
            # Use translator
            phreeqc_water = self._translator.mcas_to_phreeqc(
                mcas_state,
                self.config.property_package
            )
        else:
            # Use provided state
            phreeqc_water = state_args
        
        # Calculate acid dose
        target_ph = self.target_pH.value
        acid_type = self.config.acid_type
        
        result = self._phreeqc_engine.calculate_acid_dose_for_degasser(
            influent_water=phreeqc_water,
            target_ph=target_ph,
            acid_type=acid_type
        )
        
        # Update model variables
        if 'optimal_dose_mmol_L' in result:
            self.acid_dose_mol_L.set_value(result['optimal_dose_mmol_L'] / 1000)
            logger.info(f"PHREEQC acid dose: {result['optimal_dose_mmol_L']:.2f} mmol/L {acid_type}")
            logger.info(f"Achieved pH: {result['achieved_pH']:.2f}")
            logger.info(f"CO2 generated: {result['co2_generated_mg_L']:.1f} mg/L")
        
        return result
    
    def initialize_build(
        self,
        state_args=None,
        outlvl=idaeslog.NOTSET,
        solver=None,
        optarg=None,
    ):
        """
        General wrapper for initialization routines.
        
        Args:
            state_args: Dictionary with initial property values
            outlvl: Logging output level
            solver: Solver to use for initialization
            optarg: Solver options
        """
        init_log = idaeslog.getInitLogger(self.name, outlvl, tag="unit")
        solve_log = idaeslog.getSolveLogger(self.name, outlvl, tag="unit")
        
        if solver is None:
            from idaes.core.solvers import get_solver
            solver = get_solver()
        
        # Calculate acid dose if using PHREEQC
        if self.config.use_phreeqc_for_dosing and state_args:
            self.calculate_acid_dose_phreeqc(state_args)
        
        # Save inlet values to ensure they don't get modified
        inlet_values = {}
        for t in self.flowsheet().time:
            for p in self.config.property_package.phase_list:
                for j in self.config.property_package.component_list:
                    var = self.inlet.flow_mass_phase_comp[t, p, j]
                    if var.fixed:
                        inlet_values[(t, p, j)] = var.value
        
        # Initialize inlet state block first
        flags = self.control_volume.properties_in.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=None,  # Let property package create its own solver
            state_args=state_args,
        )
        
        init_log.info("Initialization Step 1 Complete.")
        
        # Store degrees of freedom
        init_log.info(f"DOF before fixing inlet: {degrees_of_freedom(self)}")
        
        # Initialize outlet state block with inlet conditions
        # This provides a better starting point
        propagate_state(
            source=self.control_volume.properties_in[0],
            destination=self.control_volume.properties_out[0],
        )
        
        self.control_volume.properties_out.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=None,
        )
        
        # Now solve the unit model
        from pyomo.opt import TerminationCondition
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = solver.solve(self, tee=slc.tee)
        
        init_log.info(f"Initialization Step 2 {idaeslog.condition(res)}")
        
        # Restore inlet values
        for key, value in inlet_values.items():
            t, p, j = key
            self.inlet.flow_mass_phase_comp[t, p, j].set_value(value)
        
        # Release states
        self.control_volume.properties_in.release_state(flags, outlvl=outlvl)
        
        if res.solver.termination_condition == TerminationCondition.optimal:
            init_log.info("Initialization Complete.")
        else:
            init_log.warning(f"Initialization incomplete. Solver status: {res.solver.status}")
    
    def calculate_scaling_factors(self):
        """Calculate scaling factors for constraints."""
        super().calculate_scaling_factors()
        
        # Scale mass transfer constraints
        for t in self.flowsheet().time:
            for j in self.config.property_package.component_list:
                if j in ['H_+', 'HCO3_-']:
                    sf = iscale.get_scaling_factor(
                        self.control_volume.properties_in[t].flow_mol_phase_comp['Liq', j],
                        default=1e3
                    )
                    iscale.constraint_scaling_transform(
                        self.control_volume.material_balances[t, j],
                        sf
                    )
    
    @property
    def default_costing_method(self):
        """Return default costing method."""
        return self._default_costing_method
    
    def _default_costing_method(self, blk):
        """Default costing for degasser tower."""
        from idaes.core.base.costing_base import make_capital_cost_var
        
        make_capital_cost_var(blk)
        
        # Tower vessel cost
        blk.vessel_cost = Var(
            initialize=50000,
            bounds=(0, None),
            units=pyunits.USD_2023,
            doc="Tower vessel cost"
        )
        
        tower_volume = self.tower_diameter**2 * 3.14159/4 * self.packing_height
        
        @blk.Constraint()
        def vessel_cost_constraint(b):
            return b.vessel_cost == 10000 * (tower_volume/pyunits.m**3)**0.65
        
        # Packing cost
        blk.packing_cost = Var(
            initialize=20000,
            bounds=(0, None),
            units=pyunits.USD_2023,
            doc="Packing material cost"
        )
        
        @blk.Constraint()
        def packing_cost_constraint(b):
            return b.packing_cost == 500 * tower_volume
        
        # Total capital cost
        @blk.Constraint()
        def capital_cost_constraint(b):
            return b.capital_cost == b.vessel_cost + b.packing_cost