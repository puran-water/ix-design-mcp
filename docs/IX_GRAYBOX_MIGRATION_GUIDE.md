# IX GrayBox Migration Guide

## Table of Contents
1. [Introduction](#introduction)
2. [What are GrayBox Models?](#what-are-graybox-models)
3. [Benefits for IX Modeling](#benefits-for-ix-modeling)
4. [Migration Steps](#migration-steps)
5. [Implementation Examples](#implementation-examples)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)
8. [Performance Considerations](#performance-considerations)

## Introduction

This guide provides comprehensive instructions for migrating Ion Exchange (IX) models from standard IDAES/WaterTAP implementations to GrayBox models that directly interface with PHREEQC for enhanced geochemical accuracy.

## What are GrayBox Models?

GrayBox models in Pyomo are external function interfaces that allow integration of black-box calculations within optimization frameworks. For IX modeling, GrayBox enables:

- Direct PHREEQC equilibrium calculations within the optimization model
- Accurate speciation and activity coefficient calculations
- Complex ion exchange equilibria with multiple competing ions
- Temperature and ionic strength effects on selectivity

### Architecture Overview

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   IDAES/WaterTAP   │────▶│  GrayBox Block   │────▶│    PHREEQC      │
│   Property Model    │     │  (Interface)     │     │   Executable    │
└─────────────────────┘     └──────────────────┘     └─────────────────┘
         ▲                           │                         │
         │                           │                         │
         └───────────────────────────┴─────────────────────────┘
                        Material Balance Loop
```

## Benefits for IX Modeling

### 1. **Improved Accuracy**
- PHREEQC provides rigorous activity coefficient models (Davies, Debye-Hückel, Pitzer)
- Accurate handling of ion pairing and complexation
- Temperature-dependent equilibrium constants

### 2. **Flexibility**
- Easy switching between thermodynamic databases
- Support for trace species without modifying Pyomo model
- Custom exchange reactions and selectivities

### 3. **Reduced Development Time**
- No need to implement complex equilibrium calculations in Pyomo
- Leverage existing PHREEQC databases and models
- Validated thermodynamic data

## Migration Steps

### Step 1: Assess Current Model

Identify components in your existing IX model:

```python
# Existing standard IX model
from watertap_ix_transport import IonExchangeTransport0D

m.fs.ix_unit = IonExchangeTransport0D(
    property_package=m.fs.properties,
    resin_type=ResinType.SAC,
    regenerant=RegenerantChem.NaCl
)
```

### Step 2: Choose GrayBox Implementation

Two options are available:

1. **Simple GrayBox** (`PhreeqcIXBlockSimple`)
   - Pre-defined inputs/outputs
   - Easier to implement
   - Limited customization

2. **Full GrayBox** (`PhreeqcIXBlock`)
   - Complete flexibility
   - Custom state definitions
   - Advanced features

### Step 3: Define PHREEQC State

For full GrayBox implementation:

```python
from phreeqc_pse.core.phreeqc_state import PhreeqcState

# Define system state
phreeqc_state = PhreeqcState(
    database="phreeqc.dat",  # or pitzer.dat for high TDS
    components=['Ca_2+', 'Mg_2+', 'Na_+', 'Cl_-', 'HCO3_-'],
    phases=['Aqueous'],
    temperature=298.15,
    pressure=101325
)

# Add ion exchange
phreeqc_state.add_ion_exchange(
    site_name='X',
    capacity=2.0,  # eq/L
    exchanger_species=['CaX2', 'MgX2', 'NaX', 'KX']
)
```

### Step 4: Create GrayBox Block

```python
from phreeqc_pse.blocks.phreeqc_ix_block import PhreeqcIXBlock

# Replace standard IX unit with GrayBox
m.fs.ix_graybox = PhreeqcIXBlock(
    phreeqc_state=phreeqc_state,
    feed_composition=feed_comp_dict,
    column_parameters=column_params
)
```

### Step 5: Connect to Flowsheet

```python
# Connect inlet streams
@m.fs.Constraint()
def connect_feed_to_graybox(b):
    return b.ix_graybox.inputs['flow_rate'] == b.feed.outlet.flow_vol[0]

# Connect outlet streams  
@m.fs.Constraint()
def connect_graybox_to_product(b):
    return b.product.inlet.conc_mass_comp[0, 'Ca_2+'] == \
           b.ix_graybox.outputs['Ca_2+']
```

## Implementation Examples

### Example 1: Simple GrayBox Migration

```python
# Before: Standard IX model
m.fs.ix_unit = IonExchangeTransport0D(
    property_package=properties,
    resin_type=ResinType.SAC
)
m.fs.ix_unit.bed_depth.fix(2.0)
m.fs.ix_unit.bed_diameter.fix(1.5)

# After: Simple GrayBox
from phreeqc_pse.blocks.phreeqc_ix_block_simple import PhreeqcIXBlockSimple

m.fs.ix_graybox = PhreeqcIXBlockSimple(
    database="phreeqc.dat",
    resin_type="SAC",
    resin_capacity=2.0
)

# Initialize with feed conditions
m.fs.ix_graybox.initialize(
    feed_composition={
        'Ca': 180,  # mg/L
        'Mg': 80,
        'Na': 50,
        'pH': 7.5,
        'temperature': 25
    },
    column_params={
        'bed_volume': 3.53,  # m³
        'flow_rate': 100     # m³/hr
    }
)
```

### Example 2: Full GrayBox with Custom Database

```python
# Use Pitzer database for high salinity water
phreeqc_state = PhreeqcState(
    database="pitzer.dat",
    components=['Ca_2+', 'Mg_2+', 'Na_+', 'Cl_-', 'SO4_2-'],
    temperature=298.15
)

# Add exchange with custom selectivities
phreeqc_state.add_ion_exchange(
    site_name='X',
    capacity=1.8,
    exchanger_species=['CaX2', 'MgX2', 'NaX']
)

# Create GrayBox with minerals
phreeqc_state.add_mineral('Gypsum', saturation_index=0)
phreeqc_state.add_mineral('Calcite', saturation_index=0)

m.fs.ix_graybox = PhreeqcIXBlock(
    phreeqc_state=phreeqc_state,
    feed_composition=high_tds_feed
)
```

### Example 3: Migrating Constraints

```python
# Before: Manual selectivity constraints
@m.fs.Constraint()
def ca_na_selectivity(b, t):
    K_Ca_Na = 5.16
    return (b.ix_unit.resin_ca[t] * b.solution_na[t]**2) == \
           K_Ca_Na * (b.resin_na[t]**2 * b.solution_ca[t])

# After: Handled automatically by PHREEQC
# No manual constraints needed - PHREEQC uses database values
```

## Best Practices

### 1. **Database Selection**
- Use `phreeqc.dat` for standard conditions
- Use `pitzer.dat` for TDS > 10,000 mg/L
- Use `minteq.dat` for trace metals

### 2. **State Definition**
- Include all major ions in component list
- Add H+ and OH- for pH calculations
- Define appropriate exchange capacity

### 3. **Initialization**
```python
# Always initialize GrayBox before solving
m.fs.ix_graybox.initialize(
    feed_composition=feed_dict,
    column_params=column_dict
)

# Then solve full model
solver = SolverFactory('ipopt')
solver.solve(m, tee=True)
```

### 4. **Scaling**
```python
# Scale GrayBox variables for better convergence
m.fs.ix_graybox.outputs['Ca_2+'].setlb(0)
m.fs.ix_graybox.outputs['Ca_2+'].setub(200)
m.fs.ix_graybox.scaling_factor['Ca_2+'] = 1e-2
```

## Troubleshooting

### Common Issues and Solutions

#### 1. **PHREEQC Not Found**
```
Error: PHREEQC executable not found
```
**Solution**: Set PHREEQC path explicitly:
```python
os.environ['PHREEQC_PATH'] = r'C:\Program Files\USGS\phreeqc\bin\phreeqc.bat'
```

#### 2. **Database File Missing**
```
Error: Database file 'phreeqc.dat' not found
```
**Solution**: Use absolute path:
```python
database_path = r'C:\Program Files\USGS\phreeqc\database\phreeqc.dat'
```

#### 3. **Convergence Issues**
```
Warning: GrayBox function evaluation failed
```
**Solution**: 
- Check feed composition bounds
- Ensure positive concentrations
- Verify charge balance
- Use tighter variable bounds

#### 4. **Species Not in Database**
```
Error: Unknown species 'Fe_3+'
```
**Solution**: 
- Check species naming (Fe+3 vs Fe_3+)
- Use appropriate database
- Define custom species if needed

### Debugging Tips

1. **Enable PHREEQC Output**
```python
m.fs.ix_graybox.keep_phreeqc_files = True
# Check generated files in temp directory
```

2. **Test PHREEQC Independently**
```python
# Generate input file
input_str = m.fs.ix_graybox.generate_phreeqc_input()
print(input_str)
# Run in PHREEQC GUI to debug
```

3. **Check Mass Balance**
```python
# Verify mass balance closure
inlet_tds = sum(feed_composition.values())
outlet_tds = sum(m.fs.ix_graybox.outputs[ion].value 
                 for ion in ions)
print(f"Mass balance error: {abs(inlet_tds - outlet_tds)/inlet_tds * 100}%")
```

## Performance Considerations

### Execution Time
- GrayBox adds ~0.1-0.5s per function evaluation
- Use warm starts when possible
- Cache PHREEQC results for repeated calculations

### Memory Usage
- Each GrayBox call creates temporary files
- Clean up temp files after optimization:
```python
import shutil
shutil.rmtree(temp_dir)
```

### Parallel Execution
- PHREEQC calls can be parallelized:
```python
from multiprocessing import Pool

def evaluate_graybox_parallel(feed_conditions):
    with Pool(processes=4) as pool:
        results = pool.map(graybox_evaluation, feed_conditions)
    return results
```

### Optimization Strategies

1. **Use Bounds**
```python
# Tight bounds improve convergence
m.fs.ix_graybox.outputs['Ca_2+'].setlb(0.1)  # mg/L
m.fs.ix_graybox.outputs['Ca_2+'].setub(50)   # mg/L
```

2. **Initial Guesses**
```python
# Provide good initial values
m.fs.ix_graybox.outputs['Ca_2+'].set_value(10)
m.fs.ix_graybox.outputs['pH'].set_value(7.5)
```

3. **Solver Options**
```python
solver = SolverFactory('ipopt')
solver.options['mu_strategy'] = 'adaptive'
solver.options['nlp_scaling_method'] = 'gradient-based'
```

## Conclusion

Migrating to GrayBox models provides significant advantages for IX modeling:
- Improved accuracy through rigorous thermodynamics
- Reduced model development time
- Access to validated databases
- Flexibility for complex systems

Start with simple GrayBox for standard applications and progress to full GrayBox for advanced features.

For questions or issues, consult:
- PHREEQC documentation: https://www.usgs.gov/software/phreeqc
- Pyomo GrayBox docs: https://pyomo.readthedocs.io/
- WaterTAP forums: https://github.com/watertap-org/watertap