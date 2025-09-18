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
    # Debug: Log that .env was loaded
    if os.path.exists('.env'):
        print(f"Loaded .env file from {os.path.abspath('.env')}", file=sys.stderr)
except ImportError:
    # dotenv not installed, continue without it
    print("python-dotenv not installed, skipping .env loading", file=sys.stderr)
    pass

# Ensure project root is on sys.path so our local `utils` package wins over any
# site-packages modules with the same name.
def _resolve_project_root() -> Path:
    """Resolve the project root using environment override when valid."""
    env_root = os.environ.get("IX_DESIGN_MCP_ROOT")
    if env_root:
        candidate = Path(env_root)
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent


PROJECT_ROOT = _resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
from concurrent.futures import ThreadPoolExecutor

from fastmcp import FastMCP, Context
from pydantic import Field, BaseModel

# Import our utilities
# from tools.ix_configuration import optimize_ix_configuration  # COMMENTED OUT
# from tools.ix_simulation import simulate_ix_system, simulate_ix_system_graybox  # COMMENTED OUT
# from tools.ix_direct_phreeqc_simulation import IXDirectPhreeqcTool  # Replaced by SAC tools

# Configure logging for MCP - CRITICAL for protocol integrity
# Use a file handler for detailed logs and a stderr handler for warnings/errors only
file_handler = logging.FileHandler('ix_design_mcp.log')
file_handler.setLevel(logging.INFO)

stderr_handler = logging.StreamHandler(sys.stderr)
# Avoid flooding MCP stderr pipe to prevent blocking/hangs
stderr_handler.setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[file_handler, stderr_handler]
)
logger = logging.getLogger(__name__)

# Debug: Log PHREEQC_EXE environment variable
phreeqc_exe = os.environ.get('PHREEQC_EXE', 'NOT SET')
logger.info(f"PHREEQC_EXE environment variable: {phreeqc_exe}")
if phreeqc_exe != 'NOT SET' and os.path.exists(phreeqc_exe):
    logger.info(f"PHREEQC executable found at: {phreeqc_exe}")
else:
    logger.warning(f"PHREEQC executable not found at: {phreeqc_exe}")

# Import SAC tools at module level to prevent hanging on first call
logger.info("Starting imports of SAC tools...")
import_start = time.time()

from tools.sac_configuration import configure_sac_vessel, SACConfigurationInput
logger.info(f"Imported sac_configuration in {time.time() - import_start:.2f}s")

from tools.sac_simulation import simulate_sac_phreeqc, SACSimulationInput
logger.info(f"Imported sac_simulation in {time.time() - import_start:.2f}s total")

# Import WAC tools
from tools.wac_configuration import configure_wac_vessel, WACConfigurationInput
logger.info(f"Imported wac_configuration in {time.time() - import_start:.2f}s total")

from tools.wac_simulation import simulate_wac_system, WACSimulationInput
logger.info(f"Imported wac_simulation in {time.time() - import_start:.2f}s total")

logger.info(f"All IX tools imported in {time.time() - import_start:.2f}s total")

# Import notebook runner for integrated analysis
try:
    from tools.notebook_runner import run_sac_notebook_analysis_impl
    logger.info("Notebook runner imported successfully")
    NOTEBOOK_RUNNER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Notebook runner not available: {e}")
    logger.warning("Install papermill and nbconvert for notebook-based analysis")
    NOTEBOOK_RUNNER_AVAILABLE = False

# Configuration constants
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB max request size
REQUEST_TIMEOUT = 300  # 5 minutes timeout for long simulations

# Dedicated executor for hybrid tasks to avoid starvation in default pool
try:
    HYBRID_EXECUTOR_WORKERS = int(os.environ.get('MCP_HYBRID_EXECUTOR_WORKERS', '2'))
except Exception:
    HYBRID_EXECUTOR_WORKERS = 2
HYBRID_EXECUTOR = ThreadPoolExecutor(max_workers=HYBRID_EXECUTOR_WORKERS, thread_name_prefix="hybrid")

# Create FastMCP instance with configuration
mcp = FastMCP("IX Design Server")


