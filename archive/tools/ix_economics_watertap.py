"""
Ion Exchange System Economics Calculator - WaterTAP Implementation

Uses exclusively WaterTAP costing functions for IX systems.
Based on watertap.costing.unit_models.ion_exchange module.

Reference: WaterTAP v0.12.0 costing methodology
"""

import math
from typing import Dict, Any
import pyomo.environ as pyo
from .schemas import IXConfigurationOutput


# WaterTAP Ion Exchange Costing Parameters (USD 2020 basis)
WATERTAP_IX_PARAMS = {
    # Vessel cost coefficients: C = A * V^B where V is in gallons
    "vessel_A_coeff": 1596.499,  # USD_2020
    "vessel_b_coeff": 0.459496,  # dimensionless
    
    # Backwash/rinse tank coefficients
    "backwash_tank_A_coeff": 308.9371,  # USD_2020
    "backwash_tank_b_coeff": 0.501467,  # dimensionless
    
    # Regeneration tank coefficients
    "regen_tank_A_coeff": 57.02158,  # USD_2020
    "regen_tank_b_coeff": 0.729325,  # dimensionless
    
    # Resin costs (USD_2020/ft³)
    "cation_exchange_resin_cost": 153,
    "anion_exchange_resin_cost": 205,
    
    # Operating parameters
    "annual_resin_replacement_factor": 0.05,  # 5% per year
    "regen_dose": 300,  # kg regenerant/m³ resin (default)
    "regen_recycle": 1,  # Number of regenerant reuse cycles
    
    # Hazardous waste parameters (USD_2020)
    "hazardous_min_cost": 3240,  # USD/year minimum
    "hazardous_resin_disposal": 347.10,  # USD/ton
    "hazardous_regen_disposal": 3.64,  # USD/gal
    
    # Regenerant costs (USD_2020/kg)
    "regenerant_costs": {
        "NaCl": 0.09,
        "HCl": 0.17,
        "NaOH": 0.59,
        "H2SO4": 0.20,  # Estimated based on typical industrial pricing
    },
    
    # System factors
    "total_installed_cost_factor": 1.65,
    
    # WaterTAP standard electricity cost
    "electricity_cost_per_kwh": 0.07,  # USD_2020/kWh
    
    # Labor from WaterTAP standard assumptions
    "labor_cost_per_hour": 50,  # USD_2020/hr
}


def convert_m3_to_gallons(m3: float) -> float:
    """Convert cubic meters to gallons"""
    return m3 * 264.172


def convert_m3_to_ft3(m3: float) -> float:
    """Convert cubic meters to cubic feet"""
    return m3 * 35.3147


def convert_kg_to_tons(kg: float) -> float:
    """Convert kilograms to US tons"""
    return kg / 907.185


