"""
Unified Schema Definitions for IX Simulations

Provides Pydantic v2 models for standardized input/output across all IX engines.
"""

from typing import Dict, List, Optional, Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ============= Input Schemas =============

class WaterComposition(BaseModel):
    """Water composition for IX simulation"""
    flow_m3h: float = Field(description="Flow rate in m³/hr")
    temperature_c: float = Field(default=25.0, description="Temperature in Celsius")
    ph: float = Field(default=7.8, description="pH")
    ions_mg_l: Dict[str, float] = Field(description="Ion concentrations in mg/L")
    
    # Common ions with defaults
    ca_mg_l: Optional[float] = Field(default=None, description="Calcium in mg/L")
    mg_mg_l: Optional[float] = Field(default=None, description="Magnesium in mg/L")
    na_mg_l: Optional[float] = Field(default=None, description="Sodium in mg/L")
    cl_mg_l: Optional[float] = Field(default=None, description="Chloride in mg/L")
    hco3_mg_l: Optional[float] = Field(default=None, description="Bicarbonate in mg/L")
    so4_mg_l: Optional[float] = Field(default=None, description="Sulfate in mg/L")
    
    def get_ion_dict(self) -> Dict[str, float]:
        """Convert to ion dictionary, merging individual fields with ions_mg_l"""
        ions = self.ions_mg_l.copy() if self.ions_mg_l else {}
        
        # Add individual ion fields if specified
        if self.ca_mg_l is not None:
            ions['Ca_2+'] = self.ca_mg_l
        if self.mg_mg_l is not None:
            ions['Mg_2+'] = self.mg_mg_l
        if self.na_mg_l is not None:
            ions['Na_+'] = self.na_mg_l
        if self.cl_mg_l is not None:
            ions['Cl_-'] = self.cl_mg_l
        if self.hco3_mg_l is not None:
            ions['HCO3_-'] = self.hco3_mg_l
        if self.so4_mg_l is not None:
            ions['SO4_2-'] = self.so4_mg_l
            
        return ions


class VesselConfiguration(BaseModel):
    """IX vessel configuration"""
    diameter_m: float = Field(description="Vessel diameter in meters")
    bed_depth_m: float = Field(description="Resin bed depth in meters")
    number_in_service: int = Field(default=1, description="Number of vessels in service")
    number_in_parallel: int = Field(default=1, description="Number of parallel trains")
    bed_volume_l: Optional[float] = Field(default=None, description="Calculated bed volume in liters")
    resin_volume_m3: Optional[float] = Field(default=None, description="Resin volume in m³")
    bed_porosity: float = Field(default=0.35, description="Bed porosity")
    resin_capacity_eq_l: float = Field(default=2.0, description="Resin capacity in eq/L")
    
    def model_post_init(self, __context):
        """Post-init processing to calculate derived values"""
        # Calculate bed_volume_l if not provided
        if self.bed_volume_l is None:
            self.bed_volume_l = 3.14159 * (self.diameter_m / 2) ** 2 * self.bed_depth_m * 1000
        
        # Calculate resin_volume_m3 if not provided
        if self.resin_volume_m3 is None:
            self.resin_volume_m3 = 3.14159 * (self.diameter_m / 2) ** 2 * self.bed_depth_m


class PerformanceTargets(BaseModel):
    """Performance targets for IX system"""
    hardness_mg_l_caco3: float = Field(default=5.0, description="Target effluent hardness as CaCO3")
    alkalinity_mg_l_caco3: Optional[float] = Field(default=None, description="Target alkalinity (WAC-H)")
    tds_mg_l: Optional[float] = Field(default=None, description="Target TDS")


class CycleConfiguration(BaseModel):
    """IX cycle configuration"""
    backwash: bool = Field(default=True, description="Enable backwash")
    regenerant_type: Literal["NaCl", "HCl", "H2SO4", "NaOH"] = Field(default="NaCl")
    regenerant_concentration_wt: float = Field(default=10.0, description="Weight percent")
    regenerant_dose_g_per_l: Optional[float] = Field(default=100.0, description="Dose in g/L resin")
    stoich_factor: float = Field(default=1.2, description="Stoichiometric excess factor")
    rinse_strategy: Literal["fast", "slow", "fast+slow"] = Field(default="fast+slow")
    flow_direction: Literal["co-current", "counter-current"] = Field(default="counter-current")


