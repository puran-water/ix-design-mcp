"""
Custom exception hierarchy for IX Design MCP.

Provides specific exception types for better error handling and debugging.
All exceptions inherit from IXDesignError for easy catching of IX-specific errors.
"""
from typing import Any, Dict, Optional


class IXDesignError(Exception):
    """Base exception for all IX Design MCP errors.

    All custom exceptions in this module inherit from this class,
    allowing callers to catch any IX-specific error with a single handler.

    Attributes:
        message: Human-readable error description
        details: Optional dictionary with additional context
        hint: Optional suggestion for resolution
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        hint: Optional[str] = None
    ):
        self.message = message
        self.details = details or {}
        self.hint = hint
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the full error message."""
        parts = [self.message]
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            parts.append(f"[{details_str}]")
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for MCP error responses."""
        result = {
            "error": self.__class__.__name__,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.hint:
            result["hint"] = self.hint
        return result


# =============================================================================
# PHREEQC-Related Exceptions
# =============================================================================

class PHREEQCError(IXDesignError):
    """Base exception for PHREEQC-related errors."""
    pass


class PHREEQCNotFoundError(PHREEQCError):
    """PHREEQC executable not found or not accessible."""

    def __init__(
        self,
        path: Optional[str] = None,
        hint: str = "Set PHREEQC_EXE environment variable to the PHREEQC executable path"
    ):
        super().__init__(
            message="PHREEQC executable not found",
            details={"path": path} if path else None,
            hint=hint
        )


class PHREEQCConvergenceError(PHREEQCError):
    """PHREEQC simulation failed to converge.

    This typically indicates numerical issues with the chemistry model,
    often due to extreme ion concentrations or pH values.
    """

    def __init__(
        self,
        message: str = "PHREEQC simulation failed to converge",
        step: Optional[int] = None,
        max_iterations: Optional[int] = None,
        hint: str = "Try reducing simulation complexity or adjusting input chemistry"
    ):
        details = {}
        if step is not None:
            details["step"] = step
        if max_iterations is not None:
            details["max_iterations"] = max_iterations
        super().__init__(message=message, details=details, hint=hint)


class PHREEQCTimeoutError(PHREEQCError):
    """PHREEQC simulation exceeded time limit."""

    def __init__(
        self,
        timeout_seconds: float,
        hint: str = "Increase PHREEQC_RUN_TIMEOUT_S or simplify simulation"
    ):
        super().__init__(
            message=f"PHREEQC simulation timed out after {timeout_seconds} seconds",
            details={"timeout_seconds": timeout_seconds},
            hint=hint
        )


class PHREEQCInputError(PHREEQCError):
    """Invalid input for PHREEQC simulation."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        hint: Optional[str] = None
    ):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        super().__init__(message=message, details=details, hint=hint)


# =============================================================================
# Simulation-Related Exceptions
# =============================================================================

class SimulationError(IXDesignError):
    """Base exception for simulation errors."""
    pass


class BreakthroughNotDetectedError(SimulationError):
    """Breakthrough point could not be detected in simulation results.

    This may indicate:
    - Target hardness too low (never achieved)
    - Simulation duration too short
    - Very high resin capacity
    """

    def __init__(
        self,
        target_hardness: float,
        max_bv: float,
        last_hardness: Optional[float] = None,
        hint: str = "Try increasing max_bv or adjusting target hardness"
    ):
        details = {
            "target_hardness_mg_l": target_hardness,
            "max_bv_simulated": max_bv,
        }
        if last_hardness is not None:
            details["last_hardness_mg_l"] = last_hardness
        super().__init__(
            message=f"Breakthrough not detected within {max_bv} bed volumes",
            details=details,
            hint=hint
        )


class RegenerationError(SimulationError):
    """Error during regeneration simulation."""

    def __init__(
        self,
        stage: Optional[int] = None,
        message: str = "Regeneration simulation failed",
        hint: Optional[str] = None
    ):
        details = {"stage": stage} if stage is not None else None
        super().__init__(message=message, details=details, hint=hint)


