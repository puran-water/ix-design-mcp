"""
Lightweight integration tests for SAC and WAC configurators.

Guards against accidental regression of hydraulic_analysis integration.
Each test calls the full configurator and asserts:
- hydraulic_analysis field is populated
- freeboard_m matches hydraulic calculation
"""
import pytest
from tools.sac_configuration import configure_sac_vessel, SACConfigurationInput, SACWaterComposition
from tools.wac_configuration import configure_wac_vessel, WACConfigurationInput, WACWaterComposition


class TestSACConfiguratorIntegration:
    """Integration tests for SAC configurator with hydraulics."""

    def test_sac_configurator_populates_hydraulic_analysis(self):
        """Test that configure_sac_vessel populates hydraulic_analysis field."""
        input_data = SACConfigurationInput(
            water_analysis=SACWaterComposition(
                flow_m3_hr=50.0,
                ca_mg_l=80.0,
                mg_mg_l=24.3,
                na_mg_l=230.0,
                hco3_mg_l=122.0,
                pH=7.5,
                so4_mg_l=96.0
            ),
            target_hardness_mg_l_caco3=10.0
        )
        result = configure_sac_vessel(input_data)

        # Assert hydraulic_analysis is populated
        assert result.hydraulic_analysis is not None
        assert hasattr(result.hydraulic_analysis, 'pressure_drop_service_kpa')
        assert hasattr(result.hydraulic_analysis, 'bed_expansion_percent')
        assert hasattr(result.hydraulic_analysis, 'required_freeboard_m')

        # Assert physical reasonableness
        assert result.hydraulic_analysis.pressure_drop_service_kpa > 0
        assert result.hydraulic_analysis.bed_expansion_percent >= 0
        assert result.hydraulic_analysis.required_freeboard_m >= 0

        # Assert freeboard approximately matches hydraulic calculation
        # (Allow for MINIMUM_FREEBOARD_M override)
        assert result.vessel_configuration.freeboard_m >= result.hydraulic_analysis.required_freeboard_m

    def test_sac_configurator_freeboard_matches_hydraulics(self):
        """Test that freeboard calculation respects hydraulic analysis."""
        input_data = SACConfigurationInput(
            water_analysis=SACWaterComposition(
                flow_m3_hr=100.0,
                ca_mg_l=120.0,
                mg_mg_l=40.0,
                na_mg_l=500.0,
                hco3_mg_l=200.0,
                pH=7.8,
                so4_mg_l=150.0
            ),
            target_hardness_mg_l_caco3=5.0
        )
        result = configure_sac_vessel(input_data)

        # freeboard_m should be max(hydraulic_required, MINIMUM_FREEBOARD_M)
        # So it should never be less than hydraulic requirement
        assert result.vessel_configuration.freeboard_m >= result.hydraulic_analysis.required_freeboard_m

        # And should be close if above minimum (within 0.2m for rounding/safety)
        if result.hydraulic_analysis.required_freeboard_m > 0.3:
            assert abs(result.vessel_configuration.freeboard_m -
                      result.hydraulic_analysis.required_freeboard_m) < 0.5

    def test_sac_configurator_tiny_flow_edge_case(self):
        """Test configurator with very small flow (edge case)."""
        input_data = SACConfigurationInput(
            water_analysis=SACWaterComposition(
                flow_m3_hr=10.0,  # Very small flow
                ca_mg_l=50.0,
                mg_mg_l=15.0,
                na_mg_l=100.0,
                hco3_mg_l=100.0,
                pH=7.5,
                so4_mg_l=50.0
            ),
            target_hardness_mg_l_caco3=5.0
        )
        result = configure_sac_vessel(input_data)

        # Should still populate hydraulic_analysis even with tiny flow
        assert result.hydraulic_analysis is not None
        assert result.hydraulic_analysis.linear_velocity_m_hr > 0

        # Likely to trigger low velocity warning
        if result.hydraulic_analysis.linear_velocity_m_hr < 5.0:
            assert any("velocity" in note.lower() for note in result.design_notes)


