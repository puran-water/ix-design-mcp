"""
WAC Ion Exchange Configuration Tool

Performs hydraulic sizing for WAC (Weak Acid Cation) vessels.
Supports both Na-form and H-form WAC resins.
Uses knowledge-based approach for WAC_H to avoid PHREEQC convergence issues.
"""

import math
import logging
import json
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from pathlib import Path

# Import centralized configuration
from .core_config import CONFIG

# Import knowledge-based configurator for WAC_H
try:
    from .knowledge_based_config import KnowledgeBasedConfigurator
    KNOWLEDGE_BASED_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASED_AVAILABLE = False

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

    # Validation options
    strict_charge_balance: bool = Field(
        False,
        description="If True, raise ValueError on charge imbalance instead of auto-correcting"
    )

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

            # Calculate required Cl for balance
            cl_required_meq = cation_meq - anion_meq
            cl_required_mg_l = cl_required_meq * CONFIG.CL_EQUIV_WEIGHT

            # Check for charge imbalance
            total_meq = max(cation_meq, anion_meq)
            if total_meq > 0:
                imbalance_pct = abs(cl_required_meq / total_meq) * 100
            else:
                imbalance_pct = 0

            # Handle negative Cl (anions > cations)
            if cl_required_mg_l < 0:
                error_msg = (
                    f"Charge imbalance: anions exceed cations by {-cl_required_meq:.2f} meq/L "
                    f"({imbalance_pct:.1f}% imbalance). "
                    f"Ion inventory: Ca={self.ca_mg_l:.1f}, Mg={self.mg_mg_l:.1f}, "
                    f"Na={self.na_mg_l:.1f}, K={self.k_mg_l:.1f}, HCO3={self.hco3_mg_l:.1f}, "
                    f"SO4={self.so4_mg_l:.1f}, CO3={self.co3_mg_l:.1f} mg/L. "
                    f"Provide explicit Cl⁻ or correct the analysis."
                )
                if self.strict_charge_balance:
                    raise ValueError(error_msg)
                else:
                    logger.warning(f"{error_msg} Clamping Cl⁻ to 0 mg/L.")
                    self.cl_mg_l = 0.0
            else:
                self.cl_mg_l = cl_required_mg_l
                logger.info(f"Auto-calculated Cl for charge balance: {self.cl_mg_l:.1f} mg/L")

                # Warn if imbalance is significant (>5%)
                if imbalance_pct > 5.0:
                    warn_msg = (
                        f"Significant charge imbalance: {imbalance_pct:.1f}% "
                        f"(cations={cation_meq:.2f} meq/L, anions={anion_meq:.2f} meq/L). "
                        f"Verify water analysis data."
                    )
                    if self.strict_charge_balance and imbalance_pct > 10.0:
                        raise ValueError(warn_msg + " Exceeds 10% threshold in strict mode.")
                    else:
                        logger.warning(warn_msg)


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


class WACServicePerformance(BaseModel):
    """WAC service cycle performance metrics"""
    breakthrough_BV: float = Field(..., description="Breakthrough in bed volumes")
    run_length_hrs: float = Field(..., description="Service run duration in hours")
    run_volume_m3: float = Field(..., description="Volume treated per cycle")
    operating_capacity_eq_L: float = Field(..., description="Operating exchange capacity")
    utilization: float = Field(..., description="Bed utilization fraction")
    LUB_fraction: float = Field(..., description="Length of unused bed fraction")
    # WAC_H specific
    alkalinity_feed_mg_L: Optional[float] = Field(None, description="Feed alkalinity as CaCO3")
    alkalinity_effluent_mg_L: Optional[float] = Field(None, description="Effluent alkalinity as CaCO3")
    CO2_generation_mg_L: Optional[float] = Field(None, description="CO2 generation")
    pH_dependent_fraction: Optional[float] = Field(None, description="pH-dependent capacity fraction")
    pH_profile: Optional[Dict[str, float]] = Field(None, description="pH profile through cycle")
    pH_floor: Optional[float] = Field(None, description="pH floor for alkalinity removal")
    # WAC_Na specific
    removable_hardness_mg_L: Optional[float] = Field(None, description="Removable temporary hardness")
    meets_alkalinity_target: Optional[bool] = Field(None, description="Whether alkalinity target met")

