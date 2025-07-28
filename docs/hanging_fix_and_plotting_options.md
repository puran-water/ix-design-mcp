# MCP Server Hanging Fix and New Plotting Options

## Problem Solved

The configuration tool was hanging on first call due to matplotlib's slow initial import (~3.5 seconds). The issue was caused by `tools/__init__.py` importing both configuration and simulation tools, creating unnecessary coupling.

## Solution Implemented

### 1. Removed Tool Coupling
Modified `tools/__init__.py` to only export shared utilities, not the tools themselves. This ensures tools remain independent and are only imported when explicitly needed.

### 2. Lazy Matplotlib Import
Moved matplotlib imports inside the plotting methods, so it's only loaded when actually generating plots.

### 3. New Output Format Options
Added `output_format` parameter to `simulate_sac_phreeqc()`:

```python
def simulate_sac_phreeqc(
    input_data: SACSimulationInput,
    output_format: Literal['none', 'png', 'html', 'csv', 'all'] = 'none'
) -> SACSimulationOutput:
```

#### Output Formats:
- **'none'** (default): No plotting, fastest response for API calls
- **'png'**: Traditional matplotlib PNG plot
- **'html'**: Interactive Plotly HTML plot with zoom/pan/hover
- **'csv'**: Export raw data to CSV file
- **'all'**: Generate all output formats

## Performance Improvements

| Operation | Before | After |
|-----------|--------|-------|
| Configuration tool import | ~3.5s | ~0.3s |
| Configuration call | Hanging | Instant |
| Simulation (no plot) | ~40s | ~35s |
| Simulation (with plot) | ~40s | ~40s |

## New Features

### Interactive HTML Plots
When using `output_format='html'`, generates interactive plots with:
- Zoom and pan functionality
- Hover tooltips showing exact values
- Export to PNG button built-in
- Smaller file size using CDN for Plotly library

### Raw Data Export
All non-'none' formats now include raw breakthrough data:
```python
breakthrough_data = {
    'bed_volumes': [...],
    'ca_pct': [...],
    'mg_pct': [...],
    'na_mg_l': [...],
    'hardness_mg_l': [...],
    'target_hardness': 5.0
}
```

### CSV Export
Export data for external analysis or custom plotting:
```csv
bed_volumes,ca_pct,mg_pct,na_mg_l,hardness_mg_l,target_hardness
0.000,0.000,0.000,850.000,0.000,5.0
0.259,0.000,0.000,892.345,0.000,5.0
...
```

## Usage Examples

### API/MCP Usage (Fast, No Plotting)
```python
# Default behavior - no plotting overhead
result = simulate_sac_phreeqc(input_data)  # output_format='none'
```

### Generate Interactive HTML
```python
# For user-facing applications
result = simulate_sac_phreeqc(input_data, output_format='html')
# Access at: result.plot_html_path
```

### Traditional PNG Plot
```python
# For reports or documentation
result = simulate_sac_phreeqc(input_data, output_format='png')
# Access at: result.plot_path
```

### Export Data Only
```python
# For custom analysis
result = simulate_sac_phreeqc(input_data, output_format='csv')
# Access at: result.breakthrough_data_path
```

## Technical Details

### Import Chain Before Fix
```
server.py 
  → tools.sac_configuration (via `from tools.sac_configuration import ...`)
  → tools/__init__.py (Python loads package first)
  → tools.sac_simulation (unnecessary import)
  → matplotlib (3.5s import time)
```

### Import Chain After Fix
```
server.py 
  → tools.sac_configuration (direct import)
  → tools/__init__.py (only utilities, no tool imports)
  ✗ No matplotlib import
```

### MCP Server Default
The MCP server now uses `output_format='none'` by default, ensuring fast response times without plotting overhead. Clients can request specific output formats when needed.

## Migration Guide

For existing code:
1. The default behavior changes from generating PNG to no plotting
2. To maintain old behavior, explicitly pass `output_format='png'`
3. Consider using 'html' for better user experience
4. Raw data is now available for custom visualizations

## Dependencies

Optional dependencies for full functionality:
- `plotly`: For HTML interactive plots
- `pandas`: For optimized CSV export (falls back to manual writing if not installed)