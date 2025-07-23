"""
Ion Exchange System Economics Calculator

Provides CAPEX and OPEX calculations for IX configurations.
Based on the WaterTAP costing module parameters.
"""

import math
from typing import Dict, Any
from .schemas import IXConfigurationOutput


# Cost parameters (2023 USD basis)
COST_PARAMS = {
    "vessel_cost_per_m3": 15000,  # $/m³ for FRP vessels
    "resin_cost_per_m3": {
        "SAC": 2000,
        "WAC_H": 3500,
        "WAC_Na": 3500,
    },
    "degasser_cost_per_m2": 3000,  # $/m² cross-sectional area
    "pump_base_cost": 5000,  # Base cost for 1 m³/hr, 10 m head
    "pump_size_exponent": 0.65,
    "installation_factor": 2.5,
    "instrumentation_factor": 0.15,  # As fraction of equipment cost
    "regenerant_costs_per_kg": {
        "NaCl": 0.10,  # Salt for SAC regeneration
        "HCl": 0.25,   # Acid for WAC regeneration
        "H2SO4": 0.15  # Sulfuric acid alternative
    },
    "electricity_cost_per_kwh": 0.10,
    "labor_cost_per_hour": 50,
    "waste_disposal_cost_per_m3": 20
}


def calculate_ix_economics(config: IXConfigurationOutput) -> Dict[str, Any]:
    """
    Calculate CAPEX and OPEX for an IX configuration.
    
    Returns:
        Dictionary with economics including:
        - capital_cost_usd: Total installed cost
        - annual_opex_usd: Annual operating cost
        - cost_per_m3: Levelized water cost
    """
    # CAPEX Calculations
    capex_breakdown = {}
    
    # Vessel costs
    vessel_cost = 0
    total_resin_cost = 0
    
    for vessel_name, vessel_config in config.ix_vessels.items():
        # Vessel shell cost
        vessel_volume = math.pi * (vessel_config.diameter_m/2)**2 * vessel_config.vessel_height_m
        single_vessel_cost = vessel_volume * COST_PARAMS["vessel_cost_per_m3"]
        
        # Total vessels (service + standby)
        total_vessels = vessel_config.number_service + vessel_config.number_standby
        vessel_cost += single_vessel_cost * total_vessels
        
        # Resin cost
        resin_type = vessel_config.resin_type
        resin_cost_per_m3 = COST_PARAMS["resin_cost_per_m3"].get(resin_type, 3000)
        total_resin_cost += vessel_config.resin_volume_m3 * resin_cost_per_m3
    
    capex_breakdown["vessels"] = vessel_cost
    capex_breakdown["resin"] = total_resin_cost
    
    # Degasser cost
    if config.degasser:
        degasser_area = math.pi * (config.degasser.diameter_m/2)**2
        degasser_cost = degasser_area * COST_PARAMS["degasser_cost_per_m2"]
        
        # Add fan/blower cost
        fan_cost = (config.degasser.fan_power_kW / 10) ** COST_PARAMS["pump_size_exponent"] * 8000
        capex_breakdown["degasser"] = degasser_cost + fan_cost
    else:
        capex_breakdown["degasser"] = 0
    
    # Pumps (feed and regeneration)
    flow_m3_hr = config.hydraulics.get("feed_flow_m3_hr", 100)  # Assume 100 if not provided
    pump_cost = COST_PARAMS["pump_base_cost"] * (flow_m3_hr) ** COST_PARAMS["pump_size_exponent"]
    pump_cost *= 3  # Feed, backwash, and regeneration pumps
    capex_breakdown["pumps"] = pump_cost
    
    # Total equipment cost
    equipment_cost = sum(capex_breakdown.values())
    
    # Instrumentation
    instrumentation_cost = equipment_cost * COST_PARAMS["instrumentation_factor"]
    capex_breakdown["instrumentation"] = instrumentation_cost
    
    # Total installed cost
    total_capex = (equipment_cost + instrumentation_cost) * COST_PARAMS["installation_factor"]
    
    # OPEX Calculations
    opex_breakdown = {}
    
    # Regenerant costs
    annual_regenerant_cost = 0
    
    # Estimate regeneration frequency (cycles per year)
    # Assume 24 hr service cycle for simplicity
    cycles_per_year = 365
    
    # Calculate regenerant consumption based on resin type
    for vessel_name, vessel_config in config.ix_vessels.items():
        if vessel_config.resin_type == "SAC":
            # SAC uses salt (NaCl)
            regen_kg_per_cycle = vessel_config.resin_volume_m3 * 120  # 120 kg/m³ typical
            annual_regenerant_cost += regen_kg_per_cycle * cycles_per_year * COST_PARAMS["regenerant_costs_per_kg"]["NaCl"]
        elif vessel_config.resin_type.startswith("WAC"):
            # WAC uses acid (HCl)
            regen_kg_per_cycle = vessel_config.resin_volume_m3 * 80  # 80 kg/m³ typical
            annual_regenerant_cost += regen_kg_per_cycle * cycles_per_year * COST_PARAMS["regenerant_costs_per_kg"]["HCl"]
    
    opex_breakdown["regenerant"] = annual_regenerant_cost
    
    # Power costs
    # Pumping power estimate
    pumping_kw = flow_m3_hr * 0.3  # Rough estimate: 0.3 kWh/m³
    if config.degasser:
        pumping_kw += config.degasser.fan_power_kW
    
    annual_power_cost = pumping_kw * 8760 * COST_PARAMS["electricity_cost_per_kwh"]
    opex_breakdown["power"] = annual_power_cost
    
    # Labor (operator attention)
    # Assume 2 hours per day for IX system
    annual_labor_cost = 2 * 365 * COST_PARAMS["labor_cost_per_hour"]
    opex_breakdown["labor"] = annual_labor_cost
    
    # Waste disposal
    # Estimate 6 BV of waste per regeneration
    waste_m3_per_cycle = config.hydraulics["total_resin_volume_m3"] * 6
    annual_waste_cost = waste_m3_per_cycle * cycles_per_year * COST_PARAMS["waste_disposal_cost_per_m3"]
    opex_breakdown["waste_disposal"] = annual_waste_cost
    
    # Maintenance (3% of CAPEX)
    annual_maintenance = total_capex * 0.03
    opex_breakdown["maintenance"] = annual_maintenance
    
    # Total OPEX
    total_opex = sum(opex_breakdown.values())
    
    # Calculate levelized cost of water (LCOW)
    # Assume 10 year life, 8% discount rate
    crf = 0.08 * (1 + 0.08)**10 / ((1 + 0.08)**10 - 1)  # Capital recovery factor
    annual_capex = total_capex * crf
    
    # Annual water production (assume 90% availability)
    annual_water_m3 = flow_m3_hr * 8760 * 0.9
    
    lcow = (annual_capex + total_opex) / annual_water_m3
    
    return {
        "capital_cost_usd": round(total_capex),
        "capex_breakdown": {k: round(v) for k, v in capex_breakdown.items()},
        "annual_opex_usd": round(total_opex),
        "opex_breakdown": {k: round(v) for k, v in opex_breakdown.items()},
        "cost_per_m3": round(lcow, 3),
        "annual_water_m3": round(annual_water_m3),
        "payback_years": round(total_capex / total_opex, 1) if total_opex > 0 else None
    }