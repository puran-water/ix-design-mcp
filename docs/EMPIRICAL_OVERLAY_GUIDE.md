# Empirical Leakage Overlay Guide for IX Digital Twins

## Overview

This guide describes how to implement and tune empirical leakage overlays for ion exchange (IX) simulations. The two-layer architecture separates thermodynamic calculations (PHREEQC) from empirical leakage prediction, enabling accurate digital twin modeling for operating assets.

### Why Two Layers?

**The Problem**: PHREEQC calculates thermodynamic equilibrium, which predicts near-zero leakage for well-designed IX systems. This is mathematically correct but doesn't match real-world observations of 0.5-10 mg/L hardness leakage.

**The Solution**: Industry projection software (DuPont WAVE, Purolite PRSM, Veolia) uses empirical correlations calibrated from pilot data. Our two-layer architecture replicates this approach:

| Layer | Purpose | Tool |
|-------|---------|------|
| Layer 1 | Thermodynamic equilibrium, breakthrough timing | PHREEQC |
| Layer 2 | Realistic leakage, kinetics, aging | Empirical Overlay |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     IX Simulation Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Feed Water ──► PHREEQC Simulation ──► Raw Results              │
│                      │                      │                   │
│                      │                      ▼                   │
│                      │              ┌──────────────────┐        │
│                      │              │ Empirical Overlay │        │
│                      │              │                  │        │
│                      │              │ • Leakage floor  │        │
│                      │              │ • TDS effects    │        │
│                      │              │ • Regen efficiency│       │
│                      │              │ • Kinetics       │        │
│                      │              │ • Aging          │        │
│                      │              └──────────────────┘        │
│                      │                      │                   │
│                      ▼                      ▼                   │
│              Breakthrough BV ◄────► Adjusted Leakage            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Leakage Model

### Core Formula

The empirical leakage model follows the pattern used by IX vendors:

```
C_leak = max(C_eq, a₀ + a₁×TDS/1000 + a₂×(1-η)^b)
```

Where:
- `C_eq` = PHREEQC equilibrium leakage (typically ~0)
- `a₀` = Minimum leakage floor (mg/L as CaCO3)
- `a₁` = TDS sensitivity coefficient
- `TDS` = Total dissolved solids (mg/L)
- `a₂` = Regeneration inefficiency coefficient
- `η` = Regeneration efficiency (0.85-0.98)
- `b` = Regeneration exponent (typically 1.3-1.5)

### Physical Interpretation

| Term | Physical Meaning |
|------|------------------|
| `a₀` (floor) | Irreducible leakage from mass transfer zone, even with perfect regeneration |
| `a₁×TDS` | Selectivity reduction at high ionic strength (Davies equation effect) |
| `a₂×(1-η)^b` | Residual hardness from incomplete regeneration |

---

## Resin-Specific Implementation

### SAC (Strong Acid Cation)

SAC resins are the most common IX resins for water softening. They have moderate selectivity and fast kinetics.

#### Leakage Sources for SAC

1. **Incomplete Regeneration**: Primary source (~60% of leakage)
   - NaCl regeneration never achieves 100% conversion
   - Typical efficiency: 90-95%

2. **TDS/Ionic Strength**: Secondary source (~25% of leakage)
   - High TDS reduces selectivity (Davies equation)
   - Effect: ~1 mg/L leakage per 1000 mg/L TDS increase

3. **Mass Transfer Zone**: Minor source (~15% of leakage)
   - Equilibrium in MTZ is incomplete
   - Depends on flow rate and particle size

#### SAC Calibration Parameters

```json
{
  "capacity_factor": 0.95,
  "regen_eff_eta": 0.92,
  "leak_floor_a0": 0.5,
  "leak_tds_slope_a1": 0.8,
  "leak_regen_coeff_a2": 25.0,
  "leak_regen_exponent_b": 1.5,
  "k_ldf_25c": 50.0,
  "ea_activation_kj_mol": 20.0,
  "channeling_factor": 1.0,
  "aging_rate_per_cycle": 0.001,
  "cycles_operated": 0,

  "regenerant_dose_g_per_l": 100.0,
  "regen_flow_direction": "counter",
  "slow_rinse_volume_bv": 1.0,
  "fast_rinse_volume_bv": 3.0,
  "service_flow_bv_hr": 12.0,
  "bed_depth_m": 1.5,
  "resin_crosslinking_dvb": 8.0,
  "resin_form": "gel"
}
```

