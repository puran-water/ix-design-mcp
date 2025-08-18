"""
WAC Ion Exchange Configuration Tool

Performs hydraulic sizing for WAC (Weak Acid Cation) vessels.
Supports both Na-form and H-form WAC resins.
"""

import math
import logging
import json
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from pathlib import Path

# Import centralized configuration
from .core_config import CONFIG

logger = logging.getLogger(__name__)


class WACWaterComposition(BaseModel):
    """Water composition with alkalinity emphasis for WAC"""
    # Required parameters
    flow_m3_hr: float = Field(..., description="Feed water flow rate")
    ca_mg_l: float = Field(..., description="Calcium (required)")
    mg_mg_l: float = Field(..., description="Magnesium (required)")
    na_mg_l: float = Field(..., description="Sodium (required)")
    hco3_mg_l: float = Field(..., description="Bicarbonate/Alkalinity (required for WAC)")
    pH: float = Field(..., description="pH (required)")
    
    # Optional parameters with defaults
    temperature_celsius: float = Field(25.0, description="Temperature")
    pressure_bar: float = Field(3.0, description="Pressure")
    
    # Optional cations
    k_mg_l: float = Field(0.0, description="Potassium")
    nh4_mg_l: float = Field(0.0, description="Ammonium")
    fe2_mg_l: float = Field(0.0, description="Iron(II)")
    fe3_mg_l: float = Field(0.0, description="Iron(III)")
    
    # Optional anions
    cl_mg_l: Optional[float] = Field(None, description="Chloride (auto-balanced if not provided)")
    so4_mg_l: float = Field(0.0, description="Sulfate")
    co3_mg_l: float = Field(0.0, description="Carbonate")
    no3_mg_l: float = Field(0.0, description="Nitrate")
    
    def model_post_init(self, __context):
        """Auto-calculate Cl if not provided for charge balance"""
        if self.cl_mg_l is None:
            # Calculate charge balance
            cation_meq = (
                self.ca_mg_l/CONFIG.CA_EQUIV_WEIGHT + 
                self.mg_mg_l/CONFIG.MG_EQUIV_WEIGHT + 
                self.na_mg_l/CONFIG.NA_EQUIV_WEIGHT +
                self.k_mg_l/CONFIG.K_EQUIV_WEIGHT + 
                self.nh4_mg_l/CONFIG.NH4_EQUIV_WEIGHT +
                self.fe2_mg_l/CONFIG.FE2_EQUIV_WEIGHT + 
                self.fe3_mg_l/CONFIG.FE3_EQUIV_WEIGHT
            )
            anion_meq = (
                self.hco3_mg_l/CONFIG.HCO3_EQUIV_WEIGHT + 
                self.so4_mg_l/CONFIG.SO4_EQUIV_WEIGHT +
                self.co3_mg_l/CONFIG.CO3_EQUIV_WEIGHT + 
                self.no3_mg_l/CONFIG.NO3_EQUIV_WEIGHT
            )
            # Set Cl to balance
            self.cl_mg_l = max(0, (cation_meq - anion_meq) * CONFIG.CL_EQUIV_WEIGHT)
            logger.info(f"Auto-calculated Cl for charge balance: {self.cl_mg_l:.1f} mg/L")


class WACConfigurationInput(BaseModel):
    """Input for WAC configuration"""
    water_analysis: WACWaterComposition
    resin_type: str = Field(..., description="WAC_Na or WAC_H")
    target_hardness_mg_l_caco3: float = Field(
        5.0,
        description="Target effluent hardness"
    )
    target_alkalinity_mg_l_caco3: Optional[float] = Field(
        None,
        description="Target effluent alkalinity (for H-form)"
    )


class WACVesselConfiguration(BaseModel):
    """WAC vessel configuration with bed volume"""
    resin_type: str
    number_service: int
    number_standby: int
    diameter_m: float
    bed_depth_m: float
    bed_volume_L: float
    resin_volume_m3: float
    freeboard_m: float
    vessel_height_m: float
    bed_expansion_percent: float


class WACConfigurationOutput(BaseModel):
    """Output from WAC configuration"""
    vessel_configuration: WACVesselConfiguration
    water_analysis: WACWaterComposition
    resin_type: str
    target_hardness_mg_l_caco3: float
    target_alkalinity_mg_l_caco3: Optional[float]
    regeneration_parameters: Dict[str, Any]
    design_notes: List[str]
    water_chemistry_notes: List[str]


