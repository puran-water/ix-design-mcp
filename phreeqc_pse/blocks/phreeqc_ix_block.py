"""
PHREEQC Ion Exchange Block
Specialized block for ion exchange equilibrium calculations using PHREEQC
"""

from pyomo.environ import (
    Var, Constraint, Param, Set as PyomoSet, Expression,
    Reference, units as pyunits, value, exp, log
)
from idaes.core import declare_process_block_class
from pyomo.common.config import ConfigBlock, ConfigValue, In
# InitializationStatus is defined differently in different IDAES versions
try:
    from idaes.core.util.initialization import InitializationStatus
except ImportError:
    from enum import Enum
    class InitializationStatus(Enum):
        Ok = "optimal"
        Error = "error"

from ..core.phreeqc_block import PhreeqcBlockData
from ..core.phreeqc_state import PhreeqcState
from ..core.phreeqc_io import PhreeqcInputSpec, PhreeqcOutputSpec, VariableType
from ..core.phreeqc_solver import PhreeqcSolver

import logging

logger = logging.getLogger(__name__)
init_logger = logging.getLogger("idaes.init")


@declare_process_block_class("PhreeqcIXBlock")
class PhreeqcIXBlockData(PhreeqcBlockData):
    """
    PHREEQC Ion Exchange Block for IDAES/WaterTAP
    
    This specialized block handles ion exchange equilibrium calculations
    with proper integration into WaterTAP flowsheets.
    """
    
    CONFIG = PhreeqcBlockData.CONFIG()
    
    CONFIG.declare("resin_type", ConfigValue(
        default="SAC",
        domain=In(["SAC", "WAC_H", "WAC_Na", "SBA", "WBA"]),
        description="Type of ion exchange resin",
        doc="Resin type: SAC (strong acid cation), WAC (weak acid cation), etc."
    ))
    
    CONFIG.declare("exchange_capacity", ConfigValue(
        default=2.0,
        domain=float,
        description="Ion exchange capacity (eq/L)",
        doc="Total exchange capacity of the resin"
    ))
    
    CONFIG.declare("target_ions", ConfigValue(
        default=["Ca", "Mg"],
        domain=list,
        description="List of target ions for removal",
        doc="Ions to be removed by ion exchange"
    ))
    
    CONFIG.declare("regenerant_ion", ConfigValue(
        default="Na",
        domain=str,
        description="Regenerant ion",
        doc="Ion used for regeneration (e.g., Na for SAC)"
    ))
    
    CONFIG.declare("column_parameters", ConfigValue(
        default={},
        domain=dict,
        description="Column design parameters",
        doc="Dictionary with bed_volume, flow_rate, etc."
    ))
    
    CONFIG.declare("include_breakthrough", ConfigValue(
        default=False,
        domain=bool,
        description="Include breakthrough calculations",
        doc="Whether to calculate breakthrough time"
    ))
    
    def build(self):
        """
        Build the ion exchange block
        """
        # First create the state
        self._create_ix_state()
        
        # Set the state in config for parent class
        self.config.phreeqc_state = self.phreeqc_state
        
        # Build parent block first
        super().build()
        
        # Now we can create I/O specs that depend on the state
        if not hasattr(self.config, 'input_specs') or self.config.input_specs is None:
            self.config.input_specs = self._create_ix_input_specs()
        if not hasattr(self.config, 'output_specs') or self.config.output_specs is None:
            self.config.output_specs = self._create_ix_output_specs()
            
        # Rebuild I/O if needed
        if hasattr(self, '_build_inputs'):
            self._build_inputs()
        if hasattr(self, '_build_outputs'):
            self._build_outputs()
        
        # Add IX-specific components
        self._add_ix_parameters()
        self._add_ix_variables()
        self._add_ix_constraints()
        self._add_ix_expressions()
        
        logger.info(f"PhreeqcIXBlock built for {self.config.resin_type} resin")
    
    def _create_ix_state(self):
        """Create PhreeqcState configured for ion exchange"""
        
        # Get database from config or use default
        database = self.config.database if hasattr(self.config, 'database') else "phreeqc.dat"
            
        # Define components based on resin type
        if self.config.resin_type in ["SAC", "WAC_H", "WAC_Na"]:
            # Cation exchange
            components = ['H2O', 'H+', 'OH-', 'Ca', 'Mg', 'Na', 'K', 'Cl', 'SO4', 'HCO3']
        else:  # SBA, WBA
            # Anion exchange
            components = ['H2O', 'H+', 'OH-', 'Cl', 'SO4', 'HCO3', 'NO3', 'Ca', 'Mg', 'Na']
        
        # Create state
        self.phreeqc_state = PhreeqcState(
            database=self.config.database,
            components=components,
            temperature=298.15,
            pressure=101325
        )
        
        # Add ion exchange
        site_name = 'X' if self.config.resin_type in ["SAC", "WAC_H", "WAC_Na"] else 'Y'
        self.phreeqc_state.add_ion_exchange(
            site_name=site_name,
            capacity=self.config.exchange_capacity
        )
        
        # State is now available for use
    
    def _create_ix_input_specs(self):
        """Create input specifications for IX"""
        specs = PhreeqcInputSpec()
        
        # Add inlet flows for all components
        for comp in self.phreeqc_state.components:
            if comp not in ['H2O', 'H+', 'OH-']:
                specs.add_flow_input(comp)
        
        # Add system variables
        specs.add_system_input(VariableType.TEMPERATURE)
        specs.add_system_input(VariableType.PRESSURE)
        specs.add_system_input(VariableType.PH)
        
        # Add column parameters if included
        if self.config.column_parameters:
            specs.add_column_input(
                name='bed_volume',
                description='Bed volume',
                units=pyunits.m**3,
                bounds=(0.1, 100),
                default=self.config.column_parameters.get('bed_volume', 1.0)
            )
            specs.add_column_input(
                name='flow_rate',
                description='Volumetric flow rate',
                units=pyunits.m**3/pyunits.s,
                bounds=(1e-6, 0.1),
                default=self.config.column_parameters.get('flow_rate', 0.001)
            )
        
        return specs
    
    def _create_ix_output_specs(self):
        """Create output specifications for IX"""
        specs = PhreeqcOutputSpec()
        
        # Add outlet flows for all components
        for comp in self.phreeqc_state.components:
            if comp not in ['H2O', 'H+', 'OH-']:
                specs.add_flow_output(comp)
                
                # Add removal for target ions
                if comp in self.config.target_ions:
                    specs.add_removal_output(comp)
        
        # Add system outputs
        specs.add_system_output(VariableType.PH)
        specs.add_system_output(VariableType.IONIC_STRENGTH)
        
        # Add exchange fractions
        if self.config.resin_type == "SAC":
            for ion in ['Ca', 'Mg', 'Na', 'H']:
                specs.add_exchange_output(f"{ion}X")
        
        # Add breakthrough if requested
        if self.config.include_breakthrough:
            specs.add_breakthrough_output()
        
        return specs
    
    def _add_ix_parameters(self):
        """Add IX-specific parameters"""
        
        # Selectivity coefficients (approximate)
        selectivity_data = {
            'SAC': {'Ca': 5.2, 'Mg': 3.3, 'Na': 1.0, 'K': 1.5, 'H': 1.0},
            'WAC_H': {'Ca': 3.5, 'Mg': 2.5, 'Na': 0.7, 'K': 0.9, 'H': 1.0},
            'WAC_Na': {'Ca': 4.0, 'Mg': 2.8, 'Na': 1.0, 'K': 1.2, 'H': 0.5}
        }
        
        if self.config.resin_type in selectivity_data:
            self.selectivity = Param(
                self.config.target_ions + [self.config.regenerant_ion],
                initialize=selectivity_data[self.config.resin_type],
                doc="Selectivity coefficients relative to Na+"
            )
        
        # Kinetic parameters (if needed)
        self.mass_transfer_coefficient = Param(
            initialize=0.0001,
            units=pyunits.m/pyunits.s,
            doc="Mass transfer coefficient"
        )
    
    def _add_ix_variables(self):
        """Add IX-specific variables"""
        
        # Resin loading
        self.resin_loading = Var(
            self.config.target_ions,
            bounds=(0, self.config.exchange_capacity),
            initialize=0.5,
            units=pyunits.mol/pyunits.L,
            doc="Resin loading for each ion"
        )
        
        # Total hardness removal
        self.total_hardness_removal = Var(
            bounds=(0, None),
            initialize=0.0001,
            units=pyunits.kg/pyunits.s,
            doc="Total hardness removal rate"
        )
        
        # Utilization
        self.resin_utilization = Var(
            bounds=(0, 1),
            initialize=0.5,
            units=pyunits.dimensionless,
            doc="Fraction of resin capacity utilized"
        )
    
    def _add_ix_constraints(self):
        """Add IX-specific constraints"""
        
        # Total hardness removal
        @self.Constraint()
        def eq_total_hardness_removal(b):
            total = 0
            for ion in b.config.target_ions:
                if hasattr(b.outputs, f"{ion}_removal"):
                    total += getattr(b.outputs, f"{ion}_removal")
            return b.total_hardness_removal == total
        
        # Resin utilization
        @self.Constraint()
        def eq_resin_utilization(b):
            total_loading = sum(b.resin_loading[ion] for ion in b.config.target_ions)
            return b.resin_utilization == total_loading / b.config.exchange_capacity
        
        # Minimum removal constraint (optional)
        if hasattr(self, 'minimum_removal_fraction'):
            @self.Constraint(self.config.target_ions)
            def eq_minimum_removal(b, ion):
                inlet = getattr(b.inputs, f"{ion}_in")
                outlet = getattr(b.outputs, f"{ion}_out")
                return outlet <= inlet * (1 - b.minimum_removal_fraction)
    
    def _add_ix_expressions(self):
        """Add IX-specific expressions"""
        
        # Hardness (as CaCO3 equivalent)
        @self.Expression()
        def hardness_in(b):
            hardness = 0
            mw_caco3 = 100.09  # g/mol
            if hasattr(b.inputs, 'Ca_in'):
                hardness += getattr(b.inputs, 'Ca_in') * mw_caco3 / 40.08
            if hasattr(b.inputs, 'Mg_in'):
                hardness += getattr(b.inputs, 'Mg_in') * mw_caco3 / 24.31
            return hardness
        
        @self.Expression()
        def hardness_out(b):
            hardness = 0
            mw_caco3 = 100.09  # g/mol
            if hasattr(b.outputs, 'Ca_out'):
                hardness += getattr(b.outputs, 'Ca_out') * mw_caco3 / 40.08
            if hasattr(b.outputs, 'Mg_out'):
                hardness += getattr(b.outputs, 'Mg_out') * mw_caco3 / 24.31
            return hardness
        
        @self.Expression()
        def hardness_removal_percent(b):
            if value(b.hardness_in) > 0:
                return (b.hardness_in - b.hardness_out) / b.hardness_in * 100
            else:
                return 0
        
        # Bed volumes to breakthrough (if included)
        if self.config.include_breakthrough and hasattr(self.outputs, 'breakthrough_time'):
            @self.Expression()
            def bed_volumes_to_breakthrough(b):
                if hasattr(b.inputs, 'bed_volume') and hasattr(b.inputs, 'flow_rate'):
                    return (b.outputs.breakthrough_time * 3600 * b.inputs.flow_rate) / b.inputs.bed_volume
                else:
                    return 100  # Default
    
    def initialize_build(self, **kwargs):
        """
        Initialize the IX block with IX-specific logic
        """
        init_logger.info("Beginning PhreeqcIXBlock initialization...")
        
        # Configure solver for IX
        if hasattr(self.phreeqc_solver, 'transport_engine'):
            self.phreeqc_solver.transport_engine.resin_type = self.config.resin_type
        
        # Call parent initialization
        result = super().initialize_build(**kwargs)
        
        # Post-process IX results
        if result == InitializationStatus.Ok:
            # Calculate derived variables
            self.total_hardness_removal.value = value(self.eq_total_hardness_removal.body)
            self.resin_utilization.value = value(self.eq_resin_utilization.body)
            
            # Log IX performance
            init_logger.info(f"Hardness removal: {value(self.hardness_removal_percent):.1f}%")
            init_logger.info(f"Resin utilization: {value(self.resin_utilization)*100:.1f}%")
            
            if self.config.include_breakthrough:
                init_logger.info(f"Bed volumes to breakthrough: {value(self.bed_volumes_to_breakthrough):.1f}")
        
        return result
    
    def report(self, index=0, stream=None):
        """
        Generate IX-specific report
        """
        if stream is None:
            stream = logger.info
            
        stream("=" * 60)
        stream(f"Ion Exchange Block Report ({self.config.resin_type})")
        stream("=" * 60)
        
        # System conditions
        stream("\nSystem Conditions:")
        stream(f"  Temperature: {value(self.inputs.temperature):.1f} K")
        stream(f"  Pressure: {value(self.inputs.pressure)/1e5:.2f} bar")
        stream(f"  pH: {value(self.inputs.pH):.2f}")
        
        # Inlet composition
        stream("\nInlet Composition:")
        for ion in self.config.target_ions + [self.config.regenerant_ion]:
            if hasattr(self.inputs, f"{ion}_in"):
                flow = value(getattr(self.inputs, f"{ion}_in"))
                stream(f"  {ion}: {flow*1000:.3f} g/s")
        
        # Outlet composition
        stream("\nOutlet Composition:")
        for ion in self.config.target_ions + [self.config.regenerant_ion]:
            if hasattr(self.outputs, f"{ion}_out"):
                flow = value(getattr(self.outputs, f"{ion}_out"))
                stream(f"  {ion}: {flow*1000:.3f} g/s")
        
        # Performance
        stream("\nPerformance:")
        stream(f"  Hardness In: {value(self.hardness_in)*1000:.1f} g/s as CaCO3")
        stream(f"  Hardness Out: {value(self.hardness_out)*1000:.1f} g/s as CaCO3")
        stream(f"  Hardness Removal: {value(self.hardness_removal_percent):.1f}%")
        stream(f"  Resin Utilization: {value(self.resin_utilization)*100:.1f}%")
        
        # Individual ion removal
        stream("\nIon Removal:")
        for ion in self.config.target_ions:
            if hasattr(self.outputs, f"{ion}_removal"):
                removal = value(getattr(self.outputs, f"{ion}_removal"))
                inlet = value(getattr(self.inputs, f"{ion}_in"))
                if inlet > 0:
                    percent = removal / inlet * 100
                    stream(f"  {ion}: {removal*1000:.3f} g/s ({percent:.1f}%)")
        
        # Breakthrough (if included)
        if self.config.include_breakthrough and hasattr(self.outputs, 'breakthrough_time'):
            stream("\nBreakthrough:")
            stream(f"  Time to breakthrough: {value(self.outputs.breakthrough_time):.1f} hours")
            stream(f"  Bed volumes: {value(self.bed_volumes_to_breakthrough):.1f} BV")
        
        stream("=" * 60)