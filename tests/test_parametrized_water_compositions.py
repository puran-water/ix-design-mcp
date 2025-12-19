"""
Parametrized tests for water composition variations.

Uses pytest parametrization to test IX simulation behavior
across multiple water compositions, target hardnesses, and
regenerant doses with a single test definition.

Markers:
    @pytest.mark.unit - Uses mock PHREEQC (fast)
    @pytest.mark.integration - Uses real PHREEQC (slow)
"""

import sys
import os
import pytest
import numpy as np

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import (
    WATER_COMPOSITIONS,
    TARGET_HARDNESS_VALUES,
    REGENERANT_DOSES,
)


# =============================================================================
# Water Composition Tests (Unit - with mock PHREEQC)
# =============================================================================

@pytest.mark.unit
class TestWaterCompositionValidation:
    """Test water composition validation across various inputs."""

    @pytest.mark.parametrize("water_comp", WATER_COMPOSITIONS)
    def test_hardness_calculation(self, water_comp):
        """Test hardness calculation for different water compositions."""
        ca_mg_l = water_comp.get("ca_mg_l", 0)
        mg_mg_l = water_comp.get("mg_mg_l", 0)

        # Calculate hardness as CaCO3
        # Ca: MW 40.08, CaCO3 equiv 100.09 -> factor 2.497
        # Mg: MW 24.31, CaCO3 equiv 100.09 -> factor 4.116
        ca_hardness = ca_mg_l * 2.497
        mg_hardness = mg_mg_l * 4.116
        total_hardness = ca_hardness + mg_hardness

        # All test waters should have positive hardness
        assert total_hardness > 0, "Water should have positive hardness"

        # Verify component contributions
        assert ca_hardness >= 0
        assert mg_hardness >= 0

    @pytest.mark.parametrize("water_comp", WATER_COMPOSITIONS)
    def test_alkalinity_present(self, water_comp):
        """Test that all waters have alkalinity defined."""
        hco3_mg_l = water_comp.get("hco3_mg_l", 0)

        # All waters should have some bicarbonate
        assert hco3_mg_l > 0, "Water should have bicarbonate alkalinity"

        # Convert to alkalinity as CaCO3
        # HCO3: MW 61.02, CaCO3 equiv 100.09 -> factor 0.82
        alkalinity_caco3 = hco3_mg_l * 0.82

        assert alkalinity_caco3 > 0

    @pytest.mark.parametrize("water_comp", WATER_COMPOSITIONS)
    def test_ph_range(self, water_comp):
        """Test that pH is in valid range for IX treatment."""
        ph = water_comp.get("pH", 7.0)

        # IX typically operates pH 6-9
        assert 5.0 < ph < 10.0, f"pH {ph} outside typical IX range"

        # Most groundwater is pH 6.5-8.5
        assert 6.0 <= ph <= 9.0


@pytest.mark.unit
class TestTargetHardnessVariations:
    """Test behavior across different target hardness values."""

    @pytest.mark.parametrize("target", TARGET_HARDNESS_VALUES)
    def test_target_hardness_positive(self, target):
        """Verify all target hardness values are positive."""
        assert target > 0, "Target hardness must be positive"

    @pytest.mark.parametrize("target", TARGET_HARDNESS_VALUES)
    def test_target_below_feed(self, target, standard_brackish_water):
        """Verify target is below feed hardness."""
        ca_mg_l = standard_brackish_water["ca_mg_l"]
        mg_mg_l = standard_brackish_water["mg_mg_l"]

        feed_hardness = ca_mg_l * 2.497 + mg_mg_l * 4.116

        # Target should be achievable (less than feed)
        assert target < feed_hardness, f"Target {target} > feed {feed_hardness}"


@pytest.mark.unit
class TestRegenerantDoseVariations:
    """Test regenerant dose parameter variations."""

    @pytest.mark.parametrize("dose", REGENERANT_DOSES)
    def test_dose_positive(self, dose):
        """Verify all regenerant doses are positive."""
        assert dose > 0, "Regenerant dose must be positive"

    @pytest.mark.parametrize("dose", REGENERANT_DOSES)
    def test_dose_in_typical_range(self, dose):
        """Verify doses are in typical industrial range."""
        # Typical NaCl doses: 60-250 g/L resin
        assert 50 <= dose <= 300, f"Dose {dose} outside typical range"


