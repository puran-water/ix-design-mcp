# IX Calibration Parameters Schema

This document describes the calibration parameters used in the empirical leakage overlay model.

## Overview

The IX simulation uses a two-layer architecture:
1. **Layer 1 (PHREEQC)**: Thermodynamic equilibrium for breakthrough timing
2. **Layer 2 (Empirical Overlay)**: Realistic leakage prediction

The calibration parameters control Layer 2 behavior.

## File Naming Convention

```
{site_id}_{resin_type}.json
```

Examples:
- `default_sac.json` - Default SAC parameters
- `plant_a_wac_na.json` - Site-specific WAC Na parameters
- `customer_xyz_sac.json` - Customer-specific SAC parameters

## Parameter Descriptions

### Capacity Parameters

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `capacity_factor` | float | 0.5-1.0 | Effective capacity vs fresh resin. Accounts for fouling, oxidation. |
| `cycles_operated` | int | 0+ | Number of service cycles completed. Used for aging calculations. |
| `aging_rate_per_cycle` | float | 0.0005-0.002 | Fractional capacity loss per cycle. |

### Regeneration Parameters

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `regen_eff_eta` | float | 0.80-0.98 | Regeneration efficiency. 0.92 = 92% of theoretical capacity recovered. |

### Leakage Model Parameters

The leakage formula:
```
C_leak = max(C_eq, a0 + a1*TDS/1000 + a2*(1-eta)^b)
```

| Parameter | Type | Typical | Description |
|-----------|------|---------|-------------|
| `leak_floor_a0` | float | 0.2-1.0 | Minimum leakage floor (mg/L as CaCO3). Even perfect regen has some leakage. |
| `leak_tds_slope_a1` | float | 0.5-1.5 | TDS sensitivity. Higher TDS = higher leakage due to reduced selectivity. |
| `leak_regen_coeff_a2` | float | 15-35 | Regeneration inefficiency coefficient. |
| `leak_regen_exponent_b` | float | 1.0-2.0 | Exponent for regeneration term. Higher = sharper sensitivity to poor regen. |

### Kinetic Parameters

| Parameter | Type | Typical | Description |
|-----------|------|---------|-------------|
| `k_ldf_25c` | float | 30-60 | Linear driving force mass transfer coefficient at 25C (1/hr). |
| `ea_activation_kj_mol` | float | 15-30 | Activation energy for temperature correction (kJ/mol). |

### Maldistribution Parameters

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `channeling_factor` | float | 1.0-1.5 | Flow maldistribution factor. 1.0 = perfect distribution. |

### WAC-Specific Parameters

| Parameter | Type | Typical | Description |
|-----------|------|---------|-------------|
| `pka_shift` | float | -0.5 to +0.5 | Adjustment to literature pKa value (4.8) for effective pKa. |

## Calibration Workflow

### 1. Start with Defaults
Use `default_{resin_type}.json` as baseline.

### 2. Collect Operational Data
- Effluent hardness at various service depths (BV)
- Regeneration efficiency (post-regen capacity test)
- Feed water TDS and composition
- Temperature

### 3. Fit Parameters
Adjust parameters to match observed leakage:

```python
from tools.empirical_leakage_overlay import CalibrationParameters, EmpiricalLeakageOverlay

# Start with defaults
params = CalibrationParameters()

# Adjust based on data
params.regen_eff_eta = 0.88  # If seeing higher leakage
params.leak_floor_a0 = 0.8   # If minimum leakage is higher

# Test
overlay = EmpiricalLeakageOverlay(params)
result = overlay.calculate_empirical_leakage(
    feed_hardness_mg_l_caco3=250,
    feed_tds_mg_l=1500,
    temperature_c=22
)
print(f"Predicted leakage: {result.hardness_leakage_mg_l_caco3:.2f} mg/L")
```

### 4. Save Site-Specific Calibration
```python
from tools.empirical_leakage_overlay import CalibrationLoader

loader = CalibrationLoader()
loader.save(params, 'my_site', 'SAC')
```

## Typical Values by Resin Type

### SAC (Strong Acid Cation)
- `capacity_factor`: 0.95
- `regen_eff_eta`: 0.92
- `leak_floor_a0`: 0.5
- `k_ldf_25c`: 50

### WAC Na-form
- `capacity_factor`: 0.90 (harder to maintain)
- `regen_eff_eta`: 0.88 (two-step regen less efficient)
- `leak_floor_a0`: 0.3 (higher selectivity)
- `k_ldf_25c`: 40 (slower diffusion)

### WAC H-form
- `capacity_factor`: 0.92
- `regen_eff_eta`: 0.95 (acid regen efficient)
- `leak_floor_a0`: 0.2 (very high selectivity)
- `k_ldf_25c`: 35

## Integration with Digital Twin

For operating assets, calibration should be updated periodically:

1. **Weekly**: Adjust `cycles_operated` based on actual service cycles
2. **Monthly**: Compare predicted vs actual leakage, tune `leak_floor_a0`
3. **Quarterly**: Review `regen_eff_eta` based on capacity tests
4. **Annually**: Full recalibration with resin sampling if available
