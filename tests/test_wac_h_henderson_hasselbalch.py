"""
Tests for WAC H-form Henderson-Hasselbalch capacity and leakage calculations.

These tests validate the empirical overlay functions that correct for the
equilibrium vs kinetic capacity discrepancy in WAC H-form resins.

Key physics:
- WAC H-form has carboxylic acid sites with pKa ~4.8
- At feed pH > pKa (e.g., 7.8), equilibrium predicts near-zero capacity
- Real systems work because protonation is kinetically trapped from acid regeneration
- The kinetic_trap_factor parameter captures this operational reality
"""
import pytest
import numpy as np
from tools.empirical_leakage_overlay import (
    EmpiricalLeakageOverlay,
    CalibrationParameters,
    EmpiricalOverlayResult,
    calculate_wac_h_leakage
)


class TestWACHEffectiveCapacity:
    """Tests for calculate_wac_h_effective_capacity method."""

    def test_basic_capacity_calculation(self):
        """Test basic capacity calculation at typical conditions."""
        overlay = EmpiricalLeakageOverlay()

        # Typical feed: pH 7.8, 200 mg/L alkalinity
        capacity, diagnostics = overlay.calculate_wac_h_effective_capacity(
            feed_ph=7.8,
            feed_alkalinity_mg_l_caco3=200.0
        )

        # Default ktf = 0.85, theoretical = 4.7 eq/L
        # Expected: 4.7 * 0.85 = 3.995 eq/L
        assert capacity == pytest.approx(3.995, rel=0.01)
        assert diagnostics['kinetic_trap_factor'] == 0.85
        assert diagnostics['effective_capacity_eq_l'] == pytest.approx(3.995, rel=0.01)

    def test_equilibrium_capacity_near_zero_at_high_ph(self):
        """Verify Henderson-Hasselbalch predicts near-zero capacity at pH 7.8."""
        overlay = EmpiricalLeakageOverlay()

        capacity, diagnostics = overlay.calculate_wac_h_effective_capacity(
            feed_ph=7.8,
            feed_alkalinity_mg_l_caco3=200.0
        )

        # At pH 7.8, pKa 4.8: fraction_protonated = 1/(1 + 10^3) ≈ 0.001
        # Equilibrium capacity ≈ 4.7 * 0.001 = 0.0047 eq/L
        eq_capacity = diagnostics['equilibrium_capacity_eq_l']
        assert eq_capacity < 0.01  # Near zero
        assert diagnostics['fraction_protonated_equilibrium'] < 0.002

    def test_kinetic_trap_factor_variations(self):
        """Test that kinetic_trap_factor scales capacity correctly."""
        base_params = CalibrationParameters()

        test_cases = [
            (0.0, 0.0),      # No kinetic trapping = no capacity
            (0.50, 2.35),    # 50% trap = 2.35 eq/L
            (0.85, 3.995),   # Default = 3.995 eq/L
            (1.0, 4.7),      # Perfect regeneration = full theoretical
        ]

        for ktf, expected_capacity in test_cases:
            params = CalibrationParameters(wac_h_kinetic_trap_factor=ktf)
            overlay = EmpiricalLeakageOverlay(params)

            capacity, _ = overlay.calculate_wac_h_effective_capacity(
                feed_ph=7.8,
                feed_alkalinity_mg_l_caco3=200.0
            )

            assert capacity == pytest.approx(expected_capacity, rel=0.01), \
                f"ktf={ktf} expected {expected_capacity}, got {capacity}"

    def test_alkalinity_tracked_but_not_capacity_limiter(self):
        """Verify alkalinity is tracked but doesn't limit capacity."""
        overlay = EmpiricalLeakageOverlay()

        # Low alkalinity case
        cap_low, diag_low = overlay.calculate_wac_h_effective_capacity(
            feed_ph=7.8,
            feed_alkalinity_mg_l_caco3=50.0
        )

        # High alkalinity case
        cap_high, diag_high = overlay.calculate_wac_h_effective_capacity(
            feed_ph=7.8,
            feed_alkalinity_mg_l_caco3=400.0
        )

        # Capacity should be the same (alkalinity doesn't limit capacity)
        assert cap_low == cap_high

        # But alkalinity values should be tracked
        assert diag_low['alkalinity_mg_l_caco3'] == 50.0
        assert diag_high['alkalinity_mg_l_caco3'] == 400.0

    def test_low_ph_increases_equilibrium_capacity(self):
        """Test that lower feed pH increases equilibrium fraction protonated."""
        overlay = EmpiricalLeakageOverlay()

        # At pH 4.8 (= pKa): 50% protonated
        _, diag_at_pka = overlay.calculate_wac_h_effective_capacity(
            feed_ph=4.8,
            feed_alkalinity_mg_l_caco3=200.0
        )

        # At pH 3.8: ~90% protonated
        _, diag_low_ph = overlay.calculate_wac_h_effective_capacity(
            feed_ph=3.8,
            feed_alkalinity_mg_l_caco3=200.0
        )

        assert diag_at_pka['fraction_protonated_equilibrium'] == pytest.approx(0.5, rel=0.01)
        assert diag_low_ph['fraction_protonated_equilibrium'] > 0.9

    def test_diagnostics_completeness(self):
        """Verify all expected diagnostics are returned."""
        overlay = EmpiricalLeakageOverlay()

        _, diagnostics = overlay.calculate_wac_h_effective_capacity(
            feed_ph=7.8,
            feed_alkalinity_mg_l_caco3=200.0
        )

        required_keys = [
            'equilibrium_capacity_eq_l',
            'fraction_protonated_equilibrium',
            'kinetic_capacity_eq_l',
            'kinetic_trap_factor',
            'alkalinity_eq_l',
            'alkalinity_mg_l_caco3',
            'effective_capacity_eq_l',
            'capacity_utilization_factor',
            'limiting_factor'
        ]

        for key in required_keys:
            assert key in diagnostics, f"Missing diagnostic key: {key}"


