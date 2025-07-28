# PHREEQC GrayBox Architecture Design

## Overview

Following the Reaktoro-PSE pattern, we should implement a proper GrayBox integration for PHREEQC that addresses the current issues with mass balance and removal rates.

## Proposed Architecture

### 1. Core Components

```
phreeqc_pse/
├── core/
│   ├── phreeqc_state.py          # Manages PHREEQC system configuration
│   ├── phreeqc_inputs.py         # Handles input specifications
│   ├── phreeqc_outputs.py        # Defines output properties
│   ├── phreeqc_jacobian.py       # Jacobian calculations
│   ├── phreeqc_solver.py         # Wraps DirectPhreeqcEngine
│   └── phreeqc_gray_box.py       # ExternalGreyBoxModel implementation
├── blocks/
│   ├── phreeqc_block.py          # Main IDAES block
│   └── phreeqc_block_builder.py  # Builds Pyomo blocks
└── transport/
    └── ix_transport_model.py     # Ion exchange specific model
```

### 2. Key Design Principles

#### A. PhreeqcGrayBox (similar to ReaktoroGrayBox)
```python
class PhreeqcGrayBox(ExternalGreyBoxModel):
    def configure(self, phreeqc_solver, inputs, outputs):
        self.phreeqc_solver = phreeqc_solver
        self.inputs = inputs  # e.g., ['Ca_feed', 'Mg_feed', 'Na_feed', ...]
        self.outputs = outputs  # e.g., ['Ca_out', 'Mg_out', 'Na_out', ...]
    
    def evaluate_outputs(self):
        # Run PHREEQC with current inputs
        results = self.phreeqc_solver.solve(self._input_values)
        return np.array(results)
    
    def evaluate_jacobian_outputs(self):
        # Calculate numerical derivatives
        return self.phreeqc_solver.calculate_jacobian()
```

#### B. PhreeqcBlock (similar to ReaktoroBlock)
```python
@declare_process_block_class("PhreeqcBlock")
class PhreeqcBlockData(ProcessBlockData):
    CONFIG = ProcessBlockData.CONFIG()
    
    def build(self):
        # Create state manager
        self.phreeqc_state = PhreeqcState()
        
        # Configure inputs/outputs
        self.phreeqc_inputs = PhreeqcInputSpec(self.phreeqc_state)
        self.phreeqc_outputs = PhreeqcOutputSpec(self.phreeqc_state)
        
        # Create solver
        self.phreeqc_solver = PhreeqcSolver(
            state=self.phreeqc_state,
            engine=DirectPhreeqcEngine()
        )
        
        # Build GrayBox
        self.gray_box = PhreeqcGrayBox()
        self.gray_box.configure(
            phreeqc_solver=self.phreeqc_solver,
            inputs=self.phreeqc_inputs.get_input_list(),
            outputs=self.phreeqc_outputs.get_output_list()
        )
```

### 3. Integration with Ion Exchange Model

Instead of the current approach where IonExchangeTransport0D directly manages PHREEQC calculations, we should:

1. **Create a dedicated PhreeqcIXBlock**:
   - Inherits from PhreeqcBlock
   - Configures exchange reactions
   - Handles breakthrough calculations
   
2. **Use proper material balance constraints**:
   ```python
   @self.Constraint(self.flowsheet().time, self.config.property_package.component_list)
   def material_balance(b, t, j):
       return b.outlet_flow[t, j] == b.inlet_flow[t, j] + b.gray_box.outputs[f"{j}_removal"]
   ```

3. **Let the GrayBox handle removal calculations**:
   - PHREEQC calculates equilibrium
   - GrayBox extracts removal rates
   - Pyomo constraints enforce mass balance

### 4. Benefits of This Approach

1. **Proper mass balance**: The GrayBox model ensures mass transfer terms are correctly linked
2. **Better numerical stability**: Automatic scaling and Jacobian calculations
3. **Cleaner separation**: PHREEQC logic separated from Pyomo constraints
4. **Easier debugging**: Can test PHREEQC calculations independently
5. **Parallel execution**: Can use BlockManager pattern for multiple units

### 5. Implementation Steps

1. **Phase 1**: Create core GrayBox infrastructure
   - Implement PhreeqcGrayBox with DirectPhreeqcEngine
   - Test with simple equilibrium calculations
   
2. **Phase 2**: Build PhreeqcBlock framework
   - Implement state, inputs, outputs, jacobian components
   - Create block builder
   
3. **Phase 3**: Create IX-specific implementation
   - PhreeqcIXBlock with exchange configuration
   - Breakthrough curve calculations
   - Integration with WaterTAP property packages
   
4. **Phase 4**: Replace current implementation
   - Refactor IonExchangeTransport0D to use PhreeqcIXBlock
   - Ensure backward compatibility

### 6. Example Usage

```python
from phreeqc_pse import PhreeqcIXBlock

m = ConcreteModel()
m.fs = FlowsheetBlock()

# Create property package
m.fs.properties = MCASParameterBlock(...)

# Create IX unit using PHREEQC GrayBox
m.fs.ix = PhreeqcIXBlock(
    property_package=m.fs.properties,
    database="phreeqc.dat",
    exchange_species={
        "X-": {"Na+": 1.0, "Ca+2": 0.5, "Mg+2": 0.45}  # selectivity
    },
    resin_capacity=2.0,  # eq/L
    bed_volume=1.0,      # m³
)

# Connect to property package
m.fs.ix.inlet.temperature.fix(298.15)
m.fs.ix.inlet.pressure.fix(101325)
# ... set flow rates ...

# Initialize and solve
m.fs.ix.initialize()
solver.solve(m)
```

## Conclusion

This architecture would provide a robust, maintainable solution that properly integrates PHREEQC with WaterTAP/IDAES while avoiding the current issues with mass balance and removal rate calculations. The GrayBox pattern ensures proper communication between PHREEQC and Pyomo's optimization framework.