def get_project_root() -> Path:
    """
    Determine project root with multiple fallback strategies.
    
    Returns absolute path to project root directory.
    """
    # Strategy 1: Environment variable (most reliable for MCP clients)
    if 'IX_DESIGN_MCP_ROOT' in os.environ:
        root = Path(os.environ['IX_DESIGN_MCP_ROOT'])
        if root.exists():
            logger.info(f"Using project root from IX_DESIGN_MCP_ROOT: {root}")
            return root
        else:
            logger.warning(f"IX_DESIGN_MCP_ROOT points to non-existent path: {root}")
    
    # Strategy 2: Relative to this file (fallback)
    # Use resolve() to get absolute path first
    root = Path(__file__).resolve().parent
    logger.info(f"Using project root relative to server.py: {root}")
    return root


def validate_paths():
    """Validate critical paths exist at startup."""
    root = get_project_root()
    required_paths = [
        root / "notebooks",
        root / "databases",
        root / "tools"
    ]
    
    missing_paths = []
    for path in required_paths:
        if not path.exists():
            missing_paths.append(str(path))
            logger.error(f"Required path not found: {path}")
    
    if missing_paths:
        logger.error(f"Project root: {root}")
        logger.error("Set IX_DESIGN_MCP_ROOT environment variable to the project directory")
        logger.error("Example: export IX_DESIGN_MCP_ROOT=/path/to/ix-design-mcp")
        raise FileNotFoundError(f"Required paths not found: {', '.join(missing_paths)}")
    
    logger.info("All required paths validated successfully")


