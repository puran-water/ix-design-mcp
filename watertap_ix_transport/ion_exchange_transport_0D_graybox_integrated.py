"""
Ion Exchange Transport 0D Model with GrayBox Integration

This version uses the PhreeqcIXBlock GrayBox model for PHREEQC integration,
providing bullet-proof mass balance enforcement and automatic Jacobian calculation.
"""

import logging
from enum import Enum, auto

# Pyomo imports
from pyomo.environ import (
    Constraint,
    Var,
    Param,
    Reference,
    units as pyunits,
    NonNegativeReals,
    Set,
    value,
    log,
)
from pyomo.common.config import ConfigBlock, ConfigValue, In

# IDAES imports
from idaes.core import (
    ControlVolume0DBlock,
    declare_process_block_class,
    MaterialBalanceType,
    EnergyBalanceType,
    MomentumBalanceType,
    UnitModelBlockData,
    useDefault,
)
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.exceptions import ConfigurationError, InitializationError
from idaes.core.util.tables import create_stream_table_dataframe
import idaes.core.util.scaling as iscale
import idaes.logger as idaeslog

# WaterTAP imports
from watertap.core import InitializationMixin
from watertap.core.util.initialization import interval_initializer
from watertap.costing.unit_models.ion_exchange import cost_ion_exchange

# Import GrayBox model
from phreeqc_pse.blocks.phreeqc_ix_block import PhreeqcIXBlock

__author__ = "GrayBox Integration Team"

_log = logging.getLogger(__name__)
init_logger = logging.getLogger('idaes.init')


class ResinType(Enum):
    """Resin type options"""
    SAC = auto()        # Strong Acid Cation (Na+ form)
    WAC_H = auto()      # Weak Acid Cation (H+ form)
    WAC_Na = auto()     # Weak Acid Cation (Na+ form)


class RegenerantChem(Enum):
    """Regenerant chemical options"""
    NaCl = auto()        # For SAC
    HCl = auto()        # For WAC_H
    NaOH = auto()       # For WAC_Na
    H2SO4 = auto()      # Alternative for WAC_H