class WACRegenerationPerformance(BaseModel):
    """WAC regeneration cycle parameters"""
    type: str = Field(..., description="single_step or two_step")
    chemical: Optional[str] = Field(None, description="Primary regenerant")
    concentration: Optional[str] = Field(None, description="Regenerant concentration")
    dose_eq_L: Optional[float] = Field(None, description="Regenerant dose eq/L")
    volume_BV: Optional[float] = Field(None, description="Regenerant volume in BV")
    volume_m3: Optional[float] = Field(None, description="Regenerant volume in m³")
    rinse_volume_BV: float = Field(..., description="Rinse volume in BV")
    duration_hrs: float = Field(..., description="Total regeneration time")
    waste_volume_m3: float = Field(..., description="Total waste volume")
    # Two-step specific
    step1: Optional[Dict[str, Any]] = Field(None, description="First step details")
    step2: Optional[Dict[str, Any]] = Field(None, description="Second step details")

class WACConfigurationOutput(BaseModel):
    """Output from WAC configuration with performance metrics"""
    vessel_configuration: WACVesselConfiguration
    water_analysis: WACWaterComposition
    resin_type: str
    target_hardness_mg_l_caco3: float
    target_alkalinity_mg_l_caco3: Optional[float]
    service_performance: Optional[WACServicePerformance] = Field(None, description="Service performance")
    regeneration_parameters: Dict[str, Any]  # Legacy format
    regeneration_performance: Optional[WACRegenerationPerformance] = Field(None, description="Regeneration details")
    design_notes: List[str]
    water_chemistry_notes: List[str]
    calculation_method: str = Field("hydraulic_only", description="Calculation method used")


