# IX Design MCP Server API Reference

## Overview

The IX Design MCP Server provides four primary tools for ion exchange system design and simulation, supporting both SAC (Strong Acid Cation) and WAC (Weak Acid Cation) resins. All tools communicate via JSON and include comprehensive error handling.

## Tools

### 1. configure_sac_ix

Configure and size SAC (Strong Acid Cation) vessels for ion exchange treatment.

#### Purpose
Performs hydraulic sizing of SAC vessels based on industry-standard design parameters, without performing chemistry calculations.

#### Parameters

```json
{
  "configuration_input": {
    "water_analysis": {
      "flow_m3_hr": number,        // Required: Feed water flow rate (m³/hr)
      "ca_mg_l": number,           // Required: Calcium concentration (mg/L)
      "mg_mg_l": number,           // Required: Magnesium concentration (mg/L)
      "na_mg_l": number,           // Required: Sodium concentration (mg/L)
      "hco3_mg_l": number,         // Required: Bicarbonate concentration (mg/L)
      "pH": number,                // Required: Feed water pH (5.0-9.0)
      "cl_mg_l": number,           // Optional: Chloride (auto-balanced if omitted)
      "k_mg_l": number,            // Optional: Potassium (mg/L)
      "so4_mg_l": number,          // Optional: Sulfate (mg/L)
      "no3_mg_l": number,          // Optional: Nitrate (mg/L)
      "temperature_celsius": number // Optional: Temperature (5-40°C, default: 25)
    },
    "target_hardness_mg_l_caco3": number  // Optional: Target effluent hardness (default: 5.0)
  }
}
```

#### Response

```json
{
  "vessel_configuration": {
    "bed_volume_L": number,         // Total bed volume (liters)
    "bed_depth_m": number,          // Bed depth (meters)
    "diameter_m": number,           // Vessel diameter (meters)
    "vessels_in_service": number,   // Number of service vessels (typically 1)
    "vessels_standby": number,      // Number of standby vessels (typically 1)
    "resin_volume_L": number,       // Total resin volume
    "design_flow_bv_hr": number,    // Design flow rate (BV/hr)
    "linear_velocity_m_hr": number, // Linear velocity (m/hr)
    "resin_type": "SAC"
  },
  "water_chemistry": {
    "total_hardness_mg_l_caco3": number,  // Feed hardness as CaCO₃
    "alkalinity_mg_l_caco3": number,      // Feed alkalinity as CaCO₃
    "tds_mg_l": number,                   // Total dissolved solids
    "ionic_strength_mol_l": number        // Ionic strength (mol/L)
  },
  "design_notes": [string]  // Array of design considerations and warnings
}
```

#### Design Constraints
- Service flow rate: 16 BV/hr
- Maximum linear velocity: 25 m/hr
- Minimum bed depth: 0.75 m
- Maximum vessel diameter: 2.4 m (shipping constraint)
- N+1 redundancy included

---

### 2. configure_wac_ix

Configure and size WAC (Weak Acid Cation) vessels for ion exchange treatment.

#### Purpose
Performs hydraulic sizing of WAC vessels, supporting both Na-form and H-form configurations.

#### Parameters

```json
{
  "configuration_input": {
    "water_analysis": {
      // Same as configure_sac_ix
    },
    "resin_type": string,  // Required: "WAC_Na" or "WAC_H"
    "target_hardness_mg_l_caco3": number,     // Optional: Target hardness (default: 5.0)
    "target_alkalinity_mg_l_caco3": number    // Optional: For H-form (default: 5.0)
  }
}
```

#### Response

```json
{
  "vessel_configuration": {
    // Same structure as configure_sac_ix
    "resin_type": "WAC_Na" or "WAC_H",
    "bed_expansion_percent": number  // Bed expansion during regeneration
  },
  "water_chemistry": {
    // Same as configure_sac_ix
    "temporary_hardness_mg_l_caco3": number,  // Alkalinity-limited hardness
    "permanent_hardness_mg_l_caco3": number   // Non-alkalinity hardness
  },
  "design_notes": [string],
  "wac_specific": {
    "pH_dependent_capacity": boolean,
    "requires_decarbonation": boolean  // True for H-form
  }
}
```