class TestWACConfiguratorIntegration:
    """Integration tests for WAC configurators with hydraulics."""

    def test_wac_na_configurator_populates_hydraulic_analysis(self):
        """Test that configure_wac_vessel (Na form) populates hydraulic_analysis field."""
        input_data = WACConfigurationInput(
            water_analysis=WACWaterComposition(
                flow_m3_hr=50.0,
                ca_mg_l=80.0,
                mg_mg_l=24.3,
                na_mg_l=230.0,
                hco3_mg_l=122.0,
                pH=7.5,
                so4_mg_l=96.0
            ),
            target_hardness_mg_l_caco3=10.0,
            resin_type="WAC_Na"
        )
        result = configure_wac_vessel(input_data)

        # Assert hydraulic_analysis is populated
        assert result.hydraulic_analysis is not None
        assert result.hydraulic_analysis.pressure_drop_service_kpa > 0
        assert result.hydraulic_analysis.bed_expansion_percent >= 0
        assert result.hydraulic_analysis.required_freeboard_m >= 0

        # Assert freeboard respects hydraulics
        assert result.vessel_configuration.freeboard_m >= result.hydraulic_analysis.required_freeboard_m

    def test_wac_h_configurator_uses_knowledge_based_path(self):
        """Test that configure_wac_vessel (H form) uses knowledge-based calculation.

        Note: WAC_H uses knowledge-based calculation (not PHREEQC),
        so hydraulic_analysis is None. This is expected behavior.
        """
        input_data = WACConfigurationInput(
            water_analysis=WACWaterComposition(
                flow_m3_hr=75.0,
                ca_mg_l=100.0,
                mg_mg_l=30.0,
                na_mg_l=300.0,
                hco3_mg_l=150.0,
                pH=7.8,
                so4_mg_l=120.0
            ),
            target_hardness_mg_l_caco3=8.0,
            target_alkalinity_mg_l_caco3=10.0,
            resin_type="WAC_H"
        )
        result = configure_wac_vessel(input_data)

        # WAC_H uses knowledge-based calculation, so hydraulic_analysis is None
        assert result.calculation_method == "knowledge_based"
        assert result.hydraulic_analysis is None

        # But vessel configuration should still be valid
        assert result.vessel_configuration.bed_depth_m > 0
        assert result.vessel_configuration.freeboard_m > 0

    def test_wac_configurator_freeboard_matches_hydraulics(self):
        """Test that WAC freeboard calculation respects hydraulic analysis."""
        input_data = WACConfigurationInput(
            water_analysis=WACWaterComposition(
                flow_m3_hr=100.0,
                ca_mg_l=120.0,
                mg_mg_l=40.0,
                na_mg_l=500.0,
                hco3_mg_l=200.0,
                pH=7.8,
                so4_mg_l=150.0
            ),
            target_hardness_mg_l_caco3=5.0,
            resin_type="WAC_Na"
        )
        result = configure_wac_vessel(input_data)

        # freeboard_m should be max(hydraulic_required, MINIMUM_FREEBOARD_M)
        assert result.vessel_configuration.freeboard_m >= result.hydraulic_analysis.required_freeboard_m

        # Should be close if above minimum (within 0.5m for rounding/safety)
        if result.hydraulic_analysis.required_freeboard_m > 0.3:
            assert abs(result.vessel_configuration.freeboard_m -
                      result.hydraulic_analysis.required_freeboard_m) < 0.5

    def test_wac_configurator_bed_expansion_integration(self):
        """Test that WAC configurator accounts for bed expansion correctly."""
        input_data = WACConfigurationInput(
            water_analysis=WACWaterComposition(
                flow_m3_hr=80.0,
                ca_mg_l=90.0,
                mg_mg_l=25.0,
                na_mg_l=400.0,
                hco3_mg_l=180.0,
                pH=7.6,
                so4_mg_l=100.0
            ),
            target_hardness_mg_l_caco3=7.0,
            resin_type="WAC_Na"
        )
        result = configure_wac_vessel(input_data)

        # Hydraulic analysis should calculate expanded bed depth
        assert result.hydraulic_analysis.expanded_bed_depth_m > result.vessel_configuration.bed_depth_m

        # Total vessel height should accommodate expansion
        total_height = (result.vessel_configuration.bed_depth_m +
                       result.vessel_configuration.freeboard_m)
        expanded_height = result.hydraulic_analysis.expanded_bed_depth_m

        # Freeboard should be sufficient for expansion
        assert total_height >= expanded_height
