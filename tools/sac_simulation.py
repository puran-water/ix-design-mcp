"""
SAC Ion Exchange Simulation Tool

Simulates SAC ion exchange using Direct PHREEQC engine.
Uses target hardness breakthrough definition and PHREEQC-determined capacity.
NO HEURISTIC CALCULATIONS - all competition effects from thermodynamics.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from datetime import datetime
from pydantic import BaseModel, Field

# Add project root to path
project_root = Path(__file__).parent.parent
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

logger = logging.getLogger(__name__)


class SACSimulationInput(BaseModel):
    """Input for SAC simulation"""
    water_analysis: SACWaterComposition
    vessel_configuration: SACVesselConfiguration
    target_hardness_mg_l_caco3: float
    full_data: bool = Field(default=False, description="Return full resolution data (1000+ points) instead of smart-sampled data (~80 points)")


class SACSimulationOutput(BaseModel):
    """Output from SAC simulation"""
    status: str  # "success" or "warning"
    breakthrough_bv: float
    service_time_hours: float
    breakthrough_hardness_mg_l_caco3: float
    breakthrough_reached: bool
    warnings: List[str]
    phreeqc_determined_capacity_factor: float  # NOT heuristic
    capacity_utilization_percent: float
    breakthrough_data: Dict[str, List[float]]  # Always included for plotting tool
    simulation_details: Dict[str, Any]


class IXDirectPhreeqcSimulation:
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
            self.engine = DirectPhreeqcEngine(keep_temp_files=False)
            logger.info("Using DirectPhreeqcEngine with system PHREEQC")
            
    def run_sac_simulation(
        self,
        water: SACWaterComposition,
        vessel_config: Dict[str, Any],
        max_bv: int = 100,
        cells: int = 10
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
        
        # CORRECTED: Resin capacity is per liter of BED VOLUME
        resin_capacity_eq_L = vessel_config.get('resin_capacity_eq_L', CONFIG.RESIN_CAPACITY_EQ_L)  # eq/L bed
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
        
        # Build PHREEQC input with all MCAS ions
        phreeqc_input = f"""DATABASE {db_path}
TITLE SAC Simulation - Target Hardness Breakthrough

PHASES
    Fix_H+
    H+ = H+
    log_k 0.0

# Exchange species loaded from database

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
    Simulate SAC ion exchange with Direct PHREEQC.
    
    Key features:
    - Uses bed volume directly from configuration
    - Target hardness breakthrough detection
    - Dynamic max_bv calculation
    - PHREEQC determines all competition effects
    - No heuristic calculations
    """
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
    sim = IXDirectPhreeqcSimulation()
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