#### WAC-Specific Considerations
- Na-form: Standard hardness removal with two-step regeneration
- H-form: Limited to temporary hardness removal, generates CO₂
- pH-dependent capacity (optimal pH > 7)
- Lower regenerant requirements than SAC

---

### 3. simulate_sac_ix

Simulate complete SAC ion exchange cycle including service and regeneration phases.

#### Purpose
Performs Direct PHREEQC simulation to predict breakthrough curves, determine operating capacity, and optimize regeneration.

#### Parameters

```json
{
  "water_analysis": {
    // Same as configuration input
  },
  "vessel_configuration": {
    // Output from configure_sac_ix
  },
  "target_hardness_mg_l_caco3": number,  // Breakthrough target
  "capacity_factor": number,  // Optional: 0.0-1.0 for aged resins (default: 1.0)
  "temperature_celsius": number,  // Optional: Operating temperature
  "cycles_operated": number,  // Optional: Number of cycles for degradation
  "enable_enhancements": boolean,  // Optional: Enable universal corrections (default: true)
  "regeneration_config": {
    "regenerant_type": string,  // "NaCl", "HCl", or "H2SO4"
    "concentration_percent": number,  // Regenerant concentration (default: 10)
    "regenerant_dose_g_per_L": number,  // Dose in g/L resin
    "mode": string,  // "staged_optimize", "staged_fixed", or "single_stage"
    "target_recovery": number,  // Target recovery fraction (0.0-1.0)
    "regeneration_stages": number,  // Number of stages (1-10)
    "flow_rate_bv_hr": number,  // Regeneration flow rate (default: 2.5)
    "flow_direction": string,  // "back" (counter-current) or "forward"
    "backwash_enabled": boolean  // Enable backwash phase (default: true)
  }
}
```

#### Response

```json
{
  "status": "success" or "error",
  "service_phase": {
    "breakthrough_bv": number,  // Bed volumes to breakthrough
    "service_time_hours": number,  // Service run time
    "breakthrough_hardness_mg_l_caco3": number,  // Effluent at breakthrough
    "phreeqc_determined_capacity_factor": number,  // Actual utilization
    "total_hardness_removed_kg": number,  // Total hardness removed
    "total_alkalinity_removed_kg": number,  // Alkalinity removed
    "water_treated_m3": number,  // Volume treated
    "mtz_length_m": number,  // Mass transfer zone length (if enabled)
    "effective_bed_depth_m": number,  // Usable bed depth
    "breakthrough_curve": [  // Time series data
      {
        "bv": number,
        "hardness_mg_l_caco3": number,
        "ca_mg_l": number,
        "mg_mg_l": number,
        "na_mg_l": number,
        "pH": number,
        "alkalinity_mg_l_caco3": number
      }
    ]
  },
  "regeneration_phase": {
    "regenerant_consumed_kg": number,  // Total regenerant used
    "regenerant_volume_L": number,  // Total volume
    "peak_waste_tds_mg_l": number,  // Peak TDS in waste
    "peak_waste_hardness_mg_l": number,  // Peak hardness in waste
    "total_waste_volume_m3": number,  // Total waste generated
    "final_recovery_percent": number,  // Achieved recovery
    "regeneration_time_hours": number,  // Total regeneration time
    "stages": [  // Stage-by-stage data
      {
        "stage": number,
        "volume_L": number,
        "tds_mg_l": number,
        "hardness_removed_kg": number
      }
    ]
  },
  "enhancements_applied": {  // If enhancements enabled
    "ionic_strength_mol_l": number,
    "temperature_correction_factor": number,
    "capacity_degradation_factor": number,
    "na_leakage_mg_l": number,  // For H-form
    "k_leakage_mg_l": number,
    "co2_generated_mg_l": number  // From alkalinity
  },
  "cycle_summary": {
    "total_cycle_time_hours": number,
    "bed_volumes_treated": number,
    "water_recovery_percent": number,
    "regenerant_efficiency_percent": number,
    "operating_capacity_eq_l": number
  }
}
```

