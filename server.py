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
from typing import Dict, Any, Optional, List, Annotated
import time
from datetime import datetime

from fastmcp import FastMCP, Context
from pydantic import Field, BaseModel

# Import our utilities
# from tools.ix_configuration import optimize_ix_configuration  # COMMENTED OUT
# from tools.ix_simulation import simulate_ix_system, simulate_ix_system_graybox  # COMMENTED OUT
# from tools.ix_direct_phreeqc_simulation import IXDirectPhreeqcTool  # Replaced by SAC tools

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

# Configuration constants
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB max request size
REQUEST_TIMEOUT = 300  # 5 minutes timeout for long simulations

# Create FastMCP instance with configuration
mcp = FastMCP("IX Design Server")

# Register tools with enhanced metadata
# COMMENTED OUT - Replaced by SAC-only configuration
# @mcp.tool(
#     description="""Size ion exchange vessels for RO pretreatment.
#     
#     Returns hydraulic sizing for ALL THREE flowsheet alternatives:
#     - H-WAC → Degasser → Na-WAC (for mostly temporary hardness)
#     - SAC → Na-WAC → Degasser (for mixed hardness types)  
#     - Na-WAC → Degasser (for simple water chemistry)
#     
#     EXAMPLE INPUT:
#     {
#       "water_analysis": {
#         "flow_m3_hr": 100,
#         "ion_concentrations_mg_L": {
#           "Na_+": 838.9,
#           "Ca_2+": 80.06,
#           "Mg_2+": 24.29,
#           "Cl_-": 1435.0,
#           "HCO3_-": 121.95,
#           "SO4_2-": 240.0
#         },
#         "temperature_celsius": 25.0,
#         "pressure_bar": 4.0,
#         "pH": 7.0
#       },
#       "treatment_goals": ["remove_hardness", "remove_alkalinity"],
#       "max_vessels_per_train": 3,
#       "regenerant_type": "HCl",
#       "max_vessel_diameter_m": 2.4
#     }
#     
#     IMPORTANT: The 'water_analysis' field is REQUIRED and must contain:
#     - flow_m3_hr: Flow rate (required)
#     - ion_concentrations_mg_L: Dictionary of ion concentrations (required)
#     
#     Ion Format (MCAS notation with underscores):
#     - Cations: Na_+, Ca_2+, Mg_2+, K_+, H_+, NH4_+, Fe_2+, Fe_3+
#     - Anions: Cl_-, SO4_2-, HCO3_-, CO3_2-, NO3_-, PO4_3-, F_-, OH_-
#     - Neutrals: CO2, H2O, SiO2, B(OH)3"""
# )
# async def optimize_ix_configuration_wrapped(input_data: Dict[str, Any]) -> Dict[str, Any]:
#     """Wrapper to handle dict input/output for MCP tool."""
#     try:
#         from tools.schemas import IXConfigurationInput
#         
#         # Convert dict to pydantic model
#         ix_input = IXConfigurationInput(**input_data)
#         
#         # Call the multi-configuration function
#         result = optimize_ix_configuration(ix_input)
#         
#         # Convert result to dict using model_dump instead of deprecated dict()
#         return result.model_dump()
#         
#     except Exception as e:
#         # Provide helpful error message
#         if "water_analysis" in str(e):
#             return {
#                 "error": "Invalid input structure",
#                 "details": str(e),
#                 "hint": "The 'water_analysis' field must contain 'flow_m3_hr' and 'ion_concentrations_mg_L' as nested fields. See the tool description for the correct structure.",
#                 "example_structure": {
#                     "water_analysis": {
#                         "flow_m3_hr": 100,
#                         "ion_concentrations_mg_L": {
#                             "Na_+": 500,
#                             "Ca_2+": 120,
#                             "Cl_-": 800
#                         }
#                     }
#                 }
#             }
#         raise

