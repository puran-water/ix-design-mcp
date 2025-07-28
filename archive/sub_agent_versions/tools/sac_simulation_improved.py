"""
SAC Ion Exchange Simulation Tool - Improved Integration

Uses optimized PHREEQC engine with proper configuration and monitoring.
"""

import sys
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime
from pydantic import BaseModel, Field

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import PHREEQC engines with proper error handling
try:
    from watertap_ix_transport.transport_core.optimized_phreeqc_engine_refactored import OptimizedPhreeqcEngine
    OPTIMIZED_ENGINE_AVAILABLE = True
except ImportError:
    OPTIMIZED_ENGINE_AVAILABLE = False
    logging.warning("Optimized PHREEQC engine not available, using standard engine")
    
from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine

# Import schemas from sac_configuration
from .sac_configuration import (
    SACWaterComposition,
    SACVesselConfiguration,
    SACConfigurationOutput
)

# Import centralized configuration
from .core_config import CONFIG

logger = logging.getLogger(__name__)


class SACSimulationInput(BaseModel):
    """Input for SAC simulation"""
    water_analysis: SACWaterComposition
    vessel_configuration: SACVesselConfiguration
    target_hardness_mg_l_caco3: float


class SACSimulationOutput(BaseModel):
    """Output from SAC simulation with performance metrics"""
    status: str  # "success" or "warning"
    breakthrough_bv: float
    service_time_hours: float
    breakthrough_hardness_mg_l_caco3: float
    breakthrough_reached: bool
    warnings: List[str]
    phreeqc_determined_capacity_factor: float
    capacity_utilization_percent: float
    plot_path: str
    simulation_details: Dict[str, Any]
    performance_metrics: Optional[Dict[str, Any]] = None  # NEW


