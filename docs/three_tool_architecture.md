# Three-Tool Architecture for IX Design MCP Server

## Overview

The IX Design MCP Server now uses a three-tool architecture that completely eliminates hanging issues and provides maximum flexibility for clients. Each tool has a single responsibility and only imports the dependencies it needs.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌───────────────────────┐
│  configure_sac_ix   │ --> │   simulate_sac_ix    │ --> │ plot_breakthrough_   │
│                     │     │                      │     │      curves           │
│ • Fast import       │     │ • PHREEQC simulation │     │ • Optional plotting   │
│ • No heavy deps     │     │ • Returns data       │     │ • Multiple formats    │
│ • ~0.3s load time   │     │ • No plotting        │     │ • Lazy imports        │
└─────────────────────┘     └──────────────────────┘     └───────────────────────┘
```

## Tool Details

### 1. Configuration Tool (`configure_sac_ix`)
- **Purpose**: Size SAC vessels based on hydraulic constraints
- **Imports**: Only basic Python modules and pydantic
- **Load Time**: ~0.3 seconds
- **Output**: Vessel dimensions and configuration

### 2. Simulation Tool (`simulate_sac_ix`)
- **Purpose**: Run PHREEQC simulation to determine breakthrough
- **Imports**: numpy, PHREEQC engines (but NOT matplotlib)
- **Load Time**: ~3-4 seconds (due to numpy and engines)
- **Output**: Numerical results + raw breakthrough data arrays

### 3. Plotting Tool (`plot_breakthrough_curves`)
- **Purpose**: Generate visualizations from simulation data
- **Imports**: matplotlib/plotly only when called
- **Load Time**: ~0.015 seconds (until actual plotting)
- **Output**: PNG/HTML/CSV files

## Key Benefits

### 1. No More Hanging
- Configuration tool loads instantly (no matplotlib)
- Tools are completely independent
- MCP handshake completes immediately

### 2. Performance
| Operation | Before | After |
|-----------|--------|-------|
| First configuration call | Hanging (~3.5s) | Instant (~0.3s) |
| Simulation without plot | ~40s + matplotlib | ~35s (no matplotlib) |
| Plot generation | Included in simulation | Separate, on-demand |

### 3. Flexibility
- Clients can run simulations without plotting overhead
- Multiple output formats available
- Raw data always available for custom visualization

## Usage Workflow

### Step 1: Configure Vessel
```json
// Request
{
  "water_analysis": {
    "flow_m3_hr": 100,
    "ca_mg_l": 180,
    "mg_mg_l": 80,
    "na_mg_l": 50,
    "hco3_mg_l": 300,
    "pH": 7.5
  },
  "target_hardness_mg_l_caco3": 5.0
}

// Response includes vessel configuration
```

### Step 2: Run Simulation
```json
// Request uses configuration output
{
  "water_analysis": {...},
  "vessel_configuration": {...},
  "target_hardness_mg_l_caco3": 5.0
}

// Response includes breakthrough_data
{
  "breakthrough_bv": 118.6,
  "service_time_hours": 7.4,
  "breakthrough_data": {
    "bed_volumes": [...],
    "ca_pct": [...],
    "mg_pct": [...],
    "na_mg_l": [...],
    "hardness_mg_l": [...]
  }
}
```

### Step 3: Generate Plot (Optional)
```json
// Request
{
  "breakthrough_data": {...},  // From simulation
  "feed_na_mg_l": 50.0,
  "target_hardness_mg_l": 5.0,
  "output_format": "html"  // or "png" or "csv"
}

// Response
{
  "status": "success",
  "output_path": "output/plots/breakthrough_curves_20250728_184449.html",
  "output_format": "html",
  "file_size_kb": 36.88
}
```

## Import Behavior

### Configuration Tool
```python
# Only imports:
- pydantic
- core_config
- unit_conversions
# NO matplotlib, numpy, or plotting libraries
```

### Simulation Tool
```python
# Imports:
- numpy (for arrays)
- PHREEQC engines
- Configuration schemas
# NO matplotlib or plotting libraries
```

### Plotting Tool
```python
# Base imports:
- pydantic
- pathlib
# Lazy imports (only when called):
- matplotlib (for PNG)
- plotly (for HTML)
- pandas (for CSV, with fallback)
```

## Error Handling

Each tool handles errors independently:
- Configuration: Validates water chemistry and constraints
- Simulation: Handles PHREEQC failures gracefully
- Plotting: Falls back if libraries not installed

## Migration from Old Architecture

### Before (Coupled Tools)
```python
# tools/__init__.py imported everything
from .sac_configuration import ...
from .sac_simulation import ...  # This imported matplotlib!
```

### After (Independent Tools)
```python
# tools/__init__.py only has utilities
# Tools imported directly where needed
# No cross-dependencies
```

## Best Practices

1. **Always check if plotting is needed** - Many use cases only need numerical results
2. **Use HTML format for interactive plots** - Better user experience, smaller with CDN
3. **Export CSV for custom analysis** - Allows users to create their own visualizations
4. **Cache simulation results** - Plotting can be repeated without re-running PHREEQC

## Technical Details

### Why Was It Hanging?

1. `tools/__init__.py` imported all tools at package level
2. When importing configuration tool, Python loaded the entire package
3. This triggered simulation tool import, which imported matplotlib
4. Matplotlib's first import takes ~3.5 seconds (font caching, backend setup)
5. MCP's stdio protocol timed out waiting for response

### Solution Implementation

1. Removed tool imports from `__init__.py`
2. Made matplotlib imports lazy (inside functions)
3. Separated plotting into its own tool
4. Each tool now has minimal, focused imports
5. **Added smart breakthrough sampling** to prevent BrokenResourceError

## Smart Breakthrough Sampling

The simulation tool now uses intelligent data sampling to prevent MCP communication errors while preserving critical information:

### Sampling Strategy

| Zone | Distance from Breakthrough | Sampling Rate | Purpose |
|------|---------------------------|---------------|---------|
| Critical | ±10 BV | Every point | Maximum accuracy where it matters |
| Transition | ±10-30 BV | Every 5th point | Capture curve shape |
| Far | >30 BV | Every 20th point | General trend only |

### Results

- **Data reduction**: ~88-93% (1001 → ~114 points)
- **Response size**: ~50KB → ~3KB
- **Critical zone density**: ~2.5 points/BV maintained
- **No more BrokenResourceError** on large simulations

### Optional Full Resolution

```json
{
  "water_analysis": {...},
  "vessel_configuration": {...},
  "target_hardness_mg_l_caco3": 5.0,
  "full_data": true  // Returns all 1000+ points
}
```

## Future Enhancements

1. **Batch Plotting**: Plot multiple simulation results
2. **Plot Customization**: Pass styling options
3. **Additional Formats**: SVG, PDF, interactive dashboards
4. **Caching**: Reuse plots for identical data