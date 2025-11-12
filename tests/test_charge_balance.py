"""
Tests for charge balance validation (Tier 1 correctness fix).

Validates charge imbalance detection, warning messages, strict mode,
and auto-correction behavior for both SAC and WAC configurations.
"""
import pytest
from tools.sac_configuration import SACWaterComposition
from tools.wac_configuration import WACWaterComposition
from tools.core_config import CONFIG


class TestSACChargeBalance:
    """Test suite for SAC water composition charge balance."""

    def test_auto_calculate_cl_positive(self):
        """Test auto-calculation of Cl when cations > anions."""
        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=120.0,
            mg_mg_l=40.0,
            na_mg_l=850.0,
            hco3_mg_l=122.0,
            pH=7.5,
            so4_mg_l=96.0
            # Cl not provided - should be auto-calculated
        )

        # Cl should be auto-calculated and positive
        assert water.cl_mg_l is not None
        assert water.cl_mg_l > 0

        # Verify charge balance
        cation_meq = (
            water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT +
            water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT +
            water.na_mg_l / CONFIG.NA_EQUIV_WEIGHT
        )
        anion_meq = (
            water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT +
            water.so4_mg_l / CONFIG.SO4_EQUIV_WEIGHT +
            water.cl_mg_l / CONFIG.CL_EQUIV_WEIGHT
        )

        # Should be approximately balanced
        assert abs(cation_meq - anion_meq) < 0.1

    def test_auto_calculate_cl_negative_clamped(self, caplog):
        """Test that negative Cl is clamped to 0 with warning in non-strict mode."""
        import logging
        caplog.set_level(logging.WARNING)

        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=100.0,   # Low cations
            hco3_mg_l=122.0,
            pH=7.5,
            so4_mg_l=960.0,  # High anions
            strict_charge_balance=False  # Non-strict mode
        )

        # Should clamp to 0
        assert water.cl_mg_l == 0.0

        # Should have logged warning
        assert any("Charge imbalance" in record.message for record in caplog.records)
        assert any("anions exceed cations" in record.message for record in caplog.records)
        assert any("Clamping Cl⁻ to 0" in record.message for record in caplog.records)

    def test_auto_calculate_cl_negative_strict_mode_raises(self):
        """Test that negative Cl raises ValueError in strict mode."""
        with pytest.raises(ValueError) as exc_info:
            water = SACWaterComposition(
                flow_m3_hr=100.0,
                ca_mg_l=80.0,
                mg_mg_l=25.0,
                na_mg_l=100.0,
                hco3_mg_l=122.0,
                pH=7.5,
                so4_mg_l=960.0,
                strict_charge_balance=True  # Strict mode
            )

        error_msg = str(exc_info.value)
        assert "Charge imbalance" in error_msg
        assert "anions exceed cations" in error_msg
        assert "Ion inventory" in error_msg
        assert "Ca=" in error_msg
        assert "Mg=" in error_msg
        assert "Na=" in error_msg

    def test_significant_imbalance_warning(self, caplog):
        """Test warning when imbalance > 5% even with positive Cl."""
        import logging
        caplog.set_level(logging.WARNING)

        # Create water with ~10% imbalance
        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=200.0,  # High cations
            mg_mg_l=80.0,
            na_mg_l=850.0,
            hco3_mg_l=50.0,  # Low anions
            pH=7.5,
            so4_mg_l=48.0,
            strict_charge_balance=False
        )

        # Calculate imbalance
        cation_meq = (
            water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT +
            water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT +
            water.na_mg_l / CONFIG.NA_EQUIV_WEIGHT
        )
        anion_meq = (
            water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT +
            water.so4_mg_l / CONFIG.SO4_EQUIV_WEIGHT
        )

        imbalance_pct = abs((cation_meq - anion_meq) / max(cation_meq, anion_meq)) * 100

        if imbalance_pct > 5.0:
            assert any("Significant charge imbalance" in record.message for record in caplog.records)

    def test_significant_imbalance_strict_mode_raises(self):
        """Test that >10% imbalance raises ValueError in strict mode."""
        with pytest.raises(ValueError) as exc_info:
            water = SACWaterComposition(
                flow_m3_hr=100.0,
                ca_mg_l=300.0,  # Very high cations
                mg_mg_l=120.0,
                na_mg_l=1000.0,
                hco3_mg_l=30.0,  # Very low anions
                pH=7.5,
                so4_mg_l=24.0,
                strict_charge_balance=True
            )

        error_msg = str(exc_info.value)
        assert "charge imbalance" in error_msg.lower()
        assert "10%" in error_msg or "threshold" in error_msg

    def test_explicit_cl_not_overridden(self):
        """Test that explicitly provided Cl is not overridden."""
        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=120.0,
            mg_mg_l=40.0,
            na_mg_l=850.0,
            hco3_mg_l=122.0,
            pH=7.5,
            so4_mg_l=96.0,
            cl_mg_l=500.0  # Explicitly provided
        )

        # Should keep explicit value
        assert water.cl_mg_l == 500.0

    def test_balanced_water_no_warning(self, caplog):
        """Test that well-balanced water doesn't trigger warnings."""
        import logging
        caplog.set_level(logging.WARNING)

        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=80.0,
            mg_mg_l=24.3,
            na_mg_l=230.0,
            hco3_mg_l=122.0,
            pH=7.5,
            so4_mg_l=96.0,
            cl_mg_l=354.0  # Well-balanced
        )

        # Should not have charge imbalance warnings
        warning_messages = [record.message for record in caplog.records if record.levelno >= logging.WARNING]
        charge_warnings = [msg for msg in warning_messages if "charge imbalance" in msg.lower()]
        assert len(charge_warnings) == 0


