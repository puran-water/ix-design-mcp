"""
SAC Ion Exchange Configuration Tool

Performs hydraulic sizing for SAC (Strong Acid Cation) vessels.
This tool focuses ONLY on vessel sizing and hydraulic calculations.
All chemistry, competition effects, and breakthrough predictions are
determined by PHREEQC simulation - NO HEURISTICS.
"""

import math
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# SAC design parameters - HYDRAULIC ONLY, NO CHEMISTRY
SAC_DESIGN_PARAMETERS = {
    "max_bed_volume_per_hour": 16.0,      # BV/hr service flow rate
    "max_linear_velocity_m_hr": 25.0,     # m/hr linear velocity limit
    "min_bed_depth_m": 0.75,              # Minimum bed depth
    "freeboard_percent": 100.0,           # SAC resins need 100% freeboard
    "max_vessel_diameter_m": 2.4          # Shipping container limit
}


class SACWaterComposition(BaseModel):
    """Water composition with all MCAS ions"""
    # Required parameters
    flow_m3_hr: float = Field(..., description="Feed water flow rate")
    ca_mg_l: float = Field(..., description="Calcium (required)")
    mg_mg_l: float = Field(..., description="Magnesium (required)")
    na_mg_l: float = Field(..., description="Sodium (required)")
    hco3_mg_l: float = Field(..., description="Bicarbonate (required)")
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
    po4_mg_l: float = Field(0.0, description="Phosphate")
    f_mg_l: float = Field(0.0, description="Fluoride")
    oh_mg_l: float = Field(0.0, description="Hydroxide")
    
    # Optional neutrals
    co2_mg_l: float = Field(0.0, description="Carbon dioxide")
    sio2_mg_l: float = Field(0.0, description="Silica")
    b_oh_3_mg_l: float = Field(0.0, description="Boric acid")
    
    def model_post_init(self, __context):
        """Auto-calculate Cl if not provided for charge balance"""
        if self.cl_mg_l is None:
            # Calculate charge balance
            cation_meq = (
                self.ca_mg_l/20.04 + self.mg_mg_l/12.15 + self.na_mg_l/23.0 +
                self.k_mg_l/39.1 + self.nh4_mg_l/18.04 +
                self.fe2_mg_l/27.92 + self.fe3_mg_l/18.62
            )
            anion_meq = (
                self.hco3_mg_l/61.02 + self.so4_mg_l/48.03 +
                self.co3_mg_l/30.0 + self.no3_mg_l/62.0 +
                self.po4_mg_l/31.67 + self.f_mg_l/19.0 + self.oh_mg_l/17.0
            )
            # Set Cl to balance
            self.cl_mg_l = max(0, (cation_meq - anion_meq) * 35.45)
            logger.info(f"Auto-calculated Cl for charge balance: {self.cl_mg_l:.1f} mg/L")


class SACConfigurationInput(BaseModel):
    """Input for SAC configuration"""
    water_analysis: SACWaterComposition
    target_hardness_mg_l_caco3: float = Field(
        5.0,
        description="Target effluent hardness (typically 1-5 mg/L for RO)"
    )


class SACVesselConfiguration(BaseModel):
    """Vessel configuration with bed volume"""
    resin_type: str = "SAC"
    number_service: int
    number_standby: int
    diameter_m: float
    bed_depth_m: float
    bed_volume_L: float  # CRITICAL - used in simulation
    resin_volume_m3: float
    freeboard_m: float
    vessel_height_m: float


class SACConfigurationOutput(BaseModel):
    """Output from SAC configuration"""
    vessel_configuration: SACVesselConfiguration
    water_analysis: SACWaterComposition
    target_hardness_mg_l_caco3: float
    regeneration_parameters: Dict[str, Any]
    design_notes: List[str]