# COMMENTED OUT - Replaced by Direct PHREEQC simulation
# @mcp.tool(
#     description="""Execute WaterTAP simulation for ion exchange system.
#     
#     Requires configuration from optimize_ix_configuration tool.
#     Returns:
#     - Detailed performance metrics and breakthrough curves
#     - Regenerant consumption and operating cycles
#     - Water quality progression through stages
#     - Complete economics (CAPEX, OPEX, LCOW)
#     - Verified capacity with Na+ competition effects
#     
#     Uses the full WaterTAP framework with:
#     - WaterTAP IonExchangeTransport0D unit models
#     - Integrated PHREEQC TRANSPORT engine for accurate breakthrough curves
#     - Proper WaterTAP costing functions (including degasser costing)
#     - Physics-based derating factors for real-world performance
#     
#     Water composition must use MCAS format (same as optimize tool).
#     
#     Derating Options (automatically applied):
#     - resin_age_years: Age of resin (affects capacity)
#     - fouling_potential: "low", "moderate", "high"  
#     - regeneration_level: "standard", "enhanced", "poor"
#     - distributor_quality: "excellent", "good", "fair", "poor"
#     
#     The model accounts for real-world effects including fouling, channeling,
#     competition, and incomplete regeneration. Typical industrial systems achieve
#     50-80% of theoretical capacity, which this model accurately predicts.
#     
#     Simulation Options:
#     - use_graybox: Set to true to use GrayBox model with automatic mass balance
#       enforcement. GrayBox provides:
#       * Automatic mass balance through Pyomo constraints
#       * Proper Jacobian calculation for optimization
#       * No manual variable updates required
#       * Follows Reaktoro-PSE integration pattern"""
# )
# async def simulate_ix_system_wrapped(input_data: Dict[str, Any]) -> Dict[str, Any]:
#     """Wrapper to handle dict input/output for MCP tool."""
#     from tools.schemas import IXSimulationInput
#     
#     # Convert dict to pydantic model
#     sim_input = IXSimulationInput(**input_data)
#     
#     # Check if GrayBox option is requested
#     use_graybox = input_data.get('simulation_options', {}).get('use_graybox', False)
#     
#     if use_graybox:
#         logger.info("Using GrayBox model for simulation")
#         result = simulate_ix_system_graybox(sim_input)
#     else:
#         # Call the standard function
#         result = simulate_ix_system(sim_input)
#     
#     # Convert result to dict using model_dump instead of deprecated dict()
#     return result.model_dump()

# Add SAC-only configuration tool
@mcp.tool(
    description="""Configure SAC ion exchange vessel for RO pretreatment.
    
    Sizes a single SAC vessel based on:
    - Service flow rate: 16 BV/hr (bed volumes per hour)
    - Linear velocity: 25 m/hr maximum
    - Minimum bed depth: 0.75 m
    - N+1 redundancy (1 service + 1 standby vessel)
    - Shipping container constraint: 2.4 m maximum diameter
    
    Input parameter: configuration_input (object with water_analysis and target_hardness_mg_l_caco3)
    
    Example:
    {
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
    
    Required fields:
    - water_analysis.flow_m3_hr: Feed water flow rate (m³/hr)
    - water_analysis.ca_mg_l: Calcium (mg/L)
    - water_analysis.mg_mg_l: Magnesium (mg/L)  
    - water_analysis.na_mg_l: Sodium (mg/L)
    - water_analysis.hco3_mg_l: Bicarbonate (mg/L)
    - water_analysis.pH: Feed water pH
    
    Optional fields:
    - water_analysis.cl_mg_l: Chloride (auto-balanced if not provided)
    - target_hardness_mg_l_caco3: Target effluent hardness (default 5.0)
    """
)
async def configure_sac_ix(configuration_input: Dict[str, Any]) -> Dict[str, Any]:
    """Configure SAC vessel with hydraulic sizing only."""
    import time
    start_time = time.time()
    logger.info(f"configure_sac_ix started at {start_time}")
    
    try:
        import json
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        # Handle both string and object inputs
        if isinstance(configuration_input, str):
            try:
                configuration_input = json.loads(configuration_input)
            except json.JSONDecodeError:
                return {
                    "error": "Invalid JSON input",
                    "details": "Input must be a valid JSON object or dict"
                }
        
        # Validate input size
        input_size = len(json.dumps(configuration_input))
        if input_size > MAX_REQUEST_SIZE:
            return {
                "error": "Request too large",
                "details": f"Request size {input_size} bytes exceeds maximum {MAX_REQUEST_SIZE} bytes",
                "hint": "Please reduce the size of your request"
            }
        
        from tools.sac_configuration import configure_sac_vessel, SACConfigurationInput
        
        # Convert dict to pydantic model
        sac_input = SACConfigurationInput(**configuration_input)
        
        # Log before calling the function
        logger.info("About to call configure_sac_vessel")
        
        # Run synchronous function in thread pool to avoid blocking event loop
        # Add timeout to prevent infinite hanging
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, configure_sac_vessel, sac_input),
                timeout=30.0  # 30 second timeout
            )
            logger.info("configure_sac_vessel returned")
        except asyncio.TimeoutError:
            logger.error("configure_sac_vessel timed out after 30 seconds")
            return {
                "error": "Configuration timeout",
                "details": "The configuration process took too long to complete",
                "hint": "Try again or check server logs"
            }
        
        # Convert result to dict
        output = result.model_dump()
        
        elapsed = time.time() - start_time
        logger.info(f"configure_sac_ix completed in {elapsed:.2f} seconds")
        return output
        
    except Exception as e:
        logger.error(f"SAC configuration failed: {e}")
        
        # Provide helpful error message with exact structure needed
        example_structure = {
            "configuration_input": {
                "water_analysis": {
                    "flow_m3_hr": 100,
                    "ca_mg_l": 80,
                    "mg_mg_l": 25,
                    "na_mg_l": 800,
                    "hco3_mg_l": 120,
                    "pH": 7.5
                },
                "target_hardness_mg_l_caco3": 5.0
            }
        }
        
        return {
            "error": "Configuration failed",
            "details": str(e),
            "hint": "All water parameters must be inside 'water_analysis' object",
            "example_structure": example_structure
        }