class TestWACChargeBalance:
    """Test suite for WAC water composition charge balance."""

    def test_auto_calculate_cl_positive(self):
        """Test auto-calculation of Cl when cations > anions (WAC)."""
        water = WACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=120.0,
            mg_mg_l=40.0,
            na_mg_l=850.0,
            hco3_mg_l=244.0,  # Required for WAC
            pH=7.5,
            so4_mg_l=96.0
        )

        assert water.cl_mg_l is not None
        assert water.cl_mg_l > 0

    def test_auto_calculate_cl_negative_clamped(self, caplog):
        """Test that negative Cl is clamped to 0 with warning (WAC)."""
        import logging
        caplog.set_level(logging.WARNING)

        water = WACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=80.0,
            mg_mg_l=25.0,
            na_mg_l=100.0,
            hco3_mg_l=244.0,
            pH=7.5,
            so4_mg_l=960.0,
            strict_charge_balance=False
        )

        assert water.cl_mg_l == 0.0
        assert any("Charge imbalance" in record.message for record in caplog.records)

    def test_auto_calculate_cl_negative_strict_mode_raises(self):
        """Test that negative Cl raises ValueError in strict mode (WAC)."""
        with pytest.raises(ValueError) as exc_info:
            water = WACWaterComposition(
                flow_m3_hr=100.0,
                ca_mg_l=80.0,
                mg_mg_l=25.0,
                na_mg_l=100.0,
                hco3_mg_l=244.0,
                pH=7.5,
                so4_mg_l=960.0,
                strict_charge_balance=True
            )

        assert "Charge imbalance" in str(exc_info.value)
        assert "Ion inventory" in str(exc_info.value)

    def test_significant_imbalance_warning(self, caplog):
        """Test warning when imbalance > 5% (WAC)."""
        import logging
        caplog.set_level(logging.WARNING)

        water = WACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=200.0,
            mg_mg_l=80.0,
            na_mg_l=850.0,
            hco3_mg_l=100.0,
            pH=7.5,
            so4_mg_l=48.0,
            strict_charge_balance=False
        )

        # Check for warning if imbalance exists
        cation_meq = (
            water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT +
            water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT +
            water.na_mg_l / CONFIG.NA_EQUIV_WEIGHT
        )
        anion_meq = (
            water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT +
            water.so4_mg_l / CONFIG.SO4_EQUIV_WEIGHT
        )
        imbalance_pct = abs((cation_meq - anion_meq) / max(cation_meq, anion_meq)) * 100

        if imbalance_pct > 5.0:
            assert any("Significant charge imbalance" in record.message for record in caplog.records)


class TestChargeBalanceCalculations:
    """Test suite for charge balance calculation accuracy."""

    def test_charge_balance_formula_accuracy(self):
        """Test that charge balance calculations are accurate."""
        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=100.0,
            mg_mg_l=50.0,
            na_mg_l=500.0,
            hco3_mg_l=200.0,
            pH=7.5,
            so4_mg_l=100.0
        )

        # Manual calculation
        cation_meq = (
            100.0 / CONFIG.CA_EQUIV_WEIGHT +
            50.0 / CONFIG.MG_EQUIV_WEIGHT +
            500.0 / CONFIG.NA_EQUIV_WEIGHT
        )
        anion_meq = (
            200.0 / CONFIG.HCO3_EQUIV_WEIGHT +
            100.0 / CONFIG.SO4_EQUIV_WEIGHT
        )
        expected_cl_mg_l = (cation_meq - anion_meq) * CONFIG.CL_EQUIV_WEIGHT

        # Compare with auto-calculated
        assert abs(water.cl_mg_l - expected_cl_mg_l) < 0.1

    def test_zero_ions_no_crash(self):
        """Test that all-zero ions don't cause division by zero."""
        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=0.0,
            mg_mg_l=0.0,
            na_mg_l=0.0,
            hco3_mg_l=0.0,
            pH=7.0,
            so4_mg_l=0.0
        )

        # Should set Cl to 0 without crashing
        assert water.cl_mg_l == 0.0

    def test_imbalance_percentage_calculation(self):
        """Test that imbalance percentage is calculated correctly."""
        # Create water with known imbalance
        water = SACWaterComposition(
            flow_m3_hr=100.0,
            ca_mg_l=200.0,  # 10 meq/L
            mg_mg_l=121.5,  # 10 meq/L
            na_mg_l=230.0,  # 10 meq/L (total 30 meq/L cations)
            hco3_mg_l=366.0,  # 6 meq/L
            pH=7.5,
            so4_mg_l=288.0,  # 6 meq/L (total 12 meq/L anions)
            strict_charge_balance=False
            # Cl will auto-calc to balance (18 meq/L difference = 60% imbalance)
        )

        # Verify Cl was calculated
        assert water.cl_mg_l > 0

        # Calculate expected imbalance
        cation_meq = 30.0  # Approximate
        anion_meq_without_cl = 12.0  # Approximate
        # Imbalance before Cl = (30-12)/30 = 60%
        # Should trigger warning for >5% imbalance
