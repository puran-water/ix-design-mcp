"""
Degasser Tower 0D Model for WaterTAP

This model simulates CO2 stripping from water after acidification,
commonly used after WAC regeneration to remove dissolved CO2.

Key features:
- Acid dosing to convert bicarbonate to CO2
- Air stripping to remove dissolved CO2
- pH and alkalinity tracking
- Integration with MCAS property package
"""

import logging
from typing import Optional

from pyomo.environ import (
    Var, Param, Constraint, Expression,
    units as pyunits, exp, log, value,
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
    is_reaction_parameter_block,
)
from idaes.core.util.exceptions import ConfigurationError
import idaes.core.util.scaling as iscale
import idaes.logger as idaeslog

from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock

__author__ = "Kurban Sitterley, WaterTAP Team"

logger = logging.getLogger(__name__)
_log = idaeslog.getLogger(__name__)


class AcidType:
    """Enumeration of acid types for dosing."""
    HCl = "HCl"
    H2SO4 = "H2SO4"


@declare_process_block_class("DegasserTower0D")
class DegasserTower0DData(UnitModelBlockData):
    """
    0D Degasser Tower model for CO2 stripping.
    
    This model simulates:
    1. Acid addition to convert HCO3- to CO2
    2. Air stripping to remove dissolved CO2
    3. pH adjustment and alkalinity reduction
    """
    
    CONFIG = ConfigBlock()
    
    CONFIG.declare(
        "dynamic",
        ConfigValue(
            domain=In([False]),
            default=False,
            description="Dynamic model flag - must be False",
            doc="""Indicates whether this model will be dynamic or not,
    **default** = False. The filtration unit does not support dynamic
    behavior.""",
        ),
    )
    
    CONFIG.declare(
        "has_holdup",
        ConfigValue(
            default=False,
            domain=In([False]),
            description="Holdup construction flag - must be False",
            doc="""Indicates whether holdup terms should be constructed or not.
    **default** - False. The filtration unit does not have defined volume, thus
    this must be False.""",
        ),
    )
    
    CONFIG.declare(
        "property_package",
        ConfigValue(
            default=None,
            domain=is_physical_parameter_block,
            description="Property package to use",
            doc="""Property parameter object used to define property calculations,
    **default** - None.
    **Valid values:** {
    **useDefault** - use default package from parent model or flowsheet,
    **PhysicalParameterObject** - a PhysicalParameterBlock object.}""",
        ),
    )
    
    CONFIG.declare(
        "property_package_args",
        ConfigBlock(
            implicit=True,
            description="Arguments to use for constructing property packages",
            doc="""A ConfigBlock with arguments to be passed to a property block(s)
    and used when constructing these,
    **default** - None.
    **Valid values:** {
    see property package for documentation.}""",
        ),
    )
    
    CONFIG.declare(
        "acid_type",
        ConfigValue(
            default=AcidType.HCl,
            domain=In([AcidType.HCl, AcidType.H2SO4]),
            description="Type of acid for dosing",
            doc="Type of acid used for pH adjustment (HCl or H2SO4)"
        ),
    )
    
    CONFIG.declare(
        "has_pressure_drop",
        ConfigValue(
            default=True,
            domain=In([True, False]),
            description="Include pressure drop through packed tower",
            doc="Whether to include pressure drop calculations"
        ),
    )
    
    def build(self):
        """Build the degasser tower model."""
        super().build()
        
        # Check property package
        if not isinstance(self.config.property_package, MCASParameterBlock):
            raise ConfigurationError(
                "DegasserTower0D requires MCAS property package for pH/alkalinity calculations"
            )
        
        # Check that CO2/HCO3/CO3 are in component list
        required_species = {'H2O', 'H_+', 'OH_-', 'HCO3_-', 'CO3_2-'}
        available = set(self.config.property_package.component_list)
        
        if not required_species.issubset(available):
            missing = required_species - available
            raise ConfigurationError(
                f"Property package missing required species: {missing}"
            )
        
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
            has_mass_transfer=True  # For CO2 stripping
        )
        
        self.control_volume.add_energy_balances(
            balance_type=EnergyBalanceType.none  # Isothermal
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
        self.acid_dose = Var(
            initialize=0.001,
            bounds=(0, 0.1),
            units=pyunits.mol/pyunits.L,
            doc="Acid dose (mol/L)"
        )
        
        self.target_pH = Var(
            initialize=4.5,
            bounds=(3, 7),
            units=pyunits.dimensionless,
            doc="Target pH after acid addition"
        )
        
        # pH before and after
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
        
        # Link inlet pH to property package
        @self.Constraint(self.flowsheet().time)
        def eq_pH_in(b, t):
            # Get pH from inlet if available
            if hasattr(b.control_volume.properties_in[t], 'pH'):
                return b.pH_in == b.control_volume.properties_in[t].pH
            else:
                # Calculate from H+ concentration
                # Convert from mol/m³ to mol/L and make dimensionless
                h_conc_mol_m3 = b.control_volume.properties_in[t].conc_mol_phase_comp['Liq', 'H_+']
                # Divide by unit constant to make dimensionless for log10
                return b.pH_in == -log10(h_conc_mol_m3 / (1000 * pyunits.mol/pyunits.m**3))
        
        # Alkalinity tracking
        self.alkalinity_in = Var(
            initialize=100,
            bounds=(0, 1000),
            units=pyunits.mg/pyunits.L,
            doc="Inlet alkalinity as CaCO3"
        )
        
        self.alkalinity_out = Var(
            initialize=10,
            bounds=(0, 1000),
            units=pyunits.mg/pyunits.L,
            doc="Outlet alkalinity as CaCO3"
        )
        
        # CO2 removal
        self.co2_removed = Var(
            self.flowsheet().time,
            initialize=0.001,
            bounds=(0, None),
            units=pyunits.mol/pyunits.s,
            doc="Molar flow of CO2 stripped"
        )
        
        # Calculate alkalinity from species
        @self.Constraint(self.flowsheet().time)
        def eq_alkalinity_in(b, t):
            # Alkalinity = [HCO3-] + 2*[CO3--] + [OH-] - [H+]
            # Convert to mg/L as CaCO3 (MW = 100, eq.wt = 50)
            props_in = b.control_volume.properties_in[t]
            
            # Calculate alkalinity with proper unit handling
            # conc_mol_phase_comp is in mol/m³, convert to mol/L then to mg/L as CaCO3
            alk_mol_m3 = (
                props_in.conc_mol_phase_comp['Liq', 'HCO3_-'] +
                2 * props_in.conc_mol_phase_comp['Liq', 'CO3_2-'] +
                props_in.conc_mol_phase_comp['Liq', 'OH_-'] -
                props_in.conc_mol_phase_comp['Liq', 'H_+']
            )
            
            # Convert mol/m³ to mg/L as CaCO3: (mol/m³) * (1000 L/m³) * (50 mg CaCO3/mol)
            return b.alkalinity_in == alk_mol_m3 * 50
        
        # Acid dosing converts alkalinity to CO2
        @self.Constraint(self.flowsheet().time)
        def eq_acid_reaction(b, t):
            # HCO3- + H+ -> H2O + CO2
            # CO3-- + 2H+ -> H2O + CO2
            # Acid dose reduces alkalinity
            props_in = b.control_volume.properties_in[t]
            flow_vol = props_in.flow_vol_phase['Liq']
            
            # Moles of H+ added (mol/s)
            h_added_mol = b.acid_dose * flow_vol  # (mol/L) * (L/s) = mol/s
            
            # Convert to mass basis: mol/s * MW(H+) = kg/s
            # MW of H+ = 0.001 kg/mol
            h_added_mass = h_added_mol * 0.001  # kg/s
            
            # This constraint ensures H+ is consumed by alkalinity
            return b.control_volume.mass_transfer_term[t, 'Liq', 'H_+'] == -h_added_mass
        
        # CO2 stripping
        @self.Constraint(self.flowsheet().time)
        def eq_co2_stripping(b, t):
            # CO2 removal based on stripping efficiency
            # All converted CO2 can be stripped
            props_in = b.control_volume.properties_in[t]
            
            # CO2 formed from alkalinity destruction (mol/s)
            co2_formed = b.acid_dose * props_in.flow_vol_phase['Liq']
            
            # Actual CO2 removed (mol/s)
            return b.co2_removed[t] == b.stripping_efficiency * co2_formed
        
        # Mass transfer for CO2 removal (as HCO3- reduction)
        @self.Constraint(self.flowsheet().time)
        def eq_co2_mass_transfer(b, t):
            # Remove CO2 by reducing HCO3-
            # co2_removed is in mol/s, convert to kg/s for mass transfer term
            # MW of HCO3- = 0.061 kg/mol
            co2_removed_mass = b.co2_removed[t] * 0.061  # kg/s
            return b.control_volume.mass_transfer_term[t, 'Liq', 'HCO3_-'] == -co2_removed_mass
        
        # Outlet alkalinity
        @self.Constraint(self.flowsheet().time)
        def eq_alkalinity_out(b, t):
            props_out = b.control_volume.properties_out[t]
            
            # Calculate alkalinity with proper unit handling
            alk_mol_m3 = (
                props_out.conc_mol_phase_comp['Liq', 'HCO3_-'] +
                2 * props_out.conc_mol_phase_comp['Liq', 'CO3_2-'] +
                props_out.conc_mol_phase_comp['Liq', 'OH_-'] -
                props_out.conc_mol_phase_comp['Liq', 'H_+']
            )
            
            # Convert mol/m³ to mg/L as CaCO3
            return b.alkalinity_out == alk_mol_m3 * 50
        
        # Outlet pH
        @self.Constraint(self.flowsheet().time)
        def eq_pH_out(b, t):
            if hasattr(b.control_volume.properties_out[t], 'pH'):
                return b.pH_out == b.control_volume.properties_out[t].pH
            else:
                # Convert from mol/m³ to mol/L and make dimensionless
                h_conc_mol_m3 = b.control_volume.properties_out[t].conc_mol_phase_comp['Liq', 'H_+']
                # Divide by unit constant to make dimensionless for log10
                return b.pH_out == -log10(h_conc_mol_m3 / (1000 * pyunits.mol/pyunits.m**3))
        
        # Pressure drop (if enabled)
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
        self.acid_dose.set_value(0.002)  # 2 mmol/L
        self.target_pH.set_value(4.5)
    
    def _set_scaling_factors(self):
        """Set scaling factors for variables."""
        iscale.set_scaling_factor(self.tower_diameter, 1)
        iscale.set_scaling_factor(self.packing_height, 0.5)
        iscale.set_scaling_factor(self.acid_dose, 1000)  # Small values
        iscale.set_scaling_factor(self.co2_removed, 1000)
        iscale.set_scaling_factor(self.alkalinity_in, 0.01)
        iscale.set_scaling_factor(self.alkalinity_out, 0.01)
    
    def initialize_build(
        self,
        state_args=None,
        outlvl=idaeslog.NOTSET,
        solver=None,
        optarg=None,
    ):
        """
        General wrapper for initialization routines using staged approach.
        
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
            
        # Stage 1: Initialize control volume with hold_state=True
        init_log.info("Beginning staged initialization")
        init_log.info_high("Stage 1: Initializing control volume")
        
        # Check if inlet is already fixed (typical case)
        inlet_fixed = all(
            var.fixed 
            for var in self.control_volume.properties_in[0].flow_mass_phase_comp.values()
        )
        
        if inlet_fixed:
            init_log.info_high("Inlet properties already fixed, skipping property initialization")
            # Just initialize outlet properties based on inlet
            outlet = self.control_volume.properties_out[0]
            inlet = self.control_volume.properties_in[0]
            
            # Copy inlet values to outlet as initial guesses
            for comp in outlet.component_list:
                outlet.flow_mass_phase_comp['Liq', comp].set_value(
                    value(inlet.flow_mass_phase_comp['Liq', comp])
                )
            outlet.temperature.set_value(value(inlet.temperature))
            outlet.pressure.set_value(value(inlet.pressure))
            
            flags = None  # No flags since we didn't fix anything
        else:
            # Normal initialization path when inlet is not fixed
            if hasattr(self.control_volume, 'initialize'):
                # Don't pass solver object to control volume - it will get its own
                flags = self.control_volume.initialize(
                    state_args=state_args,
                    outlvl=outlvl,
                    optarg=optarg,
                    solver=None,  # Let control volume get its own solver
                    hold_state=True,  # Critical: prevent overwriting inlet conditions
                )
            else:
                # Fall back to initializing properties directly
                flags = self.control_volume.properties_in.initialize(
                    outlvl=outlvl,
                    optarg=optarg,
                    solver=None,  # Let property package get its own solver
                    state_args=state_args,
                    hold_state=True,
                )
                self.control_volume.properties_out.initialize(
                    outlvl=outlvl,
                    optarg=optarg,
                    solver=None,  # Let property package get its own solver
                    state_args=state_args,
                )
        
        init_log.info("Stage 1 Complete: Control volume initialized")
        
        # Stage 2: Deactivate mass transfer constraints for initial solve
        init_log.info_high("Stage 2: Deactivating mass transfer constraints")
        
        # Store constraint activity state
        mass_transfer_active = {}
        for t in self.flowsheet().time:
            for j in ['H_+', 'HCO3_-', 'CO3_2-']:
                if j in self.control_volume.properties_in[t].component_list:
                    constr = self.control_volume.material_balances[t, j]
                    mass_transfer_active[(t, j)] = constr.active
                    constr.deactivate()
        
        # Stage 3: Set initial guesses for degasser-specific variables
        init_log.info_high("Stage 3: Setting initial guesses")
        
        for t in self.flowsheet().time:
            # Initial guesses for performance variables
            if hasattr(self, 'co2_removal_fraction'):
                self.co2_removal_fraction[t].set_value(0.9)
            if hasattr(self, 'co2_removed'):
                self.co2_removed[t].set_value(1e-6)  # Small initial value
                
        # pH and alkalinity are not indexed by time
        if hasattr(self, 'pH_out'):
            # Estimate outlet pH based on inlet
            # MCAS doesn't have pH property, so just set a reasonable guess
            self.pH_out.set_value(7.5)
        if hasattr(self, 'alkalinity_out'):
            # Estimate alkalinity reduction
            self.alkalinity_out.set_value(50)  # mg/L as CaCO3
        
        # Stage 4: Solve without mass transfer constraints
        init_log.info_high("Stage 4: Initial solve without mass transfer")
        
        from pyomo.opt import TerminationCondition
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = solver.solve(self, tee=slc.tee)
        
        init_log.info(f"Stage 4 {idaeslog.condition(res)}")
        
        # Stage 5: Reactivate mass transfer constraints
        init_log.info_high("Stage 5: Reactivating mass transfer constraints")
        
        for (t, j), was_active in mass_transfer_active.items():
            if was_active:
                self.control_volume.material_balances[t, j].activate()
        
        # Stage 6: Final solve with all constraints active
        init_log.info_high("Stage 6: Final solve with all constraints")
        
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = solver.solve(self, tee=slc.tee)
        
        init_log.info(f"Stage 6 {idaeslog.condition(res)}")
        
        # Release inlet state only if we have flags
        if flags is not None:
            if hasattr(self.control_volume, 'release_state'):
                self.control_volume.release_state(flags, outlvl=outlvl)
            else:
                self.control_volume.properties_in.release_state(flags, outlvl=outlvl)
        
        if res.solver.termination_condition == TerminationCondition.optimal:
            init_log.info("Staged initialization completed successfully")
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
        return cost_degasser_tower


def cost_degasser_tower(blk):
    """
    Costing method for degasser tower.
    
    Costs include:
    - Tower vessel
    - Packing material
    - Air blower
    - Acid dosing system
    """
    from idaes.core.base.costing_base import make_capital_cost_var
    
    make_capital_cost_var(blk)
    
    # Tower vessel cost
    blk.vessel_cost = Var(
        initialize=50000,
        bounds=(0, None),
        units=pyunits.USD_2023,
        doc="Tower vessel cost"
    )
    
    # Vessel cost correlation
    # Cost = a * (Volume)^b
    tower_volume = blk.unit_model.tower_diameter**2 * 3.14159/4 * blk.unit_model.packing_height
    
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
        # $500/m³ for random packing
        return b.packing_cost == 500 * tower_volume
    
    # Total capital cost
    @blk.Constraint()
    def capital_cost_constraint(b):
        return b.capital_cost == b.vessel_cost + b.packing_cost


# Pyomo imports for log10
try:
    from pyomo.environ import log10
except ImportError:
    # Define log10 using natural log
    from pyomo.environ import log as ln
    def log10(x):
        return ln(x) / ln(10)