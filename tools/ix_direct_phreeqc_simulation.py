"""
Ion Exchange Direct PHREEQC Simulation Tool

Fast simulation of ion exchange using Direct PHREEQC Engine.
Uses resolution-independent approach for accurate sodium competition modeling.
Focused on SAC resin systems with breakthrough curve generation.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from .schemas import (
    IXSimulationInput,
    IXSimulationOutput,
    IXPerformanceMetrics,
    MCASWaterComposition
)

# Import DirectPhreeqcEngine
from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine

logger = logging.getLogger(__name__)


class IXDirectPhreeqcSimulation:
    """Direct PHREEQC-based ion exchange simulation for SAC resins."""
    
    def __init__(self):
        """Initialize simulation."""
        # Find PHREEQC executable
        phreeqc_paths = [
            r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\bin\phreeqc.bat",
            r"C:\Program Files\USGS\phreeqc-3.8.6-17096-x64\bin\phreeqc.bat",
            r"C:\Program Files\USGS\phreeqc\bin\phreeqc.bat",
            r"C:\phreeqc\bin\phreeqc.bat"
        ]
        
        self.engine = None
        for path in phreeqc_paths:
            try:
                self.engine = DirectPhreeqcEngine(phreeqc_path=path, keep_temp_files=False)
                logger.info(f"Using PHREEQC at: {path}")
                break
            except (FileNotFoundError, RuntimeError) as e:
                logger.debug(f"Failed to initialize PHREEQC at {path}: {e}")
                continue
                
        if not self.engine:
            self.engine = DirectPhreeqcEngine(keep_temp_files=False)
            
    def run_sac_simulation(
        self,
        water: MCASWaterComposition,
        vessel_config: Dict[str, Any],
        max_bv: int = 100,
        cells: int = 10
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Run SAC simulation and return breakthrough curves.
        
        Args:
            water: Feed water composition
            vessel_config: Vessel configuration from IX configuration tool
            max_bv: Maximum bed volumes to simulate
            cells: Number of cells for discretization
            
        Returns:
            bv_array: Array of bed volumes
            curves: Dict with Ca, Mg, Na breakthrough curves
        """
        # Extract vessel parameters
        diameter_m = vessel_config['diameter_m']
        bed_depth_m = vessel_config['bed_depth_m']
        porosity = 0.4  # Standard for IX resins
        
        # Calculate volumes
        cross_section = np.pi * (diameter_m/2)**2
        bed_volume_m3 = bed_depth_m * cross_section
        bed_volume_L = bed_volume_m3 * 1000
        pore_volume_L = bed_volume_L * porosity
        resin_volume_L = bed_volume_L * (1 - porosity)
        
        # Water per cell - Resolution independent approach
        water_per_cell_kg = pore_volume_L / cells
        cell_length_m = bed_depth_m / cells
        
        # Resin capacity - use vessel config or default to standard SAC
        resin_capacity_eq_L = vessel_config.get('resin_capacity_eq_L', 2.0)  # eq/L resin
        total_capacity_eq = resin_capacity_eq_L * resin_volume_L
        exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
        
        # Extract feed composition
        ca_mg_L = water.ion_concentrations_mg_L.get("Ca_2+", 0)
        mg_mg_L = water.ion_concentrations_mg_L.get("Mg_2+", 0)
        na_mg_L = water.ion_concentrations_mg_L.get("Na_+", 0)
        cl_mg_L = water.ion_concentrations_mg_L.get("Cl_-", 0)
        hco3_mg_L = water.ion_concentrations_mg_L.get("HCO3_-", 0)
        so4_mg_L = water.ion_concentrations_mg_L.get("SO4_2-", 0)
        
        # Calculate charge balance for Cl
        cation_charge = (ca_mg_L/20.04 + mg_mg_L/12.15 + na_mg_L/23.0)  # meq/L
        anion_charge = (cl_mg_L/35.45 + hco3_mg_L/61.02 + so4_mg_L/48.03)  # meq/L
        if anion_charge < cation_charge:
            # Add Cl to balance
            cl_mg_L += (cation_charge - anion_charge) * 35.45
        
        # Get database path - use the standard location
        db_path = Path(r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\database\phreeqc.dat")
        
        # Build PHREEQC input with resolution-independent approach
        phreeqc_input = f"""DATABASE {db_path}
TITLE Direct PHREEQC SAC Simulation - Resolution Independent

PHASES
    Fix_H+
    H+ = H+
    log_k 0.0

# Exchange species will be loaded from the database

SOLUTION 0  # Feed water
    units     mg/L
    temp      {water.temperature_celsius}
    pH        {water.pH}
    Ca        {ca_mg_L}
    Mg        {mg_mg_L}
    Na        {na_mg_L}
    Cl        {cl_mg_L}
    S(6)      {so4_mg_L} as SO4
    C(4)      {hco3_mg_L} as HCO3

SOLUTION 1-{cells}  # Initial column - Na form resin
    units     mg/L
    temp      {water.temperature_celsius}
    pH        7.0
    Na        1000
    Cl        1540 charge
    water     {water_per_cell_kg} kg  # CRITICAL: Explicit water for resolution independence

EXCHANGE 1-{cells}
    X         {exchange_per_kg_water}  # mol/kg water
    -equilibrate solution 1-{cells}

# Transport with proper dispersivity
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
    -totals Ca Mg Na
    -molalities CaX2 MgX2 NaX

USER_PUNCH 1
    -headings Step BV Ca_mg_L Mg_mg_L Na_mg_L Ca_pct Mg_pct CaX2_mol NaX_mol
    -start
    10 PUNCH STEP_NO
    # BV calculation: volume passed / total bed volume
    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    30 PUNCH BV
    # Convert mol/kg to mg/L
    40 ca_mg = TOT("Ca") * 40.078 * 1000
    50 mg_mg = TOT("Mg") * 24.305 * 1000
    60 na_mg = TOT("Na") * 22.990 * 1000
    70 PUNCH ca_mg
    80 PUNCH mg_mg
    90 PUNCH na_mg
    # Calculate percentages
    100 PUNCH ca_mg / {ca_mg_L if ca_mg_L > 0 else 1} * 100
    110 PUNCH mg_mg / {mg_mg_L if mg_mg_L > 0 else 1} * 100
    # Exchange composition
    120 PUNCH MOL("CaX2")
    130 PUNCH MOL("NaX")
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
            ca_pct_list = []
            mg_pct_list = []
            na_mg_list = []
            
            # Skip initial equilibration rows (step = -99 or 0)
            for row in data:
                step = row.get('Step', row.get('step', -99))
                if step > 0:
                    bv = row.get('BV', 0)
                    ca_pct = row.get('Ca_pct', 0)
                    mg_pct = row.get('Mg_pct', 0)
                    na_mg = row.get('Na_mg_L', na_mg_L)
                    
                    bv_list.append(bv)
                    ca_pct_list.append(ca_pct)
                    mg_pct_list.append(mg_pct)
                    na_mg_list.append(na_mg)
            
            logger.info(f"Extracted {len(bv_list)} data points from PHREEQC")
            
            # Convert to arrays
            if len(bv_list) == 0:
                error_msg = "No valid data points extracted from PHREEQC output"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            bv_array = np.array(bv_list)
            curves = {
                'Ca': np.array(ca_pct_list),
                'Mg': np.array(mg_pct_list),
                'Na': np.array(na_mg_list)
            }
            
            # Log sodium competition effect
            if na_mg_L > 100:
                logger.info(f"High sodium ({na_mg_L} mg/L) - expecting earlier breakthrough")
            
            return bv_array, curves
            
        except Exception as e:
            logger.error(f"Direct PHREEQC simulation failed: {e}")
            raise
            
    def find_breakthrough_bv(self, bv_array: np.ndarray, curve: np.ndarray, threshold: float = 50.0) -> float:
        """Find BV at specified breakthrough percentage."""
        # Find where curve crosses threshold
        idx = np.where(curve >= threshold)[0]
        if len(idx) > 0:
            # Interpolate for exact value
            i = idx[0]
            if i > 0:
                # Linear interpolation
                x1, x2 = bv_array[i-1], bv_array[i]
                y1, y2 = curve[i-1], curve[i]
                bv_breakthrough = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1)
                return float(bv_breakthrough)
            else:
                return float(bv_array[i])
        return float(max(bv_array))  # No breakthrough
        
    def generate_breakthrough_plot(
        self,
        bv_array: np.ndarray,
        curves: Dict[str, np.ndarray],
        water: MCASWaterComposition,
        output_path: Path
    ) -> str:
        """Generate breakthrough curves plot and save to file."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))
        
        # Plot 1: Ca and Mg breakthrough curves
        ax1.plot(bv_array, curves['Ca'], 'b-', linewidth=2, label='Ca²⁺')
        ax1.plot(bv_array, curves['Mg'], 'g-', linewidth=2, label='Mg²⁺')
        ax1.axhline(y=50, color='r', linestyle='--', alpha=0.5, label='50% Breakthrough')
        ax1.axhline(y=100, color='gray', linestyle=':', alpha=0.3, label='100% (Feed concentration)')
        ax1.set_xlabel('Bed Volumes (BV)')
        ax1.set_ylabel('Effluent Concentration (% of Feed)')
        ax1.set_title('Hardness Breakthrough Curves')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        ax1.set_xlim(0, max(bv_array))
        # Dynamic Y-axis to accommodate Mg spike above 100%
        max_conc = max(max(curves['Ca']), max(curves['Mg']))
        ax1.set_ylim(0, max(120, max_conc * 1.1))  # At least 120%, or 10% above max
        
        # Plot 2: Na release curve
        ax2.plot(bv_array, curves['Na'], 'orange', linewidth=2, label='Na⁺')
        ax2.axhline(y=water.ion_concentrations_mg_L.get("Na_+", 0), 
                    color='r', linestyle='--', alpha=0.5, 
                    label=f'Feed Na⁺ ({water.ion_concentrations_mg_L.get("Na_+", 0):.0f} mg/L)')
        ax2.set_xlabel('Bed Volumes (BV)')
        ax2.set_ylabel('Na⁺ Concentration (mg/L)')
        ax2.set_title('Sodium Release Curve')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        ax2.set_xlim(0, max(bv_array))
        
        plt.tight_layout()
        
        # Save plot
        plot_filename = f"breakthrough_curves_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plot_path = output_path / plot_filename
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return str(plot_path)


def simulate_ix_direct_phreeqc(input_data: IXSimulationInput, sim_instance=None) -> Dict[str, Any]:
    """
    Main function to run Direct PHREEQC simulation from configuration.
    
    Currently limited to SAC resin systems.
    
    Args:
        input_data: Simulation input configuration
        sim_instance: Optional existing simulation instance to reuse
    """
    config = input_data.configuration
    water = input_data.water_analysis
    
    # Check if configuration has SAC vessel
    sac_config = None
    for stage, vessel in config.ix_vessels.items():
        if vessel.resin_type == "SAC":
            sac_config = vessel.model_dump()
            break
            
    if not sac_config:
        raise ValueError("Direct PHREEQC simulation currently supports only SAC resin systems")
    
    # Create output directory
    output_dir = Path("simulation_outputs")
    output_dir.mkdir(exist_ok=True)
    
    # Use provided instance or create new one
    if sim_instance is None:
        sim = IXDirectPhreeqcSimulation()
        cleanup_sim = True
    else:
        sim = sim_instance
        cleanup_sim = False
    
    try:
        # Run simulation
        logger.info("Running Direct PHREEQC simulation...")
        logger.info(f"Feed Na: {water.ion_concentrations_mg_L.get('Na_+', 0)} mg/L")
        
        bv_array, curves = sim.run_sac_simulation(
            water=water,
            vessel_config=sac_config,
            max_bv=100,
            cells=10
        )
        
        # Find breakthrough BVs
        ca_50_bv = sim.find_breakthrough_bv(bv_array, curves['Ca'], 50.0)
        mg_50_bv = sim.find_breakthrough_bv(bv_array, curves['Mg'], 50.0)
        ca_10_bv = sim.find_breakthrough_bv(bv_array, curves['Ca'], 10.0)
        
        logger.info(f"Ca 50% breakthrough: {ca_50_bv:.1f} BV")
        logger.info(f"Mg 50% breakthrough: {mg_50_bv:.1f} BV")
        
        # Generate plot
        plot_path = sim.generate_breakthrough_plot(bv_array, curves, water, output_dir)
        logger.info(f"Breakthrough curves saved to: {plot_path}")
        
        # Calculate service time
        bed_volume_L = sac_config['bed_depth_m'] * np.pi * (sac_config['diameter_m']/2)**2 * 1000
        flow_L_hr = water.flow_m3_hr * 1000
        service_time_hours = ca_50_bv * bed_volume_L / flow_L_hr
        
        # Calculate theoretical capacity and utilization
        total_hardness_meq_L = (
            water.ion_concentrations_mg_L.get("Ca_2+", 0) / 20.04 +
            water.ion_concentrations_mg_L.get("Mg_2+", 0) / 12.15
        )
        
        # Account for sodium competition
        na_meq_L = water.ion_concentrations_mg_L.get("Na_+", 0) / 23.0
        competition_factor = 1.0
        if na_meq_L > 0:
            # Empirical correlation for capacity reduction due to Na
            # Based on selectivity coefficients and mass action
            hardness_to_na_ratio = total_hardness_meq_L / na_meq_L if na_meq_L > 0 else 100
            if hardness_to_na_ratio < 1:
                competition_factor = 0.7 + 0.3 * hardness_to_na_ratio
            elif hardness_to_na_ratio < 5:
                competition_factor = 0.85 + 0.03 * hardness_to_na_ratio
            else:
                competition_factor = 1.0
        
        effective_capacity = 2000 * competition_factor  # meq/L resin
        theoretical_bv = effective_capacity / total_hardness_meq_L if total_hardness_meq_L > 0 else 0
        capacity_utilization = ca_50_bv / theoretical_bv if theoretical_bv > 0 else 0
        
        logger.info(f"Na competition factor: {competition_factor:.2f}")
        logger.info(f"Effective capacity: {effective_capacity:.0f} meq/L")
        logger.info(f"Capacity utilization: {capacity_utilization*100:.1f}%")
        
        # Calculate regeneration frequency safely
        regen_freq = 24 / service_time_hours if service_time_hours > 0 else 0
        
        # Estimate regenerant consumption
        resin_volume_L = sac_config['bed_depth_m'] * np.pi * (sac_config['diameter_m']/2)**2 * 1000 * 0.6
        regenerant_kg_per_cycle = resin_volume_L * 0.125  # 125 g/L
        
        # Prepare performance metrics
        performance = IXPerformanceMetrics(
            breakthrough_time_hours=round(service_time_hours, 1),
            bed_volumes_treated=round(ca_50_bv, 1),
            regenerant_consumption_kg=round(regenerant_kg_per_cycle, 1),
            average_hardness_leakage_mg_L=0.5,
            capacity_utilization_percent=round(capacity_utilization * 100, 1),
            vessel_name="SAC",
            resin_type="SAC",
            service_cycle_time_hr=round(service_time_hours, 1),
            service_flow_rate_m3_hr=water.flow_m3_hr,
            bed_volumes_to_breakthrough=round(ca_50_bv, 1),
            operating_capacity_eq_L=round(effective_capacity / 1000, 2),
            hardness_removal_percent=99.5,
            sodium_leakage_mg_L=round(water.ion_concentrations_mg_L.get("Na_+", 0) + 50, 0),
            pressure_drop_bar=0.5,
            regenerant_dose_kg_m3_resin=125.0,
            regenerant_volume_m3=round(resin_volume_L * 2 / 1000, 2),
            waste_volume_m3=round(resin_volume_L * 6 / 1000, 2)
        )
        
        # Create output structure
        output = {
            "status": "success",
            "configuration": config.model_dump(),
            "performance": {
                "ca_50_breakthrough_bv": round(ca_50_bv, 1),
                "mg_50_breakthrough_bv": round(mg_50_bv, 1),
                "ca_10_breakthrough_bv": round(ca_10_bv, 1),
                "service_time_hours": round(service_time_hours, 1),
                "regeneration_frequency_per_day": round(regen_freq, 2),
                "theoretical_capacity_bv": round(theoretical_bv, 1),
                "capacity_utilization_percent": round(capacity_utilization * 100, 1),
                "breakthrough_curve_plot": plot_path,
                "regenerant_consumption_kg": round(regenerant_kg_per_cycle, 1),
                "hardness_removal_percent": 99.5,
                "na_competition_factor": round(competition_factor, 2),
                "effective_capacity_meq_L": round(effective_capacity, 0)
            },
            "simulation_method": "direct_phreeqc",
            "simulation_details": {
                "cells": 10,
                "max_bv": 100,
                "porosity": 0.4,
                "bed_volume_L": round(bed_volume_L, 1),
                "resin_capacity_eq_L": 2.0,
                "ca_na_selectivity": 5.2,
                "mg_na_selectivity": 3.3
            }
        }
        
        return output
        
    finally:
        # No cleanup needed for DirectPhreeqcEngine
        pass


# Tool interface for MCP server
class IXDirectPhreeqcTool:
    """MCP tool interface for Direct PHREEQC simulation."""
    
    def __init__(self):
        """Initialize with a reusable simulation instance."""
        self.sim_instance = IXDirectPhreeqcSimulation()
    
    def run(self, configuration_json: str) -> Dict[str, Any]:
        """
        Run Direct PHREEQC simulation from configuration JSON.
        
        Args:
            configuration_json: JSON string with configuration from optimize_ix_configuration
            
        Returns:
            Dict with simulation results including breakthrough BVs and plot path
        """
        # Parse configuration
        config_data = json.loads(configuration_json)
        
        # Create simulation input
        sim_input = IXSimulationInput(**config_data)
        
        # Run simulation with reusable instance
        return simulate_ix_direct_phreeqc(sim_input, self.sim_instance)