# Rename Direct PHREEQC simulation tool
@mcp.tool(
    description="""Simulate SAC ion exchange with Direct PHREEQC engine.
    
    Key Features:
    - Uses bed volume directly from configuration tool
    - PHREEQC determines actual operating capacity and competition
    - Dynamic breakthrough detection based on target hardness
    - Resolution-independent approach
    - Real PHREEQC results only (no mock data)
    
    Breakthrough Definition:
    - Simulation continues until effluent hardness exceeds target
    - Hardness = Ca × 2.5 + Mg × 4.1 (as CaCO3)
    - Reports bed volumes treated before target is exceeded
    - Automatically extends simulation if needed
    
    Input: JSON with configuration from configure_sac_ix tool
    
    Returns:
    - Breakthrough BV when target hardness is reached
    - Service time in hours
    - PHREEQC-determined capacity factor (not heuristic)
    - Breakthrough curve plot (saved as PNG)
    - Warnings if breakthrough not found
    """
)
async def simulate_sac_ix(simulation_input: str) -> Dict[str, Any]:
    """Wrapper for SAC PHREEQC simulation."""
    try:
        # Validate input size
        if len(simulation_input) > MAX_REQUEST_SIZE:
            return {
                "status": "error",
                "error": "Request too large",
                "details": f"Request size {len(simulation_input)} bytes exceeds maximum {MAX_REQUEST_SIZE} bytes"
            }
        
        import asyncio
        from tools.sac_simulation import simulate_sac_phreeqc, SACSimulationInput
        
        # Parse input JSON
        input_data = json.loads(simulation_input)
        
        # Convert to pydantic model
        sim_input = SACSimulationInput(**input_data)
        
        # Run simulation in thread pool to avoid blocking event loop
        # This is important as PHREEQC simulations can take several seconds
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, simulate_sac_phreeqc, sim_input)
        
        # Convert result to dict
        return result.model_dump()
        
    except Exception as e:
        logger.error(f"SAC simulation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "details": "SAC simulation failed. Check PHREEQC installation and input data."
        }

# Tools are already registered via decorators above

# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting Ion Exchange Design MCP Server...")
    logger.info("Designed for RO pretreatment in industrial wastewater ZLD applications")
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - configure_sac_ix: SAC vessel hydraulic sizing (no chemistry calculations)")
    logger.info("  - simulate_sac_ix: Direct PHREEQC simulation with target hardness breakthrough")
    
    # Log key features
    logger.info("\nKey Features:")
    logger.info("  - SAC-only system focused on RO pretreatment")
    logger.info("  - Direct PHREEQC engine for accurate breakthrough curves")
    logger.info("  - PHREEQC determines operating capacity and Na+ competition (no heuristics)")
    logger.info("  - Target hardness breakthrough definition (not 50%)")
    logger.info("  - All MCAS ions supported (Ca, Mg, Na, HCO3, pH required)")
    logger.info("  - Bed volume flows directly from configuration to simulation")
    logger.info("  - Dynamic simulation extension if breakthrough not found")
    logger.info("  - No silent failures - clear warnings and real results only")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()