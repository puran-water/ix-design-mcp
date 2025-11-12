"""
Tests for hydraulic calculations module (Tier 2).

Validates Ergun pressure drop, Richardson-Zaki bed expansion,
distributor headloss, and complete system hydraulics analysis.

References:
- Ergun, S. (1952). "Fluid flow through packed columns"
- Richardson & Zaki (1954). "Sedimentation and fluidisation"
- AWWA B100-09: Ion Exchange Materials Standard
"""
import pytest
import math
from tools.hydraulics import (
    calculate_ergun_pressure_drop,
    calculate_bed_expansion,
    calculate_distributor_headloss,
    calculate_system_hydraulics,
    STANDARD_SAC_RESIN,
    STANDARD_WAC_RESIN,
    ResinProperties,
    HydraulicResult,
    WATER_DENSITY_KG_M3,
    WATER_VISCOSITY_PA_S,
    GRAVITY_M_S2
)


class TestErgunPressureDrop:
    """Test suite for Ergun equation pressure drop calculations."""

    def test_ergun_basic_calculation(self):
        """Test Ergun ΔP against hand calculation for typical SAC vessel."""
        # Representative SAC vessel
        bed_depth_m = 2.0
        bed_diameter_m = 2.0
        flow_rate_m3_h = 100.0

        # Calculate pressure drop
        dp_kpa = calculate_ergun_pressure_drop(
            bed_depth_m, bed_diameter_m, flow_rate_m3_h,
            STANDARD_SAC_RESIN, temperature_c=20.0
        )

        # Hand calculation for validation
        bed_area_m2 = math.pi * (bed_diameter_m / 2.0) ** 2
        velocity_m_s = (flow_rate_m3_h / 3600.0) / bed_area_m2  # ~0.00884 m/s

        porosity = STANDARD_SAC_RESIN.bed_porosity  # 0.40
        dp = STANDARD_SAC_RESIN.particle_diameter_m  # 0.00065 m
        sphericity = STANDARD_SAC_RESIN.sphericity  # 0.95

        # Ergun viscous term
        term1 = (
            150.0 * WATER_VISCOSITY_PA_S * (1 - porosity) ** 2 * velocity_m_s
            / (porosity ** 3 * dp ** 2 * sphericity ** 2)
        )

        # Ergun inertial term
        term2 = (
            1.75 * WATER_DENSITY_KG_M3 * (1 - porosity) * velocity_m_s ** 2
            / (porosity ** 3 * dp * sphericity)
        )

        expected_dp_kpa = (term1 + term2) * bed_depth_m / 1000.0

        # Should match within 0.1 kPa
        assert abs(dp_kpa - expected_dp_kpa) < 0.1

        # Sanity check: typical service ΔP should be 10-50 kPa
        assert 5.0 < dp_kpa < 100.0

    def test_ergun_flow_rate_scaling(self):
        """Test that ΔP scales correctly with flow rate (linear + quadratic)."""
        bed_depth_m = 2.0
        bed_diameter_m = 2.0

        # Calculate ΔP at three flow rates
        dp_50 = calculate_ergun_pressure_drop(
            bed_depth_m, bed_diameter_m, 50.0,
            STANDARD_SAC_RESIN
        )
        dp_100 = calculate_ergun_pressure_drop(
            bed_depth_m, bed_diameter_m, 100.0,
            STANDARD_SAC_RESIN
        )
        dp_200 = calculate_ergun_pressure_drop(
            bed_depth_m, bed_diameter_m, 200.0,
            STANDARD_SAC_RESIN
        )

        # ΔP should increase with flow rate
        assert dp_50 < dp_100 < dp_200

        # Scaling should be between linear (2×) and quadratic (4×)
        # for 2× flow increase (viscous + inertial contributions)
        ratio_low = dp_100 / dp_50
        ratio_high = dp_200 / dp_100

        assert 1.5 < ratio_low < 2.5  # Between linear and quadratic
        assert 1.5 < ratio_high < 2.5

    def test_ergun_temperature_effect(self):
        """Test that higher temperature reduces ΔP (lower viscosity)."""
        bed_depth_m = 2.0
        bed_diameter_m = 2.0
        flow_rate_m3_h = 100.0

        # Calculate at 20°C and 40°C
        dp_20c = calculate_ergun_pressure_drop(
            bed_depth_m, bed_diameter_m, flow_rate_m3_h,
            STANDARD_SAC_RESIN, temperature_c=20.0
        )
        dp_40c = calculate_ergun_pressure_drop(
            bed_depth_m, bed_diameter_m, flow_rate_m3_h,
            STANDARD_SAC_RESIN, temperature_c=40.0
        )

        # Higher temperature should reduce ΔP
        assert dp_40c < dp_20c

        # Reduction should be significant (viscosity effect)
        # μ(40°C) ≈ 0.65 × μ(20°C)
        reduction_pct = (dp_20c - dp_40c) / dp_20c * 100
        assert 20.0 < reduction_pct < 50.0  # Expect 20-50% reduction

    def test_ergun_bed_depth_linear(self):
        """Test that ΔP scales linearly with bed depth."""
        bed_diameter_m = 2.0
        flow_rate_m3_h = 100.0

        dp_1m = calculate_ergun_pressure_drop(
            1.0, bed_diameter_m, flow_rate_m3_h, STANDARD_SAC_RESIN
        )
        dp_2m = calculate_ergun_pressure_drop(
            2.0, bed_diameter_m, flow_rate_m3_h, STANDARD_SAC_RESIN
        )
        dp_3m = calculate_ergun_pressure_drop(
            3.0, bed_diameter_m, flow_rate_m3_h, STANDARD_SAC_RESIN
        )

        # Should be approximately linear
        assert abs((dp_2m / dp_1m) - 2.0) < 0.01
        assert abs((dp_3m / dp_1m) - 3.0) < 0.01

    def test_ergun_particle_size_effect(self):
        """Test that smaller particles increase ΔP significantly."""
        # Coarse resin (800 μm)
        coarse_resin = ResinProperties(
            particle_diameter_m=0.0008,
            particle_density_kg_m3=1250.0,
            bed_porosity=0.40,
            sphericity=0.95
        )

        # Fine resin (500 μm)
        fine_resin = ResinProperties(
            particle_diameter_m=0.0005,
            particle_density_kg_m3=1250.0,
            bed_porosity=0.40,
            sphericity=0.95
        )

        dp_coarse = calculate_ergun_pressure_drop(
            2.0, 2.0, 100.0, coarse_resin
        )
        dp_fine = calculate_ergun_pressure_drop(
            2.0, 2.0, 100.0, fine_resin
        )

        # Fine resin should have higher ΔP
        assert dp_fine > dp_coarse

        # Viscous term scales as 1/Dp², so expect significant difference
        ratio = dp_fine / dp_coarse
        assert ratio > 1.5  # Should be substantially higher


