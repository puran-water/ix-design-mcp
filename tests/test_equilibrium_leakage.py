"""
Tests for equilibrium leakage calculator using Gaines-Thomas model.
"""
import pytest
from tools.equilibrium_leakage import EquilibriumLeakageCalculator


class TestEquilibriumLeakageCalculator:

    def test_basic_sac_leakage_calculation(self):
        """Test basic SAC equilibrium leakage calculation."""
        calc = EquilibriumLeakageCalculator()

        result = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            K_Ca_Na=5.16,
            K_Mg_Na=3.29,
            f_active=0.10
        )

        assert 'hardness_leakage_mg_l_caco3' in result
        assert 'ca_leakage_mg_l' in result
        assert 'mg_leakage_mg_l' in result
        assert result['hardness_leakage_mg_l_caco3'] >= 0
        assert result['hardness_leakage_mg_l_caco3'] < 50

    def test_high_sodium_fraction_affects_equilibrium(self):
        """
        Test that changing Na concentration affects equilibrium.

        NOTE: The direction of this effect requires PHREEQC calibration.
        Current implementation based on Gaines-Thomas with f_active parameterization.

        This test just verifies that leakage changes with Na concentration.
        The actual relationship will be calibrated against PHREEQC simulations.
        """
        calc = EquilibriumLeakageCalculator()

        result_low_na = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=100.0,
            mg_mg_l=30.0,
            na_mg_l=100.0,
            f_active=0.10
        )

        result_high_na = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=100.0,
            mg_mg_l=30.0,
            na_mg_l=1000.0,
            f_active=0.10
        )

        assert result_high_na['hardness_leakage_mg_l_caco3'] != result_low_na['hardness_leakage_mg_l_caco3']
        assert result_high_na['resin_composition']['X_Ca'] != result_low_na['resin_composition']['X_Ca']

    def test_f_active_increases_leakage(self):
        """Test that larger f_active (more active MTZ) increases leakage."""
        calc = EquilibriumLeakageCalculator()

        result_small_f = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            f_active=0.05
        )

        result_large_f = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            f_active=0.15
        )

        assert result_large_f['hardness_leakage_mg_l_caco3'] > result_small_f['hardness_leakage_mg_l_caco3']

    def test_resin_composition_sums_to_one(self):
        """Test that resin phase composition sums to 1.0."""
        calc = EquilibriumLeakageCalculator()

        result = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            f_active=0.10
        )

        X_total = (result['resin_composition']['X_Ca'] +
                   result['resin_composition']['X_Mg'] +
                   result['resin_composition']['X_Na'])

        assert abs(X_total - 1.0) < 0.01

    def test_effluent_fractions_sum_to_one(self):
        """Test that effluent phase composition sums to 1.0."""
        calc = EquilibriumLeakageCalculator()

        result = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            f_active=0.10
        )

        y_total = (result['effluent_fractions']['y_Ca'] +
                   result['effluent_fractions']['y_Mg'] +
                   result['effluent_fractions']['y_Na'])

        assert abs(y_total - 1.0) < 0.01

    def test_gaines_thomas_relationship_satisfied(self):
        """Verify that predicted compositions satisfy Gaines-Thomas equilibrium."""
        calc = EquilibriumLeakageCalculator()

        result = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            K_Ca_Na=5.16,
            K_Mg_Na=3.29,
            f_active=0.08
        )

        resin = result['resin_composition']
        effluent = result['effluent_fractions']

        K_Ca = (effluent['y_Ca'] * resin['X_Na']**2) / (effluent['y_Na']**2 * resin['X_Ca'])
        K_Mg = (effluent['y_Mg'] * resin['X_Na']**2) / (effluent['y_Na']**2 * resin['X_Mg'])

        assert K_Ca == pytest.approx(5.16, rel=1e-5)
        assert K_Mg == pytest.approx(3.29, rel=1e-5)

    def test_calibrate_f_active(self):
        """Test f_active calibration to match target leakage."""
        calc = EquilibriumLeakageCalculator()

        target_leakage = 20.0

        f_active = calc.calibrate_f_active(
            phreeqc_leakage_mg_l_caco3=target_leakage,
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0
        )

        assert 0.03 <= f_active <= 0.20

        result = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            f_active=f_active
        )

        assert abs(result['hardness_leakage_mg_l_caco3'] - target_leakage) < 0.2

    def test_calibrate_f_active_expands_bounds_for_low_target(self):
        """Calibration should handle very low targets by shrinking f_active."""
        calc = EquilibriumLeakageCalculator()

        low_target = 2.0

        f_active = calc.calibrate_f_active(
            phreeqc_leakage_mg_l_caco3=low_target,
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0
        )

        assert 1e-4 <= f_active < 0.05

        result = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=840.0,
            f_active=f_active
        )

        assert result['hardness_leakage_mg_l_caco3'] == pytest.approx(low_target, abs=0.2)

    def test_zero_hardness_feed(self):
        """Test handling of zero hardness feed water."""
        calc = EquilibriumLeakageCalculator()

        result = calc.calculate_sac_equilibrium_leakage(
            ca_mg_l=0.0,
            mg_mg_l=0.0,
            na_mg_l=1000.0,
            f_active=0.10
        )

        assert result['hardness_leakage_mg_l_caco3'] == 0.0
        assert result['ca_leakage_mg_l'] == 0.0
        assert result['mg_leakage_mg_l'] == 0.0