#### SAC Two-Layer Architecture: ADDITIVE Approach

SAC simulation uses PHREEQC's native Na+ competition modeling via selectivity coefficients. However, PHREEQC only calculates **equilibrium leakage** (~0.1 mg/L). Real SAC systems show 1-5 mg/L due to non-equilibrium effects that PHREEQC doesn't model:

| Factor | PHREEQC Models? | Empirical Overlay? | Contribution |
|--------|-----------------|-------------------|--------------|
| Na+ competition | YES | (additive) | Equilibrium baseline |
| Incomplete regeneration | NO | YES | **60%** of real leakage |
| Mass transfer zone | NO | YES | 15% |
| Channeling | NO | YES | 10% |
| Resin aging | NO | YES | Variable |

The overlay uses an **ADDITIVE** approach: `final_leakage = PHREEQC_competition + empirical_floor_offset`

#### SAC Implementation Code (Actual)

The SAC overlay is integrated in `tools/sac_simulation.py` after PHREEQC service simulation:

```python
from tools.empirical_leakage_overlay import (
    EmpiricalLeakageOverlay,
    CalibrationLoader,
    CalibrationParameters
)

# In SACSimulation.run_full_cycle_simulation() after PHREEQC extraction:

try:
    cal_loader = CalibrationLoader()
    cal_params = cal_loader.load('default', 'SAC')

    # Wire designer parameters from regeneration config
    if regen_config.regenerant_dose_g_per_L:
        cal_params.regenerant_dose_g_per_l = regen_config.regenerant_dose_g_per_L
    if hasattr(regen_config, 'flow_direction') and regen_config.flow_direction:
        cal_params.regen_flow_direction = regen_config.flow_direction
    if regen_config.slow_rinse_bv:
        cal_params.slow_rinse_volume_bv = regen_config.slow_rinse_bv
    if regen_config.fast_rinse_bv:
        cal_params.fast_rinse_volume_bv = regen_config.fast_rinse_bv

    overlay = EmpiricalLeakageOverlay(cal_params)
    # Calculate regen efficiency from designer parameters
    overlay.update_regen_efficiency_from_design(resin_type='SAC')

    # Calculate feed properties
    feed_hardness_caco3 = water.ca_mg_l * 2.5 + water.mg_mg_l * 4.1
    feed_tds = (water.ca_mg_l + water.mg_mg_l + water.na_mg_l +
                water.cl_mg_l + water.so4_mg_l + water.hco3_mg_l)

    # Get PHREEQC's competition-based leakage (early BV values)
    phreeqc_early_leakage = float(np.min(curves['Hardness'][:max(5, len(curves['Hardness'])//10)]))

    overlay_result = overlay.calculate_empirical_leakage(
        feed_hardness_mg_l_caco3=feed_hardness_caco3,
        feed_tds_mg_l=feed_tds,
        temperature_c=getattr(water, 'temperature_c', 25.0),
        phreeqc_leakage_mg_l=phreeqc_early_leakage,  # ADDITIVE approach
        resin_type='SAC'
    )

    # Apply ADDITIVE offset to breakthrough curve
    empirical_floor = overlay_result.hardness_leakage_mg_l_caco3
    original_min = float(np.min(curves['Hardness']))
    if empirical_floor > original_min:
        offset = empirical_floor - original_min
        curves['Hardness'] = curves['Hardness'] + offset
        logger.info(f"SAC Empirical Overlay Applied: offset +{offset:.2f} mg/L")

except Exception as e:
    logger.warning(f"Empirical overlay failed, using raw PHREEQC results: {e}")
```

#### SAC Typical Leakage Values

| Feed TDS (mg/L) | Regen Efficiency | Expected Leakage (mg/L as CaCO3) |
|-----------------|------------------|----------------------------------|
| 500 | 95% | 1.0 - 1.5 |
| 1000 | 92% | 2.0 - 3.0 |
| 2000 | 90% | 3.5 - 5.0 |
| 3000 | 88% | 5.0 - 7.0 |

---

### WAC H-form (Weak Acid Cation, Hydrogen Form)

WAC H-form is used for dealkalizing and partial softening. It has very high selectivity but pH-dependent capacity.

