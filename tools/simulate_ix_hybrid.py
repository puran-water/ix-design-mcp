"""
Hybrid IX Simulation Module

Integrates PHREEQC chemistry with WaterTAP flowsheet and costing.
Main entry point for hybrid simulations.
"""

import logging
import json
import os
import sys
from typing import Dict, Any, Optional, Literal
from datetime import datetime
from pathlib import Path
import time
import faulthandler


def _resolve_project_root() -> Path:
    """Resolve project root honoring IX_DESIGN_MCP_ROOT when valid."""
    env_root = os.environ.get("IX_DESIGN_MCP_ROOT")
    if env_root:
        candidate = Path(env_root)
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import schemas
from utils.schemas import (
    IXSimulationInput,
    IXSimulationResult,
    EngineInfo,
    PerformanceMetrics,
    IonTracking,
    MassBalance,
    EconomicsResult,
    UnitCosts,
    SolverInfo,
    ExecutionContext,
    convert_legacy_sac_output
)

# Import artifact manager
from utils.artifacts import get_artifact_manager

# Defer WaterTAP wrapper import to runtime for graceful degradation

# Import existing PHREEQC tools
from tools.sac_simulation import simulate_sac_phreeqc, SACSimulationInput
from tools.wac_simulation import simulate_wac_system, WACSimulationInput

logger = logging.getLogger(__name__)
 
# Lightweight, non-blocking trace writer to OS temp (bypasses stderr logging)
def _safe_trace(msg: str) -> None:
    try:
        import tempfile
        ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        trace_file = os.path.join(tempfile.gettempdir(), 'ix-hybrid-trace.log')
        with open(trace_file, 'a', encoding='utf-8') as f:
            f.write(f"{ts} - {msg}\n")
    except Exception:
        # Never raise from tracing
        pass


def _as_plain_dict(obj: Any) -> Any:
    """Best-effort conversion to a plain dict without importing heavy deps.

    - dict -> dict (unchanged)
    - Pydantic v2 BaseModel -> model_dump()
    - Pydantic v1 BaseModel -> dict()
    - Dataclass -> asdict()
    - Mapping-like -> dict(items())
    Otherwise returns the object unchanged.
    """
    try:
        if isinstance(obj, dict):
            return obj
        # Try Pydantic v2
        if hasattr(obj, 'model_dump') and callable(getattr(obj, 'model_dump')):
            return obj.model_dump()
        # Try Pydantic v1
        if hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
            return obj.dict()
        # Try dataclasses
        try:
            import dataclasses
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
        except Exception:
            pass
        # Try mapping-like
        if hasattr(obj, 'items') and callable(getattr(obj, 'items')):
            return dict(obj.items())
    except Exception:
        # Fall through to return original object on any failure
        pass
    return obj


def get_watertap_mode() -> Literal["off", "auto", "on"]:
    """
    Get WaterTAP mode from environment or config.
    
    Returns:
        "off": Never use WaterTAP
        "auto": Try WaterTAP with smoke test, fallback if fails
        "on": Force WaterTAP, error if not available
    """
    mode = os.environ.get("IX_WATERTAP", "off").lower()
    if mode not in ["off", "auto", "on"]:
        logger.warning(f"Invalid IX_WATERTAP mode: {mode}, defaulting to 'off'")
        return "off"
    return mode


def run_watertap_smoke_test(timeout_seconds: int = 30) -> bool:
    """
    Run a minimal WaterTAP smoke test with timeout.
    
    This creates a minimal flowsheet to verify WaterTAP is functional
    without running a full simulation.
    
    Args:
        timeout_seconds: Maximum time to wait for smoke test
        
    Returns:
        True if smoke test passes, False otherwise
    """
    # Use the isolated smoke test from process_isolation module
    from utils.process_isolation import test_watertap_availability_isolated
    return test_watertap_availability_isolated(timeout_seconds)