def ensure_simulation_input_complete(input_data: Dict[str, Any], resin_type: str) -> Dict[str, Any]:
    """
    Ensure simulation input has all required fields.
    Fills in missing fields with appropriate defaults.
    
    Args:
        input_data: Partial simulation input data
        resin_type: Type of resin (SAC, WAC_Na, WAC_H)
    
    Returns:
        Complete simulation input data
    """
    # Ensure vessel_configuration has all required fields
    if 'vessel_configuration' in input_data:
        vessel_config = input_data['vessel_configuration']
        
        # Add bed_expansion_percent if missing (common issue)
        if 'bed_expansion_percent' not in vessel_config:
            if resin_type == 'WAC_Na':
                vessel_config['bed_expansion_percent'] = 50.0  # Na-form WAC default
            elif resin_type == 'WAC_H':
                vessel_config['bed_expansion_percent'] = 100.0  # H-form WAC default
            else:
                vessel_config['bed_expansion_percent'] = 50.0  # SAC default
            logger.info(f"Added missing bed_expansion_percent: {vessel_config['bed_expansion_percent']}%")
        
        # Ensure resin_type is set in vessel_configuration
        if 'resin_type' not in vessel_config:
            vessel_config['resin_type'] = resin_type
            logger.info(f"Added missing resin_type: {resin_type}")
        
        # Add number_service if missing
        if 'number_service' not in vessel_config:
            vessel_config['number_service'] = 1
            logger.info("Added missing number_service: 1")
        
        # Add number_standby if missing
        if 'number_standby' not in vessel_config:
            vessel_config['number_standby'] = 1
            logger.info("Added missing number_standby: 1")
        
        # Calculate resin_volume_m3 from bed_volume_L if missing
        if 'resin_volume_m3' not in vessel_config:
            if 'bed_volume_L' in vessel_config:
                vessel_config['resin_volume_m3'] = vessel_config['bed_volume_L'] / 1000.0
                logger.info(f"Calculated resin_volume_m3: {vessel_config['resin_volume_m3']:.2f} m3")
            else:
                # Calculate from diameter and bed depth if available
                if 'diameter_m' in vessel_config and 'bed_depth_m' in vessel_config:
                    import math
                    area = math.pi * (vessel_config['diameter_m'] / 2) ** 2
                    volume_m3 = area * vessel_config['bed_depth_m']
                    vessel_config['resin_volume_m3'] = volume_m3
                    vessel_config['bed_volume_L'] = volume_m3 * 1000
                    logger.info(f"Calculated resin_volume_m3: {volume_m3:.2f} m3")
        
        # Calculate freeboard_m if missing
        if 'freeboard_m' not in vessel_config:
            bed_depth = vessel_config.get('bed_depth_m', 1.5)
            expansion_percent = vessel_config.get('bed_expansion_percent', 50.0)
            # Freeboard = bed_depth * expansion_percent / 100 + 0.3m safety
            vessel_config['freeboard_m'] = bed_depth * expansion_percent / 100 + 0.3
            logger.info(f"Calculated freeboard_m: {vessel_config['freeboard_m']:.2f} m")
        
        # Calculate vessel_height_m if missing
        if 'vessel_height_m' not in vessel_config:
            bed_depth = vessel_config.get('bed_depth_m', 1.5)
            freeboard = vessel_config.get('freeboard_m', 1.5)
            # Add 0.3m for bottom support and 0.3m for top distributor
            vessel_config['vessel_height_m'] = bed_depth + freeboard + 0.61
            logger.info(f"Calculated vessel_height_m: {vessel_config['vessel_height_m']:.2f} m")
    
    # Ensure regeneration_config exists with defaults
    if 'regeneration_config' not in input_data or not input_data['regeneration_config']:
        # Load defaults from resin parameters
        project_root = get_project_root()
        db_path = project_root / "databases" / "resin_parameters.json"
        try:
            with open(db_path, 'r') as f:
                resin_db = json.load(f)

            resin_types = resin_db.get('resin_types', {})
            resin_entry = resin_types.get(resin_type)

            if resin_entry:
                regen_params = resin_entry.get('regeneration', {})
                if resin_type == 'SAC':
                    input_data['regeneration_config'] = {
                        'enabled': True,
                        'regenerant_type': 'NaCl',
                        'concentration_percent': 10,
                        'regenerant_dose_g_per_L': 100,
                        'mode': 'staged_fixed',  # Use fixed mode for speed
                        'regeneration_stages': 5,
                        'flow_direction': 'back',
                        'backwash_enabled': True,
                        'target_recovery': 0.90
                    }
                elif resin_type in ['WAC_Na', 'WAC_H']:
                    input_data['regeneration_config'] = {
                        'enabled': True,
                        'regenerant_type': 'HCl',
                        'concentration_percent': 5,
                        'regenerant_dose_g_per_L': regen_params.get('total_regenerant_dose_g_L', 100),
                        'mode': 'staged_fixed',
                        'regeneration_stages': len(regen_params.get('steps', [])) or 2,
                        'flow_direction': 'back',
                        'backwash_enabled': False  # WAC typically doesn't backwash
                    }
                logger.info(f"Added default regeneration_config for {resin_type}")
        except Exception as e:
            logger.warning(f"Could not load default regeneration config: {e}")
            # Use minimal defaults
            input_data['regeneration_config'] = {
                'enabled': True,
                'regenerant_type': 'NaCl' if resin_type == 'SAC' else 'HCl',
                'concentration_percent': 10 if resin_type == 'SAC' else 5,
                'regenerant_dose_g_per_L': 100,
                'mode': 'staged_fixed',
                'regeneration_stages': 5,
                'flow_direction': 'back',
                'backwash_enabled': resin_type == 'SAC'
            }
    
    return input_data


# Register tools with enhanced metadata
# COMMENTED OUT - Replaced by SAC-only configuration
# @mcp.tool(
#     description="""Size ion exchange vessels for RO pretreatment.
#     
#     Returns hydraulic sizing for ALL THREE flowsheet alternatives:
#     - H-WAC -> Degasser -> Na-WAC (for mostly temporary hardness)
#     - SAC -> Na-WAC -> Degasser (for mixed hardness types)  
#     - Na-WAC -> Degasser (for simple water chemistry)
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
    - water_analysis.flow_m3_hr: Feed water flow rate (m3/hr)
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

