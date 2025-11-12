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

# Import centralized configuration
from .core_config import CONFIG

# Import hydraulics calculations
from .hydraulics import (
    calculate_system_hydraulics,
    STANDARD_SAC_RESIN,
    HydraulicResult
)

# Import knowledge-based configurator for performance calculations
try:
    from .knowledge_based_config import KnowledgeBasedConfigurator
    KNOWLEDGE_BASED_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASED_AVAILABLE = False

logger = logging.getLogger(__name__)


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

    # Validation options
    strict_charge_balance: bool = Field(
        False,
        description="If True, raise ValueError on charge imbalance instead of auto-correcting"
    )

    def model_post_init(self, __context):
        """Auto-calculate Cl if not provided for charge balance"""
        if self.cl_mg_l is None:
            # Calculate charge balance using centralized equivalent weights
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
                self.no3_mg_l/CONFIG.NO3_EQUIV_WEIGHT +
                self.po4_mg_l/CONFIG.PO4_EQUIV_WEIGHT +
                self.f_mg_l/CONFIG.F_EQUIV_WEIGHT +
                self.oh_mg_l/CONFIG.OH_EQUIV_WEIGHT
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


class SACConfigurationInput(BaseModel):
    """
    Input for SAC vessel configuration.

    SAC (Strong Acid Cation) resins are used for complete hardness removal
    in RO pretreatment applications. Uses Gaines-Thomas equilibrium to predict
    hardness leakage based on feed water composition.

    Args:
        water_analysis: Water composition (SACWaterComposition)
        target_hardness_mg_l_caco3: Target effluent hardness (default 5.0 mg/L, typical range 1-5 mg/L for RO)

    Note:
        All water parameters must be inside 'water_analysis' object.
        Chloride is auto-calculated for charge balance if not provided.

    Example:
        {
            "water_analysis": {
                "flow_m3_hr": 100,
                "ca_mg_l": 80.06,
                "mg_mg_l": 24.29,
                "na_mg_l": 230.0,
                "hco3_mg_l": 122.0,
                "pH": 7.5,
                "so4_mg_l": 96.0
            },
            "target_hardness_mg_l_caco3": 5.0
        }
    """
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


class ServicePerformance(BaseModel):
    """Service cycle performance metrics"""
    breakthrough_BV: float = Field(..., description="Breakthrough in bed volumes")
    run_length_hrs: float = Field(..., description="Service run duration in hours")
    run_volume_m3: float = Field(..., description="Volume treated per cycle")
    hardness_feed_mg_L: float = Field(..., description="Feed hardness as CaCO3")
    hardness_leakage_mg_L: float = Field(..., description="Average hardness leakage")
    operating_capacity_eq_L: float = Field(..., description="Operating exchange capacity")
    utilization: float = Field(..., description="Bed utilization fraction")
    LUB_fraction: float = Field(..., description="Length of unused bed fraction")
    meets_target: bool = Field(..., description="Whether effluent meets target")
    derating_factor: float = Field(..., description="Capacity derating factor")

class RegenerationPerformance(BaseModel):
    """Regeneration cycle parameters"""
    chemical: str = Field(..., description="Regenerant chemical")
    dose_g_L: float = Field(..., description="Regenerant dose per L resin")
    concentration: str = Field(..., description="Regenerant concentration")
    volume_BV: float = Field(..., description="Regenerant volume in bed volumes")
    volume_m3: float = Field(..., description="Regenerant volume in m³")
    rinse_volume_BV: float = Field(..., description="Rinse volume in bed volumes")
    duration_hrs: float = Field(..., description="Total regeneration time")
    efficiency: float = Field(..., description="Regeneration efficiency")
    waste_volume_m3: float = Field(..., description="Total waste volume")


class HydraulicAnalysis(BaseModel):
    """Hydraulic analysis results from Ergun and Richardson-Zaki calculations"""
    pressure_drop_service_kpa: float = Field(..., description="Service pressure drop (Ergun equation)")
    pressure_drop_backwash_kpa: float = Field(..., description="Backwash pressure drop")
    bed_expansion_percent: float = Field(..., description="Bed expansion during backwash (Richardson-Zaki)")
    expanded_bed_depth_m: float = Field(..., description="Expanded bed depth during backwash")
    required_freeboard_m: float = Field(..., description="Required freeboard (expansion × safety factor)")
    distributor_headloss_kpa: float = Field(..., description="Distributor/collector headloss")
    nozzle_velocity_m_s: float = Field(..., description="Velocity through distributor nozzles")
    linear_velocity_m_hr: float = Field(..., description="Service linear velocity (for AWWA B100 check)")
    velocity_in_range: bool = Field(..., description="True if 5-40 m/hr (AWWA B100 compliant)")
    expansion_acceptable: bool = Field(..., description="True if expansion <100%")
    warnings: List[str] = Field(..., description="Hydraulic design warnings")