# =============================================================================
# Cross-product Parametrization
# =============================================================================

@pytest.mark.unit
class TestWaterTargetCombinations:
    """Test combinations of water compositions and targets."""

    @pytest.mark.parametrize("water_comp", WATER_COMPOSITIONS)
    @pytest.mark.parametrize("target", TARGET_HARDNESS_VALUES)
    def test_water_target_compatibility(self, water_comp, target):
        """Test all water-target combinations are physically meaningful."""
        ca_mg_l = water_comp.get("ca_mg_l", 0)
        mg_mg_l = water_comp.get("mg_mg_l", 0)

        feed_hardness = ca_mg_l * 2.497 + mg_mg_l * 4.116
        removal_fraction = 1 - (target / feed_hardness)

        # Should require some removal
        assert removal_fraction > 0, "Target already met by feed water"

        # Calculate expected capacity utilization (rough estimate)
        # Higher removal fraction = more bed volumes before breakthrough
        # This is just a sanity check


@pytest.mark.unit
class TestCapacityEstimation:
    """Test capacity estimation formulas."""

    @pytest.mark.parametrize("water_comp", WATER_COMPOSITIONS)
    def test_meq_calculation(self, water_comp):
        """Test milliequivalent calculation for hardness ions."""
        ca_mg_l = water_comp.get("ca_mg_l", 0)
        mg_mg_l = water_comp.get("mg_mg_l", 0)
        na_mg_l = water_comp.get("na_mg_l", 0)

        # Convert to meq/L
        # Ca2+: MW 40.08, valence 2 -> equiv wt 20.04
        # Mg2+: MW 24.31, valence 2 -> equiv wt 12.155
        # Na+: MW 22.99, valence 1 -> equiv wt 22.99
        ca_meq = ca_mg_l / 20.04
        mg_meq = mg_mg_l / 12.155
        na_meq = na_mg_l / 22.99

        hardness_meq = ca_meq + mg_meq

        # Verify meq calculations are positive
        assert ca_meq >= 0
        assert mg_meq >= 0
        assert hardness_meq > 0

    @pytest.mark.parametrize("dose", REGENERANT_DOSES)
    def test_regenerant_efficiency_estimate(self, dose):
        """Estimate regenerant efficiency at various doses."""
        # Typical SAC efficiency curve (approximate)
        # Lower doses = higher efficiency but lower capacity recovery
        # Higher doses = lower efficiency but better capacity recovery

        # Stoichiometric: 58.44 g NaCl per eq
        # At 100 g/L dose on 2 eq/L resin: efficiency ~70%
        stoichiometric_g_eq = 58.44

        # Estimate regenerant excess ratio
        excess_ratio = dose / (stoichiometric_g_eq * 2.0)  # Assuming 2 eq/L resin

        # Higher excess = lower efficiency
        estimated_efficiency = min(0.9, 1.0 / (0.5 + excess_ratio))

        assert 0.3 <= estimated_efficiency <= 1.0


# =============================================================================
# Mock PHREEQC Integration Tests
# =============================================================================

@pytest.mark.unit
class TestMockPHREEQCWithParameters:
    """Tests using mock PHREEQC with parametrized inputs."""

    @pytest.mark.parametrize("water_comp", WATER_COMPOSITIONS)
    def test_mock_engine_with_water(self, mock_phreeqc_engine, water_comp):
        """Test mock engine produces output for each water composition."""
        output, selected = mock_phreeqc_engine.run_phreeqc("")

        assert len(selected) > 0
        parsed = mock_phreeqc_engine.parse_selected_output(selected)

        # Should have data rows
        assert len(parsed) > 0

    def test_mock_engine_basic(self, mock_phreeqc_engine):
        """Test mock engine basic functionality."""
        output, selected = mock_phreeqc_engine.run_phreeqc("TEST")

        assert output is not None
        assert selected is not None


# =============================================================================
# Fixture Verification Tests
# =============================================================================

