"""
MCAS-Compatible Schemas for Ion Exchange MCP Server

These schemas ensure compatibility with WaterTAP's MCAS property package
and seamless integration with the RO Design MCP Server.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, validator

# MCAS-compatible ion list for industrial wastewater
# Note: This list includes common species found in industrial water
MCAS_IONS = {
    "cations": ["Na_+", "Ca_2+", "Mg_2+", "K_+", "H_+", "NH4_+", "Fe_2+", "Fe_3+"],
    "anions": ["Cl_-", "SO4_2-", "HCO3_-", "CO3_2-", "NO3_-", "PO4_3-", "F_-", "OH_-"],
    "neutrals": ["CO2", "H2O", "SiO2", "B(OH)3"]  # Added silica and boric acid
}

# Molecular weights for MCAS components (g/mol)
MOLECULAR_WEIGHTS = {
    "H2O": 18.015,
    "Na_+": 22.990,
    "Ca_2+": 40.078,
    "Mg_2+": 24.305,
    "K_+": 39.098,
    "H_+": 1.008,
    "NH4_+": 18.039,
    "Fe_2+": 55.845,
    "Fe_3+": 55.845,
    "Cl_-": 35.453,
    "SO4_2-": 96.064,
    "HCO3_-": 61.017,
    "CO3_2-": 60.009,
    "NO3_-": 62.004,
    "PO4_3-": 94.971,
    "F_-": 18.998,
    "OH_-": 17.007,
    "CO2": 44.010,
    "SiO2": 60.08,      # Silica (common in industrial water)
    "B(OH)3": 61.83     # Boric acid
}

# Charge data for MCAS components
CHARGE_DATA = {
    "Na_+": 1, "Ca_2+": 2, "Mg_2+": 2, "K_+": 1, "H_+": 1, "NH4_+": 1,
    "Fe_2+": 2, "Fe_3+": 3, "Cl_-": -1, "SO4_2-": -2, "HCO3_-": -1,
    "CO3_2-": -2, "NO3_-": -1, "PO4_3-": -3, "F_-": -1, "OH_-": -1,
    "CO2": 0, "H2O": 0, "SiO2": 0, "B(OH)3": 0
}


class MCASWaterComposition(BaseModel):
    """MCAS-compatible water composition for WaterTAP integration."""
    
    # Flow and basic properties
    flow_m3_hr: float = Field(..., description="Volumetric flow rate in m³/hr", gt=0)
    temperature_celsius: float = Field(25.0, description="Temperature in Celsius", ge=0, le=100)
    pressure_bar: float = Field(4.0, description="Pressure in bar", gt=0)
    pH: float = Field(7.0, description="pH value", ge=0, le=14)
    
    # Ion concentrations in mg/L (MCAS format)
    ion_concentrations_mg_L: Dict[str, float] = Field(
        ...,
        description="Ion concentrations in mg/L using MCAS notation (e.g., 'Na_+', 'Ca_2+', 'Cl_-')"
    )
    
    @validator('ion_concentrations_mg_L')
    def validate_ions(cls, v):
        """Validate and clean ion notation, with flexible handling of non-standard ions."""
        import logging
        logger = logging.getLogger(__name__)
        
        valid_ions = set(MCAS_IONS["cations"] + MCAS_IONS["anions"] + MCAS_IONS["neutrals"])
        cleaned_ions = {}
        
        for ion, conc in v.items():
            if ion in valid_ions:
                cleaned_ions[ion] = conc
            else:
                # Log warning but include the ion anyway - let downstream handle it
                logger.warning(
                    f"Non-standard ion '{ion}' provided (concentration: {conc} mg/L). "
                    f"Expected MCAS format ions: {', '.join(sorted(valid_ions))}"
                )
                # Still include it for transparency, but it won't affect IX calculations
                cleaned_ions[ion] = conc
        
        # Ensure we have at least some valid ions for IX design
        valid_ion_count = sum(1 for ion in cleaned_ions if ion in valid_ions)
        if valid_ion_count == 0:
            raise ValueError(
                "No valid MCAS ions found in water composition. "
                "At least one of the following is required: " + ", ".join(sorted(valid_ions))
            )
        
        return cleaned_ions
    
    def get_total_hardness_mg_L_CaCO3(self) -> float:
        """Calculate total hardness as CaCO3."""
        ca_mg_L = self.ion_concentrations_mg_L.get("Ca_2+", 0)
        mg_mg_L = self.ion_concentrations_mg_L.get("Mg_2+", 0)
        
        # Convert to meq/L then to mg/L as CaCO3
        ca_meq_L = ca_mg_L / 20.04  # Ca molecular weight / charge
        mg_meq_L = mg_mg_L / 12.15  # Mg molecular weight / charge
        
        return (ca_meq_L + mg_meq_L) * 50.045  # Convert to mg/L as CaCO3
    
    def get_alkalinity_mg_L_CaCO3(self) -> float:
        """Calculate alkalinity as CaCO3."""
        hco3_mg_L = self.ion_concentrations_mg_L.get("HCO3_-", 0)
        co3_mg_L = self.ion_concentrations_mg_L.get("CO3_2-", 0)
        oh_mg_L = self.ion_concentrations_mg_L.get("OH_-", 0)
        
        # Convert to meq/L
        hco3_meq_L = hco3_mg_L / 61.017
        co3_meq_L = co3_mg_L / 30.005  # MW/charge
        oh_meq_L = oh_mg_L / 17.007
        
        # H+ contribution (negative alkalinity)
        h_mg_L = self.ion_concentrations_mg_L.get("H_+", 0)
        h_meq_L = h_mg_L / 1.008
        
        total_alk_meq_L = hco3_meq_L + 2 * co3_meq_L + oh_meq_L - h_meq_L
        
        return max(0, total_alk_meq_L * 50.045)  # Convert to mg/L as CaCO3
    
    def get_tds_mg_L(self) -> float:
        """Calculate total dissolved solids."""
        return sum(self.ion_concentrations_mg_L.values())
    
    def get_ionic_strength_mol_L(self) -> float:
        """Calculate ionic strength in mol/L."""
        ionic_strength = 0.0
        
        for ion, conc_mg_L in self.ion_concentrations_mg_L.items():
            if ion in CHARGE_DATA and CHARGE_DATA[ion] != 0:
                charge = CHARGE_DATA[ion]
                mw = MOLECULAR_WEIGHTS.get(ion, 100)  # Default MW if not found
                conc_mol_L = conc_mg_L / (mw * 1000)
                ionic_strength += 0.5 * conc_mol_L * charge**2
                
        return ionic_strength


class IXConfigurationInput(BaseModel):
    """Input for optimize_ix_configuration tool."""
    water_analysis: MCASWaterComposition = Field(..., description="Feed water composition in MCAS format")
    max_vessel_diameter_m: float = Field(2.4, description="Maximum vessel diameter for shipping constraints")
    target_treated_quality: Optional[Dict[str, float]] = Field(
        None,
        description="Optional target quality parameters (e.g., {'hardness_mg_L_CaCO3': 5})"
    )


class VesselConfiguration(BaseModel):
    """Configuration for a single IX stage."""
    resin_type: str = Field(..., description="Type of resin (e.g., 'SAC', 'WAC_H', 'WAC_Na')")
    number_service: int = Field(..., description="Number of vessels in service")
    number_standby: int = Field(..., description="Number of standby vessels")
    diameter_m: float = Field(..., description="Vessel diameter in meters")
    bed_depth_m: float = Field(..., description="Resin bed depth in meters")
    freeboard_m: float = Field(..., description="Freeboard height in meters")
    resin_volume_m3: float = Field(..., description="Total resin volume in m³")
    vessel_height_m: float = Field(..., description="Total vessel height in meters")


class DegasserConfiguration(BaseModel):
    """Configuration for CO2 degasser tower."""
    type: str = Field("packed_tower", description="Type of degasser")
    packing: str = Field("pall_rings", description="Type of packing material")
    diameter_m: float = Field(..., description="Tower diameter in meters")
    packed_height_m: float = Field(..., description="Packed bed height in meters")
    hydraulic_loading_m_hr: float = Field(40.0, description="Hydraulic loading rate in m/hr")
    air_flow_m3_hr: float = Field(..., description="Air flow rate in m³/hr")
    fan_discharge_pressure_mbar: float = Field(100.0, description="Fan discharge pressure in mbar")
    fan_power_kW: float = Field(..., description="Fan power in kW")


class IXConfigurationOutput(BaseModel):
    """Output from optimize_ix_configuration tool."""
    flowsheet_type: str = Field(..., description="Selected flowsheet configuration")
    flowsheet_description: str = Field(..., description="Description of the selected flowsheet")
    
    # Na+ competition analysis
    na_competition_factor: float = Field(..., description="Capacity reduction factor due to Na+ competition (0-1)")
    effective_capacity: Dict[str, float] = Field(..., description="Effective resin capacities accounting for Na+ competition")
    
    # Vessel configurations
    ix_vessels: Dict[str, VesselConfiguration] = Field(..., description="Vessel configurations for each IX stage")
    
    # Degasser configuration
    degasser: DegasserConfiguration = Field(..., description="CO2 degasser configuration")
    
    # Hydraulic summary
    hydraulics: Dict[str, float] = Field(
        ...,
        description="Hydraulic parameters (bed_volumes_per_hour, linear_velocity_m_hr, etc.)"
    )
    
    # Warnings or recommendations
    warnings: Optional[List[str]] = Field(None, description="Any warnings or recommendations")
    
    # Flowsheet characteristics
    characteristics: Optional[Dict[str, Any]] = Field(None, description="Flowsheet characteristics and suitability info")
    
    # Economics
    economics: Optional[Dict[str, Any]] = Field(None, description="Economic analysis (CAPEX, OPEX, LCOW)")


class IXMultiConfigurationOutput(BaseModel):
    """Output containing ALL flowsheet configurations."""
    status: str = Field("success", description="Status of the configuration generation")
    configurations: List[IXConfigurationOutput] = Field(..., description="All available flowsheet configurations")
    summary: Dict[str, Any] = Field(..., description="Summary of water analysis and recommendations")
    water_chemistry_analysis: Dict[str, float] = Field(..., description="Analyzed water chemistry parameters")


class IXSimulationInput(BaseModel):
    """Input for simulate_ix_system tool."""
    configuration: IXConfigurationOutput = Field(..., description="Configuration from optimize_ix_configuration")
    water_analysis: MCASWaterComposition = Field(..., description="Feed water composition in MCAS format")
    
    breakthrough_criteria: Dict[str, float] = Field(
        {"hardness_mg_L_CaCO3": 5.0, "min_pH": 4.5},
        description="Breakthrough criteria for different parameters"
    )
    
    regenerant_parameters: Dict[str, Any] = Field(
        {
            "SAC": {"chemical": "NaCl", "concentration_percent": 10, "level_kg_m3": 160},
            "WAC": {"chemical": "HCl", "concentration_percent": 5, "level_kg_m3": 80}
        },
        description="Regeneration parameters for each resin type"
    )
    
    acid_options: Optional[Dict[str, Any]] = Field(
        {"chemicals": ["H2SO4", "HCl"], "target_conversion": 0.99, "target_pH": 7.0},
        description="Acid options for bicarbonate conversion (if applicable)"
    )
    
    regeneration: Optional[Dict[str, Any]] = Field(
        {
            "regenerant_type": "NaCl",
            "concentration_percent": 10.0,
            "dose_kg_m3_resin": 120.0,
            "flow_rate_bv_hr": 2.0,
            "slow_rinse_bv": 2.0,
            "fast_rinse_bv": 4.0
        },
        description="Regeneration parameters for simulation"
    )
    
    simulation_options: Dict[str, Any] = Field(
        {
            "time_steps": 100, 
            "parallel_execution": True,
            "model_type": "equilibrium",  # Default to existing model
            "transport_cells": 20,  # For TRANSPORT model
            "industrial_efficiency": None  # Auto-select based on resin type
        },
        description="Simulation options including model type ('equilibrium' or 'transport')"
    )


class BreakthroughCurve(BaseModel):
    """Breakthrough curve data for a specific ion."""
    ion: str = Field(..., description="Ion species (e.g., Ca_2+, Mg_2+)")
    breakthrough_bed_volumes: float = Field(..., description="Bed volumes to breakthrough")
    loading_eq_L: float = Field(0.0, description="Loading at breakthrough in eq/L")
    leakage_mg_L: float = Field(0.0, description="Average leakage concentration in mg/L")


class IXPerformanceMetrics(BaseModel):
    """Performance metrics for an IX stage - extended version."""
    # Basic metrics (backward compatible)
    breakthrough_time_hours: float = Field(..., description="Time to breakthrough in hours")
    bed_volumes_treated: float = Field(..., description="Bed volumes treated before regeneration")
    regenerant_consumption_kg: float = Field(..., description="Regenerant consumption per cycle in kg")
    average_hardness_leakage_mg_L: float = Field(..., description="Average hardness in treated water")
    capacity_utilization_percent: float = Field(..., description="Percentage of theoretical capacity utilized")
    
    # Extended metrics for WaterTAP model
    vessel_name: Optional[str] = Field(None, description="Name of the vessel")
    resin_type: Optional[str] = Field(None, description="Type of resin (SAC, WAC_H, WAC_Na)")
    service_cycle_time_hr: Optional[float] = Field(None, description="Service cycle time in hours")
    service_flow_rate_m3_hr: Optional[float] = Field(None, description="Service flow rate in m³/hr")
    bed_volumes_to_breakthrough: Optional[float] = Field(None, description="Bed volumes to breakthrough")
    operating_capacity_eq_L: Optional[float] = Field(None, description="Operating capacity in eq/L")
    hardness_removal_percent: Optional[float] = Field(None, description="Hardness removal percentage")
    sodium_leakage_mg_L: Optional[float] = Field(0.0, description="Sodium leakage in mg/L")
    silica_leakage_mg_L: Optional[float] = Field(0.0, description="Silica leakage in mg/L")
    pressure_drop_bar: Optional[float] = Field(None, description="Pressure drop across bed in bar")
    rinse_volume_m3: Optional[float] = Field(None, description="Rinse volume in m³")
    regenerant_dose_kg_m3_resin: Optional[float] = Field(None, description="Regenerant dose in kg/m³ resin")
    regenerant_volume_m3: Optional[float] = Field(None, description="Regenerant volume in m³")
    waste_volume_m3: Optional[float] = Field(None, description="Waste volume in m³")
    breakthrough_curves: Optional[List['BreakthroughCurve']] = Field(None, description="Breakthrough curves for different ions")
    
    # Legacy fields for backward compatibility
    regenerant_chemical: Optional[str] = Field(None, description="Type of regenerant chemical")
    specific_regenerant_g_L: Optional[float] = Field(None, description="Specific regenerant consumption in g/L")
    cycles_completed: Optional[int] = Field(None, description="Number of cycles completed")
    total_throughput_m3: Optional[float] = Field(None, description="Total throughput in m³")


class WaterQualityProgression(BaseModel):
    """Water quality at different stages of treatment."""
    stage: str = Field(..., description="Treatment stage name")
    pH: float = Field(..., description="pH value")
    temperature_celsius: float = Field(..., description="Temperature in Celsius")
    ion_concentrations_mg_L: Dict[str, float] = Field(..., description="Ion concentrations in MCAS format")
    alkalinity_mg_L_CaCO3: float = Field(..., description="Alkalinity as CaCO3")
    hardness_mg_L_CaCO3: float = Field(..., description="Total hardness as CaCO3")
    tds_mg_L: float = Field(..., description="Total dissolved solids")


class IXSimulationOutput(BaseModel):
    """Output from simulate_ix_system tool."""
    status: str = Field(..., description="Simulation status")
    watertap_notebook_path: str = Field(..., description="Path to executed Jupyter notebook")
    model_type: Optional[str] = Field("direct", description="Simulation model type (direct, transport, watertap)")
    actual_runtime_seconds: Optional[float] = Field(None, description="Actual simulation runtime in seconds")
    
    # Treated water quality for RO feed
    treated_water: MCASWaterComposition = Field(..., description="Treated water quality in MCAS format")
    
    # Performance metrics by stage
    ix_performance: Dict[str, IXPerformanceMetrics] = Field(..., description="Performance metrics for each IX stage")
    
    # Degasser performance
    degasser_performance: Dict[str, float] = Field(
        ...,
        description="Degasser performance (influent_CO2_mg_L, effluent_CO2_mg_L, efficiency, etc.)"
    )
    
    # Acid requirements (if applicable)
    acid_requirements: Optional[Dict[str, Dict[str, float]]] = Field(
        None,
        description="Acid dosing requirements for different acid types"
    )
    
    # Water quality progression
    water_quality_progression: List[WaterQualityProgression] = Field(
        ...,
        description="Water quality at each treatment stage"
    )
    
    # Chemical consumption
    chemical_consumption: Optional[Dict[str, float]] = Field(
        None,
        description="Chemical consumption (NaCl_kg_per_day, HCl_kg_per_day, etc.)"
    )
    
    # Waste generation
    waste_generation: Optional[Dict[str, float]] = Field(
        None,
        description="Waste generation (brine_m3_per_day, sludge_kg_per_day)"
    )
    
    # Economic results
    economics: Dict[str, float] = Field(
        ...,
        description="Economic metrics (capital_cost, operating_cost_annual, cost_per_m3)"
    )
    
    # Breakthrough curves and other detailed results
    detailed_results: Optional[Dict[str, Any]] = Field(
        None,
        description="Detailed simulation results including breakthrough curves"
    )
    
    # Recommendations or warnings
    recommendations: Optional[List[str]] = Field(None, description="Operational recommendations based on simulation")
    warnings: Optional[List[str]] = Field(None, description="Any warnings from the simulation")
    
    @property
    def performance_metrics(self) -> Optional[IXPerformanceMetrics]:
        """Get primary vessel performance for backward compatibility"""
        if self.ix_performance:
            # Return the first vessel's metrics
            return list(self.ix_performance.values())[0]
        return None
    
    @property
    def vessel_performance(self) -> Optional[Dict[str, Any]]:
        """Get vessel performance dict for backward compatibility"""
        if self.ix_performance:
            return {name: {"utilization": metrics.capacity_utilization_percent, 
                          "loading": metrics.bed_volumes_treated}
                   for name, metrics in self.ix_performance.items()}
        return None