class TestWACHLeakage:
    """Tests for calculate_wac_h_leakage method."""

    def test_basic_leakage_calculation(self):
        """Test basic leakage calculation returns valid result."""
        overlay = EmpiricalLeakageOverlay()

        result = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=300.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0,
            temperature_c=25.0,
            phreeqc_leakage_mg_l=260.0  # PHREEQC predicts near-feed due to pKa issue
        )

        assert isinstance(result, EmpiricalOverlayResult)
        assert result.hardness_leakage_mg_l_caco3 >= 0
        assert result.hardness_leakage_mg_l_caco3 < 300.0  # Less than feed

    def test_leakage_decreases_with_higher_ktf(self):
        """Higher kinetic_trap_factor should reduce leakage."""
        results = []

        for ktf in [0.5, 0.7, 0.85, 0.95]:
            params = CalibrationParameters(wac_h_kinetic_trap_factor=ktf)
            overlay = EmpiricalLeakageOverlay(params)

            result = overlay.calculate_wac_h_leakage(
                feed_hardness_mg_l_caco3=300.0,
                feed_alkalinity_mg_l_caco3=200.0,
                feed_ph=7.8,
                feed_tds_mg_l=1500.0
            )
            results.append((ktf, result.hardness_leakage_mg_l_caco3))

        # Higher ktf should give lower leakage
        for i in range(len(results) - 1):
            assert results[i][1] > results[i+1][1], \
                f"ktf {results[i][0]} should have higher leakage than ktf {results[i+1][0]}"

    def test_leakage_increases_with_higher_feed_hardness(self):
        """Higher feed hardness should increase leakage."""
        overlay = EmpiricalLeakageOverlay()

        result_low = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=100.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        result_high = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=500.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        assert result_high.hardness_leakage_mg_l_caco3 > result_low.hardness_leakage_mg_l_caco3

    def test_zero_ktf_gives_maximum_leakage(self):
        """Zero kinetic_trap_factor should give near-feed leakage."""
        params = CalibrationParameters(wac_h_kinetic_trap_factor=0.0)
        overlay = EmpiricalLeakageOverlay(params)

        result = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=300.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        # With zero capacity, expect high leakage (scaled by 0.5 heuristic)
        # Should be around 0.5 * 300 = 150 mg/L plus floor
        assert result.hardness_leakage_mg_l_caco3 > 100.0

    def test_perfect_ktf_gives_minimal_leakage(self):
        """Perfect kinetic_trap_factor (1.0) should give low leakage."""
        params = CalibrationParameters(wac_h_kinetic_trap_factor=1.0)
        overlay = EmpiricalLeakageOverlay(params)

        result = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=300.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        # Perfect capacity utilization, leakage should be mostly just floor
        assert result.hardness_leakage_mg_l_caco3 < 30.0  # Low leakage

    def test_notes_contain_hh_diagnostics(self):
        """Verify model_notes include Henderson-Hasselbalch diagnostics."""
        overlay = EmpiricalLeakageOverlay()

        result = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=300.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        notes_text = " ".join(result.model_notes)
        assert "equilibrium capacity" in notes_text.lower()
        assert "kinetic" in notes_text.lower()


