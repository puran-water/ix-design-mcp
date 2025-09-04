"""
Process-based isolation for WaterTAP operations.

Provides hard timeout capability and crash isolation for WaterTAP
flowsheet operations that may hang or crash due to solver issues.
"""

import subprocess
import json
import signal
import threading
import logging
import traceback
from typing import Dict, Any, Optional
from pathlib import Path
import sys
import os
import time

logger = logging.getLogger(__name__)


def run_watertap_with_timeout(
    feed_composition: Dict[str, float],
    flow_rate_m3h: float,
    vessel_config: Dict[str, Any],
    phreeqc_results: Dict[str, Any],
    timeout_seconds: int = 60
) -> Dict[str, Any]:
    """
    Run WaterTAP flowsheet using subprocess.Popen with timeout.
    
    This approach provides complete isolation by running a standalone
    Python script in a fresh interpreter, avoiding all import graph issues.
    
    Args:
        feed_composition: Ion concentrations in mg/L
        flow_rate_m3h: Feed flow rate
        vessel_config: Vessel configuration
        phreeqc_results: Results from PHREEQC simulation
        timeout_seconds: Maximum time to wait for flowsheet
        
    Returns:
        Dictionary with flowsheet results or timeout/error info
    """
    logger.info(f"Starting WaterTAP flowsheet in subprocess (timeout: {timeout_seconds}s)")
    
    # Prepare input data
    input_data = {
        'feed_composition': feed_composition,
        'flow_rate_m3h': flow_rate_m3h,
        'vessel_config': vessel_config,
        'phreeqc_results': phreeqc_results
    }
    
    # Path to worker script
    worker_script = Path(__file__).parent / "watertap_worker.py"
    if not worker_script.exists():
        logger.error(f"Worker script not found: {worker_script}")
        return {
            "status": "error",
            "message": f"Worker script not found: {worker_script}",
            "watertap_used": False
        }
    
    # Get Python executable - use venv312 which has WaterTAP installed
    # Check if running on Windows (for proper path handling)
    if sys.platform == "win32" or os.name == "nt":
        python_exe = r"C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe"
    else:
        # WSL or Linux path
        python_exe = "/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe"
    
    # Verify Python executable exists
    if not Path(python_exe).exists():
        logger.error(f"Python executable not found: {python_exe}")
        return {
            "status": "error",
            "message": f"Python executable not found: {python_exe}",
            "watertap_used": False
        }
    
    try:
        # Start subprocess with the worker script
        logger.info(f"Launching subprocess: {python_exe} {worker_script}")
        
        # Create subprocess with proper isolation
        process = subprocess.Popen(
            [python_exe, str(worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,  # Create new process group for clean termination
            # Use clean environment to avoid inheriting problematic variables
            env={
                **os.environ,
                'OMP_NUM_THREADS': '1',
                'MKL_NUM_THREADS': '1',
                'OPENBLAS_NUM_THREADS': '1',
                'NUMEXPR_NUM_THREADS': '1',
                'VECLIB_MAXIMUM_THREADS': '1',
                'PYTHONUNBUFFERED': '1',  # Ensure predictable I/O
                'PYTHONPATH': str(Path(__file__).parent.parent)  # Add project root
            }
        )
        
        # Send input data to subprocess
        input_json = json.dumps(input_data)
        
        # Use threading to implement timeout
        stdout_data = []
        stderr_data = []
        exception = []
        
        def communicate_thread():
            try:
                out, err = process.communicate(input=input_json, timeout=timeout_seconds)
                stdout_data.append(out)
                stderr_data.append(err)
            except subprocess.TimeoutExpired as e:
                exception.append(e)
            except Exception as e:
                exception.append(e)
        
        thread = threading.Thread(target=communicate_thread)
        thread.start()
        thread.join(timeout=timeout_seconds + 1)  # Extra second for cleanup
        
        if thread.is_alive():
            # Thread is still running, process hung
            logger.warning(f"Process still running after {timeout_seconds} seconds, terminating...")
            
            # Try graceful termination first
            process.terminate()
            time.sleep(2)
            
            if process.poll() is None:
                # Force kill if still running
                logger.warning("Process did not terminate, killing process group...")
                try:
                    # Kill entire process group on POSIX
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    # Fallback to simple kill on Windows
                    process.kill()
            
            return {
                "status": "timeout",
                "message": f"WaterTAP flowsheet exceeded {timeout_seconds} second timeout",
                "watertap_used": False,
                "suggestion": "Consider simplifying vessel configuration or using PHREEQC-only mode"
            }
        
        # Check for exceptions
        if exception:
            exc = exception[0]
            if isinstance(exc, subprocess.TimeoutExpired):
                logger.warning(f"WaterTAP flowsheet timed out after {timeout_seconds} seconds")
                process.terminate()
                return {
                    "status": "timeout",
                    "message": f"WaterTAP flowsheet exceeded {timeout_seconds} second timeout",
                    "watertap_used": False,
                    "suggestion": "Consider simplifying vessel configuration or using PHREEQC-only mode"
                }
            else:
                logger.error(f"Communication error: {exc}")
                return {
                    "status": "error",
                    "message": f"Process communication failed: {str(exc)}",
                    "watertap_used": False
                }
        
        # Get output
        stdout = stdout_data[0] if stdout_data else ""
        stderr = stderr_data[0] if stderr_data else ""
        
        # Check return code
        return_code = process.returncode
        if return_code != 0:
            logger.error(f"Worker process failed with return code {return_code}")
            logger.error(f"Stderr: {stderr}")
            return {
                "status": "error",
                "message": f"Worker process failed with return code {return_code}",
                "stderr": stderr,
                "watertap_used": False
            }
        
        # Parse JSON output with robust fallback
        try:
            result = json.loads(stdout)
            logger.info(f"WaterTAP flowsheet completed: {result.get('status')}")
            return result
        except json.JSONDecodeError as e:
            # Try to extract JSON from mixed output
            logger.warning(f"Initial JSON parse failed: {e}, attempting fallback parsing")
            
            # Find JSON boundaries
            start = stdout.find('{')
            end = stdout.rfind('}')
            
            if start != -1 and end != -1 and end > start:
                try:
                    # Extract and parse the JSON portion
                    json_str = stdout[start:end+1]
                    result = json.loads(json_str)
                    logger.info("Successfully parsed JSON using fallback method")
                    return result
                except json.JSONDecodeError:
                    pass
            
            # If all parsing fails, return error with details
            logger.error(f"Failed to parse worker output: {e}")
            logger.error(f"Stdout: {stdout[:500]}")  # Truncate for logging
            logger.error(f"Stderr: {stderr[:500]}")
            return {
                "status": "error",
                "message": f"Failed to parse worker output: {str(e)}",
                "stdout": stdout,
                "stderr": stderr,
                "watertap_used": False
            }
            
    except Exception as e:
        logger.error(f"Subprocess execution failed: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": f"Subprocess execution failed: {str(e)}",
            "traceback": traceback.format_exc(),
            "watertap_used": False
        }


def test_watertap_availability_isolated(timeout_seconds: int = 10) -> bool:
    """
    Test WaterTAP availability using subprocess.
    
    Args:
        timeout_seconds: Maximum time for smoke test
        
    Returns:
        True if WaterTAP is available and functional
    """
    logger.info("Testing WaterTAP availability via subprocess...")
    
    # Create a simple test script
    test_script = '''
import sys
import json

result = {"available": False, "failed_at": None, "error": None}

try:
    # Test imports
    import watertap
    result["watertap_import"] = True
    
    from idaes.core import FlowsheetBlock
    result["idaes_core"] = True
    
    from watertap.core.solvers import get_solver
    result["watertap_solver"] = True
    
    from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock
    result["mcas_import"] = True
    
    from pyomo.environ import ConcreteModel
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    result["flowsheet_created"] = True
    
    result["available"] = True
    
except Exception as e:
    result["error"] = str(e)
    import traceback
    result["traceback"] = traceback.format_exc()

print(json.dumps(result))
'''
    
    try:
        # Use the same interpreter as run_watertap_with_timeout so we test the right environment
        if sys.platform == "win32" or os.name == "nt":
            python_exe = r"C:\\Users\\hvksh\\mcp-servers\\venv312\\Scripts\\python.exe"
        else:
            python_exe = "/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe"

        # Run test script
        process = subprocess.Popen(
            [python_exe, "-c", test_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={
                **os.environ,
                'OMP_NUM_THREADS': '1',
                'MKL_NUM_THREADS': '1'
            }
        )
        
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        
        if process.returncode != 0:
            logger.warning(f"WaterTAP test failed with return code {process.returncode}")
            if stderr:
                logger.warning(f"Stderr: {stderr}")
            return False
        
        result = json.loads(stdout)
        if not result.get("available", False):
            logger.warning(f"WaterTAP not available: {result.get('error')}")
            if result.get("failed_at"):
                logger.warning(f"Failed at: {result['failed_at']}")
        
        return result.get("available", False)
        
    except subprocess.TimeoutExpired:
        logger.warning(f"WaterTAP test timed out after {timeout_seconds} seconds")
        process.terminate()
        return False
    except Exception as e:
        logger.warning(f"WaterTAP test exception: {e}")
        return False