class SACConfigurationOutput(BaseModel):
    """Output from SAC configuration with performance metrics"""
    vessel_configuration: SACVesselConfiguration
    water_analysis: SACWaterComposition
    target_hardness_mg_l_caco3: float
    service_performance: Optional[ServicePerformance] = Field(None, description="Service cycle performance")
    regeneration_parameters: Dict[str, Any]  # Legacy format
    regeneration_performance: Optional[RegenerationPerformance] = Field(None, description="Regeneration details")
    hydraulic_analysis: Optional[HydraulicAnalysis] = Field(None, description="Hydraulic analysis (Ergun ΔP, bed expansion)")
    design_notes: List[str]
    calculation_method: str = Field("hydraulic_only", description="Calculation method used")


def configure_sac_vessel(input_data: SACConfigurationInput, use_knowledge_based: bool = True) -> SACConfigurationOutput:
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
    resin_volume_m3 = water.flow_m3_hr / CONFIG.MAX_BED_VOLUME_PER_HOUR
    design_notes.append(f"Resin volume based on {CONFIG.MAX_BED_VOLUME_PER_HOUR} BV/hr: {resin_volume_m3:.2f} m³")
    
    # Calculate diameter from linear velocity
    required_area_m2 = water.flow_m3_hr / CONFIG.MAX_LINEAR_VELOCITY_M_HR
    design_notes.append(f"Cross-sectional area for {CONFIG.MAX_LINEAR_VELOCITY_M_HR} m/hr: {required_area_m2:.2f} m²")
    
    # Split into multiple vessels if needed for diameter constraint
    n_service = 1
    while True:
        area_per_vessel = required_area_m2 / n_service
        diameter = math.sqrt(4 * area_per_vessel / math.pi)
        if diameter <= CONFIG.MAX_VESSEL_DIAMETER_M:
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
    if actual_linear_velocity > CONFIG.MAX_LINEAR_VELOCITY_M_HR:
        # Need to increase diameter slightly
        diameter = math.ceil(diameter_original * 10) / 10  # Round up
        actual_area = math.pi * diameter**2 / 4
        design_notes.append(f"Diameter adjusted to {diameter} m to maintain linear velocity")

    # Check minimum velocity to prevent maldistribution
    actual_linear_velocity = (water.flow_m3_hr / n_service) / actual_area
    if actual_linear_velocity < CONFIG.MIN_LINEAR_VELOCITY_M_HR:
        design_notes.append(
            f"WARNING: Linear velocity ({actual_linear_velocity:.1f} m/h) below minimum "
            f"({CONFIG.MIN_LINEAR_VELOCITY_M_HR} m/h). Risk of maldistribution. "
            f"Consider: (1) Multiple smaller trains, (2) Shorter cycle time, or "
            f"(3) Accept higher velocity if hydraulically feasible."
        )

    # Calculate bed depth
    resin_volume_per_vessel = resin_volume_m3 / n_service
    bed_depth = max(
        resin_volume_per_vessel / actual_area,
        CONFIG.MIN_BED_DEPTH_M
    )
    
    if bed_depth == CONFIG.MIN_BED_DEPTH_M:
        design_notes.append("Minimum bed depth applied")
        # Recalculate actual resin volume
        resin_volume_per_vessel = bed_depth * actual_area
        resin_volume_m3 = resin_volume_per_vessel * n_service
    
    # Calculate bed volume in L (CRITICAL - this is used in simulation)
    bed_volume_L = bed_depth * actual_area * 1000
    
    # Add N+1 redundancy
    n_standby = 1

    # Perform hydraulic analysis (Ergun ΔP, Richardson-Zaki expansion)
    # Estimate backwash flow rate: typically 1.5-2.0× service flow for bed expansion
    backwash_flow_m3_h = (water.flow_m3_hr / n_service) * 1.75  # Per vessel

    hydraulic_result = calculate_system_hydraulics(
        bed_depth_m=bed_depth,
        bed_diameter_m=diameter,
        service_flow_m3_h=(water.flow_m3_hr / n_service),  # Per vessel
        backwash_flow_m3_h=backwash_flow_m3_h,
        resin_props=STANDARD_SAC_RESIN,
        temperature_c=20.0,
        freeboard_safety_factor=1.5
    )

    # Use hydraulic-calculated freeboard with minimum allowance for hardware
    # AWWA guidelines: minimum 0.3m for distributor/internals
    MINIMUM_FREEBOARD_M = 0.3
    freeboard_m = max(hydraulic_result.required_freeboard_m, MINIMUM_FREEBOARD_M)

    # Add hydraulic warnings to design notes
    if hydraulic_result.warnings:
        design_notes.extend(hydraulic_result.warnings)

    # Log hydraulic analysis results
    logger.info(f"Hydraulic analysis:")
    logger.info(f"  - Service ΔP: {hydraulic_result.pressure_drop_service_kpa:.1f} kPa (Ergun equation)")
    logger.info(f"  - Backwash ΔP: {hydraulic_result.pressure_drop_backwash_kpa:.1f} kPa")
    logger.info(f"  - Bed expansion: {hydraulic_result.bed_expansion_percent:.1f}% (Richardson-Zaki)")
    logger.info(f"  - Required freeboard: {hydraulic_result.required_freeboard_m:.2f} m")
    logger.info(f"  - AWWA B100 compliant: {hydraulic_result.velocity_in_range}")

    # Total vessel height
    # Include space for bottom distributor/support (0.3m) and top distributor/nozzles (0.2m)
    vessel_height = bed_depth + freeboard_m + 0.3 + 0.2
    
    logger.info(f"SAC vessel configuration complete:")
    logger.info(f"  - Service vessels: {n_service}")
    logger.info(f"  - Diameter: {diameter} m")
    logger.info(f"  - Bed depth: {bed_depth:.2f} m")
    logger.info(f"  - Bed volume: {bed_volume_L:.1f} L")
    logger.info(f"  - Linear velocity: {actual_linear_velocity:.1f} m/hr")
    
    # Calculate performance metrics using knowledge-based approach if available
    service_performance = None
    regeneration_performance = None
    calculation_method = "hydraulic_only"

    if use_knowledge_based and KNOWLEDGE_BASED_AVAILABLE:
        try:
            configurator = KnowledgeBasedConfigurator()

            # Convert water analysis to dict format for knowledge-based calc
            water_dict = {
                'flow_m3_hr': water.flow_m3_hr,
                'ca_mg_l': water.ca_mg_l,
                'mg_mg_l': water.mg_mg_l,
                'na_mg_l': water.na_mg_l,
                'flow_BV_hr': CONFIG.MAX_BED_VOLUME_PER_HOUR
            }

            # Get knowledge-based configuration with performance metrics
            regen_dose_g_L = CONFIG.REGENERANT_DOSE_KG_M3  # Convert kg/m³ to g/L
            kb_config = configurator.configure_sac_softening(
                water_dict,
                regen_dose_g_L=regen_dose_g_L,
                target_hardness_mg_L=target_hardness
            )

            # Extract performance metrics
            perf = kb_config['performance']
            service_performance = ServicePerformance(
                breakthrough_BV=perf['breakthrough_BV'],
                run_length_hrs=perf['run_length_hrs'],
                run_volume_m3=perf['run_volume_m3'],
                hardness_feed_mg_L=perf['hardness_feed_mg_L'],
                hardness_leakage_mg_L=perf['hardness_leakage_mg_L'],
                operating_capacity_eq_L=perf['operating_capacity_eq_L'],
                utilization=perf['utilization'],
                LUB_fraction=perf['LUB_fraction'],
                meets_target=perf['hardness_leakage_mg_L'] <= target_hardness,
                derating_factor=perf['derating_factor']
            )

            # Extract regeneration metrics
            regen = kb_config['regeneration']
            regeneration_performance = RegenerationPerformance(
                chemical=regen['chemical'],
                dose_g_L=regen['dose_g_L'],
                concentration=regen['concentration'],
                volume_BV=regen['volume_BV'],
                volume_m3=regen['volume_m3'],
                rinse_volume_BV=regen['rinse_volume_BV'],
                duration_hrs=regen['duration_hrs'],
                efficiency=regen['efficiency'],
                waste_volume_m3=regen['waste_volume_m3']
            )

            calculation_method = "knowledge_based"
            design_notes.append("Performance calculated using knowledge-based correlations")
            design_notes.append(f"Predicted hardness leakage: {perf['hardness_leakage_mg_L']:.1f} mg/L as CaCO3")

        except Exception as e:
            logger.warning(f"Knowledge-based calculation failed: {e}")
            design_notes.append("Knowledge-based calculation unavailable - hydraulic sizing only")

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
        service_performance=service_performance,
        regeneration_parameters={
            "regenerant_type": "NaCl",
            "regenerant_dose_kg_m3": CONFIG.REGENERANT_DOSE_KG_M3,
            "regenerant_concentration_percent": CONFIG.REGENERANT_CONCENTRATION_PERCENT,
            "rinse_volume_BV": CONFIG.RINSE_VOLUME_BV,
            "regenerant_flow_BV_hr": CONFIG.REGENERANT_FLOW_BV_HR
        },
        regeneration_performance=regeneration_performance,
        hydraulic_analysis=HydraulicAnalysis(
            pressure_drop_service_kpa=round(hydraulic_result.pressure_drop_service_kpa, 2),
            pressure_drop_backwash_kpa=round(hydraulic_result.pressure_drop_backwash_kpa, 2),
            bed_expansion_percent=round(hydraulic_result.bed_expansion_percent, 1),
            expanded_bed_depth_m=round(hydraulic_result.expanded_bed_depth_m, 2),
            required_freeboard_m=round(hydraulic_result.required_freeboard_m, 2),
            distributor_headloss_kpa=round(hydraulic_result.distributor_headloss_kpa, 2),
            nozzle_velocity_m_s=round(hydraulic_result.nozzle_velocity_m_s, 2),
            linear_velocity_m_hr=round(actual_linear_velocity, 1),
            velocity_in_range=hydraulic_result.velocity_in_range,
            expansion_acceptable=hydraulic_result.expansion_acceptable,
            warnings=hydraulic_result.warnings
        ),
        design_notes=design_notes,
        calculation_method=calculation_method
    )