class IXDirectPhreeqcSimulation:
    """
    Direct PHREEQC-based ion exchange simulation for SAC resins.
    
    Improved version with:
    - Configurable optimization settings
    - Performance monitoring
    - Better error handling
    - Cache management
    """
    
    def __init__(
        self,
        enable_optimization: bool = True,
        cache_size: int = 256,
        cache_ttl_hours: float = 1.0,
        max_workers: int = 4,
        collect_metrics: bool = True
    ):
        """
        Initialize simulation with configurable optimization.
        
        Args:
            enable_optimization: Use optimized engine if available
            cache_size: Number of results to cache (0 disables)
            cache_ttl_hours: Cache time-to-live in hours
            max_workers: Maximum parallel workers
            collect_metrics: Collect performance metrics
        """
        self.collect_metrics = collect_metrics
        self.optimization_enabled = False
        
        # Get PHREEQC path from centralized config
        phreeqc_exe = CONFIG.get_phreeqc_exe()
        
        # Try to initialize optimized engine if requested
        if enable_optimization and OPTIMIZED_ENGINE_AVAILABLE:
            try:
                # Configure based on environment
                if os.getenv('IX_DISABLE_CACHE') == '1':
                    cache_size = 0
                    logger.info("Cache disabled by environment variable")
                
                if os.getenv('IX_DISABLE_PARALLEL') == '1':
                    max_workers = 1
                    logger.info("Parallel execution disabled by environment variable")
                
                self.engine = OptimizedPhreeqcEngine(
                    phreeqc_path=str(phreeqc_exe),
                    cache_size=cache_size,
                    cache_ttl_seconds=cache_ttl_hours * 3600,
                    max_workers=max_workers,
                    enable_cache=cache_size > 0,
                    enable_parallel=max_workers > 1,
                    collect_metrics=collect_metrics
                )
                self.optimization_enabled = True
                logger.info(
                    f"Using OptimizedPhreeqcEngine: "
                    f"cache_size={cache_size}, "
                    f"ttl={cache_ttl_hours}h, "
                    f"workers={max_workers}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize OptimizedPhreeqcEngine: {e}")
                enable_optimization = False
        
        # Fall back to standard engine
        if not self.optimization_enabled:
            try:
                self.engine = DirectPhreeqcEngine(
                    phreeqc_path=str(phreeqc_exe), 
                    keep_temp_files=False
                )
                logger.info(f"Using DirectPhreeqcEngine at: {phreeqc_exe}")
            except (FileNotFoundError, RuntimeError) as e:
                logger.warning(f"Failed to initialize PHREEQC at {phreeqc_exe}: {e}")
                # Try without specifying path (will search system)
                self.engine = DirectPhreeqcEngine(keep_temp_files=False)
                logger.info("Using DirectPhreeqcEngine with system search")
    
    def get_performance_metrics(self) -> Optional[Dict[str, Any]]:
        """Get performance metrics if available."""
        if self.optimization_enabled and hasattr(self.engine, 'get_metrics'):
            return self.engine.get_metrics()
        return None
    
    def clear_cache(self) -> None:
        """Clear cache if optimized engine is used."""
        if self.optimization_enabled and hasattr(self.engine, 'clear_cache'):
            self.engine.clear_cache()
            logger.info("Cache cleared")
    
    def run_sac_simulation(
        self,
        water: SACWaterComposition,
        vessel_config: Dict[str, Any],
        max_bv: int = 100,
        cells: int = 10
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Run SAC simulation with proper error handling and validation.
        
        Args:
            water: Feed water composition
            vessel_config: Vessel configuration from configuration tool
            max_bv: Maximum bed volumes to simulate (1-1000)
            cells: Number of cells for discretization (5-50)
            
        Returns:
            bv_array: Array of bed volumes
            curves: Dict with Ca, Mg, Na breakthrough curves
            
        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If simulation fails
        """
        # Parameter validation
        if not 1 <= max_bv <= 1000:
            raise ValueError(f"max_bv must be 1-1000, got {max_bv}")
        
        if not 5 <= cells <= 50:
            raise ValueError(f"cells must be 5-50, got {cells}")
        
        # Extract vessel parameters with validation
        bed_volume_L = vessel_config.get('bed_volume_L')
        if not bed_volume_L or bed_volume_L <= 0:
            raise ValueError(f"Invalid bed_volume_L: {bed_volume_L}")
        
        bed_depth_m = vessel_config.get('bed_depth_m')
        diameter_m = vessel_config.get('diameter_m')
        porosity = vessel_config.get('bed_porosity', CONFIG.BED_POROSITY)
        
        # Validate physical parameters
        if not 0.1 <= porosity <= 0.6:
            logger.warning(f"Unusual porosity: {porosity}")
        
        # Calculate volumes
        pore_volume_L = bed_volume_L * porosity
        
        # Water per cell - Resolution independent approach
        water_per_cell_kg = pore_volume_L / cells
        cell_length_m = bed_depth_m / cells
        
        # Resin capacity with proper units
        resin_capacity_eq_L = vessel_config.get(
            'resin_capacity_eq_L', 
            CONFIG.RESIN_CAPACITY_EQ_L
        )  # eq/L bed volume
        
        total_capacity_eq = resin_capacity_eq_L * bed_volume_L
        exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
        
        # Extract and validate feed composition
        ca_mg_L = water.ca_mg_l
        mg_mg_L = water.mg_mg_l
        na_mg_L = water.na_mg_l
        cl_mg_L = water.cl_mg_l
        hco3_mg_L = water.hco3_mg_l
        so4_mg_L = water.so4_mg_l
        k_mg_L = water.k_mg_l
        nh4_mg_L = water.nh4_mg_l
        
        # Check charge balance
        cation_charge = (
            ca_mg_L/CONFIG.CA_EQUIV_WEIGHT + 
            mg_mg_L/CONFIG.MG_EQUIV_WEIGHT + 
            na_mg_L/CONFIG.NA_EQUIV_WEIGHT + 
            k_mg_L/CONFIG.K_EQUIV_WEIGHT + 
            nh4_mg_L/CONFIG.NH4_EQUIV_WEIGHT
        )  # meq/L
        
        anion_charge = (
            cl_mg_L/CONFIG.CL_EQUIV_WEIGHT + 
            hco3_mg_L/CONFIG.HCO3_EQUIV_WEIGHT + 
            so4_mg_L/CONFIG.SO4_EQUIV_WEIGHT
        )  # meq/L
        
        charge_imbalance_pct = abs(cation_charge - anion_charge) / max(cation_charge, anion_charge) * 100
        if charge_imbalance_pct > 5:
            logger.warning(
                f"Significant charge imbalance: {charge_imbalance_pct:.1f}% "
                f"(cations: {cation_charge:.2f}, anions: {anion_charge:.2f} meq/L)"
            )
        
        # Get database path
        db_path = CONFIG.get_phreeqc_database()
        
        # Build PHREEQC input with comprehensive ion list
        phreeqc_input = f"""DATABASE {db_path}
TITLE SAC Simulation - Optimized Engine
# Water composition: Ca={ca_mg_L}, Mg={mg_mg_L}, Na={na_mg_L} mg/L
# Vessel: {bed_volume_L:.1f} L, {cells} cells
# Exchange capacity: {exchange_per_kg_water:.4f} mol/kg water

PHASES
    Fix_H+
    H+ = H+
    log_k 0.0

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
    water     {water_per_cell_kg} kg  # Explicit water mass

EXCHANGE 1-{cells}
    X         {exchange_per_kg_water}  # mol/kg water
    -equilibrate solution 1-{cells}

# Transport parameters
TRANSPORT
    -cells    {cells}
    -shifts   {int(max_bv * bed_volume_L / water_per_cell_kg)}
    -lengths  {cell_length_m}
    -dispersivities {cells}*0.002  # Typical for packed beds
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
    -water true

USER_PUNCH 1
    -headings Step BV Ca_mg_L Mg_mg_L Na_mg_L K_mg_L Hardness_CaCO3 Water_kg
    -start
    10 PUNCH STEP_NO
    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    30 PUNCH BV
    # Convert mol/kg to mg/L with proper units
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
    # Water mass for validation
    140 PUNCH TOT("water")
    -end

END
"""
        
        try:
            # Log simulation start
            logger.info(
                f"Starting PHREEQC simulation: "
                f"max_bv={max_bv}, cells={cells}, "
                f"optimization={self.optimization_enabled}"
            )
            
            start_time = time.time()
            
            # Run simulation
            output, selected = self.engine.run_phreeqc(phreeqc_input, database=str(db_path))
            
            execution_time = time.time() - start_time
            logger.info(f"PHREEQC execution completed in {execution_time:.2f}s")
            
            # Parse selected output
            data = self.engine.parse_selected_output(selected)
            
            if not data or len(data) < 2:
                error_msg = f"Insufficient data from PHREEQC: {len(data) if data else 0} rows"
                logger.error(error_msg)
                
                # Log PHREEQC output for debugging
                if output:
                    logger.debug("PHREEQC output (first 1000 chars):")
                    logger.debug(output[:1000])
                
                raise RuntimeError(error_msg)
            
            # Extract and validate data
            bv_list = []
            ca_mg_list = []
            mg_mg_list = []
            na_mg_list = []
            hardness_list = []
            water_mass_list = []
            
            # Skip initial equilibration rows
            for row in data:
                step = row.get('Step', row.get('step', -99))
                if step > 0:
                    bv = row.get('BV', 0)
                    ca_mg = row.get('Ca_mg_L', 0)
                    mg_mg = row.get('Mg_mg_L', 0)
                    na_mg = row.get('Na_mg_L', na_mg_L)
                    hardness = row.get('Hardness_CaCO3', 0)
                    water_kg = row.get('Water_kg', water_per_cell_kg)
                    
                    # Validate water mass
                    if abs(water_kg - water_per_cell_kg) / water_per_cell_kg > 0.01:
                        logger.warning(
                            f"Water mass deviation at BV {bv:.1f}: "
                            f"expected {water_per_cell_kg:.3f} kg, "
                            f"got {water_kg:.3f} kg"
                        )
                    
                    bv_list.append(bv)
                    ca_mg_list.append(ca_mg)
                    mg_mg_list.append(mg_mg)
                    na_mg_list.append(na_mg)
                    hardness_list.append(hardness)
                    water_mass_list.append(water_kg)
            
            logger.info(f"Extracted {len(bv_list)} valid data points from PHREEQC")
            
            # Convert to arrays
            if len(bv_list) == 0:
                raise RuntimeError("No valid data points extracted from PHREEQC output")
            
            bv_array = np.array(bv_list)
            curves = {
                'Ca': np.array(ca_mg_list),
                'Mg': np.array(mg_mg_list),
                'Na': np.array(na_mg_list),
                'Hardness': np.array(hardness_list),
                'Ca_pct': np.array(ca_mg_list) / ca_mg_L * 100 if ca_mg_L > 0 else np.zeros_like(ca_mg_list),
                'Mg_pct': np.array(mg_mg_list) / mg_mg_L * 100 if mg_mg_L > 0 else np.zeros_like(mg_mg_list),
                'Water_kg': np.array(water_mass_list)
            }
            
            # Log key results
            max_hardness = np.max(curves['Hardness'])
            if na_mg_L > 100:
                logger.info(
                    f"High Na concentration ({na_mg_L:.0f} mg/L) - "
                    f"competition effects included in simulation"
                )
            
            logger.info(f"Maximum effluent hardness: {max_hardness:.1f} mg/L CaCO3")
            
            return bv_array, curves
            
        except Exception as e:
            logger.error(f"PHREEQC simulation failed: {e}")
            
            # Log performance metrics if available
            if self.collect_metrics:
                metrics = self.get_performance_metrics()
                if metrics:
                    logger.error(f"Performance metrics at failure: {metrics}")
            
            raise
    
    def find_target_breakthrough(
        self, 
        bv_array: np.ndarray, 
        hardness_array: np.ndarray, 
        target: float
    ) -> Optional[float]:
        """Find exact BV where hardness crosses target with validation."""
        # Validate inputs
        if len(bv_array) != len(hardness_array):
            raise ValueError("Array lengths must match")
        
        if len(bv_array) == 0:
            return None
        
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
    
    def generate_breakthrough_plot_with_target(
        self,
        bv_array: np.ndarray,
        curves: Dict[str, np.ndarray],
        water: SACWaterComposition,
        target_hardness: float,
        output_path: Path
    ) -> str:
        """Generate comprehensive breakthrough curves plot."""
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12))
        
        # Plot 1: Ca and Mg breakthrough with hardness
        ax1.plot(bv_array, curves['Ca_pct'], 'b-', linewidth=2, label='Ca²⁺')
        ax1.plot(bv_array, curves['Mg_pct'], 'g-', linewidth=2, label='Mg²⁺')
        
        # Total hardness on secondary y-axis
        ax1_twin = ax1.twinx()
        ax1_twin.plot(bv_array, curves['Hardness'], 'k-', linewidth=2, label='Total Hardness')
        ax1_twin.axhline(
            y=target_hardness,
            color='red',
            linestyle='--',
            linewidth=2,
            label=f'Target Hardness ({target_hardness} mg/L CaCO₃)'
        )
        ax1_twin.set_ylabel('Hardness (mg/L as CaCO₃)')
        ax1_twin.legend(loc='upper right')
        
        ax1.axhline(y=100, color='gray', linestyle=':', alpha=0.3)
        ax1.set_xlabel('Bed Volumes (BV)')
        ax1.set_ylabel('Effluent Concentration (% of Feed)')
        ax1.set_title('Hardness Breakthrough Curves')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left')
        ax1.set_xlim(0, max(bv_array))
        
        # Dynamic Y-axis
        max_conc = max(max(curves['Ca_pct']), max(curves['Mg_pct']))
        ax1.set_ylim(0, max(120, max_conc * 1.1))
        
        # Plot 2: Na release
        ax2.plot(bv_array, curves['Na'], 'orange', linewidth=2, label='Na⁺')
        ax2.axhline(
            y=water.na_mg_l, 
            color='r', 
            linestyle='--', 
            alpha=0.5, 
            label=f'Feed Na⁺ ({water.na_mg_l:.0f} mg/L)'
        )
        ax2.set_xlabel('Bed Volumes (BV)')
        ax2.set_ylabel('Na⁺ Concentration (mg/L)')
        ax2.set_title('Sodium Release Curve')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        ax2.set_xlim(0, max(bv_array))
        
        # Plot 3: Water mass conservation (quality check)
        if 'Water_kg' in curves:
            ax3.plot(bv_array, curves['Water_kg'], 'purple', linewidth=1, alpha=0.7)
            ax3.axhline(
                y=np.mean(curves['Water_kg']), 
                color='purple', 
                linestyle='--', 
                label=f'Mean: {np.mean(curves["Water_kg"]):.3f} kg'
            )
            ax3.set_xlabel('Bed Volumes (BV)')
            ax3.set_ylabel('Water Mass per Cell (kg)')
            ax3.set_title('Water Mass Conservation Check')
            ax3.grid(True, alpha=0.3)
            ax3.legend()
            ax3.set_xlim(0, max(bv_array))
            
            # Calculate deviation
            water_std_pct = np.std(curves['Water_kg']) / np.mean(curves['Water_kg']) * 100
            ax3.text(
                0.02, 0.95, 
                f'Std Dev: {water_std_pct:.1f}%',
                transform=ax3.transAxes,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5)
            )
        
        plt.tight_layout()
        
        # Save plot
        plot_filename = f"sac_breakthrough_optimized_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plot_path = output_path / plot_filename
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return str(plot_path)


def simulate_sac_phreeqc(input_data: SACSimulationInput) -> SACSimulationOutput:
    """
    Simulate SAC ion exchange with optimized PHREEQC engine.
    
    Enhanced version with:
    - Performance monitoring
    - Better error reporting
    - Cache management
    - Configurable optimization
    """
    water = input_data.water_analysis
    vessel = input_data.vessel_configuration
    target_hardness = input_data.target_hardness_mg_l_caco3
    
    # Get configuration from environment or defaults
    enable_optimization = os.getenv('IX_ENABLE_OPTIMIZATION', '1') == '1'
    cache_size = int(os.getenv('IX_CACHE_SIZE', '256'))
    collect_metrics = os.getenv('IX_COLLECT_METRICS', '1') == '1'
    
    # Use bed volume from configuration
    bed_volume_L = vessel.bed_volume_L
    bed_depth_m = vessel.bed_depth_m
    diameter_m = vessel.diameter_m
    
    # Calculate parameters
    porosity = CONFIG.BED_POROSITY
    pore_volume_L = bed_volume_L * porosity
    
    # Calculate theoretical capacity
    ca_meq_L = water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT
    mg_meq_L = water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT
    hardness_meq_L = ca_meq_L + mg_meq_L
    
    # Resin capacity per bed volume
    resin_capacity_eq_L = CONFIG.RESIN_CAPACITY_EQ_L
    total_capacity_eq = resin_capacity_eq_L * bed_volume_L
    
    # Theoretical bed volumes
    theoretical_bv = (resin_capacity_eq_L * 1000) / hardness_meq_L if hardness_meq_L > 0 else 0
    
    # Dynamic max_bv with safety factor
    max_bv = int(theoretical_bv * 1.2) if theoretical_bv > 0 else 200
    max_bv = min(max_bv, 500)  # Cap at reasonable maximum
    
    logger.info(f"Starting optimized simulation:")
    logger.info(f"  - Bed volume: {bed_volume_L:.1f} L")
    logger.info(f"  - Theoretical BV: {theoretical_bv:.1f}")
    logger.info(f"  - Simulation BV: {max_bv}")
    logger.info(f"  - Target hardness: {target_hardness} mg/L CaCO3")
    logger.info(f"  - Optimization: {enable_optimization}")
    
    # Build vessel config
    vessel_config_phreeqc = {
        'resin_type': 'SAC',
        'bed_depth_m': bed_depth_m,
        'diameter_m': diameter_m,
        'bed_volume_L': bed_volume_L,
        'resin_capacity_eq_L': resin_capacity_eq_L,
        'bed_porosity': porosity
    }
    
    # Create output directory
    output_dir = Path("simulation_outputs")
    output_dir.mkdir(exist_ok=True)
    
    # Initialize simulation with optimization settings
    sim = IXDirectPhreeqcSimulation(
        enable_optimization=enable_optimization,
        cache_size=cache_size,
        collect_metrics=collect_metrics
    )
    
    warnings = []
    performance_metrics = None
    
    try:
        # Run simulation
        start_time = time.time()
        
        bv_array, curves = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_config_phreeqc,
            max_bv=max_bv,
            cells=CONFIG.DEFAULT_CELLS
        )
        
        total_time = time.time() - start_time
        logger.info(f"Total simulation time: {total_time:.2f}s")
        
        # Get performance metrics
        if collect_metrics:
            performance_metrics = sim.get_performance_metrics()
            if performance_metrics:
                logger.info(f"Performance metrics: {performance_metrics}")
        
        # Find breakthrough
        breakthrough_bv = sim.find_target_breakthrough(
            bv_array,
            curves['Hardness'],
            target_hardness
        )
        
        if breakthrough_bv is not None:
            breakthrough_found = True
            logger.info(f"Breakthrough at {breakthrough_bv:.1f} BV")
        else:
            breakthrough_found = False
            max_hardness = max(curves['Hardness'])
            breakthrough_bv = max(bv_array)
            
            warnings.append(
                f"Target hardness not reached. Max: {max_hardness:.1f} mg/L "
                f"(target: {target_hardness}). Using {breakthrough_bv:.1f} BV."
            )
            logger.warning(warnings[-1])
            
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        
        # Log final metrics on failure
        if collect_metrics:
            final_metrics = sim.get_performance_metrics()
            if final_metrics:
                logger.error(f"Metrics at failure: {final_metrics}")
        
        raise
    
    # Calculate service time
    flow_L_hr = water.flow_m3_hr * 1000
    service_time_hours = breakthrough_bv * bed_volume_L / flow_L_hr
    
    # Calculate utilization
    actual_capacity_utilization = breakthrough_bv / theoretical_bv if theoretical_bv > 0 else 0
    phreeqc_competition_factor = actual_capacity_utilization
    
    logger.info(f"Results:")
    logger.info(f"  - Service time: {service_time_hours:.1f} hours")
    logger.info(f"  - Capacity factor: {phreeqc_competition_factor:.2f}")
    logger.info(f"  - Utilization: {actual_capacity_utilization * 100:.1f}%")
    
    # Generate plot
    plot_path = sim.generate_breakthrough_plot_with_target(
        bv_array, curves, water, target_hardness, output_dir
    )
    
    # Calculate regenerant
    hardness_removed_eq = hardness_meq_L * breakthrough_bv * bed_volume_L / 1000
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
        plot_path=str(plot_path),
        simulation_details={
            "bed_volume_L": bed_volume_L,
            "theoretical_bv": round(theoretical_bv, 1),
            "max_bv_simulated": max_bv,
            "cells": CONFIG.DEFAULT_CELLS,
            "porosity": porosity,
            "hardness_removed_eq": round(hardness_removed_eq, 1),
            "regenerant_required_kg": round(regenerant_kg, 1),
            "total_capacity_eq": round(total_capacity_eq, 1),
            "optimization_enabled": sim.optimization_enabled,
            "simulation_time_s": round(total_time, 2)
        },
        performance_metrics=performance_metrics
    )