# IX Design MCP Server

A comprehensive MCP (Model Context Protocol) server for ion exchange system design, supporting both SAC (Strong Acid Cation) and WAC (Weak Acid Cation) resins. Features universal enhancements for temperature correction, ionic strength effects, mass transfer zones, and capacity degradation. Specifically tailored for industrial water treatment applications with Direct PHREEQC simulation.

## Overview

This MCP server provides AI-powered tools for designing and simulating complete ion exchange cycles for both SAC and WAC systems. It performs hydraulic sizing based on industry-standard design parameters and uses Direct PHREEQC engine for accurate breakthrough curve prediction. The system includes universal enhancements that model real-world effects like temperature variations, ionic strength corrections, and resin aging. Designed for seamless integration into larger agentic industrial wastewater treatment workflows.

## Supported Resin Types

### SAC (Strong Acid Cation)
- Complete hardness removal for RO pretreatment
- High capacity across all pH ranges
- Na-form standard operation
- Complete regeneration with NaCl, HCl, or H₂SO₄

### WAC (Weak Acid Cation)
- **WAC Na-form**: Efficient hardness removal with lower regenerant usage
- **WAC H-form**: Alkalinity removal limited to temporary hardness
- pH-dependent capacity (optimal pH > 7)
- Lower regenerant requirements than SAC
- Post-processing ensures H-form limitations are properly modeled

## Features

### Core Capabilities
- **Multi-Resin Support**: SAC, WAC-Na, and WAC-H configurations
- **Complete Cycle Simulation**: Models full industrial IX cycles including service, backwash, regeneration, and rinse phases
- **Direct PHREEQC Engine**: Uses PHREEQC TRANSPORT for thermodynamically accurate predictions
- **Multi-Ion Competition**: Accurately models Ca²⁺, Mg²⁺, Na⁺, K⁺, and H⁺ competition effects
- **Resolution-Independent**: PHREEQC determines actual operating capacity without heuristic factors
- **Target-Based Operation**: Dynamic simulation until target effluent quality is reached
- **FastMCP Framework**: Built on FastMCP for high-performance async operations

### Universal Enhancement Features
- **Ionic Strength Corrections**: Davies equation for activity coefficient adjustments
- **Temperature Corrections**: Van't Hoff equation for selectivity temperature dependence
- **Mass Transfer Zone (MTZ) Modeling**: Accounts for concentration gradients in bed
- **Capacity Degradation**: Models aged or fouled resins with reduced capacity
- **H-form Leakage**: Na⁺/K⁺ leakage calculations for H-form resins
- **CO₂ Generation Tracking**: Monitors CO₂ production from alkalinity removal
- **Universal Exchange Species Generator**: Consistent selectivity modeling across all resins

### WAC-Specific Features
- **pH-Dependent Capacity**: Properly models carboxylic acid functional groups
- **Temporary Hardness Limitation**: H-form removes only alkalinity-associated hardness
- **Post-Processing Corrections**: Ensures realistic H-form performance predictions
- **Alkalinity Tracking**: Monitors HCO₃⁻ removal and pH changes
- **Dual Regeneration**: Acid step for H-form conversion, caustic for Na-form

### Regeneration Features
- **Multi-Stage Counter-Current**: 3-10 stage regeneration with optimization
- **Multiple Regenerants**: Support for NaCl, HCl, H₂SO₄, and NaOH
- **Industry-Standard Dosing**: Specify regenerant dose in g/L resin
- **Auto-Optimization**: Finds optimal regenerant dose for target recovery
- **Waste Stream Analysis**: Complete characterization of regenerant waste

### Integration Features
- **Workflow-Ready Outputs**: Structured data for downstream process integration
- **Cycle Timing Data**: Service time, regeneration time, total cycle time
- **Mass Balance Data**: Total hardness/alkalinity removed, regenerant consumed
- **Enhancement Parameters**: Configurable for site-specific conditions
- **Notebook-Based Reports**: Professional HTML reports with interactive visualizations

## Tools

### configure_sac_ix
Performs hydraulic sizing for SAC vessels with:
- Service flow rate: 16 BV/hr design basis
- Linear velocity: 25 m/hr maximum
- Minimum bed depth: 0.75 m
- N+1 redundancy (1 service + 1 standby)
- Returns bed volume for direct use in simulation
- **Fast loading** - No heavy dependencies

