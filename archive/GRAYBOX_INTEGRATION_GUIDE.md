# GrayBox Integration Guide for IonExchangeTransport0D

## Overview

The PhreeqcIXBlock GrayBox model provides a bullet-proof integration pattern for PHREEQC within IDAES/WaterTAP models. This guide explains how to integrate it into the existing IonExchangeTransport0D model.

## Key Benefits

1. **Automatic Mass Balance Enforcement**: The GrayBox model ensures mass balance constraints are satisfied through Pyomo's optimization framework
2. **Proper Jacobian Calculation**: Provides gradient information for efficient optimization
3. **No Manual Updates**: The optimizer handles all variable updates based on PHREEQC equilibrium
4. **Robust Integration**: Follows the proven Reaktoro-PSE pattern

## Integration Approach

### Option 1: Direct GrayBox Usage (Recommended)

Instead of using IonExchangeTransport0D, directly use the PhreeqcIXBlock:

```python
from phreeqc_pse.blocks.phreeqc_ix_block import PhreeqcIXBlock
from pyomo.environ import ConcreteModel, SolverFactory

# Create model
m = ConcreteModel()

# Create IX unit with GrayBox
m.ix_unit = PhreeqcIXBlock(
    resin_type='SAC',
    exchange_capacity=2.0,  # eq/L
    target_ions=['Ca', 'Mg'],
    regenerant_ion='Na',
    column_parameters={
        'bed_volume': 14.137,  # m³
        'flow_rate': 0.0278    # m³/s (100 m³/hr)
    },
    include_breakthrough=True,
    use_direct_phreeqc=True
)

# Set inlet conditions (kg/s)
m.ix_unit.inputs.Ca_in.fix(0.005)    # 180 mg/L at 100 m³/hr
m.ix_unit.inputs.Mg_in.fix(0.0022)   # 80 mg/L
m.ix_unit.inputs.Na_in.fix(0.0014)   # 50 mg/L
m.ix_unit.inputs.Cl_in.fix(0.014)    # 500 mg/L
m.ix_unit.inputs.HCO3_in.fix(0.005)  # 180 mg/L
m.ix_unit.inputs.SO4_in.fix(0.0067)  # 240 mg/L

# Set system conditions
m.ix_unit.inputs.temperature.fix(298.15)  # K
m.ix_unit.inputs.pressure.fix(101325)     # Pa
m.ix_unit.inputs.pH.fix(7.5)

# Column parameters
m.ix_unit.inputs.bed_volume.fix(14.137)  # m³
m.ix_unit.inputs.flow_rate.fix(0.0278)   # m³/s

# Initialize and solve
m.ix_unit.initialize_build()
solver = SolverFactory('ipopt')
results = solver.solve(m)

# Access results
ca_out = value(m.ix_unit.outputs.Ca_out)  # kg/s
mg_out = value(m.ix_unit.outputs.Mg_out)  # kg/s
breakthrough = value(m.ix_unit.outputs.breakthrough_time)  # hours
```

### Option 2: Wrapper Approach

Create a wrapper that uses PhreeqcIXBlock internally but provides the IonExchangeTransport0D interface:

```python
class IonExchangeTransport0DWithGrayBox(UnitModelBlockData):
    """Wrapper using GrayBox internally"""
    
    def build(self):
        # Create control volume for compatibility
        self.control_volume = ControlVolume0DBlock(...)
        
        # Create GrayBox model
        self.graybox = PhreeqcIXBlock(...)
        
        # Link control volume to GrayBox
        @self.Constraint()
        def link_mass_transfer(b, t, j):
            # GrayBox calculates removal rates
            inlet = b.control_volume.properties_in[t].flow_mass_phase_comp['Liq', j]
            outlet = b.graybox.outputs[f"{j}_out"]
            return b.control_volume.mass_transfer_term[t, 'Liq', j] == inlet - outlet
```

## Implementation in MCP Workflow

### 1. Update the Notebook Template

Modify `ix_simulation_unified_template.ipynb` to use GrayBox:

```python
# Instead of IonExchangeTransport0D
from phreeqc_pse.blocks.phreeqc_ix_block import PhreeqcIXBlock

# Build IX vessels
for vessel_name, vessel_config in ix_vessels.items():
    # Create GrayBox IX unit
    ix_unit = PhreeqcIXBlock(
        resin_type=vessel_config['resin_type'],
        exchange_capacity=get_capacity(vessel_config['resin_type']),
        target_ions=['Ca', 'Mg'],
        regenerant_ion=get_regenerant_ion(vessel_config['resin_type']),
        column_parameters={
            'bed_volume': vessel_config['resin_volume_m3'],
            'flow_rate': flow_rate_m3_s
        }
    )
    setattr(m.fs, vessel_name, ix_unit)
```

### 2. Update the MCP Server

In `tools/ix_simulation.py`, update to use GrayBox models:

```python
def simulate_ix_system_unified(config, water_analysis):
    """Run IX simulation using GrayBox models"""
    
    # Execute notebook with GrayBox-enabled template
    notebook_path = "notebooks/ix_simulation_graybox_template.ipynb"
    
    # Parameters remain the same
    parameters = {
        "configuration": config,
        "water_analysis": water_analysis,
        "use_graybox": True  # Flag to use GrayBox models
    }
    
    # Execute and return results
    result = pm.execute_notebook(...)
```

## Validation Results

The GrayBox model has been validated to:
- Properly enforce mass balance constraints
- Calculate correct ion removal rates
- Provide accurate breakthrough predictions
- Handle all resin types (SAC, WAC_H, WAC_Na)

## Migration Path

1. **Phase 1**: Test GrayBox models in parallel with existing code
2. **Phase 2**: Update notebooks to use GrayBox as primary model
3. **Phase 3**: Deprecate manual mass transfer updates in favor of GrayBox

## Troubleshooting

### Import Errors
If `phreeqc_pse` module is not found:
1. Ensure the module is in the Python path
2. Check that all dependencies are installed
3. Use the fallback wrapper approach

### Solver Issues
- GrayBox models may require different solver settings
- Try increasing tolerance: `solver.options['tol'] = 1e-6`
- Enable constraint scaling for better convergence

### Performance
- GrayBox models cache PHREEQC results for efficiency
- First solve may be slower due to Jacobian calculation
- Subsequent solves are typically faster

## Conclusion

The PhreeqcIXBlock GrayBox model provides a robust solution to the mass transfer integration issues. It eliminates the need for manual constraint updates and ensures proper mass balance enforcement through Pyomo's optimization framework.