@declare_process_block_class("IonExchangeTransport0DGrayBox")
class IonExchangeTransport0DGrayBoxData(InitializationMixin, UnitModelBlockData):
    """
    Zero-order ion exchange model using PHREEQC GrayBox integration
    
    This model provides rigorous multi-component ion exchange with:
    - True thermodynamic equilibrium (activity coefficients)
    - Automatic mass balance enforcement through GrayBox
    - Proper Jacobian calculation for optimization
    - Multiple resin types (SAC, WAC_H, WAC_Na)
    """
    
    CONFIG = ConfigBlock()
    
    CONFIG.declare(
        "dynamic",
        ConfigValue(
            domain=In([False]),
            default=False,
            description="Dynamic model flag - must be False",
            doc="""Currently only steady-state models are supported.""",
        ),
    )
    
    CONFIG.declare(
        "has_holdup",
        ConfigValue(
            default=False,
            domain=In([False]),
            description="Holdup construction flag - must be False",
            doc="""Holdup is not supported for 0D unit models.""",
        ),
    )
    
    CONFIG.declare(
        "property_package",
        ConfigValue(
            default=useDefault,
            domain=is_physical_parameter_block,
            description="Property package to use for control volume",
            doc="""Property parameter object used to define property calculations,
    **default** - useDefault.
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
    and used when constructing these.
    **default** - None.
    **Valid values:** {
    see property package for documentation.}""",
        ),
    )
    
    CONFIG.declare(
        "material_balance_type",
        ConfigValue(
            default=MaterialBalanceType.useDefault,
            domain=In(MaterialBalanceType),
            description="Material balance construction flag",
            doc="""Indicates what type of mass balance should be constructed,
    **default** - MaterialBalanceType.useDefault.
    **Valid values:** {
    **MaterialBalanceType.useDefault** - refer to property package for default
    balance type
    **MaterialBalanceType.none** - exclude material balances,
    **MaterialBalanceType.componentPhase** - use phase component balances,
    **MaterialBalanceType.componentTotal** - use total component balances,
    **MaterialBalanceType.elementTotal** - use total element balances,
    **MaterialBalanceType.total** - use total material balance.}""",
        ),
    )
    
    CONFIG.declare(
        "energy_balance_type",
        ConfigValue(
            default=EnergyBalanceType.none,
            domain=In(EnergyBalanceType),
            description="Energy balance construction flag",
            doc="""Indicates what type of energy balance should be constructed,
    **default** - EnergyBalanceType.none.
    **Valid values:** {
    **EnergyBalanceType.useDefault** - refer to property package for default
    balance type
    **EnergyBalanceType.none** - exclude energy balances,
    **EnergyBalanceType.enthalpyTotal** - single enthalpy balance for material,
    **EnergyBalanceType.enthalpyPhase** - enthalpy balances for each phase,
    **EnergyBalanceType.energyTotal** - single energy balance for material,
    **EnergyBalanceType.energyPhase** - energy balances for each phase.}""",
        ),
    )
    
    CONFIG.declare(
        "momentum_balance_type",
        ConfigValue(
            default=MomentumBalanceType.pressureTotal,
            domain=In(MomentumBalanceType),
            description="Momentum balance construction flag",
            doc="""Indicates what type of momentum balance should be constructed,
        **default** - MomentumBalanceType.pressureTotal.
        **Valid values:** {
        **MomentumBalanceType.none** - exclude momentum balances,
        **MomentumBalanceType.pressureTotal** - single pressure balance for material,
        **MomentumBalanceType.pressurePhase** - pressure balances for each phase,
        **MomentumBalanceType.momentumTotal** - single momentum balance for material,
        **MomentumBalanceType.momentumPhase** - momentum balances for each phase.}""",
        ),
    )
    
    CONFIG.declare(
        "resin_type",
        ConfigValue(
            default=ResinType.SAC,
            domain=In(ResinType),
            description="Type of ion exchange resin",
            doc="""Resin type determines exchange reactions and selectivity.
        **default** - ResinType.SAC
        **Valid values:** {
        **ResinType.SAC** - Strong Acid Cation exchanger (Na+ form),
        **ResinType.WAC_H** - Weak Acid Cation exchanger (H+ form),
        **ResinType.WAC_Na** - Weak Acid Cation exchanger (Na+ form)}""",
        ),
    )
    
    CONFIG.declare(
        "regenerant",
        ConfigValue(
            default=RegenerantChem.NaCl,
            domain=In(RegenerantChem),
            description="Regenerant chemical",
            doc="""Chemical used for regeneration.
        **default** - RegenerantChem.NaCl
        **Valid values:** {
        **RegenerantChem.NaCl** - 10% NaCl for SAC,
        **RegenerantChem.HCl** - 5% HCl for WAC_H,
        **RegenerantChem.H2SO4** - 5% H2SO4 for WAC_H,
        **RegenerantChem.NaOH** - 4% NaOH for WAC_Na}""",
        ),
    )
    
    CONFIG.declare(
        "number_of_beds",
        ConfigValue(
            default=2,
            domain=int,
            description="Number of beds in operation",
            doc="Number of parallel beds in service (for duty calculations)"
        ),
    )
    
    def build(self):
        """
        Begin building model with GrayBox integration
        """
        super().build()
        
        # Map resin type to GrayBox format
        resin_map = {
            ResinType.SAC: "SAC",
            ResinType.WAC_H: "WAC_H",
            ResinType.WAC_Na: "WAC_Na"
        }
        graybox_resin_type = resin_map[self.config.resin_type]
        
        # Map regenerant ion
        regenerant_map = {
            RegenerantChem.NaCl: "Na",
            RegenerantChem.HCl: "H",
            RegenerantChem.H2SO4: "H",
            RegenerantChem.NaOH: "Na"
        }
        regenerant_ion = regenerant_map[self.config.regenerant]
        
        # Create control volume for material balances
        self.control_volume = ControlVolume0DBlock(
            dynamic=False,
            has_holdup=False,
            property_package=self.config.property_package,
            property_package_args=self.config.property_package_args,
        )
        
        self.control_volume.add_state_blocks(has_phase_equilibrium=False)
        self.control_volume.add_material_balances(
            balance_type=self.config.material_balance_type,
            has_mass_transfer=True
        )
        self.control_volume.add_energy_balances(
            balance_type=self.config.energy_balance_type,
            has_enthalpy_transfer=False
        )
        self.control_volume.add_momentum_balances(
            balance_type=self.config.momentum_balance_type,
            has_pressure_change=True
        )
        
        # Add inlet/outlet ports
        self.add_inlet_port()
        self.add_outlet_port()
        
        # Add bed parameters
        self._add_bed_parameters()
        
        # Determine target ions based on resin type
        if self.config.resin_type == ResinType.SAC:
            # SAC targets all cations
            self.target_ion_set = Set(initialize=[
                j for j in self.config.property_package.cation_set
                if j not in ['H_+', 'Na_+']
            ])
        else:  # WAC_H or WAC_Na
            # WAC primarily targets hardness ions
            self.target_ion_set = Set(initialize=[
                j for j in self.config.property_package.cation_set
                if j in ['Ca_2+', 'Mg_2+']
            ])
        
        # Get exchange capacity based on resin type
        if self.config.resin_type == ResinType.SAC:
            exchange_capacity = 2.0  # eq/L
        elif self.config.resin_type == ResinType.WAC_H:
            exchange_capacity = 4.0  # eq/L
        else:  # WAC_Na
            exchange_capacity = 3.5  # eq/L
        
        # Create GrayBox IX model
        self.graybox_ix = PhreeqcIXBlock(
            resin_type=graybox_resin_type,
            exchange_capacity=exchange_capacity,
            target_ions=[ion.strip('_+') for ion in self.target_ion_set],  # Remove charge notation
            regenerant_ion=regenerant_ion,
            column_parameters={
                'bed_volume': value(self.bed_volume),
                'flow_rate': value(self.control_volume.properties_in[0].flow_vol_phase["Liq"])
            },
            include_breakthrough=True,
            use_direct_phreeqc=True
        )
        
        # Connect control volume to GrayBox
        self._connect_to_graybox()
        
        # Add performance variables
        self._add_performance_variables()
        
        # Add constraints
        self._add_constraints()
        
        # Add expressions
        self._add_expressions()
    
    def _add_bed_parameters(self):
        """Add bed design parameters"""
        
        # Bed geometry
        self.bed_depth = Var(
            initialize=2.0,
            bounds=(0.5, 5.0),
            units=pyunits.m,
            doc="Bed depth"
        )
        
        self.bed_diameter = Var(
            initialize=2.0,
            bounds=(0.1, 10.0),
            units=pyunits.m,
            doc="Bed diameter"
        )
        
        # Bed volume per vessel
        @self.Expression(doc="Bed volume per vessel")
        def bed_volume(b):
            return 0.25 * 3.14159 * b.bed_diameter**2 * b.bed_depth
        
        # Total bed volume (all vessels)
        @self.Expression(doc="Total bed volume")
        def total_bed_volume(b):
            return b.bed_volume * b.config.number_of_beds
    
    def _connect_to_graybox(self):
        """Connect control volume to GrayBox model"""
        
        # Map inlet flows to GrayBox inputs
        t = self.flowsheet().time.first()
        inlet_state = self.control_volume.properties_in[t]
        
        # Temperature and pressure
        @self.Constraint()
        def eq_graybox_temperature(b):
            return b.graybox_ix.inputs.temperature == inlet_state.temperature
        
        @self.Constraint()
        def eq_graybox_pressure(b):
            return b.graybox_ix.inputs.pressure == inlet_state.pressure
        
        # Map component flows
        for comp in self.config.property_package.component_list:
            if comp == 'H2O':
                continue
                
            # Map component names (remove charge notation for GrayBox)
            gb_comp = comp.strip('_+-0123456789')
            
            if hasattr(self.graybox_ix.inputs, f"{gb_comp}_in"):
                @self.Constraint(doc=f"Map {comp} inlet flow")
                def eq_inlet_flow(b, c=comp, gbc=gb_comp):
                    if hasattr(inlet_state, 'flow_mass_phase_comp'):
                        return getattr(b.graybox_ix.inputs, f"{gbc}_in") == \
                               inlet_state.flow_mass_phase_comp['Liq', c]
                    else:
                        # Convert molar to mass flow
                        mw = b.config.property_package.mw_comp[c]
                        return getattr(b.graybox_ix.inputs, f"{gbc}_in") == \
                               inlet_state.flow_mol_phase_comp['Liq', c] * mw
        
        # Map outlet flows from GrayBox
        outlet_state = self.control_volume.properties_out[t]
        
        for comp in self.config.property_package.component_list:
            if comp == 'H2O':
                continue
                
            gb_comp = comp.strip('_+-0123456789')
            
            if hasattr(self.graybox_ix.outputs, f"{gb_comp}_out"):
                # Calculate mass transfer term
                @self.Constraint(doc=f"Mass transfer for {comp}")
                def eq_mass_transfer(b, c=comp, gbc=gb_comp):
                    inlet_flow = inlet_state.flow_mass_phase_comp['Liq', c] if \
                                hasattr(inlet_state, 'flow_mass_phase_comp') else \
                                inlet_state.flow_mol_phase_comp['Liq', c] * b.config.property_package.mw_comp[c]
                    outlet_flow = getattr(b.graybox_ix.outputs, f"{gbc}_out")
                    
                    # Mass transfer term = inlet - outlet (positive for removal)
                    return b.control_volume.mass_transfer_term[t, 'Liq', c] == inlet_flow - outlet_flow
    
    def _add_performance_variables(self):
        """Add performance tracking variables"""
        
        # Service time
        self.service_time = Var(
            initialize=24,
            bounds=(1, 168),
            units=pyunits.hour,
            doc="Service time between regenerations"
        )
        
        # Breakthrough time (link to GrayBox)
        @self.Constraint()
        def eq_breakthrough_time(b):
            if hasattr(b.graybox_ix.outputs, 'breakthrough_time'):
                return b.service_time == b.graybox_ix.outputs.breakthrough_time
            else:
                return b.service_time == 24  # Default
        
        # Regenerant dose
        self.regenerant_dose = Var(
            initialize=100,
            bounds=(50, 200),
            units=pyunits.kg/pyunits.m**3,
            doc="Regenerant dose per bed volume"
        )
    
    def _add_constraints(self):
        """Add additional constraints"""
        
        # Pressure drop (simplified)
        self.velocity = Var(
            initialize=10,
            bounds=(1, 30),
            units=pyunits.m/pyunits.hour,
            doc="Superficial velocity"
        )
        
        @self.Constraint()
        def eq_velocity(b):
            t = b.flowsheet().time.first()
            flow_vol = b.control_volume.properties_in[t].flow_vol_phase["Liq"]
            area = 0.25 * 3.14159 * b.bed_diameter**2
            return b.velocity == flow_vol * 3600 / area  # Convert to m/hr
        
        @self.Constraint()
        def eq_pressure_drop(b):
            t = b.flowsheet().time.first()
            # Simplified Ergun equation
            dp = 150 * b.velocity * b.bed_depth / 3600  # Pa
            return b.control_volume.deltaP[t] == -dp
    
    def _add_expressions(self):
        """Add performance expressions"""
        
        # Total hardness removal
        @self.Expression()
        def total_hardness_removal(b):
            if hasattr(b.graybox_ix, 'total_hardness_removal'):
                return b.graybox_ix.total_hardness_removal
            else:
                return 0
        
        # Resin utilization
        @self.Expression()
        def resin_utilization(b):
            if hasattr(b.graybox_ix, 'resin_utilization'):
                return b.graybox_ix.resin_utilization
            else:
                return 0.5
    
    def initialize_build(self, **kwargs):
        """
        Custom initialization routine for GrayBox model
        """
        init_log = idaeslog.getInitLogger(self.name, **kwargs)
        solve_log = idaeslog.getSolveLogger(self.name, **kwargs)
        
        init_log.info("Beginning initialization...")
        
        # Initialize control volume
        flags = self.control_volume.properties_in.initialize(**kwargs)
        
        # Initialize GrayBox
        self.graybox_ix.initialize_build(**kwargs)
        
        # Solve the integrated model
        solver = kwargs.get("solver", "ipopt")
        solver = SolverFactory(solver)
        solver.solve(self, tee=kwargs.get("tee", False))
        
        # Release inlet state
        self.control_volume.properties_in.release_state(flags)
        
        init_log.info("Initialization complete")
    
    def report(self, **kwargs):
        """
        Report ion exchange performance
        """
        self.control_volume.report(**kwargs)
        
        print("\n" + "="*60)
        print("Ion Exchange Performance (GrayBox)")
        print("="*60)
        
        # Report from GrayBox
        if hasattr(self.graybox_ix, 'report'):
            self.graybox_ix.report()
        
        # Additional reporting
        print(f"\nService time: {value(self.service_time):.1f} hours")
        print(f"Regenerant dose: {value(self.regenerant_dose):.1f} kg/m³")
        
    @property
    def default_costing_method(self):
        return cost_ion_exchange