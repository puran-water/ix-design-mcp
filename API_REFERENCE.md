IX Design MCP Server API Reference

Overview
- Four primary tools exposed via JSON over MCP stdio.
- Performance metrics include both breakthrough (design) and average (operations).

1) configure_sac_ix
- Purpose: Hydraulic sizing for SAC vessels (no chemistry).
- Input
  {
    "configuration_input": {
      "water_analysis": {
        "flow_m3_hr": number,
        "ca_mg_l": number,
        "mg_mg_l": number,
        "na_mg_l": number,
        "hco3_mg_l": number,
        "pH": number,
        "cl_mg_l": number?  // optional, auto-balanced if omitted
      },
      "target_hardness_mg_l_caco3": number?  // default 5.0
    }
  }
- Output
  {
    "vessel_configuration": {
      "resin_type": "SAC",
      "number_service": int,
      "number_standby": int,
      "diameter_m": number,
      "bed_depth_m": number,
      "bed_volume_L": number,
      "resin_volume_m3": number,
      "freeboard_m": number,
      "vessel_height_m": number
    },
    "water_analysis": { ... },
    "target_hardness_mg_l_caco3": number,
    "regeneration_parameters": { ... },
    "design_notes": [string]
  }

2) configure_wac_ix
- Purpose: Hydraulic sizing for WAC vessels (Na-form or H-form).
- Input
  {
    "configuration_input": {
      "water_analysis": { // same fields as SAC },
      "resin_type": "WAC_Na" | "WAC_H",
      "target_hardness_mg_l_caco3": number?,
      "target_alkalinity_mg_l_caco3": number?  // H-form
    }
  }
- Output
  {
    "vessel_configuration": {
      // same geometry fields as SAC
      "resin_type": "WAC_Na" | "WAC_H",
      "bed_expansion_percent": number
    },
    "water_analysis": { ... },
    "resin_type": "WAC_Na" | "WAC_H",
    "target_hardness_mg_l_caco3": number,
    "target_alkalinity_mg_l_caco3": number?,
    "regeneration_parameters": { ... },
    "design_notes": [string],
    "water_chemistry_notes": [string]
  }

3) simulate_sac_ix
- Purpose: SAC service + regeneration simulation using Direct PHREEQC.
- Input
  {
    "water_analysis": { ... },
    "vessel_configuration": { ... },
    "target_hardness_mg_l_caco3": number,
    "regeneration_config": {
      "regenerant_type": "NaCl" | "HCl" | "H2SO4",
      "concentration_percent": number,
      "regenerant_dose_g_per_L": number?,
      "mode": "staged_fixed" | "staged_optimize",
      "regeneration_stages": int,
      "flow_rate_bv_hr": number,
      "flow_direction": "back" | "forward",
      "backwash_enabled": boolean,
      // tool may calculate BV from dose internally
    },
    "full_data": boolean?  // default false
  }
- Output
  {
    "status": "success" | "warning" | "error" | "timeout",
    "breakthrough_bv": number,
    "service_time_hours": number,
    "breakthrough_hardness_mg_l_caco3": number,
    "breakthrough_reached": boolean,
    "warnings": [string],
    "phreeqc_determined_capacity_factor": number,
    "capacity_utilization_percent": number,
    "breakthrough_data": { ... },
    "performance_metrics": {
      "breakthrough_ca_removal_percent": number,
      "breakthrough_mg_removal_percent": number,
      "breakthrough_hardness_removal_percent": number,
      "avg_ca_removal_percent": number,
      "avg_mg_removal_percent": number,
      "avg_hardness_removal_percent": number,
      "average_effluent_ph": number,
      "min_effluent_ph": number,
      "max_effluent_ph": number
    },
    "simulation_details": { ... },
    "regeneration_results": {
      "actual_regenerant_bv": number,
      "regenerant_consumed_kg": number,
      "regenerant_type": string,
      "peak_waste_tds_mg_l": number,
      "peak_waste_hardness_mg_l": number,
      "total_hardness_removed_kg": number,
      "waste_volume_m3": number,
      "final_resin_recovery": number,   // 0-1
      "ready_for_service": boolean,
      "regeneration_time_hours": number,
      "sites_restored_eq_L": number?,
      "hardness_eluted_kg_caco3": number?
    },
    "total_cycle_time_hours": number
  }

4) simulate_wac_ix
- Purpose: WAC simulation with Na-form (hardness breakthrough) or H-form (alkalinity breakthrough) behavior.
- Input
  {
    "water_analysis": { ... },
    "vessel_configuration": { ..., "resin_type": "WAC_Na" | "WAC_H" },
    "resin_type": "WAC_Na" | "WAC_H"?,  // optional if present in vessel_configuration
    "target_hardness_mg_l_caco3": number,
    "target_alkalinity_mg_l_caco3": number?,  // H-form
    "regeneration_config": { ... }?  // optional; server auto-fills sensible defaults
  }
- Output
  {
    "status": "success" | "error",
    "breakthrough_bv": number,
    "service_time_hours": number,
    "breakthrough_hardness_mg_l_caco3": number,
    "breakthrough_alkalinity_mg_l_caco3": number?,
    "breakthrough_reached": boolean,
    "warnings": [string],
    "phreeqc_capacity_factor": number,
    "capacity_utilization_percent": number,
    "breakthrough_data": { ... },
    "performance_metrics": {
      "breakthrough_ca_removal_percent": number,
      "breakthrough_mg_removal_percent": number,
      "breakthrough_hardness_removal_percent": number,
      "breakthrough_alkalinity_removal_percent": number,
      "avg_ca_removal_percent": number,
      "avg_mg_removal_percent": number,
      "avg_hardness_removal_percent": number,
      "avg_alkalinity_removal_percent": number,
      "average_effluent_ph": number,
      "min_effluent_ph": number,
      "max_effluent_ph": number,
      "co2_generation_mg_l": number,
      "active_sites_percent_final": number?,
      "temporary_hardness_removed_percent": number?,
      "permanent_hardness_removed_percent": number?
    },
    "simulation_details": { ... },
    "regeneration_results": { ... }?,
    "total_cycle_time_hours": number
  }

5) run_sac_notebook_analysis (optional)
- Purpose: Execute integrated SAC analysis notebook and produce an HTML report.
- Input: same structure as simulate_sac_ix (JSON string or object)
- Output: key metrics + file paths to executed notebook and HTML report

Errors & Limits
- Error shape (typical): { "status": "error", "error": string, "details": string, "hint": string? }
- Timeout shape: { "status": "timeout", "error": "Simulation timeout", ... }
- Max request size: ~10 MB. Timeouts are server-configured (see `MCP_SIMULATION_TIMEOUT_S`).

Performance Metrics Fix (critical)
- Metrics now include both breakthrough and average values. Use breakthrough values for equipment sizing to avoid undersized designs.
