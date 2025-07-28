# Kinetic Model Implementation Guide

## Overview

The kinetic model accounts for mass transfer limitations in ion exchange columns that prevent the system from reaching equilibrium, especially at high flow rates or short contact times.

## Key Concepts

### Mass Transfer Mechanisms

Ion exchange involves two main mass transfer steps:

1. **Film Diffusion**: Transfer from bulk solution to resin surface
   - Controlled by fluid flow conditions (Reynolds number)
   - Dominant at high flow rates
   - Improved by turbulence

2. **Particle Diffusion**: Transfer within the resin bead
   - Controlled by resin properties (bead size, porosity)
   - Dominant at low flow rates
   - Improved by smaller beads

### Kinetic Efficiency

The kinetic efficiency represents the fraction of theoretical capacity achieved under non-equilibrium conditions:

```
η = 1 - exp(-EBCT / τ)
```

Where:
- η = kinetic efficiency (0-1)
- EBCT = empty bed contact time (minutes)
- τ = characteristic time constant (minutes)

## Implementation

### Basic Usage

```python
from tools.kinetic_model import KineticModel, KineticParameters

# Define operating conditions
params = KineticParameters(
    flow_rate_m3_hr=10.0,      # 10 m³/hr
    bed_volume_m3=2.0,         # 2 m³
    bed_diameter_m=1.5,        # 1.5 m
    temperature_celsius=20,    # 20°C
    resin_bead_diameter_mm=0.6 # 0.6 mm beads
)

# Calculate kinetic efficiency
model = KineticModel()
efficiency = model.calculate_kinetic_efficiency(params)
print(f"Kinetic efficiency: {efficiency:.0%}")
```

### Integration with TRANSPORT Model

The kinetic model automatically adjusts PHREEQC TRANSPORT parameters:

```python
# In column_params, set apply_kinetics=True (default)
column_params = {
    'bed_volume_m3': 2.0,
    'diameter_m': 1.5,
    'flow_rate_m3_hr': 10.0,
    'apply_kinetics': True  # Enable kinetic adjustments
}

# TRANSPORT engine will automatically apply kinetic corrections
engine = PhreeqcTransportEngine(resin_type="SAC")
results = engine.simulate_breakthrough(column_params, feed_composition)
```

### Manual Parameter Adjustment

For advanced users, kinetic adjustments can be calculated manually:

```python
# Get adjusted transport parameters
adjustments = model.adjust_transport_parameters(
    params,
    base_dispersivity=0.02,
    base_diffusion=1e-10
)

# Use adjusted values in TRANSPORT
transport_params = TransportParameters(
    dispersivity=adjustments['dispersivity'],
    diffusion_coefficient=adjustments['diffusion_coefficient']
)
```

## Design Guidelines

### EBCT Recommendations

| EBCT (min) | Efficiency | Application |
|------------|------------|-------------|
| > 10       | > 95%      | Optimal design |
| 5-10       | 70-95%     | Standard design |
| 3-5        | 50-70%     | High flow systems |
| < 3        | < 50%      | Kinetically limited |

### Flow Rate Impact

Higher flow rates lead to:
- Shorter EBCT
- Lower kinetic efficiency
- Earlier breakthrough
- Reduced operating capacity

### Temperature Effects

Lower temperatures result in:
- Slower diffusion rates
- Reduced kinetic efficiency
- Need for longer EBCT

Temperature correction: ~2% per °C

### Resin Selection

For high flow applications:
- Use smaller bead size (0.3-0.5 mm)
- Consider uniform particle size
- WAC resins have better kinetics than SAC

## Troubleshooting

### Low Efficiency at Normal Flow

**Possible causes:**
- Temperature too low
- Resin beads too large
- Fouling reducing diffusion

**Solutions:**
- Check operating temperature
- Consider smaller bead resin
- Check for fouling (TOC, TSS)

### Film vs Particle Control

**Film diffusion control (high flow):**
- Increase turbulence
- Reduce flow rate
- Improve distribution

**Particle diffusion control (normal flow):**
- Use smaller beads
- Increase temperature
- Consider different resin type

## Example: Industrial Design

```python
# Industrial softener design
flow_rate = 50  # m³/hr
hardness_removal = 200  # mg/L as CaCO3

# Check multiple bed sizes
for bed_volume in [5, 10, 15, 20]:  # m³
    params = KineticParameters(
        flow_rate_m3_hr=flow_rate,
        bed_volume_m3=bed_volume,
        bed_diameter_m=(4 * bed_volume / (3.14 * 2))**0.5,  # L/D = 2
        temperature_celsius=15  # Conservative winter temp
    )
    
    model = KineticModel()
    efficiency = model.calculate_kinetic_efficiency(params)
    ebct = params.ebct_minutes
    
    print(f"Bed: {bed_volume} m³, EBCT: {ebct:.1f} min, Efficiency: {efficiency:.0%}")
    
    if efficiency > 0.85:
        print(f"  → Recommended design")
```

## Physical Basis

### Film Transfer Coefficient

Uses Wilson-Geankoplis correlation:
```
Sh = 1.09 * (Re * Sc)^(1/3) / ε^(1/3)
```

Valid for packed beds with:
- 0.0016 < Re < 55
- Typical porosity: 0.35-0.45

### Particle Diffusion Rate

For spherical particles:
```
k_p = 15 * D_p / r_p²
```

Where:
- D_p = particle diffusion coefficient
- r_p = particle radius

### Overall Mass Transfer

Resistances in series:
```
1/k_overall = 1/k_film + 1/k_particle
```

The slower process controls the overall rate.

## Summary

The kinetic model provides physically-based adjustments for non-equilibrium conditions without using arbitrary fudge factors. It's essential for:

1. High flow rate systems (SV > 40 h⁻¹)
2. Short contact times (EBCT < 5 min)
3. Cold water applications (< 15°C)
4. Systems with large resin beads (> 0.8 mm)

By accounting for kinetic limitations, the model provides more realistic breakthrough predictions and helps optimize system design for actual operating conditions.