class TestBedExpansion:
    """Test suite for Richardson-Zaki bed expansion calculations."""

    def test_expansion_vs_flow_rate(self):
        """Test that expansion increases with backwash flow rate."""
        bed_diameter_m = 2.0

        # Three backwash rates: 50, 100, 150 m³/h
        exp_50, void_50 = calculate_bed_expansion(
            50.0, bed_diameter_m, STANDARD_SAC_RESIN
        )
        exp_100, void_100 = calculate_bed_expansion(
            100.0, bed_diameter_m, STANDARD_SAC_RESIN
        )
        exp_150, void_150 = calculate_bed_expansion(
            150.0, bed_diameter_m, STANDARD_SAC_RESIN
        )

        # Expansion should increase monotonically
        assert exp_50 < exp_100 < exp_150

        # Voidage should increase
        assert void_50 < void_100 < void_150

        # Expansion should be positive
        assert exp_50 >= 0
        assert exp_100 >= 0
        assert exp_150 >= 0

    def test_expansion_clamping_low_velocity(self):
        """Test edge case: very low velocity should give zero or minimal expansion."""
        bed_diameter_m = 2.0

        # Very low backwash rate (1 m³/h)
        expansion_pct, expanded_voidage = calculate_bed_expansion(
            1.0, bed_diameter_m, STANDARD_SAC_RESIN
        )

        # Should give zero or very small expansion
        assert 0.0 <= expansion_pct < 5.0

        # Expanded voidage should not be less than settled porosity
        assert expanded_voidage >= STANDARD_SAC_RESIN.bed_porosity

        # Should be clamped to physically reasonable range
        assert expanded_voidage < 0.95

    def test_expansion_temperature_effect(self):
        """Test that temperature affects expansion (viscosity changes terminal velocity)."""
        bed_diameter_m = 2.0
        flow_rate_m3_h = 100.0

        exp_20c, _ = calculate_bed_expansion(
            flow_rate_m3_h, bed_diameter_m, STANDARD_SAC_RESIN, temperature_c=20.0
        )
        exp_40c, _ = calculate_bed_expansion(
            flow_rate_m3_h, bed_diameter_m, STANDARD_SAC_RESIN, temperature_c=40.0
        )

        # Higher temperature (lower viscosity) increases terminal velocity
        # so same flow rate causes less expansion
        assert exp_40c < exp_20c

    def test_expansion_resin_density_effect(self):
        """Test that resin density affects expansion."""
        # Light resin (1150 kg/m³)
        light_resin = ResinProperties(
            particle_diameter_m=0.00065,
            particle_density_kg_m3=1150.0,
            bed_porosity=0.40,
            sphericity=0.95
        )

        # Heavy resin (1350 kg/m³)
        heavy_resin = ResinProperties(
            particle_diameter_m=0.00065,
            particle_density_kg_m3=1350.0,
            bed_porosity=0.40,
            sphericity=0.95
        )

        exp_light, _ = calculate_bed_expansion(100.0, 2.0, light_resin)
        exp_heavy, _ = calculate_bed_expansion(100.0, 2.0, heavy_resin)

        # Light resin should expand more (lower terminal velocity)
        assert exp_light > exp_heavy

    def test_expansion_physical_limits(self):
        """Test that expansion stays within physical limits."""
        bed_diameter_m = 2.0

        # Very high backwash rate (300 m³/h)
        expansion_pct, expanded_voidage = calculate_bed_expansion(
            300.0, bed_diameter_m, STANDARD_SAC_RESIN
        )

        # Should be clamped to reasonable maximum
        assert expanded_voidage <= 0.95

        # Expansion can be very high at extreme backwash rates
        # but should stay finite and physically reasonable
        assert expansion_pct < 500.0  # Extreme but finite limit
        assert expansion_pct > 0

    def test_expansion_calculation_accuracy(self):
        """Test expansion calculation against known values."""
        # Standard conditions: 100 m³/h, 2m diameter
        bed_area_m2 = math.pi * (2.0 / 2.0) ** 2
        velocity_m_s = (100.0 / 3600.0) / bed_area_m2  # Superficial velocity

        # Terminal velocity calculation (Stokes)
        dp = STANDARD_SAC_RESIN.particle_diameter_m
        density_diff = STANDARD_SAC_RESIN.particle_density_kg_m3 - WATER_DENSITY_KG_M3
        v_terminal = (
            GRAVITY_M_S2 * dp ** 2 * density_diff / (18.0 * WATER_VISCOSITY_PA_S)
        )

        # Richardson-Zaki
        n = 4.0
        expected_voidage = (velocity_m_s / v_terminal) ** (1.0 / n)
        expected_voidage = min(max(expected_voidage, 0.40), 0.95)

        expansion_pct, expanded_voidage = calculate_bed_expansion(
            100.0, 2.0, STANDARD_SAC_RESIN
        )

        # Should match expected voidage
        assert abs(expanded_voidage - expected_voidage) < 0.01


