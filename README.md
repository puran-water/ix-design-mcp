# IX Design MCP Server

An MCP (Model Context Protocol) server for SAC ion exchange system design, specifically tailored for RO pretreatment in industrial wastewater applications. This server powers process engineering AI agents with specialized SAC ion exchange design capabilities using Direct PHREEQC simulation.

## Overview

This MCP server provides AI-powered tools for designing and simulating SAC (Strong Acid Cation) ion exchange systems. It performs hydraulic sizing based on industry-standard design parameters and uses Direct PHREEQC engine for accurate breakthrough curve prediction without relying on heuristic capacity factors.

## Features

- **SAC-Only Configuration**: Focused on single-vessel SAC systems for RO pretreatment
- **Direct PHREEQC Engine**: Uses PHREEQC TRANSPORT for accurate breakthrough predictions
- **Resolution-Independent**: PHREEQC determines actual operating capacity and competition effects
- **Target Hardness Breakthrough**: Dynamic simulation until target effluent quality is reached
- **No Mock Data**: All results come from actual PHREEQC calculations
- **FastMCP Framework**: Built on FastMCP for high-performance async operations
- **Three-Tool Architecture**: Separate tools for configuration, simulation, and plotting to prevent import-time delays

## Tools

### configure_sac_ix
Performs hydraulic sizing for SAC vessels with:
- Service flow rate: 16 BV/hr design basis
- Linear velocity: 25 m/hr maximum
- Minimum bed depth: 0.75 m
- N+1 redundancy (1 service + 1 standby)
- Shipping container constraint: 2.4 m max diameter
- Returns bed volume for direct use in simulation
- **Fast loading** - No heavy dependencies

### simulate_sac_ix
Performs Direct PHREEQC simulation with:
- Uses bed volume directly from configuration
- PHREEQC TRANSPORT for breakthrough curves
- Dynamic breakthrough detection based on target hardness
- Real capacity factors from PHREEQC (no heuristics)
- Effluent hardness monitoring (Ca × 2.5 + Mg × 4.1 as CaCO3)
- Automatic simulation extension if breakthrough not found
- **Smart breakthrough sampling**: ~90% data reduction while preserving critical detail
- Optional `full_data` parameter for complete resolution

### plot_breakthrough_curves
Generates breakthrough curve visualizations:
- Multiple output formats: PNG, HTML, CSV
- Interactive HTML plots with Plotly (zoom, pan, hover)
- Static PNG plots with matplotlib (150 DPI)
- CSV export for external analysis
- Lazy imports - matplotlib/plotly only loaded when needed
- Completely optional - simulation can run without plotting

## Design Philosophy

- **Hydraulic Sizing**: Configuration tool handles vessel geometry only
- **Chemistry in PHREEQC**: All ion exchange chemistry, selectivity, and competition handled by PHREEQC
- **No Heuristics**: No capacity derating factors or empirical corrections
- **Target-Based Operation**: Simulation continues until effluent exceeds target hardness

## Performance Architecture

The three-tool architecture eliminates hanging issues that can occur with MCP stdio transport:

| Tool | Load Time | Dependencies | Purpose |
|------|-----------|--------------|---------|
| configure_sac_ix | ~0.3s | Basic Python only | Fast vessel sizing |
| simulate_sac_ix | ~3-4s | PHREEQC engines | Breakthrough simulation |
| plot_breakthrough_curves | ~0.015s* | Lazy matplotlib/plotly | Optional visualization |

*Plotting tool loads instantly but imports matplotlib/plotly only when actually generating plots.

### Why Three Tools?

1. **No More Hanging**: Configuration tool loads instantly without matplotlib
2. **Flexibility**: Run simulations without plotting overhead
3. **Performance**: Each tool only imports what it needs
4. **Optional Plotting**: Visualization is completely optional

The separation ensures that the MCP handshake completes immediately for all tools, preventing the timeout issues that occurred when matplotlib was imported at module level.

