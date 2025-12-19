"""
Tests for Unified IX Economics Calculator Module.

Validates CRF calculation, LCOW calculation, CAPEX/OPEX components,
and ensures consistency with EPA-WBS methodologies.

References:
- EPA Water Treatment Plant Cost Model
- Standard time-value-of-money formulas
"""
import pytest
import math
from tools.ix_economics import (
    IXEconomicsCalculator,
    EconomicsConfig,
    CostConfidence,
    calculate_crf,
    calculate_lcow
)


class TestCRFCalculation:
    """Test suite for Capital Recovery Factor calculations."""

    def test_crf_standard_defaults(self):
        """Test CRF with default parameters (8% rate, 20 years)."""
        calc = IXEconomicsCalculator()
        crf = calc.calculate_crf()

        # Hand calculation: CRF = r(1+r)^n / ((1+r)^n - 1)
        r = 0.08
        n = 20
        expected = r * (1 + r) ** n / ((1 + r) ** n - 1)

        assert abs(crf - expected) < 1e-6
        # Expected value ~0.1019 for 8%/20yr
        assert 0.10 < crf < 0.11

    def test_crf_various_rates(self):
        """Test CRF at various discount rates."""
        config = EconomicsConfig(plant_lifetime_years=20)

        test_cases = [
            (0.05, 0.0802),  # 5% rate
            (0.08, 0.1019),  # 8% rate
            (0.10, 0.1175),  # 10% rate
            (0.12, 0.1339),  # 12% rate
        ]

        for rate, expected_crf in test_cases:
            config.discount_rate = rate
            calc = IXEconomicsCalculator(config=config)
            crf = calc.calculate_crf()
            assert abs(crf - expected_crf) < 0.001, f"CRF at {rate:.0%} should be ~{expected_crf}"

    def test_crf_various_lifetimes(self):
        """Test CRF at various plant lifetimes."""
        config = EconomicsConfig(discount_rate=0.08)

        test_cases = [
            (10, 0.1490),
            (15, 0.1168),
            (20, 0.1019),
            (25, 0.0937),
            (30, 0.0888),
        ]

        for years, expected_crf in test_cases:
            config.plant_lifetime_years = years
            calc = IXEconomicsCalculator(config=config)
            crf = calc.calculate_crf()
            assert abs(crf - expected_crf) < 0.001, f"CRF at {years}yr should be ~{expected_crf}"

    def test_crf_zero_discount_rate(self):
        """Test CRF with zero discount rate (simple payback)."""
        config = EconomicsConfig(discount_rate=0.0, plant_lifetime_years=20)
        calc = IXEconomicsCalculator(config=config)
        crf = calc.calculate_crf()

        # With zero rate, CRF = 1/n
        expected = 1.0 / 20
        assert abs(crf - expected) < 1e-6

    def test_crf_standalone_function(self):
        """Test standalone calculate_crf function."""
        crf = calculate_crf(0.08, 20)
        expected = 0.08 * (1.08) ** 20 / ((1.08) ** 20 - 1)
        assert abs(crf - expected) < 1e-6


class TestLCOWCalculation:
    """Test suite for Levelized Cost of Water calculations."""

    def test_lcow_basic_calculation(self):
        """Test basic LCOW calculation."""
        calc = IXEconomicsCalculator()

        capital = 500000  # $500k
        annual_opex = 50000  # $50k/yr
        annual_production = 100000  # 100,000 m³/yr

        lcow = calc.calculate_lcow(capital, annual_opex, annual_production)

        # LCOW = (CAPEX × CRF + OPEX) / Production
        crf = calc.calculate_crf()  # ~0.1019
        expected = (capital * crf + annual_opex) / annual_production

        assert abs(lcow - expected) < 0.001

    def test_lcow_zero_capex(self):
        """Test LCOW with zero capital cost."""
        calc = IXEconomicsCalculator()

        lcow = calc.calculate_lcow(0, 50000, 100000)

        # Should be just OPEX / Production
        expected = 50000 / 100000
        assert abs(lcow - expected) < 0.001

    def test_lcow_zero_opex(self):
        """Test LCOW with zero operating cost."""
        calc = IXEconomicsCalculator()

        capital = 500000
        lcow = calc.calculate_lcow(capital, 0, 100000)

        # Should be CAPEX × CRF / Production
        crf = calc.calculate_crf()
        expected = capital * crf / 100000
        assert abs(lcow - expected) < 0.001

    def test_lcow_zero_production(self):
        """Test LCOW with zero production returns infinity."""
        calc = IXEconomicsCalculator()
        lcow = calc.calculate_lcow(500000, 50000, 0)
        assert lcow == float('inf')

    def test_lcow_standalone_function(self):
        """Test standalone calculate_lcow function."""
        lcow = calculate_lcow(
            capital_cost_usd=500000,
            annual_opex_usd=50000,
            annual_production_m3=100000,
            discount_rate=0.08,
            plant_lifetime_years=20
        )

        crf = calculate_crf(0.08, 20)
        expected = (500000 * crf + 50000) / 100000
        assert abs(lcow - expected) < 0.001


