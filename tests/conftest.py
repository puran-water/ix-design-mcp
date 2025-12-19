"""
Shared pytest fixtures for ix-design-mcp test suite.

Provides:
- Common water composition fixtures
- Test markers registration
- Parametrized test data for various scenarios
"""
import pytest
from typing import Dict, Any


# =============================================================================
# Pytest Markers Registration
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests requiring PHREEQC")
    config.addinivalue_line("markers", "unit: marks unit tests (fast, no external deps)")
    config.addinivalue_line("markers", "sac: marks SAC-specific tests")
    config.addinivalue_line("markers", "wac: marks WAC-specific tests")
    config.addinivalue_line("markers", "economics: marks economics/costing tests")
    config.addinivalue_line("markers", "hydraulics: marks hydraulic calculation tests")


# =============================================================================
# Water Composition Fixtures
# =============================================================================

@pytest.fixture
def standard_brackish_water() -> Dict[str, Any]:
    """Standard brackish water composition for testing.

    Typical of brackish groundwater with moderate hardness.
    TDS ~3000 mg/L, Hardness ~300 mg/L as CaCO3.
    """
    return {
        "flow_m3_hr": 100.0,
        "ca_mg_l": 80.0,
        "mg_mg_l": 25.0,
        "na_mg_l": 850.0,
        "hco3_mg_l": 122.0,
        "pH": 7.5,
        "cl_mg_l": 1435.0,
        "so4_mg_l": 96.0,
        "temperature_celsius": 25.0
    }


@pytest.fixture
def high_hardness_water() -> Dict[str, Any]:
    """High hardness water for capacity testing.

    Hardness ~500 mg/L as CaCO3, typical of hard groundwater.
    """
    return {
        "flow_m3_hr": 100.0,
        "ca_mg_l": 150.0,
        "mg_mg_l": 50.0,
        "na_mg_l": 200.0,
        "hco3_mg_l": 300.0,
        "pH": 7.8,
        "cl_mg_l": 100.0,
        "so4_mg_l": 50.0,
        "temperature_celsius": 25.0
    }


@pytest.fixture
def low_hardness_water() -> Dict[str, Any]:
    """Low hardness water for breakthrough testing.

    Hardness ~50 mg/L as CaCO3, typical of softened water.
    """
    return {
        "flow_m3_hr": 100.0,
        "ca_mg_l": 15.0,
        "mg_mg_l": 5.0,
        "na_mg_l": 500.0,
        "hco3_mg_l": 100.0,
        "pH": 7.2,
        "cl_mg_l": 400.0,
        "so4_mg_l": 50.0,
        "temperature_celsius": 25.0
    }


@pytest.fixture
def high_alkalinity_water() -> Dict[str, Any]:
    """High alkalinity water for WAC H-form testing.

    High temporary hardness, ideal for WAC H-form treatment.
    """
    return {
        "flow_m3_hr": 100.0,
        "ca_mg_l": 100.0,
        "mg_mg_l": 30.0,
        "na_mg_l": 150.0,
        "hco3_mg_l": 400.0,  # High alkalinity
        "pH": 8.2,
        "cl_mg_l": 50.0,
        "so4_mg_l": 30.0,
        "temperature_celsius": 25.0
    }


@pytest.fixture
def seawater_composition() -> Dict[str, Any]:
    """Seawater composition for high-TDS testing.

    TDS ~35000 mg/L, requires Pitzer activity model.
    """
    return {
        "flow_m3_hr": 100.0,
        "ca_mg_l": 400.0,
        "mg_mg_l": 1300.0,
        "na_mg_l": 10700.0,
        "hco3_mg_l": 142.0,
        "pH": 8.1,
        "cl_mg_l": 19400.0,
        "so4_mg_l": 2700.0,
        "k_mg_l": 400.0,
        "temperature_celsius": 25.0
    }


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture
def sac_configuration_input(standard_brackish_water) -> Dict[str, Any]:
    """Standard SAC configuration input."""
    return {
        "water_analysis": standard_brackish_water,
        "target_hardness_mg_l_caco3": 5.0
    }


@pytest.fixture
def wac_na_configuration_input(high_hardness_water) -> Dict[str, Any]:
    """WAC Na-form configuration input."""
    return {
        "water_analysis": high_hardness_water,
        "resin_type": "WAC_Na",
        "target_hardness_mg_l_caco3": 5.0
    }


@pytest.fixture
def wac_h_configuration_input(high_alkalinity_water) -> Dict[str, Any]:
    """WAC H-form configuration input for alkalinity removal."""
    return {
        "water_analysis": high_alkalinity_water,
        "resin_type": "WAC_H",
        "target_hardness_mg_l_caco3": 5.0,
        "target_alkalinity_mg_l_caco3": 20.0
    }


# =============================================================================
# Vessel Configuration Fixtures
# =============================================================================

@pytest.fixture
def standard_vessel_config() -> Dict[str, Any]:
    """Standard vessel configuration for simulations."""
    return {
        "diameter_m": 2.0,
        "bed_depth_m": 1.5,
        "number_in_service": 1,
        "number_in_standby": 1,
        "resin_capacity_eq_l": 2.0
    }


