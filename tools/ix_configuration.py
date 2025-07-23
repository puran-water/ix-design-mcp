"""
Ion Exchange Configuration Tool

Performs hydraulic sizing and flowsheet selection for ion exchange systems
with Na+ competition awareness. This tool focuses on hydraulic calculations
and configuration, NOT simulation or regeneration analysis.
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
from .ix_economics import calculate_ix_economics

logger = logging.getLogger(__name__)

# Resin properties for hydraulic sizing
RESIN_PROPERTIES = {
    "SAC": {
        "exchange_capacity_eq_L": 2.0,  # eq/L of resin
        "operating_capacity_factor": 0.6,  # Without Na+ competition
        "max_bed_volume_per_hour": 16.0,
        "max_linear_velocity_m_hr": 25.0,
        "min_bed_depth_m": 0.75,
        "freeboard_percent": 125.0,
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
    Includes N+1 redundancy and 125% freeboard.
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
    freeboard_m = bed_depth * (resin_props["freeboard_percent"] / 100 - 1)
    
    # Total vessel height
    vessel_height = bed_depth + freeboard_m + 0.5  # 0.5m for distributors
    
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


def optimize_ix_configuration_single(input_data: IXConfigurationInput, flowsheet_type: str, flowsheet_desc: str, stages: List[str], characteristics: Dict[str, Any]) -> IXConfigurationOutput:
    """
    Generate configuration for a single flowsheet option.
    Internal function used by optimize_ix_configuration.
    """
    water = input_data.water_analysis
    max_diameter = input_data.max_vessel_diameter_m
    
    # Calculate Na+ competition factor
    competition_factor = calculate_na_competition_factor(water)
    
    # Calculate effective resin capacities with Na+ competition
    effective_capacity = {}
    for resin_type, props in RESIN_PROPERTIES.items():
        base_capacity = props["exchange_capacity_eq_L"] * props["operating_capacity_factor"]
        
        if resin_type == "SAC":
            # SAC is most affected by Na+ competition
            effective_capacity[resin_type] = base_capacity * competition_factor
        elif resin_type.startswith("WAC"):
            # WAC is less affected, but still some impact
            effective_capacity[resin_type] = base_capacity * (0.7 + 0.3 * competition_factor)
        else:
            effective_capacity[resin_type] = base_capacity
    
    # Size vessels for each stage
    ix_vessels = {}
    warnings = []
    
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
            
            # Check if vessels are getting too large
            if vessel_config.diameter_m >= max_diameter * 0.95:
                warnings.append(
                    f"{stage} vessels near maximum diameter ({vessel_config.diameter_m:.1f}m). "
                    f"Consider multiple trains for larger flows."
                )
    
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
    
    # Add Na+ competition warning if significant
    if competition_factor < 0.5:
        warnings.append(
            f"High Na+ competition detected (factor={competition_factor:.2f}). "
            f"Consider pre-treatment for Na+ reduction or adjust regeneration levels."
        )
    
    # Create configuration object
    config = IXConfigurationOutput(
        flowsheet_type=flowsheet_type,
        flowsheet_description=flowsheet_desc,
        na_competition_factor=round(competition_factor, 3),
        effective_capacity=effective_capacity,
        ix_vessels=ix_vessels,
        degasser=degasser_config,
        hydraulics=hydraulics,
        warnings=warnings if warnings else None,
        characteristics=characteristics,
        economics=None  # Will be calculated next
    )
    
    # Calculate economics
    try:
        economics = calculate_ix_economics(config)
        config.economics = economics
    except Exception as e:
        logger.warning(f"Economics calculation failed: {str(e)}")
        # Provide simplified economics if detailed calculation fails
        config.economics = {
            "capital_cost_usd": len(ix_vessels) * 200000,  # Rough estimate
            "annual_opex_usd": len(ix_vessels) * 50000,
            "cost_per_m3": 0.5,
            "note": "Simplified estimate - detailed calculation failed"
        }
    
    return config


def optimize_ix_configuration(input_data: IXConfigurationInput) -> IXMultiConfigurationOutput:
    """
    Optimize ion exchange system configuration for RO pretreatment.
    
    Performs hydraulic sizing and flowsheet selection based on water chemistry,
    accounting for Na+ competition effects on resin capacity. Designed for
    industrial wastewater ZLD applications.
    
    Args:
        input_data: IXConfigurationInput containing:
            - water_analysis: MCASWaterComposition with feed water quality
            - max_vessel_diameter_m: Maximum vessel diameter (default 2.4m)
            - target_treated_quality: Optional treatment targets
    
    Water Composition Requirements:
        The water_analysis must include ion concentrations in MCAS format.
        
        Accepted ions (use exact notation):
        - Cations: Na_+, Ca_2+, Mg_2+, K_+, H_+, NH4_+, Fe_2+, Fe_3+
        - Anions: Cl_-, SO4_2-, HCO3_-, CO3_2-, NO3_-, PO4_3-, F_-, OH_-
        - Neutrals: CO2, H2O, SiO2, B(OH)3
        
        Example water composition:
        {
            "flow_m3_hr": 100.0,
            "temperature_celsius": 25.0,
            "pressure_bar": 4.0,
            "pH": 7.8,
            "ion_concentrations_mg_L": {
                "Na_+": 500.0,      # Sodium (affects IX capacity)
                "Ca_2+": 120.0,     # Calcium (hardness)
                "Mg_2+": 48.0,      # Magnesium (hardness)
                "K_+": 10.0,        # Potassium
                "Cl_-": 800.0,      # Chloride
                "SO4_2-": 240.0,    # Sulfate
                "HCO3_-": 180.0,    # Bicarbonate (alkalinity)
                "NO3_-": 5.0,       # Nitrate
                "SiO2": 25.0        # Silica (passes through IX)
            }
        }
        
        Note: Non-standard ions will generate warnings but won't cause errors.
        They will be ignored for IX calculations but passed through for transparency.
    
    Returns:
        IXConfigurationOutput containing:
        - flowsheet_type: Selected configuration (e.g., "sac_na_wac_degasser")
        - flowsheet_description: Human-readable description
        - na_competition_factor: Capacity reduction due to Na+ (0-1)
        - effective_capacity: Adjusted resin capacities
        - ix_vessels: Vessel configurations for each stage
        - degasser: CO2 stripping tower configuration
        - hydraulics: Flow and velocity parameters
        - warnings: Any operational concerns
    
    Design Basis:
        - Service flow: 16 BV/hr (bed volumes per hour)
        - Linear velocity: 25 m/hr maximum
        - Redundancy: N+1 vessels (one standby)
        - Freeboard: 125% of bed depth
        - Degasser: 40 m/hr loading, 45:1 air/water ratio
    
    Flowsheet Selection Logic:
        1. H-WAC → Degasser → Na-WAC: For >90% temporary hardness
        2. SAC → Na-WAC → Degasser: For significant permanent hardness
        3. Na-WAC → Degasser: For simple water chemistry
    
    Na+ Competition Model:
        - Uses selectivity coefficients: K_Ca/Na ≈ 5.0, K_Mg/Na ≈ 3.0
        - Competition factor = 1/(1 + Na_hardness_ratio/avg_selectivity)
        - Minimum capacity retained: 30% (even at very high Na+)
    """
    water = input_data.water_analysis
    max_diameter = input_data.max_vessel_diameter_m
    
    # Calculate Na+ competition factor
    competition_factor = calculate_na_competition_factor(water)
    logger.info(f"Na+ competition factor: {competition_factor:.2f}")
    
    # Select flowsheet based on water chemistry
    flowsheet_type, flowsheet_desc, stages = select_flowsheet(water)
    logger.info(f"Selected flowsheet: {flowsheet_type}")
    
    # Calculate effective resin capacities with Na+ competition
    effective_capacity = {}
    for resin_type, props in RESIN_PROPERTIES.items():
        base_capacity = props["exchange_capacity_eq_L"] * props["operating_capacity_factor"]
        if resin_type == "SAC":
            # SAC is most affected by Na+ competition
            effective_capacity[resin_type] = base_capacity * competition_factor
        else:
            # WAC less affected but still some impact
            effective_capacity[resin_type] = base_capacity * (0.5 + 0.5 * competition_factor)
    
    # Size vessels for each stage
    ix_vessels = {}
    flow_m3_hr = water.flow_m3_hr
    
    # Get hardness values
    total_hardness = water.get_total_hardness_mg_L_CaCO3()
    alkalinity = water.get_alkalinity_mg_L_CaCO3()
    
    # Convert to meq/L for sizing calculations
    total_hardness_meq_L = total_hardness / 50.045
    alkalinity_meq_L = alkalinity / 50.045
    
    for stage in stages:
        if stage == "SAC":
            # SAC removes all cations (total hardness)
            hardness_to_remove = total_hardness_meq_L
            vessel_config = size_ix_vessel(
                flow_m3_hr, "SAC", hardness_to_remove, 
                competition_factor, max_diameter
            )
            ix_vessels["SAC"] = vessel_config
            
        elif stage == "H-WAC":
            # H-WAC removes temporary hardness (alkalinity)
            hardness_to_remove = min(total_hardness_meq_L, alkalinity_meq_L)
            vessel_config = size_ix_vessel(
                flow_m3_hr, "WAC_H", hardness_to_remove,
                competition_factor, max_diameter
            )
            ix_vessels["H-WAC"] = vessel_config
            
        elif stage == "Na-WAC":
            # Na-WAC for polishing or alkalinity adjustment
            if "SAC" in stages:
                # After SAC, mainly for alkalinity adjustment
                hardness_to_remove = 0.2  # Minimal hardness leakage
            else:
                # Primary softening
                hardness_to_remove = min(total_hardness_meq_L, alkalinity_meq_L)
            
            vessel_config = size_ix_vessel(
                flow_m3_hr, "WAC_Na", hardness_to_remove,
                competition_factor, max_diameter
            )
            ix_vessels["Na-WAC"] = vessel_config
    
    # Size degasser
    degasser_config = size_degasser(flow_m3_hr)
    
    # Calculate hydraulic parameters
    hydraulics = {
        "bed_volumes_per_hour": RESIN_PROPERTIES["SAC"]["max_bed_volume_per_hour"],
        "linear_velocity_m_hr": RESIN_PROPERTIES["SAC"]["max_linear_velocity_m_hr"],
        "total_resin_volume_m3": sum(v.resin_volume_m3 for v in ix_vessels.values()),
        "total_vessels": sum(v.number_service + v.number_standby for v in ix_vessels.values())
    }
    
    # Generate warnings
    warnings = []
    if competition_factor < 0.5:
        warnings.append(
            f"High Na+ levels detected. Resin capacity reduced to {competition_factor*100:.0f}% "
            "of nominal. Consider more frequent regenerations."
        )
    
    if water.get_tds_mg_L() > 10000:
        warnings.append(
            "High TDS water (>10,000 mg/L). Consider RO treatment instead of IX for better economics."
        )
    
    return IXConfigurationOutput(
        flowsheet_type=flowsheet_type,
        flowsheet_description=flowsheet_desc,
        na_competition_factor=round(competition_factor, 3),
        effective_capacity=effective_capacity,
        ix_vessels=ix_vessels,
        degasser=degasser_config,
        hydraulics=hydraulics,
        warnings=warnings if warnings else None
    )


def optimize_ix_configuration_all(input_data: IXConfigurationInput) -> IXMultiConfigurationOutput:
    """
    Generate ALL ion exchange system configurations (like RO server).
    
    Returns all three flowsheet options with sizing and characteristics,
    allowing the engineer to select based on their priorities.
    """
    water = input_data.water_analysis
    
    # Calculate water chemistry parameters
    total_hardness = water.get_total_hardness_mg_L_CaCO3()
    alkalinity = water.get_alkalinity_mg_L_CaCO3()
    temporary_hardness = min(total_hardness, alkalinity)
    permanent_hardness = max(0, total_hardness - alkalinity)
    
    # Calculate Na+ competition factor once for all configurations
    competition_factor = calculate_na_competition_factor(water)
    logger.info(f"Na+ competition factor: {competition_factor:.2f}")
    
    # Prepare water chemistry analysis
    water_chemistry_analysis = {
        "total_hardness_mg_L_CaCO3": round(total_hardness, 1),
        "alkalinity_mg_L_CaCO3": round(alkalinity, 1),
        "temporary_hardness_mg_L_CaCO3": round(temporary_hardness, 1),
        "permanent_hardness_mg_L_CaCO3": round(permanent_hardness, 1),
        "temporary_hardness_fraction": round(temporary_hardness / total_hardness, 2) if total_hardness > 0 else 0,
        "na_concentration_mg_L": round(water.ion_concentrations_mg_L.get("Na_+", 0), 1),
        "na_competition_factor": round(competition_factor, 3)
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
                stages=stages,
                characteristics=characteristics
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
    
    # Add Na+ competition warning to summary if needed
    if competition_factor < 0.5:
        summary["warning"] = (
            f"High Na+ competition detected (factor={competition_factor:.2f}). "
            "All configurations will have reduced capacity. Consider Na+ pre-treatment."
        )
    
    return IXMultiConfigurationOutput(
        status="success",
        configurations=configurations,
        summary=summary,
        water_chemistry_analysis=water_chemistry_analysis
    )