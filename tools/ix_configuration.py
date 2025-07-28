"""
Ion Exchange Configuration Tool

Performs hydraulic sizing and flowsheet selection for ion exchange systems.
This tool focuses ONLY on vessel sizing and hydraulic calculations.
Economics, breakthrough predictions, and regeneration analysis are handled
by the simulation tool.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple, Any
from .schemas import (
    IXConfigurationInput, 
    IXConfigurationOutput,
    IXMultiConfigurationOutput,
    VesselConfiguration,
    DegasserConfiguration,
    MCASWaterComposition
)
# Economics calculation moved to simulation tool

logger = logging.getLogger(__name__)

# Resin properties for hydraulic sizing
# 
# IMPORTANT: Freeboard Requirements and Resin Swelling Behavior
# 
# WAC (Weak Acid Cation) Resins:
# - Swell significantly when converting from H+ form (regenerated) to Na+ form (exhausted)
# - Gel-type WAC resins can swell up to 90% in volume
# - Macroporous WAC resins swell up to 60% in volume
# - Require 125% freeboard (vessel height = 2.25 × bed depth) to accommodate:
#   a) Swelling during service cycle (H+ → Na+ conversion)
#   b) Bed expansion during backwash (typically 50% expansion)
#   c) Safety margin for operational variations
# 
# SAC (Strong Acid Cation) Resins:
# - Behave opposite to WAC resins
# - Are most swollen in H+ form (regenerated state)
# - Contract when loading with Na+, Ca2+, Mg2+ during service
# - Require 100% freeboard (vessel height = 2.0 × bed depth) to accommodate:
#   a) Bed expansion during backwash (typically 50% expansion)
#   b) Less swelling concern during service cycle
# 
# The freeboard_percent value represents freeboard height as a percentage of bed depth
# Example: 125% freeboard means freeboard height = 1.25 × bed depth
#
RESIN_PROPERTIES = {
    "SAC": {
        "exchange_capacity_eq_L": 2.0,  # eq/L of resin
        "operating_capacity_factor": 0.6,  # Without Na+ competition
        "max_bed_volume_per_hour": 16.0,
        "max_linear_velocity_m_hr": 25.0,
        "min_bed_depth_m": 0.75,
        "freeboard_percent": 100.0,  # SAC resins are most swollen in H+ form, less swelling concern
        "particle_size_mm": 0.6
    },
    "WAC_H": {
        "exchange_capacity_eq_L": 4.0,  # Higher capacity than SAC
        "operating_capacity_factor": 0.7,
        "max_bed_volume_per_hour": 16.0,
        "max_linear_velocity_m_hr": 25.0,
        "min_bed_depth_m": 0.75,
        "freeboard_percent": 125.0,
        "particle_size_mm": 0.5
    },
    "WAC_Na": {
        "exchange_capacity_eq_L": 4.0,
        "operating_capacity_factor": 0.7,
        "max_bed_volume_per_hour": 16.0,
        "max_linear_velocity_m_hr": 25.0,
        "min_bed_depth_m": 0.75,
        "freeboard_percent": 125.0,
        "particle_size_mm": 0.5
    }
}

# Degasser design parameters
DEGASSER_PARAMETERS = {
    "hydraulic_loading_m_hr": 40.0,
    "air_water_ratio": 45.0,  # m³ air per m³ water
    "fan_discharge_pressure_mbar": 100.0,
    "packing_height_transfer_units": 3.0,  # NTU for 90% removal
    "height_of_transfer_unit_m": 0.6,  # HTU for pall rings
    "fan_efficiency": 0.75,
    "motor_efficiency": 0.92
}


def calculate_na_competition_factor(water: MCASWaterComposition) -> float:
    """
    Calculate capacity reduction factor due to Na+ competition.
    
    Based on selectivity coefficients and competitive ion exchange theory.
    Returns a factor between 0 and 1 to multiply with base capacity.
    """
    # Get ion concentrations in meq/L
    ca_mg_L = water.ion_concentrations_mg_L.get("Ca_2+", 0)
    mg_mg_L = water.ion_concentrations_mg_L.get("Mg_2+", 0)
    na_mg_L = water.ion_concentrations_mg_L.get("Na_+", 0)
    
    # Convert to meq/L
    ca_meq_L = ca_mg_L / 20.04  # MW/charge for Ca
    mg_meq_L = mg_mg_L / 12.15  # MW/charge for Mg
    na_meq_L = na_mg_L / 22.99  # MW/charge for Na
    
    total_hardness_meq_L = ca_meq_L + mg_meq_L
    
    if total_hardness_meq_L == 0:
        return 0.0  # No hardness to remove
    
    # Selectivity coefficients (approximate)
    # K_Ca/Na ≈ 5.0, K_Mg/Na ≈ 3.0 for strong acid cation resin
    K_Ca_Na = 5.0
    K_Mg_Na = 3.0
    
    # Separation factor calculation
    if na_meq_L > 0:
        # Weighted average selectivity
        avg_selectivity = (ca_meq_L * K_Ca_Na + mg_meq_L * K_Mg_Na) / total_hardness_meq_L
        
        # Competition factor based on selectivity and Na/hardness ratio
        na_hardness_ratio = na_meq_L / total_hardness_meq_L
        
        # Empirical correlation for capacity reduction
        # Higher Na+ reduces effective capacity
        competition_factor = 1.0 / (1.0 + na_hardness_ratio / avg_selectivity)
        
        # Additional reduction for very high Na+ levels
        if na_hardness_ratio > 10:
            competition_factor *= 0.85  # Further 15% reduction
        
        return max(0.3, competition_factor)  # Minimum 30% capacity
    else:
        return 1.0  # No Na+ competition


def select_flowsheet(water: MCASWaterComposition) -> Tuple[str, str, List[str]]:
    """
    Select appropriate flowsheet based on water chemistry.
    Kept for backward compatibility with existing code.
    
    Returns:
        - flowsheet_type: Type identifier
        - description: Human-readable description
        - stages: List of treatment stages in order
    """
    # Calculate key water quality parameters
    total_hardness = water.get_total_hardness_mg_L_CaCO3()
    alkalinity = water.get_alkalinity_mg_L_CaCO3()
    
    # Calculate temporary and permanent hardness
    temporary_hardness = min(total_hardness, alkalinity)
    permanent_hardness = max(0, total_hardness - alkalinity)
    
    # Temporary hardness fraction
    if total_hardness > 0:
        temp_fraction = temporary_hardness / total_hardness
    else:
        temp_fraction = 0
    
    logger.info(f"Water chemistry analysis: TH={total_hardness:.0f}, "
               f"Alk={alkalinity:.0f}, Temp={temporary_hardness:.0f}, "
               f"Perm={permanent_hardness:.0f} mg/L as CaCO3")
    
    # Flowsheet selection logic
    if temp_fraction >= 0.9 and permanent_hardness < 50:
        # Mostly temporary hardness - use H-WAC
        return (
            "h_wac_degasser_na_wac",
            "H-WAC → Degasser → Na-WAC (for mostly temporary hardness)",
            ["H-WAC", "Degasser", "Na-WAC"]
        )
    elif temp_fraction < 0.5 or permanent_hardness > 100:
        # Significant permanent hardness - need SAC
        return (
            "sac_na_wac_degasser",
            "SAC → Na-WAC → Degasser (for mixed hardness types)",
            ["SAC", "Na-WAC", "Degasser"]
        )
    else:
        # Simple systems with moderate hardness
        return (
            "na_wac_degasser",
            "Na-WAC → Degasser (for simple water chemistry)",
            ["Na-WAC", "Degasser"]
        )


def get_all_flowsheet_configurations() -> List[Tuple[str, str, List[str], Dict[str, Any]]]:
    """
    Get all available flowsheet configurations with their characteristics.
    
    Returns:
        List of tuples containing:
        - flowsheet_type: Type identifier
        - description: Human-readable description
        - stages: List of treatment stages in order
        - characteristics: Dict with suitability info
    """
    return [
        (
            "h_wac_degasser_na_wac",
            "H-WAC → Degasser → Na-WAC (for mostly temporary hardness)",
            ["H-WAC", "Degasser", "Na-WAC"],
            {
                "best_for": ">90% temporary hardness",
                "hardness_removal": "Excellent for temporary, limited for permanent",
                "complexity": "High",
                "chemical_usage": "Lowest (acid regeneration)",
                "waste_volume": "Moderate"
            }
        ),
        (
            "sac_na_wac_degasser",
            "SAC → Na-WAC → Degasser (for mixed hardness types)",
            ["SAC", "Na-WAC", "Degasser"],
            {
                "best_for": "Mixed permanent/temporary hardness",
                "hardness_removal": "Excellent for all hardness types",
                "complexity": "High",
                "chemical_usage": "Highest (salt + acid)",
                "waste_volume": "Highest"
            }
        ),
        (
            "na_wac_degasser",
            "Na-WAC → Degasser (for simple water chemistry)",
            ["Na-WAC", "Degasser"],
            {
                "best_for": "Moderate hardness, simple treatment",
                "hardness_removal": "Good for temporary, none for permanent",
                "complexity": "Low",
                "chemical_usage": "Low (salt regeneration)",
                "waste_volume": "Low"
            }
        )
    ]


def size_ix_vessel(
    flow_m3_hr: float,
    resin_type: str,
    hardness_to_remove_meq_L: float,
    competition_factor: float,
    max_diameter_m: float = 2.4
) -> VesselConfiguration:
    """
    Size ion exchange vessels based on hydraulic constraints.
    
    Uses 16 BV/hr service flow rate and 25 m/hr linear velocity.
    Includes N+1 redundancy and appropriate freeboard:
    - WAC resins: 125% freeboard to accommodate H+ to Na+ swelling
    - SAC resins: 100% freeboard (less swelling concern)
    """
    resin_props = RESIN_PROPERTIES[resin_type]
    
    # Calculate required resin volume based on BV/hr
    bed_volumes_per_hour = resin_props["max_bed_volume_per_hour"]
    required_resin_volume_m3 = flow_m3_hr / bed_volumes_per_hour
    
    # Calculate vessel dimensions based on linear velocity
    linear_velocity_m_hr = resin_props["max_linear_velocity_m_hr"]
    required_area_m2 = flow_m3_hr / linear_velocity_m_hr
    
    # Determine number of vessels and size
    # Start with single vessel and increase if diameter exceeds limit
    for n_service in range(1, 10):
        area_per_vessel = required_area_m2 / n_service
        diameter = math.sqrt(4 * area_per_vessel / math.pi)
        
        if diameter <= max_diameter_m:
            break
    
    # Round diameter to practical size (0.1m increments)
    diameter_original = diameter  # Keep original for potential rounding up
    diameter = round(diameter * 10) / 10
    actual_area = math.pi * diameter**2 / 4
    
    # Verify linear velocity after rounding
    actual_linear_velocity = (flow_m3_hr / n_service) / actual_area
    if actual_linear_velocity > linear_velocity_m_hr:
        # Need to increase diameter slightly to stay within velocity limit
        diameter = math.ceil(diameter_original * 10) / 10  # Round up from original
        actual_area = math.pi * diameter**2 / 4
    
    # Calculate bed depth
    resin_volume_per_vessel = required_resin_volume_m3 / n_service
    bed_depth = resin_volume_per_vessel / actual_area
    
    # Ensure minimum bed depth
    if bed_depth < resin_props["min_bed_depth_m"]:
        bed_depth = resin_props["min_bed_depth_m"]
        resin_volume_per_vessel = bed_depth * actual_area
        required_resin_volume_m3 = resin_volume_per_vessel * n_service
    
    # Calculate freeboard
    # Freeboard percent represents the freeboard height as a percentage of bed depth
    # e.g., 125% means freeboard = 1.25 × bed depth (total vessel height = 2.25 × bed depth)
    # This is critical for WAC resins which swell significantly when converting from H+ to Na+ form
    freeboard_m = bed_depth * (resin_props["freeboard_percent"] / 100)
    
    # Total vessel height
    # Include space for bottom distributor/support (0.3m) and top distributor/nozzles (0.2m)
    vessel_height = bed_depth + freeboard_m + 0.3 + 0.2  # Bottom + top distribution systems
    
    # Add standby vessel (N+1 redundancy)
    n_standby = 1
    
    return VesselConfiguration(
        resin_type=resin_type,
        number_service=n_service,
        number_standby=n_standby,
        diameter_m=diameter,
        bed_depth_m=round(bed_depth, 2),
        freeboard_m=round(freeboard_m, 2),
        resin_volume_m3=round(required_resin_volume_m3, 2),
        vessel_height_m=round(vessel_height, 2)
    )


def size_degasser(flow_m3_hr: float) -> DegasserConfiguration:
    """
    Size CO2 degasser based on hydraulic loading and air requirements.
    
    Uses 40 m/hr hydraulic loading, 45:1 air/water ratio,
    and 100 mbar fan discharge pressure.
    """
    params = DEGASSER_PARAMETERS
    
    # Calculate tower diameter based on hydraulic loading
    hydraulic_loading = params["hydraulic_loading_m_hr"]
    required_area = flow_m3_hr / hydraulic_loading
    diameter = math.sqrt(4 * required_area / math.pi)
    
    # Round to practical size (0.1m increments)
    diameter = round(diameter * 10) / 10
    
    # Calculate packing height
    ntu = params["packing_height_transfer_units"]
    htu = params["height_of_transfer_unit_m"]
    packed_height = ntu * htu
    
    # Calculate air flow
    air_flow_m3_hr = flow_m3_hr * params["air_water_ratio"]
    
    # Calculate fan power (simplified)
    # Power = Q * ΔP / (3600 * η_fan * η_motor)
    pressure_pa = params["fan_discharge_pressure_mbar"] * 100  # Convert to Pa
    fan_power_kW = (air_flow_m3_hr * pressure_pa) / (
        3600 * 1000 * params["fan_efficiency"] * params["motor_efficiency"]
    )
    
    return DegasserConfiguration(
        type="packed_tower",
        packing="pall_rings",
        diameter_m=diameter,
        packed_height_m=round(packed_height, 1),
        hydraulic_loading_m_hr=hydraulic_loading,
        air_flow_m3_hr=round(air_flow_m3_hr, 0),
        fan_discharge_pressure_mbar=params["fan_discharge_pressure_mbar"],
        fan_power_kW=round(fan_power_kW, 1)
    )


def optimize_ix_configuration_single(input_data: IXConfigurationInput, flowsheet_type: str, flowsheet_desc: str, stages: List[str]) -> IXConfigurationOutput:
    """
    Generate configuration for a single flowsheet option.
    Internal function used by optimize_ix_configuration.
    """
    water = input_data.water_analysis
    max_diameter = input_data.max_vessel_diameter_m
    
    # Calculate Na+ competition factor (used internally for sizing)
    competition_factor = calculate_na_competition_factor(water)
    
    # Size vessels for each stage
    ix_vessels = {}
    
    # Get water chemistry for sizing
    total_hardness = water.get_total_hardness_mg_L_CaCO3()
    alkalinity = water.get_alkalinity_mg_L_CaCO3()
    
    # Convert to meq/L
    total_hardness_meq_L = total_hardness / 50.045
    alkalinity_meq_L = alkalinity / 50.045
    
    for stage in stages:
        if stage != "Degasser":
            # Map stage name to resin type
            if stage == "H-WAC":
                resin_type = "WAC_H"
                # H-WAC removes temporary hardness
                hardness_to_remove = min(total_hardness_meq_L, alkalinity_meq_L)
            elif stage == "Na-WAC":
                resin_type = "WAC_Na"
                # Na-WAC depends on position in flowsheet
                if "SAC" in stages:
                    # After SAC, mainly for alkalinity adjustment
                    hardness_to_remove = 0.2  # Minimal hardness leakage
                else:
                    # Primary softening
                    hardness_to_remove = min(total_hardness_meq_L, alkalinity_meq_L)
            else:
                # SAC removes all hardness
                resin_type = stage  # SAC
                hardness_to_remove = total_hardness_meq_L
            
            vessel_config = size_ix_vessel(
                flow_m3_hr=water.flow_m3_hr,
                resin_type=resin_type,
                hardness_to_remove_meq_L=hardness_to_remove,
                competition_factor=competition_factor,
                max_diameter_m=max_diameter
            )
            
            ix_vessels[stage] = vessel_config
            
            # Vessel sizing complete
    
    # Size degasser
    degasser_config = size_degasser(water.flow_m3_hr)
    
    # Calculate hydraulic summary
    total_vessels_service = sum(v.number_service for v in ix_vessels.values())
    total_vessels_standby = sum(v.number_standby for v in ix_vessels.values())
    
    hydraulics = {
        "bed_volumes_per_hour": 16.0,
        "linear_velocity_m_hr": 25.0,
        "total_vessels_service": total_vessels_service,
        "total_vessels_standby": total_vessels_standby,
        "total_resin_volume_m3": sum(v.resin_volume_m3 for v in ix_vessels.values()),
        "degasser_hydraulic_loading_m_hr": DEGASSER_PARAMETERS["hydraulic_loading_m_hr"],
        "air_water_ratio": DEGASSER_PARAMETERS["air_water_ratio"],
        "feed_flow_m3_hr": water.flow_m3_hr  # Add flow for economics calculation
    }
    
    # Na+ competition factor is used internally for sizing calculations
    
    # Create configuration object
    return IXConfigurationOutput(
        flowsheet_type=flowsheet_type,
        flowsheet_description=flowsheet_desc,
        ix_vessels=ix_vessels,
        degasser=degasser_config,
        hydraulics=hydraulics
    )


# Legacy single configuration function removed - use optimize_ix_configuration (multi-config) instead


def optimize_ix_configuration(input_data: IXConfigurationInput) -> IXMultiConfigurationOutput:
    """
    Generate vessel sizing for ALL three ion exchange flowsheet options.
    
    This tool performs ONLY hydraulic sizing calculations:
    - Vessel dimensions based on flow rates and hydraulic constraints
    - Number of vessels needed (service + standby)
    - Resin volumes based on bed depths
    - Degasser tower sizing
    
    Does NOT calculate:
    - Economics (CAPEX/OPEX) - handled by simulation tool
    - Breakthrough times - requires PHREEQC simulation
    - Regenerant consumption - requires mass balance simulation
    - Operating capacity - requires competitive ion exchange modeling
    
    Returns all three flowsheet options with hydraulic sizing only.
    """
    water = input_data.water_analysis
    
    # Calculate water chemistry parameters
    total_hardness = water.get_total_hardness_mg_L_CaCO3()
    alkalinity = water.get_alkalinity_mg_L_CaCO3()
    temporary_hardness = min(total_hardness, alkalinity)
    permanent_hardness = max(0, total_hardness - alkalinity)
    
    # Prepare water chemistry analysis
    water_chemistry_analysis = {
        "total_hardness_mg_L_CaCO3": round(total_hardness, 1),
        "alkalinity_mg_L_CaCO3": round(alkalinity, 1),
        "temporary_hardness_mg_L_CaCO3": round(temporary_hardness, 1),
        "permanent_hardness_mg_L_CaCO3": round(permanent_hardness, 1),
        "temporary_hardness_fraction": round(temporary_hardness / total_hardness, 2) if total_hardness > 0 else 0,
        "na_concentration_mg_L": round(water.ion_concentrations_mg_L.get("Na_+", 0), 1)
    }
    
    # Get all flowsheet configurations
    all_flowsheets = get_all_flowsheet_configurations()
    configurations = []
    
    # Generate configuration for each flowsheet
    for flowsheet_type, flowsheet_desc, stages, characteristics in all_flowsheets:
        try:
            config = optimize_ix_configuration_single(
                input_data=input_data,
                flowsheet_type=flowsheet_type,
                flowsheet_desc=flowsheet_desc,
                stages=stages
            )
            configurations.append(config)
            logger.info(f"Generated configuration for {flowsheet_type}")
        except Exception as e:
            logger.error(f"Error generating configuration for {flowsheet_type}: {str(e)}")
            # Continue with other configurations
    
    # Prepare summary and recommendations
    summary = {
        "feed_flow_m3_hr": water.flow_m3_hr,
        "configurations_generated": len(configurations),
        "recommended_flowsheet": None,
        "recommendation_reason": None
    }
    
    # Determine recommended flowsheet based on water chemistry
    if water_chemistry_analysis["temporary_hardness_fraction"] >= 0.9:
        summary["recommended_flowsheet"] = "h_wac_degasser_na_wac"
        summary["recommendation_reason"] = "High temporary hardness fraction (≥90%)"
    elif water_chemistry_analysis["permanent_hardness_mg_L_CaCO3"] > 100:
        summary["recommended_flowsheet"] = "sac_na_wac_degasser"
        summary["recommendation_reason"] = "Significant permanent hardness (>100 mg/L)"
    else:
        summary["recommended_flowsheet"] = "na_wac_degasser"
        summary["recommendation_reason"] = "Simple water chemistry with moderate hardness"
    
    
    return IXMultiConfigurationOutput(
        status="success",
        configurations=configurations,
        summary=summary,
        water_chemistry_analysis=water_chemistry_analysis
    )