### configure_wac_ix
Performs hydraulic sizing for WAC vessels with:
- Support for both Na-form and H-form configurations
- Automatic capacity adjustment based on resin type
- pH-dependent capacity considerations
- Similar hydraulic constraints as SAC
- Lower regenerant requirements factored into sizing

### simulate_sac_ix
Performs complete SAC cycle simulation with Direct PHREEQC:
- **Service Phase**: 
  - PHREEQC TRANSPORT for breakthrough curves
  - Dynamic breakthrough detection based on target hardness
  - Universal enhancements applied (if enabled)
  - Real capacity factors from competition effects
- **Regeneration Phase**:
  - Multi-stage counter-current regeneration
  - Industry-standard dosing (g regenerant/L resin)
  - Complete waste stream characterization
- **Enhancement Options**:
  - `capacity_factor`: 0.0-1.0 for aged resins
  - `enable_enhancements`: Enable/disable universal corrections
  - Temperature and ionic strength auto-calculated

### simulate_wac_ix
Performs complete WAC cycle simulation with Direct PHREEQC:
- **Service Phase**:
  - Separate models for Na-form and H-form
  - H-form limited to temporary hardness removal
  - Alkalinity tracking and pH monitoring
  - Universal enhancements applied (if enabled)
- **Regeneration Phase**:
  - Two-step for WAC: acid (H-form) + caustic (Na-form)
  - Lower chemical requirements than SAC
  - Optimized staging for efficiency
- **Special Features**:
  - Post-processing for H-form limitations
  - CO₂ generation calculations
  - pH depression tracking

### run_sac_notebook_analysis (Recommended)
Executes integrated analysis with Jupyter notebook:
- Combines simulation and visualization in one tool
- Generates interactive HTML reports
- Professional engineering report format
- Automatic unit conversion and data handling
- Supports all enhancement parameters

## Design Philosophy

- **Hydraulic Sizing**: Configuration tools handle vessel geometry only
- **Chemistry in PHREEQC**: All ion exchange chemistry, selectivity, and competition handled by PHREEQC
- **Universal Enhancements**: Consistent correction methods across all resin types
- **No Heuristics**: Direct thermodynamic calculations with optional real-world corrections
- **Target-Based Operation**: Simulation continues until effluent exceeds target quality

## Enhancement Configuration

All enhancements can be individually configured through `CONFIG` parameters:

### Control Flags
- `ENABLE_IONIC_STRENGTH_CORRECTION`: Apply Davies equation corrections (default: True)
- `ENABLE_TEMPERATURE_CORRECTION`: Apply van't Hoff corrections (default: True)
- `ENABLE_MTZ_MODELING`: Include mass transfer zone effects (default: True)
- `ENABLE_CAPACITY_DEGRADATION`: Model resin aging/fouling (default: True)
- `ENABLE_H_FORM_LEAKAGE`: Calculate Na/K leakage for H-forms (default: True)
- `ENABLE_CO2_TRACKING`: Monitor CO₂ generation (default: True)

### Key Parameters
- `capacity_factor`: 0.0-1.0, manual capacity reduction (default: 1.0)
- `temperature_celsius`: Operating temperature for corrections
- `cycles_operated`: Number of service cycles for degradation calculations
- `particle_diameter_mm`: Resin bead size for MTZ calculations (default: 0.65)

## Technical Architecture

### Class Hierarchy
```
BaseIXSimulation (Abstract)
├── SACSimulation
└── BaseWACSimulation (Abstract)
    ├── WacNaSimulation
    └── WacHSimulation
```

### Universal Enhancement Methods
All simulations inherit these methods from `BaseIXSimulation`:
- `calculate_ionic_strength()`: Computes ionic strength from water composition
- `adjust_selectivity_for_ionic_strength()`: Davies equation implementation
- `calculate_temperature_correction()`: Van't Hoff equation implementation
- `calculate_mtz_length()`: Mass transfer zone calculations
- `apply_capacity_degradation()`: Aging and fouling effects
- `calculate_h_form_leakage()`: Na/K leakage for H-forms
- `track_co2_generation()`: CO₂ production from alkalinity
- `generate_enhanced_exchange_species()`: Universal EXCHANGE_SPECIES generator