def configure_wac_vessel(input_data: WACConfigurationInput) -> WACConfigurationOutput:
    """
    Configure WAC vessel with hydraulic sizing.
    
    Similar to SAC but with WAC-specific considerations:
    - Higher total capacity but working capacity depends on water chemistry
    - Bed expansion during regeneration (50% Na-form, 100% H-form)
    - Alkalinity considerations for H-form
    """
    water = input_data.water_analysis
    resin_type = input_data.resin_type
    target_hardness = input_data.target_hardness_mg_l_caco3
    target_alkalinity = input_data.target_alkalinity_mg_l_caco3
    
    design_notes = []
    water_chemistry_notes = []
    
    # Validate resin type
    if resin_type not in ["WAC_Na", "WAC_H"]:
        raise ValueError(f"Invalid resin type: {resin_type}. Must be WAC_Na or WAC_H")
    
    # Load resin parameters
    project_root = Path(__file__).resolve().parent.parent
    db_path = project_root / "databases" / "resin_parameters.json"
    
    with open(db_path, 'r') as f:
        resin_db = json.load(f)
    
    if resin_type not in resin_db.get("resin_types", {}):
        raise ValueError(f"Resin type {resin_type} not found in database")
    
    resin_params = resin_db["resin_types"][resin_type]
    
    # Water chemistry analysis
    total_hardness = water.ca_mg_l + water.mg_mg_l * (CONFIG.CA_EQUIV_WEIGHT / CONFIG.MG_EQUIV_WEIGHT)
    alkalinity_as_caco3 = water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT * CONFIG.ALKALINITY_EQUIV_WEIGHT
    
    # Determine temporary vs permanent hardness
    temp_hardness = min(total_hardness, alkalinity_as_caco3)
    perm_hardness = max(0, total_hardness - alkalinity_as_caco3)
    
    water_chemistry_notes.append(f"Total hardness: {total_hardness:.1f} mg/L as CaCO3")
    water_chemistry_notes.append(f"Total alkalinity: {alkalinity_as_caco3:.1f} mg/L as CaCO3")
    water_chemistry_notes.append(f"Temporary hardness: {temp_hardness:.1f} mg/L as CaCO3")
    water_chemistry_notes.append(f"Permanent hardness: {perm_hardness:.1f} mg/L as CaCO3")
    
    # WAC suitability check
    if resin_type == "WAC_H" and temp_hardness < 0.8 * total_hardness:
        water_chemistry_notes.append("WARNING: H-form WAC is most effective for temporary hardness removal")
    
    if alkalinity_as_caco3 < 50:
        water_chemistry_notes.append("WARNING: Low alkalinity may limit WAC capacity")
    
    # Calculate resin volume from BV/hr (same as SAC)
    max_bv_hr = resin_params["hydraulic"]["max_service_flow_bv_hr"]
    resin_volume_m3 = water.flow_m3_hr / max_bv_hr
    design_notes.append(f"Resin volume based on {max_bv_hr} BV/hr: {resin_volume_m3:.2f} m³")
    
    # Calculate diameter from linear velocity
    max_linear_velocity = resin_params["hydraulic"]["max_linear_velocity_m_hr"]
    required_area_m2 = water.flow_m3_hr / max_linear_velocity
    design_notes.append(f"Cross-sectional area for {max_linear_velocity} m/hr: {required_area_m2:.2f} m²")
    
    # Split into multiple vessels if needed
    max_diameter = resin_params["hydraulic"].get("max_vessel_diameter_m", CONFIG.MAX_VESSEL_DIAMETER_M)
    n_service = 1
    while True:
        area_per_vessel = required_area_m2 / n_service
        diameter = math.sqrt(4 * area_per_vessel / math.pi)
        if diameter <= max_diameter:
            break
        n_service += 1
    
    if n_service > 1:
        design_notes.append(f"Split into {n_service} vessels to meet diameter constraint")
    
    # Round diameter to practical size
    diameter_original = diameter
    diameter = round(diameter * 10) / 10
    actual_area = math.pi * diameter**2 / 4
    
    # Verify linear velocity
    actual_linear_velocity = (water.flow_m3_hr / n_service) / actual_area
    if actual_linear_velocity > max_linear_velocity:
        diameter = math.ceil(diameter_original * 10) / 10
        actual_area = math.pi * diameter**2 / 4
        design_notes.append(f"Diameter adjusted to {diameter} m to maintain linear velocity")
    
    # Calculate bed depth
    min_bed_depth = resin_params["hydraulic"]["min_bed_depth_m"]
    resin_volume_per_vessel = resin_volume_m3 / n_service
    bed_depth = max(resin_volume_per_vessel / actual_area, min_bed_depth)
    
    if bed_depth == min_bed_depth:
        design_notes.append("Minimum bed depth applied")
        resin_volume_per_vessel = bed_depth * actual_area
        resin_volume_m3 = resin_volume_per_vessel * n_service
    
    # Calculate bed volume in L
    bed_volume_L = bed_depth * actual_area * 1000
    
    # Add N+1 redundancy
    n_standby = 1
    
    # Calculate freeboard considering bed expansion
    bed_expansion_percent = resin_params["hydraulic"]["bed_expansion_percent"]
    freeboard_percent = resin_params["hydraulic"]["freeboard_percent"]
    
    # Freeboard must accommodate both expansion and normal operation
    expansion_height = bed_depth * bed_expansion_percent / 100
    normal_freeboard = bed_depth * freeboard_percent / 100
    freeboard_m = max(expansion_height, normal_freeboard)
    
    design_notes.append(f"Bed expansion during regeneration: {bed_expansion_percent}%")
    design_notes.append(f"Freeboard sized for: {freeboard_m:.2f} m")
    
    # Total vessel height
    vessel_height = bed_depth + freeboard_m + 0.3 + 0.2  # Bottom/top internals
    
    logger.info(f"WAC {resin_type} vessel configuration complete:")
    logger.info(f"  - Service vessels: {n_service}")
    logger.info(f"  - Diameter: {diameter} m")
    logger.info(f"  - Bed depth: {bed_depth:.2f} m")
    logger.info(f"  - Bed volume: {bed_volume_L:.1f} L")
    logger.info(f"  - Linear velocity: {actual_linear_velocity:.1f} m/hr")
    
    # Prepare regeneration parameters based on resin type
    if resin_type == "WAC_Na":
        regeneration_params = {
            "regeneration_type": "two_step",
            "steps": resin_params["regeneration"]["steps"],
            "total_regenerant_dose_g_L": resin_params["regeneration"]["total_regenerant_dose_g_L"],
            "acid_efficiency_percent": resin_params["regeneration"]["acid_efficiency_percent"],
            "caustic_efficiency_percent": resin_params["regeneration"]["caustic_efficiency_percent"]
        }
    else:  # WAC_H
        regeneration_params = {
            "regeneration_type": "single_step",
            "steps": resin_params["regeneration"]["steps"],
            "total_regenerant_dose_g_L": resin_params["regeneration"]["total_regenerant_dose_g_L"],
            "acid_efficiency_percent": resin_params["regeneration"]["acid_efficiency_percent"]
        }
        
        # Add performance thresholds for H-form
        regeneration_params.update(resin_params.get("performance", {}))
        
        # Set default alkalinity target if not provided
        if target_alkalinity is None:
            target_alkalinity = resin_params["performance"]["alkalinity_leak_mg_L_caco3"]
            design_notes.append(f"Using default alkalinity target: {target_alkalinity} mg/L as CaCO3")
    
    return WACConfigurationOutput(
        vessel_configuration=WACVesselConfiguration(
            resin_type=resin_type,
            number_service=n_service,
            number_standby=n_standby,
            diameter_m=diameter,
            bed_depth_m=round(bed_depth, 2),
            bed_volume_L=round(bed_volume_L, 1),
            resin_volume_m3=round(resin_volume_per_vessel, 2),
            freeboard_m=round(freeboard_m, 2),
            vessel_height_m=round(vessel_height, 2),
            bed_expansion_percent=bed_expansion_percent
        ),
        water_analysis=water,
        resin_type=resin_type,
        target_hardness_mg_l_caco3=target_hardness,
        target_alkalinity_mg_l_caco3=target_alkalinity,
        regeneration_parameters=regeneration_params,
        design_notes=design_notes,
        water_chemistry_notes=water_chemistry_notes
    )