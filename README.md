# IX Design MCP Server

An MCP (Model Context Protocol) server for SAC ion exchange system design, specifically tailored for RO pretreatment in industrial wastewater applications. This server powers process engineering AI agents with specialized SAC ion exchange design capabilities using Direct PHREEQC simulation for complete service and regeneration cycle modeling.

## Overview

This MCP server provides AI-powered tools for designing and simulating complete SAC (Strong Acid Cation) ion exchange cycles. It performs hydraulic sizing based on industry-standard design parameters and uses Direct PHREEQC engine for accurate breakthrough curve prediction and regeneration modeling without relying on heuristic capacity factors. Designed for seamless integration into larger agentic industrial wastewater treatment workflows.

## Features

### Core Capabilities
- **Complete Cycle Simulation**: Models full industrial IX cycles including service, backwash, regeneration, and rinse phases
- **Direct PHREEQC Engine**: Uses PHREEQC TRANSPORT for thermodynamically accurate predictions
- **Multi-Ion Competition**: Accurately models Ca²⁺, Mg²⁺, and Na⁺ competition effects
- **Resolution-Independent**: PHREEQC determines actual operating capacity without heuristic factors
- **Target-Based Operation**: Dynamic simulation until target effluent hardness is reached
- **FastMCP Framework**: Built on FastMCP for high-performance async operations

### Regeneration Features
- **Multi-Stage Counter-Current**: 3-10 stage regeneration with optimization
- **Multiple Regenerants**: Support for NaCl, HCl, and H₂SO₄
- **Industry-Standard Dosing**: Specify regenerant dose in g/L resin (e.g., NaCl: 80-120 g/L)
- **Auto-Optimization**: Finds optimal regenerant dose for target recovery
- **Waste Stream Analysis**: Complete characterization of regenerant waste (TDS, hardness, volume)

### Integration Features
- **Workflow-Ready Outputs**: Structured data for downstream process integration
- **Cycle Timing Data**: Service time, regeneration time, total cycle time for scheduling
- **Mass Balance Data**: Total hardness removed, regenerant consumed for economics
- **Waste Profiles**: Time-series data for waste treatment system design
- **Notebook-Based Reports**: Professional HTML reports with interactive visualizations

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
Performs complete industrial cycle simulation with Direct PHREEQC:
- **Service Phase**: 
  - PHREEQC TRANSPORT for breakthrough curves
  - Dynamic breakthrough detection based on target hardness
  - Effluent hardness monitoring (Ca × 2.5 + Mg × 4.1 as CaCO₃)
  - Real capacity factors from competition effects
- **Regeneration Phase**:
  - Multi-stage counter-current regeneration
  - Industry-standard dosing (g regenerant/L resin)
  - Auto-optimization for target recovery (90-95%)
  - Complete waste stream characterization
- **Rinse Phases**:
  - Slow rinse (displacement)
  - Fast rinse (quality polish)
- **Smart Data Sampling**: ~90% reduction while preserving critical detail
- **Full Mass Balance**: Hardness removed, regenerant consumed, waste generated

### run_sac_notebook_analysis (Recommended)
Executes integrated analysis with Jupyter notebook:
- Combines simulation and visualization in one tool
- Generates interactive HTML reports
- Professional engineering report format
- Automatic unit conversion and data handling
- No data transfer issues between tools
- Requires papermill package

## Design Philosophy

- **Hydraulic Sizing**: Configuration tool handles vessel geometry only
- **Chemistry in PHREEQC**: All ion exchange chemistry, selectivity, and competition handled by PHREEQC
- **No Heuristics**: No capacity derating factors or empirical corrections
- **Target-Based Operation**: Simulation continues until effluent exceeds target hardness

## Performance Architecture

The streamlined architecture ensures fast response times:

| Tool | Load Time | Dependencies | Purpose |
|------|-----------|--------------|---------|
| configure_sac_ix | ~0.3s | Basic Python only | Fast vessel sizing |
| simulate_sac_ix | ~3-4s | PHREEQC engines | Breakthrough simulation |
| run_sac_notebook_analysis | ~0.5s | papermill (optional) | Integrated analysis |

### Architecture Benefits:

1. **Fast Response**: Configuration tool loads instantly
2. **Modular Design**: Each tool serves a specific purpose
3. **Integrated Analysis**: Notebook tool combines simulation and visualization
4. **No Data Transfer Issues**: Notebook keeps everything in context

The separation ensures clean tool boundaries while the notebook integration provides a complete workflow solution.

