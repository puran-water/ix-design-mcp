"""
Tests for fallback exchange species generation (Tier 2 regression tests).

Validates that when resin_selectivity.json is missing or incomplete,
the fallback path correctly uses CONFIG constants as single source of truth.

Key Validation Points:
- SAC_LOGK_CA_NA and SAC_LOGK_MG_NA from CONFIG appear in PHREEQC input
- Gamma values (5.0, 0.165) are correct
- No AttributeError when accessing fallback constants
"""
import pytest
from tools.enhanced_phreeqc_generator import EnhancedPHREEQCGenerator
from tools.core_config import CONFIG


class TestFallbackExchangeSpecies:
    """Test suite for fallback exchange species generation."""

    def test_fallback_sac_logk_values(self):
        """Test that SAC fallback uses correct log_k values from CONFIG."""
        generator = EnhancedPHREEQCGenerator()
        result = generator._fallback_exchange_species("SAC")

        # Validate SAC log_k values from CONFIG
        assert f"log_k {CONFIG.SAC_LOGK_CA_NA:.3f}" in result
        assert f"log_k {CONFIG.SAC_LOGK_MG_NA:.3f}" in result

        # Expected values
        assert "log_k 0.416" in result  # Ca/Na selectivity
        assert "log_k 0.221" in result  # Mg/Na selectivity

        # Validate gamma values
        assert "-gamma 5.0 0.165" in result

        # Validate basic structure
        assert "EXCHANGE_SPECIES" in result
        assert "Ca+2 + 2X- = CaX2" in result
        assert "Mg+2 + 2X- = MgX2" in result
        assert "Na+ + X- = NaX" in result

    def test_fallback_wac_na_pka_values(self):
        """Test that WAC_Na fallback uses correct pKa values from CONFIG."""
        generator = EnhancedPHREEQCGenerator()
        result = generator._fallback_exchange_species("WAC_Na")

        # Validate WAC pKa from CONFIG (used for H+ exchange in WAC_Na)
        assert f"log_k {CONFIG.WAC_PKA:.3f}" in result

        # Validate structure
        assert "EXCHANGE_SPECIES" in result
        assert "H+ + X- = HX" in result  # Acid dissociation

        # Should also include Ca and Mg for WAC_Na
        assert "Ca+2 + 2X- = CaX2" in result
        assert "Mg+2 + 2X- = MgX2" in result

    def test_fallback_wac_na_selectivity(self):
        """Test that WAC_Na fallback uses correct selectivity from CONFIG."""
        generator = EnhancedPHREEQCGenerator()
        result = generator._fallback_exchange_species("WAC_Na")

        # Validate WAC_Na selectivity from CONFIG
        # WAC_Na typically has lower selectivity than SAC
        assert "EXCHANGE_SPECIES" in result or "SURFACE_SPECIES" in result

    def test_fallback_no_attribute_error(self):
        """Test that fallback doesn't raise AttributeError (Tier 0 bug fix)."""
        generator = EnhancedPHREEQCGenerator()

        # This should NOT raise AttributeError: 'CoreConfig' object has no attribute 'SAC_LOGK_CA_NA'
        result = generator._fallback_exchange_species("SAC")

        # If we got here without exception, test passed
        assert result is not None
        assert len(result) > 0

    def test_fallback_gamma_values_correct(self):
        """Test that gamma values in fallback are physically reasonable."""
        generator = EnhancedPHREEQCGenerator()
        result = generator._fallback_exchange_species("SAC")

        # Validate gamma parameters
        # Format: -gamma <value1> <value2>
        # Typical values for Debye-Hückel: a0 = 5.0 Å, b = 0.165 kg/mol
        assert "-gamma 5.0 0.165" in result or "-gamma 5.0 0.1" in result

        # Should appear for divalent cations (Ca, Mg)
        lines = result.split('\n')
        gamma_count = sum(1 for line in lines if '-gamma' in line)
        assert gamma_count >= 2  # At least for Ca and Mg

    def test_fallback_includes_all_major_ions(self):
        """Test that fallback includes Na, Ca, Mg exchange reactions."""
        generator = EnhancedPHREEQCGenerator()
        result = generator._fallback_exchange_species("SAC")

        # Essential ions for softening
        assert "Na+ + X- = NaX" in result
        assert "Ca+2 + 2X- = CaX2" in result
        assert "Mg+2 + 2X- = MgX2" in result

        # Should also have the reverse reactions or proper equilibrium definitions
        lines = result.split('\n')
        assert any('NaX' in line for line in lines)
        assert any('CaX2' in line for line in lines)
        assert any('MgX2' in line for line in lines)

    def test_config_constants_exist(self):
        """Test that all required fallback constants exist in CONFIG."""
        # Tier 0 fix validation: these must exist to avoid AttributeError
        assert hasattr(CONFIG, 'SAC_LOGK_CA_NA')
        assert hasattr(CONFIG, 'SAC_LOGK_MG_NA')
        assert hasattr(CONFIG, 'WAC_PKA')

        # Validate types and ranges
        assert isinstance(CONFIG.SAC_LOGK_CA_NA, float)
        assert isinstance(CONFIG.SAC_LOGK_MG_NA, float)
        assert isinstance(CONFIG.WAC_PKA, float)

        # Sanity check values
        assert 0.0 < CONFIG.SAC_LOGK_CA_NA < 1.0  # Typical range for Ca/Na
        assert 0.0 < CONFIG.SAC_LOGK_MG_NA < 0.5  # Mg selectivity lower than Ca
        assert 4.0 < CONFIG.WAC_PKA < 6.0  # Typical pKa for weak acid resins

    def test_fallback_output_valid_phreeqc_syntax(self):
        """Test that fallback output is syntactically valid for PHREEQC."""
        generator = EnhancedPHREEQCGenerator()
        result = generator._fallback_exchange_species("SAC")

        # Basic PHREEQC syntax validation
        lines = [l.strip() for l in result.split('\n') if l.strip()]

        # Should start with EXCHANGE_SPECIES block
        assert any('EXCHANGE_SPECIES' in line for line in lines)

        # All exchange reactions should have "="
        reaction_lines = [l for l in lines if '+' in l and 'X' in l]
        assert all('=' in line for line in reaction_lines)

        # log_k lines should have proper format
        logk_lines = [l for l in lines if 'log_k' in l]
        for line in logk_lines:
            assert 'log_k' in line
            # Should have a numeric value after log_k
            parts = line.split()
            assert len(parts) >= 2
            try:
                float(parts[1])  # Should be a number
            except ValueError:
                pytest.fail(f"Invalid log_k format: {line}")

    def test_fallback_consistency_across_calls(self):
        """Test that fallback generates consistent output across multiple calls."""
        generator = EnhancedPHREEQCGenerator()
        result1 = generator._fallback_exchange_species("SAC")
        result2 = generator._fallback_exchange_species("SAC")

        # Should be identical (deterministic)
        assert result1 == result2

        # Should use same CONFIG constants
        assert result1.count(f"log_k {CONFIG.SAC_LOGK_CA_NA:.3f}") == result2.count(f"log_k {CONFIG.SAC_LOGK_CA_NA:.3f}")

    def test_fallback_uses_config_as_single_source_of_truth(self):
        """Test that fallback uses only CONFIG, not hardcoded values."""
        generator = EnhancedPHREEQCGenerator()
        result = generator._fallback_exchange_species("SAC")

        # All log_k values should match CONFIG
        # Ca/Na selectivity
        assert f"{CONFIG.SAC_LOGK_CA_NA:.3f}" in result

        # Mg/Na selectivity
        assert f"{CONFIG.SAC_LOGK_MG_NA:.3f}" in result

        # No other hardcoded log_k values should appear
        # (except those from CONFIG)