#### Leakage Sources for WAC H-form

1. **Na/K Leakage**: Primary concern (NOT hardness)
   - WAC H-form has excellent hardness removal
   - But Na+ and K+ compete for sites
   - Typical Na leakage: 2-5% of influent

2. **Alkalinity Slip**: At exhaustion
   - As H+ sites deplete, HCO3- passes through
   - CO2 generation decreases

3. **pH-Dependent Capacity**: pKa effect
   - Capacity depends on pH > pKa + 2
   - Low pH feed = reduced capacity

#### WAC H-form Calibration Parameters

```json
{
  "capacity_factor": 0.92,
  "regen_eff_eta": 0.95,
  "leak_floor_a0": 0.2,
  "leak_tds_slope_a1": 0.5,
  "leak_regen_coeff_a2": 20.0,
  "leak_regen_exponent_b": 1.3,
  "k_ldf_25c": 35.0,
  "ea_activation_kj_mol": 25.0,
  "channeling_factor": 1.0,
  "aging_rate_per_cycle": 0.0008,
  "pka_shift": 0.0,

  "regenerant_dose_g_per_l": 50.0,
  "regen_flow_direction": "counter",
  "slow_rinse_volume_bv": 0.5,
  "fast_rinse_volume_bv": 1.5,
  "service_flow_bv_hr": 10.0,
  "bed_depth_m": 1.5,
  "resin_crosslinking_dvb": 8.0,
  "resin_form": "gel",

  "base_na_leakage_percent": 2.0,
  "base_k_leakage_percent": 1.5,
  "leakage_exhaustion_factor": 3.0
}
```

#### WAC H-form Special Considerations

**1. Na/K Leakage Model**

WAC H-form hardness leakage is minimal, but Na/K leakage is significant. Use the existing `calculate_h_form_leakage()` method in `BaseIXSimulation`:

```python
from tools.base_ix_simulation import BaseIXSimulation

# Calculate Na/K leakage
leakage_result = self.calculate_h_form_leakage(
    influent_na_mg_l=water.na_mg_l,
    influent_k_mg_l=water.k_mg_l,
    resin_exhaustion_percent=exhaustion_pct,
    base_na_leakage_percent=2.0,
    base_k_leakage_percent=1.5,
    exhaustion_factor=3.0
)

na_leakage = leakage_result['na_mg_l']
k_leakage = leakage_result['k_mg_l']
```

**2. CO2 Generation**

WAC H-form generates CO2 from alkalinity removal:

```python
co2_result = self.track_co2_generation(
    alkalinity_removed_mg_l=alk_removed,
    ph_initial=water.ph,
    ph_final=effluent_ph,
    temperature_c=water.temperature_c
)

if co2_result['stripping_required']:
    logger.warning(f"CO2 stripping required: {co2_result['co2_saturation_percent']:.0f}% saturation")
```

**3. pKa Shift Calibration**

If observed capacity differs from theoretical:

```python
# Effective pKa = literature pKa + pka_shift
# Higher pKa = lower capacity at given pH
# Lower pKa = higher capacity at given pH

params.pka_shift = -0.3  # Increase effective capacity
# or
params.pka_shift = +0.2  # Decrease effective capacity
```

#### WAC H-form Implementation Code (Actual)

The WAC H+ overlay is integrated in `tools/wac_simulation.py` in `WacHSimulation.run_simulation()`:

