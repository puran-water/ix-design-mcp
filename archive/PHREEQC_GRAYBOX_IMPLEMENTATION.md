# PHREEQC GrayBox Implementation Documentation

## Overview

This document describes the implementation of a PHREEQC GrayBox model following the Reaktoro-PSE architectural pattern. The GrayBox model allows PHREEQC equilibrium calculations to be seamlessly integrated into IDAES/WaterTAP optimization frameworks.

## Architecture

The implementation consists of several key components:

### 1. Core Components (`phreeqc_pse/core/`)

#### PhreeqcState (`phreeqc_state.py`)
- Manages system configuration (components, phases, temperature, pressure)
- Handles ion exchange, mineral equilibrium, and gas phase specifications
- Generates PHREEQC input templates
- Provides serialization/deserialization capabilities

#### PhreeqcInputSpec & PhreeqcOutputSpec (`phreeqc_io.py`)
- Define variable specifications for model inputs/outputs
- Handle unit conversions between Pyomo and PHREEQC
- Support various variable types (flows, concentrations, system properties)
- Build Pyomo variables automatically

#### PhreeqcSolver (`phreeqc_solver.py`)
- Wraps DirectPhreeqcEngine for equilibrium calculations
- Converts between Pyomo variable format and PHREEQC input/output
- Implements caching for performance
- Provides fallback values on solver failures

#### PhreeqcGrayBox (`phreeqc_gray_box.py`)
- Implements Pyomo's ExternalGreyBoxModel interface
- Manages input/output evaluation
- Calculates Jacobians (analytical or numerical)
- Handles solver iterations and caching

#### PhreeqcBlock (`phreeqc_block.py`)
- Main IDAES block for general PHREEQC equilibrium
- Creates and manages the GrayBox model
- Links Pyomo variables to GrayBox inputs/outputs
- Provides initialization and reporting methods

### 2. Specialized Blocks (`phreeqc_pse/blocks/`)

#### PhreeqcIXBlock (`phreeqc_ix_block.py`)
- Specialized block for ion exchange applications
- Adds IX-specific parameters (selectivity, capacity)
- Calculates hardness removal and resin utilization
- Includes breakthrough time calculations
- Provides detailed IX performance reporting

## Usage Example

```python
from phreeqc_pse.blocks.phreeqc_ix_block import PhreeqcIXBlock
from pyomo.environ import ConcreteModel, SolverFactory

# Create model
m = ConcreteModel()

# Create ion exchange unit
m.ix_unit = PhreeqcIXBlock(
    resin_type='SAC',           # Strong Acid Cation resin
    exchange_capacity=2.0,       # eq/L
    target_ions=['Ca', 'Mg'],    # Ions to remove
    regenerant_ion='Na',         # Regenerant
    include_breakthrough=True,   # Calculate breakthrough
    use_direct_phreeqc=True     # Use DirectPhreeqcEngine
)

# Set inlet conditions (kg/s)
m.ix_unit.inputs.Ca_in.fix(0.0002)   # 200 mg/L at 1 L/s
m.ix_unit.inputs.Mg_in.fix(0.00005)  # 50 mg/L at 1 L/s
m.ix_unit.inputs.Na_in.fix(0.0001)   # 100 mg/L at 1 L/s

# Set system conditions
m.ix_unit.inputs.temperature.fix(298.15)  # K
m.ix_unit.inputs.pressure.fix(101325)     # Pa
m.ix_unit.inputs.pH.fix(7.0)

# Initialize and solve
m.ix_unit.initialize_build()
solver = SolverFactory('ipopt')
results = solver.solve(m)

# Report results
m.ix_unit.report()
```

## Key Features

### 1. Proper Pyomo Integration
- Uses ExternalGreyBoxModel for black-box integration
- Supports analytical and numerical Jacobians
- Handles variable scaling automatically
- Compatible with all Pyomo solvers

### 2. Flexible Configuration
- Customizable input/output specifications
- Support for different resin types (SAC, WAC, SBA, WBA)
- Configurable system conditions and components
- Optional features (breakthrough, minerals, gas phase)

### 3. Performance Optimization
- Result caching to minimize PHREEQC calls
- Efficient Jacobian calculation
- Sparse matrix representation
- Fallback mechanisms for robustness

### 4. IX-Specific Features
- Hardness removal calculations
- Resin utilization tracking
- Breakthrough time prediction
- Individual ion removal rates
- Exchange fraction monitoring

## Integration with Existing Code

The GrayBox model is designed to replace the current direct integration approach that has issues with mass balance enforcement. Key improvements:

1. **Proper constraint handling**: The GrayBox model ensures all mass balance constraints are satisfied through Pyomo's optimization framework.

2. **No manual mass transfer updates**: The optimizer handles all variable updates based on the PHREEQC equilibrium results.

3. **Better convergence**: The Jacobian information helps the optimizer converge more reliably.

4. **Cleaner architecture**: Separation of concerns between PHREEQC calculations and IDAES modeling.

## Testing

A comprehensive test script (`test_phreeqc_graybox.py`) demonstrates:
- Basic GrayBox model usage
- Ion exchange calculations
- Comparison with direct PHREEQC results
- Validation of removal rates

## Next Steps

1. **Integration with IonExchangeTransport0D**: Replace the current PHREEQC integration in IonExchangeTransport0D with the GrayBox model.

2. **Extended validation**: Test with various feed compositions and operating conditions.

3. **Performance tuning**: Optimize Jacobian calculations and caching strategies.

4. **Additional features**: Add support for kinetic reactions, surface complexation, and other PHREEQC capabilities.

## Benefits Over Current Approach

1. **Solves the 0% removal issue**: Properly integrates PHREEQC results into the material balance.

2. **More robust**: Handles solver failures gracefully with fallback mechanisms.

3. **Better optimization**: Provides gradient information for efficient optimization.

4. **Cleaner code**: Follows established patterns from Reaktoro-PSE.

5. **Extensible**: Easy to add new features and capabilities.

## Conclusion

The PHREEQC GrayBox implementation provides a robust, efficient, and maintainable solution for integrating PHREEQC equilibrium calculations into IDAES/WaterTAP models. It follows best practices from the Reaktoro-PSE project and addresses the current integration issues while providing a foundation for future enhancements.