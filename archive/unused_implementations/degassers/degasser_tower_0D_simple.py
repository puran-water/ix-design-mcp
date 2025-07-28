"""
Simplified Degasser Tower 0D Model for WaterTAP

This model simulates CO2 stripping from water with minimal complexity.
Key simplifications:
- Fixed stripping efficiency
- Simple alkalinity tracking
- No detailed pH calculations
"""

import logging
from typing import Optional

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

__author__ = "Kurban Sitterley, WaterTAP Team"

logger = logging.getLogger(__name__)
_log = idaeslog.getLogger(__name__)


@declare_process_block_class("DegasserTower0DSimple")
class DegasserTower0DSimpleData(UnitModelBlockData):
    """
    Simplified 0D Degasser Tower model for CO2 stripping.
    
    This model simulates:
    1. HCO3- removal as CO2
    2. Simple alkalinity tracking
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
        """Build the simplified degasser tower model."""
        super().build()
        
        # Check property package
        if not isinstance(self.config.property_package, MCASParameterBlock):
            raise ConfigurationError(
                "DegasserTower0DSimple requires MCAS property package"
            )
        
        # Check that HCO3- is in component list
        if 'HCO3_-' not in self.config.property_package.component_list:
            raise ConfigurationError(
                "Property package must include HCO3_- for degasser model"
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
            has_mass_transfer=True  # For HCO3- removal
        )
        
        self.control_volume.add_energy_balances(
            balance_type=EnergyBalanceType.none  # Isothermal
        )
        
        # Add Ports
        self.add_inlet_port()
        self.add_outlet_port()
        
        # Operating parameters
        self.removal_fraction = Var(
            initialize=0.9,
            bounds=(0, 1),
            units=pyunits.dimensionless,
            doc="Fraction of HCO3- removed as CO2"
        )
        
        # Performance tracking
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
        
        self.co2_removed = Var(
            self.flowsheet().time,
            initialize=1e-6,
            bounds=(0, None),
            units=pyunits.kg/pyunits.s,
            doc="Mass flow of CO2 removed"
        )
        
        # Constraints
        @self.Constraint(self.flowsheet().time)
        def hco3_removal(b, t):
            """Remove HCO3- as CO2."""
            # Get inlet HCO3- flow
            hco3_in = b.control_volume.properties_in[t].flow_mass_phase_comp['Liq', 'HCO3_-']
            
            # Calculate removal
            hco3_removed = b.removal_fraction * hco3_in
            
            # Set mass transfer term (negative for removal)
            return b.control_volume.mass_transfer_term[t, 'Liq', 'HCO3_-'] == -hco3_removed
        
        @self.Constraint(self.flowsheet().time)
        def co2_removed_calc(b, t):
            """Calculate CO2 removed."""
            # MW ratio: CO2/HCO3- = 44/61
            hco3_removed = -b.control_volume.mass_transfer_term[t, 'Liq', 'HCO3_-']
            return b.co2_removed[t] == hco3_removed * (44.0/61.0)
        
        @self.Constraint(self.flowsheet().time)
        def alkalinity_in_calc(b, t):
            """Calculate inlet alkalinity from HCO3-."""
            # Simplified: alkalinity ≈ [HCO3-] in mg/L as CaCO3
            hco3_conc = b.control_volume.properties_in[t].conc_mol_phase_comp['Liq', 'HCO3_-']
            # 1 mol/m³ HCO3- = 50 mg/L as CaCO3
            return b.alkalinity_in == hco3_conc * 50
        
        @self.Constraint(self.flowsheet().time)
        def alkalinity_out_calc(b, t):
            """Calculate outlet alkalinity from HCO3-."""
            hco3_conc = b.control_volume.properties_out[t].conc_mol_phase_comp['Liq', 'HCO3_-']
            return b.alkalinity_out == hco3_conc * 50
        
        # Set default mass transfer terms to zero for other components
        for t in self.flowsheet().time:
            for j in self.config.property_package.component_list:
                if j != 'HCO3_-':
                    self.control_volume.mass_transfer_term[t, 'Liq', j].fix(0)
        
        # Initialize variables
        self._set_initial_values()
        
        # Set scaling factors
        self._set_scaling_factors()
    
    def _set_initial_values(self):
        """Set initial values for key variables."""
        self.removal_fraction.set_value(0.9)
    
    def _set_scaling_factors(self):
        """Set scaling factors for variables."""
        iscale.set_scaling_factor(self.removal_fraction, 1)
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
        Initialize the simplified degasser model.
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
            # Initialize outlet based on inlet
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
            # Normal initialization
            flags = self.control_volume.initialize(
                state_args=state_args,
                outlvl=outlvl,
                optarg=optarg,
                solver=None,  # Let it get its own solver
                hold_state=True
            )
            init_log.info("Control volume initialized")
        
        # Solve unit
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = solver.solve(self, tee=slc.tee)
        
        init_log.info(f"Initialization {idaeslog.condition(res)}")
        
        # Release state if we have flags
        if flags is not None:
            self.control_volume.release_state(flags, outlvl=outlvl)
        
        if res.solver.termination_condition == 'optimal':
            init_log.info("Initialization completed successfully")
        else:
            init_log.warning(f"Initialization incomplete. Solver status: {res.solver.status}")
    
    def calculate_scaling_factors(self):
        """Calculate scaling factors for constraints."""
        super().calculate_scaling_factors()
        
        # Scale mass transfer constraint
        for t in self.flowsheet().time:
            sf = iscale.get_scaling_factor(
                self.control_volume.properties_in[t].flow_mass_phase_comp['Liq', 'HCO3_-'],
                default=1e3
            )
            iscale.constraint_scaling_transform(
                self.control_volume.material_balances[t, 'HCO3_-'],
                sf
            )