```python
from tools.empirical_leakage_overlay import (
    EmpiricalLeakageOverlay,
    CalibrationLoader,
    CalibrationParameters
)

# In WacHSimulation.run_simulation() after _adjust_hform_breakthrough_data():

try:
    cal_loader = CalibrationLoader()
    cal_params = cal_loader.load('default', 'WAC_H')

    # Calculate feed properties
    feed_hardness_caco3 = water.ca_mg_l * 2.5 + water.mg_mg_l * 4.1
    feed_tds = (water.ca_mg_l + water.mg_mg_l + water.na_mg_l +
                water.cl_mg_l + water.so4_mg_l + water.hco3_mg_l)

    # === Part 1: Na/K Leakage Calculation ===
    # Na/K leakage is the PRIMARY concern for WAC H+ (2-8% of feed)
    bv_array = breakthrough_data.get('BV', np.array([]))

    if len(bv_array) > 0:
        # Calculate theoretical BV for exhaustion percentage
        alkalinity_meq_L = water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT
        theoretical_bv = (CONFIG.WAC_H_TOTAL_CAPACITY * 1000) / alkalinity_meq_L

        # Calculate Na/K leakage at each BV point
        na_leakage_array = np.zeros_like(bv_array)
        k_leakage_array = np.zeros_like(bv_array)

        for i, bv in enumerate(bv_array):
            exhaustion_pct = min(100.0, (bv / theoretical_bv) * 100)
            leakage_result = self.calculate_h_form_leakage(
                influent_na_mg_l=water.na_mg_l,
                influent_k_mg_l=getattr(water, 'k_mg_l', 0.0),
                resin_exhaustion_percent=exhaustion_pct,
                base_na_leakage_percent=cal_params.params.base_na_leakage_percent,
                base_k_leakage_percent=cal_params.params.base_k_leakage_percent,
                exhaustion_factor=cal_params.params.leakage_exhaustion_factor
            )
            na_leakage_array[i] = leakage_result['na_mg_l']
            k_leakage_array[i] = leakage_result['k_mg_l']

        # Add Na/K leakage to breakthrough data
        breakthrough_data['Na_leakage_mg/L'] = na_leakage_array
        breakthrough_data['K_leakage_mg/L'] = k_leakage_array

        logger.info(f"WAC H+ Na/K leakage overlay applied: Na {na_leakage_array[0]:.1f}-{na_leakage_array[-1]:.1f} mg/L")

    # === Part 2: Hardness Overlay (minimal effect for H-form) ===
    overlay = EmpiricalLeakageOverlay(cal_params)
    overlay.update_regen_efficiency_from_design(resin_type='WAC_H')

    hardness_key = 'Hardness_CaCO3' if 'Hardness_CaCO3' in breakthrough_data else 'Hardness_mg/L'
    hardness_array = breakthrough_data.get(hardness_key, np.array([]))

    if len(hardness_array) > 0:
        phreeqc_early_leakage = float(np.min(hardness_array[:max(5, len(hardness_array)//10)]))

        overlay_result = overlay.calculate_empirical_leakage(
            feed_hardness_mg_l_caco3=feed_hardness_caco3,
            feed_tds_mg_l=feed_tds,
            temperature_c=getattr(water, 'temperature_c', 25.0),
            phreeqc_leakage_mg_l=phreeqc_early_leakage,
            resin_type='WAC_H'
        )

        empirical_floor = overlay_result.hardness_leakage_mg_l_caco3
        original_min = float(np.min(hardness_array))
        if empirical_floor > original_min:
            offset = empirical_floor - original_min
            breakthrough_data[hardness_key] = hardness_array + offset
            logger.info(f"WAC H+ hardness overlay applied: offset +{offset:.2f} mg/L")

except Exception as e:
    logger.warning(f"WAC H+ empirical overlay failed, using raw PHREEQC results: {e}")
```

The output includes Na/K leakage arrays in the breakthrough data:
```python
breakthrough_data={
    'bv': [...],
    'hardness_mg_l': [...],
    # ... other fields ...
    'na_leakage_mg_l': [...],  # Na+ leakage at each BV
    'k_leakage_mg_l': [...]    # K+ leakage at each BV
}
```

#### WAC H-form Typical Values

| Parameter | Typical Range | Notes |
|-----------|---------------|-------|
| Hardness leakage | 0.1 - 1.0 mg/L | Much lower than SAC |
| Na leakage | 2 - 8% of influent | Increases with exhaustion |
| K leakage | 1.5 - 6% of influent | Slightly lower than Na |
| CO2 generated | 90-100% of HCO3 removed | Stoichiometric |
| pH depression | 0.5 - 2.0 units | From CO2 generation |

---

## Digital Twin Calibration Workflow

### Step 1: Baseline Data Collection

Collect operational data for calibration:

