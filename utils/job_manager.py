"""
Background Job Manager for Long-Running IX Simulations

Implements the Background Job Pattern to avoid MCP STDIO blocking issues
with heavy PHREEQC/WaterTAP simulations.

Key Features:
- Async subprocess execution with immediate job_id return
- Crash recovery via disk-based job metadata
- Concurrency control with semaphore (max 3 concurrent jobs)
- Per-job output isolation to prevent file conflicts
- Progress tracking via stdout parsing
- Automatic cleanup of orphaned processes

Architecture:
    User → MCP Tool → JobManager.execute() → Returns job_id immediately
                              ↓
                    Background subprocess runs PHREEQC simulation
                              ↓
    User → get_job_status(job_id) → "running, 65% complete"
                              ↓
    User → get_job_results(job_id) → Full structured results
"""

import asyncio
import json
import logging
import os
import psutil
import signal
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class JobManager:
    """
    Singleton job manager with crash recovery and concurrency control.

    Usage:
        manager = JobManager()

        # Start job
        job = await manager.execute(
            cmd=["python", "utils/simulate_ix_cli.py", "--input", "input.json"],
            cwd="/path/to/project"
        )

        # Check status
        status = await manager.get_status(job["id"])

        # Get results
        results = await manager.get_results(job["id"])
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_concurrent_jobs: int = 3, jobs_base_dir: str = "jobs"):
        """
        Initialize job manager.

        Args:
            max_concurrent_jobs: Maximum number of simultaneous background jobs
            jobs_base_dir: Base directory for job workspaces
        """
        # Only initialize once
        if hasattr(self, '_initialized'):
            return

        self.jobs: Dict[str, dict] = {}
        self.jobs_dir = Path(jobs_base_dir)
        self.jobs_dir.mkdir(exist_ok=True)
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.max_concurrent_jobs = max_concurrent_jobs

        # Load existing jobs from disk (crash recovery)
        self._load_existing_jobs()

        # Register signal handlers for cleanup
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except Exception as e:
            # Signal handling may not work in all contexts
            logger.debug(f"Could not register signal handlers: {e}")

        self._initialized = True
        logger.info(f"JobManager initialized: max_concurrent={max_concurrent_jobs}, jobs_dir={self.jobs_dir}")

    def _load_existing_jobs(self):
        """Recover job metadata from disk, detect stale PIDs."""
        logger.info("Loading existing jobs from disk...")
        recovered = 0
        stale = 0

        for job_file in self.jobs_dir.glob("*/job.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)

                job_id = job.get("id")
                if not job_id:
                    continue

                # Check if process is still running
                pid = job.get("pid")
                if pid and self._is_process_alive(pid):
                    job["status"] = "running"
                    recovered += 1
                    logger.info(f"Recovered running job {job_id} (PID: {pid})")
                else:
                    # Only mark as failed if it was running
                    if job.get("status") == "running":
                        job["status"] = "failed"
                        job["error"] = "Process terminated (server restart or crash)"
                        job["recovered_at"] = time.time()
                        stale += 1
                        logger.warning(f"Marked stale job {job_id} as failed")

                self.jobs[job_id] = job

            except Exception as e:
                logger.error(f"Failed to load job from {job_file}: {e}")

        logger.info(f"Job recovery complete: {recovered} running, {stale} stale")

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process with given PID is still running."""
        try:
            process = psutil.Process(pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals by terminating all running jobs."""
        logger.warning(f"Received signal {signum}, terminating running jobs...")
        for job_id, job in self.jobs.items():
            if job["status"] == "running" and "pid" in job:
                try:
                    process = psutil.Process(job["pid"])
                    process.terminate()
                    logger.info(f"Terminated job {job_id} (PID: {job['pid']})")
                except Exception as e:
                    logger.error(f"Failed to terminate job {job_id}: {e}")

    async def execute(self, cmd: List[str], cwd: str = ".", env: Optional[Dict[str, str]] = None, job_id: Optional[str] = None) -> dict:
        """
        Execute command in background subprocess.

        Args:
            cmd: Command as list (e.g., ["python", "script.py", "--arg", "value"])
            cwd: Working directory for subprocess
            env: Optional environment variables
            job_id: Optional pre-determined job ID (for pre-created directories)

        Returns:
            Job metadata dict with job_id, status, command, etc.
        """
        # Generate or validate job ID
        if job_id is None:
            job_id = str(uuid.uuid4())[:8]
            job_dir = self.jobs_dir / job_id
            job_dir.mkdir(exist_ok=True)
        else:
            # Guardrail: Check for collision (caller must have created directory already)
            job_dir = self.jobs_dir / job_id
            if job_id in self.jobs:
                raise ValueError(f"Job ID {job_id} already exists in active jobs")
            if not job_dir.exists():
                raise ValueError(f"Job directory {job_dir} must exist when providing custom job_id")
            # Caller already created directory - don't create again

        # Replace {job_id} placeholder in command
        cmd_with_id = [arg.replace("{job_id}", job_id) for arg in cmd]

        # Prepare job metadata
        job = {
            "id": job_id,
            "command": cmd_with_id,
            "cwd": str(Path(cwd).absolute()),
            "status": "starting",
            "started_at": time.time(),
            "job_dir": str(job_dir.absolute()),
            "env": env or {}
        }

        logger.info(f"Starting job {job_id}: {' '.join(cmd_with_id)}")

        # Save initial metadata
        self._save_job_metadata(job)

        # Start subprocess asynchronously (acquire semaphore for concurrency control)
        async with self.semaphore:
            try:
                # Prepare environment
                proc_env = os.environ.copy()
                if env:
                    proc_env.update(env)

                # Start subprocess
                proc = await asyncio.create_subprocess_exec(
                    *cmd_with_id,
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=proc_env
                )

                job["pid"] = proc.pid
                job["status"] = "running"
                self.jobs[job_id] = job

                # Update metadata with PID
                self._save_job_metadata(job)

                logger.info(f"Job {job_id} started with PID {proc.pid}")

                # Monitor in background (fire and forget - don't await!)
                asyncio.create_task(self._monitor_job(job_id, proc))

            except Exception as e:
                job["status"] = "failed"
                job["error"] = str(e)
                job["completed_at"] = time.time()
                self._save_job_metadata(job)
                logger.error(f"Failed to start job {job_id}: {e}")

        return job

    async def _monitor_job(self, job_id: str, proc: asyncio.subprocess.Process):
        """
        Monitor job completion and capture output.

        This runs in the background and updates job status when complete.
        """
        job = self.jobs[job_id]
        job_dir = Path(job["job_dir"])

        stdout_path = job_dir / "stdout.log"
        stderr_path = job_dir / "stderr.log"

        try:
            # Drain stdout/stderr to files (prevents pipe buffer overflow)
            stdout_data, stderr_data = await proc.communicate()

            # Write to log files
            with open(stdout_path, "wb") as f:
                f.write(stdout_data)
            with open(stderr_path, "wb") as f:
                f.write(stderr_data)

            # Get exit code
            exit_code = proc.returncode

            # Update job status
            job["status"] = "completed" if exit_code == 0 else "failed"
            job["exit_code"] = exit_code
            job["completed_at"] = time.time()

            if exit_code != 0:
                # Read first 500 chars of stderr for error message
                with open(stderr_path, "r") as f:
                    job["error"] = f.read(500)

            logger.info(f"Job {job_id} {job['status']} with exit code {exit_code}")

        except Exception as e:
            job["status"] = "failed"
            job["error"] = f"Monitoring error: {str(e)}"
            job["completed_at"] = time.time()
            logger.error(f"Job {job_id} monitoring failed: {e}")

        finally:
            # Save final metadata
            self._save_job_metadata(job)

    def _save_job_metadata(self, job: dict):
        """Save job metadata to disk."""
        job_dir = Path(job["job_dir"])
        metadata_file = job_dir / "job.json"

        try:
            with open(metadata_file, "w") as f:
                json.dump(job, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata for job {job['id']}: {e}")

    async def get_status(self, job_id: str) -> dict:
        """
        Get job status with progress hints.

        Args:
            job_id: Job identifier

        Returns:
            Dict with status, progress, elapsed_time, etc.
        """
        if job_id not in self.jobs:
            return {"error": f"Job {job_id} not found"}

        job = self.jobs[job_id]

        # Calculate elapsed time
        elapsed = time.time() - job["started_at"]

        # Parse progress from stdout if available
        progress = self._parse_progress(job["job_dir"])

        # Build status response
        status_response = {
            "job_id": job_id,
            "status": job["status"],
            "elapsed_time_seconds": round(elapsed, 1),
            "started_at": job["started_at"]
        }

        if progress:
            status_response["progress"] = progress

        if job["status"] == "completed":
            status_response["completed_at"] = job.get("completed_at")
            status_response["total_time_seconds"] = round(job.get("completed_at", time.time()) - job["started_at"], 1)

        if job["status"] == "failed":
            status_response["error"] = job.get("error", "Unknown error")
            status_response["exit_code"] = job.get("exit_code")

        return status_response

    def _parse_progress(self, job_dir: str) -> Optional[dict]:
        """
        Parse progress hints from stdout.

        Looks for patterns like:
        - "Progress: 45%"
        - "BV 150/300"
        - JSON fragments with progress field
        """
        stdout_file = Path(job_dir) / "stdout.log"
        if not stdout_file.exists():
            return None

        try:
            with open(stdout_file, "r") as f:
                lines = f.readlines()

            # Look for progress patterns in last 20 lines
            for line in reversed(lines[-20:]):
                # Pattern: "Progress: 45%"
                if "progress:" in line.lower():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        try:
                            percent = int(''.join(filter(str.isdigit, parts[1])))
                            return {"percent": percent, "message": line.strip()}
                        except ValueError:
                            pass

                # Pattern: "BV 150/300"
                if "/" in line and "bv" in line.lower():
                    return {"message": line.strip()}

            # If no progress found, return last non-empty line as status
            for line in reversed(lines):
                if line.strip():
                    return {"message": line.strip()[:100]}

        except Exception as e:
            logger.debug(f"Failed to parse progress: {e}")

        return None

    async def get_results(self, job_id: str) -> dict:
        """
        Get results from completed job.

        Args:
            job_id: Job identifier

        Returns:
            Dict with job_id, status, results (parsed JSON), and log file paths
        """
        if job_id not in self.jobs:
            return {"error": f"Job {job_id} not found"}

        job = self.jobs[job_id]
        job_dir = Path(job["job_dir"])

        if job["status"] != "completed":
            return {
                "error": f"Job {job_id} not completed (status: {job['status']})",
                "job_id": job_id,
                "status": job["status"]
            }

        # Look for common result file patterns
        result_files = [
            "results.json",
            "output.json",
            "simulation_results.json"
        ]

        results = None
        result_file_found = None

        for filename in result_files:
            result_path = job_dir / filename
            if result_path.exists():
                try:
                    with open(result_path) as f:
                        results = json.load(f)
                    result_file_found = str(result_path)
                    break
                except Exception as e:
                    logger.error(f"Failed to parse {result_path}: {e}")

        response = {
            "job_id": job_id,
            "status": "completed",
            "total_time_seconds": round(job.get("completed_at", time.time()) - job["started_at"], 1),
            "stdout_file": str(job_dir / "stdout.log"),
            "stderr_file": str(job_dir / "stderr.log")
        }

        if results:
            # Exclude breakthrough_data to avoid token limit (use get_breakthrough_data tool instead)
            if "breakthrough_data" in results:
                bd_len = len(results.get("breakthrough_data", []))
                response["breakthrough_data_available"] = True
                response["breakthrough_data_points"] = bd_len
                response["breakthrough_data_note"] = "Breakthrough data excluded from response. Use get_breakthrough_data(job_id) to retrieve."
                # Create filtered copy without breakthrough_data
                results_filtered = {k: v for k, v in results.items() if k != "breakthrough_data"}
                response["results"] = results_filtered
            else:
                response["results"] = results
            response["result_file"] = result_file_found
        else:
            response["warning"] = "No result JSON file found. Check stdout/stderr logs."

        return response

    async def get_breakthrough_data(self, job_id: str) -> dict:
        """
        Get breakthrough data for a completed simulation job.

        Args:
            job_id: Job identifier

        Returns:
            Dict with breakthrough data or error
        """
        if job_id not in self.jobs:
            return {"error": f"Job {job_id} not found"}

        job = self.jobs[job_id]
        job_dir = Path(job["job_dir"])

        if job["status"] != "completed":
            return {
                "error": f"Job {job_id} not completed (status: {job['status']})",
                "job_id": job_id,
                "status": job["status"]
            }

        # Look for results with breakthrough_data
        result_path = job_dir / "results.json"
        if not result_path.exists():
            return {
                "error": "results.json not found",
                "job_id": job_id,
                "note": "Breakthrough data only available for simulation jobs"
            }

        try:
            with open(result_path) as f:
                results = json.load(f)

            if "breakthrough_data" in results:
                return {
                    "job_id": job_id,
                    "status": "completed",
                    "breakthrough_data": results["breakthrough_data"],
                    "result_file": str(result_path)
                }
            else:
                return {
                    "error": "No breakthrough_data in results",
                    "job_id": job_id
                }
        except Exception as e:
            logger.error(f"Failed to load breakthrough data from {result_path}: {e}")
            return {
                "error": f"Failed to parse results: {e}",
                "job_id": job_id
            }

    async def list_jobs(
        self,
        status_filter: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        """
        List all jobs with optional status filter and pagination.

        Args:
            status_filter: Filter by status ("running", "completed", "failed", or None for all)
            limit: Maximum number of jobs to return per page
            offset: Number of jobs to skip for pagination

        Returns:
            Dict with jobs list and pagination metadata
        """
        # First, filter all jobs by status
        filtered_jobs = []
        for job_id, job in sorted(
            self.jobs.items(),
            key=lambda x: x[1].get("started_at", 0),
            reverse=True
        ):
            if status_filter and job["status"] != status_filter:
                continue
            filtered_jobs.append((job_id, job))

        # Calculate pagination
        total_filtered = len(filtered_jobs)
        has_more = (offset + limit) < total_filtered
        next_offset = offset + limit if has_more else None

        # Apply pagination (offset and limit)
        paginated_jobs = filtered_jobs[offset:offset + limit]

        # Build response list
        jobs_list = []
        for job_id, job in paginated_jobs:
            jobs_list.append({
                "id": job_id,
                "status": job["status"],
                "command": " ".join(job["command"][:3]) + ("..." if len(job["command"]) > 3 else ""),
                "started_at": job["started_at"],
                "elapsed_time_seconds": round(time.time() - job["started_at"], 1) if job["status"] == "running" else None
            })

        return {
            "jobs": jobs_list,
            "pagination": {
                "total": total_filtered,
                "count": len(jobs_list),
                "offset": offset,
                "limit": limit,
                "has_more": has_more,
                "next_offset": next_offset
            },
            "filter": status_filter,
            "running_jobs": sum(1 for j in self.jobs.values() if j["status"] == "running"),
            "max_concurrent": self.max_concurrent_jobs
        }

    async def terminate_job(self, job_id: str) -> dict:
        """
        Terminate a running job.

        Args:
            job_id: Job identifier

        Returns:
            Dict with termination status
        """
        if job_id not in self.jobs:
            return {"error": f"Job {job_id} not found"}

        job = self.jobs[job_id]

        if job["status"] != "running":
            return {"error": f"Job {job_id} is not running (status: {job['status']})"}

        pid = job.get("pid")
        if not pid:
            return {"error": f"Job {job_id} has no PID recorded"}

        try:
            process = psutil.Process(pid)
            process.terminate()

            # Wait briefly for graceful termination
            await asyncio.sleep(1)

            if process.is_running():
                process.kill()

            job["status"] = "terminated"
            job["completed_at"] = time.time()
            self._save_job_metadata(job)

            logger.info(f"Terminated job {job_id} (PID: {pid})")

            return {
                "job_id": job_id,
                "status": "terminated",
                "message": f"Job {job_id} terminated successfully"
            }

        except psutil.NoSuchProcess:
            job["status"] = "failed"
            job["error"] = "Process no longer exists"
            self._save_job_metadata(job)
            return {"error": f"Process {pid} no longer exists"}

        except Exception as e:
            logger.error(f"Failed to terminate job {job_id}: {e}")
            return {"error": f"Failed to terminate: {str(e)}"}