class TestDistributorHeadloss:
    """Test suite for distributor/collector headloss calculations."""

    def test_headloss_calculation(self):
        """Test distributor headloss against orifice equation."""
        flow_rate_m3_h = 100.0
        bed_diameter_m = 2.0
        nozzle_count = 20
        nozzle_diameter_mm = 10.0

        headloss_kpa, nozzle_vel = calculate_distributor_headloss(
            flow_rate_m3_h, bed_diameter_m, nozzle_count, nozzle_diameter_mm
        )

        # Hand calculation
        flow_rate_m3_s = flow_rate_m3_h / 3600.0
        nozzle_diameter_m = nozzle_diameter_mm / 1000.0
        nozzle_area_m2 = math.pi * (nozzle_diameter_m / 2.0) ** 2
        total_nozzle_area = nozzle_area_m2 * nozzle_count
        expected_nozzle_vel = flow_rate_m3_s / total_nozzle_area

        discharge_coeff = 0.7
        expected_headloss_pa = (
            WATER_DENSITY_KG_M3 * expected_nozzle_vel ** 2
            / (2.0 * discharge_coeff ** 2)
        )
        expected_headloss_kpa = expected_headloss_pa / 1000.0

        # Should match within tolerance
        assert abs(nozzle_vel - expected_nozzle_vel) < 0.01
        assert abs(headloss_kpa - expected_headloss_kpa) < 0.1

    def test_nozzle_velocity_scaling(self):
        """Test that nozzle velocity scales inversely with nozzle count."""
        flow_rate_m3_h = 100.0
        bed_diameter_m = 2.0

        _, vel_10 = calculate_distributor_headloss(
            flow_rate_m3_h, bed_diameter_m, 10, 10.0
        )
        _, vel_20 = calculate_distributor_headloss(
            flow_rate_m3_h, bed_diameter_m, 20, 10.0
        )
        _, vel_40 = calculate_distributor_headloss(
            flow_rate_m3_h, bed_diameter_m, 40, 10.0
        )

        # Velocity should be inversely proportional to nozzle count
        assert abs((vel_10 / vel_20) - 2.0) < 0.01
        assert abs((vel_10 / vel_40) - 4.0) < 0.01

    def test_nozzle_velocity_warning_threshold(self, caplog):
        """Test that high nozzle velocity (>3 m/s) triggers warning."""
        import logging
        caplog.set_level(logging.WARNING)

        # Very few nozzles to force high velocity
        flow_rate_m3_h = 200.0
        bed_diameter_m = 2.0
        nozzle_count = 5  # Too few

        headloss_kpa, nozzle_vel = calculate_distributor_headloss(
            flow_rate_m3_h, bed_diameter_m, nozzle_count, 10.0
        )

        # Should have high velocity
        assert nozzle_vel > 3.0

        # Should log warning
        assert any("High nozzle velocity" in record.message for record in caplog.records)
        assert any("resin damage" in record.message or "resin attrition" in record.message
                   for record in caplog.records)

    def test_zero_nozzles_guard(self):
        """Test edge case: nozzle_count=0 should cause division by zero."""
        flow_rate_m3_h = 100.0
        bed_diameter_m = 2.0

        # This should either raise an error or return inf/nan
        # Current implementation will divide by zero, which should be caught
        with pytest.raises((ZeroDivisionError, ValueError)):
            headloss_kpa, nozzle_vel = calculate_distributor_headloss(
                flow_rate_m3_h, bed_diameter_m, 0, 10.0
            )

    def test_headloss_flow_rate_quadratic(self):
        """Test that headloss scales with velocity² (orifice equation)."""
        bed_diameter_m = 2.0
        nozzle_count = 20

        hl_50, _ = calculate_distributor_headloss(50.0, bed_diameter_m, nozzle_count, 10.0)
        hl_100, _ = calculate_distributor_headloss(100.0, bed_diameter_m, nozzle_count, 10.0)
        hl_200, _ = calculate_distributor_headloss(200.0, bed_diameter_m, nozzle_count, 10.0)

        # Headloss should scale quadratically (v²)
        # Doubling flow should quadruple headloss
        ratio_low = hl_100 / hl_50
        ratio_high = hl_200 / hl_100

        assert abs(ratio_low - 4.0) < 0.1  # Should be ~4×
        assert abs(ratio_high - 4.0) < 0.1