```python
# Required data points
baseline_data = {
    'feed_water': {
        'ca_mg_l': 120,
        'mg_mg_l': 40,
        'na_mg_l': 200,
        'hco3_mg_l': 250,
        'cl_mg_l': 150,
        'so4_mg_l': 80,
        'tds_mg_l': 800,
        'temperature_c': 18
    },
    'effluent_at_various_bv': [
        {'bv': 50, 'hardness_mg_l': 1.2, 'na_mg_l': 195},
        {'bv': 100, 'hardness_mg_l': 1.5, 'na_mg_l': 196},
        {'bv': 200, 'hardness_mg_l': 2.1, 'na_mg_l': 198},
        {'bv': 300, 'hardness_mg_l': 4.5, 'na_mg_l': 200},  # Near breakthrough
    ],
    'regeneration': {
        'nacl_dose_g_per_l': 120,
        'measured_capacity_percent': 88  # vs fresh resin
    },
    'operating_conditions': {
        'cycles_since_resin_replacement': 500,
        'flow_rate_bv_hr': 12
    }
}
```

### Step 2: Initial Parameter Estimation

```python
from tools.empirical_leakage_overlay import CalibrationParameters

# Start with defaults
params = CalibrationParameters()

# Adjust based on known conditions
params.regen_eff_eta = baseline_data['regeneration']['measured_capacity_percent'] / 100
params.cycles_operated = baseline_data['operating_conditions']['cycles_since_resin_replacement']

# Estimate capacity factor from age
expected_aging = (1 - params.aging_rate_per_cycle) ** params.cycles_operated
params.capacity_factor = expected_aging
```

### Step 3: Parameter Optimization

Use observed leakage to tune parameters:

```python
import numpy as np
from scipy.optimize import minimize

def objective(params_array):
    """Minimize difference between predicted and observed leakage."""
    a0, a1, a2 = params_array

    total_error = 0
    for obs in baseline_data['effluent_at_various_bv']:
        # Calculate predicted leakage
        tds_term = a1 * baseline_data['feed_water']['tds_mg_l'] / 1000
        regen_term = a2 * (1 - params.regen_eff_eta) ** 1.5
        predicted = a0 + tds_term + regen_term

        # Compare to observed (weight early BV higher)
        weight = 1.0 if obs['bv'] < 200 else 0.5
        error = weight * (predicted - obs['hardness_mg_l']) ** 2
        total_error += error

    return total_error

# Optimize
initial_guess = [0.5, 0.8, 25.0]  # a0, a1, a2
bounds = [(0.1, 2.0), (0.3, 2.0), (10.0, 50.0)]
result = minimize(objective, initial_guess, bounds=bounds, method='L-BFGS-B')

# Update parameters
params.leak_floor_a0 = result.x[0]
params.leak_tds_slope_a1 = result.x[1]
params.leak_regen_coeff_a2 = result.x[2]

print(f"Optimized: a0={params.leak_floor_a0:.2f}, a1={params.leak_tds_slope_a1:.2f}, a2={params.leak_regen_coeff_a2:.2f}")
```

### Step 4: Save Site-Specific Calibration

```python
from tools.empirical_leakage_overlay import CalibrationLoader

loader = CalibrationLoader()
loader.save(params, 'plant_xyz', 'SAC')

# Creates: databases/calibrations/plant_xyz_sac.json
```

### Step 5: Validate Calibration

```python
# Run simulation with calibrated parameters
from tools.empirical_leakage_overlay import EmpiricalLeakageOverlay

overlay = EmpiricalLeakageOverlay(params)

# Predict for new conditions
for obs in baseline_data['effluent_at_various_bv']:
    result = overlay.calculate_empirical_leakage(
        feed_hardness_mg_l_caco3=feed_hardness,
        feed_tds_mg_l=baseline_data['feed_water']['tds_mg_l'],
        temperature_c=baseline_data['feed_water']['temperature_c'],
        phreeqc_leakage_mg_l=0.0,
        resin_type='SAC'
    )

    print(f"BV={obs['bv']}: Predicted={result.hardness_leakage_mg_l_caco3:.2f}, "
          f"Observed={obs['hardness_mg_l']:.2f}")
```

---

## Online Digital Twin Updates

For operating assets, update calibration periodically:

### Weekly Updates

```python
def weekly_update(site_id: str, resin_type: str, new_cycle_count: int):
    """Update cycles_operated weekly."""
    loader = CalibrationLoader()
    params = loader.load(site_id, resin_type)
    params.cycles_operated = new_cycle_count
    loader.save(params, site_id, resin_type)
```

### Monthly Updates