class EconomicParameters(BaseModel):
    """Economic parameters for costing"""
    electricity_usd_kwh: float = Field(default=0.07, description="Electricity cost in $/kWh")
    nacl_usd_kg: float = Field(default=0.12, description="NaCl cost in $/kg")
    hcl_usd_kg: float = Field(default=0.25, description="HCl cost in $/kg")
    h2so4_usd_kg: float = Field(default=0.20, description="H2SO4 cost in $/kg")
    naoh_usd_kg: float = Field(default=0.35, description="NaOH cost in $/kg")
    resin_usd_m3: float = Field(default=2800.0, description="Resin cost in $/m³")
    resin_replacement_rate: float = Field(default=0.05, description="Annual replacement fraction")
    discount_rate: float = Field(default=0.08, description="Discount rate for LCOW")
    plant_lifetime_years: int = Field(default=20, description="Plant lifetime in years")


class SimulationOptions(BaseModel):
    """Simulation options"""
    timeout_seconds: int = Field(default=120, description="Simulation timeout")
    write_artifacts: bool = Field(default=True, description="Write result artifacts")
    generate_plots: bool = Field(default=False, description="Generate breakthrough plots")
    full_data: bool = Field(default=False, description="Return complete simulation data")


class IXSimulationInput(BaseModel):
    """Complete IX simulation input"""
    schema_version: str = Field(default="1.0.0")
    resin_type: Literal["SAC", "WAC_Na", "WAC_H"] = Field(description="Resin type")
    water: WaterComposition = Field(description="Feed water composition")
    vessel: VesselConfiguration = Field(description="Vessel configuration")
    targets: PerformanceTargets = Field(description="Performance targets")
    cycle: CycleConfiguration = Field(description="Cycle configuration")
    pricing: Optional[EconomicParameters] = Field(default=None, description="Economic parameters")
    engine: Literal["phreeqc", "watertap", "watertap_hybrid"] = Field(default="phreeqc")
    options: Optional[SimulationOptions] = Field(default=None)


# ============= Output Schemas =============

class EngineInfo(BaseModel):
    """Engine metadata"""
    name: str = Field(description="Engine name")
    chemistry: str = Field(description="Chemistry engine")
    flowsheet: Optional[str] = Field(default=None, description="Flowsheet engine")
    costing: Optional[str] = Field(default=None, description="Costing method")
    version: str = Field(description="Engine version")
    mode: str = Field(description="Simulation mode")


class PerformanceMetrics(BaseModel):
    """System performance metrics"""
    service_bv_to_target: float = Field(description="Bed volumes to breakthrough")
    service_hours: float = Field(description="Service run time in hours")
    effluent_hardness_mg_l_caco3: float = Field(description="Effluent hardness")
    effluent_alkalinity_mg_l_caco3: Optional[float] = Field(default=None)
    effluent_ph: float = Field(description="Effluent pH")
    effluent_tds_mg_l: float = Field(description="Effluent TDS")
    delta_p_bar: float = Field(default=0.6, description="Pressure drop in bar")
    sec_kwh_m3: float = Field(description="Specific energy consumption")
    capacity_utilization_percent: float = Field(description="Resin capacity utilization")


class IonTracking(BaseModel):
    """Ion-specific tracking"""
    feed_mg_l: Dict[str, float] = Field(description="Feed ion concentrations")
    effluent_mg_l: Dict[str, float] = Field(description="Average effluent concentrations")
    waste_mg_l: Dict[str, float] = Field(description="Waste stream concentrations")
    removal_percent: Dict[str, float] = Field(description="Removal percentages by ion")


class MassBalance(BaseModel):
    """Mass balance information"""
    regenerant_kg_cycle: float = Field(description="Regenerant per cycle")
    backwash_m3_cycle: float = Field(description="Backwash volume per cycle")
    rinse_m3_cycle: float = Field(description="Rinse volume per cycle")
    waste_m3_cycle: float = Field(description="Total waste per cycle")
    hardness_removed_kg_caco3: float = Field(description="Hardness removed per cycle")
    closure_percent: float = Field(default=99.0, description="Mass balance closure")


class UnitCosts(BaseModel):
    """Itemized capital costs"""
    vessels_usd: float = Field(description="Vessel costs")
    resin_initial_usd: float = Field(description="Initial resin charge")
    pumps_usd: float = Field(description="Pump costs")
    degasser_usd: Optional[float] = Field(default=None, description="Degasser cost (WAC-H)")
    instrumentation_usd: float = Field(description="Instrumentation costs")
    installation_factor: float = Field(default=2.5, description="Installation multiplier")


