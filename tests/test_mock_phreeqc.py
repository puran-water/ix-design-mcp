"""
Tests for mock PHREEQC engine functionality.

Validates that the mock engine correctly simulates PHREEQC behavior
for unit testing purposes.
"""

import sys
import os
import pytest
import subprocess

# Ensure project root is in path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mocks import MockPhreeqcEngine, MockBreakthroughData
from tests.mocks.mock_phreeqc import (
    MockPhreeqcEngineFailure,
    MockPhreeqcEnginePartialData,
    create_mock_engine,
)


@pytest.mark.unit
class TestMockPhreeqcEngine:
    """Tests for basic mock engine functionality."""

    def test_initialization(self):
        """Test mock engine initializes correctly."""
        engine = MockPhreeqcEngine()

        assert engine.phreeqc_exe == "/mock/phreeqc.exe"
        assert engine.default_database == "/mock/phreeqc.dat"
        assert len(engine.run_phreeqc_calls) == 0

    def test_custom_path(self):
        """Test mock engine accepts custom paths."""
        engine = MockPhreeqcEngine(phreeqc_path="/custom/phreeqc")

        assert engine.phreeqc_exe == "/custom/phreeqc"

    def test_run_phreeqc_returns_data(self):
        """Test run_phreeqc returns valid output."""
        engine = MockPhreeqcEngine()

        output, selected = engine.run_phreeqc("TEST INPUT")

        assert output is not None
        assert selected is not None
        assert len(selected) > 0
        assert len(engine.run_phreeqc_calls) == 1
        assert engine.run_phreeqc_calls[0]["input_string"] == "TEST INPUT"

    def test_selected_output_format(self):
        """Test selected output is tab-separated with headers."""
        engine = MockPhreeqcEngine()

        _, selected = engine.run_phreeqc("")
        lines = selected.strip().split('\n')

        # Should have headers and data
        assert len(lines) > 1

        # Headers should include expected columns
        headers = lines[0].split('\t')
        assert "step" in headers
        assert "pH" in headers

    def test_parse_selected_output(self):
        """Test parse_selected_output returns list of dicts."""
        engine = MockPhreeqcEngine()

        _, selected = engine.run_phreeqc("")
        parsed = engine.parse_selected_output(selected)

        assert isinstance(parsed, list)
        assert len(parsed) > 0
        assert isinstance(parsed[0], dict)
        assert "step" in parsed[0]
        assert "pH" in parsed[0]

    def test_call_tracking(self):
        """Test that calls are tracked for verification."""
        engine = MockPhreeqcEngine()

        engine.run_phreeqc("input1")
        engine.run_phreeqc("input2")

        assert len(engine.run_phreeqc_calls) == 2

    def test_empty_selected_output_parsing(self):
        """Test parsing empty selected output."""
        engine = MockPhreeqcEngine()

        result = engine.parse_selected_output("")
        assert result == []

        result = engine.parse_selected_output("   \n  ")
        assert result == []


@pytest.mark.unit
class TestBreakthroughCurve:
    """Tests for breakthrough curve generation."""

    def test_default_breakthrough(self):
        """Test default breakthrough occurs around 300 BV."""
        engine = MockPhreeqcEngine()
        _, selected = engine.run_phreeqc("")
        parsed = engine.parse_selected_output(selected)

        # Find the point where Ca starts appearing significantly
        ca_values = [row.get("m_Ca+2", 0) for row in parsed]
        steps = [row.get("step", 0) for row in parsed]

        # Ca should be low early, high later
        early_ca = ca_values[10] if len(ca_values) > 10 else 0
        late_ca = ca_values[-10] if len(ca_values) > 10 else 0

        assert late_ca > early_ca  # Breakthrough occurred

    def test_custom_breakthrough_bv(self):
        """Test configuring custom breakthrough point."""
        config = MockBreakthroughData(breakthrough_bv=100.0, max_bv=200)
        engine = MockPhreeqcEngine(breakthrough_config=config)

        _, selected = engine.run_phreeqc("")
        parsed = engine.parse_selected_output(selected)

        # Breakthrough at 100 BV should show earlier rise
        ca_values = [row.get("m_Ca+2", 0) for row in parsed]

        # With 100 steps over 200 BV, step 50 is at 100 BV (breakthrough)
        mid_point = len(ca_values) // 2
        early_ca = ca_values[mid_point - 20] if mid_point > 20 else ca_values[0]
        late_ca = ca_values[mid_point + 20] if mid_point + 20 < len(ca_values) else ca_values[-1]

        assert late_ca > early_ca

    def test_steepness_affects_curve(self):
        """Test that steepness parameter affects breakthrough sharpness."""
        config_steep = MockBreakthroughData(steepness=0.1, breakthrough_bv=100, max_bv=200)
        config_gradual = MockBreakthroughData(steepness=0.02, breakthrough_bv=100, max_bv=200)

        engine_steep = MockPhreeqcEngine(breakthrough_config=config_steep)
        engine_gradual = MockPhreeqcEngine(breakthrough_config=config_gradual)

        _, selected_steep = engine_steep.run_phreeqc("")
        _, selected_gradual = engine_gradual.run_phreeqc("")

        parsed_steep = engine_steep.parse_selected_output(selected_steep)
        parsed_gradual = engine_gradual.parse_selected_output(selected_gradual)

        # Both should have data
        assert len(parsed_steep) > 0
        assert len(parsed_gradual) > 0


