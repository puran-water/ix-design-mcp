"""
Notebook Runner Tool - Redirect to Generic IX Report Generator

This module is maintained for import compatibility but redirects
all functionality to the new generic IX report generator.
"""

import logging
from typing import Dict, Any

# Import the new generic report generator
from .ix_report_generator import generate_ix_report

logger = logging.getLogger(__name__)


async def run_sac_notebook_analysis_impl(analysis_input: str) -> Dict[str, Any]:
    """
    Legacy SAC notebook analysis - now redirects to generic report generator.

    Args:
        analysis_input: JSON string with simulation results

    Returns:
        Report generation status and paths
    """
    import json

    try:
        # Parse input
        if isinstance(analysis_input, str):
            params = json.loads(analysis_input)
        else:
            params = analysis_input

        # Extract simulation results if nested
        if 'simulation_result' in params:
            simulation_result = params['simulation_result']
        else:
            # Assume the entire input is the simulation result
            simulation_result = params

        # Ensure resin_type is set for SAC
        if 'resin_type' not in simulation_result:
            simulation_result['resin_type'] = 'SAC'

        # Extract design inputs if present
        design_inputs = params.get('water_analysis', {})

        # Call the generic report generator
        result = await generate_ix_report(
            simulation_result=simulation_result,
            design_inputs=design_inputs
        )

        # Map new response format to legacy format if needed
        if result['status'] == 'success':
            # Add any legacy fields expected by old callers
            result['breakthrough_bv'] = simulation_result.get('performance', {}).get('service_bv_to_target')
            result['service_time_hours'] = simulation_result.get('performance', {}).get('service_hours')

        return result

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'details': 'Failed to generate IX report'
        }


# Re-export the generic function for direct use
generate_ix_report_async = generate_ix_report


def run_ix_report_analysis(simulation_result: Dict[str, Any],
                          design_inputs: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Synchronous wrapper for IX report generation.

    Args:
        simulation_result: IXSimulationResult as dict
        design_inputs: Original design configuration

    Returns:
        Report generation status and paths
    """
    import asyncio

    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            generate_ix_report(simulation_result, design_inputs)
        )
    finally:
        loop.close()