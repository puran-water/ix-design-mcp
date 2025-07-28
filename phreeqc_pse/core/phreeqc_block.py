"""
PHREEQC Block for IDAES Integration
Main block that integrates PHREEQC equilibrium calculations with IDAES/WaterTAP
"""

from pyomo.environ import (
    Block, Var, Constraint, Param, Set as PyomoSet,
    Reference, units as pyunits, value, log10
)
from pyomo.contrib.pynumero.interfaces.external_grey_box import ExternalGreyBoxBlock
from idaes.core import declare_process_block_class, ProcessBlockData
from pyomo.common.config import ConfigBlock, ConfigValue, In
# InitializationStatus is defined differently in different IDAES versions
try:
    from idaes.core.util.initialization import InitializationStatus
except ImportError:
    from enum import Enum
    class InitializationStatus(Enum):
        Ok = "optimal"
        Error = "error"
import idaes.logger as idaeslog

from .phreeqc_gray_box import PhreeqcGrayBox
from .phreeqc_solver import PhreeqcSolver
from .phreeqc_state import PhreeqcState
from .phreeqc_io import PhreeqcInputSpec, PhreeqcOutputSpec, VariableType

import logging

logger = logging.getLogger(__name__)
init_logger = idaeslog.getInitLogger(__name__, level=logging.INFO)