@pytest.fixture
def large_vessel_config() -> Dict[str, Any]:
    """Large vessel configuration for high-flow applications."""
    return {
        "diameter_m": 2.4,
        "bed_depth_m": 2.0,
        "number_in_service": 2,
        "number_in_standby": 1,
        "resin_capacity_eq_l": 2.0
    }


# =============================================================================
# Pricing Fixtures
# =============================================================================

@pytest.fixture
def standard_pricing() -> Dict[str, Any]:
    """Standard pricing for economic calculations."""
    return {
        "electricity_usd_kwh": 0.07,
        "nacl_usd_kg": 0.12,
        "hcl_usd_kg": 0.20,
        "naoh_usd_kg": 0.35,
        "resin_usd_m3": 2800.0,
        "discount_rate": 0.08,
        "plant_lifetime_years": 20
    }


# =============================================================================
# Parametrized Test Data
# =============================================================================

# Water compositions for parametrized testing
WATER_COMPOSITIONS = [
    pytest.param(
        {"ca_mg_l": 80, "mg_mg_l": 25, "na_mg_l": 850, "hco3_mg_l": 122, "pH": 7.5},
        id="brackish"
    ),
    pytest.param(
        {"ca_mg_l": 150, "mg_mg_l": 50, "na_mg_l": 200, "hco3_mg_l": 300, "pH": 7.8},
        id="high_hardness"
    ),
    pytest.param(
        {"ca_mg_l": 15, "mg_mg_l": 5, "na_mg_l": 500, "hco3_mg_l": 100, "pH": 7.2},
        id="low_hardness"
    ),
]

# Target hardness values for parametrized testing
TARGET_HARDNESS_VALUES = [
    pytest.param(1.0, id="very_low"),
    pytest.param(5.0, id="standard"),
    pytest.param(17.0, id="moderate"),
    pytest.param(50.0, id="high"),
]

# Regenerant doses for parametrized testing
REGENERANT_DOSES = [
    pytest.param(80.0, id="low_dose"),
    pytest.param(100.0, id="standard_dose"),
    pytest.param(150.0, id="high_dose"),
    pytest.param(200.0, id="very_high_dose"),
]


@pytest.fixture(params=WATER_COMPOSITIONS)
def parametrized_water(request) -> Dict[str, Any]:
    """Parametrized water composition fixture."""
    base = {
        "flow_m3_hr": 100.0,
        "cl_mg_l": 1000.0,  # Will be recalculated
        "so4_mg_l": 96.0,
        "temperature_celsius": 25.0
    }
    base.update(request.param)
    return base


# =============================================================================
# Mock PHREEQC Fixtures
# =============================================================================

@pytest.fixture
def mock_phreeqc_engine():
    """Provide a mock PHREEQC engine for unit tests.

    Use this fixture for fast tests that don't require actual PHREEQC.

    Example:
        def test_breakthrough_detection(mock_phreeqc_engine):
            # Engine returns canned breakthrough data
            output, selected = mock_phreeqc_engine.run_phreeqc("")
            assert len(selected) > 0
    """
    from tests.mocks import MockPhreeqcEngine
    return MockPhreeqcEngine()


@pytest.fixture
def mock_phreeqc_early_breakthrough():
    """Mock engine configured for early breakthrough scenario.

    Returns breakthrough at 50 BV instead of 300 BV.
    """
    from tests.mocks.mock_phreeqc import MockPhreeqcEngine, MockBreakthroughData

    config = MockBreakthroughData(
        breakthrough_bv=50.0,
        max_bv=200
    )
    return MockPhreeqcEngine(breakthrough_config=config)


@pytest.fixture
def mock_phreeqc_failure():
    """Mock engine that simulates convergence failure.

    Use for testing error handling paths.
    """
    from tests.mocks.mock_phreeqc import MockPhreeqcEngineFailure
    return MockPhreeqcEngineFailure(failure_type="convergence")


@pytest.fixture
def mock_phreeqc_timeout():
    """Mock engine that simulates timeout failure."""
    from tests.mocks.mock_phreeqc import MockPhreeqcEngineFailure
    return MockPhreeqcEngineFailure(failure_type="timeout")


@pytest.fixture
def patch_phreeqc_engine(monkeypatch):
    """Fixture that patches DirectPhreeqcEngine with MockPhreeqcEngine.

    Use this to run simulation classes with mocked PHREEQC:

    Example:
        def test_sac_simulation(patch_phreeqc_engine):
            # SACSimulation will use mock engine
            sim = SACSimulation()
            assert isinstance(sim.engine, MockPhreeqcEngine)
    """
    from tests.mocks import MockPhreeqcEngine

    # Patch in base_ix_simulation
    monkeypatch.setattr(
        "tools.base_ix_simulation.DirectPhreeqcEngine",
        MockPhreeqcEngine
    )
    # Patch in sac_simulation (legacy class)
    monkeypatch.setattr(
        "tools.sac_simulation.DirectPhreeqcEngine",
        MockPhreeqcEngine
    )
    # Patch in wac_simulation
    monkeypatch.setattr(
        "tools.wac_simulation.DirectPhreeqcEngine",
        MockPhreeqcEngine
    )

    return MockPhreeqcEngine
