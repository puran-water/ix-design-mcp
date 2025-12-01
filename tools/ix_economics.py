"""
Unified IX Economics Calculator

Single source of truth for LCOW, CAPEX, OPEX, and related economics calculations.
All IX simulation and configuration tools should use this module for economics.

Design Principles:
- Use discount_rate and plant_lifetime_years from EconomicParameters schema
- EPA-WBS correlations for vessel and equipment costing
- Consistent CRF calculation across all code paths
- Clear documentation of all assumptions and sources
"""

import math
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CostConfidence(Enum):
    """Cost estimate confidence levels"""
    ESTIMATE = "estimate"      # +/- 30%
    BUDGETARY = "budgetary"    # +/- 15%
    FIRM = "firm"              # +/- 5%


@dataclass
class EconomicsConfig:
    """Economics configuration with sensible defaults.

    These values can be overridden by EconomicParameters schema input.
    """
    # Time value of money
    discount_rate: float = 0.08
    plant_lifetime_years: int = 20
    availability: float = 0.90  # 90% uptime

    # Equipment parameters
    pump_efficiency: float = 0.70
    installation_factor: float = 2.5  # Total installed cost multiplier

    # Chemical costs ($/kg) - defaults, typically overridden
    nacl_usd_kg: float = 0.12
    hcl_usd_kg: float = 0.25
    h2so4_usd_kg: float = 0.20
    naoh_usd_kg: float = 0.35

    # Equipment costs
    electricity_usd_kwh: float = 0.07
    resin_usd_m3: float = 2800.0
    resin_replacement_rate: float = 0.05  # 5% annual replacement


