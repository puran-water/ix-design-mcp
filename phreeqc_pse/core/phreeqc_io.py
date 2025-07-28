"""
PHREEQC Input/Output Specifications
Defines the input and output variable specifications for PHREEQC GrayBox models
"""

from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from pyomo.environ import Var, units as pyunits
import logging

logger = logging.getLogger(__name__)


class VariableType(Enum):
    """Types of variables in PHREEQC models"""
    FLOW = "flow"
    CONCENTRATION = "concentration"
    MOLE_FRACTION = "mole_fraction"
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    PH = "pH"
    PE = "pe"
    IONIC_STRENGTH = "ionic_strength"
    ACTIVITY = "activity"
    FUGACITY = "fugacity"
    SATURATION_INDEX = "saturation_index"
    EXCHANGE_FRACTION = "exchange_fraction"
    REMOVAL_RATE = "removal_rate"
    

class PhreeqcInputSpec:
    """
    Specification for PHREEQC model inputs
    
    Manages the mapping between Pyomo variables and PHREEQC inputs
    """
    
    def __init__(self):
        """Initialize input specification"""
        self.specs = []
        self._name_to_spec = {}
        
    def add_flow_input(self, 
                      component: str,
                      phase: str = "Liq",
                      units: Any = pyunits.kg/pyunits.s,
                      bounds: Tuple[float, float] = (0, None),
                      default: float = 0.001):
        """
        Add component flow rate input
        
        Args:
            component: Component name (e.g., 'Ca', 'Mg')
            phase: Phase (default 'Liq')
            units: Pyomo units
            bounds: Variable bounds
            default: Default value
        """
        name = f"{component}_in"
        spec = {
            'name': name,
            'type': VariableType.FLOW,
            'component': component,
            'phase': phase,
            'units': units,
            'bounds': bounds,
            'default': default,
            'phreeqc_key': component  # Key in PHREEQC input
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
        
    def add_system_input(self,
                        var_type: VariableType,
                        name: Optional[str] = None,
                        units: Any = None,
                        bounds: Tuple[float, float] = None,
                        default: float = None):
        """
        Add system variable input (T, P, pH, etc.)
        
        Args:
            var_type: Variable type
            name: Variable name (defaults to type name)
            units: Pyomo units
            bounds: Variable bounds
            default: Default value
        """
        # Set defaults based on type
        if name is None:
            name = var_type.value
            
        if units is None:
            if var_type == VariableType.TEMPERATURE:
                units = pyunits.K
                bounds = bounds or (273.15, 373.15)
                default = default or 298.15
            elif var_type == VariableType.PRESSURE:
                units = pyunits.Pa
                bounds = bounds or (1e4, 1e6)
                default = default or 101325
            elif var_type == VariableType.PH:
                units = pyunits.dimensionless
                bounds = bounds or (0, 14)
                default = default or 7.0
            elif var_type == VariableType.PE:
                units = pyunits.dimensionless
                bounds = bounds or (-20, 20)
                default = default or 4.0
        
        spec = {
            'name': name,
            'type': var_type,
            'units': units,
            'bounds': bounds,
            'default': default,
            'phreeqc_key': name
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
    
    def add_column_input(self,
                        name: str,
                        description: str,
                        units: Any,
                        bounds: Tuple[float, float],
                        default: float):
        """
        Add column design parameter input
        
        Args:
            name: Parameter name (e.g., 'bed_volume')
            description: Parameter description
            units: Pyomo units
            bounds: Variable bounds
            default: Default value
        """
        spec = {
            'name': name,
            'type': VariableType.FLOW,  # Treat as flow type
            'description': description,
            'units': units,
            'bounds': bounds,
            'default': default,
            'phreeqc_key': name
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
    
    def get_input_names(self) -> List[str]:
        """Get list of all input variable names"""
        return [spec['name'] for spec in self.specs]
    
    def get_spec(self, name: str) -> Dict:
        """Get specification for a named input"""
        return self._name_to_spec.get(name, None)
    
    def build_pyomo_inputs(self, block):
        """
        Build Pyomo input variables on a block
        
        Args:
            block: Pyomo block to add variables to
        """
        block.inputs = Var()
        
        for spec in self.specs:
            var = Var(
                initialize=spec['default'],
                bounds=spec['bounds'],
                units=spec['units'],
                doc=spec.get('description', f"{spec['type'].value} input")
            )
            setattr(block.inputs, spec['name'], var)
            
        logger.info(f"Built {len(self.specs)} input variables")
        
    def to_phreeqc_dict(self, input_values: Dict[str, float]) -> Dict[str, Any]:
        """
        Convert Pyomo input values to PHREEQC format
        
        Args:
            input_values: Dictionary of input values
            
        Returns:
            Dictionary formatted for PHREEQC
        """
        phreeqc_inputs = {}
        
        for spec in self.specs:
            name = spec['name']
            if name in input_values:
                value = input_values[name]
                key = spec['phreeqc_key']
                
                # Convert units if needed
                if spec['type'] == VariableType.TEMPERATURE and spec['units'] == pyunits.K:
                    # Convert K to °C for PHREEQC
                    value = value - 273.15
                elif spec['type'] == VariableType.PRESSURE and spec['units'] == pyunits.Pa:
                    # Convert Pa to atm for PHREEQC
                    value = value / 101325
                
                phreeqc_inputs[key] = value
                
        return phreeqc_inputs


class PhreeqcOutputSpec:
    """
    Specification for PHREEQC model outputs
    
    Manages the mapping between PHREEQC results and Pyomo variables
    """
    
    def __init__(self):
        """Initialize output specification"""
        self.specs = []
        self._name_to_spec = {}
        
    def add_flow_output(self,
                       component: str,
                       phase: str = "Liq",
                       units: Any = pyunits.kg/pyunits.s,
                       bounds: Tuple[float, float] = (0, None)):
        """
        Add component flow rate output
        
        Args:
            component: Component name
            phase: Phase
            units: Pyomo units
            bounds: Variable bounds
        """
        name = f"{component}_out"
        spec = {
            'name': name,
            'type': VariableType.FLOW,
            'component': component,
            'phase': phase,
            'units': units,
            'bounds': bounds,
            'phreeqc_key': f"effluent_{component}_mg_L"
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
        
    def add_removal_output(self,
                          component: str,
                          units: Any = pyunits.kg/pyunits.s,
                          bounds: Tuple[float, float] = (None, None)):
        """
        Add removal rate output
        
        Args:
            component: Component name
            units: Pyomo units
            bounds: Variable bounds
        """
        name = f"{component}_removal"
        spec = {
            'name': name,
            'type': VariableType.REMOVAL_RATE,
            'component': component,
            'units': units,
            'bounds': bounds,
            'phreeqc_key': f"{component}_removal_rate"
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
        
    def add_system_output(self,
                         var_type: VariableType,
                         name: Optional[str] = None,
                         units: Any = None,
                         bounds: Tuple[float, float] = None):
        """
        Add system variable output
        
        Args:
            var_type: Variable type
            name: Variable name
            units: Pyomo units
            bounds: Variable bounds
        """
        if name is None:
            name = f"{var_type.value}_out"
            
        if units is None:
            if var_type == VariableType.PH:
                units = pyunits.dimensionless
                bounds = bounds or (0, 14)
            elif var_type == VariableType.IONIC_STRENGTH:
                units = pyunits.mol/pyunits.L
                bounds = bounds or (0, 10)
                
        spec = {
            'name': name,
            'type': var_type,
            'units': units,
            'bounds': bounds,
            'phreeqc_key': var_type.value
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
        
    def add_exchange_output(self,
                           species: str,
                           units: Any = pyunits.dimensionless,
                           bounds: Tuple[float, float] = (0, 1)):
        """
        Add ion exchange fraction output
        
        Args:
            species: Exchange species (e.g., 'CaX2')
            units: Pyomo units
            bounds: Variable bounds
        """
        name = f"{species}_fraction"
        spec = {
            'name': name,
            'type': VariableType.EXCHANGE_FRACTION,
            'species': species,
            'units': units,
            'bounds': bounds,
            'phreeqc_key': f"exchange_{species}"
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
        
    def add_breakthrough_output(self,
                               name: str = "breakthrough_time",
                               units: Any = pyunits.hour,
                               bounds: Tuple[float, float] = (0, None)):
        """
        Add breakthrough time output
        
        Args:
            name: Variable name
            units: Pyomo units
            bounds: Variable bounds
        """
        spec = {
            'name': name,
            'type': VariableType.FLOW,  # Generic type
            'units': units,
            'bounds': bounds,
            'phreeqc_key': 'breakthrough_time'
        }
        self.specs.append(spec)
        self._name_to_spec[name] = spec
        
    def get_output_names(self) -> List[str]:
        """Get list of all output variable names"""
        return [spec['name'] for spec in self.specs]
    
    def get_spec(self, name: str) -> Dict:
        """Get specification for a named output"""
        return self._name_to_spec.get(name, None)
    
    def build_pyomo_outputs(self, block):
        """
        Build Pyomo output variables on a block
        
        Args:
            block: Pyomo block to add variables to
        """
        block.outputs = Var()
        
        for spec in self.specs:
            var = Var(
                initialize=0,
                bounds=spec['bounds'],
                units=spec['units'],
                doc=f"{spec['type'].value} output"
            )
            setattr(block.outputs, spec['name'], var)
            
        logger.info(f"Built {len(self.specs)} output variables")
        
    def from_phreeqc_dict(self, phreeqc_results: Dict[str, Any]) -> Dict[str, float]:
        """
        Convert PHREEQC results to output values
        
        Args:
            phreeqc_results: PHREEQC calculation results
            
        Returns:
            Dictionary of output values
        """
        output_values = {}
        
        for spec in self.specs:
            name = spec['name']
            key = spec['phreeqc_key']
            
            if key in phreeqc_results:
                value = phreeqc_results[key]
                
                # Handle array results (e.g., breakthrough curves)
                if isinstance(value, (list, tuple)):
                    if len(value) > 0:
                        # Use average or specific value
                        value = sum(value) / len(value)
                    else:
                        value = 0
                
                # Convert units if needed
                if spec['type'] == VariableType.CONCENTRATION:
                    # PHREEQC returns mg/L, might need mol/L
                    pass  # Handle conversion based on units
                    
                output_values[name] = float(value)
            else:
                # Default value if not found
                output_values[name] = 0.0
                
        return output_values