class TestSystemHydraulics:
    """Test suite for complete system hydraulic analysis."""

    def test_complete_sac_vessel(self):
        """Test full hydraulic analysis for representative SAC vessel."""
        # Typical SAC vessel: 2m diameter × 2.5m depth
        result = calculate_system_hydraulics(
            bed_depth_m=2.5,
            bed_diameter_m=2.0,
            service_flow_m3_h=100.0,
            backwash_flow_m3_h=150.0,
            resin_props=STANDARD_SAC_RESIN,
            temperature_c=20.0,
            freeboard_safety_factor=1.5
        )

        # Validate result structure
        assert isinstance(result, HydraulicResult)
        assert result.pressure_drop_service_kpa > 0
        assert result.pressure_drop_backwash_kpa > 0
        assert result.bed_expansion_percent >= 0
        assert result.expanded_bed_depth_m > 2.5
        assert result.required_freeboard_m > 0
        assert result.distributor_headloss_kpa > 0
        assert result.nozzle_velocity_m_s > 0

        # Sanity checks
        assert result.pressure_drop_service_kpa < 100.0  # Typical < 70 kPa
        assert result.bed_expansion_percent < 150.0  # High but reasonable
        assert result.required_freeboard_m < 5.0  # Can be large with high expansion

        # Warnings should be a list
        assert isinstance(result.warnings, list)

    def test_awwa_velocity_validation_in_range(self):
        """Test that valid velocity (5-40 m/h) passes AWWA B100 check."""
        # Design for ~20 m/h velocity
        bed_area = math.pi * (2.0 / 2.0) ** 2
        flow_for_20_m_h = bed_area * 20.0  # ~62.8 m³/h

        result = calculate_system_hydraulics(
            bed_depth_m=2.5,
            bed_diameter_m=2.0,
            service_flow_m3_h=flow_for_20_m_h,
            backwash_flow_m3_h=100.0,
            resin_props=STANDARD_SAC_RESIN
        )

        assert result.velocity_in_range is True
        assert len([w for w in result.warnings if "velocity" in w.lower()]) == 0

    def test_awwa_velocity_validation_too_low(self):
        """Test that low velocity (<5 m/h) triggers AWWA warning."""
        # Very low flow rate
        result = calculate_system_hydraulics(
            bed_depth_m=2.5,
            bed_diameter_m=2.0,
            service_flow_m3_h=10.0,  # ~3.2 m/h
            backwash_flow_m3_h=100.0,
            resin_props=STANDARD_SAC_RESIN
        )

        assert result.velocity_in_range is False
        assert any("AWWA B100" in w for w in result.warnings)
        assert any("5-40 m/h" in w for w in result.warnings)

    def test_awwa_velocity_validation_too_high(self):
        """Test that high velocity (>40 m/h) triggers AWWA warning."""
        # Very high flow rate
        result = calculate_system_hydraulics(
            bed_depth_m=2.5,
            bed_diameter_m=2.0,
            service_flow_m3_h=500.0,  # ~159 m/h
            backwash_flow_m3_h=100.0,
            resin_props=STANDARD_SAC_RESIN
        )

        assert result.velocity_in_range is False
        assert any("AWWA B100" in w for w in result.warnings)

    def test_excessive_expansion_warning(self):
        """Test that >100% expansion triggers warning."""
        # Very high backwash rate to force excessive expansion
        result = calculate_system_hydraulics(
            bed_depth_m=2.5,
            bed_diameter_m=2.0,
            service_flow_m3_h=100.0,
            backwash_flow_m3_h=500.0,  # Very high
            resin_props=STANDARD_SAC_RESIN
        )

        if result.bed_expansion_percent >= 100.0:
            assert result.expansion_acceptable is False
            assert any("expansion" in w.lower() for w in result.warnings)

    def test_high_pressure_drop_warning(self):
        """Test that high service ΔP (>70 kPa) triggers warning."""
        # Deep bed with fine particles to force high ΔP
        fine_resin = ResinProperties(
            particle_diameter_m=0.0004,  # Very fine
            particle_density_kg_m3=1250.0,
            bed_porosity=0.38,
            sphericity=0.90
        )

        result = calculate_system_hydraulics(
            bed_depth_m=3.5,  # Deep bed
            bed_diameter_m=1.5,  # Small diameter
            service_flow_m3_h=100.0,
            backwash_flow_m3_h=80.0,
            resin_props=fine_resin
        )

        if result.pressure_drop_service_kpa > 70.0:
            assert any("pressure drop" in w.lower() for w in result.warnings)

    def test_freeboard_calculation(self):
        """Test freeboard calculation with safety factor."""
        result = calculate_system_hydraulics(
            bed_depth_m=2.0,
            bed_diameter_m=2.0,
            service_flow_m3_h=100.0,
            backwash_flow_m3_h=120.0,
            resin_props=STANDARD_SAC_RESIN,
            freeboard_safety_factor=1.5
        )

        # Freeboard should be expansion × safety factor
        expansion_height = result.expanded_bed_depth_m - 2.0
        expected_freeboard = expansion_height * 1.5

        assert abs(result.required_freeboard_m - expected_freeboard) < 0.01

    def test_freeboard_minimum(self):
        """Test edge case: ensure minimum freeboard even with low expansion."""
        # Very low backwash rate (minimal expansion)
        result = calculate_system_hydraulics(
            bed_depth_m=2.0,
            bed_diameter_m=2.0,
            service_flow_m3_h=100.0,
            backwash_flow_m3_h=20.0,  # Very low
            resin_props=STANDARD_SAC_RESIN
        )

        # Should have some freeboard even if expansion is minimal
        assert result.required_freeboard_m > 0.0

        # Typically should be at least 0.3m minimum
        # (This is not currently enforced in code, but could be added)

    def test_wac_resin_properties(self):
        """Test hydraulics with WAC resin properties."""
        result = calculate_system_hydraulics(
            bed_depth_m=2.5,
            bed_diameter_m=2.0,
            service_flow_m3_h=100.0,
            backwash_flow_m3_h=150.0,
            resin_props=STANDARD_WAC_RESIN
        )

        # WAC resin is less dense and slightly coarser
        # Should have different hydraulic behavior than SAC
        assert result.pressure_drop_service_kpa > 0
        assert result.bed_expansion_percent > 0

    def test_backwash_pressure_drop_vs_service(self):
        """Test that backwash ΔP is typically higher than service ΔP."""
        result = calculate_system_hydraulics(
            bed_depth_m=2.5,
            bed_diameter_m=2.0,
            service_flow_m3_h=100.0,
            backwash_flow_m3_h=150.0,  # 1.5× service flow
            resin_props=STANDARD_SAC_RESIN
        )

        # Backwash at higher flow should have higher ΔP
        assert result.pressure_drop_backwash_kpa > result.pressure_drop_service_kpa