# DEPRECATED: Use simulate_ix_watertap instead
# This tool is kept for backward compatibility but is no longer exposed via MCP
# @mcp.tool(
#     description="""Simulate complete SAC ion exchange cycle (service + regeneration).
#     
#     Required input structure:
#     {
#         "water_analysis": {...},
#         "vessel_configuration": {...},
#         "target_hardness_mg_l_caco3": 5.0,
#         "regeneration_config": {
#             "regenerant_type": "NaCl",  // Default, HCl/H2SO4 also supported
#             "concentration_percent": 10,  // Default 10%
#             "regenerant_dose_g_per_L": 100,  // Regenerant dose in g/L resin (industry standard)
#             "mode": "staged_optimize",  // Default - finds optimal regenerant dose
#             "target_recovery": 0.90,  // Default 90% (achievable)
#             "regeneration_stages": 5,  // Default 5 stages
#             "flow_rate_bv_hr": 2.5,  // Default 2.5 BV/hr
#             "flow_direction": "back",  // Counter-current (default)
#             "backwash_enabled": true  // Default true
#         }
#     }
#     
#     Regenerant Dose Guidelines:
#     - NaCl: 80-120 g/L (standard), 150-200 g/L (high TDS water), up to 1000 g/L (extreme)
#     - HCl: 60-80 g/L (standard)
#     - H2SO4: 80-100 g/L (standard)
#     The system automatically calculates bed volumes from dose and concentration.
#     
#     Simulates complete industrial cycle:
#     1. Service run to breakthrough
#     2. Backwash (optional) - bed expansion and fines removal
#     3. Regeneration with auto-stop at target recovery
#     4. Slow rinse (displacement)
#     5. Fast rinse (quality polish)
#     
#     Key Features:
#     - PHREEQC determines actual operating capacity and competition
#     - Dynamic breakthrough detection based on target hardness
#     - Counter-current regeneration support
#     - Automatic regenerant dosing based on recovery
#     - Full waste stream characterization
#     
#     Returns complete cycle results:
#     - Service phase:
#       - Breakthrough BV when target hardness is reached
#       - Service time in hours  
#       - PHREEQC-determined capacity factor
#       - Breakthrough curve data
#     - Regeneration phase:
#       - Actual regenerant consumption (kg)
#       - Peak waste TDS and hardness
#       - Total hardness removed (kg)
#       - Waste volume (m3)
#       - Final resin recovery (%)
#     - Total cycle time (hours)
#     - Multi-phase breakthrough data for complete cycle visualization
#     """
# )
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
        
        # Parse input JSON
        input_data = json.loads(simulation_input)
        
        # Ensure all required fields are present
        input_data = ensure_simulation_input_complete(input_data, 'SAC')
        
        # Convert to pydantic model
        sim_input = SACSimulationInput(**input_data)
        
        # Run simulation in thread pool to avoid blocking event loop
        # This is important as PHREEQC simulations can take several seconds
        loop = asyncio.get_event_loop()
        
        try:
            # Set timeout to be less than typical MCP client timeout
            # Client usually times out at ~120s, so we timeout at 100s
            timeout_seconds = int(os.environ.get('MCP_SIMULATION_TIMEOUT_S', '600'))  # 10 minutes
            logger.info(f"SAC simulation starting with timeout: {timeout_seconds} seconds")
            
            result = await asyncio.wait_for(
                loop.run_in_executor(None, simulate_sac_phreeqc, sim_input),
                timeout=timeout_seconds
            )
            return result.model_dump()
        except asyncio.TimeoutError:
            # Don't run another simulation - return timeout error
            logger.warning(f"SAC simulation timed out after {timeout_seconds} seconds")
            
            # Return structured timeout response
            return {
                "status": "timeout",
                "error": "Simulation timeout",
                "details": (
                    f"The simulation exceeded the {timeout_seconds} second timeout. "
                    f"This typically happens with complex water chemistry or when optimization is enabled. "
                    f"Consider: (1) Using fixed regeneration mode instead of optimization, "
                    f"(2) Reducing the number of simulation cells, or "
                    f"(3) Simplifying the water chemistry."
                ),
                "suggestions": {
                    "use_fixed_mode": {
                        "regeneration_config": {
                            "mode": "staged_fixed",
                            "regenerant_bv": 3.5,
                            "regeneration_stages": 5
                        }
                    },
                    "reduce_complexity": "Try reducing cells or simplifying water chemistry"
                },
                "timeout_seconds": timeout_seconds
            }
        
    except Exception as e:
        logger.error(f"SAC simulation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "details": "SAC simulation failed. Check PHREEQC installation and input data."
        }

