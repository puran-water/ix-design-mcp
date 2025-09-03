IX Design MCP Server

Ion exchange design MCP server with SAC and WAC tools. Uses Direct PHREEQC for breakthrough prediction and reports clear metrics for equipment sizing.

Key behavior: Performance metrics include both breakthrough (for design) and average (for operations). Always size equipment using breakthrough values.

Tools
- configure_sac_ix: Hydraulic sizing for SAC vessels (no chemistry).
- configure_wac_ix: Hydraulic sizing for WAC vessels (Na-form or H-form).
- simulate_sac_ix: SAC service + regeneration simulation via PHREEQC.
- simulate_wac_ix: WAC simulation (Na-form hardness, H-form alkalinity).
- run_sac_notebook_analysis: Optional notebook report (if papermill/nbconvert installed).

Install
- Python 3.8+
- PHREEQC v3 available on PATH or set `PHREEQC_EXE`
- `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
- `pip install -r requirements.txt`

Run With MCP Clients
- Set root so the server can find notebooks/databases:
  - Bash: `export IX_DESIGN_MCP_ROOT=/path/to/ix-design-mcp`
  - PowerShell: `$env:IX_DESIGN_MCP_ROOT="C:\\path\\to\\ix-design-mcp"`
- Claude Desktop example:
  {
    "mcpServers": {
      "ix-design-mcp": {
        "type": "stdio",
        "command": "python",
        "args": ["/path/to/ix-design-mcp/server.py"],
        "env": { "IX_DESIGN_MCP_ROOT": "/path/to/ix-design-mcp" }
      }
    }
  }

Inputs (minimal)
- configure_sac_ix
  - `configuration_input.water_analysis`: `{ flow_m3_hr, ca_mg_l, mg_mg_l, na_mg_l, hco3_mg_l, pH, [cl_mg_l] }`
  - `configuration_input.target_hardness_mg_l_caco3` (default 5.0)
- configure_wac_ix
  - Same water_analysis; `resin_type`: `"WAC_Na" | "WAC_H"`; optional alkalinity target for H-form
- simulate_sac_ix
  - `water_analysis`, `vessel_configuration` (from configure), `target_hardness_mg_l_caco3`, `regeneration_config` (see API)
  - Optional `full_data: true` for high-resolution curves
- simulate_wac_ix
  - `water_analysis`, `vessel_configuration` (must include `resin_type`), targets; `regeneration_config` optional (auto-filled)

Example: SAC Configuration (abridged)
{
  "configuration_input": {
    "water_analysis": {
      "flow_m3_hr": 100, "ca_mg_l": 80, "mg_mg_l": 24,
      "na_mg_l": 839, "hco3_mg_l": 122, "pH": 7.8
    },
    "target_hardness_mg_l_caco3": 5.0
  }
}

Response (abridged)
{
  "vessel_configuration": {
    "resin_type": "SAC", "number_service": 1, "number_standby": 1,
    "diameter_m": 1.8, "bed_depth_m": 2.0, "bed_volume_L": 5080.0,
    "resin_volume_m3": 5.08, "freeboard_m": 1.0, "vessel_height_m": 3.5
  },
  "water_analysis": { ... },
  "target_hardness_mg_l_caco3": 5.0,
  "regeneration_parameters": { ... },
  "design_notes": [ ... ]
}

Example: SAC Simulation (output abridged)
{
  "status": "success",
  "breakthrough_bv": 118.6,
  "service_time_hours": 7.4,
  "breakthrough_hardness_mg_l_caco3": 5.0,
  "breakthrough_reached": true,
  "phreeqc_determined_capacity_factor": 0.36,
  "capacity_utilization_percent": 72.1,
  "performance_metrics": {
    "breakthrough_ca_removal_percent": 87.5,
    "breakthrough_mg_removal_percent": 82.1,
    "breakthrough_hardness_removal_percent": 85.2,
    "avg_ca_removal_percent": 99.8,
    "avg_mg_removal_percent": 99.9,
    "avg_hardness_removal_percent": 99.85,
    "average_effluent_ph": 7.8,
    "min_effluent_ph": 7.0,
    "max_effluent_ph": 8.5
  },
  "regeneration_results": {
    "actual_regenerant_bv": 3.5,
    "regenerant_consumed_kg": 120.5,
    "peak_waste_tds_mg_l": 25000,
    "waste_volume_m3": 3.5,
    "final_resin_recovery": 0.935,
    "regeneration_time_hours": 2.8
  },
  "total_cycle_time_hours": 9.9
}

Notes
- WAC outputs include alkalinity and CO2 metrics; H-form breakthrough uses alkalinity.
- Request limit ~10 MB. Simulation timeout uses `MCP_SIMULATION_TIMEOUT_S`.
- Set `PHREEQC_EXE` if PHREEQC is not on PATH.

### Important: MCP Client Timeout Configuration
For long-running simulations (>5 minutes), configure MCP client timeouts before starting Claude Code:
```bash
export MCP_TOOL_TIMEOUT=900  # 15 minutes for tool calls
claude
```
See MCP_TIMEOUT_CONFIG.md for detailed configuration instructions.

See API_REFERENCE.md for complete field definitions.