## Installation

### Prerequisites
- Python 3.8+
- Git

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd ix-design-mcp
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure PHREEQC database path (if needed):
```bash
export PHREEQC_DATABASE_PATH=/path/to/phreeqc/database
```

## Usage

### Starting the Server

```bash
python server.py
```

### Example Configuration Request

```json
{
  "configuration_input": {
    "water_analysis": {
      "flow_m3_hr": 100,
      "ca_mg_l": 80.06,
      "mg_mg_l": 24.29,
      "na_mg_l": 838.9,
      "hco3_mg_l": 121.95,
      "pH": 7.8,
      "cl_mg_l": 1435
    },
    "target_hardness_mg_l_caco3": 5.0
  }
}
```

### Example Configuration Response

```json
{
  "status": "success",
  "configuration": {
    "vessels": {
      "service": 1,
      "standby": 1,
      "total": 2
    },
    "vessel_geometry": {
      "diameter_m": 2.4,
      "bed_depth_m": 2.21,
      "total_height_m": 4.42,
      "bed_volume_L": 10000
    },
    "hydraulic_parameters": {
      "service_flow_m3_hr": 100,
      "linear_velocity_m_hr": 22.1,
      "bed_volumes_per_hour": 10.0
    }
  }
}
```

### Example Simulation Request

Pass the configuration response directly to the simulation tool:

```json
{
  "configuration": { /* configuration response from above */ },
  "water_analysis": { /* same water analysis */ },
  "target_hardness_mg_l_caco3": 5.0,
  "simulation_time_hours": 24
}
```

### Example Simulation Response

```json
{
  "status": "success",
  "breakthrough_bv": 118.6,
  "service_time_hours": 7.4,
  "breakthrough_hardness_mg_l_caco3": 5.0,
  "phreeqc_determined_capacity_factor": 0.42,
  "breakthrough_data": {
    "bed_volumes": [0.0, 1.0, 2.0, ...],
    "ca_pct": [0.0, 0.1, 0.2, ...],
    "mg_pct": [0.0, 0.1, 0.3, ...],
    "na_mg_l": [1800, 1750, 1700, ...],
    "hardness_mg_l": [0.0, 0.5, 1.0, ...]
  },
  "warnings": []
}
```

### Example Plotting Request

Use the breakthrough data from simulation to generate plots:

```json
{
  "breakthrough_data": { /* from simulation response */ },
  "feed_na_mg_l": 838.9,
  "target_hardness_mg_l": 5.0,
  "output_format": "html"
}
```

### Example Plotting Response

```json
{
  "status": "success",
  "output_path": "output/plots/breakthrough_curves_20250728_184449.html",
  "output_format": "html",
  "file_size_kb": 36.88
}
```

## Water Chemistry Format

Use simple mg/L notation for all ions:
- Required: `ca_mg_l`, `mg_mg_l`, `na_mg_l`, `hco3_mg_l`, `pH`
- Optional anions: `cl_mg_l` (auto-balanced if not provided), `so4_mg_l`, `co3_mg_l`, `no3_mg_l`
- Optional cations: `k_mg_l`, `nh4_mg_l`, `fe2_mg_l`, `fe3_mg_l`
- Optional neutrals: `co2_mg_l`, `sio2_mg_l`, `b_oh_3_mg_l`

## Integration with AI Agents

This MCP server is designed to power process engineering AI agents by providing:
- Standardized tool interfaces for SAC ion exchange design
- Direct PHREEQC integration for accurate predictions
- Resolution-independent breakthrough modeling
- Simple JSON-based communication

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: Create an issue in the repository
- Documentation: See `/docs` folder
- Examples: See `/examples` folder

## Acknowledgments

- Built on the FastMCP framework for high-performance async operations
- Uses PHREEQC TRANSPORT for ion exchange breakthrough modeling
- Integrates WaterTAP property models for water chemistry
- Direct PHREEQC integration pattern inspired by phreeqc-pse approaches