#### Regenerant Dosing Guidelines
- **NaCl**: 80-120 g/L (standard), 150-200 g/L (high TDS), up to 1000 g/L (extreme)
- **HCl**: 60-80 g/L (standard)
- **H₂SO₄**: 80-100 g/L (standard)

---

### 4. simulate_wac_ix

Simulate complete WAC ion exchange cycle for Na-form or H-form resins.

#### Purpose
Performs PHREEQC simulation with WAC-specific chemistry, pH-dependent capacity, and appropriate breakthrough criteria.

#### Parameters

```json
{
  "water_analysis": {
    // Same as configuration input
  },
  "vessel_configuration": {
    // Output from configure_wac_ix
    "resin_type": "WAC_Na" or "WAC_H"  // Must match configuration
  },
  "target_hardness_mg_l_caco3": number,  // For Na-form
  "target_alkalinity_mg_l_caco3": number,  // For H-form
  "capacity_factor": number,  // Optional: Same as SAC
  "enable_enhancements": boolean,  // Optional: Same as SAC
  "regeneration_config": {
    // Auto-populated based on resin_type if not provided
    // WAC_Na: Two-step (acid → water → caustic → water)
    // WAC_H: Single-step acid regeneration
  }
}
```

#### Response

```json
{
  "status": "success" or "error",
  "service_phase": {
    // Similar to SAC with additions:
    "alkalinity_breakthrough_bv": number,  // For H-form
    "co2_generation_mg_l": number,  // CO₂ produced
    "ph_depression": number,  // pH change
    "active_sites_percent": number,  // H-form active sites
    "temporary_hardness_removed_kg": number,  // H-form specific
    "permanent_hardness_removed_kg": number,  // Should be ~0 for H-form
    "breakthrough_curve": [
      {
        // Same as SAC plus:
        "co2_mg_l": number,
        "active_sites_percent": number  // H-form only
      }
    ]
  },
  "regeneration_phase": {
    // Similar to SAC with additions for two-step:
    "acid_step": {
      "volume_L": number,
      "chemical_consumed_kg": number,
      "waste_tds_mg_l": number
    },
    "caustic_step": {  // Na-form only
      "volume_L": number,
      "chemical_consumed_kg": number,
      "waste_tds_mg_l": number
    }
  },
  "wac_performance": {
    "ph_operating_range": [number, number],
    "capacity_utilization_percent": number,
    "requires_decarbonation": boolean,
    "co2_total_generated_kg": number
  }
}
```

#### WAC-Specific Breakthrough Criteria
- **Na-form**: Hardness breakthrough (same as SAC)
- **H-form**: Alkalinity breakthrough OR active sites < 10%

---

## Enhancement Parameters

All simulation tools support universal enhancements that can be controlled through parameters:

### Available Enhancements

1. **Ionic Strength Correction**
   - Davies equation for activity coefficients
   - Automatic calculation from water composition
   - Flag: `ENABLE_IONIC_STRENGTH_CORRECTION`

2. **Temperature Correction**
   - Van't Hoff equation for selectivity adjustment
   - Applied when temperature ≠ 25°C
   - Flag: `ENABLE_TEMPERATURE_CORRECTION`

3. **Mass Transfer Zone (MTZ)**
   - Models concentration gradients in bed
   - Calculates effective bed depth
   - Flag: `ENABLE_MTZ_MODELING`

4. **Capacity Degradation**
   - Models resin aging and fouling
   - Uses `capacity_factor` parameter (0.0-1.0)
   - Flag: `ENABLE_CAPACITY_DEGRADATION`

5. **H-form Leakage**
   - Calculates Na⁺/K⁺ leakage for H-form resins
   - Based on selectivity and pH
   - Flag: `ENABLE_H_FORM_LEAKAGE`