# Add notebook-based analysis tool if available
# Add WAC configuration tool
@mcp.tool(
    description="""Configure WAC ion exchange vessel for RO pretreatment.
    
    Sizes WAC vessels based on:
    - Service flow rate: 16 BV/hr (bed volumes per hour)
    - Linear velocity: 25 m/hr maximum
    - Minimum bed depth: 0.75 m
    - N+1 redundancy (1 service + 1 standby vessel)
    - Bed expansion during regeneration (50% Na-form, 100% H-form)
    
    Input parameters:
    {
      "water_analysis": {
        "flow_m3_hr": 100,
        "ca_mg_l": 80.06,
        "mg_mg_l": 24.29,
        "na_mg_l": 838.9,
        "hco3_mg_l": 121.95,  // Required for WAC
        "pH": 7.8,
        "cl_mg_l": 1435
      },
      "resin_type": "WAC_Na",  // or "WAC_H"
      "target_hardness_mg_l_caco3": 5.0,
      "target_alkalinity_mg_l_caco3": 5.0  // For H-form
    }
    
    Key differences from SAC:
    - resin_type parameter selects WAC_Na or WAC_H
    - Alkalinity (hco3_mg_l) is critical for WAC performance
    - H-form removes alkalinity and generates CO2
    - Na-form uses two-step regeneration
    - Higher capacity but pH-dependent
    
    Returns vessel configuration with:
    - Hydraulic sizing
    - Regeneration sequence
    - Water chemistry analysis
    - Design notes and warnings
    """
)
async def configure_wac_ix(configuration_input: Dict[str, Any]) -> Dict[str, Any]:
    """Configure WAC vessel with hydraulic sizing."""
    import time
    start_time = time.time()
    logger.info(f"configure_wac_ix started at {start_time}")
    
    try:
        import json
        import asyncio
        
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
                "details": f"Request size {input_size} bytes exceeds maximum {MAX_REQUEST_SIZE} bytes"
            }
        
        # Convert dict to pydantic model
        wac_input = WACConfigurationInput(**configuration_input)
        
        # Log before calling the function
        logger.info(f"Configuring WAC {wac_input.resin_type} vessel")
        
        # Run synchronous function in thread pool
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, configure_wac_vessel, wac_input),
                timeout=30.0
            )
            logger.info("configure_wac_vessel returned")
        except asyncio.TimeoutError:
            logger.error("configure_wac_vessel timed out after 30 seconds")
            return {
                "error": "Configuration timeout",
                "details": "The configuration process took too long to complete"
            }
        
        # Convert result to dict
        output = result.model_dump()
        
        elapsed = time.time() - start_time
        logger.info(f"configure_wac_ix completed in {elapsed:.2f} seconds")
        return output
        
    except Exception as e:
        logger.error(f"WAC configuration failed: {e}")
        return {
            "error": "Configuration failed",
            "details": str(e),
            "hint": "Check resin_type (WAC_Na or WAC_H) and water_analysis parameters"
        }

if NOTEBOOK_RUNNER_AVAILABLE:
    @mcp.tool(
        description="""Generate professional IX report from simulation artifacts.

        Creates HTML report with:
        - Basis of design tables
        - Hydraulic sizing calculations (rendered with handcalcs)
        - Breakthrough curve visualizations
        - Mass balance and regeneration details
        - Economic analysis (if available)
        - Conclusions and recommendations

        Input format:
        {
            "run_id": "20250918_122820_94b183ba"  # From any IX simulation
        }

        The report automatically adapts to resin type (SAC, WAC_Na, WAC_H).
        Works with artifacts from simulate_ix_watertap or any other IX simulation tool.

        Returns:
        - Paths to generated notebook and HTML report
        - Report metadata (resin type, timestamp, etc.)
        """
    )
    async def generate_ix_report(report_input: str) -> Dict[str, Any]:
        """Generate professional IX report from simulation artifacts."""
        try:
            from tools.ix_report_generator import generate_ix_report as gen_report

            # Parse input
            input_data = json.loads(report_input)

            if 'run_id' not in input_data:
                return {
                    "status": "error",
                    "error": "Missing required field: run_id",
                    "details": "Provide the run_id from a completed IX simulation"
                }

            # Generate report from artifacts
            return await gen_report(run_id=input_data['run_id'])

        except ImportError as e:
            return {
                "status": "error",
                "error": "Report generator not available",
                "details": f"Install required packages: {e}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "details": "Failed to generate IX report"
            }