def configure_sac_vessel(input_data: SACConfigurationInput) -> SACConfigurationOutput:
    """
    Configure SAC vessel with hydraulic sizing only.
    
    NO chemistry calculations - PHREEQC determines:
    - Operating capacity
    - Competition effects
    - Breakthrough time
    - Service cycle length
    """
    water = input_data.water_analysis
    target_hardness = input_data.target_hardness_mg_l_caco3
    
    design_notes = []
    
    # Calculate resin volume from BV/hr
    resin_volume_m3 = water.flow_m3_hr / SAC_DESIGN_PARAMETERS["max_bed_volume_per_hour"]
    design_notes.append(f"Resin volume based on 16 BV/hr: {resin_volume_m3:.2f} m³")
    
    # Calculate diameter from linear velocity
    required_area_m2 = water.flow_m3_hr / SAC_DESIGN_PARAMETERS["max_linear_velocity_m_hr"]
    design_notes.append(f"Cross-sectional area for 25 m/hr: {required_area_m2:.2f} m²")
    
    # Split into multiple vessels if needed for diameter constraint
    n_service = 1
    while True:
        area_per_vessel = required_area_m2 / n_service
        diameter = math.sqrt(4 * area_per_vessel / math.pi)
        if diameter <= SAC_DESIGN_PARAMETERS["max_vessel_diameter_m"]:
            break
        n_service += 1
    
    if n_service > 1:
        design_notes.append(f"Split into {n_service} vessels to meet diameter constraint")
    
    # Round diameter to practical size (0.1m increments)
    diameter_original = diameter
    diameter = round(diameter * 10) / 10
    actual_area = math.pi * diameter**2 / 4
    
    # Verify linear velocity after rounding
    actual_linear_velocity = (water.flow_m3_hr / n_service) / actual_area
    if actual_linear_velocity > SAC_DESIGN_PARAMETERS["max_linear_velocity_m_hr"]:
        # Need to increase diameter slightly
        diameter = math.ceil(diameter_original * 10) / 10  # Round up
        actual_area = math.pi * diameter**2 / 4
        design_notes.append(f"Diameter adjusted to {diameter} m to maintain linear velocity")
    
    # Calculate bed depth
    resin_volume_per_vessel = resin_volume_m3 / n_service
    bed_depth = max(
        resin_volume_per_vessel / actual_area,
        SAC_DESIGN_PARAMETERS["min_bed_depth_m"]
    )
    
    if bed_depth == SAC_DESIGN_PARAMETERS["min_bed_depth_m"]:
        design_notes.append("Minimum bed depth applied")
        # Recalculate actual resin volume
        resin_volume_per_vessel = bed_depth * actual_area
        resin_volume_m3 = resin_volume_per_vessel * n_service
    
    # Calculate bed volume in L (CRITICAL - this is used in simulation)
    bed_volume_L = bed_depth * actual_area * 1000
    
    # Add N+1 redundancy
    n_standby = 1
    
    # Calculate freeboard
    freeboard_m = bed_depth * SAC_DESIGN_PARAMETERS["freeboard_percent"] / 100
    
    # Total vessel height
    # Include space for bottom distributor/support (0.3m) and top distributor/nozzles (0.2m)
    vessel_height = bed_depth + freeboard_m + 0.3 + 0.2
    
    logger.info(f"SAC vessel configuration complete:")
    logger.info(f"  - Service vessels: {n_service}")
    logger.info(f"  - Diameter: {diameter} m")
    logger.info(f"  - Bed depth: {bed_depth:.2f} m")
    logger.info(f"  - Bed volume: {bed_volume_L:.1f} L")
    logger.info(f"  - Linear velocity: {actual_linear_velocity:.1f} m/hr")
    
    # NO CAPACITY OR COMPETITION CALCULATIONS HERE
    # PHREEQC will determine actual operating capacity
    
    return SACConfigurationOutput(
        vessel_configuration=SACVesselConfiguration(
            resin_type="SAC",
            number_service=n_service,
            number_standby=n_standby,
            diameter_m=diameter,
            bed_depth_m=round(bed_depth, 2),
            bed_volume_L=round(bed_volume_L, 1),  # CRITICAL for simulation
            resin_volume_m3=round(resin_volume_per_vessel, 2),
            freeboard_m=round(freeboard_m, 2),
            vessel_height_m=round(vessel_height, 2)
        ),
        water_analysis=water,
        target_hardness_mg_l_caco3=target_hardness,
        regeneration_parameters={
            "regenerant_type": "NaCl",
            "regenerant_dose_kg_m3": 125.0,  # kg NaCl per m³ resin
            "regenerant_concentration_percent": 10.0,
            "rinse_volume_BV": 4.0,  # Bed volumes for rinse
            "regenerant_flow_BV_hr": 4.0  # Slow flow for regeneration
        },
        design_notes=design_notes
    )