# Notebook-Based SAC Analysis

This directory contains Jupyter notebooks for ion exchange analysis workflows that can be executed through the MCP server.

## Overview

The notebook-based approach solves several issues with the traditional separate simulation + plotting workflow:

1. **No Unit Conversion Issues**: The simulation output stays in the notebook context, eliminating mg/L vs percentage confusion
2. **Rich Output**: Generates complete HTML reports with interactive plots and tables
3. **Single Tool Call**: One MCP tool call provides complete analysis
4. **Reproducible**: Notebooks can be re-run or modified later

## Available Notebooks

### sac_breakthrough_analysis.ipynb

Complete SAC ion exchange cycle analysis including:
- Service phase simulation to breakthrough
- Regeneration optimization or fixed-dose simulation
- Interactive breakthrough curve plots
- Summary tables and key metrics

## Usage via MCP Server

The `run_sac_notebook_analysis` tool executes notebooks with parameters:

```json
{
  "water_analysis": {
    "flow_m3_hr": 100,
    "ca_mg_l": 80,
    "mg_mg_l": 25,
    "na_mg_l": 800,
    "hco3_mg_l": 120,
    "pH": 7.5
  },
  "vessel_configuration": {
    "bed_volume_L": 1000,
    "service_flow_rate_bv_hr": 16,
    // ... other vessel parameters
  },
  "target_hardness_mg_l_caco3": 5.0,
  "regeneration_config": {
    "mode": "staged_optimize",
    "target_recovery": 0.90
    // ... other regeneration parameters
  }
}
```

## Output

Each execution creates:
1. **Executed notebook** (`output/notebooks/sac_analysis_TIMESTAMP.ipynb`)
2. **HTML report** (`output/notebooks/sac_analysis_TIMESTAMP.html`)
3. **JSON results** returned by the MCP tool

## Technical Implementation

### Key Design Principles

1. **DRY Code**: Notebooks only call functions from existing modules
2. **Parameterized**: Uses papermill for parameter injection
3. **Result Extraction**: Structured results stored in notebook for extraction
4. **Error Handling**: Continues execution even if some cells fail

### Required Packages

```bash
pip install papermill nbformat nbconvert
```

### Adding New Notebooks

1. Create notebook template in this directory
2. Tag parameter cell with 'parameters'
3. Store results in a structured format for extraction
4. Update notebook_runner.py to support new notebook type

## Advantages Over Direct Tool Calls

1. **Context Preservation**: All data stays in notebook environment
2. **Visual Output**: Plots are embedded in the report
3. **Debugging**: Can step through notebook interactively
4. **Extensibility**: Easy to add new analyses or visualizations

## Example Results

A typical analysis provides:
- Breakthrough at X bed volumes
- Service time of Y hours
- Regeneration achieving Z% recovery
- Interactive plots showing full cycle behavior
- Detailed phase-by-phase progression