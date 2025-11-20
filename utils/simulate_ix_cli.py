#!/usr/bin/env python
"""
CLI script for running IX simulations in background jobs.

This script handles the heavy PHREEQC/WaterTAP operations outside the MCP server
to avoid STDIO connection timeouts during long-running simulations.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set PHREEQC timeout before importing simulation modules
# Background jobs should run to completion without arbitrary timeout
os.environ['PHREEQC_RUN_TIMEOUT_S'] = os.environ.get('PHREEQC_RUN_TIMEOUT_S', '3600')

import json
import argparse
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_ix_simulation(
    input_file: str,
    output_dir: str = '.',
    output_file: str = 'results.json'
):
    """
    Run IX simulation from JSON input file.

    Simulations run until completion (no timeout).

    Args:
        input_file: Path to simulation input JSON
        output_dir: Directory for all output files
        output_file: Name of results JSON file
    """
    try:
        start_time = datetime.now()

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Load input file
        logger.info(f"Loading input from {input_file}...")
        with open(input_file, 'r') as f:
            simulation_input = json.load(f)

        resin_type = simulation_input.get('resin_type', 'SAC')
        flow = simulation_input.get('water', {}).get('flow_m3h', 0)
        logger.info(f"Resin type: {resin_type}, Flow: {flow} m³/hr")

        # Import simulation module
        logger.info("Loading simulation modules...")
        from tools.simulate_ix_hybrid import simulate_ix_hybrid

        # Run simulation (no timeout - runs to completion)
        logger.info("Starting IX simulation (running to completion)...")
        logger.info("Progress: 0% - Initializing PHREEQC...")

        # Log expected runtime based on BV
        targets = simulation_input.get('targets', {})
        vessel = simulation_input.get('vessel', {})
        if vessel.get('bed_volume_l'):
            logger.info(f"Vessel bed volume: {vessel.get('bed_volume_l'):.0f} L")
        if targets.get('hardness_mg_l_caco3'):
            logger.info(f"Target hardness: {targets.get('hardness_mg_l_caco3')} mg/L as CaCO3")

        results = simulate_ix_hybrid(
            simulation_input=simulation_input,
            write_artifacts=True
        )

        # Log progress milestones from results
        if results.get('status') == 'success':
            perf = results.get('performance', {})
            logger.info(f"Progress: 100% - Breakthrough at {perf.get('service_bv_to_target', 0):.0f} BV")

        # Check results
        if results.get('status') == 'error':
            logger.error(f"Simulation failed: {results.get('message')}")
            raise RuntimeError(results.get('message'))

        logger.info("Progress: 100% - Simulation complete")

        # Calculate runtime
        end_time = datetime.now()
        runtime_seconds = (end_time - start_time).total_seconds()

        logger.info(f"Simulation completed in {runtime_seconds:.1f} seconds")

        # Extract key metrics for summary
        performance = results.get('performance', {})
        economics = results.get('economics', {})

        # Build result structure
        result = {
            "success": True,
            "message": f"IX simulation completed in {runtime_seconds:.1f}s",
            "resin_type": resin_type,
            "run_id": results.get('run_id'),
            "summary": {
                "service_bv": performance.get('service_bv_to_target', 0),
                "service_hours": performance.get('service_hours', 0),
                "effluent_hardness_mg_l": performance.get('effluent_hardness_mg_l_caco3', 0),
                "capacity_utilization_percent": performance.get('capacity_utilization_percent', 0),
                "lcow_usd_m3": economics.get('lcow_usd_m3', 0),
                "capital_cost_usd": economics.get('capital_cost_usd', 0),
                "operating_cost_usd_year": economics.get('operating_cost_usd_year', 0)
            },
            "performance": performance,
            "economics": economics,
            "ion_tracking": results.get('ion_tracking', {}),
            "mass_balance": results.get('mass_balance', {}),
            "breakthrough_data": results.get('breakthrough_data', []),
            "warnings": results.get('warnings', []),
            "artifacts": results.get('artifacts', []),
            "runtime_seconds": runtime_seconds
        }

        # Save results
        results_path = output_path / output_file
        with open(results_path, 'w') as f:
            json.dump(result, f, indent=2)
        logger.info(f"Results saved to {results_path}")

        logger.info("=== IX Simulation Complete ===")

        return result

    except Exception as e:
        logger.error(f"Error in simulation: {str(e)}", exc_info=True)
        result = {
            "success": False,
            "message": f"Simulation failed: {str(e)}"
        }

        # Save error result
        error_path = Path(output_dir) / output_file
        error_path.parent.mkdir(parents=True, exist_ok=True)
        with open(error_path, 'w') as f:
            json.dump(result, f, indent=2)

        return result


def main():
    parser = argparse.ArgumentParser(
        description='Run IX simulation from CLI'
    )
    parser.add_argument(
        '--input',
        required=True,
        help='Path to simulation input JSON file'
    )
    parser.add_argument(
        '--output-dir',
        default='.',
        help='Directory for output files (default: current directory)'
    )
    parser.add_argument(
        '--output',
        default='results.json',
        help='Name of results JSON file (default: results.json)'
    )

    args = parser.parse_args()

    result = run_ix_simulation(
        input_file=args.input,
        output_dir=args.output_dir,
        output_file=args.output
    )

    # Exit with appropriate code
    sys.exit(0 if result.get("success", False) else 1)


if __name__ == "__main__":
    main()
