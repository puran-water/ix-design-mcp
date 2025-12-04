"""
Mock PHREEQC Engine for Unit Testing

Provides a mock implementation of DirectPhreeqcEngine that returns
realistic breakthrough data without requiring actual PHREEQC execution.

Usage:
    from tests.mocks import MockPhreeqcEngine

    # In test
    with patch('tools.base_ix_simulation.DirectPhreeqcEngine', MockPhreeqcEngine):
        sim = SACSimulation()
        # sim.engine is now MockPhreeqcEngine

    # Or for fixture-based testing
    @pytest.fixture
    def mock_engine():
        return MockPhreeqcEngine()
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MockBreakthroughData:
    """
    Configuration for mock breakthrough curve generation.

    Attributes:
        max_bv: Maximum bed volumes to simulate
        breakthrough_bv: BV at which breakthrough occurs
        target_hardness: Target hardness (mg/L as CaCO3)
        initial_hardness: Feed water hardness
        steepness: Breakthrough curve steepness (higher = sharper)
        initial_ph: Starting pH
        final_ph: Ending pH
        initial_alkalinity: Starting alkalinity (mg/L as CaCO3)
        ca_fraction: Fraction of hardness from calcium (vs magnesium)
    """
    max_bv: int = 500
    breakthrough_bv: float = 300.0
    target_hardness: float = 5.0
    initial_hardness: float = 200.0
    steepness: float = 0.05
    initial_ph: float = 7.5
    final_ph: float = 7.0
    initial_alkalinity: float = 150.0
    ca_fraction: float = 0.6

    # Ion concentrations in feed water (mg/L)
    feed_ions: Dict[str, float] = field(default_factory=lambda: {
        "Ca": 80.0,
        "Mg": 24.0,
        "Na": 200.0,
        "K": 10.0,
        "Cl": 300.0,
        "S(6)": 50.0,
        "Alkalinity": 150.0,
    })


class MockPhreeqcEngine:
    """
    Mock PHREEQC engine that returns realistic breakthrough data.

    Simulates the DirectPhreeqcEngine interface without requiring
    actual PHREEQC installation. Generates S-curve breakthrough
    profiles using logistic function.
    """

    def __init__(
        self,
        phreeqc_path: Optional[str] = None,
        keep_temp_files: bool = False,
        default_timeout_s: int = 600,
        breakthrough_config: Optional[MockBreakthroughData] = None
    ):
        """
        Initialize mock engine.

        Args:
            phreeqc_path: Ignored (for interface compatibility)
            keep_temp_files: Ignored (for interface compatibility)
            default_timeout_s: Ignored (for interface compatibility)
            breakthrough_config: Configuration for breakthrough curve
        """
        self.phreeqc_exe = phreeqc_path or "/mock/phreeqc.exe"
        self.default_database = "/mock/phreeqc.dat"
        self.keep_temp_files = keep_temp_files
        self.default_timeout_s = default_timeout_s
        self.config = breakthrough_config or MockBreakthroughData()

        # Track calls for verification
        self.run_phreeqc_calls: List[Dict[str, Any]] = []
        self.parse_selected_output_calls: List[str] = []

        logger.info("MockPhreeqcEngine initialized")

    @staticmethod
    def get_platform_path(path: str) -> str:
        """Mock platform path conversion (returns path unchanged)."""
        return path

    def _generate_breakthrough_curve(
        self,
        num_steps: int,
        bv_start: float = 0.0,
        bv_end: float = 500.0
    ) -> np.ndarray:
        """
        Generate S-curve breakthrough using logistic function.

        The breakthrough curve follows:
        C/C0 = 1 / (1 + exp(-k * (BV - BV_breakthrough)))

        Args:
            num_steps: Number of data points
            bv_start: Starting bed volumes
            bv_end: Ending bed volumes

        Returns:
            Array of C/C0 ratios (0 to 1)
        """
        bv = np.linspace(bv_start, bv_end, num_steps)
        k = self.config.steepness
        bv_bt = self.config.breakthrough_bv

        # Logistic function for breakthrough
        c_ratio = 1 / (1 + np.exp(-k * (bv - bv_bt)))

        return c_ratio

    def _generate_selected_output(self, num_steps: int = 100) -> str:
        """
        Generate mock PHREEQC selected output string.

        Creates tab-separated output matching PHREEQC format with
        columns for step, pH, pe, alkalinity, and ion concentrations.

        Args:
            num_steps: Number of data points to generate

        Returns:
            PHREEQC selected output string
        """
        # Generate breakthrough ratio
        c_ratio = self._generate_breakthrough_curve(num_steps)
        bv = np.linspace(0, self.config.max_bv, num_steps)

        # Calculate ion concentrations based on breakthrough
        ca_feed = self.config.feed_ions.get("Ca", 80.0)
        mg_feed = self.config.feed_ions.get("Mg", 24.0)
        na_feed = self.config.feed_ions.get("Na", 200.0)

        # During service: Ca/Mg removed, replaced by Na
        # As breakthrough occurs, Ca/Mg increase
        ca_effluent = c_ratio * ca_feed
        mg_effluent = c_ratio * mg_feed

        # Na initially elevated (from exchange), decreases during breakthrough
        na_baseline = na_feed
        na_from_exchange = (1 - c_ratio) * (ca_feed * 2.17 + mg_feed * 4.12) / 2  # Approximate
        na_effluent = na_baseline + na_from_exchange

        # pH slightly decreases during breakthrough (approximation)
        ph = self.config.initial_ph - c_ratio * (self.config.initial_ph - self.config.final_ph)

        # Build selected output string
        headers = ["step", "pH", "pe", "Alkalinity", "m_Ca+2", "m_Mg+2", "m_Na+", "m_K+", "m_Cl-"]
        lines = ["\t".join(headers)]

        for i in range(num_steps):
            row = [
                str(i),  # step
                f"{ph[i]:.4f}",  # pH
                f"{4.0:.4f}",  # pe (constant)
                f"{self.config.initial_alkalinity:.4f}",  # Alkalinity
                f"{ca_effluent[i] / 40.08 / 1000:.6e}",  # Ca mol/kgw
                f"{mg_effluent[i] / 24.31 / 1000:.6e}",  # Mg mol/kgw
                f"{na_effluent[i] / 22.99 / 1000:.6e}",  # Na mol/kgw
                f"{10.0 / 39.10 / 1000:.6e}",  # K mol/kgw
                f"{300.0 / 35.45 / 1000:.6e}",  # Cl mol/kgw
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    def run_phreeqc(
        self,
        input_string: str,
        database: Optional[str] = None,
        timeout_s: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Mock PHREEQC execution.

        Args:
            input_string: PHREEQC input commands (logged but not executed)
            database: Path to database file (ignored)
            timeout_s: Timeout in seconds (ignored)

        Returns:
            Tuple of (output_string, selected_output_string)
        """
        # Track the call
        self.run_phreeqc_calls.append({
            "input_string": input_string,
            "database": database,
            "timeout_s": timeout_s
        })

        logger.debug(f"MockPhreeqcEngine.run_phreeqc called (call #{len(self.run_phreeqc_calls)})")

        # Parse input to determine number of steps
        num_steps = 100  # Default
        if "TRANSPORT" in input_string.upper():
            # Try to extract shifts from input
            import re
            shifts_match = re.search(r'-shifts\s+(\d+)', input_string, re.IGNORECASE)
            if shifts_match:
                num_steps = int(shifts_match.group(1))

        # Generate mock output
        output_string = f"""
------------------------------------
Reading input data for simulation 1.
------------------------------------

	DATABASE {database or self.default_database}

    SOLUTION 0 Feed water
        temp      25
        pH        7.5
        pe        4
        redox     pe
        units     mg/l
        -water    1
    END

Beginning of transport simulation.
"""

        selected_output = self._generate_selected_output(num_steps)

        return output_string, selected_output

    def parse_selected_output(self, selected_string: str) -> List[Dict]:
        """
        Parse PHREEQC selected output into list of dictionaries.

        Args:
            selected_string: Selected output string from PHREEQC

        Returns:
            List of dictionaries with column headers as keys
        """
        self.parse_selected_output_calls.append(selected_string)

        if not selected_string.strip():
            return []

        lines = selected_string.strip().split('\n')
        if len(lines) < 2:
            return []

        # Parse headers
        headers = lines[0].split('\t')

        # Parse data rows
        result = []
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split('\t')
            row = {}
            for i, header in enumerate(headers):
                if i < len(values):
                    try:
                        # Try to convert to float
                        row[header] = float(values[i])
                    except ValueError:
                        row[header] = values[i]
            result.append(row)

        return result

    def cleanup(self):
        """Mock cleanup method (no-op)."""
        pass