class TestAnnualProduction:
    """Test suite for annual production calculations."""

    def test_annual_production_standard(self):
        """Test annual production with default availability (90%)."""
        calc = IXEconomicsCalculator()

        flow_m3_hr = 100  # 100 m³/hr
        annual = calc.calculate_annual_production_m3(flow_m3_hr)

        expected = 100 * 8760 * 0.90  # hours × availability
        assert abs(annual - expected) < 1

    def test_annual_production_custom_availability(self):
        """Test annual production with custom availability."""
        config = EconomicsConfig(availability=0.95)
        calc = IXEconomicsCalculator(config=config)

        flow_m3_hr = 100
        annual = calc.calculate_annual_production_m3(flow_m3_hr)

        expected = 100 * 8760 * 0.95
        assert abs(annual - expected) < 1


class TestVesselCAPEX:
    """Test suite for vessel capital cost calculations."""

    def test_vessel_capex_epa_wbs_correlation(self):
        """Test vessel cost follows EPA-WBS correlation."""
        calc = IXEconomicsCalculator()

        # Standard vessel: 2m dia × 3m height
        cost = calc.calculate_vessel_capex(
            diameter_m=2.0,
            height_m=3.0,
            n_vessels=2,
            material="FRP"
        )

        # Hand calculation: Cost = 1596.5 × V^0.459
        volume_m3 = math.pi * (2.0 / 2) ** 2 * 3.0  # ~9.42 m³
        volume_gal = volume_m3 * 264.172  # ~2490 gal
        expected_per_vessel = 1596.5 * (volume_gal ** 0.459)
        expected_total = expected_per_vessel * 2

        assert abs(cost - expected_total) < 100

    def test_vessel_capex_material_factors(self):
        """Test vessel cost scales with material factors."""
        calc = IXEconomicsCalculator()

        base_params = {"diameter_m": 2.0, "height_m": 3.0, "n_vessels": 1}

        cost_frp = calc.calculate_vessel_capex(**base_params, material="FRP")
        cost_steel = calc.calculate_vessel_capex(**base_params, material="steel")
        cost_lined = calc.calculate_vessel_capex(**base_params, material="lined_steel")
        cost_ss = calc.calculate_vessel_capex(**base_params, material="stainless_steel")

        # Steel cheaper, lined more, stainless most
        assert cost_steel < cost_frp
        assert cost_frp < cost_lined
        assert cost_lined < cost_ss

    def test_vessel_capex_scales_with_count(self):
        """Test vessel cost scales linearly with vessel count."""
        calc = IXEconomicsCalculator()

        cost_1 = calc.calculate_vessel_capex(2.0, 3.0, 1)
        cost_2 = calc.calculate_vessel_capex(2.0, 3.0, 2)
        cost_3 = calc.calculate_vessel_capex(2.0, 3.0, 3)

        assert abs(cost_2 - 2 * cost_1) < 1
        assert abs(cost_3 - 3 * cost_1) < 1


class TestResinCAPEX:
    """Test suite for resin capital cost calculations."""

    def test_resin_capex_default_cost(self):
        """Test resin cost with default price ($2800/m³)."""
        calc = IXEconomicsCalculator()

        bed_volume_m3 = 10.0  # 10 m³
        cost = calc.calculate_resin_capex(bed_volume_m3)

        expected = 10.0 * 2800
        assert abs(cost - expected) < 1

    def test_resin_capex_custom_cost(self):
        """Test resin cost with custom price."""
        calc = IXEconomicsCalculator()

        cost = calc.calculate_resin_capex(10.0, resin_usd_m3=3500)
        expected = 10.0 * 3500
        assert abs(cost - expected) < 1