class IXEconomicsCalculator:
    """
    Single source of truth for IX economics calculations.

    Usage:
        from tools.ix_economics import IXEconomicsCalculator
        from utils.schemas import EconomicParameters

        pricing = EconomicParameters(discount_rate=0.10, plant_lifetime_years=15)
        calc = IXEconomicsCalculator(pricing)

        lcow = calc.calculate_lcow(
            capital_cost_usd=500000,
            annual_opex_usd=50000,
            annual_production_m3=100000
        )
    """

    def __init__(self, pricing=None, config: Optional[EconomicsConfig] = None):
        """
        Initialize economics calculator.

        Args:
            pricing: EconomicParameters schema object (from MCP input)
            config: EconomicsConfig for defaults not in schema
        """
        self.config = config or EconomicsConfig()
        self.pricing = pricing

        # Override config with pricing if provided
        if pricing is not None:
            self.config.discount_rate = getattr(pricing, 'discount_rate', self.config.discount_rate)
            self.config.plant_lifetime_years = getattr(pricing, 'plant_lifetime_years', self.config.plant_lifetime_years)
            self.config.electricity_usd_kwh = getattr(pricing, 'electricity_usd_kwh', self.config.electricity_usd_kwh)
            self.config.nacl_usd_kg = getattr(pricing, 'nacl_usd_kg', self.config.nacl_usd_kg)
            self.config.hcl_usd_kg = getattr(pricing, 'hcl_usd_kg', self.config.hcl_usd_kg)
            self.config.h2so4_usd_kg = getattr(pricing, 'h2so4_usd_kg', self.config.h2so4_usd_kg)
            self.config.naoh_usd_kg = getattr(pricing, 'naoh_usd_kg', self.config.naoh_usd_kg)
            self.config.resin_usd_m3 = getattr(pricing, 'resin_usd_m3', self.config.resin_usd_m3)
            self.config.resin_replacement_rate = getattr(pricing, 'resin_replacement_rate', self.config.resin_replacement_rate)

    # ==================== Core Calculations ====================

    def calculate_crf(self) -> float:
        """
        Calculate Capital Recovery Factor.

        CRF = r(1+r)^n / ((1+r)^n - 1)

        Uses discount_rate and plant_lifetime_years from schema.

        Returns:
            CRF value (typically 0.08-0.15)
        """
        r = self.config.discount_rate
        n = self.config.plant_lifetime_years

        if r <= 0:
            # Zero discount rate - simple payback
            return 1.0 / n if n > 0 else 0.1

        numerator = r * (1 + r) ** n
        denominator = (1 + r) ** n - 1

        crf = numerator / denominator

        logger.debug(f"CRF calculation: r={r:.3f}, n={n}, CRF={crf:.4f}")
        return crf

    def calculate_lcow(
        self,
        capital_cost_usd: float,
        annual_opex_usd: float,
        annual_production_m3: float
    ) -> float:
        """
        Calculate Levelized Cost of Water.

        LCOW = (CAPEX × CRF + OPEX) / Annual_Production

        Args:
            capital_cost_usd: Total installed capital cost ($)
            annual_opex_usd: Annual operating cost ($)
            annual_production_m3: Annual water production (m³)

        Returns:
            LCOW in $/m³
        """
        if annual_production_m3 <= 0:
            logger.warning("Annual production is zero - returning infinite LCOW")
            return float('inf')

        crf = self.calculate_crf()
        annual_capital = capital_cost_usd * crf
        lcow = (annual_capital + annual_opex_usd) / annual_production_m3

        logger.debug(f"LCOW: CAPEX=${capital_cost_usd:,.0f}, CRF={crf:.4f}, "
                    f"OPEX=${annual_opex_usd:,.0f}/yr, Prod={annual_production_m3:,.0f} m³/yr, "
                    f"LCOW=${lcow:.4f}/m³")
        return lcow

    def calculate_annual_production_m3(self, flow_m3_hr: float) -> float:
        """
        Calculate annual water production.

        Args:
            flow_m3_hr: Flow rate in m³/hr

        Returns:
            Annual production in m³
        """
        hours_per_year = 8760
        return flow_m3_hr * hours_per_year * self.config.availability

    # ==================== Capital Costs ====================

    def calculate_vessel_capex(
        self,
        diameter_m: float,
        height_m: float,
        n_vessels: int,
        material: str = "FRP"
    ) -> float:
        """
        Calculate vessel capital cost using EPA-WBS correlation.

        Based on EPA Water Treatment Plant Cost Model (EPA-WBS).
        Cost = 1596.5 × V^0.459 per vessel (V in gallons)

        Args:
            diameter_m: Vessel diameter in meters
            height_m: Total vessel height in meters
            n_vessels: Number of vessels (service + standby)
            material: Vessel material (FRP, steel, lined_steel)

        Returns:
            Total vessel cost ($)
        """
        # Calculate volume
        volume_m3 = math.pi * (diameter_m / 2) ** 2 * height_m
        volume_gal = volume_m3 * 264.172  # m³ to gallons

        # EPA-WBS correlation (1596.5 × V^0.459)
        cost_per_vessel = 1596.5 * (volume_gal ** 0.459)

        # Material adjustment factors
        material_factors = {
            "FRP": 1.0,
            "steel": 0.85,
            "lined_steel": 1.15,
            "stainless_steel": 1.8
        }
        factor = material_factors.get(material, 1.0)

        total_cost = cost_per_vessel * n_vessels * factor

        logger.debug(f"Vessel CAPEX: D={diameter_m:.2f}m, H={height_m:.2f}m, "
                    f"V={volume_gal:.0f}gal, n={n_vessels}, ${total_cost:,.0f}")
        return total_cost

    def calculate_resin_capex(
        self,
        bed_volume_m3: float,
        resin_usd_m3: Optional[float] = None
    ) -> float:
        """
        Calculate initial resin charge cost.

        Args:
            bed_volume_m3: Total resin bed volume in m³
            resin_usd_m3: Resin cost per m³ (uses config default if not provided)

        Returns:
            Resin cost ($)
        """
        cost_per_m3 = resin_usd_m3 if resin_usd_m3 is not None else self.config.resin_usd_m3
        return bed_volume_m3 * cost_per_m3

    def calculate_pump_capex(
        self,
        flow_m3_hr: float,
        head_m: float = 30.0,
        n_pumps: int = 2
    ) -> float:
        """
        Calculate pump capital cost.

        Based on EPA-WBS correlation for centrifugal pumps.

        Args:
            flow_m3_hr: Design flow rate in m³/hr
            head_m: Total dynamic head in meters
            n_pumps: Number of pumps (1 duty + 1 standby typical)

        Returns:
            Pump cost ($)
        """
        # Convert to gallons per minute
        flow_gpm = flow_m3_hr * 4.4029

        # Power required (kW)
        power_kw = (flow_m3_hr / 3600) * (head_m * 9.81 * 1000) / (self.config.pump_efficiency * 1000)

        # EPA-WBS correlation for centrifugal pumps
        # Base cost ~$5000 + $500/kW for smaller pumps
        cost_per_pump = 5000 + 500 * power_kw

        # Minimum cost
        cost_per_pump = max(cost_per_pump, 8000)

        return cost_per_pump * n_pumps

    def calculate_total_capex(
        self,
        vessel_cost: float,
        resin_cost: float,
        pump_cost: float,
        instrumentation_fraction: float = 0.15,
        installation_factor: Optional[float] = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate total installed capital cost.

        Args:
            vessel_cost: Vessel capital cost
            resin_cost: Initial resin cost
            pump_cost: Pump capital cost
            instrumentation_fraction: I&C as fraction of equipment (default 15%)
            installation_factor: Total installed cost multiplier (default from config)

        Returns:
            Tuple of (total_capex, breakdown_dict)
        """
        factor = installation_factor if installation_factor is not None else self.config.installation_factor

        equipment_subtotal = vessel_cost + resin_cost + pump_cost
        instrumentation = equipment_subtotal * instrumentation_fraction

        direct_cost = equipment_subtotal + instrumentation
        total_capex = direct_cost * factor

        breakdown = {
            "vessels_usd": vessel_cost,
            "resin_initial_usd": resin_cost,
            "pumps_usd": pump_cost,
            "instrumentation_usd": instrumentation,
            "direct_cost_usd": direct_cost,
            "installation_factor": factor,
            "total_capex_usd": total_capex
        }

        return total_capex, breakdown

    # ==================== Operating Costs ====================

    def calculate_pump_power_kw(
        self,
        flow_m3_hr: float,
        pressure_drop_bar: float,
        efficiency: Optional[float] = None
    ) -> float:
        """
        Calculate pump power from hydraulics.

        P = Q × ΔP / η

        Args:
            flow_m3_hr: Flow rate in m³/hr
            pressure_drop_bar: Pressure drop in bar
            efficiency: Pump efficiency (uses config default if not provided)

        Returns:
            Pump power in kW
        """
        eta = efficiency if efficiency is not None else self.config.pump_efficiency

        q_m3s = flow_m3_hr / 3600
        delta_p_pa = pressure_drop_bar * 1e5

        power_kw = (q_m3s * delta_p_pa) / eta / 1000
        return power_kw

    def calculate_energy_cost_annual(
        self,
        power_kw: float,
        operating_hours: Optional[float] = None
    ) -> float:
        """
        Calculate annual energy cost.

        Args:
            power_kw: Average pump power in kW
            operating_hours: Annual operating hours (uses 8760 × availability if not provided)

        Returns:
            Annual energy cost ($)
        """
        hours = operating_hours if operating_hours is not None else (8760 * self.config.availability)
        kwh_year = power_kw * hours
        return kwh_year * self.config.electricity_usd_kwh

    def calculate_regenerant_cost_annual(
        self,
        regenerant_type: str,
        regenerant_kg_cycle: float,
        cycles_per_year: float
    ) -> float:
        """
        Calculate annual regenerant cost.

        Args:
            regenerant_type: NaCl, HCl, H2SO4, or NaOH
            regenerant_kg_cycle: Regenerant consumption per cycle (kg)
            cycles_per_year: Number of regeneration cycles per year

        Returns:
            Annual regenerant cost ($)
        """
        cost_map = {
            "NaCl": self.config.nacl_usd_kg,
            "HCl": self.config.hcl_usd_kg,
            "H2SO4": self.config.h2so4_usd_kg,
            "NaOH": self.config.naoh_usd_kg
        }

        cost_per_kg = cost_map.get(regenerant_type, self.config.nacl_usd_kg)
        annual_consumption = regenerant_kg_cycle * cycles_per_year

        return annual_consumption * cost_per_kg

    def calculate_resin_replacement_cost_annual(
        self,
        resin_cost_initial: float,
        replacement_rate: Optional[float] = None
    ) -> float:
        """
        Calculate annual resin replacement cost.

        Args:
            resin_cost_initial: Initial resin charge cost ($)
            replacement_rate: Annual replacement fraction (uses config default if not provided)

        Returns:
            Annual resin replacement cost ($)
        """
        rate = replacement_rate if replacement_rate is not None else self.config.resin_replacement_rate
        return resin_cost_initial * rate

    def calculate_total_opex(
        self,
        energy_cost: float,
        regenerant_cost: float,
        resin_replacement_cost: float,
        labor_cost: float = 0,
        maintenance_fraction: float = 0.02,
        capex: float = 0
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate total annual operating cost.

        Args:
            energy_cost: Annual energy cost
            regenerant_cost: Annual regenerant cost
            resin_replacement_cost: Annual resin replacement
            labor_cost: Annual labor cost (default 0 for automated systems)
            maintenance_fraction: Maintenance as fraction of CAPEX
            capex: Total CAPEX for maintenance calculation

        Returns:
            Tuple of (total_opex, breakdown_dict)
        """
        maintenance_cost = capex * maintenance_fraction

        total_opex = (
            energy_cost +
            regenerant_cost +
            resin_replacement_cost +
            labor_cost +
            maintenance_cost
        )

        breakdown = {
            "energy_cost_usd_year": energy_cost,
            "regenerant_cost_usd_year": regenerant_cost,
            "resin_replacement_cost_usd_year": resin_replacement_cost,
            "labor_cost_usd_year": labor_cost,
            "maintenance_cost_usd_year": maintenance_cost,
            "total_opex_usd_year": total_opex
        }

        return total_opex, breakdown

    # ==================== Convenience Methods ====================

    def calculate_full_economics(
        self,
        flow_m3_hr: float,
        diameter_m: float,
        bed_depth_m: float,
        vessel_height_m: float,
        n_service_vessels: int,
        n_standby_vessels: int,
        regenerant_type: str,
        regenerant_kg_cycle: float,
        service_hours_per_cycle: float,
        pressure_drop_bar: float = 0.6
    ) -> Dict:
        """
        Calculate complete economics from design parameters.

        Returns comprehensive economics breakdown including LCOW.
        """
        # Derived values
        n_vessels = n_service_vessels + n_standby_vessels
        bed_volume_m3 = math.pi * (diameter_m / 2) ** 2 * bed_depth_m * n_service_vessels
        cycles_per_year = 8760 * self.config.availability / service_hours_per_cycle
        annual_production = self.calculate_annual_production_m3(flow_m3_hr)

        # CAPEX
        vessel_cost = self.calculate_vessel_capex(diameter_m, vessel_height_m, n_vessels)
        resin_cost = self.calculate_resin_capex(bed_volume_m3)
        pump_cost = self.calculate_pump_capex(flow_m3_hr)
        total_capex, capex_breakdown = self.calculate_total_capex(vessel_cost, resin_cost, pump_cost)

        # OPEX
        pump_power = self.calculate_pump_power_kw(flow_m3_hr, pressure_drop_bar)
        energy_cost = self.calculate_energy_cost_annual(pump_power)
        regenerant_cost = self.calculate_regenerant_cost_annual(regenerant_type, regenerant_kg_cycle, cycles_per_year)
        resin_replacement = self.calculate_resin_replacement_cost_annual(resin_cost)
        total_opex, opex_breakdown = self.calculate_total_opex(
            energy_cost, regenerant_cost, resin_replacement, capex=total_capex
        )

        # LCOW
        lcow = self.calculate_lcow(total_capex, total_opex, annual_production)

        # SEC
        sec = pump_power / flow_m3_hr if flow_m3_hr > 0 else 0.05

        return {
            "capital_cost_usd": total_capex,
            "operating_cost_usd_year": total_opex,
            "lcow_usd_m3": lcow,
            "sec_kwh_m3": sec,
            "crf": self.calculate_crf(),
            "annual_production_m3": annual_production,
            "capex_breakdown": capex_breakdown,
            "opex_breakdown": opex_breakdown,
            "confidence": CostConfidence.ESTIMATE.value,
            "notes": [
                f"Discount rate: {self.config.discount_rate:.1%}",
                f"Plant lifetime: {self.config.plant_lifetime_years} years",
                f"Availability: {self.config.availability:.0%}"
            ]
        }


# ==================== Module-Level Convenience Functions ====================

def calculate_crf(discount_rate: float, plant_lifetime_years: int) -> float:
    """
    Standalone CRF calculation.

    CRF = r(1+r)^n / ((1+r)^n - 1)
    """
    if discount_rate <= 0:
        return 1.0 / plant_lifetime_years if plant_lifetime_years > 0 else 0.1

    r = discount_rate
    n = plant_lifetime_years
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


def calculate_lcow(
    capital_cost_usd: float,
    annual_opex_usd: float,
    annual_production_m3: float,
    discount_rate: float = 0.08,
    plant_lifetime_years: int = 20
) -> float:
    """
    Standalone LCOW calculation.

    LCOW = (CAPEX × CRF + OPEX) / Annual_Production
    """
    crf = calculate_crf(discount_rate, plant_lifetime_years)
    return (capital_cost_usd * crf + annual_opex_usd) / annual_production_m3
