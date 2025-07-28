# Active Files in MCP Server Workflow

## Entry Point
- `server.py` - MCP server entry point

## Direct Server Imports
- `tools/ix_configuration.py` - Configuration tool
- `tools/ix_simulation.py` - Simulation tool  
- `tools/schemas.py` - Pydantic schemas

## Notebooks Used by Simulation Tool
- `notebooks/ix_simulation_graybox_template.ipynb` - GrayBox simulation
- `notebooks/ix_simulation_cli_wrapper.ipynb` - CLI wrapper for standard simulation

## CLI System (used by CLI wrapper notebook)
- `ix_cli.py` - Core CLI for IX model execution

## watertap_ix_transport Package (imported by ix_cli.py)
- `watertap_ix_transport/__init__.py`
- `watertap_ix_transport/ion_exchange_transport_0D.py` - Core IX model
- `watertap_ix_transport/ion_exchange_transport_0D_graybox.py` - GrayBox IX model
- `watertap_ix_transport/ion_exchange_transport_0D_graybox_integrated.py` - Integrated GrayBox
- `watertap_ix_transport/utilities/property_calculations.py` - fix_mole_fractions utility
- `watertap_ix_transport/species_alias.py` - PHREEQC species mapping
- `watertap_ix_transport/transport_core/phreeqc_transport_engine.py` - PHREEQC integration
- `watertap_ix_transport/transport_core/direct_phreeqc_engine.py` - Direct PHREEQC execution
- `watertap_ix_transport/phreeqc_translator.py` - PHREEQC translator
- `watertap_ix_transport/data/resin_parameters.json` - Resin data

## phreeqc_pse Package (GrayBox Integration - Future Use)
- `phreeqc_pse/__init__.py`
- `phreeqc_pse/core/phreeqc_block.py` - Base PHREEQC block
- `phreeqc_pse/core/phreeqc_gray_box.py` - GrayBox implementation
- `phreeqc_pse/core/phreeqc_io.py` - I/O utilities
- `phreeqc_pse/core/phreeqc_solver.py` - Solver interface
- `phreeqc_pse/core/phreeqc_state.py` - State management
- `phreeqc_pse/blocks/phreeqc_ix_block.py` - IX-specific block
- `phreeqc_pse/blocks/phreeqc_ix_block_simple.py` - Simplified IX block

## Supporting Files
- `requirements.txt` - Dependencies
- `CLAUDE.md` - Project instructions
- `README.md` - Project documentation
- `LICENSE` - License file
- `SETUP.md` - Setup instructions
- `PROJECT_STATUS_ONBOARDING.md` - Current status

## Configuration/Data
- `data/resin_parameters.json` - Resin parameters

## Test Files (Active)
- `test_mcp_workflow.py` - Main test suite

## Examples (Active)
- `examples/mcp_client_example.py` - MCP client example

## Documentation (Active)
- `docs/` - All documentation is referenced and used