## Installation

### Prerequisites
- Python 3.8+
- Git

### Setup

1. Clone the repository:
```bash
git clone https://github.com/puran-water/ix-design-mcp.git
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

## Usage Examples

### SAC Configuration Request

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
      "cl_mg_l": 1435,
      "temperature_celsius": 25
    },
    "target_hardness_mg_l_caco3": 5.0
  }
}
```

### WAC Configuration Request

```json
{
  "configuration_input": {
    "water_analysis": {
      "flow_m3_hr": 100,
      "ca_mg_l": 120,
      "mg_mg_l": 40,
      "na_mg_l": 50,
      "hco3_mg_l": 300,
      "pH": 7.5,
      "cl_mg_l": 150,
      "temperature_celsius": 20
    },
    "resin_type": "WAC_H",  // or "WAC_Na"
    "target_hardness_mg_l_caco3": 10.0
  }
}
```

### SAC Simulation with Enhancements

```json
{
  "water_analysis": { /* same as configuration */ },
  "vessel_configuration": { /* from configuration response */ },
  "target_hardness_mg_l_caco3": 5.0,
  "capacity_factor": 0.85,  // 15% capacity loss from aging
  "temperature_celsius": 30,  // Higher temperature operation
  "regeneration_config": {
    "regenerant_type": "NaCl",
    "concentration_percent": 10,
    "regenerant_dose_g_per_L": 100,
    "mode": "staged_optimize",
    "target_recovery": 0.90,
    "regeneration_stages": 5
  }
}
```

### WAC H-form Simulation

```json
{
  "water_analysis": { /* same as configuration */ },
  "vessel_configuration": { /* from configuration response */ },
  "resin_type": "WAC_H",
  "target_hardness_mg_l_caco3": 10.0,
  "target_alkalinity_mg_l_caco3": 5.0,  // H-form specific
  "capacity_factor": 1.0,  // Fresh resin
  "regeneration_config": {
    "regenerant_type": "HCl",
    "concentration_percent": 5,
    "regenerant_dose_g_per_L": 60,  // Lower than SAC
    "mode": "staged_fixed",
    "regeneration_stages": 3
  }
}
```

### Example Simulation Response with Breakthrough vs Average Metrics