@declare_process_block_class("PhreeqcBlock")
class PhreeqcBlockData(ProcessBlockData):
    """
    PHREEQC equilibrium block for IDAES
    
    This block wraps PHREEQC equilibrium calculations in an IDAES-compatible
    format using Pyomo's ExternalGreyBoxBlock.
    """
    
    CONFIG = ConfigBlock()
    
    CONFIG.declare("phreeqc_state", ConfigValue(
        default=None,
        domain=None,
        description="PhreeqcState object defining system configuration",
        doc="PhreeqcState instance or dict to create one"
    ))
    
    CONFIG.declare("input_specs", ConfigValue(
        default=None,
        domain=None,
        description="PhreeqcInputSpec defining inputs",
        doc="Input specification object"
    ))
    
    CONFIG.declare("output_specs", ConfigValue(
        default=None,
        domain=None,
        description="PhreeqcOutputSpec defining outputs",
        doc="Output specification object"
    ))
    
    CONFIG.declare("database", ConfigValue(
        default="phreeqc.dat",
        domain=str,
        description="PHREEQC database file",
        doc="Path to PHREEQC database"
    ))
    
    CONFIG.declare("use_direct_phreeqc", ConfigValue(
        default=True,
        domain=bool,
        description="Use DirectPhreeqcEngine",
        doc="Whether to use direct PHREEQC execution"
    ))
    
    CONFIG.declare("solver_options", ConfigValue(
        default={},
        domain=dict,
        description="Options for PHREEQC solver",
        doc="Additional solver configuration"
    ))
    
    def build(self):
        """
        Build the PHREEQC block
        """
        super().build()
        
        # Initialize state
        if self.config.phreeqc_state is None:
            # Create default state
            self.phreeqc_state = PhreeqcState(
                database=self.config.database,
                components=['H2O', 'H+', 'OH-', 'Ca', 'Mg', 'Na', 'Cl', 'SO4', 'HCO3']
            )
        elif isinstance(self.config.phreeqc_state, dict):
            # Create from dict
            self.phreeqc_state = PhreeqcState.from_dict(self.config.phreeqc_state)
        else:
            self.phreeqc_state = self.config.phreeqc_state
            
        # Initialize I/O specs
        if self.config.input_specs is None:
            self.input_specs = self._create_default_input_specs()
        else:
            self.input_specs = self.config.input_specs
            
        if self.config.output_specs is None:
            self.output_specs = self._create_default_output_specs()
        else:
            self.output_specs = self.config.output_specs
        
        # Build Pyomo sets from state
        self.phreeqc_state.build_pyomo_sets(self)
        
        # Build input/output variables
        self.input_specs.build_pyomo_inputs(self)
        self.output_specs.build_pyomo_outputs(self)
        
        # Create PHREEQC solver
        self.phreeqc_solver = PhreeqcSolver(
            database=self.config.database,
            use_direct_phreeqc=self.config.use_direct_phreeqc
        )
        
        # Create GrayBox model
        self.phreeqc_graybox = PhreeqcGrayBox()
        self.phreeqc_graybox.configure(
            phreeqc_solver=self.phreeqc_solver,
            inputs=self.input_specs.get_input_names(),
            outputs=self.output_specs.get_output_names()
        )
        
        # Create ExternalGreyBoxBlock
        self.graybox_block = ExternalGreyBoxBlock()
        self.graybox_block.set_external_model(self.phreeqc_graybox)
        
        # Link variables
        self._link_variables()
        
        # Add additional constraints if needed
        self._add_constraints()
        
        logger.info(f"PhreeqcBlock built with {len(self.input_specs.specs)} inputs, "
                   f"{len(self.output_specs.specs)} outputs")
    
    def _create_default_input_specs(self):
        """Create default input specifications"""
        specs = PhreeqcInputSpec()
        
        # Add component flows
        for comp in ['Ca', 'Mg', 'Na', 'Cl', 'SO4', 'HCO3']:
            specs.add_flow_input(comp)
        
        # Add system variables
        specs.add_system_input(VariableType.TEMPERATURE)
        specs.add_system_input(VariableType.PRESSURE)
        specs.add_system_input(VariableType.PH)
        
        return specs
    
    def _create_default_output_specs(self):
        """Create default output specifications"""
        specs = PhreeqcOutputSpec()
        
        # Add component flows
        for comp in ['Ca', 'Mg', 'Na', 'Cl', 'SO4', 'HCO3']:
            specs.add_flow_output(comp)
            specs.add_removal_output(comp)
        
        # Add system outputs
        specs.add_system_output(VariableType.PH)
        specs.add_system_output(VariableType.IONIC_STRENGTH)
        
        return specs
    
    def _link_variables(self):
        """Link block variables to GrayBox inputs/outputs"""
        
        # Create references for easier access
        self.graybox_inputs = Reference(self.graybox_block.inputs[:])
        self.graybox_outputs = Reference(self.graybox_block.outputs[:])
        
        # Link input variables
        @self.Constraint(self.input_specs.get_input_names())
        def link_inputs(b, input_name):
            idx = self.input_specs.get_input_names().index(input_name)
            return self.inputs[input_name] == self.graybox_inputs[idx]
        
        # Link output variables
        @self.Constraint(self.output_specs.get_output_names())
        def link_outputs(b, output_name):
            idx = self.output_specs.get_output_names().index(output_name)
            return self.outputs[output_name] == self.graybox_outputs[idx]
    
    def _add_constraints(self):
        """Add additional constraints"""
        
        # Charge balance constraint (optional)
        if hasattr(self, 'component_list'):
            charge_dict = {
                'Ca': 2, 'Mg': 2, 'Na': 1, 'K': 1,
                'Cl': -1, 'SO4': -2, 'HCO3': -1
            }
            
            @self.Constraint()
            def charge_balance(b):
                charge_sum = 0
                for comp in b.component_list:
                    if comp in charge_dict and hasattr(b.outputs, f"{comp}_out"):
                        charge_sum += charge_dict[comp] * getattr(b.outputs, f"{comp}_out")
                return charge_sum == 0
        
        # Mass balance for water (optional)
        if hasattr(self.inputs, 'H2O_in') and hasattr(self.outputs, 'H2O_out'):
            @self.Constraint()
            def water_balance(b):
                return b.inputs.H2O_in == b.outputs.H2O_out
    
    def initialize_build(self, **kwargs):
        """
        Initialize the PHREEQC block
        
        Args:
            **kwargs: Additional initialization options
        """
        init_logger.info("Beginning PhreeqcBlock initialization...")
        
        # Set initial values for inputs
        for spec in self.input_specs.specs:
            var = getattr(self.inputs, spec['name'])
            if var.value is None:
                var.set_value(spec['default'])
        
        # Evaluate GrayBox to get initial outputs
        try:
            input_values = {
                spec['name']: value(getattr(self.inputs, spec['name']))
                for spec in self.input_specs.specs
            }
            
            # Convert to array for GrayBox
            input_array = [input_values[name] for name in self.input_specs.get_input_names()]
            self.phreeqc_graybox.set_input_values(input_array)
            
            # Evaluate
            output_array = self.phreeqc_graybox.evaluate_outputs()
            
            # Set output values
            for i, name in enumerate(self.output_specs.get_output_names()):
                var = getattr(self.outputs, name)
                var.set_value(output_array[i])
                
            init_logger.info("PhreeqcBlock initialization completed successfully")
            return InitializationStatus.Ok
            
        except Exception as e:
            init_logger.error(f"PhreeqcBlock initialization failed: {e}")
            return InitializationStatus.Error
    
    def calculate_scaling_factors(self):
        """Calculate scaling factors for variables"""
        
        # Input scaling
        for spec in self.input_specs.specs:
            var = getattr(self.inputs, spec['name'])
            if spec['type'] == VariableType.FLOW:
                # Scale flows to ~1 g/s
                if value(var) > 0:
                    self.scaling_factor[var] = 1000 / value(var)
            elif spec['type'] == VariableType.TEMPERATURE:
                # Scale around 298K
                self.scaling_factor[var] = 1 / 298.15
            elif spec['type'] == VariableType.PRESSURE:
                # Scale around 1 atm
                self.scaling_factor[var] = 1 / 101325
        
        # Output scaling
        output_scaling = self.phreeqc_graybox.get_output_constraint_scaling_factors()
        for i, name in enumerate(self.output_specs.get_output_names()):
            var = getattr(self.outputs, name)
            self.scaling_factor[var] = output_scaling[i]
    
    def report(self, index=0, stream=None):
        """
        Generate report of PHREEQC block state
        
        Args:
            index: Time index
            stream: Output stream
        """
        if stream is None:
            stream = logger.info
            
        stream("=" * 60)
        stream(f"PHREEQC Block Report")
        stream("=" * 60)
        
        # Inputs
        stream("\nInputs:")
        for spec in self.input_specs.specs:
            var = getattr(self.inputs, spec['name'])
            stream(f"  {spec['name']}: {value(var):.4g} {spec['units']}")
        
        # Outputs
        stream("\nOutputs:")
        for spec in self.output_specs.specs:
            var = getattr(self.outputs, spec['name'])
            stream(f"  {spec['name']}: {value(var):.4g} {spec['units']}")
        
        # Removal efficiency
        stream("\nRemoval Efficiency:")
        for comp in ['Ca', 'Mg', 'Na']:
            if hasattr(self.inputs, f"{comp}_in") and hasattr(self.outputs, f"{comp}_out"):
                inlet = value(getattr(self.inputs, f"{comp}_in"))
                outlet = value(getattr(self.outputs, f"{comp}_out"))
                if inlet > 0:
                    removal = (inlet - outlet) / inlet * 100
                    stream(f"  {comp}: {removal:.1f}%")
        
        stream("=" * 60)