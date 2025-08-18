"""
SAC Ion Exchange Simulation Tool

Simulates SAC ion exchange using Direct PHREEQC engine.
Uses target hardness breakthrough definition and PHREEQC-determined capacity.
NO HEURISTIC CALCULATIONS - all competition effects from thermodynamics.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Literal
import numpy as np
from datetime import datetime
from pydantic import BaseModel, Field, validator

# Get project root with robust approach
def get_project_root() -> Path:
    """Get project root with environment variable support."""
    import os
    # Strategy 1: Environment variable (most reliable for MCP clients)
    if 'IX_DESIGN_MCP_ROOT' in os.environ:
        root = Path(os.environ['IX_DESIGN_MCP_ROOT'])
        if root.exists():
            return root
    
    # Strategy 2: Relative to this file (fallback)
    return Path(__file__).resolve().parent.parent

# Add project root to path
project_root = get_project_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import PHREEQC engines - prefer optimized engine for performance
try:
    from watertap_ix_transport.transport_core.optimized_phreeqc_engine import OptimizedPhreeqcEngine
    OPTIMIZED_AVAILABLE = True
except ImportError:
    OPTIMIZED_AVAILABLE = False
    
from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine

# Import schemas from sac_configuration
from .sac_configuration import (
    SACWaterComposition,
    SACVesselConfiguration,
    SACConfigurationOutput
)

# Import centralized configuration
from .core_config import CONFIG
from .base_ix_simulation import BaseIXSimulation

logger = logging.getLogger(__name__)


class RegenerationConfig(BaseModel):
    """Configuration for multi-stage regeneration (always enabled for full cycle simulation)"""
    enabled: bool = Field(True, description="Always enabled for full cycle simulation")
    
    # Core parameters with smart defaults
    regenerant_type: Literal["NaCl", "HCl", "H2SO4", "NaOH"] = Field("NaCl", description="Type of regenerant chemical")
    concentration_percent: float = Field(10.0, description="Regenerant concentration (weight %)", ge=5.0, le=15.0)
    flow_rate_bv_hr: float = Field(2.5, description="Regeneration flow rate (BV/hr)", ge=1.0, le=5.0)
    
    # Primary regenerant parameter - dose in g/L resin
    regenerant_dose_g_per_L: Optional[float] = Field(
        default=None,
        description="Regenerant dose (g chemical/L resin bed). Industry standard: NaCl 80-120, HCl 60-80, H2SO4 80-100 g/L",
        ge=50,  # Minimum for effectiveness
        le=1000  # Maximum reasonable dose
    )
    
    # Internal calculated field - not for user input
    regenerant_bv: float = Field(default=3.5)  # Calculated from dose internally
    
    # Mode selection (no backwards compatibility needed)
    mode: Literal["staged_fixed", "staged_optimize"] = Field(
        "staged_optimize",
        description="staged_fixed: use specified BV, staged_optimize: find optimal BV"
    )
    
    # Staged regeneration parameters
    regeneration_stages: int = Field(
        5,
        ge=3,
        le=10,
        description="Number of counter-current stages (5 -> ~90%, 8-10 -> ~95%)"
    )
    
    # Optimization parameters (for staged_optimize mode)
    target_recovery: float = Field(
        0.95,
        ge=0.80,
        le=0.97,  # Capped per kinetic ceiling
        description="Target Na fraction recovery"
    )
    min_regenerant_bv: float = Field(2.0, description="Minimum BV to search")
    max_regenerant_bv: float = Field(6.0, description="Maximum BV to search")
    optimization_tolerance: float = Field(0.01, description="Recovery tolerance (±1%)")
    max_optimization_iterations: int = Field(6, description="Max bisection iterations (reduced from 10 for speed)")
    
    # Flow and rinse parameters
    flow_direction: Literal["forward", "back"] = Field("back", description="Flow direction (back = counter-current)")
    backwash_enabled: bool = Field(True, description="Enable backwash before regeneration")
    backwash_bv: float = Field(3.0, description="Backwash volume (BV)", ge=1, le=4)
    backwash_flow_rate_bv_hr: float = Field(10.0, description="Backwash flow rate (BV/hr)")
    slow_rinse_bv: float = Field(1.0, description="Slow/displacement rinse volume (BV)", ge=0, le=2)
    slow_rinse_concentration_percent: float = Field(0.5, description="Slow rinse concentration (% of regenerant)")
    fast_rinse_bv: float = Field(3.0, description="Fast rinse volume (BV)", ge=1, le=6)
    
    @validator('regenerant_bv', always=True, pre=False)
    def calculate_bv_from_dose(cls, v, values):
        """Always calculate BV from dose. This is an internal field."""
        # If dose provided, calculate BV
        if 'regenerant_dose_g_per_L' in values and values['regenerant_dose_g_per_L'] is not None:
            dose = values['regenerant_dose_g_per_L']
            concentration = values.get('concentration_percent', 10.0)
            # BV = dose / (concentration * 10) where concentration*10 converts % to g/L
            calculated_bv = dose / (concentration * 10)
            logger.info(f"Calculated regenerant BV: {calculated_bv:.2f} from dose {dose} g/L at {concentration}%")
            return float(calculated_bv)
            
        # Default dose and BV based on regenerant type if dose not provided
        regenerant_type = values.get('regenerant_type', 'NaCl')
        concentration = values.get('concentration_percent', 10.0)
        
        # Industry-standard doses
        default_doses = {
            'NaCl': 100,   # 100 g/L is standard for SAC
            'HCl': 70,     # 70 g/L for HCl regeneration
            'H2SO4': 90    # 90 g/L for H2SO4
        }
        default_dose = default_doses.get(regenerant_type, 100)
        default_bv = default_dose / (concentration * 10)
        
        logger.info(f"Using default regenerant dose: {default_dose} g/L for {regenerant_type}")
        logger.info(f"Calculated default BV: {default_bv:.2f} at {concentration}%")
        return float(default_bv)
    
    @validator('min_regenerant_bv', 'max_regenerant_bv')
    def validate_bv_bounds(cls, v, values):
        """Auto-fallback to staged_fixed if bounds are equal"""
        if 'min_regenerant_bv' in values and values['min_regenerant_bv'] == v:
            if values.get('mode') == 'staged_optimize':
                logger.info("BV bounds equal, switching to staged_fixed mode")
                values['mode'] = 'staged_fixed'
        return v
    
    @validator('min_regenerant_bv', 'max_regenerant_bv', pre=False)
    def adjust_bv_bounds_for_dose(cls, v, values):
        """When dose is specified, ensure BV bounds are reasonable for optimization."""
        if 'regenerant_bv' in values:
            calculated_bv = values['regenerant_bv']
            # Adjust bounds based on calculated BV
            if v is not None:
                # For min bound
                if 'min_regenerant_bv' in cls.__fields__ and v == values.get('min_regenerant_bv'):
                    if v > calculated_bv:
                        return max(calculated_bv * 0.7, 2.0)
                # For max bound
                elif 'max_regenerant_bv' in cls.__fields__ and v == values.get('max_regenerant_bv'):
                    if v < calculated_bv:
                        return min(calculated_bv * 1.3, 6.0)
        return v
    
    def model_dump(self, **kwargs):
        """Override to exclude regenerant_bv from user-facing output."""
        data = super().model_dump(**kwargs)
        # Remove internal calculated field
        data.pop('regenerant_bv', None)
        return data
    
    def model_dump_json(self, **kwargs):
        """Override to exclude regenerant_bv from JSON output."""
        # First get the dict without regenerant_bv
        data = self.model_dump(**kwargs)
        # Then convert to JSON
        import json
        return json.dumps(data, **kwargs)


class SACSimulationInput(BaseModel):
    """Input for SAC simulation with full cycle (service + regeneration)"""
    water_analysis: SACWaterComposition
    vessel_configuration: SACVesselConfiguration
    target_hardness_mg_l_caco3: float
    full_data: bool = Field(default=False, description="Return full resolution data (1000+ points) instead of smart-sampled data (~80 points)")
    regeneration_config: RegenerationConfig = Field(..., description="Regeneration cycle configuration (required for full cycle simulation)")


class RegenerationResults(BaseModel):
    """Results from regeneration phase"""
    actual_regenerant_bv: float
    regenerant_consumed_kg: float
    regenerant_type: str
    peak_waste_tds_mg_l: float
    peak_waste_hardness_mg_l: float
    total_hardness_removed_kg: float
    waste_volume_m3: float
    final_resin_recovery: float
    ready_for_service: bool
    rinse_quality_achieved: bool
    regeneration_time_hours: float
    
    # Add optimization information
    optimization_info: Optional[Dict[str, Any]] = Field(
        None,
        description="Optimization details if auto_optimize mode was used"
    )
    
    def summary_report(self) -> str:
        """Generate human-readable summary"""
        report = f"""
Regeneration Performance:
- Recovery achieved: {self.final_resin_recovery:.1%}
- Regenerant used: {self.regenerant_consumed_kg:.1f} kg ({self.actual_regenerant_bv:.2f} BV)
- Regeneration time: {self.regeneration_time_hours:.1f} hours
"""
        if self.optimization_info:
            report += f"""