```json
{
  "status": "success",
  "service_phase": {
    "breakthrough_bv": 118.6,
    "service_time_hours": 7.4,
    "breakthrough_hardness_mg_l_caco3": 5.0,
    "phreeqc_determined_capacity_factor": 0.36,  // With enhancements
    "total_hardness_removed_kg": 45.2,
    "mtz_length_m": 0.25,  // Mass transfer zone
    "effective_bed_depth_m": 1.95
  },
  "performance_metrics": {
    // Critical breakthrough values for equipment design
    "breakthrough_ca_removal_percent": 87.5,
    "breakthrough_mg_removal_percent": 82.1,
    "breakthrough_hardness_removal_percent": 85.2,
    "breakthrough_alkalinity_removal_percent": 84.8,  // WAC H-form example
    // Average operational values for economics
    "avg_ca_removal_percent": 99.8,
    "avg_mg_removal_percent": 99.9,
    "avg_hardness_removal_percent": 99.85,
    "avg_alkalinity_removal_percent": 99.996,
    "average_effluent_ph": 6.2,
    "co2_generation_mg_l": 45
  },
  "regeneration_phase": {
    "regenerant_consumed_kg": 120.5,
    "regenerant_volume_L": 3500,
    "peak_waste_tds_mg_l": 25000,
    "final_recovery_percent": 93.5
  },
  "enhancements_applied": {
    "ionic_strength_mol_l": 0.045,
    "temperature_correction_factor": 0.92,
    "capacity_degradation_factor": 0.85,
    "na_leakage_mg_l": 1.2,  // For H-form
    "co2_generated_mg_l": 45  // From alkalinity removal
  },
  "cycle_summary": {
    "total_cycle_time_hours": 9.9,
    "bed_volumes_treated": 118.6,
    "water_treated_m3": 1186
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
- **Operating conditions**: `temperature_celsius` (5-40°C), `pressure_bar`

### Water Quality Ranges Supported
- **TDS**: 100 - 10,000 mg/L (residential to industrial)
- **Hardness**: 50 - 2,000 mg/L as CaCO₃
- **Alkalinity**: 20 - 1,000 mg/L as CaCO₃
- **pH**: 5.0 - 9.0
- **Temperature**: 5 - 40°C
- **Sodium**: Up to 5,000 mg/L (high TDS applications)

### WAC-Specific Considerations
- **H-form Operation**: Requires alkalinity for effective hardness removal
- **Temporary Hardness**: Ca/Mg associated with HCO₃⁻ (removable by H-form)
- **Permanent Hardness**: Ca/Mg associated with Cl⁻/SO₄²⁻ (not removed by H-form)
- **pH Effects**: WAC capacity increases with pH (optimal > 7)

## Integration with AI Agents

This MCP server is designed to power process engineering AI agents by providing:
- Standardized tool interfaces for both SAC and WAC ion exchange design
- Direct PHREEQC integration for accurate predictions
- Universal enhancement framework for real-world corrections
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

#### SAC Capacity
- **Gel Type**: 2.0 eq/L
- **Macroporous**: 1.8 eq/L
- **Selectivity Order**: Pb²⁺ > Ba²⁺ > Sr²⁺ > Ca²⁺ > Mg²⁺ > K⁺ > NH₄⁺ > Na⁺ > H⁺
- **Regeneration Efficiency**: 90-95% with proper staging

#### WAC Capacity
- **Na-form**: 4.5 eq/L (pH > 7)
- **H-form**: 4.2 eq/L (pH dependent)
- **Selectivity Order**: H⁺ > Ca²⁺ > Mg²⁺ > K⁺ > Na⁺
- **pKa**: ~4.5 (carboxylic acid groups)
- **Regeneration Efficiency**: 95-98% (lower regenerant requirement)

### Design Constraints
- **Service Flow**: 8-16 BV/hr (design at 16 BV/hr for SAC, 12 BV/hr for WAC)
- **Linear Velocity**: 25 m/hr maximum
- **Bed Depth**: 0.75 m minimum, 3.0 m typical maximum
- **Vessel Diameter**: 2.4 m maximum (shipping constraint)
- **Regeneration Flow**: 2-4 BV/hr counter-current
- **Temperature Range**: 5-40°C (corrections applied outside 20-30°C)

### Performance Metrics

#### Critical Design Metrics Update (v2.0.1)
Performance metrics now correctly report **breakthrough values** (worst-case) for equipment design instead of misleading averages:

- **Breakthrough Metrics**: Values at the breakthrough point when target is reached
  - Used for equipment sizing and design (worst-case scenarios)
  - WAC H-form: ~85% alkalinity removal at breakthrough
  - SAC: 100% hardness removal at target breakthrough
- **Average Metrics**: Average performance over the service cycle
  - Used for operational estimates and economic analysis
  - WAC H-form: 99.996% average alkalinity removal
  - Much higher than breakthrough values due to excellent initial performance

This ensures proper equipment sizing based on end-of-cycle quality, not optimistic averages.

#### General Performance Characteristics
- **Breakthrough Definition**: Target hardness/alkalinity (not 50% breakthrough)
- **Capacity Utilization**: 
  - SAC: 30-60% depending on water quality
  - WAC: 40-70% (higher efficiency than SAC)
- **Regeneration Recovery**: 90-95% with proper staging
- **Water Recovery**: >99% (minimal waste)
- **Enhancement Impact**: ±20% capacity adjustment typical

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
- API Reference: See API_REFERENCE.md for detailed tool documentation
- Enhancement Details: See ENHANCEMENTS.md for technical specifications

## Acknowledgments

- Built on the FastMCP framework for high-performance async operations
- Uses PHREEQC v3 geochemical simulator from USGS for transport modeling
- Ion exchange selectivity data from PHREEQC's built-in EXCHANGE_SPECIES definitions
- Enhancement correlations based on literature and industrial best practices
- Designed for integration with WaterTAP/IDAES process modeling frameworks