class TestWACHConvenienceFunction:
    """Tests for the module-level calculate_wac_h_leakage convenience function."""

    def test_convenience_function_with_defaults(self):
        """Test convenience function works with default parameters."""
        # Convenience function returns (leakage_float, diagnostics_dict)
        leakage, diagnostics = calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=300.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        assert isinstance(leakage, float)
        assert leakage >= 0
        assert 'effective_capacity_eq_l' in diagnostics
        assert 'kinetic_trap_factor' in diagnostics

    def test_convenience_function_custom_ktf(self):
        """Test convenience function accepts custom kinetic_trap_factor."""
        leakage, diagnostics = calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=300.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0,
            kinetic_trap_factor=0.70
        )

        assert diagnostics['kinetic_trap_factor'] == 0.70

    def test_sensitivity_analysis(self):
        """Test that sensitivity analysis produces expected pattern."""
        ktf_values = [0.5, 0.7, 0.85, 0.95]
        leakage_values = []

        for ktf in ktf_values:
            leakage, diagnostics = calculate_wac_h_leakage(
                feed_hardness_mg_l_caco3=300.0,
                feed_alkalinity_mg_l_caco3=200.0,
                feed_ph=7.8,
                feed_tds_mg_l=1500.0,
                kinetic_trap_factor=ktf
            )
            leakage_values.append(leakage)

        # Verify monotonically decreasing leakage with increasing ktf
        for i in range(len(leakage_values) - 1):
            assert leakage_values[i] > leakage_values[i+1], \
                f"Leakage should decrease: ktf {ktf_values[i]} -> {ktf_values[i+1]}"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_hardness_feed(self):
        """Test handling of zero hardness feed water."""
        overlay = EmpiricalLeakageOverlay()

        result = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=0.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        # Zero feed hardness should give minimal leakage (just floor)
        assert result.hardness_leakage_mg_l_caco3 >= 0

    def test_zero_alkalinity_feed(self):
        """Test handling of zero alkalinity feed water."""
        overlay = EmpiricalLeakageOverlay()

        # Should not raise exception
        capacity, diagnostics = overlay.calculate_wac_h_effective_capacity(
            feed_ph=7.8,
            feed_alkalinity_mg_l_caco3=0.0
        )

        # Capacity should still be determined by kinetic factor
        assert capacity > 0
        assert diagnostics['alkalinity_eq_l'] == 0.0

    def test_extreme_ph_values(self):
        """Test handling of extreme pH values."""
        overlay = EmpiricalLeakageOverlay()

        # Very low pH (acidic)
        cap_low, _ = overlay.calculate_wac_h_effective_capacity(
            feed_ph=2.0,
            feed_alkalinity_mg_l_caco3=0.0  # Can't have alkalinity at pH 2
        )

        # Very high pH (alkaline)
        cap_high, _ = overlay.calculate_wac_h_effective_capacity(
            feed_ph=10.0,
            feed_alkalinity_mg_l_caco3=200.0
        )

        # Both should give same kinetic capacity (kinetic factor dominates)
        assert cap_low == cap_high

    def test_division_by_zero_guard_theoretical_capacity(self):
        """Test that zero theoretical capacity doesn't cause division by zero."""
        params = CalibrationParameters(wac_h_theoretical_capacity_eq_l=0.0)
        overlay = EmpiricalLeakageOverlay(params)

        # Should not raise exception - test effective_capacity first
        capacity, diagnostics = overlay.calculate_wac_h_effective_capacity(
            feed_ph=7.8,
            feed_alkalinity_mg_l_caco3=200.0
        )

        # With zero theoretical capacity, effective capacity is 0
        assert capacity == 0.0
        assert diagnostics['capacity_utilization_factor'] == 0.0

        # Also test the leakage calculation
        result = overlay.calculate_wac_h_leakage(
            feed_hardness_mg_l_caco3=300.0,
            feed_alkalinity_mg_l_caco3=200.0,
            feed_ph=7.8,
            feed_tds_mg_l=1500.0
        )

        # Should return some leakage (floor + other components) without exception
        assert result.hardness_leakage_mg_l_caco3 >= 0


class TestIntegrationWithCalibrationLoader:
    """Tests verifying calibration parameters load correctly for WAC H."""

    def test_default_wac_h_parameters_exist(self):
        """Verify default WAC H parameters are set."""
        params = CalibrationParameters()

        assert hasattr(params, 'wac_h_pka')
        assert hasattr(params, 'wac_h_theoretical_capacity_eq_l')
        assert hasattr(params, 'wac_h_kinetic_trap_factor')
        assert hasattr(params, 'wac_h_ph_floor')

        assert params.wac_h_pka == pytest.approx(4.8)
        assert params.wac_h_theoretical_capacity_eq_l == pytest.approx(4.7)
        assert params.wac_h_kinetic_trap_factor == pytest.approx(0.85)
        assert params.wac_h_ph_floor == pytest.approx(4.2)