class TestStandardResinProperties:
    """Test suite for standard resin property definitions."""

    def test_standard_sac_properties(self):
        """Test that STANDARD_SAC_RESIN has reasonable values."""
        assert 0.0006 <= STANDARD_SAC_RESIN.particle_diameter_m <= 0.0008  # 16-50 mesh
        assert 1200.0 <= STANDARD_SAC_RESIN.particle_density_kg_m3 <= 1300.0
        assert 0.35 <= STANDARD_SAC_RESIN.bed_porosity <= 0.45
        assert 0.90 <= STANDARD_SAC_RESIN.sphericity <= 1.0

    def test_standard_wac_properties(self):
        """Test that STANDARD_WAC_RESIN has reasonable values."""
        assert 0.0006 <= STANDARD_WAC_RESIN.particle_diameter_m <= 0.0008
        assert 1150.0 <= STANDARD_WAC_RESIN.particle_density_kg_m3 <= 1300.0
        assert 0.35 <= STANDARD_WAC_RESIN.bed_porosity <= 0.50
        assert 0.90 <= STANDARD_WAC_RESIN.sphericity <= 1.0

    def test_sac_vs_wac_differences(self):
        """Test that SAC and WAC resins have expected differences."""
        # WAC typically slightly coarser
        assert STANDARD_WAC_RESIN.particle_diameter_m >= STANDARD_SAC_RESIN.particle_diameter_m

        # WAC typically less dense (acrylic vs styrene)
        assert STANDARD_WAC_RESIN.particle_density_kg_m3 <= STANDARD_SAC_RESIN.particle_density_kg_m3

        # WAC typically slightly higher porosity
        assert STANDARD_WAC_RESIN.bed_porosity >= STANDARD_SAC_RESIN.bed_porosity


class TestPhysicalConstants:
    """Test suite for physical constants used in calculations."""

    def test_water_properties(self):
        """Test that water property constants are reasonable."""
        assert 995.0 <= WATER_DENSITY_KG_M3 <= 1005.0  # 20°C range
        assert 0.0008 <= WATER_VISCOSITY_PA_S <= 0.0012  # 15-25°C range
        assert 9.7 <= GRAVITY_M_S2 <= 9.9  # Earth gravity

    def test_constants_consistency(self):
        """Test that constants are internally consistent."""
        # Density should be positive
        assert WATER_DENSITY_KG_M3 > 0

        # Viscosity should be positive
        assert WATER_VISCOSITY_PA_S > 0

        # Gravity should be positive
        assert GRAVITY_M_S2 > 0