## Industrial Workflow Integration

This MCP server is designed as a component in larger agentic industrial wastewater treatment workflows:

### Integration Points

1. **Upstream Integration**:
   - Accepts water quality data from analytical or RO projection tools
   - Compatible with flow rate outputs from hydraulic design tools
   - Can receive target specifications from RO membrane protection requirements

2. **Downstream Data Provision**:
   - **RO Feed Quality**: Softened water composition for RO design
   - **Waste Streams**: Complete characterization for brine treatment design
   - **Scheduling Data**: Cycle times for plant-wide coordination
   - **Chemical Consumption**: Regenerant usage for procurement and storage

3. **Process Control Integration**:
   - Service time prediction for automated valve sequencing
   - Regeneration timing for waste handling coordination
   - Recovery metrics for optimization algorithms
   - Breakthrough curves for operator training/simulation

### Key Outputs for Workflow Integration

```json
{
  "cycle_timing": {
    "service_hours": 7.4,
    "regeneration_hours": 2.5,
    "total_cycle_hours": 9.9
  },
  "mass_balance": {
    "hardness_removed_kg": 45.2,
    "regenerant_consumed_kg": 120.5,
    "recovery_percent": 93.5
  },
  "waste_stream": {
    "volume_m3": 4.5,
    "peak_tds_mg_l": 25000,
    "peak_hardness_mg_l": 8500,
    "average_tds_mg_l": 15000
  },
  "effluent_quality": {
    "average_hardness_mg_l": 2.5,
    "breakthrough_point_bv": 118.6
  }
}
```

### Typical Workflow Sequence

1. **Water Analysis** → IX Design MCP Server (sizing)
2. **IX Configuration** → IX Design MCP Server (simulation)
3. **IX Results** → RO Design Tool (feed water quality)
4. **IX Waste Data** → Brine Treatment Design
5. **Cycle Timing** → Plant Scheduling System

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

## MCP Client Configuration

### Claude Desktop

Add the server to your Claude Desktop configuration file:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ix-design": {
      "command": "python",
      "args": ["C:/Users/your-username/mcp-servers/ix-design-mcp/server.py"],
      "env": {
        "IX_DESIGN_MCP_ROOT": "C:/Users/your-username/mcp-servers/ix-design-mcp"
      }
    }
  }
}
```

**Note**: The `IX_DESIGN_MCP_ROOT` environment variable ensures the server can find notebooks and databases regardless of where the MCP client launches it from.

### Other MCP Clients

For other MCP clients, ensure you set the `IX_DESIGN_MCP_ROOT` environment variable:

```bash
export IX_DESIGN_MCP_ROOT=/path/to/ix-design-mcp
python /path/to/ix-design-mcp/server.py
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

Pass the configuration response directly to the simulation tool with regeneration settings:

```json
{
  "water_analysis": { /* same water analysis */ },
  "vessel_configuration": { /* from configuration response */ },
  "target_hardness_mg_l_caco3": 5.0,
  "regeneration_config": {
    "regenerant_type": "NaCl",
    "concentration_percent": 10,
    "regenerant_dose_g_per_L": 100,  // 100 g NaCl per L resin
    "mode": "staged_optimize",
    "target_recovery": 0.90,
    "regeneration_stages": 5
  }
}
```

### Example Simulation Response

```json
{
  "status": "success",
  "service_phase": {
    "breakthrough_bv": 118.6,
    "service_time_hours": 7.4,
    "breakthrough_hardness_mg_l_caco3": 5.0,
    "phreeqc_determined_capacity_factor": 0.42,
    "total_hardness_removed_kg": 45.2
  },
  "regeneration_phase": {
    "regenerant_consumed_kg": 120.5,
    "regenerant_volume_L": 3500,
    "peak_waste_tds_mg_l": 25000,
    "peak_waste_hardness_mg_l": 8500,
    "total_waste_volume_m3": 4.5,
    "regeneration_time_hours": 2.5,
    "final_recovery_percent": 93.5
  },
  "cycle_summary": {
    "total_cycle_time_hours": 9.9,
    "bed_volumes_treated": 118.6,
    "water_treated_m3": 1186,
    "regeneration_efficiency_g_per_g": 2.67
  },
  "breakthrough_data": {
    "bed_volumes": [0.0, 1.0, 2.0, ...],
    "phases": ["service", "service", "service", ..., "backwash", "regen", ...],
    "ca_pct": [0.0, 0.1, 0.2, ...],
    "mg_pct": [0.0, 0.1, 0.3, ...],
    "na_mg_l": [1800, 1750, 1700, ...],
    "hardness_mg_l": [0.0, 0.5, 1.0, ...],
    "tds_mg_l": [2500, 2550, 2600, ...]
  }
}
```

