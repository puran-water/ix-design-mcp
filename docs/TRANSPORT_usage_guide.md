# PHREEQC TRANSPORT Model Usage Guide

## Overview

The PHREEQC TRANSPORT model provides advanced 1D reactive transport simulation for ion exchange columns, offering more realistic breakthrough predictions than equilibrium models.

## Key Benefits

### 1. **Physical Realism**
- Models actual flow through porous media
- Includes axial dispersion (non-plug flow)
- Accounts for finite reaction kinetics
- Captures gradual breakthrough curves

### 2. **Multi-Component Competition**
- Simultaneous transport of all ions
- Competition for exchange sites
- Activity corrections for ionic strength
- Temperature-dependent selectivity

### 3. **Advanced Features**
- Dual-porosity option for channeling
- Stagnant zone modeling
- Variable time steps
- Spatial discretization control

## When to Use TRANSPORT vs Equilibrium Models

### Use TRANSPORT Model When:
- **Final design verification** - Critical systems need accurate predictions
- **Troubleshooting** - Understanding why system underperforms
- **Research** - Publishing results or developing new resins
- **Complex water chemistry** - High ionic strength or many competing ions
- **Non-ideal conditions** - Poor flow distribution, channeling suspected

### Use Equilibrium Model When:
- **Preliminary sizing** - Quick estimates for feasibility
- **Screening studies** - Comparing many alternatives
- **Simple waters** - Low TDS, minimal competition
- **Time constraints** - Need results in seconds not minutes

## How to Use TRANSPORT Model

### Basic Usage

```python
from tools.schemas import IXSimulationInput, MCASWaterComposition

# Set simulation options to use TRANSPORT
simulation_input = IXSimulationInput(
    configuration=config,  # From optimize_ix_configuration
    water_analysis=water,  # MCAS format
    simulation_options={
        "model_type": "transport",  # Enable TRANSPORT
        "transport_cells": 20,      # Number of cells (default: 20)
        "time_steps": 500          # Number of shifts (BVs)
    }
)

# Run simulation
results = simulate_ix_system(simulation_input)
```

### Advanced Parameters

```python
from tools.phreeqc_transport_engine import TransportParameters

# Customize transport parameters
transport_params = TransportParameters(
    cells=20,                    # Spatial discretization
    shifts=500,                  # Time steps (each shift = 1 BV)
    time_step=1800,              # Seconds per shift
    dispersivity=0.02,           # m (typical: 0.01-0.05)
    diffusion_coefficient=1e-10, # m²/s
    porosity=0.4,                # Bed porosity
    # Dual porosity (optional)
    stagnant_enabled=True,
    stagnant_alpha=6.8e-6,       # Exchange coefficient
    stagnant_mobile_porosity=0.3,
    stagnant_immobile_porosity=0.1
)
```

## Model Parameters Explained

### Cells
- Number of computational cells along column length
- More cells = better accuracy but slower computation
- Typical: 10-50 cells
- Recommendation: 20 cells for most applications

### Dispersivity
- Captures non-ideal flow (deviation from plug flow)
- Typical values: 0.01-0.05 m
- Higher = more spreading of breakthrough curve
- Calculate from: α = 0.01 × bed_length

### Porosity
- Void fraction in packed bed
- Typical: 0.35-0.45 for ion exchange resins
- Affects residence time and exchanger concentration

### Time Step
- Seconds per computational shift
- Automatically calculated based on flow rate
- Each shift represents ~1 bed volume

## Output Interpretation

### Breakthrough Curves
```python
# TRANSPORT results include:
{
    'bed_volumes': [0, 1, 2, ...],          # Progress through column
    'effluent_Ca_mg_L': [0, 0, 0.5, ...],  # Ca concentration
    'effluent_Mg_mg_L': [0, 0, 0.2, ...],  # Mg concentration
    'effluent_Na_mg_L': [100, 120, ...],   # Na concentration
    'Ca_breakthrough_BV': 175,              # 5% breakthrough point
    'model_type': 'PHREEQC_TRANSPORT'
}
```

### Key Differences from Equilibrium Model
1. **Gradual breakthrough** - No sharp transitions
2. **Earlier initial leakage** - Due to dispersion
3. **Longer tail** - Slow approach to feed concentration
4. **Mass transfer zone** - Width depends on kinetics

## Computational Considerations

### Performance
- TRANSPORT: 5-30 seconds per simulation
- Equilibrium: <1 second per simulation
- Time scales with: cells × shifts

### Memory Usage
- Stores results for all cells at all time steps
- ~10 MB for typical 20×500 simulation

## Best Practices

### 1. **Model Validation**
- Compare with pilot data if available
- Check mass balance (<1% error)
- Verify against known systems

### 2. **Parameter Selection**
- Start with defaults
- Adjust dispersivity based on L/D ratio
- Use manufacturer resin data

### 3. **Results Interpretation**
- Remember: No fudge factors applied
- Industrial systems achieve 10-20% of theoretical
- Consider fouling, channeling, competing ions

## Common Issues and Solutions

### No Breakthrough Detected
- **Cause**: Very high theoretical capacity
- **Solution**: Check for realistic Na levels, include all competing ions

### Immediate Breakthrough
- **Cause**: Incorrect units or parameters
- **Solution**: Verify ion concentrations in mg/L, check exchange capacity

### Slow Computation
- **Cause**: Too many cells or shifts
- **Solution**: Start with 20 cells, 300 shifts

## Example Applications

### 1. SAC Softening with High Na
```python
# Realistic industrial water
water = MCASWaterComposition(
    flow_m3_hr=10,
    ion_concentrations_mg_L={
        "Ca_2+": 120,
        "Mg_2+": 48,
        "Na_+": 300,  # High Na competition
        "Cl_-": 580,
        "SO4_2-": 240
    }
)
```

### 2. WAC Dealkalization
```python
# Alkaline water treatment
water = MCASWaterComposition(
    flow_m3_hr=50,
    pH=8.2,
    ion_concentrations_mg_L={
        "Ca_2+": 80,
        "Mg_2+": 24,
        "Na_+": 100,
        "HCO3_-": 300,  # High alkalinity
        "Cl_-": 150,
        "SO4_2-": 100
    }
)
```

## Future Enhancements

Planned additions to the TRANSPORT model:
1. **Fouling model** - TOC-based capacity reduction
2. **Kinetic rate expressions** - Beyond local equilibrium
3. **Temperature effects** - Van't Hoff corrections
4. **Trace metals** - Fe, Mn, Al competition
5. **Radial dispersion** - For large diameter columns

## References

1. PHREEQC Version 3 User's Manual - TRANSPORT keyword
2. Appelo & Postma - Geochemistry, Groundwater and Pollution
3. Bear - Dynamics of Fluids in Porous Media
4. Helfferich - Ion Exchange