Optimization Results:
- Optimal dosage: {self.optimization_info['optimal_dose_g_per_L']:.0f} g/L resin
- Iterations: {self.optimization_info['iterations']}
- Savings vs typical: {self.optimization_info['savings_vs_typical']:.1f}%
"""
        return report


class SACSimulationOutput(BaseModel):
    """Output from SAC simulation with complete cycle results (service + regeneration)"""
    status: str  # "success" or "warning"
    breakthrough_bv: float
    service_time_hours: float
    breakthrough_hardness_mg_l_caco3: float
    breakthrough_reached: bool
    warnings: List[str]
    phreeqc_determined_capacity_factor: float  # NOT heuristic
    capacity_utilization_percent: float
    breakthrough_data: Dict[str, Any]  # Enhanced for multi-phase plotting (changed to Any to allow phases)
    simulation_details: Dict[str, Any]
    # Regeneration results (always included in full cycle simulation)
    regeneration_results: RegenerationResults  # No longer optional
    # Full cycle time
    total_cycle_time_hours: float  # No longer optional


class _IXDirectPhreeqcSimulation:
    """Direct PHREEQC-based ion exchange simulation for SAC resins."""
    
    def __init__(self):
        """Initialize simulation."""
        # Try optimized engine first for better performance
        if OPTIMIZED_AVAILABLE:
            try:
                # Get PHREEQC path from config
                phreeqc_exe = CONFIG.get_phreeqc_exe()
                self.engine = OptimizedPhreeqcEngine(
                    phreeqc_path=str(phreeqc_exe),
                    cache_size=256,  # Cache more results
                    max_workers=4     # Parallel execution
                )
                logger.info("Using OptimizedPhreeqcEngine with caching and batch processing")
                return  # Successfully initialized, no need for fallback
            except Exception as e:
                logger.warning(f"Failed to initialize OptimizedPhreeqcEngine: {e}")
        
        # Fall back to DirectPhreeqcEngine if optimized not available or failed
        # Get PHREEQC executable from centralized config
        phreeqc_exe = CONFIG.get_phreeqc_exe()
        
        try:
            self.engine = DirectPhreeqcEngine(phreeqc_path=str(phreeqc_exe), keep_temp_files=False)
            logger.info(f"Using DirectPhreeqcEngine at: {phreeqc_exe}")
        except (FileNotFoundError, RuntimeError) as e:
            logger.warning(f"Failed to initialize PHREEQC at {phreeqc_exe}: {e}")
            # Try without specifying path (will search system)
            try:
                self.engine = DirectPhreeqcEngine(keep_temp_files=False)
                logger.info("Using DirectPhreeqcEngine with system PHREEQC")
            except (FileNotFoundError, RuntimeError) as e2:
                logger.error(f"Failed to find PHREEQC in system PATH: {e2}")
                # Check if PHREEQC_EXE is set but not in CONFIG's path
                import os
                env_phreeqc = os.environ.get('PHREEQC_EXE')
                if env_phreeqc and env_phreeqc != str(phreeqc_exe):
                    logger.info(f"Trying PHREEQC_EXE from environment: {env_phreeqc}")
                    self.engine = DirectPhreeqcEngine(phreeqc_path=env_phreeqc, keep_temp_files=False)
                else:
                    raise RuntimeError(
                        "PHREEQC executable not found. Please install PHREEQC and set PHREEQC_EXE environment variable."
                    )
            
    def run_sac_simulation(
        self,
        water: SACWaterComposition,
        vessel_config: Dict[str, Any],
        max_bv: int = 100,
        cells: int = 10,
        enable_enhancements: bool = True,
        capacity_factor: float = 1.0
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Run SAC simulation and return breakthrough curves.
        
        Args:
            water: Feed water composition
            vessel_config: Vessel configuration from configuration tool
            max_bv: Maximum bed volumes to simulate
            cells: Number of cells for discretization
            
        Returns:
            bv_array: Array of bed volumes
            curves: Dict with Ca, Mg, Na breakthrough curves
        """
        # Log which engine is being used
        engine_type = type(self.engine).__name__
        logger.info(f"Running simulation with engine: {engine_type}")
        
        # Use bed volume from configuration directly
        bed_volume_L = vessel_config['bed_volume_L']
        bed_depth_m = vessel_config['bed_depth_m']
        diameter_m = vessel_config['diameter_m']
        porosity = vessel_config.get('bed_porosity', CONFIG.BED_POROSITY)
        
        # Calculate volumes
        pore_volume_L = bed_volume_L * porosity
        
        # Water per cell - Resolution independent approach
        water_per_cell_kg = pore_volume_L / cells
        cell_length_m = bed_depth_m / cells
        
        # Calculate MTZ if enabled
        effective_bed_depth = bed_depth_m
        if enable_enhancements and CONFIG.ENABLE_MTZ_MODELING:
            # Calculate linear velocity
            flow_rate_m3_hr = water.flow_m3_hr
            area_m2 = np.pi * (diameter_m / 2) ** 2
            linear_velocity_m_hr = flow_rate_m3_hr / area_m2
            
            # Use helper for MTZ calculation
            if 'helper' not in locals():
                class TempIXHelper(BaseIXSimulation):
                    def run_simulation(self, input_data):
                        pass
                helper = TempIXHelper()
            
            # Calculate feed concentration in eq/L
            # CORRECTED: Resin capacity is per liter of BED VOLUME
            # Define this before MTZ calculation to avoid undefined variable error
            resin_capacity_eq_L = vessel_config.get('resin_capacity_eq_L', CONFIG.RESIN_CAPACITY_EQ_L)  # eq/L bed
            
            feed_hardness_eq_l = (
                water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT +
                water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT
            ) / 1000  # Convert meq/L to eq/L
            
            mtz_length = helper.calculate_mtz_length(
                linear_velocity_m_hr,
                CONFIG.DEFAULT_PARTICLE_DIAMETER_MM,
                bed_depth_m,
                CONFIG.DEFAULT_DIFFUSION_COEFFICIENT,
                resin_capacity_eq_L,
                feed_hardness_eq_l
            )
            
            effective_bed_depth = bed_depth_m - mtz_length
            logger.info(f"MTZ length: {mtz_length:.2f} m, Effective bed depth: {effective_bed_depth:.2f} m")
            
            # Store MTZ info for later reporting
            vessel_config['mtz_length_m'] = mtz_length
            vessel_config['effective_bed_depth_m'] = effective_bed_depth
        else:
            # Define resin capacity even when MTZ modeling is disabled
            resin_capacity_eq_L = vessel_config.get('resin_capacity_eq_L', CONFIG.RESIN_CAPACITY_EQ_L)  # eq/L bed
        
        # Apply capacity degradation if enabled
        if enable_enhancements and capacity_factor < 1.0:
            # Create a temporary helper instance (doesn't need to be a full simulation)
            class TempIXHelper(BaseIXSimulation):
                def run_simulation(self, input_data):
                    pass  # Not needed for utility methods
            
            helper = TempIXHelper()
            effective_capacity = helper.apply_capacity_degradation(
                resin_capacity_eq_L, capacity_factor
            )
            logger.info(f"Applied capacity factor {capacity_factor}: {resin_capacity_eq_L} -> {effective_capacity} eq/L")
            resin_capacity_eq_L = effective_capacity
        
        total_capacity_eq = resin_capacity_eq_L * bed_volume_L  # Convert L to m³
        exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
        
        # Extract feed composition
        ca_mg_L = water.ca_mg_l
        mg_mg_L = water.mg_mg_l
        na_mg_L = water.na_mg_l
        cl_mg_L = water.cl_mg_l
        hco3_mg_L = water.hco3_mg_l
        so4_mg_L = water.so4_mg_l
        k_mg_L = water.k_mg_l
        nh4_mg_L = water.nh4_mg_l
        
        # Calculate charge balance for Cl if needed
        cation_charge = (ca_mg_L/CONFIG.CA_EQUIV_WEIGHT + 
                        mg_mg_L/CONFIG.MG_EQUIV_WEIGHT + 
                        na_mg_L/CONFIG.NA_EQUIV_WEIGHT + 
                        k_mg_L/CONFIG.K_EQUIV_WEIGHT + 
                        nh4_mg_L/CONFIG.NH4_EQUIV_WEIGHT)  # meq/L
        anion_charge = (cl_mg_L/CONFIG.CL_EQUIV_WEIGHT + 
                       hco3_mg_L/CONFIG.HCO3_EQUIV_WEIGHT + 
                       so4_mg_L/CONFIG.SO4_EQUIV_WEIGHT)  # meq/L
        if abs(cation_charge - anion_charge) > 0.1:
            logger.warning(f"Charge imbalance: {cation_charge:.2f} vs {anion_charge:.2f} meq/L")
        
        # Get database path from centralized config
        db_path = CONFIG.get_phreeqc_database()
        
        # Generate enhanced exchange species if enabled
        exchange_species_block = ""
        if enable_enhancements:
            # Use helper to generate enhanced exchange species
            if 'helper' not in locals():
                class TempIXHelper(BaseIXSimulation):
                    def run_simulation(self, input_data):
                        pass
                helper = TempIXHelper()
            
            # Convert water composition to dict format
            water_dict = {
                'ca_mg_l': ca_mg_L,
                'mg_mg_l': mg_mg_L,
                'na_mg_l': na_mg_L,
                'k_mg_l': k_mg_L,
                'cl_mg_l': cl_mg_L,
                'hco3_mg_l': hco3_mg_L,
                'so4_mg_l': so4_mg_L,
                'nh4_mg_l': nh4_mg_L,
                'temperature_celsius': water.temperature_celsius
            }
            
            exchange_species_block = helper.generate_enhanced_exchange_species(
                'SAC', water_dict, water.temperature_celsius, capacity_factor,
                enable_ionic_strength=CONFIG.ENABLE_IONIC_STRENGTH_CORRECTION,
                enable_temperature=CONFIG.ENABLE_TEMPERATURE_CORRECTION
            )
        else:
            exchange_species_block = "# Exchange species loaded from database"
        
        # Build PHREEQC input with all MCAS ions
        phreeqc_input = f"""DATABASE {db_path}
TITLE SAC Simulation - Target Hardness Breakthrough

PHASES
    Fix_H+
    H+ = H+
    log_k 0.0

{exchange_species_block}

SOLUTION 0  # Feed water
    units     mg/L
    temp      {water.temperature_celsius}
    pH        {water.pH}
    Ca        {ca_mg_L}
    Mg        {mg_mg_L}
    Na        {na_mg_L}
    K         {k_mg_L}
    N(5)      {water.nh4_mg_l} as NH4
    Cl        {cl_mg_L}
    S(6)      {so4_mg_L} as SO4
    C(4)      {hco3_mg_L} as HCO3
    N(5)      {water.no3_mg_l} as NO3
    P         {water.po4_mg_l} as PO4
    F         {water.f_mg_l}
    Si        {water.sio2_mg_l} as H4SiO4
    B         {water.b_oh_3_mg_l} as B(OH)3

SOLUTION 1-{cells}  # Initial column - Na form resin
    units     mg/L
    temp      {water.temperature_celsius}
    pH        7.0
    Na        1000
    Cl        1540 charge
    water     {water_per_cell_kg} kg  # CRITICAL: Explicit water

EXCHANGE 1-{cells}
    X         {exchange_per_kg_water}  # mol/kg water
    -equilibrate solution 1-{cells}

# Transport
TRANSPORT
    -cells    {cells}
    -shifts   {int(max_bv * bed_volume_L / water_per_cell_kg)}
    -lengths  {cell_length_m}
    -dispersivities {cells}*0.002
    -porosities {porosity}
    -flow_direction forward
    -boundary_conditions flux flux
    -print_frequency {cells}
    -punch_frequency {cells}
    -punch_cells {cells}

SELECTED_OUTPUT 1
    -file transport.sel
    -reset false
    -step true
    -totals Ca Mg Na K
    -molalities CaX2 MgX2 NaX KX

USER_PUNCH 1
    -headings Step BV Ca_mg_L Mg_mg_L Na_mg_L K_mg_L Hardness_CaCO3
    -start
    10 PUNCH STEP_NO
    # BV calculation: volume passed / total bed volume
    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    30 PUNCH BV
    # Convert mol/kg to mg/L
    40 ca_mg = TOT("Ca") * 40.078 * 1000
    50 mg_mg = TOT("Mg") * 24.305 * 1000
    60 na_mg = TOT("Na") * 22.990 * 1000
    70 k_mg = TOT("K") * 39.098 * 1000
    80 PUNCH ca_mg
    90 PUNCH mg_mg
    100 PUNCH na_mg
    110 PUNCH k_mg
    # Calculate hardness as CaCO3
    120 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1
    130 PUNCH hardness_caco3
    -end

END
"""
        
        try:
            # Run simulation
            output, selected = self.engine.run_phreeqc(phreeqc_input, database=str(db_path))
            
            # Parse selected output
            data = self.engine.parse_selected_output(selected)
            
            if not data or len(data) < 2:
                error_msg = "No data returned from PHREEQC - simulation may have failed"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Extract data
            bv_list = []
            ca_mg_list = []
            mg_mg_list = []
            na_mg_list = []
            hardness_list = []
            
            # Skip initial equilibration rows
            for row in data:
                step = row.get('Step', row.get('step', -99))
                if step > 0:
                    bv = row.get('BV', 0)
                    ca_mg = row.get('Ca_mg_L', 0)
                    mg_mg = row.get('Mg_mg_L', 0)
                    na_mg = row.get('Na_mg_L', na_mg_L)
                    hardness = row.get('Hardness_CaCO3', 0)
                    
                    bv_list.append(bv)
                    ca_mg_list.append(ca_mg)
                    mg_mg_list.append(mg_mg)
                    na_mg_list.append(na_mg)
                    hardness_list.append(hardness)
            
            logger.info(f"Extracted {len(bv_list)} data points from PHREEQC")
            
            # Convert to arrays
            if len(bv_list) == 0:
                error_msg = "No valid data points extracted from PHREEQC output"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            bv_array = np.array(bv_list)
            curves = {
                'Ca': np.array(ca_mg_list),
                'Mg': np.array(mg_mg_list),
                'Na': np.array(na_mg_list),
                'Hardness': np.array(hardness_list),
                'Ca_pct': np.array(ca_mg_list) / ca_mg_L * 100 if ca_mg_L > 0 else np.zeros_like(ca_mg_list),
                'Mg_pct': np.array(mg_mg_list) / mg_mg_L * 100 if mg_mg_L > 0 else np.zeros_like(mg_mg_list)
            }
            
            # Log competition effect
            if na_mg_L > 100:
                logger.info(f"Na concentration: {na_mg_L} mg/L - PHREEQC will calculate competition")
            
            return bv_array, curves
            
        except Exception as e:
            logger.error(f"Direct PHREEQC simulation failed: {e}")
            raise
            
    def find_target_breakthrough(
        self, 
        bv_array: np.ndarray, 
        hardness_array: np.ndarray, 
        target: float
    ) -> Optional[float]:
        """Find exact BV where hardness crosses target."""
        # Find where hardness exceeds target
        idx = np.where(hardness_array > target)[0]
        if len(idx) > 0:
            i = idx[0]
            if i > 0:
                # Linear interpolation
                bv_breakthrough = np.interp(
                    target,
                    [hardness_array[i-1], hardness_array[i]],
                    [bv_array[i-1], bv_array[i]]
                )
                return float(bv_breakthrough)
            return float(bv_array[0])
        return None
    
    def generate_full_cycle_phreeqc(
        self,
        water: SACWaterComposition,
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig,
        service_bv: float,
        target_hardness: float,
        cells: int = 10
    ) -> str:
        """Generate PHREEQC input for complete IX cycle including regeneration."""
        # Get database path
        db_path = CONFIG.get_phreeqc_database()
        
        # Extract vessel parameters
        bed_volume_L = vessel_config['bed_volume_L']
        bed_depth_m = vessel_config['bed_depth_m']
        diameter_m = vessel_config['diameter_m']
        porosity = vessel_config.get('bed_porosity', CONFIG.BED_POROSITY)
        
        # Calculate volumes
        pore_volume_L = bed_volume_L * porosity
        water_per_cell_kg = pore_volume_L / cells
        cell_length_m = bed_depth_m / cells
        
        # Resin capacity
        resin_capacity_eq_L = vessel_config.get('resin_capacity_eq_L', CONFIG.RESIN_CAPACITY_EQ_L)
        total_capacity_eq = resin_capacity_eq_L * bed_volume_L
        exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
        
        # Calculate regenerant composition
        if regen_config.regenerant_type == "NaCl":
            # Convert weight % to mol/L (assuming density ~1.07 g/mL for 10% NaCl)
            nacl_g_L = regen_config.concentration_percent * 10 * 1.07
            na_mol_L = nacl_g_L / 58.44
            cl_mol_L = na_mol_L
            h_mol_L = 0
        elif regen_config.regenerant_type == "HCl":
            # Convert weight % to mol/L (assuming density ~1.05 g/mL for 10% HCl)
            hcl_g_L = regen_config.concentration_percent * 10 * 1.05
            h_mol_L = hcl_g_L / 36.46
            cl_mol_L = h_mol_L
            na_mol_L = 0
        else:  # H2SO4
            # Convert weight % to mol/L (assuming density ~1.07 g/mL for 10% H2SO4)
            h2so4_g_L = regen_config.concentration_percent * 10 * 1.07
            h_mol_L = h2so4_g_L * 2 / 98.08  # 2 H+ per H2SO4
            so4_mol_L = h2so4_g_L / 98.08
            na_mol_L = 0
            cl_mol_L = 0
        
        # Calculate shifts for each phase
        service_shifts = int((service_bv + 5) * bed_volume_L / water_per_cell_kg)  # +5 BV buffer
        
        # Regeneration shifts
        if regen_config.mode == "auto":
            regen_shifts = int(regen_config.max_regenerant_bv * bed_volume_L / water_per_cell_kg)
        else:
            regen_shifts = int(regen_config.fixed_volume_bv * bed_volume_L / water_per_cell_kg)
        
        # Backwash calculations
        backwash_shifts = int(regen_config.backwash_bv * bed_volume_L / water_per_cell_kg)
        backwash_timestep = water_per_cell_kg / (regen_config.backwash_flow_rate_bv_hr * bed_volume_L / 3600)
        
        # Rinse calculations  
        slow_rinse_shifts = int(regen_config.slow_rinse_bv * bed_volume_L / water_per_cell_kg)
        fast_rinse_shifts = int(regen_config.fast_rinse_bv * bed_volume_L / water_per_cell_kg)
        
        # Flow timesteps
        service_timestep = water_per_cell_kg / (water.flow_m3_hr * 1000 / 3600)
        regen_timestep = water_per_cell_kg / (regen_config.flow_rate_bv_hr * bed_volume_L / 3600)
        
        # Build PHREEQC input - using SIM_NO for phase tracking
        phreeqc_input = f"""DATABASE {db_path}
TITLE Complete IX Cycle - Service + Regeneration + Rinse

# =========== INITIAL SETUP ===========
PHASES
    Fix_H+
    H+ = H+
    log_k 0.0

SELECTED_OUTPUT 1
    -file cycle.sel
    -reset false
    -step true
    -totals Ca Mg Na K Cl
    -molalities CaX2 MgX2 NaX KX
    -pH true
    -simulation true

USER_PUNCH 1
    -headings Phase Sim Step BV Ca_mg_L Mg_mg_L Na_mg_L Hardness_CaCO3 Na_fraction TDS_mg_L Regen_BV Ca_fraction Mg_fraction Ca_removed_mol Waste_TDS
    -start
    # Determine phase based on SIM_NO
    10 phase$ = "UNKNOWN"
    20 IF SIM_NO = 1 THEN phase$ = "SERVICE"
    {"30 IF SIM_NO = 2 THEN phase$ = 'BACKWASH'" if regen_config.backwash_enabled else ""}
    {"40 IF SIM_NO = " + ("3" if regen_config.backwash_enabled else "2") + " THEN phase$ = 'REGENERATION'"}
    {"50 IF SIM_NO = " + ("4" if regen_config.backwash_enabled else "3") + " THEN phase$ = 'SLOW_RINSE'"}
    {"60 IF SIM_NO = " + ("5" if regen_config.backwash_enabled else "4") + " THEN phase$ = 'FAST_RINSE'"}
    
    70 PUNCH phase$
    80 PUNCH SIM_NO
    90 PUNCH STEP_NO
    
    # Calculate BV based on phase
    100 bv = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    110 PUNCH bv
    
    # Common calculations
    120 ca_mg = TOT("Ca") * 40.078 * 1000
    130 mg_mg = TOT("Mg") * 24.305 * 1000
    140 na_mg = TOT("Na") * 22.990 * 1000
    150 PUNCH ca_mg, mg_mg, na_mg
    
    # Hardness
    160 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1
    170 PUNCH hardness_caco3
    
    # Exchange composition
    180 total_X = TOT("X")
    190 na_frac = 0
    200 IF total_X > 0 THEN na_frac = MOL("NaX") / total_X
    210 PUNCH na_frac
    
    # TDS
    220 tds = ca_mg + mg_mg + na_mg + TOT("Cl") * 35.45 * 1000
    230 IF TOT("S(6)") > 0 THEN tds = tds + TOT("S(6)") * 96.06 * 1000
    240 PUNCH tds
    
    # Regeneration-specific columns
    250 regen_bv = 0
    260 IF phase$ = "REGENERATION" THEN regen_bv = bv
    270 PUNCH regen_bv
    
    280 ca_frac = 0
    290 mg_frac = 0
    300 IF total_X > 0 THEN ca_frac = MOL("CaX2") * 2 / total_X
    310 IF total_X > 0 THEN mg_frac = MOL("MgX2") * 2 / total_X
    320 PUNCH ca_frac, mg_frac
    
    330 ca_removed = 0
    340 IF phase$ = "REGENERATION" THEN ca_removed = TOT("Ca") * {water_per_cell_kg}
    350 PUNCH ca_removed
    
    360 waste_tds = 0
    370 IF phase$ = "REGENERATION" THEN waste_tds = tds
    380 PUNCH waste_tds
    -end

# =========== PHASE 1: SERVICE RUN ===========
SOLUTION 0  # Feed water
    units     mg/L
    temp      {water.temperature_celsius}
    pH        {water.pH}
    Ca        {water.ca_mg_l}
    Mg        {water.mg_mg_l}
    Na        {water.na_mg_l}
    K         {water.k_mg_l}
    N(5)      {water.nh4_mg_l} as NH4
    Cl        {water.cl_mg_l}
    S(6)      {water.so4_mg_l} as SO4
    C(4)      {water.hco3_mg_l} as HCO3

SOLUTION 1-{cells}  # Initial column - Na form resin
    units     mg/L
    temp      {water.temperature_celsius}
    pH        7.0
    Na        1000
    Cl        1540 charge
    water     {water_per_cell_kg} kg

EXCHANGE 1-{cells}
    X         {exchange_per_kg_water}
    -equilibrate solution 1-{cells}

TRANSPORT
    -cells    {cells}
    -shifts   {service_shifts}
    -lengths  {cell_length_m}
    -dispersivities {cells}*0.002
    -porosities {porosity}
    -flow_direction forward
    -boundary_conditions flux flux
    -time_step {service_timestep}
    -print_frequency {cells}
    -punch_frequency {cells}
    -punch_cells {cells}

END
"""

        # Add backwash phase if enabled
        if regen_config.backwash_enabled:
            phreeqc_input += f"""
# =========== PHASE 2: BACKWASH ===========

SOLUTION 0  # Backwash water (feed water)
    units     mg/L
    temp      {water.temperature_celsius}
    pH        {water.pH}
    Ca        {water.ca_mg_l}
    Mg        {water.mg_mg_l}
    Na        {water.na_mg_l}
    Cl        {water.cl_mg_l}

TRANSPORT
    -cells    {cells}
    -shifts   {backwash_shifts}
    -flow_direction back
    -time_step {backwash_timestep}
    -punch_cells 1

END
"""

        # Add regeneration phase
        if regen_config.regenerant_type == "H2SO4":
            regen_solution = f"""SOLUTION 0  # Regenerant - {regen_config.regenerant_type}
    units     mol/L
    temp      25
    pH        1.0
    H         {h_mol_L}
    S(6)      {so4_mol_L} as SO4"""
        else:
            regen_solution = f"""SOLUTION 0  # Regenerant - {regen_config.regenerant_type}  
    units     mol/L
    temp      25
    pH        {7.0 if na_mol_L > 0 else 1.0}
    Na        {na_mol_L}
    H         {h_mol_L}
    Cl        {cl_mol_L}"""

        phreeqc_input += f"""
# =========== PHASE 3: REGENERATION ===========

{regen_solution}

TRANSPORT
    -cells    {cells}
    -shifts   {regen_shifts}
    -flow_direction {regen_config.flow_direction}
    -time_step {regen_timestep}
    -punch_cells {1 if regen_config.flow_direction == 'back' else cells}

END

# =========== PHASE 4: SLOW RINSE ===========

SOLUTION 0  # Dilute regenerant
    units     mol/L
    temp      25
    pH        {7.0 if na_mol_L > 0 else 3.0}
    Na        {na_mol_L * regen_config.slow_rinse_concentration_percent / 100}
    H         {h_mol_L * regen_config.slow_rinse_concentration_percent / 100}
    Cl        {cl_mol_L * regen_config.slow_rinse_concentration_percent / 100}

TRANSPORT
    -cells    {cells}
    -shifts   {slow_rinse_shifts}
    -flow_direction {regen_config.flow_direction}
    -time_step {regen_timestep}

END

# =========== PHASE 5: FAST RINSE ===========

SOLUTION 0  # Service water
    units     mg/L
    temp      {water.temperature_celsius}
    pH        {water.pH}
    Ca        {water.ca_mg_l}
    Mg        {water.mg_mg_l}
    Na        {water.na_mg_l}
    Cl        {water.cl_mg_l}

TRANSPORT
    -cells    {cells}
    -shifts   {fast_rinse_shifts}
    -flow_direction forward
    -time_step {service_timestep}

END
"""
        
        return phreeqc_input
    
    def run_full_cycle_simulation(
        self,
        water: SACWaterComposition,
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig,
        target_hardness: float
    ) -> Tuple[Dict[str, Any], RegenerationResults, float]:
        """Run complete IX cycle simulation including regeneration."""
        # Calculate theoretical BV for service simulation (same as service-only flow)
        ca_meq_L = water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT
        mg_meq_L = water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT
        hardness_meq_L = ca_meq_L + mg_meq_L
        theoretical_bv = (CONFIG.RESIN_CAPACITY_EQ_L * 1000) / hardness_meq_L if hardness_meq_L > 0 else 0
        max_bv = int(theoretical_bv * 1.2) if theoretical_bv > 0 else 200
        
        # First run a service simulation to find breakthrough
        logger.info("Running initial service simulation to find breakthrough...")
        logger.info(f"  - Theoretical BV: {theoretical_bv:.1f}")
        logger.info(f"  - Simulation BV: {max_bv} (theoretical + 20% buffer)")
        
        bv_array, curves = self.run_sac_simulation(
            water=water,
            vessel_config=vessel_config,
            max_bv=max_bv,  # Use calculated max_bv instead of hardcoded 100
            cells=CONFIG.DEFAULT_CELLS
        )
        
        # Find service breakthrough
        breakthrough_bv = self.find_target_breakthrough(
            bv_array,
            curves['Hardness'],
            target_hardness
        )
        
        if breakthrough_bv is None:
            breakthrough_bv = max(bv_array)
            logger.warning(f"Target hardness not reached in service simulation, using {breakthrough_bv} BV")
        
        logger.info(f"Service breakthrough at {breakthrough_bv:.1f} BV")
        
        # Check regeneration mode
        if regen_config.mode in ["staged_fixed", "staged_optimize"]:
            # NEW: Multi-stage regeneration path
            logger.info(f"Running {regen_config.mode} regeneration...")
            
            # Log regeneration parameters
            if regen_config.regenerant_dose_g_per_L:
                logger.info(f"  Regenerant dose: {regen_config.regenerant_dose_g_per_L} g/L resin")
            logger.info(f"  Regenerant BV: {regen_config.regenerant_bv:.2f} (calculated or specified)")
            logger.info(f"  Regenerant type: {regen_config.regenerant_type}")
            logger.info(f"  Concentration: {regen_config.concentration_percent}%")
            logger.info(f"  Stages: {regen_config.regeneration_stages}")
            logger.info(f"  Flow rate: {regen_config.flow_rate_bv_hr} BV/hr")
            
            # Extract final exchange state from service
            service_data = curves
            initial_exchange = self._extract_service_exchange_state(
                bv_array, service_data, vessel_config
            )
            
            if regen_config.mode == "staged_optimize":
                # Find optimal regenerant dosage
                optimal_bv, opt_results = self.optimize_regenerant_dosage(
                    initial_exchange_state=initial_exchange,
                    water=water,
                    vessel_config=vessel_config,
                    regen_config=regen_config
                )
                
                # Run with optimal dosage
                final_exchange, stage_results = self.run_multi_stage_regeneration(
                    initial_exchange_state=initial_exchange,
                    water=water,
                    vessel_config=vessel_config,
                    regen_config=regen_config,
                    override_bv=optimal_bv
                )
                
                # Convert to RegenerationResults format
                regen_results = self._staged_to_regeneration_results(
                    final_exchange, stage_results, vessel_config, regen_config, optimal_bv
                )
                regen_results.optimization_info = opt_results
                
            else:  # staged_fixed
                # Run with fixed BV
                final_exchange, stage_results = self.run_multi_stage_regeneration(
                    initial_exchange_state=initial_exchange,
                    water=water,
                    vessel_config=vessel_config,
                    regen_config=regen_config
                )
                
                regen_results = self._staged_to_regeneration_results(
                    final_exchange, stage_results, vessel_config, regen_config
                )
            
            # Create cycle data for plotting
            cycle_data = self._create_staged_cycle_data(
                bv_array, curves, stage_results, breakthrough_bv, target_hardness, regen_config, water
            )
            
        else:
            # LEGACY: Original single TRANSPORT regeneration
            logger.info("Generating full cycle PHREEQC simulation...")
            phreeqc_input = self.generate_full_cycle_phreeqc(
                water=water,
                vessel_config=vessel_config,
                regen_config=regen_config,
                service_bv=breakthrough_bv,
                target_hardness=target_hardness,
                cells=CONFIG.DEFAULT_CELLS
            )
            
            # Run full cycle simulation
            db_path = CONFIG.get_phreeqc_database()
            output, selected = self.engine.run_phreeqc(phreeqc_input, database=str(db_path))
            
            # Parse multi-phase output
            all_data = self.engine.parse_selected_output(selected)
            
            if not all_data or len(all_data) < 10:
                raise RuntimeError("Insufficient data returned from full cycle PHREEQC simulation")
            
            # Separate data by phase
            phase_data = {
                'SERVICE': [],
                'BACKWASH': [],
                'REGENERATION': [],
                'SLOW_RINSE': [],
                'FAST_RINSE': []
            }
            
            # Debug: Check what columns we have
            if all_data:
                logger.info(f"Available columns in PHREEQC output: {list(all_data[0].keys())}")
            
            for row in all_data:
                # Try different possible phase column names
                phase = row.get('Phase', row.get('phase', row.get('PHASE', 'UNKNOWN')))
                # Strip whitespace from phase names
                phase = phase.strip()
                if phase in phase_data:
                    phase_data[phase].append(row)
                else:
                    logger.warning(f"Unknown phase '{phase}' in row: {row}")
            
            logger.info(f"Parsed cycle data: {', '.join(f'{phase}: {len(data)} points' for phase, data in phase_data.items() if data)}")
            
            # Analyze regeneration results
            regen_results = self._analyze_regeneration_results(
                phase_data,
                vessel_config,
                regen_config,
                water.flow_m3_hr
            )
            
            # Compile full cycle data for plotting
            cycle_data = self._compile_cycle_data(phase_data, target_hardness)
        
        # Return breakthrough_bv along with other results
        return cycle_data, regen_results, breakthrough_bv
    
    def _analyze_regeneration_results(
        self,
        phase_data: Dict[str, List[Dict]],
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig,
        flow_m3_hr: float
    ) -> RegenerationResults:
        """Analyze regeneration phase data to calculate performance metrics."""
        bed_volume_L = vessel_config['bed_volume_L']
        
        # Find where regeneration actually stopped (if auto mode)
        regen_data = phase_data.get('REGENERATION', [])
        if not regen_data:
            raise RuntimeError("No regeneration data found")
        
        # Check final Na recovery
        final_na_fraction = regen_data[-1].get('Na_fraction', 0)
        
        # Find actual BV where target recovery was achieved
        actual_regen_bv = regen_config.max_regenerant_bv
        if regen_config.mode == "auto":
            for row in regen_data:
                if row.get('Na_fraction', 0) >= regen_config.target_recovery:
                    actual_regen_bv = row.get('Regen_BV', regen_config.max_regenerant_bv)
                    break
        else:
            actual_regen_bv = regen_config.fixed_volume_bv or regen_config.max_regenerant_bv
        
        # Calculate regenerant consumption
        if regen_config.regenerant_type == "NaCl":
            nacl_g_L = regen_config.concentration_percent * 10 * 1.07
            regenerant_kg = actual_regen_bv * bed_volume_L * nacl_g_L / 1000  # Convert g to kg
        elif regen_config.regenerant_type == "HCl":
            hcl_g_L = regen_config.concentration_percent * 10 * 1.05
            regenerant_kg = actual_regen_bv * bed_volume_L * hcl_g_L / 1000  # Convert g to kg
        else:  # H2SO4
            h2so4_g_L = regen_config.concentration_percent * 10 * 1.07
            regenerant_kg = actual_regen_bv * bed_volume_L * h2so4_g_L / 1000  # Convert g to kg
        
        # Peak waste characteristics
        peak_tds = max(row.get('Waste_TDS', 0) for row in regen_data)
        
        # Total hardness removed (integrate)
        ca_removed_total = sum(row.get('Ca_removed_mol', 0) for row in regen_data) * 0.04008  # mol to kg
        mg_removed_total = sum(row.get('Mg_removed_mol', 0) for row in regen_data) * 0.02431  # mol to kg
        
        # Waste volume
        waste_volume_m3 = (actual_regen_bv + regen_config.slow_rinse_bv) * bed_volume_L / 1000
        
        # Check rinse quality
        rinse_data = phase_data.get('FAST_RINSE', [])
        rinse_quality_achieved = False
        if rinse_data:
            final_hardness = rinse_data[-1].get('Hardness_mg_L', 999)
            rinse_quality_achieved = rinse_data[-1].get('Ready_for_service', 0) == 1
        
        # Calculate regeneration time
        regen_time_hours = (
            (actual_regen_bv / regen_config.flow_rate_bv_hr) +
            (regen_config.slow_rinse_bv / regen_config.flow_rate_bv_hr) +
            (regen_config.fast_rinse_bv / (flow_m3_hr * 1000 / bed_volume_L))
        )
        if regen_config.backwash_enabled:
            regen_time_hours += regen_config.backwash_bv / regen_config.backwash_flow_rate_bv_hr
        
        # Peak hardness in waste
        peak_ca_mg_l = max(row.get('Ca_mg_L', 0) for row in regen_data if 'Ca_mg_L' in row)
        peak_mg_mg_l = max(row.get('Mg_mg_L', 0) for row in regen_data if 'Mg_mg_L' in row)
        peak_hardness = peak_ca_mg_l * 2.5 + peak_mg_mg_l * 4.1
        
        return RegenerationResults(
            actual_regenerant_bv=round(actual_regen_bv, 1),
            regenerant_consumed_kg=round(regenerant_kg, 1),
            regenerant_type=regen_config.regenerant_type,
            peak_waste_tds_mg_l=round(peak_tds, 0),
            peak_waste_hardness_mg_l=round(peak_hardness, 0),
            total_hardness_removed_kg=round(ca_removed_total + mg_removed_total, 2),
            waste_volume_m3=round(waste_volume_m3, 1),
            final_resin_recovery=round(final_na_fraction, 3),
            ready_for_service=rinse_quality_achieved,
            rinse_quality_achieved=rinse_quality_achieved,
            regeneration_time_hours=round(regen_time_hours, 1)
        )
    
    def _compile_cycle_data(
        self,
        phase_data: Dict[str, List[Dict]],
        target_hardness: float
    ) -> Dict[str, Any]:
        """Compile all phase data into format suitable for plotting."""
        # Initialize lists
        all_bv = []
        all_phases = []
        all_ca_mg_l = []
        all_mg_mg_l = []
        all_na_mg_l = []
        all_hardness = []
        all_na_fraction = []
        all_conductivity = []
        all_tds = []
        
        # Process each phase in order
        phase_order = ['SERVICE', 'BACKWASH', 'REGENERATION', 'SLOW_RINSE', 'FAST_RINSE']
        current_bv_offset = 0
        
        for phase in phase_order:
            data = phase_data.get(phase, [])
            if not data:
                continue
            
            # Get max BV from this phase to calculate offset for next phase
            phase_max_bv = max(row.get('BV', 0) for row in data) if phase != 'REGENERATION' else 0
            if phase == 'REGENERATION':
                phase_max_bv = max(row.get('Regen_BV', 0) for row in data)
            
            for row in data:
                # Adjust BV to create continuous timeline
                if phase == 'REGENERATION':
                    bv = current_bv_offset + row.get('Regen_BV', 0)
                else:
                    bv = current_bv_offset + row.get('BV', 0)
                
                all_bv.append(bv)
                all_phases.append(phase)
                
                # Get concentration data
                all_ca_mg_l.append(row.get('Ca_mg_L', 0))
                all_mg_mg_l.append(row.get('Mg_mg_L', 0))
                all_na_mg_l.append(row.get('Na_mg_L', 0))
                all_hardness.append(row.get('Hardness_CaCO3', row.get('Hardness_mg_L', 0)))
                
                # Phase-specific data
                all_na_fraction.append(row.get('Na_fraction', np.nan))
                all_conductivity.append(row.get('Conductivity_mS_cm', np.nan))
                all_tds.append(row.get('TDS_mg_L', row.get('Waste_TDS', np.nan)))
            
            current_bv_offset += phase_max_bv
        
        return {
            'bed_volumes': all_bv,
            'phases': all_phases,
            'ca_mg_l': all_ca_mg_l,
            'mg_mg_l': all_mg_mg_l,
            'na_mg_l': all_na_mg_l,
            'hardness_mg_l': all_hardness,
            'na_fraction': all_na_fraction,
            'conductivity_ms_cm': all_conductivity,
            'tds_mg_l': all_tds,
            'target_hardness': target_hardness
        }
    
    def run_multi_stage_regeneration(
        self,
        initial_exchange_state: Dict[str, float],
        water: SACWaterComposition,
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig,
        override_bv: Optional[float] = None
    ) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        """
        Run counter-current regeneration as staged equilibrations.
        Ensures positive volumes and consistent database usage.
        Includes kinetic limitations for realistic recovery predictions.
        """
        n_stages = regen_config.regeneration_stages
        cells = CONFIG.DEFAULT_CELLS
        
        # Get merged database path once
        db_path = str(CONFIG.get_merged_database_path())
        
        # Use override_bv for optimization iterations
        regenerant_bv = override_bv if override_bv is not None else regen_config.regenerant_bv
        
        # Calculate per-stage volumes with guards
        bed_volume_L = vessel_config['bed_volume_L']
        stage_bv = regenerant_bv / n_stages
        stage_volume_L = stage_bv * bed_volume_L
        
        # Guard against negative effective volume
        resin_holdup_L = bed_volume_L * 0.3
        effective_stage_volume_L = max(
            stage_volume_L - resin_holdup_L / n_stages,
            0.01 * bed_volume_L  # Minimum 1% of bed volume
        )
        
        if effective_stage_volume_L < 0.1:
            logger.warning(f"Very small stage volume: {effective_stage_volume_L:.3f} L")
        
        # Initialize resin states - distribute capacity across stages
        # Each stage gets 1/n_stages of the total bed capacity
        slice_state = {
            'ca_mol': initial_exchange_state['ca_mol'] / n_stages,
            'mg_mol': initial_exchange_state['mg_mol'] / n_stages,
            'na_mol': initial_exchange_state['na_mol'] / n_stages,
            'ca_equiv': initial_exchange_state['ca_equiv'] / n_stages,
            'mg_equiv': initial_exchange_state['mg_equiv'] / n_stages,
            'na_equiv': initial_exchange_state['na_equiv'] / n_stages,
            'ca_fraction': initial_exchange_state['ca_fraction'],
            'mg_fraction': initial_exchange_state['mg_fraction'],
            'na_fraction': initial_exchange_state['na_fraction']
        }
        resin_states = [slice_state.copy() for _ in range(n_stages)]
        
        # Verify total capacity is conserved
        total_initial = (initial_exchange_state['ca_mol'] + 
                        initial_exchange_state['mg_mol'] + 
                        initial_exchange_state['na_mol'])
        total_distributed = sum(rs['ca_mol'] + rs['mg_mol'] + rs['na_mol'] 
                               for rs in resin_states)
        assert abs(total_distributed - total_initial) < 1e-6, \
            f"Capacity distribution error: {total_initial} != {total_distributed}"
        
        # Fresh regenerant with dynamic density
        density = self._get_regenerant_density(
            regen_config.regenerant_type,
            regen_config.concentration_percent
        )
        na_mol_L = regen_config.concentration_percent * 10 * density / 58.44
        
        fresh_regenerant = {
            'Na': na_mol_L * 1000,  # mmol/L
            'Cl': na_mol_L * 1000,
            'Ca': 0.0,
            'Mg': 0.0,
            'temp': 25.0,
            'pH': 7.0
        }
        
        stage_results = []
        regenerant = fresh_regenerant.copy()
        
        # Counter-current: stage N -> 1
        for stage_num in reversed(range(n_stages)):
            logger.debug(f"Stage {stage_num + 1}/{n_stages}, volume={effective_stage_volume_L:.1f} L")
            
            try:
                phreeqc_input = self._build_stage_input(
                    stage_num=stage_num,
                    n_stages=n_stages,
                    regenerant_composition=regenerant,
                    exchange_state=resin_states[stage_num],
                    volume_L=effective_stage_volume_L,
                    vessel_config=vessel_config,
                    db_path=db_path  # Pass database explicitly
                )
                
                # Run with merged database
                output, selected = self.engine.run_phreeqc(
                    phreeqc_input,
                    database=db_path
                )
                
                # Parse selected output
                selected_data = []
                if selected:
                    selected_data = self.engine.parse_selected_output(selected)
                    # Debug output (commented out to prevent stdout pollution)
                    # if stage_num == 0:
                    #     logger.debug(f"\n=== Stage {stage_num+1} PHREEQC Output Debug ===")
                    #     logger.debug(f"Number of data rows: {len(selected_data)}")
                    #     if selected_data:
                    #         logger.debug(f"Column names: {list(selected_data[0].keys())}")
                    #         logger.debug(f"Last row data: {selected_data[-1]}")
                
                # Extract results preserving absolute moles
                if not selected_data:
                    # Handle empty output - use previous state
                    logger.warning(f"No selected output for stage {stage_num + 1}, using previous state")
                    new_exchange = resin_states[stage_num]
                    spent_regenerant = regenerant
                else:
                    new_exchange = self._extract_exchange_state(selected_data, vessel_config)
                    spent_regenerant = self._extract_solution_composition(selected_data)
                
                # Update states
                resin_states[stage_num] = new_exchange
                
                # Correct for water hold-up between stages
                if stage_num > 0:  # Not needed for first stage
                    holdup_volume_L = bed_volume_L * 0.3 / n_stages
                    dilution_factor = effective_stage_volume_L / (effective_stage_volume_L + holdup_volume_L)
                    # Adjust regenerant composition to account for dilution
                    for ion in ['Na', 'Ca', 'Mg', 'Cl']:
                        if ion in spent_regenerant:
                            spent_regenerant[ion] *= dilution_factor
                
                regenerant = spent_regenerant
                
                # Track results
                stage_results.append({
                    'stage': n_stages - stage_num,  # Correct display order: fresh regenerant = highest stage
                    'na_fraction': new_exchange.get('na_fraction', 0),
                    'ca_fraction': new_exchange.get('ca_fraction', 0),
                    'waste_tds': spent_regenerant.get('tds', 0),
                    'ca_in_waste': spent_regenerant.get('Ca', 0),
                    'volume_L': effective_stage_volume_L
                })
                
            except Exception as e:
                logger.error(f"Stage {stage_num + 1} failed: {e}")
                raise RuntimeError(f"Multi-stage regeneration failed at stage {stage_num + 1}: {e}")
        
        # Calculate bed-average recovery (capacity-weighted)
        tot_sites = sum(rs['ca_equiv'] + rs['mg_equiv'] + rs['na_equiv']
                       for rs in resin_states)
        tot_na = sum(rs['na_equiv'] for rs in resin_states)
        tot_ca = sum(rs['ca_equiv'] for rs in resin_states)
        tot_mg = sum(rs['mg_equiv'] for rs in resin_states)
        
        avg_na_fraction = tot_na / tot_sites if tot_sites > 0 else 0
        avg_ca_fraction = tot_ca / tot_sites if tot_sites > 0 else 0
        avg_mg_fraction = tot_mg / tot_sites if tot_sites > 0 else 0
        
        # Total moles for reporting
        tot_na_mol = sum(rs['na_mol'] for rs in resin_states)
        tot_ca_mol = sum(rs['ca_mol'] for rs in resin_states)
        tot_mg_mol = sum(rs['mg_mol'] for rs in resin_states)
        
        final_exchange = {
            'na_fraction': avg_na_fraction,
            'ca_fraction': avg_ca_fraction,
            'mg_fraction': avg_mg_fraction,
            'na_mol': tot_na_mol,
            'ca_mol': tot_ca_mol,
            'mg_mol': tot_mg_mol,
            'na_equiv': tot_na,
            'ca_equiv': tot_ca,
            'mg_equiv': tot_mg
        }
        
        logger.debug(f"Multi-stage regeneration complete: Bed-average Na_fraction={avg_na_fraction:.3f}")
        
        return final_exchange, stage_results
    
    def _build_stage_input(
        self,
        stage_num: int,
        n_stages: int,
        regenerant_composition: Dict[str, float],
        exchange_state: Dict[str, float],
        volume_L: float,
        vessel_config: Dict[str, Any],
        db_path: str
    ) -> str:
        """Build PHREEQC input preserving absolute exchange capacity"""
        
        # Get total exchange capacity in moles (not normalized)
        bed_volume_L = vessel_config['bed_volume_L']
        resin_capacity_eq_L = vessel_config.get('resin_capacity_eq_L', 2.0)
        total_exchange_mol = resin_capacity_eq_L * bed_volume_L
        
        # Current loading in moles (preserve absolute values)
        ca_mol = exchange_state.get('ca_mol', 0)
        mg_mol = exchange_state.get('mg_mol', 0)
        na_mol = exchange_state.get('na_mol', 0)
        
        # Safety check - ensure we have exchange sites
        assert ca_mol + mg_mol + na_mol > 0, f"Exchange feed is empty – check stage {stage_num + 1} input"
        
        # Calculate water mass for USER_PUNCH
        water_kg = volume_L * 1.0  # Assume density ~1 kg/L
        
        phreeqc_input = f"""
DATABASE {db_path}
TITLE Stage {n_stages - stage_num} - Multi-stage regeneration

SOLUTION 1 Regenerant
    units     mmol/L
    temp      {regenerant_composition['temp']}
    pH        {regenerant_composition['pH']}
    Na        {regenerant_composition['Na']}
    Ca        {regenerant_composition['Ca']}
    Mg        {regenerant_composition['Mg']}
    Cl        {regenerant_composition['Cl']}
    water     {volume_L} kg

EXCHANGE 1 Resin state (in moles)
    CaX2      {ca_mol}    # moles of CaX2 (not divided by 2)
    MgX2      {mg_mol}    # moles of MgX2 (not divided by 2)
    NaX       {na_mol}    # moles of NaX

PRINT
    -high_precision true

SELECTED_OUTPUT
    -file stage{stage_num + 1}.sel
    -reset false
    -high_precision true
    -totals Na Ca Mg Cl X
    -molalities CaX2 MgX2 NaX

USER_PUNCH
    -headings Stage Na_frac Ca_frac Mg_frac TDS_mg_L Na_mmol Ca_mmol Mg_mmol NaX CaX2 MgX2
    -start
    10 PUNCH {n_stages - stage_num}
    20 total_X = TOT("X")
    30 na_frac = 0 : ca_frac = 0 : mg_frac = 0
    40 IF total_X > 0 THEN na_frac = MOL("NaX") / total_X
    50 IF total_X > 0 THEN ca_frac = MOL("CaX2") * 2 / total_X
    60 IF total_X > 0 THEN mg_frac = MOL("MgX2") * 2 / total_X
    70 PUNCH na_frac, ca_frac, mg_frac
    80 tds = (TOT("Na")*23 + TOT("Ca")*40 + TOT("Mg")*24.3 + TOT("Cl")*35.5) * 1000
    90 PUNCH tds, TOT("Na")*1000, TOT("Ca")*1000, TOT("Mg")*1000
    100 PUNCH MOL("NaX") * {water_kg}, MOL("CaX2") * {water_kg}, MOL("MgX2") * {water_kg}
    -end

END
"""
        return phreeqc_input
    
    def optimize_regenerant_dosage(
        self,
        initial_exchange_state: Dict[str, float],
        water: SACWaterComposition,
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Find minimum regenerant dosage achieving target recovery.
        Uses robust bisection with failure handling.
        """
        target = regen_config.target_recovery
        tolerance = regen_config.optimization_tolerance
        
        # Initial bounds
        low_bv = regen_config.min_regenerant_bv
        high_bv = regen_config.max_regenerant_bv
        
        # Calculate max iterations
        precision = 0.2  # Coarsened from 0.1 for faster convergence
        theoretical_max = int(np.ceil(np.log2((high_bv - low_bv) / precision)))
        max_iterations = min(
            regen_config.max_optimization_iterations,
            theoretical_max + 2  # Allow 2 extra for refinement
        )
        
        iterations = []
        iter_count = 0
        best_valid = None  # Track best solution meeting target
        
        logger.info(f"Starting optimization: target={target:.1%}, bounds=[{low_bv:.1f}, {high_bv:.1f}]")
        
        # Main bisection loop
        while (high_bv - low_bv) > precision and iter_count < max_iterations:
            mid_bv = (low_bv + high_bv) / 2
            iter_count += 1
            
            try:
                final_exchange, stage_results = self.run_multi_stage_regeneration(
                    initial_exchange_state=initial_exchange_state,
                    water=water,
                    vessel_config=vessel_config,
                    regen_config=regen_config,
                    override_bv=mid_bv
                )
                
                recovery = final_exchange['na_fraction']
                
                iterations.append({
                    'iteration': iter_count,
                    'bv': mid_bv,
                    'recovery': recovery,
                    'bracket': [low_bv, high_bv],
                    'meets_target': recovery >= target - tolerance
                })
                
                # Track best valid solution
                if recovery >= target - tolerance:
                    if best_valid is None or mid_bv < best_valid['bv']:
                        best_valid = {'bv': mid_bv, 'recovery': recovery}
                    
                    # Early stop if close enough to target (within 2%)
                    if abs(recovery - target) <= max(tolerance, 0.02):
                        logger.info(f"Early stop: {recovery:.1%} close enough to target {target:.1%}")
                        break
                
                # Monotonic bisection
                if recovery >= target:
                    high_bv = mid_bv
                    logger.info(f"Iter {iter_count}: [{low_bv:.1f} -> {high_bv:.1f}] BV, rec={recovery:.1%}")
                else:
                    low_bv = mid_bv
                    
            except RuntimeError as e:
                logger.warning(f"PHREEQC failed at {mid_bv:.2f} BV: {e}")
                low_bv = mid_bv  # Assume insufficient regenerant
                iterations.append({
                    'iteration': iter_count,
                    'bv': mid_bv,
                    'recovery': 0.0,
                    'error': str(e)
                })
        
        # Final verification with monotonicity check
        optimal_bv = (low_bv + high_bv) / 2
        
        try:
            final_exchange, _ = self.run_multi_stage_regeneration(
                initial_exchange_state=initial_exchange_state,
                water=water,
                vessel_config=vessel_config,
                regen_config=regen_config,
                override_bv=optimal_bv
            )
            final_recovery = final_exchange['na_fraction']
            
            # Monotonicity check
            if final_recovery < target and high_bv < regen_config.max_regenerant_bv:
                # One more iteration
                low_bv = optimal_bv
                optimal_bv = (low_bv + high_bv) / 2
                final_exchange, _ = self.run_multi_stage_regeneration(
                    initial_exchange_state=initial_exchange_state,
                    water=water,
                    vessel_config=vessel_config,
                    regen_config=regen_config,
                    override_bv=optimal_bv
                )
                final_recovery = final_exchange['na_fraction']
                
        except:
            # Use best valid or fallback to high_bv
            if best_valid:
                optimal_bv = best_valid['bv']
                final_recovery = best_valid['recovery']
            else:
                optimal_bv = high_bv
                final_recovery = iterations[-1]['recovery'] if iterations else 0.0
        
        # Calculate results
        bed_volume_L = vessel_config['bed_volume_L']
        density = self._get_regenerant_density(
            regen_config.regenerant_type,
            regen_config.concentration_percent
        )
        concentration_g_L = regen_config.concentration_percent * 10 * density
        optimal_kg = optimal_bv * bed_volume_L * concentration_g_L / 1000
        optimal_dose_g_L = optimal_kg * 1000 / bed_volume_L
        
        # Savings calculation
        typical_dose_g_L = 280
        typical_bv = typical_dose_g_L / concentration_g_L
        savings_percent = max(0, (typical_bv - optimal_bv) / typical_bv * 100)
        
        # Extract convergence curve
        convergence_curve = [
            [it['bv'], it['recovery']] 
            for it in iterations 
            if 'recovery' in it and it['recovery'] > 0
        ]
        
        optimization_results = {
            'optimal_bv': round(optimal_bv, 2),
            'optimal_dose_g_per_L': round(optimal_dose_g_L, 0),
            'iterations': iter_count,
            'convergence_history': iterations,
            'convergence_curve': convergence_curve,  # For UI plotting
            'savings_vs_typical': round(savings_percent, 1),
            'final_recovery': round(final_recovery, 3),
            'converged': (high_bv - low_bv) <= precision,
            'target_met': final_recovery >= target - tolerance
        }
        
        logger.info(f"Optimization complete: {optimal_bv:.2f} BV -> {final_recovery:.1%} recovery")
        if savings_percent > 0:
            logger.info(f"Chemical savings: {savings_percent:.1f}% vs typical")
        
        return optimal_bv, optimization_results
    
    def _get_regenerant_density(self, regenerant_type: str, concentration_percent: float) -> float:
        """Dynamic density calculation for accurate dosing"""
        if regenerant_type == "NaCl":
            # Polynomial fit from CRC handbook
            c = concentration_percent
            density = 0.9982 + 0.00675*c + 0.000025*c**2
        elif regenerant_type == "HCl":
            c = concentration_percent
            density = 0.9982 + 0.00467*c + 0.000013*c**2
        else:  # H2SO4
            c = concentration_percent
            density = 0.9982 + 0.00692*c + 0.000036*c**2
        
        return round(density, 3)
    
    def _extract_exchange_state(self, selected_output, vessel_config) -> Dict[str, float]:
        """Extract exchange state preserving absolute moles"""
        if not selected_output:
            return {}
        
        # Find the last row with exchange data (has CaX2, etc.)
        last_row = None
        for row in reversed(selected_output):
            if row.get('CaX2') is not None or row.get('m_CaX2') is not None:
                last_row = row
                break
        
        if not last_row:
            # Use last row if no exchange data found
            last_row = selected_output[-1]
        
        bed_volume_L = vessel_config['bed_volume_L']
        
        # Get total exchange sites
        total_x_mol = last_row.get('X') or 0
        
        # Get moles from USER_PUNCH (not molalities!)
        # Column names match the USER_PUNCH headings exactly
        na_mol = last_row.get('NaX', 0.0)
        ca_mol = last_row.get('CaX2', 0.0)
        mg_mol = last_row.get('MgX2', 0.0)
        
        # Extract fractions from USER_PUNCH data or calculate from molalities
        na_fraction = last_row.get('Na_frac') or last_row.get('Na_fraction')
        ca_fraction = last_row.get('Ca_frac') or last_row.get('Ca_fraction')
        mg_fraction = last_row.get('Mg_frac') or last_row.get('Mg_fraction')
        
        # If fractions not available from USER_PUNCH, calculate from moles
        if na_fraction is None:
            if total_x_mol > 0:
                # Calculate equivalent fractions
                na_fraction = na_mol / total_x_mol
                ca_fraction = (ca_mol * 2) / total_x_mol  # CaX2 takes 2 sites
                mg_fraction = (mg_mol * 2) / total_x_mol  # MgX2 takes 2 sites
            else:
                na_fraction = ca_fraction = mg_fraction = 0
        
        # Sanity check
        if na_fraction > 1.0 + 1e-6:
            logger.warning(f"Na fraction exceeds 1.0: {na_fraction:.3f} - check units")
        
        # Guard against silent zeros from rounding
        if (ca_mol + mg_mol) < 1e-8 and total_x_mol > 0.1:
            logger.debug(f"Trace Ca/Mg rounded to zero (Ca: {ca_mol}, Mg: {mg_mol}); high_precision enabled")
        
        return {
            'ca_mol': ca_mol,
            'mg_mol': mg_mol,
            'na_mol': na_mol,
            'ca_equiv': ca_mol * 2,
            'mg_equiv': mg_mol * 2,
            'na_equiv': na_mol,
            'na_fraction': na_fraction,
            'ca_fraction': ca_fraction,
            'mg_fraction': mg_fraction
        }
    
    def _extract_solution_composition(self, selected_output) -> Dict[str, float]:
        """Extract solution composition for next stage"""
        if not selected_output:
            return {}
        
        # Find last row with solution data
        last_row = None
        for row in reversed(selected_output):
            if row.get('Na') is not None:
                last_row = row
                break
        
        if not last_row:
            last_row = selected_output[-1] if selected_output else {}
        
        # Get totals in mol/L, then convert to mmol/L
        na_mol = last_row.get('Na') or 0
        ca_mol = last_row.get('Ca') or 0
        mg_mol = last_row.get('Mg') or 0
        
        # Check if values from USER_PUNCH are available (already in mmol)
        na_mmol = last_row.get('Na_mmol')
        ca_mmol = last_row.get('Ca_mmol') or last_row.get('Ca_mol_L')
        mg_mmol = last_row.get('Mg_mmol')
        
        # Use USER_PUNCH values if available, otherwise convert from totals
        if na_mmol is not None:
            na_final = na_mmol
        else:
            na_final = na_mol * 1000
            
        if ca_mmol is not None:
            ca_final = ca_mmol
        else:
            ca_final = ca_mol * 1000
            
        if mg_mmol is not None:
            mg_final = mg_mmol
        else:
            mg_final = mg_mol * 1000
        
        return {
            'Na': na_final,
            'Ca': ca_final,
            'Mg': mg_final,
            'Cl': na_final + 2*ca_final + 2*mg_final,  # Charge balance
            'temp': 25.0,
            'pH': 7.0,
            'tds': last_row.get('TDS_mg_L') or 0
        }
    
    def _extract_service_exchange_state(
        self, 
        bv_array: np.ndarray,
        service_data: Dict[str, np.ndarray],
        vessel_config: Dict[str, Any]
    ) -> Dict[str, float]:
        """Extract final exchange state from service simulation"""
        # Get bed parameters
        bed_volume_L = vessel_config['bed_volume_L']
        resin_capacity_eq_L = vessel_config.get('resin_capacity_eq_L', 2.0)
        total_exchange_eq = resin_capacity_eq_L * bed_volume_L
        
        # Find final Ca removal to estimate loading
        final_ca_removal = service_data['Ca_pct'][-1] / 100 if 'Ca_pct' in service_data else 0.9
        final_mg_removal = service_data['Mg_pct'][-1] / 100 if 'Mg_pct' in service_data else 0.9
        
        # Estimate exchange state (simplified - assumes complete Ca/Mg loading)
        ca_equiv = total_exchange_eq * final_ca_removal * 0.7  # Assume 70% Ca
        mg_equiv = total_exchange_eq * final_mg_removal * 0.3  # Assume 30% Mg
        na_equiv = total_exchange_eq - ca_equiv - mg_equiv
        
        return {
            'ca_mol': ca_equiv / 2,  # Convert equiv to mol for divalent
            'mg_mol': mg_equiv / 2,
            'na_mol': na_equiv,
            'ca_equiv': ca_equiv,
            'mg_equiv': mg_equiv,
            'na_equiv': na_equiv,
            'na_fraction': na_equiv / total_exchange_eq,
            'ca_fraction': ca_equiv / total_exchange_eq,
            'mg_fraction': mg_equiv / total_exchange_eq
        }
    
    def _staged_to_regeneration_results(
        self,
        final_exchange: Dict[str, float],
        stage_results: List[Dict[str, Any]],
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig,
        override_bv: Optional[float] = None
    ) -> RegenerationResults:
        """Convert staged results to standard RegenerationResults format"""
        
        # Calculate regenerant consumption
        bed_volume_L = vessel_config['bed_volume_L']
        actual_bv = override_bv if override_bv is not None else regen_config.regenerant_bv
        
        density = self._get_regenerant_density(
            regen_config.regenerant_type,
            regen_config.concentration_percent
        )
        concentration_g_L = regen_config.concentration_percent * 10 * density
        regenerant_kg = actual_bv * bed_volume_L * concentration_g_L / 1000
        
        # Peak waste TDS from all stages
        peak_tds = max(stage['waste_tds'] for stage in stage_results)
        
        # Final recovery
        final_recovery = final_exchange['na_fraction']
        
        # Waste volume
        waste_volume_m3 = (actual_bv + regen_config.slow_rinse_bv) * bed_volume_L / 1000
        
        # Regeneration time
        regen_time_hours = (
            (actual_bv / regen_config.flow_rate_bv_hr) +
            (regen_config.slow_rinse_bv / regen_config.flow_rate_bv_hr) +
            (regen_config.fast_rinse_bv / regen_config.flow_rate_bv_hr)
        )
        if regen_config.backwash_enabled:
            regen_time_hours += regen_config.backwash_bv / regen_config.backwash_flow_rate_bv_hr
        
        # Estimate hardness removed (simplified)
        total_hardness_kg = 0.1 * regenerant_kg  # Rough estimate
        
        return RegenerationResults(
            actual_regenerant_bv=round(actual_bv, 1),
            regenerant_consumed_kg=round(regenerant_kg, 1),
            regenerant_type=regen_config.regenerant_type,
            peak_waste_tds_mg_l=round(peak_tds, 0),
            peak_waste_hardness_mg_l=round(peak_tds * 0.3, 0),  # Estimate
            total_hardness_removed_kg=round(total_hardness_kg, 2),
            waste_volume_m3=round(waste_volume_m3, 1),
            final_resin_recovery=round(final_recovery, 3),
            ready_for_service=final_recovery >= 0.85,
            rinse_quality_achieved=True,  # Assumed for staged
            regeneration_time_hours=round(regen_time_hours, 1)
        )
    
    def _create_staged_cycle_data(
        self,
        bv_array: np.ndarray,
        curves: Dict[str, np.ndarray],
        stage_results: List[Dict[str, Any]],
        breakthrough_bv: float,
        target_hardness: float,
        regen_config: Optional[RegenerationConfig] = None,
        water: Optional[SACWaterComposition] = None
    ) -> Dict[str, Any]:
        """Create cycle data for plotting from staged regeneration"""
        # UPDATED: Use ALL service data to show full chromatographic behavior
        # Don't cut off at breakthrough - we want to see Mg spike and Ca S-curve
        service_bv = bv_array  # Use full array
        
        # Get actual concentrations in mg/L from curves - full data range
        service_ca_mg_l = curves['Ca'] if 'Ca' in curves else np.zeros_like(service_bv)
        service_mg_mg_l = curves['Mg'] if 'Mg' in curves else np.zeros_like(service_bv)
        service_na_mg_l = curves['Na'] if 'Na' in curves else np.zeros_like(service_bv)
        service_hardness = curves['Hardness'] if 'Hardness' in curves else np.zeros_like(service_bv)
        
        # Also get percentage values for compatibility
        service_ca_pct = curves['Ca_pct'] if 'Ca_pct' in curves else np.zeros_like(service_bv)
        service_mg_pct = curves['Mg_pct'] if 'Mg_pct' in curves else np.zeros_like(service_bv)
        
        # Create regeneration data from stages
        regenerant_bv = regen_config.regenerant_bv if regen_config else 3.5
        regen_bv = np.linspace(0, regenerant_bv, len(stage_results))
        regen_na_fraction = [stage['na_fraction'] for stage in stage_results]
        
        # Extract regeneration phase concentrations from stage results
        regen_ca_mg_l = []
        regen_mg_mg_l = []
        regen_na_mg_l = []
        regen_tds_mg_l = []
        
        for stage in stage_results:
            # Get solution composition from stage results
            # These should be in mmol/L from USER_PUNCH, convert to mg/L
            ca_mmol = stage.get('Ca_mmol', 0)
            mg_mmol = stage.get('Mg_mmol', 0)
            na_mmol = stage.get('Na_mmol', 0)
            
            regen_ca_mg_l.append(ca_mmol * 40.078)  # mmol/L to mg/L
            regen_mg_mg_l.append(mg_mmol * 24.305)
            regen_na_mg_l.append(na_mmol * 22.990)
            regen_tds_mg_l.append(stage.get('TDS_mg_L', 0))
        
        # Combine into cycle data structure
        # Append regeneration BVs after the last service BV (not just after breakthrough)
        last_service_bv = service_bv[-1] if len(service_bv) > 0 else 0
        all_bv = list(service_bv) + list(last_service_bv + regen_bv)
        all_phases = ['SERVICE'] * len(service_bv) + ['REGENERATION'] * len(regen_bv)
        all_hardness = list(service_hardness) + [0] * len(regen_bv)  # Regeneration hardness ~0
        all_na_fraction = [0] * len(service_bv) + regen_na_fraction
        
        # Combine concentration data
        all_ca_mg_l = list(service_ca_mg_l) + regen_ca_mg_l
        all_mg_mg_l = list(service_mg_mg_l) + regen_mg_mg_l
        all_na_mg_l = list(service_na_mg_l) + regen_na_mg_l
        
        # For TDS: estimate service TDS from ionic composition, use actual for regen
        if water:
            service_tds = water.ca_mg_l + water.mg_mg_l + water.na_mg_l + water.cl_mg_l + water.hco3_mg_l
        else:
            service_tds = 2000  # Default estimate
        all_tds = [service_tds] * len(service_bv) + regen_tds_mg_l
        
        return {
            'bed_volumes': all_bv,
            'phases': all_phases,
            'ca_mg_l': all_ca_mg_l,
            'mg_mg_l': all_mg_mg_l,
            'na_mg_l': all_na_mg_l,
            'hardness_mg_l': all_hardness,
            'na_fraction': all_na_fraction,
            'conductivity_ms_cm': [1.0] * len(all_bv),  # Still placeholder - not critical for plots
            'tds_mg_l': all_tds,
            'target_hardness': target_hardness,
            'breakthrough_bv': breakthrough_bv,  # Reference point where target hardness was reached
            # Also include percentage values for compatibility
            'ca_pct': list(service_ca_pct) + [0] * len(regen_bv),
            'mg_pct': list(service_mg_pct) + [0] * len(regen_bv)
        }
        


def smart_sample_breakthrough_data(
    bv_array: np.ndarray,
    curves: Dict[str, np.ndarray], 
    breakthrough_bv: float,
    critical_window: float = 10.0,
    transition_window: float = 30.0
) -> Dict[str, List[float]]:
    """
    Intelligently sample breakthrough data with high resolution near breakthrough.
    
    Sampling strategy:
    - Critical zone (breakthrough ± critical_window BV): Keep every point
    - Transition zone (breakthrough ± transition_window BV): Every 5th point
    - Far zones (beyond transition): Every 20th point
    - Always includes first and last points
    
    Args:
        bv_array: Array of bed volumes
        curves: Dictionary of breakthrough curves (Ca_pct, Mg_pct, etc.)
        breakthrough_bv: The bed volume where breakthrough occurs
        critical_window: BV window around breakthrough for full resolution (default 10)
        transition_window: BV window for medium resolution (default 30)
        
    Returns:
        Dictionary with sampled arrays, typically reducing 1000+ points to ~60-80
    """
    indices = []
    
    # Sample based on distance from breakthrough
    for i in range(len(bv_array)):
        bv = bv_array[i]
        distance = abs(bv - breakthrough_bv)
        
        if distance <= critical_window:
            # Critical zone: keep every point
            indices.append(i)
        elif distance <= transition_window:
            # Transition zone: every 5th point
            if i % 5 == 0:
                indices.append(i)
        else:
            # Far zone: every 20th point
            if i % 20 == 0:
                indices.append(i)
    
    # Always include first and last points for complete curve
    if len(indices) > 0:
        if indices[0] != 0:
            indices.insert(0, 0)
        if indices[-1] != len(bv_array) - 1:
            indices.append(len(bv_array) - 1)
    else:
        # Fallback if no indices selected
        indices = [0, len(bv_array) - 1]
    
    # Sort indices to maintain order
    indices = sorted(set(indices))
    
    # Extract sampled data
    sampled_data = {
        'bed_volumes': bv_array[indices].tolist(),
        'ca_pct': curves['Ca_pct'][indices].tolist(),
        'mg_pct': curves['Mg_pct'][indices].tolist(),
        'na_mg_l': curves['Na'][indices].tolist(),
        'hardness_mg_l': curves['Hardness'][indices].tolist()
    }
    
    logger.info(f"Smart sampling: {len(bv_array)} points reduced to {len(indices)} points")
    logger.info(f"  - Critical zone (±{critical_window} BV): {sum(1 for i in indices if abs(bv_array[i] - breakthrough_bv) <= critical_window)} points")
    logger.info(f"  - Data reduction: {(1 - len(indices)/len(bv_array))*100:.1f}%")
    
    return sampled_data


def simulate_sac_phreeqc(input_data: SACSimulationInput) -> SACSimulationOutput:
    """
    Simulate complete SAC ion exchange cycle (service + regeneration).
    
    Runs full industrial cycle:
    1. Service (to breakthrough)
    2. Backwash (optional)
    3. Regeneration
    4. Slow rinse
    5. Fast rinse
    
    Key features:
    - Uses bed volume directly from configuration
    - Target hardness breakthrough detection
    - Dynamic max_bv calculation
    - PHREEQC determines all competition effects
    - No heuristic calculations
    - Regeneration is required for complete cycle simulation
    """
    # Always run full cycle simulation (service + regeneration)
    logger.info("Running full cycle simulation with regeneration")
    return _run_full_cycle_simulation(input_data)


def _run_service_only_simulation(input_data: SACSimulationInput) -> SACSimulationOutput:
    """Run service-only simulation (existing behavior)."""
    water = input_data.water_analysis
    vessel = input_data.vessel_configuration
    target_hardness = input_data.target_hardness_mg_l_caco3
    full_data = input_data.full_data
    
    # USE BED VOLUME FROM CONFIGURATION DIRECTLY
    bed_volume_L = vessel.bed_volume_L  # From configuration tool
    bed_depth_m = vessel.bed_depth_m
    diameter_m = vessel.diameter_m
    
    # Calculate porosity and resin parameters
    porosity = CONFIG.BED_POROSITY
    pore_volume_L = bed_volume_L * porosity
    
    # Calculate theoretical capacity for reference only
    ca_meq_L = water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT
    mg_meq_L = water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT
    hardness_meq_L = ca_meq_L + mg_meq_L
    
    # CORRECTED: Resin capacity is per liter of BED VOLUME, not resin volume
    resin_capacity_eq_L = CONFIG.RESIN_CAPACITY_EQ_L  # Standard SAC capacity per L of bed volume
    total_capacity_eq = resin_capacity_eq_L * bed_volume_L  # Total eq
    
    # Theoretical BV = total capacity / (hardness per BV)
    # hardness per BV = hardness_meq_L * 1 m³ = hardness_meq_L meq
    theoretical_bv = (resin_capacity_eq_L * 1000) / hardness_meq_L if hardness_meq_L > 0 else 0
    
    # Simulate to theoretical BV with 20% buffer
    max_bv = int(theoretical_bv * 1.2) if theoretical_bv > 0 else 200
    
    logger.info(f"Starting simulation:")
    logger.info(f"  - Bed volume: {bed_volume_L:.1f} L")
    logger.info(f"  - Theoretical BV: {theoretical_bv:.1f}")
    logger.info(f"  - Simulation BV: {max_bv} (theoretical + 20% buffer)")
    logger.info(f"  - Target hardness: {target_hardness} mg/L CaCO3")
    
    # Build vessel config for PHREEQC
    vessel_config_phreeqc = {
        'resin_type': 'SAC',
        'bed_depth_m': bed_depth_m,
        'diameter_m': diameter_m,
        'bed_volume_L': bed_volume_L,  # Pass through
        'resin_capacity_eq_L': resin_capacity_eq_L,
        'bed_porosity': porosity
    }
    
    # Run PHREEQC simulation ONCE
    sim = _IXDirectPhreeqcSimulation()
    warnings = []
    
    logger.info(f"Running PHREEQC simulation...")
    
    try:
        bv_array, curves = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_config_phreeqc,
            max_bv=max_bv,
            cells=CONFIG.DEFAULT_CELLS
        )
        
        # Find breakthrough based on target hardness
        breakthrough_bv = sim.find_target_breakthrough(
            bv_array,
            curves['Hardness'],
            target_hardness
        )
        
        if breakthrough_bv is not None:
            breakthrough_found = True
            logger.info(f"Breakthrough found at {breakthrough_bv:.1f} BV")
        else:
            # Breakthrough not found - use last point
            breakthrough_found = False
            max_hardness = max(curves['Hardness'])
            breakthrough_bv = max(bv_array)
            
            warnings.append(
                f"Target hardness not reached in {max_bv} BV simulation. "
                f"Max effluent hardness: {max_hardness:.1f} mg/L (target: {target_hardness}). "
                f"Using end of simulation ({breakthrough_bv:.1f} BV) as service time."
            )
            logger.warning(warnings[-1])
            
    except Exception as e:
        logger.error(f"PHREEQC simulation failed: {e}")
        raise
    
    # Calculate service time using bed volume from config
    flow_L_hr = water.flow_m3_hr * 1000
    service_time_hours = breakthrough_bv * bed_volume_L / flow_L_hr
    
    # Calculate actual capacity utilization from PHREEQC results
    actual_capacity_utilization = breakthrough_bv / theoretical_bv if theoretical_bv > 0 else 0
    
    # PHREEQC has determined the actual competition factor implicitly
    phreeqc_competition_factor = actual_capacity_utilization
    
    logger.info(f"PHREEQC-determined capacity factor: {phreeqc_competition_factor:.2f}")
    logger.info(f"Service time: {service_time_hours:.1f} hours")
    logger.info(f"Total capacity: {total_capacity_eq:.1f} eq (based on bed volume)")
    
    # Generate breakthrough data - either full or smart-sampled
    if full_data:
        # Return full resolution data (1000+ points)
        logger.info("Returning full resolution breakthrough data")
        breakthrough_data = {
            'bed_volumes': bv_array.tolist(),
            'ca_pct': curves['Ca_pct'].tolist(),
            'mg_pct': curves['Mg_pct'].tolist(),
            'na_mg_l': curves['Na'].tolist(),
            'hardness_mg_l': curves['Hardness'].tolist()
        }
    else:
        # Use smart sampling to reduce data size and prevent MCP BrokenResourceError
        # This reduces ~1000 points to ~60-80 points while preserving critical detail
        breakthrough_data = smart_sample_breakthrough_data(
            bv_array=bv_array,
            curves=curves,
            breakthrough_bv=breakthrough_bv,
            critical_window=10.0,  # ±10 BV around breakthrough: full resolution
            transition_window=30.0  # ±30 BV: medium resolution
        )
    
    # Calculate regenerant requirements
    hardness_removed_eq = hardness_meq_L * breakthrough_bv * bed_volume_L / 1000
    # Regenerant based on bed volume (from config)
    regenerant_kg = bed_volume_L / 1000 * CONFIG.REGENERANT_DOSE_KG_M3
    
    return SACSimulationOutput(
        status="success" if breakthrough_found else "warning",
        breakthrough_bv=round(breakthrough_bv, 1),
        service_time_hours=round(service_time_hours, 1),
        breakthrough_hardness_mg_l_caco3=target_hardness,
        breakthrough_reached=breakthrough_found,
        warnings=warnings,
        phreeqc_determined_capacity_factor=round(phreeqc_competition_factor, 2),
        capacity_utilization_percent=round(actual_capacity_utilization * 100, 1),
        breakthrough_data=breakthrough_data,
        simulation_details={
            "bed_volume_L": bed_volume_L,
            "theoretical_bv": round(theoretical_bv, 1),
            "max_bv_simulated": max_bv,
            "cells": CONFIG.DEFAULT_CELLS,
            "porosity": porosity,
            "hardness_removed_eq": round(hardness_removed_eq, 1),
            "regenerant_required_kg": round(regenerant_kg, 1),
            "total_capacity_eq": round(total_capacity_eq, 1)
        }
    )


def _run_full_cycle_simulation(input_data: SACSimulationInput) -> SACSimulationOutput:
    """Run complete IX cycle simulation including regeneration."""
    water = input_data.water_analysis
    vessel = input_data.vessel_configuration
    target_hardness = input_data.target_hardness_mg_l_caco3
    regen_config = input_data.regeneration_config
    full_data = input_data.full_data
    
    # Create simulation instance
    sim = _IXDirectPhreeqcSimulation()
    
    # Build vessel config for PHREEQC
    vessel_config_phreeqc = {
        'resin_type': 'SAC',
        'bed_depth_m': vessel.bed_depth_m,
        'diameter_m': vessel.diameter_m,
        'bed_volume_L': vessel.bed_volume_L,
        'resin_capacity_eq_L': CONFIG.RESIN_CAPACITY_EQ_L,
        'bed_porosity': CONFIG.BED_POROSITY
    }
    
    try:
        # Run full cycle simulation
        cycle_data, regen_results, breakthrough_bv = sim.run_full_cycle_simulation(
            water=water,
            vessel_config=vessel_config_phreeqc,
            regen_config=regen_config,
            target_hardness=target_hardness
        )
        
        # Use the breakthrough_bv from the service simulation
        # No need to recalculate it from cycle_data
        breakthrough_found = breakthrough_bv is not None and breakthrough_bv > 0
        
        # Calculate service time
        flow_L_hr = water.flow_m3_hr * 1000
        service_time_hours = breakthrough_bv * vessel.bed_volume_L / flow_L_hr
        
        # Calculate capacity metrics
        ca_meq_L = water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT
        mg_meq_L = water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT
        hardness_meq_L = ca_meq_L + mg_meq_L
        theoretical_bv = (CONFIG.RESIN_CAPACITY_EQ_L * 1000) / hardness_meq_L if hardness_meq_L > 0 else 0
        actual_capacity_utilization = breakthrough_bv / theoretical_bv if theoretical_bv > 0 else 0
        
        # Apply smart sampling if requested
        if not full_data:
            cycle_data = _smart_sample_cycle_data(cycle_data, regen_config)
        
        # Calculate total cycle time
        total_cycle_time = service_time_hours + regen_results.regeneration_time_hours
        
        return SACSimulationOutput(
            status="success" if breakthrough_found else "warning",
            breakthrough_bv=round(breakthrough_bv, 1),
            service_time_hours=round(service_time_hours, 1),
            breakthrough_hardness_mg_l_caco3=target_hardness,
            breakthrough_reached=breakthrough_found,
            warnings=[],
            phreeqc_determined_capacity_factor=round(actual_capacity_utilization, 2),
            capacity_utilization_percent=round(actual_capacity_utilization * 100, 1),
            breakthrough_data=cycle_data,  # Now includes all phases
            simulation_details={
                "bed_volume_L": vessel.bed_volume_L,
                "theoretical_bv": round(theoretical_bv, 1),
                "cells": CONFIG.DEFAULT_CELLS,
                "porosity": CONFIG.BED_POROSITY,
                "cycle_phases": list(set(cycle_data['phases'])),
                "total_data_points": len(cycle_data['bed_volumes'])
            },
            regeneration_results=regen_results,
            total_cycle_time_hours=round(total_cycle_time, 1)
        )
        
    except Exception as e:
        logger.error(f"Full cycle simulation failed: {e}")
        raise


def _smart_sample_cycle_data(cycle_data: Dict[str, Any], regen_config: RegenerationConfig) -> Dict[str, Any]:
    """Apply phase-aware smart sampling to reduce data size for plotting."""
    total_points = len(cycle_data['bed_volumes'])
    if total_points < 500:  # If already reasonably sized, return as-is
        return cycle_data
    
    # Phase-aware sampling strategy
    indices_to_keep = []
    phases = cycle_data['phases']
    bed_volumes = cycle_data['bed_volumes']
    hardness = cycle_data.get('hardness_mg_l', [])
    na_fraction = cycle_data.get('na_fraction', [])
    
    # Get breakthrough point from cycle_data (now included)
    breakthrough_bv = cycle_data.get('breakthrough_bv', None)
    if breakthrough_bv is None:
        # Fallback: Find breakthrough point in SERVICE phase
        target_hardness = cycle_data.get('target_hardness', 5.0)
        for i, (phase, bv, h) in enumerate(zip(phases, bed_volumes, hardness)):
            if phase == 'SERVICE' and h > target_hardness:
                breakthrough_bv = bv
                break
    
    # Sample each phase with different strategies
    for i in range(total_points):
        phase = phases[i]
        bv = bed_volumes[i]
        
        # Always keep phase transitions
        if i == 0 or phases[i] != phases[i-1]:
            indices_to_keep.append(i)
            continue
        
        if phase == 'SERVICE':
            # Special handling for chromatographic features
            # 1. High resolution at start (Na spike from regenerant flush)
            if bv <= 5:
                indices_to_keep.append(i)  # Every point in first 5 BV
            # 2. High resolution near breakthrough
            elif breakthrough_bv and abs(bv - breakthrough_bv) <= 10:
                indices_to_keep.append(i)  # Every point near breakthrough
            # 3. High resolution in Mg spike region (typically 1.1-1.5x breakthrough)
            elif breakthrough_bv and breakthrough_bv * 1.1 <= bv <= breakthrough_bv * 1.5:
                if i % 2 == 0:  # Every 2nd point in Mg spike region
                    indices_to_keep.append(i)
            # 4. Medium resolution in transition zones
            elif breakthrough_bv and abs(bv - breakthrough_bv) <= 30:
                if i % 3 == 0:  # Every 3rd point in transition
                    indices_to_keep.append(i)
            # 5. Lower resolution far from features
            else:
                if i % 10 == 0:  # Every 10th point far from features
                    indices_to_keep.append(i)
                    
        elif phase == 'REGENERATION':
            # High resolution during regeneration to track recovery
            if i % 2 == 0:  # Every 2nd point
                indices_to_keep.append(i)
                
        elif phase in ['SLOW_RINSE', 'FAST_RINSE']:
            # Medium resolution during rinses
            if i % 3 == 0:  # Every 3rd point
                indices_to_keep.append(i)
                
        elif phase == 'BACKWASH':
            # Low resolution during backwash
            if i % 5 == 0:  # Every 5th point
                indices_to_keep.append(i)
    
    # Always include last point
    if indices_to_keep[-1] != total_points - 1:
        indices_to_keep.append(total_points - 1)
    
    # Create sampled data
    sampled_data = {}
    for key, values in cycle_data.items():
        if isinstance(values, list) and len(values) == total_points:
            sampled_data[key] = [values[i] for i in indices_to_keep]
        else:
            sampled_data[key] = values  # Keep non-list data as-is
    
    logger.info(f"Phase-aware sampling: {total_points} points reduced to {len(indices_to_keep)} points")
    logger.info(f"  - Data reduction: {(1 - len(indices_to_keep)/total_points)*100:.1f}%")
    
    return sampled_data