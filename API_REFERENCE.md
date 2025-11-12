# IX Design MCP Server API Reference

## MCP Tools

### Configuration Tools

#### configure_sac_ix
Hydraulic sizing for Strong Acid Cation (SAC) ion exchange vessels.

**Input Schema:**
```json
{
  "configuration_input": {
    "water_analysis": {
      "flow_m3_hr": float,      // Feed flow rate (1-1000 m³/hr)
      "ca_mg_l": float,          // Calcium concentration (mg/L)
      "mg_mg_l": float,          // Magnesium concentration (mg/L)
      "na_mg_l": float,          // Sodium concentration (mg/L)
      "hco3_mg_l": float,        // Bicarbonate concentration (mg/L)
      "cl_mg_l": float,          // Chloride concentration (mg/L) [optional]
      "pH": float,               // Feed pH (4.0-10.0)
      "temperature_celsius": float // Temperature (5-40°C) [optional]
    },
    "target_hardness_mg_l_caco3": float // Target effluent hardness (default: 5.0)
  }
}
```

**Output:**
- Vessel dimensions (diameter, bed depth, volume)
- N+1 redundancy configuration
- Design parameters and notes

#### configure_wac_ix
Hydraulic sizing for Weak Acid Cation (WAC) ion exchange vessels.

**Input Schema:**
```json
{
  "configuration_input": {
    "water_analysis": { ... },    // Same as SAC
    "resin_type": "WAC_Na" | "WAC_H",
    "target_hardness_mg_l_caco3": float,
    "target_alkalinity_mg_l_caco3": float // For H-form only
  }
}
```

### Simulation Tool

#### simulate_ix_watertap
Unified simulation with PHREEQC chemistry and WaterTAP economics.

**Input Schema (Unified):**
```json
{
  "schema_version": "1.0.0",
  "resin_type": "SAC" | "WAC_Na" | "WAC_H",
  "water": {
    "flow_m3_hr": float,
    "temperature_c": float,
    "pH": float,
    "ions_mg_l": {
      "Ca_2+": float,
      "Mg_2+": float,
      "Na_1+": float,
      "HCO3_1-": float,
      "Cl_1-": float,
      "SO4_2-": float
    }
  },
  "vessel": {
    "diameter_m": float,
    "bed_depth_m": float,
    "number_in_service": integer
  },
  "targets": {
    "hardness_mg_l_caco3": float,
    "alkalinity_mg_l_caco3": float
  },
  "cycle": {
    "regenerant_type": string,
    "regenerant_dose_g_per_l": float,
    "regenerant_concentration_wt": float,
    "flow_direction": "co-current" | "counter-current",
    "backwash": boolean
  },
  "pricing": {
    "electricity_usd_kwh": float,
    "nacl_usd_kg": float,
    "hcl_usd_kg": float,
    "resin_usd_m3": float,
    "discount_rate": float,
    "plant_lifetime_years": integer
  },
  "engine": "phreeqc" | "watertap" | "watertap_hybrid"
}
```

## Unified Output Schema

All simulation tools return results in this unified format:

```json
{
  "schema_version": "1.0.0",
  "status": "success" | "error",
  "run_id": string,
  
  "performance": {
    "service_bv_to_target": float,    // Bed volumes to breakthrough
    "service_hours": float,            // Runtime per cycle
    "effluent_hardness_mg_l_caco3": float,
    "effluent_alkalinity_mg_l_caco3": float,
    "effluent_ph": float,
    "capacity_utilization_percent": float,
    "delta_p_bar": float,              // Pressure drop
    "sec_kwh_m3": float               // Specific energy consumption
  },
  
  "ion_tracking": {
    "feed_mg_l": { ... },
    "effluent_mg_l": { ... },
    "waste_mg_l": { ... },
    "removal_percent": { ... }
  },
  
  "mass_balance": {
    "regenerant_kg_cycle": float,
    "backwash_m3_cycle": float,
    "rinse_m3_cycle": float,
    "waste_m3_cycle": float,
    "hardness_removed_kg_caco3": float,
    "closure_percent": float
  },
  
  "economics": {
    "capital_cost_usd": float,
    "operating_cost_usd_year": float,
    "regenerant_cost_usd_year": float,
    "resin_replacement_cost_usd_year": float,
    "energy_cost_usd_year": float,
    "lcow_usd_m3": float,              // Levelized cost of water
    "unit_costs": {
      "vessels_usd": float,
      "resin_initial_usd": float,
      "pumps_usd": float,
      "instrumentation_usd": float,
      "installation_factor": float
    }
  },
  
  "solve_info": {
    "engine": string,
    "termination_condition": string,
    "solve_time_seconds": float
  },
  
  "breakthrough_data": {
    "bed_volumes": [float],
    "phases": [string],
    "ca_mg_l": [float],
    "mg_mg_l": [float],
    "na_mg_l": [float],
    "hardness_mg_l": [float]
  },
  
  "artifacts": [string],               // Paths to output files
  "warnings": [string]
}
```

## Deprecated Tools

The following tools have been deprecated in favor of `simulate_ix_watertap`:
- `simulate_sac_ix` - Use `simulate_ix_watertap` with `resin_type: "SAC"`
- `simulate_wac_ix` - Use `simulate_ix_watertap` with `resin_type: "WAC_Na"` or `"WAC_H"`

These functions remain in the codebase for internal use but are no longer exposed via the MCP interface.

## Error Handling

All tools return structured error responses:

```json
{
  "status": "error",
  "message": string,
  "details": string,
  "traceback": string  // If debug mode enabled
}
```

## Performance Notes

- **Timeout Protection**: All simulations have configurable timeout (default: 60s)
- **Process Isolation**: WaterTAP runs in subprocess to prevent import conflicts
- **Memory Management**: Automatic cleanup after each simulation
- **Concurrency**: Single-threaded execution (MCP constraint)

## Version Compatibility

- **PHREEQC**: v3.8.0 or later
- **WaterTAP**: v0.11.0 (optional)
- **Python**: 3.8+ (3.12 recommended for WaterTAP)
- **MCP Protocol**: v1.0