class TestPumpCAPEX:
    """Test suite for pump capital cost calculations."""

    def test_pump_capex_calculation(self):
        """Test pump capital cost calculation."""
        calc = IXEconomicsCalculator()

        cost = calc.calculate_pump_capex(
            flow_m3_hr=100.0,
            head_m=30.0,
            n_pumps=2
        )

        # Should be positive and reasonable
        assert cost > 10000  # At least $10k for 2 pumps
        assert cost < 100000  # Not unreasonably high

    def test_pump_capex_scales_with_count(self):
        """Test pump cost scales with pump count."""
        calc = IXEconomicsCalculator()

        cost_1 = calc.calculate_pump_capex(100.0, 30.0, 1)
        cost_2 = calc.calculate_pump_capex(100.0, 30.0, 2)

        assert abs(cost_2 - 2 * cost_1) < 100


class TestPumpPower:
    """Test suite for pump power calculations."""

    def test_pump_power_calculation(self):
        """Test pump power calculation P = Q × ΔP / η."""
        calc = IXEconomicsCalculator()

        power = calc.calculate_pump_power_kw(
            flow_m3_hr=100.0,
            pressure_drop_bar=0.6,
            efficiency=0.70
        )

        # Hand calculation
        q_m3s = 100.0 / 3600
        delta_p_pa = 0.6 * 1e5
        expected = (q_m3s * delta_p_pa) / 0.70 / 1000

        assert abs(power - expected) < 0.01

    def test_pump_power_scales_with_flow(self):
        """Test pump power scales linearly with flow."""
        calc = IXEconomicsCalculator()

        power_100 = calc.calculate_pump_power_kw(100.0, 0.6)
        power_200 = calc.calculate_pump_power_kw(200.0, 0.6)

        assert abs(power_200 / power_100 - 2.0) < 0.01


class TestEnergyCost:
    """Test suite for energy cost calculations."""

    def test_energy_cost_annual(self):
        """Test annual energy cost calculation."""
        config = EconomicsConfig(
            electricity_usd_kwh=0.10,
            availability=0.90
        )
        calc = IXEconomicsCalculator(config=config)

        power_kw = 5.0  # 5 kW average
        annual_cost = calc.calculate_energy_cost_annual(power_kw)

        # Expected: 5 kW × 8760 hr × 0.90 × $0.10/kWh
        expected = 5.0 * 8760 * 0.90 * 0.10
        assert abs(annual_cost - expected) < 1


class TestRegenerantCost:
    """Test suite for regenerant cost calculations."""

    def test_regenerant_cost_nacl(self):
        """Test NaCl regenerant cost calculation."""
        config = EconomicsConfig(nacl_usd_kg=0.15)
        calc = IXEconomicsCalculator(config=config)

        annual_cost = calc.calculate_regenerant_cost_annual(
            regenerant_type="NaCl",
            regenerant_kg_cycle=100.0,
            cycles_per_year=500
        )

        expected = 100.0 * 500 * 0.15
        assert abs(annual_cost - expected) < 1

    def test_regenerant_cost_hcl(self):
        """Test HCl regenerant cost calculation."""
        config = EconomicsConfig(hcl_usd_kg=0.30)
        calc = IXEconomicsCalculator(config=config)

        annual_cost = calc.calculate_regenerant_cost_annual(
            regenerant_type="HCl",
            regenerant_kg_cycle=50.0,
            cycles_per_year=500
        )

        expected = 50.0 * 500 * 0.30
        assert abs(annual_cost - expected) < 1


class TestResinReplacementCost:
    """Test suite for resin replacement cost calculations."""

    def test_resin_replacement_default_rate(self):
        """Test resin replacement with default rate (5%)."""
        calc = IXEconomicsCalculator()

        initial_cost = 50000  # $50k initial resin
        annual_cost = calc.calculate_resin_replacement_cost_annual(initial_cost)

        expected = 50000 * 0.05
        assert abs(annual_cost - expected) < 1

    def test_resin_replacement_custom_rate(self):
        """Test resin replacement with custom rate."""
        calc = IXEconomicsCalculator()

        annual_cost = calc.calculate_resin_replacement_cost_annual(
            resin_cost_initial=50000,
            replacement_rate=0.10
        )

        expected = 50000 * 0.10
        assert abs(annual_cost - expected) < 1