```python
def monthly_calibration(site_id: str, resin_type: str,
                        observed_leakage_mg_l: float,
                        feed_tds_mg_l: float):
    """Adjust leak_floor_a0 based on observed average leakage."""
    loader = CalibrationLoader()
    params = loader.load(site_id, resin_type)

    # Calculate expected leakage from TDS and regen terms
    tds_contribution = params.leak_tds_slope_a1 * feed_tds_mg_l / 1000
    regen_contribution = params.leak_regen_coeff_a2 * (1 - params.regen_eff_eta) ** params.leak_regen_exponent_b

    # Back-calculate required floor
    new_floor = observed_leakage_mg_l - tds_contribution - regen_contribution

    # Smooth update (don't change too much at once)
    alpha = 0.3  # Learning rate
    params.leak_floor_a0 = alpha * max(0.1, new_floor) + (1 - alpha) * params.leak_floor_a0

    loader.save(params, site_id, resin_type)
    return params.leak_floor_a0
```

### Quarterly Updates

```python
def quarterly_capacity_test(site_id: str, resin_type: str,
                           measured_capacity_percent: float):
    """Update regeneration efficiency from capacity test."""
    loader = CalibrationLoader()
    params = loader.load(site_id, resin_type)

    # Capacity test measures post-regen capacity
    # This reflects both aging AND regen efficiency

    # Estimate aging component
    aging_factor = (1 - params.aging_rate_per_cycle) ** params.cycles_operated

    # Back-calculate regen efficiency
    # measured = capacity_factor * regen_eff * aging_factor
    if aging_factor > 0.5:
        implied_regen_eff = measured_capacity_percent / 100 / aging_factor / params.capacity_factor
        params.regen_eff_eta = min(0.98, max(0.80, implied_regen_eff))

    loader.save(params, site_id, resin_type)
    return params.regen_eff_eta
```

---

## Troubleshooting

### Issue: Predicted Leakage Too Low

**Symptoms**: Digital twin shows 1 mg/L, plant shows 4 mg/L

**Possible Causes & Fixes**:

1. **Regeneration efficiency overestimated**
   ```python
   params.regen_eff_eta = 0.85  # Reduce from 0.92
   ```

2. **Channeling not accounted for**
   ```python
   params.channeling_factor = 1.2  # 20% flow maldistribution
   ```

3. **TDS sensitivity underestimated**
   ```python
   params.leak_tds_slope_a1 = 1.2  # Increase from 0.8
   ```

### Issue: Predicted Leakage Too High

**Symptoms**: Digital twin shows 5 mg/L, plant shows 2 mg/L

**Possible Causes & Fixes**:

1. **Floor too high**
   ```python
   params.leak_floor_a0 = 0.3  # Reduce from 0.5
   ```

2. **Regeneration better than assumed**
   ```python
   params.regen_eff_eta = 0.95  # Increase from 0.92
   ```

### Issue: Leakage Profile Shape Wrong

**Symptoms**: Leakage increases faster/slower than observed with BV

**Fix**: Adjust breakthrough data application, not leakage parameters. The empirical overlay provides a floor, but breakthrough curve shape comes from PHREEQC.

---

## API Reference

### CalibrationParameters

```python
@dataclass
class CalibrationParameters:
    # Capacity and regeneration
    capacity_factor: float = 0.95        # 0.5-1.0
    regen_eff_eta: float = 0.92          # 0.80-0.98

    # Leakage model coefficients
    leak_floor_a0: float = 0.5           # mg/L as CaCO3
    leak_tds_slope_a1: float = 0.8       # mg/L per 1000 mg/L TDS
    leak_regen_coeff_a2: float = 25.0    # mg/L
    leak_regen_exponent_b: float = 1.5   # dimensionless

    # Kinetics
    k_ldf_25c: float = 50.0              # 1/hr
    ea_activation_kj_mol: float = 20.0   # kJ/mol

    # Maldistribution
    channeling_factor: float = 1.0       # 1.0-1.5

    # Aging
    aging_rate_per_cycle: float = 0.001  # fraction
    cycles_operated: int = 0

    # WAC-specific
    pka_shift: float = 0.0               # pH units

    # === DESIGNER LEVERS: REGENERATION ===
    regenerant_dose_g_per_l: float = 100.0    # g NaCl per L resin (80-160 SAC)
    regen_flow_direction: str = "counter"     # "counter" or "co"
    slow_rinse_volume_bv: float = 1.0         # Displacement rinse (BV)
    fast_rinse_volume_bv: float = 3.0         # Fast rinse (BV)

    # === DESIGNER LEVERS: SERVICE ===
    service_flow_bv_hr: float = 12.0          # Operating flow rate (BV/hr)
    bed_depth_m: float = 1.5                  # Actual bed depth (m)

    # === DESIGNER LEVERS: RESIN SELECTION ===
    resin_crosslinking_dvb: float = 8.0       # % DVB crosslinking (2-16)
    resin_form: str = "gel"                   # "gel" or "macroporous"

    # === WAC H+ SPECIFIC: Na/K LEAKAGE ===
    base_na_leakage_percent: float = 2.0      # Base Na+ leakage (% of influent)
    base_k_leakage_percent: float = 1.5       # Base K+ leakage (% of influent)
    leakage_exhaustion_factor: float = 3.0    # Multiplier at full exhaustion
```