class MockPhreeqcEngineFailure(MockPhreeqcEngine):
    """
    Mock engine that simulates PHREEQC failures.

    Use this to test error handling paths.
    """

    def __init__(self, failure_type: str = "convergence", **kwargs):
        """
        Initialize with specified failure type.

        Args:
            failure_type: One of "convergence", "timeout", "empty_output"
        """
        super().__init__(**kwargs)
        self.failure_type = failure_type

    def run_phreeqc(
        self,
        input_string: str,
        database: Optional[str] = None,
        timeout_s: Optional[int] = None
    ) -> Tuple[str, str]:
        """Simulate PHREEQC failure based on configured failure type."""
        self.run_phreeqc_calls.append({
            "input_string": input_string,
            "database": database,
            "timeout_s": timeout_s
        })

        if self.failure_type == "convergence":
            output = """
ERROR: Numerical method failed to converge after 200 iterations.
Convergence failure may be caused by:
  - Extreme ion concentrations
  - Invalid pH or pe values
  - Incompatible mineral phases
"""
            return output, ""

        elif self.failure_type == "timeout":
            import subprocess
            raise subprocess.TimeoutExpired("phreeqc", timeout_s or 600)

        elif self.failure_type == "empty_output":
            return "", ""

        else:
            raise RuntimeError(f"Unknown failure type: {self.failure_type}")