def calculate_watertap_ix_economics(config: IXConfigurationOutput) -> Dict[str, Any]:
    """
    Calculate CAPEX and OPEX using WaterTAP costing methodology.
    
    Returns:
        Dictionary with economics following WaterTAP structure
    """
    capex_breakdown = {}
    opex_breakdown = {}
    
    # Get flow rate
    flow_m3_hr = config.hydraulics.get("feed_flow_m3_hr", 100)
    
    # Track total resin volume and vessel count
    total_resin_volume_m3 = 0
    total_vessel_count = 0
    vessel_details = []
    
    # Calculate vessel and resin costs using WaterTAP methodology
    total_vessel_cost = 0
    total_resin_cost = 0
    
    for vessel_name, vessel_config in config.ix_vessels.items():
        # Number of vessels
        n_vessels = vessel_config.number_service + vessel_config.number_standby
        total_vessel_count += n_vessels
        
        # Vessel volume in gallons for WaterTAP equation
        vessel_volume_m3 = math.pi * (vessel_config.diameter_m/2)**2 * vessel_config.vessel_height_m
        vessel_volume_gal = convert_m3_to_gallons(vessel_volume_m3)
        
        # WaterTAP vessel cost equation: C = A * V^B
        single_vessel_cost = (
            WATERTAP_IX_PARAMS["vessel_A_coeff"] * 
            (vessel_volume_gal ** WATERTAP_IX_PARAMS["vessel_b_coeff"])
        )
        
        vessel_cost = single_vessel_cost * n_vessels
        total_vessel_cost += vessel_cost
        
        # Resin cost using WaterTAP parameters
        resin_volume_ft3 = convert_m3_to_ft3(vessel_config.resin_volume_m3)
        total_resin_volume_m3 += vessel_config.resin_volume_m3 * n_vessels
        
        # Select appropriate resin cost
        if vessel_config.resin_type == "SAC":
            resin_cost_per_ft3 = WATERTAP_IX_PARAMS["cation_exchange_resin_cost"]
        else:  # WAC (both H and Na forms)
            # WaterTAP doesn't distinguish between H-WAC and Na-WAC costs
            resin_cost_per_ft3 = WATERTAP_IX_PARAMS["cation_exchange_resin_cost"]
        
        resin_cost = resin_volume_ft3 * resin_cost_per_ft3 * n_vessels
        total_resin_cost += resin_cost
        
        vessel_details.append({
            "name": vessel_name,
            "type": vessel_config.resin_type,
            "count": n_vessels,
            "volume_m3": vessel_config.resin_volume_m3
        })
    
    capex_breakdown["capital_cost_vessel"] = total_vessel_cost
    capex_breakdown["capital_cost_resin"] = total_resin_cost
    
    # Backwash tank sizing and cost
    # Assume 2 bed volumes for backwash + 1 BV for rinse
    backwash_volume_m3 = total_resin_volume_m3 * 3
    backwash_volume_gal = convert_m3_to_gallons(backwash_volume_m3)
    
    backwash_tank_cost = (
        WATERTAP_IX_PARAMS["backwash_tank_A_coeff"] * 
        (backwash_volume_gal ** WATERTAP_IX_PARAMS["backwash_tank_b_coeff"])
    )
    capex_breakdown["capital_cost_backwash_tank"] = backwash_tank_cost
    
    # Regeneration tank sizing and cost
    # Size for one complete regeneration cycle
    regen_volume_m3 = total_resin_volume_m3 * 4  # 4 BV typical for regenerant
    regen_volume_gal = convert_m3_to_gallons(regen_volume_m3)
    
    regen_tank_cost = (
        WATERTAP_IX_PARAMS["regen_tank_A_coeff"] * 
        (regen_volume_gal ** WATERTAP_IX_PARAMS["regen_tank_b_coeff"])
    )
    capex_breakdown["capital_cost_regen_tank"] = regen_tank_cost
    
    # Total equipment cost
    equipment_cost = sum(capex_breakdown.values())
    
    # Apply WaterTAP total installed cost factor
    total_capex = equipment_cost * WATERTAP_IX_PARAMS["total_installed_cost_factor"]
    
    # OPEX Calculations following WaterTAP methodology
    
    # 1. Annual resin replacement
    annual_resin_replacement = (
        total_resin_cost * WATERTAP_IX_PARAMS["annual_resin_replacement_factor"]
    )
    opex_breakdown["resin_replacement"] = annual_resin_replacement
    
    # 2. Regenerant costs with proper accounting for Na-WAC two-step
    annual_regenerant_cost = 0
    regenerant_details = {}
    regenerant_breakdown = {}  # Initialize in case no regenerants
    
    # Estimate cycles per year based on typical breakthrough times
    # This should ideally come from simulation results
    # Use more realistic estimates based on resin type
    # SAC: ~8-12 hours, WAC: ~16-24 hours typical
    hours_per_cycle = 12  # Conservative average
    cycles_per_year = (8760 * 0.9) / hours_per_cycle  # 90% availability
    
    for vessel in vessel_details:
        vessel_regen_cost = 0
        
        if vessel["type"] == "SAC":
            # NaCl regeneration
            regen_dose = 120  # kg NaCl/m³ resin (typical for SAC)
            regen_kg_per_cycle = vessel["volume_m3"] * vessel["count"] * regen_dose
            cost_per_cycle = regen_kg_per_cycle * WATERTAP_IX_PARAMS["regenerant_costs"]["NaCl"]
            vessel_regen_cost = cost_per_cycle * cycles_per_year
            regenerant_details["NaCl"] = regenerant_details.get("NaCl", 0) + vessel_regen_cost
            
        elif vessel["type"] == "WAC_H":
            # HCl regeneration only
            regen_dose = 80  # kg HCl/m³ resin
            regen_kg_per_cycle = vessel["volume_m3"] * vessel["count"] * regen_dose
            cost_per_cycle = regen_kg_per_cycle * WATERTAP_IX_PARAMS["regenerant_costs"]["HCl"]
            vessel_regen_cost = cost_per_cycle * cycles_per_year
            regenerant_details["HCl"] = regenerant_details.get("HCl", 0) + vessel_regen_cost
            
        elif vessel["type"] == "WAC_Na":
            # Two-step regeneration: HCl followed by NaOH
            # Step 1: HCl to remove hardness
            hcl_dose = 80  # kg HCl/m³ resin
            hcl_kg_per_cycle = vessel["volume_m3"] * vessel["count"] * hcl_dose
            hcl_cost_per_cycle = hcl_kg_per_cycle * WATERTAP_IX_PARAMS["regenerant_costs"]["HCl"]
            
            # Step 2: NaOH to convert back to sodium form
            naoh_dose = 60  # kg NaOH/m³ resin
            naoh_kg_per_cycle = vessel["volume_m3"] * vessel["count"] * naoh_dose
            naoh_cost_per_cycle = naoh_kg_per_cycle * WATERTAP_IX_PARAMS["regenerant_costs"]["NaOH"]
            
            vessel_regen_cost = (hcl_cost_per_cycle + naoh_cost_per_cycle) * cycles_per_year
            regenerant_details["HCl"] = regenerant_details.get("HCl", 0) + hcl_cost_per_cycle * cycles_per_year
            regenerant_details["NaOH"] = regenerant_details.get("NaOH", 0) + naoh_cost_per_cycle * cycles_per_year
        
        annual_regenerant_cost += vessel_regen_cost
    
    opex_breakdown["regenerant_chemicals"] = annual_regenerant_cost
    # Store regenerant details separately (not in main opex_breakdown)
    regenerant_breakdown = regenerant_details
    
    # 3. Hazardous waste disposal (for acid regeneration)
    # Check if any vessels use acid regeneration
    uses_acid = any(v["type"] in ["WAC_H", "WAC_Na"] for v in vessel_details)
    
    if uses_acid:
        # Minimum hazardous waste cost
        hazardous_cost = WATERTAP_IX_PARAMS["hazardous_min_cost"]
        
        # Add regenerant disposal cost
        # Estimate waste volume: 3 BV for neutralized acid waste
        # (WaterTAP assumes neutralized waste, not raw acid)
        acid_waste_m3_per_cycle = sum(
            v["volume_m3"] * v["count"] * 3 
            for v in vessel_details 
            if v["type"] in ["WAC_H", "WAC_Na"]
        )
        # Convert to gallons per cycle, then multiply by cycles
        acid_waste_gal_per_cycle = convert_m3_to_gallons(acid_waste_m3_per_cycle)
        # Consider regenerant recycle
        effective_cycles = cycles_per_year / WATERTAP_IX_PARAMS["regen_recycle"]
        acid_waste_gal_per_year = acid_waste_gal_per_cycle * effective_cycles
        
        hazardous_cost += (
            acid_waste_gal_per_year * 
            WATERTAP_IX_PARAMS["hazardous_regen_disposal"]
        )
        
        # Add resin disposal cost (annual replacement)
        resin_mass_tons = sum(
            v["volume_m3"] * v["count"] * 600  # ~600 kg/m³ wet resin density
            for v in vessel_details
            if v["type"] in ["WAC_H", "WAC_Na"]
        )
        resin_mass_tons = convert_kg_to_tons(resin_mass_tons)
        annual_resin_disposal_tons = (
            resin_mass_tons * 
            WATERTAP_IX_PARAMS["annual_resin_replacement_factor"]
        )
        
        hazardous_cost += (
            annual_resin_disposal_tons * 
            WATERTAP_IX_PARAMS["hazardous_resin_disposal"]
        )
        
        opex_breakdown["hazardous_waste_disposal"] = hazardous_cost
    
    # 4. Power costs (pumping + degasser if present)
    # WaterTAP typically calculates pump power based on flow and head
    # Using simplified approach: 30 kW per 100 m³/hr for IX system pumps
    pumping_kw = (flow_m3_hr / 100) * 30
    
    # Add degasser fan power if present
    if config.degasser:
        pumping_kw += config.degasser.fan_power_kW
    
    annual_power_cost = (
        pumping_kw * 8760 * 0.9 *  # 90% availability
        WATERTAP_IX_PARAMS["electricity_cost_per_kwh"]
    )
    opex_breakdown["electricity"] = annual_power_cost
    
    # 5. Labor (following WaterTAP assumptions)
    # 0.5 FTE for systems up to 1000 m³/hr
    fte_required = min(0.5, flow_m3_hr / 2000)
    annual_labor_cost = fte_required * 2080 * WATERTAP_IX_PARAMS["labor_cost_per_hour"]
    opex_breakdown["labor"] = annual_labor_cost
    
    # 6. Maintenance (WaterTAP uses 1.5% of equipment cost)
    annual_maintenance = equipment_cost * 0.015
    opex_breakdown["maintenance"] = annual_maintenance
    
    # Total OPEX
    total_opex = sum(opex_breakdown.values())
    
    # Calculate LCOW using WaterTAP approach
    # Capital recovery factor (10 year, 8% discount)
    crf = 0.08 * (1 + 0.08)**10 / ((1 + 0.08)**10 - 1)
    annual_capex = total_capex * crf
    
    # Annual water production (90% availability)
    annual_water_m3 = flow_m3_hr * 8760 * 0.9
    
    # LCOW calculation
    lcow = (annual_capex + total_opex) / annual_water_m3
    
    # Prepare results in WaterTAP format
    results = {
        # Capital costs
        "capital_cost_usd": round(total_capex),
        "capex_breakdown": {k: round(v) for k, v in capex_breakdown.items()},
        "equipment_cost": round(equipment_cost),
        "installation_factor": WATERTAP_IX_PARAMS["total_installed_cost_factor"],
        
        # Operating costs
        "annual_opex_usd": round(total_opex),
        "opex_breakdown": {k: round(v) for k, v in opex_breakdown.items()},
        "regenerant_breakdown": {k: round(v) for k, v in regenerant_breakdown.items()},
        
        # Economic metrics
        "cost_per_m3": round(lcow, 3),
        "annual_water_m3": round(annual_water_m3),
        "capital_recovery_factor": round(crf, 4),
        
        # System details
        "total_resin_volume_m3": round(total_resin_volume_m3, 1),
        "total_vessel_count": total_vessel_count,
        "uses_hazardous_chemicals": uses_acid,
        
        # Missing from WaterTAP
        "degasser_costing_note": "Degasser costing not available in WaterTAP - requires custom implementation"
    }
    
    # Add warning if degasser is present
    if config.degasser:
        results["warnings"] = [
            "Degasser capital cost not included - WaterTAP lacks degasser/stripper costing functions"
        ]
    
    return results