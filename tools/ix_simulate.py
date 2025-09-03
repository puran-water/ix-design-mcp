"""
Direct IX Simulation Module

Provides direct execution of IX simulations without relying on Jupyter notebooks.
Parallel to RO's utils/simulate_ro.py pattern.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Literal
from datetime import datetime
import hashlib

# Import existing simulation modules
from tools.sac_simulation import simulate_sac_phreeqc, SACSimulationInput
from tools.wac_simulation import simulate_wac_system, WACSimulationInput
from tools.sac_configuration import SACWaterComposition, SACVesselConfiguration
from tools.wac_configuration import WACVesselConfiguration

logger = logging.getLogger(__name__)


def generate_run_id(input_data: Dict[str, Any]) -> str:
    """
    Generate deterministic run_id from input parameters.
    
    Args:
        input_data: Simulation input parameters
        
    Returns:
        Run ID as timestamp_hash format
    """
    # Create deterministic hash from inputs
    input_str = json.dumps(input_data, sort_keys=True)
    input_hash = hashlib.md5(input_str.encode()).hexdigest()[:8]
    
    # Add timestamp for uniqueness
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    return f"{timestamp}_{input_hash}"


def ensure_results_directory() -> Path:
    """
    Ensure results directory exists.
    
    Returns:
        Path to results directory
    """
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def write_results_artifact(
    results: Dict[str, Any],
    run_id: str,
    artifact_type: str = "json"
) -> str:
    """
    Write results to artifact file.
    
    Args:
        results: Simulation results
        run_id: Unique run identifier
        artifact_type: Type of artifact (json, html, etc.)
        
    Returns:
        Path to written artifact
    """
    results_dir = ensure_results_directory()
    
    # Determine file extension
    ext_map = {
        "json": "json",
        "html": "html",
        "log": "log",
        "csv": "csv"
    }
    extension = ext_map.get(artifact_type, "txt")
    
    # Write file
    artifact_path = results_dir / f"ix_simulation_{run_id}.{extension}"
    
    if artifact_type == "json":
        with open(artifact_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            f.write('\n')  # Add newline at EOF
    else:
        # For other types, just write as text for now
        with open(artifact_path, 'w', encoding='utf-8') as f:
            f.write(str(results))
    
    logger.info(f"Wrote {artifact_type} artifact to {artifact_path}")
    return str(artifact_path)


def compile_unified_results(
    simulation_output: Any,
    input_data: Dict[str, Any],
    engine_info: Dict[str, str],
    run_id: str,
    artifacts: list
) -> Dict[str, Any]:
    """
    Compile simulation results into unified schema.
    
    Args:
        simulation_output: Raw output from simulation
        input_data: Original input parameters
        engine_info: Engine metadata
        run_id: Unique run identifier
        artifacts: List of artifact paths
        
    Returns:
        Unified results dictionary
    """
    # Extract common fields from simulation output
    if hasattr(simulation_output, 'dict'):
        output_dict = simulation_output.dict()
    else:
        output_dict = simulation_output
    
    # Build unified schema
    unified_results = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "status": output_dict.get("status", "success"),
        "engine": engine_info,
        
        # Performance metrics
        "performance": {
            "breakthrough_bv": output_dict.get("breakthrough_bv"),
            "service_time_hours": output_dict.get("service_time_hours"),
            "capacity_utilization_percent": output_dict.get("capacity_utilization_percent"),
            "phreeqc_competition_factor": output_dict.get("phreeqc_determined_capacity_factor"),
        },
        
        # Ion tracking (if available)
        "ion_tracking": {
            "feed": input_data.get("water_analysis", {}),
            "effluent": output_dict.get("breakthrough_data", {}).get("effluent_composition", {}),
            "removal_percent": output_dict.get("performance_metrics", {})
        },
        
        # Regeneration results
        "regeneration": output_dict.get("regeneration_results", {}),
        
        # Economics (placeholder - will be populated in Phase 6)
        "economics": {
            "capital_cost_usd": None,
            "operating_cost_usd_year": None,
            "LCOW_usd_m3": None,
            "SEC_kWh_m3": None,
            "unit_costs": {}
        },
        
        # Metadata
        "simulation_details": output_dict.get("simulation_details", {}),
        "breakthrough_data": output_dict.get("breakthrough_data", {}),
        "warnings": output_dict.get("warnings", []),
        "artifacts": artifacts,
        
        # Context
        "context": {
            "timestamp": datetime.now().isoformat(),
            "phreeqpython": "1.5.0",  # Will be dynamically determined later
            "watertap": None,  # Will be added in Phase 4
            "git_sha": get_git_sha()
        }
    }
    
    return unified_results


def get_git_sha() -> str:
    """Get current git SHA if available."""
    # DISABLED: Git subprocess hangs on Windows despite timeout parameter
    # This is non-essential metadata, so we're disabling it to prevent timeouts
    return "unknown"


def run_sac_direct_simulation(
    input_data: Dict[str, Any],
    write_artifacts: bool = True
) -> Dict[str, Any]:
    """
    Run SAC simulation directly without notebooks.
    
    Args:
        input_data: Simulation input parameters
        write_artifacts: Whether to write result artifacts
        
    Returns:
        Unified simulation results
    """
    logger.info("Starting direct SAC simulation")
    
    # Generate run ID
    run_id = generate_run_id(input_data)
    
    # Create SAC input object
    sac_input = SACSimulationInput(**input_data)
    
    # Run PHREEQC simulation
    try:
        simulation_output = simulate_sac_phreeqc(sac_input)
    except Exception as e:
        logger.error(f"SAC simulation failed: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "run_id": run_id
        }
    
    # Prepare engine info
    engine_info = {
        "name": "phreeqc_direct",
        "chemistry": "phreeqc",
        "version": "3.7",
        "mode": "service_regeneration"
    }
    
    # Initialize artifacts list
    artifacts = []
    
    # Write artifacts if requested
    if write_artifacts:
        # Write input
        input_artifact = write_results_artifact(
            {"input": input_data},
            run_id,
            "json"
        )
        artifacts.append(input_artifact)
    
    # Compile unified results
    unified_results = compile_unified_results(
        simulation_output,
        input_data,
        engine_info,
        run_id,
        artifacts
    )
    
    # Write main results artifact
    if write_artifacts:
        results_artifact = write_results_artifact(
            unified_results,
            run_id,
            "json"
        )
        artifacts.append(results_artifact)
        unified_results["artifacts"] = artifacts
        unified_results["artifact_dir"] = str(ensure_results_directory())
    
    logger.info(f"SAC simulation complete. Run ID: {run_id}")
    return unified_results


def run_wac_direct_simulation(
    input_data: Dict[str, Any],
    write_artifacts: bool = True
) -> Dict[str, Any]:
    """
    Run WAC simulation directly without notebooks.
    
    Args:
        input_data: Simulation input parameters
        write_artifacts: Whether to write result artifacts
        
    Returns:
        Unified simulation results
    """
    logger.info("Starting direct WAC simulation")
    
    # Generate run ID
    run_id = generate_run_id(input_data)
    
    # Create WAC input object
    wac_input = WACSimulationInput(**input_data)
    
    # Run PHREEQC simulation
    try:
        simulation_output = simulate_wac_system(wac_input)
    except Exception as e:
        logger.error(f"WAC simulation failed: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "run_id": run_id
        }
    
    # Prepare engine info
    engine_info = {
        "name": "phreeqc_direct",
        "chemistry": "phreeqc",
        "version": "3.7",
        "mode": "service_regeneration",
        "resin_type": input_data.get("vessel_configuration", {}).get("resin_type", "WAC")
    }
    
    # Initialize artifacts list
    artifacts = []
    
    # Write artifacts if requested
    if write_artifacts:
        # Write input
        input_artifact = write_results_artifact(
            {"input": input_data},
            run_id,
            "json"
        )
        artifacts.append(input_artifact)
    
    # Compile unified results
    unified_results = compile_unified_results(
        simulation_output,
        input_data,
        engine_info,
        run_id,
        artifacts
    )
    
    # Write main results artifact
    if write_artifacts:
        results_artifact = write_results_artifact(
            unified_results,
            run_id,
            "json"
        )
        artifacts.append(results_artifact)
        unified_results["artifacts"] = artifacts
        unified_results["artifact_dir"] = str(ensure_results_directory())
    
    logger.info(f"WAC simulation complete. Run ID: {run_id}")
    return unified_results


def run_ix_simulation(
    simulation_input: Dict[str, Any],
    engine: Literal["phreeqc", "watertap_hybrid"] = "phreeqc",
    write_artifacts: bool = True
) -> Dict[str, Any]:
    """
    Main entry point for IX simulations.
    Routes to appropriate engine based on resin type and configuration.
    
    Args:
        simulation_input: Complete simulation input
        engine: Which engine to use
        write_artifacts: Whether to write result artifacts
        
    Returns:
        Unified simulation results
    """
    # Determine resin type
    resin_type = simulation_input.get("vessel_configuration", {}).get("resin_type", "SAC")
    
    if engine == "watertap_hybrid":
        # Will be implemented in Phase 4
        raise NotImplementedError("WaterTAP hybrid engine will be implemented in Phase 4")
    
    # Route to appropriate PHREEQC simulation
    if resin_type == "SAC":
        return run_sac_direct_simulation(simulation_input, write_artifacts)
    elif resin_type in ["WAC_Na", "WAC_H"]:
        return run_wac_direct_simulation(simulation_input, write_artifacts)
    else:
        raise ValueError(f"Unknown resin type: {resin_type}")