def simulate_ix_hybrid(
    simulation_input: Dict[str, Any],
    write_artifacts: bool = True
) -> Dict[str, Any]:
    """
    Run hybrid IX simulation: PHREEQC chemistry + WaterTAP flowsheet/costing.
    
    This is the main implementation of the hybrid approach where:
    1. PHREEQC handles the detailed multi-ion chemistry
    2. WaterTAP provides flowsheet structure and costing
    3. Results are combined into unified schema
    
    Args:
        simulation_input: Complete simulation input (dict or IXSimulationInput)
        write_artifacts: Whether to write result artifacts
        
    Returns:
        Unified simulation results conforming to IXSimulationResult schema
    """
    logger.info("Starting hybrid IX simulation")
    start_time = datetime.now()
    t0 = time.perf_counter()

    # Lightweight trace to avoid Windows/WSL log contention
    def _trace(msg: str) -> None:
        try:
            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            # Use Windows temp path since Python is running on Windows
            import tempfile
            trace_file = os.path.join(tempfile.gettempdir(), 'ix-hybrid-trace.log')
            with open(trace_file, 'a', encoding='utf-8') as f:
                f.write(f"{ts} - {msg}\n")
        except Exception:
            pass

    _trace("simulate_ix_hybrid: start")

    # Install a watchdog that dumps thread traces if something blocks for too long
    # This is diagnostic-only and harmless
    try:
        import tempfile
        stack_file = os.path.join(tempfile.gettempdir(), 'ix-hybrid-stacks.log')
        fh = open(stack_file, 'a', encoding='utf-8')
        # Dump every 120s until cancelled
        faulthandler.dump_traceback_later(120, repeat=True, file=fh)
    except Exception:
        fh = None
    
    # Parse input if needed
    if isinstance(simulation_input, dict):
        try:
            ix_input = IXSimulationInput(**simulation_input)
        except Exception as e:
            logger.error(f"Invalid input: {e}")
            return {
                "status": "error",
                "message": f"Input validation failed: {str(e)}",
                "run_id": datetime.now().strftime("%Y%m%d_%H%M%S")
            }
    else:
        ix_input = simulation_input
    
    # Get artifact manager
    artifacts_mgr = get_artifact_manager()
    run_id = artifacts_mgr.generate_run_id(ix_input.model_dump())
    artifacts = []
    
    # Write input artifact if requested
    if write_artifacts:
        _trace("writing input artifact: begin")
        input_path = artifacts_mgr.write_json_artifact(
            ix_input.model_dump(),
            run_id,
            "input"
        )
        artifacts.append(input_path)
        _trace(f"writing input artifact: done -> {input_path}")
    
    try:
        # Step 1: Run PHREEQC simulation for chemistry
        # Determine regeneration mode preference from raw input (if provided)
        requested_regen_mode: Optional[str] = None
        if isinstance(simulation_input, dict):
            # Accept multiple ways to specify optimization explicitly
            # Priority: top-level regeneration_config.mode > cycle.regeneration_mode > cycle.mode
            try:
                rc = simulation_input.get("regeneration_config") or {}
                cyc = simulation_input.get("cycle") or {}

                mode_raw = (
                    rc.get("mode")
                    or cyc.get("regeneration_mode")
                    or cyc.get("mode")
                )

                if isinstance(mode_raw, str):
                    mode_norm = mode_raw.strip().lower()
                    if mode_norm in {"staged_optimize", "optimize", "optimization", "opt"}:
                        requested_regen_mode = "staged_optimize"
                    elif mode_norm in {"staged_fixed", "fixed", "fixed_bv", "fixed_staged"}:
                        requested_regen_mode = "staged_fixed"
                    else:
                        # Unrecognized value; ignore and use default
                        logger.warning(
                            f"Unrecognized regeneration mode '{mode_raw}', defaulting to staged_fixed"
                        )
                        requested_regen_mode = None
            except Exception:
                # Be robust to unexpected shapes
                requested_regen_mode = None

        # Always default to staged_fixed unless explicitly requested
        logger.info(
            f"[Step 1/4] Running PHREEQC simulation for chemistry (regen_mode="
            f"{requested_regen_mode or 'staged_fixed'})"
        )
        _trace("phreeqc: begin")
        phreeqc_results = run_phreeqc_engine(ix_input, requested_regen_mode=requested_regen_mode)
        _trace("phreeqc: done")
        
        if phreeqc_results.get("status") == "error":
            raise RuntimeError(f"PHREEQC failed: {phreeqc_results.get('message')}")
        
        # Check WaterTAP mode and availability
        watertap_mode = get_watertap_mode()
        watertap_available = False
        import_error = None
        
        logger.info(f"WaterTAP mode: {watertap_mode}")
        _trace(f"watertap_mode: {watertap_mode}")
        
        if watertap_mode == "off":
            logger.info("WaterTAP disabled by configuration - using PHREEQC with estimated costs")
            _trace("watertap: disabled - proceeding with PHREEQC-only costing")
            watertap_available = False
        elif watertap_mode in ["auto", "on"]:
            # Keep all WaterTAP/IDAES imports in isolated worker processes.
            # Avoid importing utils.ix_watertap_wrapper here to prevent main-process hangs.
            try:
                if watertap_mode == "auto":
                    # Run smoke test for auto mode (isolated process with timeout)
                    logger.info("Running WaterTAP smoke test...")
                    watertap_available = run_watertap_smoke_test()
                    if not watertap_available:
                        logger.warning("WaterTAP smoke test failed, falling back to PHREEQC")
                else:  # mode == "on"
                    # Force attempt; actual availability will be determined in the worker
                    watertap_available = True
                    logger.info("WaterTAP forced on by configuration")
            except Exception as e:
                import_error = e
                if watertap_mode == "on":
                    raise RuntimeError(f"WaterTAP forced on but preliminary check failed: {e}")
                logger.warning(f"WaterTAP preliminary check failed, falling back to PHREEQC: {e}")

        if watertap_available:
            # Step 2: Run WaterTAP in isolated process with timeout
            logger.info("[Step 2/4] Running WaterTAP flowsheet in isolated process")
            
            # Import process isolation
            from utils.process_isolation import run_watertap_with_timeout
            
            # Prepare feed composition for WaterTAP
            feed_composition = ix_input.water.get_ion_dict()
            flow_rate_m3h = ix_input.water.flow_m3h
            vessel_config = ix_input.vessel.model_dump()
            
            # Run WaterTAP with 60-second timeout
            watertap_result = run_watertap_with_timeout(
                feed_composition,
                flow_rate_m3h,
                vessel_config,
                phreeqc_results,
                timeout_seconds=60
            )
            
            if watertap_result.get("status") == "success":
                logger.info("[Step 3/4] WaterTAP flowsheet solved successfully")
                watertap_solved = True
                economics = watertap_result.get("economics", {})
            elif watertap_result.get("status") == "timeout":
                logger.warning(f"[Step 3/4] WaterTAP timed out: {watertap_result.get('message')}")
                watertap_solved = False
                economics = estimate_costs_from_phreeqc(phreeqc_results, ix_input)
            else:
                logger.warning(f"[Step 3/4] WaterTAP failed: {watertap_result.get('message')}")
                watertap_solved = False
                economics = estimate_costs_from_phreeqc(phreeqc_results, ix_input)
        else:
            # WaterTAP not available: estimate costs and mark not solved
            watertap_solved = False
            _trace("economics: begin estimate_costs_from_phreeqc")
            logger.info("Estimating costs from PHREEQC results...")
            economics = estimate_costs_from_phreeqc(phreeqc_results, ix_input)
            logger.info("Cost estimation complete")
            _trace("economics: end estimate_costs_from_phreeqc")
        
        # Compile unified results
        logger.info("Compiling unified results...")
        _trace("compile: begin")
        unified_results = compile_hybrid_results(
            phreeqc_results,
            economics,
            ix_input,
            run_id,
            watertap_solved
        )
        logger.info("Results compilation complete")
        _trace("compile: end")
        
        # Write results artifact
        if write_artifacts:
            logger.info("Writing results artifact...")
            _trace("write_results_artifact: begin")
            results_path = artifacts_mgr.write_json_artifact(
                unified_results,
                run_id,
                "results"
            )
            artifacts.append(results_path)
            logger.info(f"Results artifact written: {results_path}")
            _trace(f"write_results_artifact: end -> {results_path}")
            
            # Create manifest
            logger.info("Creating manifest...")
            _trace("manifest: begin")
            manifest_path = artifacts_mgr.create_manifest(
                run_id,
                artifacts,
                {
                    "engine": "hybrid",
                    "phreeqc_success": True,
                    "watertap_solved": watertap_solved,
                    "duration_seconds": (datetime.now() - start_time).total_seconds()
                }
            )
            artifacts.append(manifest_path)
            logger.info(f"Manifest created: {manifest_path}")
            _trace(f"manifest: end -> {manifest_path}")
        
        # Add artifacts to results
        unified_results["artifacts"] = artifacts
        unified_results["artifact_dir"] = str(artifacts_mgr.base_dir)
        
        logger.info(f"Hybrid simulation complete. Run ID: {run_id}")
        _trace(f"simulate_ix_hybrid: complete in {time.perf_counter() - t0:.2f}s")
        # Cancel watchdog
        try:
            faulthandler.cancel_dump_traceback_later()
        except Exception:
            pass
        if fh:
            try:
                fh.close()
            except Exception:
                pass
        return unified_results
        
    except Exception as e:
        import traceback
        logger.error(f"Hybrid simulation failed: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        _trace(f"simulate_ix_hybrid: exception -> {e}")
        
        # Write error artifact
        if write_artifacts:
            error_data = {
                "status": "error",
                "message": str(e),
                "traceback": traceback.format_exc(),
                "run_id": run_id,
                "timestamp": datetime.now().isoformat()
            }
            _trace("write_error_artifact: begin")
            error_path = artifacts_mgr.write_json_artifact(
                error_data,
                run_id,
                "error"
            )
            artifacts.append(error_path)
            _trace(f"write_error_artifact: end -> {error_path}")
        
        # Cancel watchdog on error
        try:
            faulthandler.cancel_dump_traceback_later()
        except Exception:
            pass
        if fh:
            try:
                fh.close()
            except Exception:
                pass

        return {
            "status": "error",
            "message": str(e),
            "run_id": run_id,
            "artifacts": artifacts
        }


def run_phreeqc_engine(
    ix_input: IXSimulationInput,
    requested_regen_mode: Optional[Literal["staged_fixed", "staged_optimize"]] = None,
) -> Dict[str, Any]:
    """
    Run PHREEQC simulation based on resin type.
    
    Args:
        ix_input: Parsed simulation input
        
    Returns:
        PHREEQC simulation results
    """
    # Prepare input for legacy PHREEQC tools
    # Extract ions from the unified dict or individual fields
    ions = ix_input.water.get_ion_dict()
    # Determine regeneration mode: default to staged_fixed to avoid slow optimization
    regen_mode = (
        requested_regen_mode if requested_regen_mode in ["staged_fixed", "staged_optimize"] else "staged_fixed"
    )

    if regen_mode == "staged_optimize":
        logger.info("Regeneration mode explicitly set to staged_optimize (may be slow)")
    else:
        logger.info("Regeneration mode set to staged_fixed (default)")

    legacy_input = {
        "water_analysis": {
            "flow_m3_hr": ix_input.water.flow_m3h,
            "temperature_celsius": ix_input.water.temperature_c,
            "pH": ix_input.water.ph,
            "ca_mg_l": ions.get('Ca_2+', 0),
            "mg_mg_l": ions.get('Mg_2+', 0),
            "na_mg_l": ions.get('Na_+', 0),
            "cl_mg_l": ions.get('Cl_-', 0),
            "hco3_mg_l": ions.get('HCO3_-', 0),
            "so4_mg_l": ions.get('SO4_2-', 0)
        },
        "vessel_configuration": {
            "diameter_m": ix_input.vessel.diameter_m,
            "bed_depth_m": ix_input.vessel.bed_depth_m,
            "bed_volume_L": ix_input.vessel.bed_volume_l or (
                3.14159 * (ix_input.vessel.diameter_m/2)**2 * 
                ix_input.vessel.bed_depth_m * 1000
            ),
            "number_service": ix_input.vessel.number_in_service,
            "number_standby": 1,
            "resin_type": ix_input.resin_type,
            "resin_volume_m3": ix_input.vessel.resin_volume_m3 or (
                3.14159 * (ix_input.vessel.diameter_m/2)**2 * ix_input.vessel.bed_depth_m
            ),
            "freeboard_m": 0.5,  # Default freeboard
            "vessel_height_m": ix_input.vessel.bed_depth_m + 0.5  # bed depth + freeboard
        },
        "target_hardness_mg_l_caco3": ix_input.targets.hardness_mg_l_caco3,
        "regeneration_config": {
            "enabled": True,
            "regenerant_type": ix_input.cycle.regenerant_type,
            "concentration_percent": ix_input.cycle.regenerant_concentration_wt,
            "regenerant_dose_g_per_L": ix_input.cycle.regenerant_dose_g_per_l,
            "flow_direction": "back" if ix_input.cycle.flow_direction == "counter-current" else "forward",
            "backwash_enabled": ix_input.cycle.backwash,
            # Critical fix: default to staged_fixed to prevent long-running optimization
            "mode": regen_mode
        },
        "full_data": ix_input.options.full_data if ix_input.options else False
    }
    
    # Route to appropriate simulation
    if ix_input.resin_type == "SAC":
        sac_input = SACSimulationInput(**legacy_input)
        results = simulate_sac_phreeqc(sac_input)
        # Convert to dict for downstream consumers (support Pydantic v1/v2)
        if hasattr(results, 'model_dump') and callable(getattr(results, 'model_dump')):
            return results.model_dump()
        if hasattr(results, 'dict') and callable(getattr(results, 'dict')):
            return results.dict()
        return results
    
    elif ix_input.resin_type in ["WAC_Na", "WAC_H"]:
        # Add WAC-specific fields
        # Add bed_expansion_percent (required for WAC vessels)
        default_expansion = 50.0 if ix_input.resin_type == "WAC_Na" else 100.0
        legacy_input["vessel_configuration"]["bed_expansion_percent"] = (
            getattr(ix_input.vessel, 'bed_expansion_percent', None) or default_expansion
        )

        if ix_input.resin_type == "WAC_H":
            legacy_input["target_alkalinity_mg_l_caco3"] = (
                ix_input.targets.alkalinity_mg_l_caco3 or 5.0
            )

        wac_input = WACSimulationInput(**legacy_input)
        results = simulate_wac_system(wac_input)
        if hasattr(results, 'model_dump') and callable(getattr(results, 'model_dump')):
            return results.model_dump()
        if hasattr(results, 'dict') and callable(getattr(results, 'dict')):
            return results.dict()
        return results
    
    else:
        raise ValueError(f"Unsupported resin type: {ix_input.resin_type}")


def estimate_costs_from_phreeqc(
    phreeqc_results: Dict[str, Any],
    ix_input: IXSimulationInput
) -> Dict[str, Any]:
    """
    Estimate costs from PHREEQC results when WaterTAP solve fails.
    
    Args:
        phreeqc_results: Results from PHREEQC simulation
        ix_input: Original input parameters
        
    Returns:
        Estimated economics dictionary
    """
    # Extract key parameters
    vessel = ix_input.vessel
    pricing = ix_input.pricing
    regen = phreeqc_results.get("regeneration_results") or {}

    # Capital costs (simplified correlations)
    resin_volume_m3 = vessel.resin_volume_m3 or (
        3.14159 * (vessel.diameter_m/2)**2 * vessel.bed_depth_m
    )

    vessel_cost = 50000 * (resin_volume_m3 ** 0.7)
    resin_cost = (pricing.resin_usd_m3 if pricing else 2800) * resin_volume_m3
    pump_cost = 15000  # Fixed estimate
    instrumentation = (vessel_cost + resin_cost) * 0.15

    total_capital = (vessel_cost + resin_cost + pump_cost + instrumentation) * 2.5

    # Operating costs (annual) - with safety checks for missing regeneration data
    regenerant_kg = regen.get("regenerant_consumed_kg", 100) if regen else 100
    cycle_hours = regen.get("total_cycle_time_hours", 24) if regen else 24
    cycles_per_year = 8760 / cycle_hours
    
    regenerant_cost = regenerant_kg * cycles_per_year * (pricing.nacl_usd_kg if pricing else 0.12)
    resin_replacement = resin_cost * (pricing.resin_replacement_rate if pricing else 0.05)
    energy_cost = ix_input.water.flow_m3h * 8760 * 0.05 * (pricing.electricity_usd_kwh if pricing else 0.07)
    
    total_opex = regenerant_cost + resin_replacement + energy_cost
    
    # Calculate LCOW
    crf = 0.1  # Capital recovery factor (simplified)
    annual_production = ix_input.water.flow_m3h * 8760 * 0.9  # 90% availability
    lcow = (total_capital * crf + total_opex) / annual_production
    
    return {
        "capital_cost_usd": total_capital,
        "operating_cost_usd_year": total_opex,
        "regenerant_cost_usd_year": regenerant_cost,
        "resin_replacement_cost_usd_year": resin_replacement,
        "energy_cost_usd_year": energy_cost,
        "lcow_usd_m3": lcow,
        "sec_kwh_m3": 0.05,  # Default estimate
        "unit_costs": {
            "vessels_usd": vessel_cost,
            "resin_initial_usd": resin_cost,
            "pumps_usd": pump_cost,
            "instrumentation_usd": instrumentation,
            "installation_factor": 2.5
        }
    }


def compile_hybrid_results(
    phreeqc_results: Dict[str, Any],
    economics: Dict[str, Any],
    ix_input: IXSimulationInput,
    run_id: str,
    watertap_solved: bool
) -> Dict[str, Any]:
    """
    Compile results from PHREEQC and WaterTAP into unified schema.
    
    Args:
        phreeqc_results: PHREEQC simulation results
        economics: Economic results from WaterTAP or estimation
        ix_input: Original input
        run_id: Unique run identifier
        watertap_solved: Whether WaterTAP flowsheet solved
        
    Returns:
        Unified results conforming to IXSimulationResult schema
    """
    # Use file trace first to avoid potential stderr blocking
    _safe_trace("compile_hybrid_results: start")
    logger.info("compile_hybrid_results: Entered function")
    
    # Ensure inputs are plain dicts (defensive against BaseModel instances)
    try:
        phreeqc_results = _as_plain_dict(phreeqc_results)
    except Exception:
        pass
    try:
        economics = _as_plain_dict(economics)
    except Exception:
        pass
    # Extract performance metrics from PHREEQC
    _safe_trace("compile_hybrid_results: extracting PHREEQC metrics")
    logger.info("Extracting PHREEQC metrics...")
    perf_metrics = phreeqc_results.get("performance_metrics", {})
    regen_results = phreeqc_results.get("regeneration_results", {})
    
    # Build performance metrics
    _safe_trace("compile_hybrid_results: build PerformanceMetrics")
    logger.info("Building PerformanceMetrics...")
    performance = PerformanceMetrics(
        service_bv_to_target=phreeqc_results.get("breakthrough_bv", 0),
        service_hours=phreeqc_results.get("service_time_hours", 0),
        effluent_hardness_mg_l_caco3=phreeqc_results.get("breakthrough_hardness_mg_l_caco3", 5),
        effluent_ph=7.8,  # Extract from data if available
        effluent_tds_mg_l=0,  # Calculate from ion sum
        delta_p_bar=0.6,  # Default or calculate
        sec_kwh_m3=economics.get("sec_kwh_m3", 0.05),
        capacity_utilization_percent=phreeqc_results.get("capacity_utilization_percent", 0)
    )
    _safe_trace("compile_hybrid_results: PerformanceMetrics created")
    logger.info("PerformanceMetrics created")
    
    # Build ion tracking
    _safe_trace("compile_hybrid_results: build IonTracking")
    logger.info("Building IonTracking...")
    ion_tracking = IonTracking(
        feed_mg_l=ix_input.water.get_ion_dict(),
        effluent_mg_l={},  # Extract from PHREEQC if available
        waste_mg_l={},  # Extract from regeneration data
        removal_percent={
            "Ca_2+": perf_metrics.get("breakthrough_ca_removal_percent", 0),
            "Mg_2+": perf_metrics.get("breakthrough_mg_removal_percent", 0),
            "hardness": perf_metrics.get("breakthrough_hardness_removal_percent", 0)
        }
    )
    _safe_trace("compile_hybrid_results: IonTracking created")
    logger.info("IonTracking created")
    
    # Build mass balance
    _safe_trace("compile_hybrid_results: build MassBalance")
    logger.info("Building MassBalance...")
    # Handle None values properly - ensure we always have numeric values
    hardness_eluted = regen_results.get("hardness_eluted_kg_caco3")
    total_hardness = regen_results.get("total_hardness_removed_kg", 0)
    
    # Ensure we have a numeric value
    if hardness_eluted is not None and hardness_eluted != "null":
        hardness_val = float(hardness_eluted)
    elif total_hardness is not None and total_hardness != "null":
        hardness_val = float(total_hardness)
    else:
        hardness_val = 0.0
    
    logger.debug(f"hardness_val: {hardness_val}, eluted: {hardness_eluted}, total: {total_hardness}")
    
    mass_balance = MassBalance(
        regenerant_kg_cycle=float(regen_results.get("regenerant_consumed_kg", 0) or 0),
        backwash_m3_cycle=0.0,  # Extract if available
        rinse_m3_cycle=0.0,  # Extract if available
        waste_m3_cycle=float(regen_results.get("waste_volume_m3", 0) or 0),
        hardness_removed_kg_caco3=hardness_val,
        closure_percent=99.0
    )
    _safe_trace("compile_hybrid_results: MassBalance created")
    logger.info("MassBalance created")
    
    # Build economics result
    _safe_trace("compile_hybrid_results: build EconomicsResult")
    logger.info("Building economics result...")
    unit_costs = UnitCosts(
        vessels_usd=economics.get("unit_costs", {}).get("vessels_usd", 0),
        resin_initial_usd=economics.get("unit_costs", {}).get("resin_initial_usd", 0),
        pumps_usd=economics.get("unit_costs", {}).get("pumps_usd", 0),
        instrumentation_usd=economics.get("unit_costs", {}).get("instrumentation_usd", 0),
        installation_factor=economics.get("unit_costs", {}).get("installation_factor", 2.5)
    )
    
    economics_result = EconomicsResult(
        capital_cost_usd=economics.get("capital_cost_usd", 0),
        operating_cost_usd_year=economics.get("operating_cost_usd_year", 0),
        regenerant_cost_usd_year=economics.get("regenerant_cost_usd_year", 0),
        resin_replacement_cost_usd_year=economics.get("resin_replacement_cost_usd_year", 0),
        energy_cost_usd_year=economics.get("energy_cost_usd_year", 0),
        lcow_usd_m3=economics.get("lcow_usd_m3", 0),
        sec_kwh_m3=economics.get("sec_kwh_m3", 0),
        unit_costs=unit_costs
    )
    _safe_trace("compile_hybrid_results: EconomicsResult created")
    logger.info("EconomicsResult created")
    
    # Build solver info
    _safe_trace("compile_hybrid_results: build SolverInfo")
    logger.info("Building SolverInfo...")
    solver_info = SolverInfo(
        engine="phreeqc_watertap_hybrid",
        termination_condition="optimal" if watertap_solved else "phreeqc_only"
    )
    _safe_trace("compile_hybrid_results: SolverInfo created")
    logger.info("SolverInfo created")
    
    # Build execution context
    _safe_trace("compile_hybrid_results: build ExecutionContext")
    logger.info("Building ExecutionContext...")
    git_sha = "unknown"
    try:
        logger.info("Calling get_git_sha()...")
        git_sha = get_git_sha()
        logger.info(f"get_git_sha() returned: {git_sha}")
    except Exception as e:
        logger.info(f"get_git_sha() failed: {e}")
        pass
    context = ExecutionContext(
        timestamp=datetime.now().isoformat(),
        phreeqpython_version="1.5.0",  # Get dynamically if possible
        watertap_version="0.11.0" if watertap_solved else None,
        git_sha=git_sha
    )
    _safe_trace("compile_hybrid_results: ExecutionContext created")
    logger.info("ExecutionContext created")
    
    # Build engine info
    _safe_trace("compile_hybrid_results: build EngineInfo")
    logger.info("Building EngineInfo...")
    engine_info = EngineInfo(
        name="phreeqc_watertap_hybrid",
        chemistry="phreeqc_direct",
        flowsheet="watertap" if watertap_solved else None,
        costing="watertap_ix" if watertap_solved else "estimated",
        version="1.0.0",
        mode="service_regeneration"
    )
    _safe_trace("compile_hybrid_results: EngineInfo created")
    logger.info("EngineInfo created")
    
    # Create result object
    _safe_trace("compile_hybrid_results: create IXSimulationResult")
    logger.info("Creating IXSimulationResult object...")
    
    # Log breakthrough data size for debugging
    bd = phreeqc_results.get("breakthrough_data")
    if bd and isinstance(bd, list):
        _safe_trace(f"compile_hybrid_results: breakthrough_data points={len(bd)}")
        logger.info(f"Breakthrough data has {len(bd)} points")
    
    result = IXSimulationResult(
        status="success" if phreeqc_results.get("status") == "success" else "warning",
        run_id=run_id,
        performance=performance,
        ion_tracking=ion_tracking,
        mass_balance=mass_balance,
        economics=economics_result,
        solve_info=solver_info,
        warnings=phreeqc_results.get("warnings", []),
        context=context,
        artifact_dir="",  # Will be set by caller
        artifacts=[],  # Will be set by caller
        breakthrough_data=phreeqc_results.get("breakthrough_data"),
        simulation_details={
            "engine": engine_info.model_dump(),
            "phreeqc_details": phreeqc_results.get("simulation_details", {}),
            "watertap_solved": watertap_solved
        }
    )
    
    _safe_trace("compile_hybrid_results: IXSimulationResult created -> model_dump")
    logger.info("IXSimulationResult object created, calling model_dump()...")
    result_dict = result.model_dump()
    _safe_trace("compile_hybrid_results: model_dump complete")
    logger.info("model_dump() complete")
    
    _safe_trace("compile_hybrid_results: end")
    return result_dict


def get_git_sha() -> str:
    """Get current git SHA if available."""
    # DISABLED: Git subprocess hangs on Windows despite timeout parameter
    # This is non-essential metadata, so we're disabling it to prevent timeouts
    return "unknown"
    
    # Original code kept for reference:
    # try:
    #     import subprocess
    #     result = subprocess.run(
    #         ['git', 'rev-parse', '--short', 'HEAD'],
    #         capture_output=True,
    #         text=True,
    #         check=False,
    #         timeout=2
    #     )
    #     if result.returncode == 0:
    #         return result.stdout.strip()
    # except:
    #     pass
    # return "unknown"