@pytest.mark.unit
class TestFixturesCorrect:
    """Verify that conftest fixtures provide expected data."""

    def test_standard_brackish_water(self, standard_brackish_water):
        """Verify standard brackish water fixture."""
        assert "flow_m3_hr" in standard_brackish_water
        assert "ca_mg_l" in standard_brackish_water
        assert "mg_mg_l" in standard_brackish_water
        assert "pH" in standard_brackish_water

        # Check reasonable values
        assert standard_brackish_water["flow_m3_hr"] > 0
        assert standard_brackish_water["ca_mg_l"] > 0

    def test_high_hardness_water(self, high_hardness_water):
        """Verify high hardness water fixture."""
        ca = high_hardness_water["ca_mg_l"]
        mg = high_hardness_water["mg_mg_l"]
        hardness = ca * 2.497 + mg * 4.116

        # Should be "high" hardness (>300 mg/L as CaCO3)
        assert hardness > 300

    def test_low_hardness_water(self, low_hardness_water):
        """Verify low hardness water fixture."""
        ca = low_hardness_water["ca_mg_l"]
        mg = low_hardness_water["mg_mg_l"]
        hardness = ca * 2.497 + mg * 4.116

        # Should be "low" hardness (<100 mg/L as CaCO3)
        assert hardness < 100

    def test_standard_pricing(self, standard_pricing):
        """Verify standard pricing fixture."""
        assert "electricity_usd_kwh" in standard_pricing
        assert "nacl_usd_kg" in standard_pricing
        assert "resin_usd_m3" in standard_pricing

        # Check positive values
        assert all(v > 0 for v in standard_pricing.values())

    def test_standard_vessel_config(self, standard_vessel_config):
        """Verify standard vessel config fixture."""
        assert "diameter_m" in standard_vessel_config
        assert "bed_depth_m" in standard_vessel_config

        # Verify reasonable vessel dimensions
        assert 0.5 <= standard_vessel_config["diameter_m"] <= 3.0
        assert 0.5 <= standard_vessel_config["bed_depth_m"] <= 3.0


# =============================================================================
# Edge Case Tests
# =============================================================================

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.parametrize("ca_mg_l,mg_mg_l", [
        (0.0, 50.0),  # No calcium
        (100.0, 0.0),  # No magnesium
        (0.1, 0.1),   # Very low hardness
        (500.0, 200.0),  # Very high hardness
    ])
    def test_hardness_edge_cases(self, ca_mg_l, mg_mg_l):
        """Test hardness calculation at edge cases."""
        hardness = ca_mg_l * 2.497 + mg_mg_l * 4.116

        # Should always be non-negative
        assert hardness >= 0

        # If both are zero, hardness should be zero
        if ca_mg_l == 0 and mg_mg_l == 0:
            assert hardness == 0

    @pytest.mark.parametrize("ph", [5.5, 6.0, 7.0, 8.0, 9.0, 9.5])
    def test_ph_variations(self, ph):
        """Test pH variations for IX applicability."""
        # SAC operates across wide pH range
        # WAC H-form needs pH > 4 for carbonate removal

        is_valid_for_sac = 4.0 <= ph <= 10.0
        is_valid_for_wac_h = ph > 4.0 and ph < 10.0
        is_valid_for_wac_na = 4.0 <= ph <= 10.0

        assert is_valid_for_sac
        assert is_valid_for_wac_h
        assert is_valid_for_wac_na

    @pytest.mark.parametrize("flow_m3_hr", [1.0, 10.0, 100.0, 1000.0])
    def test_flow_rate_scaling(self, flow_m3_hr):
        """Test flow rate scaling for vessel sizing."""
        # At 16 BV/hr service rate, bed volume needed:
        bed_volume_m3 = flow_m3_hr / 16.0

        # Sanity check
        assert bed_volume_m3 > 0

        # At max 25 m/hr linear velocity with 2.4m max diameter:
        max_area_m2 = np.pi * (2.4 / 2) ** 2
        max_flow_single_vessel = max_area_m2 * 25.0  # m3/hr

        # Large flows may need multiple vessels
        if flow_m3_hr > max_flow_single_vessel:
            vessels_needed = np.ceil(flow_m3_hr / max_flow_single_vessel)
            assert vessels_needed > 1