### Designer Lever → Parameter Mapping

| Design Lever | Parameter | Effect on Leakage |
|--------------|-----------|-------------------|
| Salt dosage | `regenerant_dose_g_per_l` → `regen_eff_eta` | -0.5 to -1.5 mg/L per 20 g/L increase |
| Regen direction | `regen_flow_direction` | Counter: -0.5 to -1.0 mg/L vs co-current |
| Service flow | `service_flow_bv_hr` → kinetic factor | +0.2 mg/L per 4 BV/hr above 12 |
| Bed depth | `bed_depth_m` → MTZ fraction | Deeper = lower MTZ fraction |
| Temperature | `operating_temp_c` → kinetic factor | +0.1 mg/L per 5°C below 25°C |
| Resin DVB% | `resin_crosslinking_dvb` | Higher = better selectivity |

### Regeneration Efficiency Calculator

```python
def calculate_regen_efficiency_from_design(self, resin_type: str = "SAC") -> float:
    """
    Calculate regeneration efficiency from designer parameters.

    Salt dose to efficiency correlation (SAC, co-current baseline):
        - 6 lb/ft³ (96 g/L)  → 85% efficiency
        - 10 lb/ft³ (160 g/L) → 90% efficiency
        - 15 lb/ft³ (240 g/L) → 94% efficiency

    Adjustments:
        + 5% for counter-current regeneration
        - 2% penalty for insufficient rinse (<3 BV)
        - 4% for WAC Na+ (two-step regen)
        + 3% for WAC H+ (acid regen bonus)

    Returns: eta in range [0.80, 0.98]
    """
```

Usage:
```python
overlay = EmpiricalLeakageOverlay(cal_params)
overlay.update_regen_efficiency_from_design(resin_type='SAC')
# cal_params.regen_eff_eta is now updated based on designer parameters
```

### EmpiricalLeakageOverlay

```python
class EmpiricalLeakageOverlay:
    def __init__(self, params: CalibrationParameters = None)

    def calculate_empirical_leakage(
        self,
        feed_hardness_mg_l_caco3: float,
        feed_tds_mg_l: float,
        temperature_c: float = 25.0,
        phreeqc_leakage_mg_l: float = 0.0,
        resin_type: str = "SAC"
    ) -> EmpiricalOverlayResult

    def apply_to_breakthrough_data(
        self,
        breakthrough_data: Dict[str, np.ndarray],
        feed_composition: Dict[str, float],
        resin_type: str = "SAC"
    ) -> Dict[str, np.ndarray]
```

### CalibrationLoader

```python
class CalibrationLoader:
    def __init__(self, config_dir: Path = None)

    def load(self, site_id: str, resin_type: str) -> CalibrationParameters

    def save(self, params: CalibrationParameters, site_id: str, resin_type: str)
```

---

## References

1. Helfferich, F. (1962). *Ion Exchange*. McGraw-Hill.
2. DuPont Water Solutions. *WAVE Design Software Technical Manual*.
3. Purolite. *PRSM Software User Guide*.
4. WaterTAP Documentation. *IonExchange0D Model*.
5. Clifford, D. (1999). "Ion Exchange and Inorganic Adsorption." *Water Quality & Treatment*, AWWA.