class EconomicsResult(BaseModel):
    """Economic analysis results"""
    capital_cost_usd: float = Field(description="Total capital cost")
    operating_cost_usd_year: float = Field(description="Annual operating cost")
    regenerant_cost_usd_year: float = Field(description="Annual regenerant cost")
    resin_replacement_cost_usd_year: float = Field(description="Annual resin replacement")
    energy_cost_usd_year: float = Field(description="Annual energy cost")
    waste_disposal_cost_usd_year: Optional[float] = Field(default=None)
    lcow_usd_m3: float = Field(description="Levelized cost of water")
    sec_kwh_m3: float = Field(description="Specific energy consumption")
    unit_costs: UnitCosts = Field(description="Itemized capital costs")


class SolverInfo(BaseModel):
    """Solver information"""
    engine: str = Field(description="Engine used")
    termination_condition: str = Field(description="Solver termination status")
    solve_time_seconds: Optional[float] = Field(default=None)
    iterations: Optional[int] = Field(default=None)


class ExecutionContext(BaseModel):
    """Execution context and versions"""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    watertap_version: Optional[str] = Field(default=None)
    idaes_version: Optional[str] = Field(default=None)
    pyomo_version: Optional[str] = Field(default=None)
    phreeqpython_version: Optional[str] = Field(default=None)
    git_sha: str = Field(default="unknown")
    git_dirty: bool = Field(default=False)


class IXSimulationResult(BaseModel):
    """Complete IX simulation result"""
    schema_version: str = Field(default="1.0.0")
    status: Literal["success", "warning", "error", "timeout"] = Field(description="Simulation status")
    run_id: str = Field(description="Unique run identifier")
    performance: PerformanceMetrics = Field(description="Performance metrics")
    ion_tracking: IonTracking = Field(description="Ion-specific results")
    mass_balance: MassBalance = Field(description="Mass balance")
    economics: Optional[EconomicsResult] = Field(default=None, description="Economic analysis")
    solve_info: SolverInfo = Field(description="Solver information")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")
    context: ExecutionContext = Field(description="Execution context")
    artifact_dir: str = Field(description="Directory containing artifacts")
    artifacts: List[str] = Field(default_factory=list, description="Generated artifact paths")
    
    # Raw data for advanced users
    breakthrough_data: Optional[Dict[str, Any]] = Field(default=None, description="Raw breakthrough data")
    simulation_details: Optional[Dict[str, Any]] = Field(default=None, description="Detailed simulation info")


# ============= Legacy Compatibility =============

def convert_legacy_sac_output(legacy_output: Dict[str, Any]) -> IXSimulationResult:
    """
    Convert legacy SAC simulation output to unified schema.
    
    Args:
        legacy_output: Output from existing SAC simulation
        
    Returns:
        Unified simulation result
    """
    # Extract regeneration results
    regen = legacy_output.get("regeneration_results", {})
    
    # Build performance metrics
    performance = PerformanceMetrics(
        service_bv_to_target=legacy_output.get("breakthrough_bv", 0),
        service_hours=legacy_output.get("service_time_hours", 0),
        effluent_hardness_mg_l_caco3=legacy_output.get("breakthrough_hardness_mg_l_caco3", 5.0),
        effluent_ph=7.8,  # Default or extract from data
        effluent_tds_mg_l=0,  # Calculate or default
        sec_kwh_m3=0.05,  # Default or calculate
        capacity_utilization_percent=legacy_output.get("capacity_utilization_percent", 0)
    )
    
    # Build mass balance
    mass_balance = MassBalance(
        regenerant_kg_cycle=regen.get("regenerant_consumed_kg", 0),
        backwash_m3_cycle=0,  # Extract if available
        rinse_m3_cycle=0,  # Extract if available
        waste_m3_cycle=regen.get("waste_volume_m3", 0),
        hardness_removed_kg_caco3=regen.get("hardness_eluted_kg_caco3", 0),
        closure_percent=99.0
    )
    
    # Placeholder for other sections
    ion_tracking = IonTracking(
        feed_mg_l={},
        effluent_mg_l={},
        waste_mg_l={},
        removal_percent={}
    )
    
    solve_info = SolverInfo(
        engine="phreeqc_direct",
        termination_condition="success"
    )
    
    context = ExecutionContext()
    
    return IXSimulationResult(
        status=legacy_output.get("status", "success"),
        run_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
        performance=performance,
        ion_tracking=ion_tracking,
        mass_balance=mass_balance,
        economics=None,  # Will be added in Phase 6
        solve_info=solve_info,
        warnings=legacy_output.get("warnings", []),
        context=context,
        artifact_dir="results",
        artifacts=[],
        breakthrough_data=legacy_output.get("breakthrough_data"),
        simulation_details=legacy_output.get("simulation_details")
    )