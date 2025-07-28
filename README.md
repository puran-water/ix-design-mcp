# IX Design MCP Server

An MCP (Model Context Protocol) server for ion exchange system design and optimization, specifically tailored for RO pretreatment in industrial wastewater zero liquid discharge (ZLD) applications. This server powers process engineering AI agents with specialized ion exchange design capabilities.

## Overview

This MCP server provides AI-powered tools for designing and simulating ion exchange (IX) systems. It automatically selects from three flowsheet configurations based on water chemistry, performs hydraulic sizing, simulates breakthrough curves, and provides comprehensive economic analysis.

## Features

- **Multi-Configuration Analysis**: Returns all 3 viable flowsheet options with complete sizing
- **Water Chemistry Intelligence**: Automatic flowsheet selection based on hardness distribution
- **Na+ Competition Modeling**: Sophisticated selectivity models for real-world performance
- **Economic Optimization**: WaterTAP-based CAPEX/OPEX/LCOW calculations (see WATERTAP_COSTING_GAPS.md for limitations)
- **MCAS Integration**: Seamless compatibility with RO design tools
- **PhreeqPy Integration**: PHREEQC-based equilibrium calculations for accurate predictions

## Tools

### optimize_ix_configuration
Generates all three flowsheet alternatives with:
- Vessel sizing and counts (service + standby)
- Resin volumes and bed depths
- Degasser specifications
- Complete economic analysis
- Na+ competition factors

### simulate_ix_system
Performs detailed breakthrough simulation using **papermill notebook execution** for process isolation:
- Executes in subprocess to prevent WaterTAP/PhreeqPy conflicts with MCP server
- Service cycle runtime predictions
- Regenerant consumption calculations
- Water quality progression through treatment
- Breakthrough curve generation
- Waste volume estimation

**Note**: Notebook execution is REQUIRED (not optional) to ensure process isolation

## Flowsheet Options

1. **H-WAC → Degasser → Na-WAC**: For waters with >90% temporary hardness
2. **SAC → Na-WAC → Degasser**: For waters with significant permanent hardness  
3. **Na-WAC → Degasser**: For simple water chemistry with low hardness

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
  "water_analysis": {
    "flow_m3_hr": 100,
    "temperature_celsius": 25,
    "pressure_bar": 1.0,
    "pH": 7.5,
    "ion_concentrations_mg_L": {
      "Na_+": 200,
      "Ca_2+": 100,
      "Mg_2+": 40,
      "HCO3_-": 250,
      "Cl_-": 350,
      "SO4_2-": 150
    }
  },
  "design_criteria": {
    "min_runtime_hours": 8,
    "max_vessels_per_stage": 3
  }
}
```

### Example Response Structure

```json
{
  "status": "success",
  "configurations": [
    {
      "flowsheet_type": "sac_na_wac_degasser",
      "economics": {
        "capital_cost_usd": 2720792,
        "annual_opex_usd": 780759,
        "cost_per_m3": 1.50
      },
      "ix_vessels": {
        "SAC": {
          "service_vessels": 2,
          "standby_vessels": 1,
          "diameter_m": 3.0,
          "height_m": 3.5,
          "resin_volume_m3": 18.85
        }
      }
    }
  ]
}
```

## Water Chemistry Format (MCAS)

Use MCAS notation for all ions:
- Cations: `Na_+`, `Ca_2+`, `Mg_2+`, `K_+`, `H_+`, `NH4_+`, `Fe_2+`, `Fe_3+`
- Anions: `Cl_-`, `SO4_2-`, `HCO3_-`, `CO3_2-`, `NO3_-`, `PO4_3-`, `F_-`, `OH_-`
- Neutrals: `CO2`, `SiO2`, `B(OH)3`

## Integration with AI Agents

This MCP server is designed to power process engineering AI agents by providing:
- Standardized tool interfaces for IX system design
- Comprehensive performance predictions
- Economic optimization capabilities
- Water chemistry expertise

## Testing

Run the test suite:
```bash
python -m pytest tests/
```

Run integration tests:
```bash
python tests/test_mcp_server_integration.py
```

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

- Built on the MCP (Model Context Protocol) framework
- Uses PHREEQC for geochemical calculations
- Incorporates WaterTAP property models
- Economics based exclusively on WaterTAP costing functions