class MockPhreeqcEnginePartialData(MockPhreeqcEngine):
    """
    Mock engine that returns partial/incomplete breakthrough data.

    Useful for testing edge cases like:
    - Early breakthrough
    - No breakthrough detected
    - Missing columns
    """

    def __init__(self, scenario: str = "early_breakthrough", **kwargs):
        """
        Initialize with specified scenario.

        Args:
            scenario: One of "early_breakthrough", "no_breakthrough", "missing_columns"
        """
        super().__init__(**kwargs)
        self.scenario = scenario

        if scenario == "early_breakthrough":
            self.config.breakthrough_bv = 50.0  # Very early breakthrough
        elif scenario == "no_breakthrough":
            self.config.breakthrough_bv = 10000.0  # Never reaches breakthrough

    def _generate_selected_output(self, num_steps: int = 100) -> str:
        """Generate scenario-specific output."""
        if self.scenario == "missing_columns":
            # Return output with missing columns
            lines = ["step\tpH"]
            for i in range(num_steps):
                lines.append(f"{i}\t7.5")
            return "\n".join(lines)

        return super()._generate_selected_output(num_steps)


# Fixture helper functions for pytest
def create_mock_engine(
    breakthrough_bv: float = 300.0,
    initial_hardness: float = 200.0,
    target_hardness: float = 5.0,
    max_bv: int = 500
) -> MockPhreeqcEngine:
    """
    Create a mock engine with custom breakthrough parameters.

    Convenience function for creating mock engines in tests.

    Args:
        breakthrough_bv: BV at breakthrough
        initial_hardness: Feed water hardness (mg/L as CaCO3)
        target_hardness: Target effluent hardness
        max_bv: Maximum bed volumes to simulate

    Returns:
        Configured MockPhreeqcEngine instance
    """
    config = MockBreakthroughData(
        breakthrough_bv=breakthrough_bv,
        initial_hardness=initial_hardness,
        target_hardness=target_hardness,
        max_bv=max_bv
    )
    return MockPhreeqcEngine(breakthrough_config=config)