def configure_wac_vessel(input_data: WACConfigurationInput) -> WACConfigurationOutput:
    """
    Configure WAC vessel with hydraulic sizing.

    Similar to SAC but with WAC-specific considerations:
    - Higher total capacity but working capacity depends on water chemistry
    - Bed expansion during regeneration (50% Na-form, 100% H-form)
    - Alkalinity considerations for H-form

    For WAC_H: Uses knowledge-based approach to avoid PHREEQC convergence issues
    """
    water = input_data.water_analysis
    resin_type = input_data.resin_type
    target_hardness = input_data.target_hardness_mg_l_caco3
    target_alkalinity = input_data.target_alkalinity_mg_l_caco3

    # For WAC_H, use knowledge-based approach if available
    if resin_type == "WAC_H" and KNOWLEDGE_BASED_AVAILABLE:
        logger.info("Using knowledge-based approach for WAC_H configuration")
        configurator = KnowledgeBasedConfigurator()

        # Convert water analysis to dict format
        water_dict = {
            'flow_m3_hr': water.flow_m3_hr,
            'ca_mg_l': water.ca_mg_l,
            'mg_mg_l': water.mg_mg_l,
            'na_mg_l': water.na_mg_l,
            'alkalinity_mg_L_CaCO3': water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT * CONFIG.ALKALINITY_EQUIV_WEIGHT,
            'pH': water.pH,
            'temperature_C': water.temperature_celsius,
            'flow_BV_hr': water.flow_m3_hr / max(1e-6, water.flow_m3_hr / CONFIG.MAX_BED_VOLUME_PER_HOUR)
        }

        # Get knowledge-based configuration
        kb_config = configurator.configure_wac_h(water_dict, target_alkalinity or 10.0)

        # Convert to WACConfigurationOutput format
        vessel_config = WACVesselConfiguration(
            resin_type=resin_type,  # Add resin_type field
            number_service=1,
            number_standby=1,
            diameter_m=kb_config['vessel']['diameter_m'],
            bed_depth_m=kb_config['vessel']['bed_depth_m'],
            bed_volume_L=kb_config['vessel']['bed_volume_m3'] * 1000,
            resin_volume_m3=kb_config['vessel']['bed_volume_m3'],
            freeboard_m=kb_config['vessel']['bed_depth_m'] * 1.0 + 0.3,  # 100% expansion + safety
            vessel_height_m=kb_config['vessel']['bed_depth_m'] + kb_config['vessel']['bed_depth_m'] * 1.0 + 0.61,
            bed_expansion_percent=100.0  # H-form WAC
        )

        # Extract service performance metrics for WAC_H
        perf = kb_config['performance']
        service_performance = WACServicePerformance(
            breakthrough_BV=perf['breakthrough_BV'],
            run_length_hrs=perf['run_length_hrs'],
            run_volume_m3=perf['run_volume_m3'],
            operating_capacity_eq_L=perf['operating_capacity_eq_L'],
            utilization=perf['utilization'],
            LUB_fraction=perf['LUB_fraction'],
            alkalinity_feed_mg_L=perf.get('alkalinity_feed_mg_L'),
            alkalinity_effluent_mg_L=perf.get('alkalinity_effluent_mg_L', target_alkalinity),
            CO2_generation_mg_L=perf.get('CO2_generation_mg_L'),
            pH_dependent_fraction=perf.get('pH_dependent_fraction'),
            pH_profile=perf.get('pH_profile'),
            pH_floor=perf.get('pH_profile', {}).get('pH_floor'),
            # Meets target if effluent alkalinity is at or below target
            meets_alkalinity_target=(perf.get('alkalinity_effluent_mg_L', target_alkalinity) <= (target_alkalinity or 10))
        )

        # Extract regeneration metrics
        regen = kb_config['regeneration']
        regeneration_performance = WACRegenerationPerformance(
            type='single_step',
            chemical=regen.get('chemical', 'HCl'),
            concentration=regen.get('concentration', '5%'),
            dose_eq_L=regen.get('dose_eq_L'),
            volume_BV=regen.get('volume_BV'),
            volume_m3=regen.get('volume_m3'),
            rinse_volume_BV=regen.get('rinse_volume_BV', 3),
            duration_hrs=regen.get('duration_hrs'),
            waste_volume_m3=regen.get('waste_volume_m3')
        )

        return WACConfigurationOutput(
            vessel_configuration=vessel_config,
            water_analysis=water,
            resin_type=resin_type,
            target_hardness_mg_l_caco3=target_hardness,
            target_alkalinity_mg_l_caco3=target_alkalinity,
            service_performance=service_performance,
            regeneration_parameters=kb_config['regeneration'],
            regeneration_performance=regeneration_performance,
            design_notes=[
                f"Knowledge-based configuration (PHREEQC bypassed)",
                f"Breakthrough: {perf['breakthrough_BV']:.0f} BV for alkalinity",
                f"Operating capacity: {perf['operating_capacity_eq_L']:.2f} eq/L",
                f"pH floor: {perf.get('pH_profile', {}).get('pH_floor', 4.5):.2f} (from {target_alkalinity:.0f} mg/L target)",
                f"pH-dependent capacity fraction: {perf.get('pH_dependent_fraction', 0):.2%}",
                f"Effluent alkalinity: {perf.get('alkalinity_effluent_mg_L', target_alkalinity):.1f} mg/L",
                f"CO2 generation: {perf.get('CO2_generation_mg_L', 0):.0f} mg/L",
                f"Run length: {perf['run_length_hrs']:.1f} hours"
            ],
            water_chemistry_notes=kb_config.get('warnings', []),
            calculation_method="knowledge_based"
        )
    
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
    total_hardness = (
        (water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT) +
        (water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT)
    ) * CONFIG.ALKALINITY_EQUIV_WEIGHT
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
    
    # For WAC_Na without knowledge-based calc, just provide hydraulic sizing
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
        service_performance=None,  # No performance calc for WAC_Na yet
        regeneration_parameters=regeneration_params,
        regeneration_performance=None,
        design_notes=design_notes,
        water_chemistry_notes=water_chemistry_notes,
        calculation_method="hydraulic_only"
    )