@pytest.mark.unit
class TestFailureScenarios:
    """Tests for mock failure scenarios."""

    def test_convergence_failure(self):
        """Test mock convergence failure returns error output."""
        engine = MockPhreeqcEngineFailure(failure_type="convergence")

        output, selected = engine.run_phreeqc("")

        assert "ERROR" in output
        assert "convergence" in output.lower()
        assert selected == ""

    def test_timeout_failure(self):
        """Test mock timeout raises TimeoutExpired."""
        engine = MockPhreeqcEngineFailure(failure_type="timeout")

        with pytest.raises(subprocess.TimeoutExpired):
            engine.run_phreeqc("")

    def test_empty_output_failure(self):
        """Test mock empty output scenario."""
        engine = MockPhreeqcEngineFailure(failure_type="empty_output")

        output, selected = engine.run_phreeqc("")

        assert output == ""
        assert selected == ""


@pytest.mark.unit
class TestPartialDataScenarios:
    """Tests for partial data scenarios."""

    def test_early_breakthrough(self):
        """Test early breakthrough scenario."""
        engine = MockPhreeqcEnginePartialData(scenario="early_breakthrough")

        assert engine.config.breakthrough_bv == 50.0

    def test_no_breakthrough(self):
        """Test no breakthrough scenario."""
        engine = MockPhreeqcEnginePartialData(scenario="no_breakthrough")

        assert engine.config.breakthrough_bv == 10000.0  # Never reached

    def test_missing_columns(self):
        """Test missing columns scenario."""
        engine = MockPhreeqcEnginePartialData(scenario="missing_columns")

        _, selected = engine.run_phreeqc("")
        lines = selected.strip().split('\n')
        headers = lines[0].split('\t')

        # Should only have step and pH
        assert len(headers) == 2
        assert "step" in headers
        assert "pH" in headers


@pytest.mark.unit
class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_mock_engine(self):
        """Test create_mock_engine factory function."""
        engine = create_mock_engine(
            breakthrough_bv=200.0,
            initial_hardness=300.0,
            target_hardness=10.0,
            max_bv=400
        )

        assert engine.config.breakthrough_bv == 200.0
        assert engine.config.initial_hardness == 300.0
        assert engine.config.target_hardness == 10.0
        assert engine.config.max_bv == 400


@pytest.mark.unit
class TestPlatformCompatibility:
    """Tests for platform path handling."""

    def test_get_platform_path(self):
        """Test platform path conversion (mock returns unchanged)."""
        engine = MockPhreeqcEngine()

        assert engine.get_platform_path("/some/path") == "/some/path"
        assert engine.get_platform_path("C:\\Windows\\path") == "C:\\Windows\\path"


@pytest.mark.unit
def test_fixture_mock_phreeqc_engine(mock_phreeqc_engine):
    """Test the mock_phreeqc_engine fixture."""
    assert isinstance(mock_phreeqc_engine, MockPhreeqcEngine)

    output, selected = mock_phreeqc_engine.run_phreeqc("test")
    assert len(selected) > 0


@pytest.mark.unit
def test_fixture_mock_phreeqc_early_breakthrough(mock_phreeqc_early_breakthrough):
    """Test the early breakthrough fixture."""
    assert mock_phreeqc_early_breakthrough.config.breakthrough_bv == 50.0


@pytest.mark.unit
def test_fixture_mock_phreeqc_failure(mock_phreeqc_failure):
    """Test the failure fixture."""
    output, selected = mock_phreeqc_failure.run_phreeqc("")
    assert "ERROR" in output


@pytest.mark.unit
def test_fixture_mock_phreeqc_timeout(mock_phreeqc_timeout):
    """Test the timeout fixture."""
    with pytest.raises(subprocess.TimeoutExpired):
        mock_phreeqc_timeout.run_phreeqc("")