class TestTotalOPEX:
    """Test suite for total OPEX calculations."""

    def test_total_opex_components(self):
        """Test total OPEX aggregates all components."""
        calc = IXEconomicsCalculator()

        total, breakdown = calc.calculate_total_opex(
            energy_cost=10000,
            regenerant_cost=20000,
            resin_replacement_cost=5000,
            labor_cost=15000,
            maintenance_fraction=0.02,
            capex=500000
        )

        maintenance = 500000 * 0.02
        expected_total = 10000 + 20000 + 5000 + 15000 + maintenance

        assert abs(total - expected_total) < 1
        assert breakdown["energy_cost_usd_year"] == 10000
        assert breakdown["regenerant_cost_usd_year"] == 20000
        assert breakdown["resin_replacement_cost_usd_year"] == 5000
        assert breakdown["labor_cost_usd_year"] == 15000
        assert abs(breakdown["maintenance_cost_usd_year"] - maintenance) < 1


class TestFullEconomics:
    """Test suite for complete economics calculations."""

    def test_full_economics_integration(self):
        """Test full economics calculation returns expected structure."""
        calc = IXEconomicsCalculator()

        result = calc.calculate_full_economics(
            flow_m3_hr=100.0,
            diameter_m=2.0,
            bed_depth_m=2.5,
            vessel_height_m=4.0,
            n_service_vessels=1,
            n_standby_vessels=1,
            regenerant_type="NaCl",
            regenerant_kg_cycle=100.0,
            service_hours_per_cycle=16.0,
            pressure_drop_bar=0.6
        )

        # Check structure
        assert "capital_cost_usd" in result
        assert "operating_cost_usd_year" in result
        assert "lcow_usd_m3" in result
        assert "sec_kwh_m3" in result
        assert "crf" in result
        assert "annual_production_m3" in result
        assert "capex_breakdown" in result
        assert "opex_breakdown" in result
        assert "confidence" in result
        assert "notes" in result

        # Sanity checks
        assert result["capital_cost_usd"] > 0
        assert result["operating_cost_usd_year"] > 0
        assert result["lcow_usd_m3"] > 0
        assert result["lcow_usd_m3"] < 10.0  # Should be reasonable
        assert result["crf"] > 0
        assert result["confidence"] == CostConfidence.ESTIMATE.value


class TestEconomicsConfig:
    """Test suite for EconomicsConfig defaults."""

    def test_config_defaults(self):
        """Test EconomicsConfig has sensible defaults."""
        config = EconomicsConfig()

        assert config.discount_rate == 0.08
        assert config.plant_lifetime_years == 20
        assert config.availability == 0.90
        assert config.pump_efficiency == 0.70
        assert config.installation_factor == 2.5
        assert config.nacl_usd_kg > 0
        assert config.electricity_usd_kwh > 0
        assert config.resin_usd_m3 > 0
        assert config.resin_replacement_rate == 0.05


class TestPricingOverride:
    """Test suite for pricing parameter override behavior."""

    def test_pricing_overrides_config(self):
        """Test that pricing object overrides config defaults."""
        # Create mock pricing object
        class MockPricing:
            discount_rate = 0.10
            plant_lifetime_years = 15
            electricity_usd_kwh = 0.12
            nacl_usd_kg = 0.20

        calc = IXEconomicsCalculator(pricing=MockPricing())

        assert calc.config.discount_rate == 0.10
        assert calc.config.plant_lifetime_years == 15
        assert calc.config.electricity_usd_kwh == 0.12
        assert calc.config.nacl_usd_kg == 0.20

    def test_partial_pricing_override(self):
        """Test that partial pricing only overrides specified fields."""
        class PartialPricing:
            discount_rate = 0.12
            # Other fields not specified

        config = EconomicsConfig(plant_lifetime_years=25)
        calc = IXEconomicsCalculator(pricing=PartialPricing(), config=config)

        assert calc.config.discount_rate == 0.12  # Overridden
        assert calc.config.plant_lifetime_years == 25  # From config