# DEPRECATED: Use simulate_ix_watertap instead
# This tool is kept for backward compatibility but is no longer exposed via MCP
# @mcp.tool(
#     description="""Simulate complete WAC ion exchange cycle (service + regeneration).
#     
#     Required input structure:
#     {
#         "water_analysis": {...},
#         "vessel_configuration": {...},
#         "resin_type": "WAC_Na" or "WAC_H",
#         "target_hardness_mg_l_caco3": 5.0,
#         "target_alkalinity_mg_l_caco3": 5.0,  // For H-form
#         "regeneration_config": {
#             // Auto-populated based on resin type
#         }
#     }
#     
#     Key differences from SAC simulation:
#     - WAC_Na: Uses two-step regeneration (acid -> water -> caustic -> water)
#     - WAC_H: Single-step acid regeneration with high efficiency
#     - H-form tracks alkalinity breakthrough and CO2 generation
#     - Both forms have pH-dependent capacity
#     
#     Breakthrough criteria:
#     - Na-form: Hardness breakthrough (same as SAC)
#     - H-form: Alkalinity breakthrough OR active sites < 10%
#     
#     Key Features:
#     - PHREEQC determines pH-dependent capacity
#     - Tracks alkalinity, pH, and CO2 throughout service
#     - Counter-current regeneration modeling
#     - Active site utilization for H-form
#     - Temporary vs permanent hardness removal metrics
#     
#     Returns complete cycle results:
#     - Service phase:
#       - Breakthrough BV based on resin-specific criteria
#       - Alkalinity and pH profiles
#       - CO2 generation (H-form)
#       - Active site utilization (H-form)
#     - Regeneration phase:
#       - Chemical consumption by step
#       - Efficiency metrics
#       - Waste characterization
#     - Performance metrics specific to WAC chemistry
#     
#     Note: H-form WAC typically requires downstream decarbonation
#     """
# )
async def simulate_wac_ix(simulation_input: str) -> Dict[str, Any]:
    """Wrapper for WAC PHREEQC simulation."""
    try:
        # Validate input size
        if len(simulation_input) > MAX_REQUEST_SIZE:
            return {
                "status": "error",
                "error": "Request too large",
                "details": f"Request size {len(simulation_input)} bytes exceeds maximum {MAX_REQUEST_SIZE} bytes"
            }
        
        import asyncio
        
        # Parse input JSON
        input_data = json.loads(simulation_input)
        
        # Get resin type - check top level first, then vessel_configuration
        resin_type = input_data.get('resin_type')
        if not resin_type:
            resin_type = input_data.get('vessel_configuration', {}).get('resin_type', 'WAC_Na')
        
        # Ensure all required fields are present
        input_data = ensure_simulation_input_complete(input_data, resin_type)
        
        # Convert to pydantic model
        sim_input = WACSimulationInput(**input_data)
        
        # Run simulation in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, simulate_wac_system, sim_input)
        
        # Convert result to dict
        return result.model_dump()
        
    except Exception as e:
        logger.error(f"WAC simulation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "details": "WAC simulation failed. Check input data and resin type."
        }