# =============================================================================
# Configuration-Related Exceptions
# =============================================================================

class ConfigurationError(IXDesignError):
    """Base exception for configuration errors."""
    pass


class ChargeBalanceError(ConfigurationError):
    """Water composition fails charge balance check.

    Ion exchange calculations require electroneutral solutions.
    This error indicates the cation-anion balance is outside acceptable tolerance.
    """

    def __init__(
        self,
        cation_meq: float,
        anion_meq: float,
        tolerance_percent: float = 5.0,
        hint: str = "Check ion concentrations or use auto-calculate for Cl-"
    ):
        imbalance_percent = abs(cation_meq - anion_meq) / max(cation_meq, anion_meq) * 100
        super().__init__(
            message=f"Charge imbalance of {imbalance_percent:.1f}% exceeds {tolerance_percent}% tolerance",
            details={
                "cation_meq_l": round(cation_meq, 3),
                "anion_meq_l": round(anion_meq, 3),
                "imbalance_percent": round(imbalance_percent, 1),
                "tolerance_percent": tolerance_percent,
            },
            hint=hint
        )


class InvalidWaterCompositionError(ConfigurationError):
    """Water composition has invalid or missing parameters."""

    def __init__(
        self,
        message: str,
        missing_fields: Optional[list] = None,
        invalid_fields: Optional[Dict[str, str]] = None,
        hint: Optional[str] = None
    ):
        details = {}
        if missing_fields:
            details["missing_fields"] = missing_fields
        if invalid_fields:
            details["invalid_fields"] = invalid_fields
        super().__init__(message=message, details=details, hint=hint)


class VesselSizingError(ConfigurationError):
    """Vessel sizing constraints cannot be satisfied."""

    def __init__(
        self,
        message: str,
        constraint: Optional[str] = None,
        required_value: Any = None,
        actual_value: Any = None,
        hint: Optional[str] = None
    ):
        details = {}
        if constraint:
            details["constraint"] = constraint
        if required_value is not None:
            details["required"] = str(required_value)
        if actual_value is not None:
            details["actual"] = str(actual_value)
        super().__init__(message=message, details=details, hint=hint)


# =============================================================================
# Job Management Exceptions
# =============================================================================

class JobError(IXDesignError):
    """Base exception for background job errors."""
    pass


class JobNotFoundError(JobError):
    """Requested job ID does not exist."""

    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job not found: {job_id}",
            details={"job_id": job_id},
            hint="Use ix_list_jobs to see available jobs"
        )


class JobNotCompletedError(JobError):
    """Job has not completed yet."""

    def __init__(self, job_id: str, status: str):
        super().__init__(
            message=f"Job {job_id} is not completed (status: {status})",
            details={"job_id": job_id, "status": status},
            hint="Use ix_get_job_status to monitor progress"
        )


class JobFailedError(JobError):
    """Job execution failed."""

    def __init__(
        self,
        job_id: str,
        error_message: Optional[str] = None,
        hint: Optional[str] = None
    ):
        super().__init__(
            message=f"Job {job_id} failed",
            details={
                "job_id": job_id,
                "error": error_message or "Unknown error"
            },
            hint=hint or "Check job logs for details"
        )


# =============================================================================
# Economics-Related Exceptions
# =============================================================================

class EconomicsError(IXDesignError):
    """Base exception for economic calculation errors."""
    pass


class InvalidPricingError(EconomicsError):
    """Invalid or missing pricing data."""

    def __init__(
        self,
        message: str,
        missing_fields: Optional[list] = None,
        hint: str = "Provide valid pricing data in USD"
    ):
        details = {"missing_fields": missing_fields} if missing_fields else None
        super().__init__(message=message, details=details, hint=hint)
