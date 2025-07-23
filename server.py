#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ion Exchange Design MCP Server

An STDIO MCP server for ion exchange system design optimization.
Provides tools for vessel configuration and WaterTAP simulation with PhreeqPy.
Designed for RO pretreatment in industrial wastewater ZLD applications.
"""

import os
import sys
from pathlib import Path

# Load environment variables before any other imports
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, continue without it
    pass

# Set required environment variables
if 'LOCALAPPDATA' not in os.environ:
    if sys.platform == 'win32':
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    else:
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), '.local')

# Set Jupyter platform dirs to avoid deprecation warning
if 'JUPYTER_PLATFORM_DIRS' not in os.environ:
    os.environ['JUPYTER_PLATFORM_DIRS'] = '1'

# Now do the rest of the imports
import json
import logging
from typing import Dict, Any, Optional, List
import time
from datetime import datetime

from fastmcp import FastMCP, Context

# Import our utilities
from tools.ix_configuration import optimize_ix_configuration, optimize_ix_configuration_all
from tools.ix_simulation import simulate_ix_system

# Configure logging for MCP - CRITICAL for protocol integrity
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ix_design_mcp.log'),
        logging.StreamHandler(sys.stderr)  # MCP requires stdout to be clean
    ]
)
logger = logging.getLogger(__name__)

# Create FastMCP instance
mcp = FastMCP("IX Design Server")

# Register tools with enhanced metadata
@mcp.tool(
    description="""Optimize ion exchange system configuration for RO pretreatment.
    
    Returns ALL THREE flowsheet alternatives with sizing, allowing selection based on:
    - Lowest CAPEX
    - Lowest operating cost  
    - Best hardness removal
    - Simplest operation
    
    IMPORTANT - Water Composition Format:
    - Use MCAS notation for ALL ions (underscore format)
    - Cations: Na_+, Ca_2+, Mg_2+, K_+, H_+, NH4_+, Fe_2+, Fe_3+
    - Anions: Cl_-, SO4_2-, HCO3_-, CO3_2-, NO3_-, PO4_3-, F_-, OH_-
    - Neutrals: CO2, H2O, SiO2, B(OH)3
    
    Example: {"Na_+": 500, "Ca_2+": 120, "Mg_2+": 48, "Cl_-": 800, "SO4_2-": 240, "HCO3_-": 180, "SiO2": 25}
    
    Note: Non-standard ions will generate warnings but won't fail. They're ignored for IX but passed through."""
)
async def optimize_ix_configuration_wrapped(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper to handle dict input/output for MCP tool."""
    from tools.schemas import IXConfigurationInput
    
    # Convert dict to pydantic model
    ix_input = IXConfigurationInput(**input_data)
    
    # Call the new multi-configuration function
    result = optimize_ix_configuration_all(ix_input)
    
    # Convert result to dict
    return result.dict()

@mcp.tool(
    description="""Execute WaterTAP/PhreeqPy simulation for ion exchange system.
    
    Requires configuration from optimize_ix_configuration tool.
    Returns detailed performance metrics, breakthrough curves, and economics.
    
    Water composition must use MCAS format (same as optimize tool).
    
    Model Options:
    - model_type: "direct" (default), "transport", or "watertap"
      - "direct": PhreeqPy equilibrium model
      - "transport": PHREEQC TRANSPORT model with dispersion and kinetics
      - "watertap": Full WaterTAP framework with derating factors
    - apply_derating: true/false (for watertap model)
    - resin_age_years, fouling_potential, etc. (derating parameters)
    
    Note: Model predicts theoretical performance. Industrial systems typically achieve
    10-20% of theoretical capacity due to fouling, channeling, and competing species.
    The WaterTAP model includes derating factors to account for these real-world effects."""
)
async def simulate_ix_system_wrapped(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper to handle dict input/output for MCP tool."""
    from tools.schemas import IXSimulationInput
    
    # Convert dict to pydantic model
    sim_input = IXSimulationInput(**input_data)
    
    # Call the actual function
    result = simulate_ix_system(sim_input)
    
    # Convert result to dict
    return result.dict()

# Tools are already registered via decorators above

# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting Ion Exchange Design MCP Server...")
    logger.info("Designed for RO pretreatment in industrial wastewater ZLD applications")
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - optimize_ix_configuration: Hydraulic sizing and flowsheet selection with Na+ competition awareness")
    logger.info("  - simulate_ix_system: WaterTAP/PhreeqPy simulation for breakthrough and regeneration analysis")
    
    # Log key features
    logger.info("\nKey Features:")
    logger.info("  - MCAS-compatible water quality inputs/outputs for seamless RO integration")
    logger.info("  - Multi-component ion exchange modeling with Na+ competition effects")
    logger.info("  - Automatic flowsheet selection based on water chemistry")
    logger.info("  - WaterTAP framework integration for economic analysis")
    logger.info("  - Degasser sizing for CO2 stripping")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()