# Add hybrid simulation tool
@mcp.tool(
    description="""Run hybrid IX simulation with PHREEQC chemistry and WaterTAP costing.
    
    This tool provides the best of both worlds:
    - PHREEQC for accurate multi-ion chemistry and competition
    - WaterTAP for flowsheet structure and industrial economics
    
    Input structure follows unified schema:
    {
        "schema_version": "1.0.0",
        "resin_type": "SAC" | "WAC_Na" | "WAC_H",
        "water": {
            "flow_m3h": 100,
            "temperature_c": 25,
            "ions_mg_l": {"Ca_2+": 120, "Mg_2+": 40, ...}
        },
        "vessel": {
            "diameter_m": 2.0,
            "bed_depth_m": 2.5,
            "number_in_service": 1
        },
        "targets": {
            "hardness_mg_l_caco3": 5.0
        },
        "cycle": {
            "regenerant_type": "NaCl",
            "regenerant_dose_g_per_l": 100
        },
        "pricing": {
            "electricity_usd_kwh": 0.07,
            "nacl_usd_kg": 0.12,
            "resin_usd_m3": 2800
        },
        "engine": "watertap_hybrid"  // Optional, defaults to hybrid
    }
    
    Key features:
    - Unified results schema across all engines
    - Complete economic analysis (CAPEX, OPEX, LCOW)
    - Artifact writing to results/ directory
    - Detailed ion tracking and mass balance
    - Handles multi-component hardness accurately
    
    Returns:
    - Comprehensive results with performance, economics, and artifacts
    - Compatible with downstream analysis tools
    - Results written to results/ix_simulation_*.json
    """
)
async def simulate_ix_watertap(simulation_input: str) -> Dict[str, Any]:
    """Execute hybrid PHREEQC + WaterTAP simulation."""
    try:
        # Validate input size
        if len(simulation_input) > MAX_REQUEST_SIZE:
            return {
                "status": "error",
                "error": "Request too large",
                "details": f"Request size exceeds maximum {MAX_REQUEST_SIZE} bytes"
            }
        
        import asyncio
        import json
        from tools.simulate_ix_hybrid import simulate_ix_hybrid
        
        # Parse input
        input_data = json.loads(simulation_input)
        
        # Set engine to hybrid if not specified
        if "engine" not in input_data:
            input_data["engine"] = "watertap_hybrid"
        
        # Control artifact writing via env to test WSL file I/O impact
        write_artifacts_env = os.environ.get('MCP_WRITE_ARTIFACTS', '1').lower()
        write_artifacts = write_artifacts_env not in ('0', 'false', 'no')

        # Run hybrid simulation in thread pool
        loop = asyncio.get_event_loop()
        timeout_seconds = int(os.environ.get('MCP_SIMULATION_TIMEOUT_S', '600'))  # 10 minutes
        logger.info(f"Hybrid IX simulation starting with timeout: {timeout_seconds} seconds (engine: {input_data.get('engine', 'watertap_hybrid')})")
        
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(HYBRID_EXECUTOR, simulate_ix_hybrid, input_data, write_artifacts),
                timeout=timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "error": "Hybrid simulation timeout",
                "details": f"Simulation exceeded {timeout_seconds} second timeout",
                "suggestions": "Consider simplifying water chemistry or using PHREEQC-only mode"
            }
        
    except Exception as e:
        logger.error(f"Hybrid simulation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "details": "Hybrid simulation failed. Check WaterTAP installation."
        }

# Tools are already registered via decorators above

# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting Ion Exchange Design MCP Server...")
    logger.info("Designed for RO pretreatment in industrial wastewater ZLD applications")
    
    # Validate paths before continuing
    try:
        validate_paths()
    except FileNotFoundError as e:
        logger.error(f"Path validation failed: {e}")
        sys.exit(1)
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - configure_sac_ix: SAC vessel hydraulic sizing")
    logger.info("  - configure_wac_ix: WAC vessel hydraulic sizing (Na-form or H-form)")
    logger.info("  - simulate_ix_watertap: Unified simulation with PHREEQC chemistry + WaterTAP costing")
    if NOTEBOOK_RUNNER_AVAILABLE:
        logger.info("  - run_sac_notebook_analysis: Integrated analysis with Jupyter notebook (optional)")
    
    # Log timeout configuration
    phreeqc_timeout = int(os.environ.get('PHREEQC_RUN_TIMEOUT_S', '600'))
    mcp_timeout = int(os.environ.get('MCP_SIMULATION_TIMEOUT_S', '600'))
    logger.info(f"\nTimeout Configuration:")
    logger.info(f"  - PHREEQC subprocess timeout: {phreeqc_timeout} seconds")
    logger.info(f"  - MCP simulation timeout: {mcp_timeout} seconds")
    
    # Log key features
    logger.info("\nKey Features:")
    logger.info("  - Multi-engine support: PHREEQC for chemistry, WaterTAP for costing")
    logger.info("  - Direct PHREEQC engine for accurate breakthrough curves")
    logger.info("  - WaterTAP integration for flowsheet structure and economic analysis")
    logger.info("  - Unified schema across all simulation engines")
    logger.info("  - Artifact system with JSON results written to results/ directory")
    logger.info("  - Target hardness breakthrough definition (not 50%)")
    logger.info("  - All MCAS ions supported (Ca, Mg, Na, HCO3, pH required)")
    logger.info("  - Bed volume flows directly from configuration to simulation")
    logger.info("  - Dynamic simulation extension if breakthrough not found")
    logger.info("  - No silent failures - clear warnings and real results only")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()
