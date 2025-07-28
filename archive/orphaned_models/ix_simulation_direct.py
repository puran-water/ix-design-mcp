"""
Direct Ion Exchange Simulation using WaterTAP Framework

This module routes all simulations through the WaterTAP framework
with integrated PHREEQC TRANSPORT engine for accurate calculations.
"""

import logging
import time
from typing import Dict, Any

from .schemas import (
    IXSimulationInput,
    IXSimulationOutput,
)

logger = logging.getLogger(__name__)


def simulate_ix_system_direct(input_data: IXSimulationInput) -> IXSimulationOutput:
    """
    Simulate ion exchange system using WaterTAP framework.
    
    ALL simulations now use the full WaterTAP framework with:
    - WaterTAP unit models (IonExchangeTransport0D)
    - Integrated PHREEQC TRANSPORT engine
    - Proper costing functions
    - Physics-based derating factors
    
    The previous direct PhreeqPy and simplified models have been deprecated
    in favor of the unified WaterTAP approach.
    
    Args:
        input_data: Simulation input parameters
        
    Returns:
        IXSimulationOutput with detailed performance metrics
    """
    start_time = time.time()
    
    # ALWAYS use WaterTAP framework with integrated PHREEQC TRANSPORT
    logger.info("Using WaterTAP framework with PHREEQC TRANSPORT engine")
    from .ix_simulation_watertap import simulate_ix_watertap
    
    # Ensure PHREEQC TRANSPORT is used within WaterTAP
    if "use_transport" not in input_data.simulation_options:
        input_data.simulation_options["use_transport"] = True
    
    # Pass through any model-specific options
    if "apply_derating" not in input_data.simulation_options:
        input_data.simulation_options["apply_derating"] = True
        
    try:
        result = simulate_ix_watertap(input_data)
        
        # Log execution time
        execution_time = time.time() - start_time
        logger.info(f"Simulation completed in {execution_time:.2f} seconds")
        
        # Update runtime in result
        result.actual_runtime_seconds = execution_time
        
        return result
        
    except Exception as e:
        logger.error(f"WaterTAP simulation failed: {str(e)}")
        # Return error result
        return IXSimulationOutput(
            status="error",
            error_message=str(e),
            watertap_notebook_path="",
            treated_water=input_data.water_analysis,
            configuration=input_data.configuration,
            ix_performance={},
            water_quality_progression=[],
            degasser_performance={},
            actual_runtime_seconds=time.time() - start_time
        )