6. **CO₂ Tracking**
   - Monitors CO₂ generation from alkalinity removal
   - Essential for H-form WAC
   - Flag: `ENABLE_CO2_TRACKING`

### Enhancement Control

```json
{
  "enable_enhancements": boolean,  // Master switch (default: true)
  "capacity_factor": number,  // 0.0-1.0 (default: 1.0)
  "temperature_celsius": number,  // Operating temperature
  "cycles_operated": number,  // For degradation calculations
  "particle_diameter_mm": number  // Resin bead size (default: 0.65)
}
```

---

## Error Handling

All tools include comprehensive error handling with structured responses:

```json
{
  "status": "error",
  "error": "Error type",
  "details": "Detailed error message",
  "hint": "Suggested resolution",
  "example_structure": {
    // Example of correct input structure
  }
}
```

### Common Error Types

1. **Invalid Input Structure**
   - Missing required fields
   - Incorrect data types
   - Out-of-range values

2. **Configuration Errors**
   - Incompatible parameters
   - Physical constraint violations
   - Missing dependencies

3. **Simulation Failures**
   - PHREEQC convergence issues
   - Breakthrough not found
   - Mass balance errors

4. **Request Size Limits**
   - Maximum request size: 10 MB
   - Timeout: 300 seconds

---

## Integration Guidelines

### Workflow Sequence

1. **Configuration Phase**
   ```
   configure_sac_ix or configure_wac_ix
   ↓
   vessel_configuration output
   ```

2. **Simulation Phase**
   ```
   vessel_configuration + water_analysis + targets
   ↓
   simulate_sac_ix or simulate_wac_ix
   ↓
   Complete cycle results
   ```

### Best Practices

1. **Always configure before simulating** - Configuration tools determine vessel sizing required for simulation

2. **Match resin types** - WAC configuration must match WAC simulation resin_type

3. **Set realistic targets** - Use achievable breakthrough targets based on water chemistry

4. **Enable enhancements for accuracy** - Universal enhancements improve real-world predictions

5. **Monitor capacity factors** - Track degradation over multiple cycles

6. **Validate mass balance** - Check that hardness removed matches regeneration recovery

---

## Performance Considerations

### Typical Execution Times

- Configuration tools: < 1 second
- SAC simulation: 5-15 seconds
- WAC simulation: 5-20 seconds
- With enhancements: +2-5 seconds

### Resource Usage

- Memory: ~100-500 MB per simulation
- CPU: Single-threaded PHREEQC calculations
- Disk: Temporary files cleaned automatically

### Optimization Tips

1. Start with fewer cells (5-10) for initial runs
2. Increase cells (20-50) for final designs
3. Use staged_optimize mode for regeneration optimization
4. Cache configuration results for multiple simulations

---

## Validation Ranges

### Water Quality
- TDS: 100 - 10,000 mg/L
- Hardness: 50 - 2,000 mg/L as CaCO₃
- Alkalinity: 20 - 1,000 mg/L as CaCO₃
- pH: 5.0 - 9.0
- Temperature: 5 - 40°C

### Design Parameters
- Flow rate: 1 - 1000 m³/hr
- Bed depth: 0.75 - 3.0 m
- Vessel diameter: 0.3 - 2.4 m
- Service flow: 8 - 16 BV/hr
- Regeneration flow: 2 - 4 BV/hr

### Operating Conditions
- Capacity factor: 0.3 - 1.0
- Recovery target: 0.8 - 0.95
- Regeneration stages: 1 - 10
- Cycles operated: 0 - 1000

---

## Version Information

- API Version: 2.0.0
- PHREEQC Engine: v3
- Enhancement Framework: v1.0
- MCP Protocol: FastMCP

---

## Support

For issues or questions:
- GitHub: https://github.com/puran-water/ix-design-mcp
- Documentation: README.md, CLAUDE.md, ENHANCEMENTS.md
- Examples: See Usage Examples section in README.md