### Example Notebook Analysis Request

For integrated simulation and visualization, use the notebook analysis tool:

```json
{
  "water_analysis": { /* same as simulation */ },
  "vessel_configuration": { /* from configuration response */ },
  "target_hardness_mg_l_caco3": 5.0,
  "regeneration_config": { /* same as simulation */ }
}
```

### Example Notebook Analysis Response

```json
{
  "status": "success",
  "breakthrough_bv": 118.6,
  "service_time_hours": 7.4,
  "total_cycle_time_hours": 9.9,
  "capacity_factor": 0.42,
  "final_recovery": 93.5,
  "regenerant_kg": 120.5,
  "outputs": {
    "notebook_path": "output/notebooks/sac_analysis_20250131_145632.ipynb",
    "html_path": "output/notebooks/sac_analysis_20250131_145632.html"
  }
}
```

## Water Chemistry Format

### Ion Specification
Use simple mg/L notation for all ions:
- **Required ions**: `ca_mg_l`, `mg_mg_l`, `na_mg_l`, `hco3_mg_l`, `pH`
- **Optional anions**: `cl_mg_l` (auto-balanced if not provided), `so4_mg_l`, `co3_mg_l`, `no3_mg_l`, `f_mg_l`, `po4_mg_l`
- **Optional cations**: `k_mg_l`, `nh4_mg_l`, `fe2_mg_l`, `fe3_mg_l`, `mn2_mg_l`, `ba_mg_l`, `sr_mg_l`
- **Optional neutrals**: `co2_mg_l`, `sio2_mg_l`, `b_oh_3_mg_l`

### Water Quality Ranges Supported
- **TDS**: 100 - 10,000 mg/L (residential to industrial)
- **Hardness**: 50 - 2,000 mg/L as CaCO₃
- **pH**: 5.0 - 9.0
- **Temperature**: 5 - 40°C
- **Sodium**: Up to 5,000 mg/L (high TDS applications)

## Integration with AI Agents

This MCP server is designed to power process engineering AI agents by providing:
- Standardized tool interfaces for SAC ion exchange design
- Direct PHREEQC integration for accurate predictions
- Resolution-independent breakthrough modeling
- Complete cycle simulation for economic optimization
- Simple JSON-based communication

## Technical Specifications

### PHREEQC Integration
- **Engine Options**: 
  - Direct PHREEQC Engine (standard)
  - Optimized PHREEQC Engine (5x faster, when available)
- **Database**: Custom merged PHREEQC database with IX phases
- **Transport Model**: 1D advective-dispersive transport with kinetic exchange
- **Thermodynamic Data**: Ion exchange selectivity coefficients from literature

### Resin Parameters
- **SAC Capacity**: 2.0 eq/L (gel type), 1.8 eq/L (macroporous)
- **Selectivity Order**: Pb²⁺ > Ba²⁺ > Sr²⁺ > Ca²⁺ > Mg²⁺ > K⁺ > NH₄⁺ > Na⁺ > H⁺
- **Kinetic Factor**: 0.95 (fast exchange kinetics)
- **Regeneration Efficiency**: 90% typical, 95% achievable with optimization

### Design Constraints
- **Service Flow**: 8-16 BV/hr (design at 16 BV/hr)
- **Linear Velocity**: 25 m/hr maximum
- **Bed Depth**: 0.75 m minimum, 3.0 m typical maximum
- **Vessel Diameter**: 2.4 m maximum (shipping constraint)
- **Regeneration Flow**: 2-4 BV/hr counter-current

### Performance Metrics
- **Breakthrough Definition**: Target hardness (not 50% breakthrough)
- **Capacity Utilization**: 30-60% depending on water quality
- **Regeneration Recovery**: 90-95% with proper staging
- **Water Recovery**: >99% (minimal waste)

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
- Technical Documentation: See CLAUDE.md for development guidelines
- API Examples: Refer to the usage examples in this README

## Acknowledgments

- Built on the FastMCP framework for high-performance async operations
- Uses PHREEQC v3 geochemical simulator from USGS for transport modeling
- Ion exchange selectivity data from Helfferich, DuPont, and Purolite literature
- Regeneration optimization algorithms based on industrial best practices
- Designed for integration with WaterTAP/IDAES process modeling frameworks