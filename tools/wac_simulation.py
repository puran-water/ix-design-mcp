"""
WAC Ion Exchange Simulation Tool

Simulates WAC ion exchange using Direct PHREEQC engine.
Supports both Na-form and H-form WAC resins with appropriate
breakthrough detection and performance metrics.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import json
from datetime import datetime
from pydantic import BaseModel, Field, validator

# Get project root
def get_project_root() -> Path:
    """Get project root with environment variable support."""
    import os
    if 'IX_DESIGN_MCP_ROOT' in os.environ:
        root = Path(os.environ['IX_DESIGN_MCP_ROOT'])
        if root.exists():
            return root
    return Path(__file__).resolve().parent.parent

# Add project root to path
project_root = get_project_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import base simulation class
from tools.base_ix_simulation import BaseIXSimulation

# Import WAC templates (EXCHANGE-based, numerically stable at industrial scale)
from watertap_ix_transport.transport_core.wac_templates import (
    create_wac_na_phreeqc_input,
    create_wac_h_phreeqc_input  # Uses EXCHANGE model with H+ competition (Codex 019abbed)
)

# Import regeneration configuration
from tools.sac_simulation import RegenerationConfig

# Import schemas
from tools.sac_configuration import SACWaterComposition, SACVesselConfiguration

# Import centralized configuration
from tools.core_config import CONFIG

# Import empirical leakage overlay for two-layer architecture
from tools.empirical_leakage_overlay import (
    EmpiricalLeakageOverlay,
    CalibrationLoader,
    CalibrationParameters
)

logger = logging.getLogger(__name__)


class WACWaterComposition(SACWaterComposition):
    """Extended water composition for WAC with alkalinity focus"""
    # Alkalinity is already included via hco3_mg_l in base class
    # Add any WAC-specific validations here if needed
    pass


class WACVesselConfiguration(BaseModel):
    """WAC vessel configuration"""
    resin_type: str  # "WAC_Na" or "WAC_H"
    number_service: int
    number_standby: int
    diameter_m: float
    bed_depth_m: float
    bed_volume_L: float
    resin_volume_m3: float
    freeboard_m: float
    vessel_height_m: float
    bed_expansion_percent: float


class WACSimulationInput(BaseModel):
    """Input for WAC simulation"""
    water_analysis: WACWaterComposition
    vessel_configuration: WACVesselConfiguration
    target_hardness_mg_l_caco3: float = Field(default=5.0)
    target_alkalinity_mg_l_caco3: Optional[float] = Field(
        default=5.0,
        description="For H-form WAC, alkalinity breakthrough threshold"
    )
    full_data: bool = Field(default=False)
    regeneration_config: Dict[str, Any] = Field(...)
    
    @validator('target_alkalinity_mg_l_caco3')
    def validate_alkalinity_target(cls, v, values):
        """Alkalinity target only relevant for H-form WAC"""
        if 'vessel_configuration' in values:
            if values['vessel_configuration'].resin_type == 'WAC_H' and v is None:
                return 5.0  # Default for H-form
        return v


class WACPerformanceMetrics(BaseModel):
    """WAC-specific performance metrics with breakthrough and average values"""
    # Breakthrough metrics (worst case for design)
    breakthrough_ca_removal_percent: float
    breakthrough_mg_removal_percent: float
    breakthrough_hardness_removal_percent: float
    breakthrough_alkalinity_removal_percent: float
    
    # Average metrics (for operational estimates)
    avg_ca_removal_percent: float
    avg_mg_removal_percent: float
    avg_hardness_removal_percent: float
    avg_alkalinity_removal_percent: float
    
    # pH and CO2 statistics
    average_effluent_ph: float
    min_effluent_ph: float
    max_effluent_ph: float
    co2_generation_mg_l: float
    
    # Additional metrics
    active_sites_percent_final: Optional[float] = None  # For H-form
    temporary_hardness_removed_percent: Optional[float] = None
    permanent_hardness_removed_percent: Optional[float] = None


class WACSimulationOutput(BaseModel):
    """Output from WAC simulation"""
    status: str
    breakthrough_bv: float
    service_time_hours: float
    breakthrough_hardness_mg_l_caco3: float
    breakthrough_alkalinity_mg_l_caco3: Optional[float] = None
    breakthrough_reached: bool
    warnings: List[str]
    phreeqc_capacity_factor: float
    capacity_utilization_percent: float
    breakthrough_data: Dict[str, Any]
    performance_metrics: WACPerformanceMetrics
    simulation_details: Dict[str, Any]
    regeneration_results: Optional[Dict[str, Any]] = None
    total_cycle_time_hours: float


class BaseWACSimulation(BaseIXSimulation):
    """Base class for WAC simulations, inheriting common IX functionality"""
    
    def __init__(self):
        """Initialize WAC simulation."""
        super().__init__()  # Initialize PHREEQC engine from base class
    
    def _extract_final_resin_state(
        self,
        service_bv: float,
        vessel_config: Dict[str, Any],
        water_analysis: WACWaterComposition
    ) -> Dict[str, float]:
        """Extract final resin state after service run for regeneration"""
        # Get resin capacity
        bed_volume_L = vessel_config['bed_volume_L']
        
        if vessel_config['resin_type'] == 'WAC_Na':
            capacity_eq_L = CONFIG.WAC_NA_WORKING_CAPACITY
        else:  # WAC_H
            capacity_eq_L = CONFIG.WAC_H_WORKING_CAPACITY
            
        total_capacity_eq = capacity_eq_L * bed_volume_L
        
        # Calculate hardness loading
        ca_meq_L = water_analysis.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT
        mg_meq_L = water_analysis.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT
        hardness_meq_L = ca_meq_L + mg_meq_L
        
        # Estimate loading based on service BVs
        hardness_loaded_eq = hardness_meq_L * service_bv * bed_volume_L / 1000
        
        # Distribute between Ca and Mg based on feed ratio
        ca_fraction = ca_meq_L / hardness_meq_L if hardness_meq_L > 0 else 0.5
        mg_fraction = mg_meq_L / hardness_meq_L if hardness_meq_L > 0 else 0.5
        
        ca_eq = hardness_loaded_eq * ca_fraction
        mg_eq = hardness_loaded_eq * mg_fraction
        na_eq = max(0, total_capacity_eq - hardness_loaded_eq)
        
        # Convert to moles
        ca_mol = ca_eq / 2  # Ca is divalent
        mg_mol = mg_eq / 2  # Mg is divalent
        na_mol = na_eq      # Na is monovalent
        
        return {
            'ca_mol': ca_mol,
            'mg_mol': mg_mol,
            'na_mol': na_mol,
            'h_mol': 0,  # Assume fully loaded for Na-form, will be different for H-form
            'ca_equiv': ca_eq,
            'mg_equiv': mg_eq,
            'na_equiv': na_eq,
            'ca_fraction': ca_eq / total_capacity_eq if total_capacity_eq > 0 else 0,
            'mg_fraction': mg_eq / total_capacity_eq if total_capacity_eq > 0 else 0,
            'na_fraction': na_eq / total_capacity_eq if total_capacity_eq > 0 else 0,
            'total_sites_mol': total_capacity_eq  # For H-form surface calculations
        }
    
    def run_multi_stage_regeneration(
        self,
        initial_exchange_state: Dict[str, float],
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig,
        override_bv: Optional[float] = None
    ) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        """
        Run counter-current regeneration as staged equilibrations.
        Adapted from SAC for WAC-specific chemistry.
        """
        n_stages = regen_config.regeneration_stages
        cells = CONFIG.DEFAULT_CELLS  # Use optimized cell count
        
        # Get database path
        db_path = str(CONFIG.get_phreeqc_database())
        
        # Use override_bv for optimization iterations
        regenerant_bv = override_bv if override_bv is not None else regen_config.regenerant_bv
        
        # Calculate per-stage volumes
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
        slice_state = {
            'ca_mol': initial_exchange_state['ca_mol'] / n_stages,
            'mg_mol': initial_exchange_state['mg_mol'] / n_stages,
            'na_mol': initial_exchange_state['na_mol'] / n_stages,
            'h_mol': initial_exchange_state.get('h_mol', 0) / n_stages,
            'ca_equiv': initial_exchange_state['ca_equiv'] / n_stages,
            'mg_equiv': initial_exchange_state['mg_equiv'] / n_stages,
            'na_equiv': initial_exchange_state['na_equiv'] / n_stages,
            'ca_fraction': initial_exchange_state['ca_fraction'],
            'mg_fraction': initial_exchange_state['mg_fraction'],
            'na_fraction': initial_exchange_state['na_fraction'],
            'total_sites_mol': initial_exchange_state.get('total_sites_mol', 0) / n_stages
        }
        resin_states = [slice_state.copy() for _ in range(n_stages)]
        
        # Prepare regenerant based on type
        # For WAC_Na, we might use HCl or NaOH depending on the regeneration step
        # For WAC_H, we use acid (HCl or H2SO4)
        if regen_config.regenerant_type == "HCl":
            regenerant_type = "HCl"
            conc_mol_L = 0.5  # 0.5 N HCl
        elif regen_config.regenerant_type == "H2SO4":
            regenerant_type = "H2SO4"
            conc_mol_L = 0.5
        elif regen_config.regenerant_type == "NaOH":
            regenerant_type = "NaOH"
            conc_mol_L = 0.5  # 0.5 N NaOH
        elif regen_config.regenerant_type == "NaCl":
            # NaCl cannot regenerate WAC (unlike SAC) - convert to HCl
            # WAC requires acid to strip hardness, then NaOH to restore Na-form
            logger.warning("NaCl specified for WAC regeneration - using HCl instead")
            regenerant_type = "HCl"
            conc_mol_L = 0.5
        else:
            regenerant_type = "HCl"
            conc_mol_L = 0.5
        
        # Create fresh regenerant composition
        if regenerant_type == "HCl":
            fresh_regenerant = {
                'H': 0.0,  # Let PHREEQC calculate from charge balance
                'Cl': conc_mol_L * 1000,  # mmol/L
                'Ca': 0.0,
                'Mg': 0.0,
                'Na': 0.0,
                'temp': 25.0,
                'pH': -np.log10(conc_mol_L)
            }
        elif regenerant_type == "H2SO4":
            fresh_regenerant = {
                'H': 0.0,  # Let PHREEQC calculate from charge balance
                'SO4': conc_mol_L * 500,  # H2SO4 is diprotic
                'Ca': 0.0,
                'Mg': 0.0,
                'Na': 0.0,
                'temp': 25.0,
                'pH': -np.log10(conc_mol_L)
            }
        elif regenerant_type == "NaOH":
            fresh_regenerant = {
                'Na': conc_mol_L * 1000,  # mmol/L
                'Cl': 0.0,  # No chloride in NaOH
                'Ca': 0.0,
                'Mg': 0.0,
                'temp': 25.0,
                'pH': 14 + np.log10(conc_mol_L)  # High pH for NaOH
            }
        else:
            # Default to HCl
            fresh_regenerant = {
                'H': 0.0,
                'Cl': conc_mol_L * 1000,
                'Ca': 0.0,
                'Mg': 0.0,
                'Na': 0.0,
                'temp': 25.0,
                'pH': -np.log10(conc_mol_L)
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
                    db_path=db_path
                )
                
                # Run PHREEQC
                output, selected = self.engine.run_phreeqc(
                    phreeqc_input,
                    database=db_path
                )
                
                # Parse selected output
                selected_data = []
                if selected:
                    selected_data = self.engine.parse_selected_output(selected)
                
                # Extract results
                if not selected_data:
                    logger.warning(f"No selected output for stage {stage_num + 1}")
                    new_exchange = resin_states[stage_num]
                    spent_regenerant = regenerant
                else:
                    new_exchange = self._extract_exchange_state(selected_data, vessel_config)
                    spent_regenerant = self._extract_solution_composition(selected_data)
                
                # Update states
                resin_states[stage_num] = new_exchange
                
                # Correct for water hold-up between stages
                if stage_num > 0:
                    holdup_volume_L = bed_volume_L * 0.3 / n_stages
                    dilution_factor = effective_stage_volume_L / (effective_stage_volume_L + holdup_volume_L)
                    for ion in ['Na', 'Ca', 'Mg', 'Cl', 'H']:
                        if ion in spent_regenerant:
                            spent_regenerant[ion] *= dilution_factor
                
                regenerant = spent_regenerant
                
                # Track results
                stage_results.append({
                    'stage': n_stages - stage_num,
                    'na_fraction': new_exchange.get('na_fraction', 0),
                    'ca_fraction': new_exchange.get('ca_fraction', 0),
                    'mg_fraction': new_exchange.get('mg_fraction', 0),
                    'waste_tds': spent_regenerant.get('tds', 0),
                    'ca_in_waste': spent_regenerant.get('Ca', 0),
                    'mg_in_waste': spent_regenerant.get('Mg', 0),
                    'volume_L': effective_stage_volume_L
                })
                
            except Exception as e:
                logger.error(f"Stage {stage_num + 1} failed: {e}")
                raise RuntimeError(f"Multi-stage regeneration failed at stage {stage_num + 1}: {e}")
        
        # Calculate bed-average recovery
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
        tot_h_mol = sum(rs.get('h_mol', 0) for rs in resin_states)
        
        final_exchange = {
            'na_fraction': avg_na_fraction,
            'ca_fraction': avg_ca_fraction,
            'mg_fraction': avg_mg_fraction,
            'na_mol': tot_na_mol,
            'ca_mol': tot_ca_mol,
            'mg_mol': tot_mg_mol,
            'h_mol': tot_h_mol,
            'na_equiv': tot_na,
            'ca_equiv': tot_ca,
            'mg_equiv': tot_mg
        }
        
        logger.debug(f"Multi-stage regeneration complete: Na_fraction={avg_na_fraction:.3f}")
        
        return final_exchange, stage_results
    
    def run_regeneration(
        self,
        resin_state: Dict[str, float],
        vessel_config: Dict[str, Any],
        regen_config: RegenerationConfig
    ) -> Dict[str, Any]:
        """Run WAC regeneration simulation following SAC pattern."""
        logger.info(f"Starting WAC {vessel_config['resin_type']} regeneration")
        
        acid_regen_bv = 0.0
        caustic_regen_bv = 0.0

        # Handle WAC-specific two-step regeneration for Na-form
        if vessel_config['resin_type'] == 'WAC_Na':
            # WAC_Na requires two-step regeneration: acid then caustic
            bed_volume_L = vessel_config['bed_volume_L']
            hardness_eq = resin_state.get('ca_equiv', 0) + resin_state.get('mg_equiv', 0)
            if bed_volume_L <= 0:
                raise ValueError("Bed volume must be positive for regeneration calculations")

            # Convert stoichiometric requirement (eq) to chemical demand (g/L)
            acid_dose_g_per_L = (hardness_eq * 36.46 * 1.10) / bed_volume_L
            caustic_dose_g_per_L = (hardness_eq * 40.00 * 1.20) / bed_volume_L

            logger.info(
                "WAC_Na stoichiometry: %.3f eq hardness -> %.1f g/L acid, %.1f g/L caustic",
                hardness_eq,
                acid_dose_g_per_L,
                caustic_dose_g_per_L
            )

            # Step 1: Acid elution (HCl)
            logger.info("Step 1: Acid elution for WAC_Na")
            acid_config = RegenerationConfig(
                regenerant_type="HCl",
                concentration_percent=5.0,
                regenerant_dose_g_per_L=acid_dose_g_per_L,
                regeneration_stages=3,
                mode="staged_fixed",
                flow_rate_bv_hr=2.0,
                backwash_enabled=False,
                slow_rinse_bv=0.5,
                fast_rinse_bv=1.0
            )

            final_exchange_acid, stage_results_acid = self.run_multi_stage_regeneration(
                initial_exchange_state=resin_state,
                vessel_config=vessel_config,
                regen_config=acid_config
            )
            acid_regen_bv = acid_config.regenerant_bv

            # Step 2: Caustic conversion (NaOH)
            logger.info("Step 2: Caustic conversion for WAC_Na")
            caustic_config = RegenerationConfig(
                regenerant_type="NaOH",
                concentration_percent=5.0,
                regenerant_dose_g_per_L=caustic_dose_g_per_L,
                regeneration_stages=3,
                mode="staged_fixed",
                flow_rate_bv_hr=2.0,
                backwash_enabled=False,
                slow_rinse_bv=0.5,
                fast_rinse_bv=1.0
            )

            # Use the state after acid elution as input
            final_exchange, stage_results_caustic = self.run_multi_stage_regeneration(
                initial_exchange_state=final_exchange_acid,
                vessel_config=vessel_config,
                regen_config=caustic_config
            )
            caustic_regen_bv = caustic_config.regenerant_bv

            # Combine stage results
            stage_results = stage_results_acid + stage_results_caustic
            acid_total_g = acid_config.regenerant_dose_g_per_L * bed_volume_L
            caustic_total_g = caustic_config.regenerant_dose_g_per_L * bed_volume_L
            acid_regen_time = (
                (acid_config.regenerant_bv / acid_config.flow_rate_bv_hr)
                if acid_config.flow_rate_bv_hr else 0
            )
            caustic_regen_time = (
                (caustic_config.regenerant_bv / caustic_config.flow_rate_bv_hr)
                if caustic_config.flow_rate_bv_hr else 0
            )
            additional_rinse_time = sum(
                (
                    cfg.slow_rinse_bv + cfg.fast_rinse_bv
                ) / cfg.flow_rate_bv_hr if cfg.flow_rate_bv_hr else 0
                for cfg in (acid_config, caustic_config)
            )
            total_regenerant_g = acid_total_g + caustic_total_g
            regen_time_hours = acid_regen_time + caustic_regen_time + additional_rinse_time
        
        else:  # WAC_H - single acid regeneration
            logger.info("Single-step acid regeneration for WAC_H")

            final_exchange, stage_results = self.run_multi_stage_regeneration(
                initial_exchange_state=resin_state,
                vessel_config=vessel_config,
                regen_config=regen_config
            )

            bed_volume_L = vessel_config['bed_volume_L']
            acid_regen_bv = regen_config.regenerant_bv

        # Calculate regeneration metrics
        initial_ca = resin_state.get('ca_mol', 0)
        initial_mg = resin_state.get('mg_mol', 0)
        
        final_ca = final_exchange.get('ca_mol', 0)
        final_mg = final_exchange.get('mg_mol', 0)
        
        ca_eluted = initial_ca - final_ca
        mg_eluted = initial_mg - final_mg
        
        ca_eluted_percent = (ca_eluted / initial_ca * 100) if initial_ca > 0 else 0
        mg_eluted_percent = (mg_eluted / initial_mg * 100) if initial_mg > 0 else 0
        
        # Calculate regenerant consumption
        if vessel_config['resin_type'] == 'WAC_Na':
            acid_dose_g_per_L = acid_total_g / bed_volume_L if bed_volume_L > 0 else 0
            caustic_dose_g_per_L = caustic_total_g / bed_volume_L if bed_volume_L > 0 else 0
        else:  # WAC_H
            # Single acid step
            if regen_config.regenerant_type == "H2SO4":
                total_regenerant_g = regen_config.regenerant_bv * bed_volume_L * 0.5 * 49.04
            else:
                total_regenerant_g = regen_config.regenerant_bv * bed_volume_L * 0.5 * 36.46
            regen_time_hours = regen_config.regenerant_bv / regen_config.flow_rate_bv_hr
            acid_dose_g_per_L = total_regenerant_g / bed_volume_L if bed_volume_L > 0 else 0
            caustic_dose_g_per_L = 0.0

        # Calculate waste volume and TDS
        waste_volume_L = sum(sr['volume_L'] for sr in stage_results)
        max_tds = max(sr.get('waste_tds', 0) for sr in stage_results) if stage_results else 0

        return {
            'status': 'success',
            'final_na_fraction': final_exchange.get('na_fraction', 0),
            'final_h_fraction': 1 - final_exchange.get('na_fraction', 0) - final_exchange.get('ca_fraction', 0) - final_exchange.get('mg_fraction', 0),
            'ca_eluted_percent': ca_eluted_percent,
            'mg_eluted_percent': mg_eluted_percent,
            'regenerant_consumed_g': total_regenerant_g,
            'regenerant_consumed_g_per_L': total_regenerant_g / bed_volume_L if bed_volume_L > 0 else 0,
            'waste_volume_L': waste_volume_L,
            'waste_volume_bv': waste_volume_L / bed_volume_L if bed_volume_L > 0 else 0,
            'waste_tds_mg_L': max_tds,
            'regeneration_time_hours': regen_time_hours,
            'acid_dose_g_per_L': acid_dose_g_per_L,
            'caustic_dose_g_per_L': caustic_dose_g_per_L,
            'acid_regenerant_bv': acid_regen_bv,
            'caustic_regenerant_bv': caustic_regen_bv
        }
    
    def _calculate_total_x(self, exchange_state: Dict[str, float]) -> float:
        """Calculate total X from individual species (in equivalents)"""
        ca_equiv = exchange_state.get('ca_mol', 0) * 2  # CaX2: 2 equiv per mol
        mg_equiv = exchange_state.get('mg_mol', 0) * 2  # MgX2: 2 equiv per mol
        na_equiv = exchange_state.get('na_mol', 0)      # NaX: 1 equiv per mol
        return ca_equiv + mg_equiv + na_equiv
    
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
        """Build PHREEQC input for WAC regeneration stage"""
        
        resin_type = vessel_config['resin_type']
        bed_volume_L = vessel_config['bed_volume_L']
        
        if resin_type == 'WAC_Na':
            # WAC Na-form uses EXCHANGE blocks with enhanced selectivity
            ca_mol = exchange_state.get('ca_mol', 0)
            mg_mol = exchange_state.get('mg_mol', 0)
            na_mol = exchange_state.get('na_mol', 0)
            
            # Calculate total X in equivalents
            total_x_equiv = self._calculate_total_x(exchange_state)
            
            # Safety check
            assert total_x_equiv > 0, f"Exchange feed is empty – check stage {stage_num + 1} input"
            
            # Build solution block based on regenerant type
            # For HCl, don't specify pH to avoid conflicts
            if regenerant_composition['Cl'] > 0 and regenerant_composition['Na'] == 0:
                # HCl solution - let PHREEQC calculate pH from charge balance
                solution_block = f"""
SOLUTION 1 Regenerant
    units     mmol/L
    temp      {regenerant_composition['temp']}
    Na        {regenerant_composition['Na']}
    Ca        {regenerant_composition['Ca']}
    Mg        {regenerant_composition['Mg']}
    Cl        {regenerant_composition['Cl']} charge
    water     {volume_L} kg"""
            else:
                # NaOH or other solutions - can specify pH
                solution_block = f"""
SOLUTION 1 Regenerant
    units     mmol/L
    temp      {regenerant_composition['temp']}
    pH        {regenerant_composition['pH']}
    Na        {regenerant_composition['Na']}
    Ca        {regenerant_composition['Ca']}
    Mg        {regenerant_composition['Mg']}
    Cl        {regenerant_composition['Cl']}
    water     {volume_L} kg"""
            
            phreeqc_input = f"""
DATABASE {db_path}
TITLE Stage {n_stages - stage_num} - WAC Na Regeneration

# Define HX exchange species for WAC (not in standard database)
EXCHANGE_SPECIES
    # HX reaction - H+ has high selectivity
    H+ + X- = HX
        log_k {CONFIG.WAC_LOGK_H_NA}  # H+ >> Na+

{solution_block}

EXCHANGE 1 Resin state (in moles)
    CaX2      {ca_mol}
    MgX2      {mg_mol}
    NaX       {na_mol}
    HX        {exchange_state.get('h_mol', 0)}
    -equilibrate 1

PRINT
    -high_precision true

SELECTED_OUTPUT 1
    -file transport.sel
    -reset false
    -high_precision true
    -totals Ca Mg Na K Cl C(4) H
    -molalities CaX2 MgX2 NaX HX
    -ph true

USER_PUNCH
    -headings Stage Total_Ca_mmol Total_Mg_mmol Total_Na_mmol Total_H_mmol CaX2_mol MgX2_mol NaX_mol HX_mol pH TDS_mg/L
    -start
    10 REM Stage number
    20 PUNCH {n_stages - stage_num}
    30 REM Total dissolved species in mmol/L
    40 PUNCH TOT("Ca") * 1000
    50 PUNCH TOT("Mg") * 1000
    60 PUNCH TOT("Na") * 1000
    65 PUNCH TOT("H") * 1000
    70 REM Exchange composition in moles
    80 PUNCH MOL("CaX2") * {volume_L}
    90 PUNCH MOL("MgX2") * {volume_L}
    100 PUNCH MOL("NaX") * {volume_L}
    110 PUNCH MOL("HX") * {volume_L}
    115 PUNCH -LA("H+")
    120 REM TDS estimation
    130 tds = (TOT("Ca")*40.08 + TOT("Mg")*24.31 + TOT("Na")*22.99 + TOT("Cl")*35.45)*1000
    140 PUNCH tds
    -end

END
"""
        
        else:  # WAC_H uses SURFACE blocks
            # For WAC_H, we track surface sites
            total_sites = exchange_state.get('total_sites_mol', 0)
            ca_bound = exchange_state.get('ca_mol', 0)
            mg_bound = exchange_state.get('mg_mol', 0)
            na_bound = exchange_state.get('na_mol', 0)
            h_bound = exchange_state.get('h_mol', total_sites)  # Default to fully protonated
            
            # Calculate fractions for surface initialization
            ca_frac = ca_bound / total_sites if total_sites > 0 else 0
            mg_frac = mg_bound / total_sites if total_sites > 0 else 0
            na_frac = na_bound / total_sites if total_sites > 0 else 0
            h_frac = h_bound / total_sites if total_sites > 0 else 1.0
            
            phreeqc_input = f"""
DATABASE {db_path}
TITLE Stage {n_stages - stage_num} - WAC H Regeneration

# Define surface master species for carboxylic acid
SURFACE_MASTER_SPECIES
    Rcoo    RcooH

# Surface reactions for WAC H-form
SURFACE_SPECIES
    # Identity reaction
    RcooH = RcooH
        log_k 0.0
    
    # Deprotonation (pKa = 4.8)
    RcooH = Rcoo- + H+
        log_k -{CONFIG.WAC_PKA}
    
    # Ca complexation (2:1)
    2Rcoo- + Ca+2 = (Rcoo)2Ca
        log_k 3.0
    
    # Mg complexation (2:1)
    2Rcoo- + Mg+2 = (Rcoo)2Mg
        log_k 2.8
    
    # Na complexation (weak)
    Rcoo- + Na+ = RcooNa
        log_k -1.0

SOLUTION 1 Regenerant (Acid)
    units     mmol/L
    temp      {regenerant_composition['temp']}
    pH        {regenerant_composition['pH']}
    Na        {regenerant_composition['Na']}
    Ca        {regenerant_composition['Ca']}
    Mg        {regenerant_composition['Mg']}
    Cl        {regenerant_composition['Cl']}
    water     {volume_L} kg

# Initialize surface with current state
SURFACE 1 Current resin state
    RcooH     {h_frac * total_sites} {volume_L} 1.0
    Rcoo-     {(1 - h_frac) * total_sites} {volume_L} 1.0
    (Rcoo)2Ca {ca_frac * total_sites / 2} {volume_L} 1.0
    (Rcoo)2Mg {mg_frac * total_sites / 2} {volume_L} 1.0
    RcooNa    {na_frac * total_sites} {volume_L} 1.0
    -equilibrate solution 1
    -no_edl

PRINT
    -high_precision true

SELECTED_OUTPUT
    -file transport.sel
    -reset false
    -step true
    -solution true
    -surface true
    -totals Ca Mg Na K Cl C(4) Rcoo
    -molalities RcooH Rcoo- (Rcoo)2Ca (Rcoo)2Mg RcooNa

USER_PUNCH
    -headings Stage Total_Ca_mmol Total_Mg_mmol Total_Na_mmol RcooH_mol Ca_bound_mol Mg_bound_mol TDS_mg/L
    -start
    10 REM Stage number
    20 PUNCH {n_stages - stage_num}
    30 REM Total dissolved species in mmol/L
    40 PUNCH TOT("Ca") * 1000
    50 PUNCH TOT("Mg") * 1000
    60 PUNCH TOT("Na") * 1000
    70 REM Surface composition in moles
    80 PUNCH MOL("RcooH") * {volume_L}
    90 PUNCH MOL("(Rcoo)2Ca") * {volume_L}
    100 PUNCH MOL("(Rcoo)2Mg") * {volume_L}
    110 REM TDS estimation
    120 tds = (TOT("Ca")*40.08 + TOT("Mg")*24.31 + TOT("Na")*22.99 + TOT("Cl")*35.45)*1000
    130 PUNCH tds
    -end

END
"""
        
        return phreeqc_input
    
    def _extract_exchange_state(self, selected_data: List[Dict], vessel_config: Dict[str, Any]) -> Dict[str, float]:
        """Extract exchange state from PHREEQC output for WAC"""
        
        if not selected_data:
            raise ValueError("No selected output data to extract exchange state")
        
        # Get the last row of data
        last_row = selected_data[-1]
        resin_type = vessel_config['resin_type']
        bed_volume_L = vessel_config['bed_volume_L']
        
        if resin_type == 'WAC_Na':
            # Extract from EXCHANGE blocks
            ca_mol = last_row.get('CaX2_mol', 0)
            mg_mol = last_row.get('MgX2_mol', 0)
            na_mol = last_row.get('NaX_mol', 0)
            h_mol = last_row.get('HX_mol', 0)
            
            # Calculate equivalents (Ca and Mg are divalent)
            ca_equiv = ca_mol * 2
            mg_equiv = mg_mol * 2
            na_equiv = na_mol
            h_equiv = h_mol
            
            total_equiv = ca_equiv + mg_equiv + na_equiv + h_equiv
            
            # Calculate fractions
            ca_fraction = ca_equiv / total_equiv if total_equiv > 0 else 0
            mg_fraction = mg_equiv / total_equiv if total_equiv > 0 else 0
            na_fraction = na_equiv / total_equiv if total_equiv > 0 else 0
            h_fraction = h_equiv / total_equiv if total_equiv > 0 else 0
            
            # Total sites in mol (for consistency)
            total_sites_mol = total_equiv
            
        else:  # WAC_H
            # Extract from SURFACE blocks
            rcooh_mol = last_row.get('RcooH_mol', 0)
            ca_bound_mol = last_row.get('(Rcoo)2Ca_mol', 0)
            mg_bound_mol = last_row.get('(Rcoo)2Mg_mol', 0)
            
            # Calculate actual ion moles (2 sites per Ca/Mg)
            ca_mol = ca_bound_mol
            mg_mol = mg_bound_mol
            na_mol = 0  # WAC_H doesn't retain Na significantly
            h_mol = rcooh_mol
            
            # Calculate total sites
            total_sites_mol = rcooh_mol + 2*ca_bound_mol + 2*mg_bound_mol
            
            # Calculate equivalents
            ca_equiv = ca_mol * 2
            mg_equiv = mg_mol * 2
            na_equiv = na_mol
            h_equiv = h_mol
            
            total_equiv = ca_equiv + mg_equiv + na_equiv + h_equiv
            
            # Calculate fractions
            ca_fraction = ca_equiv / total_equiv if total_equiv > 0 else 0
            mg_fraction = mg_equiv / total_equiv if total_equiv > 0 else 0
            na_fraction = na_equiv / total_equiv if total_equiv > 0 else 0
            h_fraction = h_equiv / total_equiv if total_equiv > 0 else 0
        
        return {
            'ca_mol': ca_mol,
            'mg_mol': mg_mol,
            'na_mol': na_mol,
            'h_mol': h_mol,
            'ca_equiv': ca_equiv,
            'mg_equiv': mg_equiv,
            'na_equiv': na_equiv,
            'h_equiv': h_equiv,
            'ca_fraction': ca_fraction,
            'mg_fraction': mg_fraction,
            'na_fraction': na_fraction,
            'h_fraction': h_fraction,
            'total_sites_mol': total_sites_mol
        }
    
    def _extract_solution_composition(self, selected_data: List[Dict]) -> Dict[str, float]:
        """Extract solution composition from PHREEQC output"""
        
        if not selected_data:
            return {}
        
        # Get the last row
        last_row = selected_data[-1]
        
        # Extract concentrations in mmol/L
        return {
            'Ca': last_row.get('Total_Ca_mmol', 0),
            'Mg': last_row.get('Total_Mg_mmol', 0),
            'Na': last_row.get('Total_Na_mmol', 0),
            'Cl': last_row.get('Total_Ca_mmol', 0) * 2 + last_row.get('Total_Mg_mmol', 0) * 2 + last_row.get('Total_Na_mmol', 0),  # Charge balance
            'TDS_mg_L': last_row.get('TDS_mg/L', 0),
            'pH': 7.0,  # Default, could be extracted if needed
            'temp': 25  # Default temperature
        }
    
    def _calculate_performance_metrics(
        self, 
        breakthrough_data: Dict[str, np.ndarray],
        water_analysis: WACWaterComposition,
        breakthrough_bv: float
    ) -> WACPerformanceMetrics:
        """Calculate WAC-specific performance metrics at breakthrough and average."""
        # Get feed concentrations
        feed_ca = water_analysis.ca_mg_l
        feed_mg = water_analysis.mg_mg_l
        # Calculate hardness as CaCO3 using proper conversion factors
        feed_hardness = feed_ca * 2.5 + feed_mg * 4.1
        feed_alkalinity = water_analysis.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT * CONFIG.ALKALINITY_EQUIV_WEIGHT
        
        # Get effluent data arrays
        ca_eff = breakthrough_data.get('Ca_mg/L', np.array([]))
        mg_eff = breakthrough_data.get('Mg_mg/L', np.array([]))
        hardness_eff = breakthrough_data.get('Hardness_mg/L', np.array([]))
        # Handle both old and new alkalinity keys
        alk_eff = breakthrough_data.get('Alk_CaCO3_mg/L', breakthrough_data.get('Alk_mg/L', np.array([])))
        ph_eff = breakthrough_data.get('pH', np.array([]))
        co2_eff = breakthrough_data.get('CO2_mg/L', np.array([]))
        bvs = breakthrough_data.get('BV', breakthrough_data.get('bv', np.array([])))
        
        # Get breakthrough index
        breakthrough_idx = self._index_at_bv(breakthrough_data, breakthrough_bv)
        
        # Calculate AT BREAKTHROUGH removals (for design - worst case)
        if len(ca_eff) > 0 and feed_ca > 0:
            ca_at_breakthrough = ca_eff[breakthrough_idx] if breakthrough_idx < len(ca_eff) else ca_eff[-1]
            ca_removal = 100 * (1 - ca_at_breakthrough / feed_ca)
            ca_removal = max(0, min(100, ca_removal))  # Clamp to [0, 100]
        else:
            ca_removal = 0
        
        if len(mg_eff) > 0 and feed_mg > 0:
            mg_at_breakthrough = mg_eff[breakthrough_idx] if breakthrough_idx < len(mg_eff) else mg_eff[-1]
            mg_removal = 100 * (1 - mg_at_breakthrough / feed_mg)
            mg_removal = max(0, min(100, mg_removal))
        else:
            mg_removal = 0
        
        if len(hardness_eff) > 0 and feed_hardness > 0:
            hardness_at_breakthrough = hardness_eff[breakthrough_idx] if breakthrough_idx < len(hardness_eff) else hardness_eff[-1]
            hardness_removal = 100 * (1 - hardness_at_breakthrough / feed_hardness)
            hardness_removal = max(0, min(100, hardness_removal))
        else:
            hardness_removal = 0
        
        if len(alk_eff) > 0 and feed_alkalinity > 0:
            # Handle negative alkalinity at low pH by treating as zero
            alk_at_breakthrough = max(0, alk_eff[breakthrough_idx] if breakthrough_idx < len(alk_eff) else alk_eff[-1])
            alk_removal = 100 * (1 - alk_at_breakthrough / feed_alkalinity)
            alk_removal = max(0, min(100, alk_removal))
        else:
            alk_removal = 0
        
        # Calculate BV-WEIGHTED AVERAGE removals (for operations/mass balance)
        avg_ca_removal = 0
        avg_mg_removal = 0
        avg_hardness_removal = 0
        avg_alk_removal = 0
        
        if len(bvs) > 0 and breakthrough_idx > 0:
            # Use trapezoidal integration for BV-weighted average
            bvs_to_breakthrough = bvs[:breakthrough_idx+1]
            
            if len(ca_eff) > breakthrough_idx and feed_ca > 0:
                ca_to_breakthrough = ca_eff[:breakthrough_idx+1]
                # Filter out None values before integration
                ca_valid = np.array([x if x is not None else 0 for x in ca_to_breakthrough])
                bvs_valid = np.array([x if x is not None else 0 for x in bvs_to_breakthrough])
                avg_ca = np.trapz(ca_valid, bvs_valid) / breakthrough_bv if breakthrough_bv > 0 else 0
                avg_ca_removal = 100 * (1 - avg_ca / feed_ca)
                avg_ca_removal = max(0, min(100, avg_ca_removal))
            
            if len(mg_eff) > breakthrough_idx and feed_mg > 0:
                mg_to_breakthrough = mg_eff[:breakthrough_idx+1]
                # Filter out None values before integration
                mg_valid = np.array([x if x is not None else 0 for x in mg_to_breakthrough])
                bvs_valid = np.array([x if x is not None else 0 for x in bvs_to_breakthrough])
                avg_mg = np.trapz(mg_valid, bvs_valid) / breakthrough_bv if breakthrough_bv > 0 else 0
                avg_mg_removal = 100 * (1 - avg_mg / feed_mg)
                avg_mg_removal = max(0, min(100, avg_mg_removal))
            
            if len(hardness_eff) > breakthrough_idx and feed_hardness > 0:
                hardness_to_breakthrough = hardness_eff[:breakthrough_idx+1]
                # Filter out None values before integration
                hardness_valid = np.array([x if x is not None else 0 for x in hardness_to_breakthrough])
                bvs_valid = np.array([x if x is not None else 0 for x in bvs_to_breakthrough])
                avg_hardness = np.trapz(hardness_valid, bvs_valid) / breakthrough_bv if breakthrough_bv > 0 else 0
                avg_hardness_removal = 100 * (1 - avg_hardness / feed_hardness)
                avg_hardness_removal = max(0, min(100, avg_hardness_removal))
            
            if len(alk_eff) > breakthrough_idx and feed_alkalinity > 0:
                # Filter out None values and treat negative alkalinity as zero
                alk_to_breakthrough = alk_eff[:breakthrough_idx+1]
                alk_valid = np.array([max(0, x) if x is not None else 0 for x in alk_to_breakthrough])
                bvs_valid = np.array([x if x is not None else 0 for x in bvs_to_breakthrough])
                avg_alk = np.trapz(alk_valid, bvs_valid) / breakthrough_bv if breakthrough_bv > 0 else 0
                avg_alk_removal = 100 * (1 - avg_alk / feed_alkalinity)
                avg_alk_removal = max(0, min(100, avg_alk_removal))
        
        # pH statistics - filter out None values
        if len(ph_eff) > 0:
            ph_valid = [x for x in ph_eff if x is not None]
            if len(ph_valid) > 0:
                avg_ph = np.mean(ph_valid)
                min_ph = np.min(ph_valid)
                max_ph = np.max(ph_valid)
            else:
                avg_ph = min_ph = max_ph = 7.0
        else:
            avg_ph = min_ph = max_ph = 7.0
        
        # CO2 generation - filter out None values
        if len(co2_eff) > 0:
            co2_valid = [x for x in co2_eff if x is not None]
            avg_co2 = np.mean(co2_valid) if len(co2_valid) > 0 else 0
        else:
            avg_co2 = 0
        
        # Active sites (for H-form) - from USER_PUNCH if available
        active_sites = breakthrough_data.get('Active_Sites_%', None)
        final_active = float(active_sites[-1]) if active_sites is not None and len(active_sites) > 0 else None
        
        # Temporary vs permanent hardness
        temp_hardness = min(feed_hardness, feed_alkalinity)
        perm_hardness = max(0, feed_hardness - feed_alkalinity)
        
        # For WAC resins, permanent hardness cannot be removed
        # Calculate actual hardness removal based on temporary hardness only
        if perm_hardness > 0:
            # Expected effluent hardness is at least the permanent hardness
            expected_hardness_removal = (temp_hardness / feed_hardness) * 100 if feed_hardness > 0 else 0
            # Use the lower of calculated or expected removal
            hardness_removal = min(hardness_removal, expected_hardness_removal)
            avg_hardness_removal = min(avg_hardness_removal, expected_hardness_removal)
        
        # Temporary hardness removal based on alkalinity at breakthrough
        temp_removal = alk_removal if temp_hardness > 0 else 0
        perm_removal = 0  # WAC cannot remove permanent hardness
        
        return WACPerformanceMetrics(
            # Breakthrough metrics (for design)
            breakthrough_ca_removal_percent=ca_removal,
            breakthrough_mg_removal_percent=mg_removal,
            breakthrough_hardness_removal_percent=hardness_removal,
            breakthrough_alkalinity_removal_percent=alk_removal,
            # Average metrics (for operations)
            avg_ca_removal_percent=avg_ca_removal,
            avg_mg_removal_percent=avg_mg_removal,
            avg_hardness_removal_percent=avg_hardness_removal,
            avg_alkalinity_removal_percent=avg_alk_removal,
            # pH and CO2 stats
            average_effluent_ph=avg_ph,
            min_effluent_ph=min_ph,
            max_effluent_ph=max_ph,
            co2_generation_mg_l=avg_co2,
            # Additional metrics
            active_sites_percent_final=final_active,
            temporary_hardness_removed_percent=temp_removal,
            permanent_hardness_removed_percent=perm_removal
        )


class WacNaSimulation(BaseWACSimulation):
    """Simulation for Na-form WAC resins"""
    
    def run_simulation(self, input_data: WACSimulationInput) -> WACSimulationOutput:
        """Run WAC Na-form simulation."""
        water = input_data.water_analysis
        vessel = input_data.vessel_configuration
        target_hardness = input_data.target_hardness_mg_l_caco3

        logger.info("Starting WAC Na-form simulation")

        service_vessels = max(vessel.number_service, 1)
        total_flow_m3_hr = water.flow_m3_hr
        if service_vessels > 1:
            flow_per_vessel_m3_hr = total_flow_m3_hr / service_vessels
            logger.info(
                "Distributing %.2f m3/hr across %d service vessels (%.2f m3/hr each)",
                total_flow_m3_hr,
                service_vessels,
                flow_per_vessel_m3_hr
            )
            water = water.model_copy(update={"flow_m3_hr": flow_per_vessel_m3_hr})
        else:
            flow_per_vessel_m3_hr = total_flow_m3_hr

        # Check TDS and recommend Pitzer database if needed
        tds_g_l = (
            water.ca_mg_l + water.mg_mg_l + water.na_mg_l +
            water.k_mg_l + water.nh4_mg_l +
            getattr(water, 'cl_mg_l', 0) +
            water.so4_mg_l + water.hco3_mg_l
        ) / 1000.0
        requires_pitzer, pitzer_msg = CONFIG.check_tds_for_pitzer(tds_g_l)
        if requires_pitzer:
            logger.warning(pitzer_msg)

        # Validate water composition
        self._validate_water_composition(water.model_dump())
        
        # Calculate dynamic max_bv based on hardness loading
        ca_meq_L = water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT
        mg_meq_L = water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT
        hardness_meq_L = ca_meq_L + mg_meq_L
        
        max_bv = self._calculate_dynamic_max_bv(
            loading_meq_L=hardness_meq_L,
            capacity_eq_L=CONFIG.WAC_NA_WORKING_CAPACITY,
            buffer_factor=1.2,
            min_bv=200
        )
        
        logger.info(f"Dynamic max_bv calculated: {max_bv} (hardness loading: {hardness_meq_L:.2f} meq/L)")
        
        # Create PHREEQC input with dynamic max_bv
        phreeqc_input = create_wac_na_phreeqc_input(
            water_composition=water.model_dump(),
            vessel_config=vessel.model_dump(),
            cells=CONFIG.DEFAULT_CELLS,
            max_bv=max_bv,
            enable_enhancements=CONFIG.ENABLE_IONIC_STRENGTH_CORRECTION or CONFIG.ENABLE_TEMPERATURE_CORRECTION,
            capacity_factor=vessel.capacity_factor if hasattr(vessel, 'capacity_factor') else 1.0
        )
        
        # Run PHREEQC
        try:
            output, selected_output = self.engine.run_phreeqc(phreeqc_input)
        except Exception as e:
            error_response = self._handle_phreeqc_error(e, {
                'resin_type': 'WAC_Na',
                'water': water.model_dump(),
                'max_bv': max_bv
            })
            return WACSimulationOutput(
                status=error_response['status'],
                breakthrough_bv=error_response['breakthrough_bv'],
                service_time_hours=error_response['service_time_hours'],
                breakthrough_hardness_mg_l_caco3=target_hardness,
                breakthrough_reached=error_response['breakthrough_reached'],
                warnings=error_response['warnings'],
                phreeqc_capacity_factor=0,
                capacity_utilization_percent=error_response['capacity_utilization_percent'],
                breakthrough_data=error_response['breakthrough_data'],
                performance_metrics=WACPerformanceMetrics(
                    # Breakthrough metrics (at target hardness)
                    breakthrough_ca_removal_percent=0,
                    breakthrough_mg_removal_percent=0,
                    breakthrough_hardness_removal_percent=0,
                    breakthrough_alkalinity_removal_percent=0,
                    # Average metrics (over service cycle)
                    avg_ca_removal_percent=0,
                    avg_mg_removal_percent=0,
                    avg_hardness_removal_percent=0,
                    avg_alkalinity_removal_percent=0,
                    # pH and CO2 statistics
                    average_effluent_ph=7.0,
                    min_effluent_ph=7.0,
                    max_effluent_ph=7.0,
                    co2_generation_mg_l=0
                ),
                simulation_details=error_response['simulation_details'],
                total_cycle_time_hours=0
            )

        # Extract breakthrough data with equilibration filtering
        breakthrough_data = self._extract_breakthrough_data_filtered(selected_output)

        # =====================================================================
        # LAYER 2: Apply empirical leakage overlay
        # PHREEQC gives thermodynamic equilibrium (near-zero leakage).
        # Real systems show 0.5-5 mg/L leakage due to incomplete regeneration,
        # TDS effects, and kinetic limitations.
        # This overlay matches industry projection software (WAVE, PRSM).
        # =====================================================================
        try:
            # Load calibration parameters for WAC_Na
            cal_loader = CalibrationLoader()
            cal_params = cal_loader.load('default', 'WAC_Na')

            # Calculate feed properties for overlay
            feed_hardness_caco3 = water.ca_mg_l * 2.5 + water.mg_mg_l * 4.1
            feed_tds = (
                water.ca_mg_l + water.mg_mg_l + water.na_mg_l +
                water.k_mg_l + water.nh4_mg_l +
                getattr(water, 'cl_mg_l', 0) +
                water.so4_mg_l + water.hco3_mg_l
            )

            # Create overlay and apply
            overlay = EmpiricalLeakageOverlay(cal_params)
            overlay_result = overlay.calculate_empirical_leakage(
                feed_hardness_mg_l_caco3=feed_hardness_caco3,
                feed_tds_mg_l=feed_tds,
                temperature_c=water.temperature_c if hasattr(water, 'temperature_c') else 25.0,
                phreeqc_leakage_mg_l=0.0,  # PHREEQC returns ~0 for equilibrium
                resin_type='WAC_Na'
            )

            # Apply overlay to breakthrough data
            breakthrough_data = overlay.apply_to_breakthrough_data(
                breakthrough_data=breakthrough_data,
                feed_composition=water.model_dump(),
                resin_type='WAC_Na'
            )

            logger.info(f"Empirical leakage overlay applied: {overlay_result.hardness_leakage_mg_l_caco3:.2f} mg/L as CaCO3")
            for note in overlay_result.model_notes[:3]:  # Log first 3 notes
                logger.debug(f"  {note}")

        except Exception as e:
            logger.warning(f"Empirical leakage overlay failed, using raw PHREEQC results: {e}")

        # Find breakthrough point (hardness-based for Na-form)
        # Use shared detection method with hardness > target criterion
        criteria = [
            ('Hardness_CaCO3', target_hardness, 'gt'),
            ('Hardness_mg/L', target_hardness, 'gt')  # Fallback if header differs
        ]

        breakthrough_bv, breakthrough_reached, reason = self._detect_breakthrough(
            breakthrough_data, criteria
        )

        if breakthrough_reached:
            logger.info(f"WAC Na breakthrough at {breakthrough_bv:.1f} BV ({reason})")
        else:
            logger.warning(f"Target hardness {target_hardness} mg/L not reached in {max_bv} BV")
        
        # Calculate service time
        flow_rate_m3_hr = flow_per_vessel_m3_hr
        bed_volume_m3 = vessel.bed_volume_L / 1000
        service_time_hours = breakthrough_bv * bed_volume_m3 / flow_rate_m3_hr if flow_rate_m3_hr > 0 else 0
        
        # Calculate performance metrics
        performance_metrics = self._calculate_performance_metrics(breakthrough_data, water, breakthrough_bv)
        
        # Calculate capacity utilization (breakthrough-based, like SAC)
        # Formula: (actual BV at breakthrough) / (theoretical BV) * 100
        # This approach caps at ~100% and measures actual utilization
        hardness_meq_L = (water.ca_mg_l / CONFIG.CA_EQUIV_WEIGHT +
                         water.mg_mg_l / CONFIG.MG_EQUIV_WEIGHT)  # meq/L
        # theoretical_bv = (capacity in meq/L) / (feed hardness in meq/L)
        theoretical_bv = (CONFIG.WAC_NA_WORKING_CAPACITY * 1000) / hardness_meq_L if hardness_meq_L > 0 else 0
        capacity_utilization = (breakthrough_bv / theoretical_bv * 100) if theoretical_bv > 0 else 0
        
        # Apply smart sampling to reduce data size
        sampled_data = self._smart_sample_breakthrough_curves(breakthrough_data, max_points=60)
        
        # Log summary
        self._log_simulation_summary({
            'status': "success" if breakthrough_reached else "warning",
            'breakthrough_bv': breakthrough_bv,
            'service_time_hours': service_time_hours,
            'breakthrough_reached': breakthrough_reached,
            'warnings': [] if breakthrough_reached else ["Breakthrough not reached within simulation time"]
        }, 'WAC_Na')
        
        # Get final hardness for output
        hardness_key = 'Hardness_CaCO3' if 'Hardness_CaCO3' in breakthrough_data else 'Hardness_mg/L'
        final_hardness = breakthrough_data.get(hardness_key, np.array([]))
        final_hardness_value = float(final_hardness[-1]) if len(final_hardness) > 0 else target_hardness
        
        # Run regeneration simulation for WAC_Na
        # Extract resin state after service
        resin_state = self._extract_final_resin_state(
            service_bv=breakthrough_bv,
            vessel_config=vessel.model_dump(),
            water_analysis=water
        )
        
        from tools.sac_simulation import RegenerationConfig

        try:
            # WAC_Na uses two-step regeneration: HCl (acid) + NaOH (caustic)
            # The run_regeneration method handles this automatically for WAC_Na
            regen_results = self.run_regeneration(
                resin_state=resin_state,
                vessel_config=vessel.model_dump(),
                regen_config=RegenerationConfig(
                    regenerant_type="HCl",  # Primary regenerant (followed by NaOH for Na-form)
                    concentration_percent=5.0,
                    regeneration_stages=3,
                    mode="staged_fixed",
                    flow_rate_bv_hr=2.0,
                    flow_direction="back",
                    backwash_enabled=False
                )
            )
            regeneration_time_hours = regen_results.get('regeneration_time_hours', 4.0)
            if service_vessels > 1 and regen_results:
                regen_results = regen_results.copy()
                regen_results['service_vessels'] = service_vessels
                if regen_results.get('regenerant_consumed_g') is not None:
                    per_vessel_regen = regen_results['regenerant_consumed_g']
                    regen_results['regenerant_consumed_g_per_vessel'] = per_vessel_regen
                    regen_results['regenerant_consumed_g'] = per_vessel_regen * service_vessels
                if regen_results.get('waste_volume_L') is not None:
                    per_vessel_waste = regen_results['waste_volume_L']
                    regen_results['waste_volume_L_per_vessel'] = per_vessel_waste
                    regen_results['waste_volume_L'] = per_vessel_waste * service_vessels
                    if vessel.bed_volume_L > 0:
                        regen_results['waste_volume_bv'] = regen_results['waste_volume_L'] / (
                            vessel.bed_volume_L * service_vessels
                        )
                if regen_results.get('regenerant_consumed_g_per_L') is not None:
                    regen_results['regenerant_consumed_g_per_L_per_vessel'] = regen_results[
                        'regenerant_consumed_g_per_L'
                    ]
            logger.info(f"WAC_Na regeneration completed: {regeneration_time_hours:.1f} hours")
        except Exception as e:
            logger.warning(f"Regeneration simulation failed: {e}. Using estimate.")
            regeneration_time_hours = 4.0
            regen_results = {
                'status': 'error',
                'regeneration_time_hours': regeneration_time_hours
            }
        
        # Prepare output
        return WACSimulationOutput(
            status="success" if breakthrough_reached else "warning",
            breakthrough_bv=breakthrough_bv,
            service_time_hours=service_time_hours,
            breakthrough_hardness_mg_l_caco3=target_hardness if breakthrough_reached else final_hardness_value,
            breakthrough_reached=breakthrough_reached,
            warnings=[] if breakthrough_reached else ["Breakthrough not reached within simulation time"],
            phreeqc_capacity_factor=capacity_utilization / 100,
            capacity_utilization_percent=capacity_utilization,
            breakthrough_data={
                'bv': sampled_data.get('BV', np.array([])).tolist(),
                'hardness_mg_l': sampled_data.get(hardness_key, np.array([])).tolist(),
                'ca_mg_l': sampled_data.get('Ca_mg/L', np.array([])).tolist(),
                'mg_mg_l': sampled_data.get('Mg_mg/L', np.array([])).tolist(),
                'na_mg_l': sampled_data.get('Na_mg/L', np.array([])).tolist(),
                'alkalinity_mg_l': sampled_data.get('Alk_mg/L_CaCO3', sampled_data.get('Alk_CaCO3_mg/L', sampled_data.get('Alk_mg/L', np.array([])))).tolist(),
                'ph': sampled_data.get('pH', np.array([])).tolist()
            },
            performance_metrics=performance_metrics,
            simulation_details={
                'cells': 10,
                'max_bv': max_bv,
                'resin_type': 'WAC_Na',
                'hardness_loading_meq_L': hardness_meq_L,
                'theoretical_bv': max_bv / 1.2,
                'service_vessels': service_vessels,
                'system_flow_m3_hr': total_flow_m3_hr,
                'flow_per_vessel_m3_hr': flow_per_vessel_m3_hr,
                'total_bed_volume_L': vessel.bed_volume_L * service_vessels,
                'bed_volume_L_per_vessel': vessel.bed_volume_L,
                'dataset_scope': 'per_vessel'
            },
            total_cycle_time_hours=service_time_hours + regeneration_time_hours,
            regeneration_results=regen_results
        )


class WacHSimulation(BaseWACSimulation):
    """Simulation for H-form WAC resins"""
    
    def _adjust_hform_breakthrough_data(
        self, 
        breakthrough_data: Dict[str, np.ndarray], 
        water_analysis: WACWaterComposition
    ) -> Dict[str, np.ndarray]:
        """
        Adjust breakthrough data to reflect H-form WAC limitations.
        H-form WAC only removes temporary hardness (hardness associated with alkalinity).
        """
        # Calculate feed hardness and alkalinity
        feed_ca = water_analysis.ca_mg_l or 0
        feed_mg = water_analysis.mg_mg_l or 0
        feed_hardness = feed_ca * 2.5 + feed_mg * 4.1
        feed_alkalinity = (water_analysis.hco3_mg_l or 0) / CONFIG.HCO3_EQUIV_WEIGHT * CONFIG.ALKALINITY_EQUIV_WEIGHT

        # Calculate temporary and permanent hardness
        temp_hardness = min(feed_hardness, feed_alkalinity) if feed_hardness is not None and feed_alkalinity is not None else 0
        perm_hardness = max(0, feed_hardness - feed_alkalinity) if feed_hardness is not None and feed_alkalinity is not None else 0
        
        # If there's permanent hardness, adjust the effluent data
        if perm_hardness > 0 and 'Hardness_mg/L' in breakthrough_data:
            # The minimum effluent hardness should be the permanent hardness
            # WAC cannot remove permanent hardness
            hardness_data = breakthrough_data['Hardness_mg/L'].copy()
            
            # Adjust each data point to ensure minimum permanent hardness remains
            for i in range(len(hardness_data)):
                if hardness_data[i] is not None and hardness_data[i] < perm_hardness:
                    # Scale Ca and Mg proportionally
                    ca_ratio = feed_ca / (feed_ca + feed_mg)
                    mg_ratio = feed_mg / (feed_ca + feed_mg)
                    
                    # Calculate minimum Ca and Mg that should remain
                    min_ca = (perm_hardness / 2.5) * ca_ratio
                    min_mg = (perm_hardness / 4.1) * mg_ratio
                    
                    # Adjust Ca and Mg data if available
                    if 'Ca_mg/L' in breakthrough_data:
                        if breakthrough_data['Ca_mg/L'][i] is not None and breakthrough_data['Ca_mg/L'][i] < min_ca:
                            breakthrough_data['Ca_mg/L'][i] = min_ca

                    if 'Mg_mg/L' in breakthrough_data:
                        if breakthrough_data['Mg_mg/L'][i] is not None and breakthrough_data['Mg_mg/L'][i] < min_mg:
                            breakthrough_data['Mg_mg/L'][i] = min_mg
                    
                    # Update hardness
                    hardness_data[i] = perm_hardness
            
            breakthrough_data['Hardness_mg/L'] = hardness_data
        
        return breakthrough_data
    
    def run_simulation(self, input_data: WACSimulationInput) -> WACSimulationOutput:
        """Run WAC H-form simulation."""
        water = input_data.water_analysis
        vessel = input_data.vessel_configuration
        target_hardness = input_data.target_hardness_mg_l_caco3
        target_alkalinity = input_data.target_alkalinity_mg_l_caco3 or CONFIG.WAC_ALKALINITY_LEAK_MG_L

        logger.info("Starting WAC H-form simulation")

        service_vessels = max(vessel.number_service, 1)
        total_flow_m3_hr = water.flow_m3_hr
        if service_vessels > 1:
            flow_per_vessel_m3_hr = total_flow_m3_hr / service_vessels
            logger.info(
                "Distributing %.2f m3/hr across %d service vessels (%.2f m3/hr each)",
                total_flow_m3_hr,
                service_vessels,
                flow_per_vessel_m3_hr
            )
            water = water.model_copy(update={"flow_m3_hr": flow_per_vessel_m3_hr})
        else:
            flow_per_vessel_m3_hr = total_flow_m3_hr

        # Check TDS and recommend Pitzer database if needed
        tds_g_l = (
            water.ca_mg_l + water.mg_mg_l + water.na_mg_l +
            water.k_mg_l + water.nh4_mg_l +
            getattr(water, 'cl_mg_l', 0) +
            water.so4_mg_l + water.hco3_mg_l
        ) / 1000.0
        requires_pitzer, pitzer_msg = CONFIG.check_tds_for_pitzer(tds_g_l)
        if requires_pitzer:
            logger.warning(pitzer_msg)

        # Validate water composition
        self._validate_water_composition(water.model_dump())

        # Calculate dynamic max_bv based on alkalinity loading (H-form breakthrough is alkalinity-controlled)
        # WAC H-form mechanism:
        # 1. H-form releases H+ when exchanging Ca2+/Mg2+
        # 2. Released H+ reacts with HCO3- to form CO2 + H2O
        # 3. When alkalinity is exhausted, pH drops causing hardness re-elution
        # Therefore, throughput is limited by alkalinity, not hardness capacity
        alkalinity_meq_L = water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT

        # Calculate max_bv for WAC_H based on alkalinity loading
        # Use working capacity (1.8 eq/L) to match PHREEQC EXCHANGE model
        max_bv = self._calculate_dynamic_max_bv(
            loading_meq_L=alkalinity_meq_L,
            capacity_eq_L=CONFIG.WAC_NA_WORKING_CAPACITY,  # 1.8 eq/L - matches PHREEQC template
            buffer_factor=1.5,  # Modest buffer for H-form (alkalinity-controlled breakthrough)
            min_bv=200
        )

        # H-form simulations are more computationally intensive due to dual-domain exchange
        # and pH equilibration. Cap max_bv to prevent excessive runtime.
        # Empirical overlay can still predict breakthrough beyond this.
        WAC_H_MAX_BV_CAP = 3000  # Matches max_shifts cap in wac_templates.py (5000 - margin)
        if max_bv > WAC_H_MAX_BV_CAP:
            logger.info(f"Capping WAC_H max_bv: {max_bv} -> {WAC_H_MAX_BV_CAP} for practical runtime")
            max_bv = WAC_H_MAX_BV_CAP

        logger.info(f"Dynamic max_bv calculated: {max_bv} (alkalinity loading: {alkalinity_meq_L:.2f} meq/L)")

        # Smart database selection for WAC H-form EXCHANGE model
        # phreeqc.dat: Better convergence with EXCHANGE, valid to I ≈ 0.7 M
        # pitzer.dat: Required for very high TDS (I > 0.5 M), but numerical challenges with EXCHANGE

        # Calculate ionic strength for database selection
        # I ≈ 0.5 × Σ(c_i × z_i²) where c_i is concentration (mol/L), z_i is charge
        ca_mol_l = water.ca_mg_l / 40.078 / 1000
        mg_mol_l = water.mg_mg_l / 24.305 / 1000
        na_mol_l = water.na_mg_l / 22.990 / 1000
        k_mol_l = water.k_mg_l / 39.098 / 1000
        cl_mol_l = getattr(water, 'cl_mg_l', 0) / 35.453 / 1000
        so4_mol_l = water.so4_mg_l / 96.06 / 1000
        hco3_mol_l = water.hco3_mg_l / 61.017 / 1000

        ionic_strength = 0.5 * (
            ca_mol_l * 4 + mg_mol_l * 4 +  # z² = 4 for divalent
            na_mol_l * 1 + k_mol_l * 1 +     # z² = 1 for monovalent
            cl_mol_l * 1 + hco3_mol_l * 1 +  # z² = 1 for monovalent anions
            so4_mol_l * 4                     # z² = 4 for divalent anion
        )

        # Database selection logic:
        # - I < 0.5 M: Use phreeqc.dat (better with SURFACE, adequate accuracy)
        # - I ≥ 0.5 M: Use pitzer.dat (required for high ionic strength)
        if ionic_strength >= 0.5:
            phreeqc_db_path = str(CONFIG.get_phreeqc_database('pitzer.dat'))
            logger.info(f"Using pitzer.dat for high ionic strength (I = {ionic_strength:.3f} M, TDS = {tds_g_l:.1f} g/L)")
        elif requires_pitzer:
            # Moderate TDS (10-15 g/L) but I < 0.5 M: Use phreeqc.dat for better SURFACE convergence
            phreeqc_db_path = str(CONFIG.get_phreeqc_database())
            logger.info(f"Using phreeqc.dat for moderate TDS/IS (I = {ionic_strength:.3f} M, TDS = {tds_g_l:.1f} g/L)")
            logger.info("phreeqc.dat provides better SURFACE convergence at moderate ionic strength")
        else:
            phreeqc_db_path = str(CONFIG.get_phreeqc_database())

        # Create PHREEQC input with SURFACE-based chemistry for proper pH dependence
        wac_h_cells = CONFIG.DEFAULT_CELLS  # Use 10 cells for better front tracking
        vessel_dict = vessel.model_dump()
        capacity_factor = vessel_dict.get('capacity_factor', getattr(vessel, 'capacity_factor', 1.0))
        capacity_eq_l = CONFIG.WAC_H_TOTAL_CAPACITY * capacity_factor
        bed_porosity = vessel_dict.get('bed_porosity', CONFIG.BED_POROSITY)

        water_dict = water.model_dump()
        if 'pH' not in water_dict:
            default_ph = getattr(water, 'ph', 7.5)
            water_dict['pH'] = water_dict.get('ph', default_ph)

        # Use EXCHANGE model with H+ competition for WAC H-form (Codex 019abbed)
        # Rationale: SURFACE model fails at industrial scale due to massive H+ release
        # during Newton-Raphson equilibration (>22,000 mol H+ into water phase).
        # EXCHANGE model with X- + H+ = XH (log_k = pKa) reproduces Henderson-Hasselbalch
        # site fraction and is numerically stable. This matches vendor practice
        # (DuPont WAVE, Purolite Soft, Lanxess LewaPlus) which use selectivity + empirical capacity.
        logger.info(f"Using EXCHANGE model with H+ competition for WAC H-form (I = {ionic_strength:.3f} M, TDS = {tds_g_l:.1f} g/L)")

        # Prepare vessel config for template
        vessel_config = {
            'bed_volume_L': vessel.bed_volume_L,
            'bed_depth_m': vessel.bed_depth_m,
            'bed_porosity': bed_porosity
        }

        phreeqc_input = create_wac_h_phreeqc_input(
            water_composition=water_dict,
            vessel_config=vessel_config,
            cells=wac_h_cells,
            max_bv=max_bv,
            database_path=phreeqc_db_path,
            capacity_factor=1.0
        )
        
        # Run PHREEQC
        try:
            output, selected_output = self.engine.run_phreeqc(phreeqc_input)
        except Exception as e:
            error_response = self._handle_phreeqc_error(e, {
                'resin_type': 'WAC_H',
                'water': water.model_dump(),
                'max_bv': max_bv
            })
            return WACSimulationOutput(
                status=error_response['status'],
                breakthrough_bv=error_response['breakthrough_bv'],
                service_time_hours=error_response['service_time_hours'],
                breakthrough_hardness_mg_l_caco3=target_hardness,
                breakthrough_alkalinity_mg_l_caco3=target_alkalinity,
                breakthrough_reached=error_response['breakthrough_reached'],
                warnings=error_response['warnings'],
                phreeqc_capacity_factor=0,
                capacity_utilization_percent=error_response['capacity_utilization_percent'],
                breakthrough_data=error_response['breakthrough_data'],
                performance_metrics=WACPerformanceMetrics(
                    # Breakthrough metrics (at target hardness)
                    breakthrough_ca_removal_percent=0,
                    breakthrough_mg_removal_percent=0,
                    breakthrough_hardness_removal_percent=0,
                    breakthrough_alkalinity_removal_percent=0,
                    # Average metrics (over service cycle)
                    avg_ca_removal_percent=0,
                    avg_mg_removal_percent=0,
                    avg_hardness_removal_percent=0,
                    avg_alkalinity_removal_percent=0,
                    # pH and CO2 statistics
                    average_effluent_ph=7.0,
                    min_effluent_ph=7.0,
                    max_effluent_ph=7.0,
                    co2_generation_mg_l=0,
                    active_sites_percent_final=0
                ),
                simulation_details=error_response['simulation_details'],
                total_cycle_time_hours=0
            )
        
        # Extract breakthrough data with equilibration filtering
        breakthrough_data = self._extract_breakthrough_data_filtered(selected_output)
        
        # Adjust breakthrough data for H-form WAC limitations
        # H-form WAC only removes temporary hardness (hardness associated with alkalinity)
        breakthrough_data = self._adjust_hform_breakthrough_data(breakthrough_data, water)

        # === APPLY EMPIRICAL LEAKAGE OVERLAY (Two-Layer Architecture) ===
        # WAC H+ has dual leakage concerns:
        # 1. Hardness leakage (0.1-1 mg/L) - minimal compared to Na-form
        # 2. Na/K leakage (2-8% of feed) - primary concern for H-form
        try:
            cal_loader = CalibrationLoader()
            cal_params = cal_loader.load('default', 'WAC_H')

            # Calculate feed properties
            feed_hardness_caco3 = water.ca_mg_l * 2.5 + water.mg_mg_l * 4.1
            feed_tds = (water.ca_mg_l + water.mg_mg_l + water.na_mg_l +
                        water.cl_mg_l + water.so4_mg_l + water.hco3_mg_l)

            # === Part 1: Na/K Leakage Calculation ===
            # Na/K are not exchanged by H-form WAC - they pass through with some
            # additional pickup as resin exhausts. Use empirical model from base class.
            bv_array = breakthrough_data.get('BV', np.array([]))

            if len(bv_array) > 0:
                # Calculate theoretical BV for exhaustion percentage calculation
                alkalinity_meq_L = water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT
                theoretical_bv = (CONFIG.WAC_H_TOTAL_CAPACITY * 1000) / alkalinity_meq_L if alkalinity_meq_L > 0 else max_bv

                # Calculate Na/K leakage at each BV point
                na_leakage_array = np.zeros_like(bv_array)
                k_leakage_array = np.zeros_like(bv_array)

                for i, bv in enumerate(bv_array):
                    exhaustion_pct = min(100.0, (bv / theoretical_bv) * 100) if theoretical_bv > 0 else 0
                    leakage_result = self.calculate_h_form_leakage(
                        influent_na_mg_l=water.na_mg_l,
                        influent_k_mg_l=getattr(water, 'k_mg_l', 0.0),
                        resin_exhaustion_percent=exhaustion_pct,
                        base_na_leakage_percent=cal_params.base_na_leakage_percent,
                        base_k_leakage_percent=cal_params.base_k_leakage_percent,
                        exhaustion_factor=cal_params.leakage_exhaustion_factor
                    )
                    na_leakage_array[i] = leakage_result['na_mg_l']
                    k_leakage_array[i] = leakage_result['k_mg_l']

                # Add Na/K leakage to breakthrough data
                breakthrough_data['Na_leakage_mg/L'] = na_leakage_array
                breakthrough_data['K_leakage_mg/L'] = k_leakage_array

                logger.info(f"WAC H+ Na/K leakage overlay applied: Na {na_leakage_array[0]:.1f}-{na_leakage_array[-1]:.1f} mg/L")

            # === Part 2: Hardness Overlay with Henderson-Hasselbalch (WAC H-form specific) ===
            # Use WAC H-form specific leakage calculation which accounts for:
            # - Equilibrium vs kinetic capacity discrepancy (pKa effect)
            # - Kinetic trap factor for protonation retention
            overlay = EmpiricalLeakageOverlay(cal_params)
            overlay.update_regen_efficiency_from_design(resin_type='WAC_H')

            # Get PHREEQC baseline hardness (early BV values)
            hardness_key = 'Hardness_CaCO3' if 'Hardness_CaCO3' in breakthrough_data else 'Hardness_mg/L'
            hardness_array = breakthrough_data.get(hardness_key, np.array([]))

            # Calculate feed alkalinity in mg/L as CaCO3
            feed_alkalinity_caco3 = (water.hco3_mg_l or 0) / CONFIG.HCO3_EQUIV_WEIGHT * CONFIG.ALKALINITY_EQUIV_WEIGHT
            feed_ph = water_dict.get('pH', 7.5)

            if len(hardness_array) > 0:
                phreeqc_early_leakage = float(np.min(hardness_array[:max(5, len(hardness_array)//10)]))

                # Use WAC H-form specific method with Henderson-Hasselbalch model
                overlay_result = overlay.calculate_wac_h_leakage(
                    feed_hardness_mg_l_caco3=feed_hardness_caco3,
                    feed_alkalinity_mg_l_caco3=feed_alkalinity_caco3,
                    feed_ph=feed_ph,
                    feed_tds_mg_l=feed_tds,
                    temperature_c=getattr(water, 'temperature_c', 25.0),
                    phreeqc_leakage_mg_l=phreeqc_early_leakage
                )

                empirical_floor = overlay_result.hardness_leakage_mg_l_caco3
                original_min = float(np.min(hardness_array))

                # Log Henderson-Hasselbalch diagnostics
                for note in overlay_result.model_notes[:4]:  # First 4 notes are H-H diagnostics
                    logger.info(f"WAC H+ H-H: {note}")

                # Apply additive offset if empirical floor exceeds PHREEQC minimum
                if empirical_floor > original_min:
                    offset = empirical_floor - original_min
                    breakthrough_data[hardness_key] = hardness_array + offset
                    logger.info(f"WAC H+ hardness overlay applied: offset +{offset:.2f} mg/L (H-H model)")

        except Exception as e:
            logger.warning(f"WAC H+ empirical overlay failed, using raw PHREEQC results: {e}")

        # Find breakthrough point (alkalinity-based for H-form)
        # Use shared detection method with multiple criteria in priority order
        # pH breakthrough (when alkalinity is exhausted, pH crashes below pKa)
        pH_floor = 4.5  # Below WAC pKa (4.8) indicates alkalinity exhausted

        criteria = [
            # Primary: Alkalinity breakthrough (now using correct ALK measurement)
            ('Alk_CaCO3_mg/L', target_alkalinity, 'gt'),  # Column name matches USER_PUNCH header
            # Secondary: pH crash (direct indicator of alkalinity exhaustion)
            ('pH', pH_floor, 'lt'),  # pH < 4.5 means alkalinity exhausted
            # Tertiary: Hardness breakthrough (in case alkalinity is already low)
            ('Hardness_mg/L', target_hardness, 'gt')
            # Note: Active sites % not reliable for breakthrough detection
            # due to exchange front movement through column
        ]
        
        breakthrough_bv, breakthrough_reached, reason = self._detect_breakthrough(
            breakthrough_data, criteria
        )
        
        if breakthrough_reached:
            logger.info(f"WAC H breakthrough at {breakthrough_bv:.1f} BV ({reason})")
        else:
            logger.warning(f"No breakthrough criteria met in {max_bv} BV")
        
        # Calculate service time
        flow_rate_m3_hr = flow_per_vessel_m3_hr
        bed_volume_m3 = vessel.bed_volume_L / 1000
        service_time_hours = breakthrough_bv * bed_volume_m3 / flow_rate_m3_hr if flow_rate_m3_hr > 0 else 0

        # Calculate performance metrics
        performance_metrics = self._calculate_performance_metrics(breakthrough_data, water, breakthrough_bv)

        # Extract final resin state for regeneration
        resin_state = self._extract_final_resin_state(
            service_bv=breakthrough_bv,
            vessel_config=vessel.model_dump(),
            water_analysis=water
        )

        from tools.sac_simulation import RegenerationConfig

        # Calculate regenerant dose for WAC_H based on alkalinity loading
        bed_volume_L = vessel.bed_volume_L
        alkalinity_eq = resin_state.get('h_equiv', 0)  # H+ equivalents to regenerate
        # Use 110% excess for acid regeneration
        acid_dose_g_per_L = (alkalinity_eq * 36.46 * 1.10) / bed_volume_L if bed_volume_L > 0 else 100

        try:
            # WAC_H uses acid regeneration (typically HCl or H2SO4)
            regen_results = self.run_regeneration(
                resin_state=resin_state,
                vessel_config=vessel.model_dump(),
                regen_config=RegenerationConfig(
                    regenerant_type="HCl",  # Using HCl for H-form regeneration
                    concentration_percent=2.0,  # 2% HCl solution
                    regenerant_dose_g_per_L=acid_dose_g_per_L,  # Calculated dose
                    regeneration_stages=2,  # Simplified regeneration for H-form
                    mode="staged_fixed",
                    flow_rate_bv_hr=2.0,
                    flow_direction="back",
                    backwash_enabled=False,
                    slow_rinse_bv=0.5,
                    fast_rinse_bv=1.0
                )
            )
            regeneration_time_hours = regen_results.get("total_regen_time_hours", 2.5)
            logger.info(f"WAC_H regeneration time: {regeneration_time_hours:.2f} hours")
        except Exception as e:
            logger.warning(f"Regeneration simulation failed: {e}")
            regeneration_time_hours = 2.5  # Default estimate
            regen_results = {
                "status": "estimated",
                "total_regen_time_hours": regeneration_time_hours,
                "warning": str(e)
            }

        # Calculate capacity utilization (breakthrough-based, like SAC)
        # For H-form, use alkalinity since that's the limiting factor
        # Formula: (actual BV at breakthrough) / (theoretical BV) * 100
        alkalinity_meq_L = water.hco3_mg_l / CONFIG.HCO3_EQUIV_WEIGHT  # meq/L
        # theoretical_bv = (capacity in meq/L) / (feed alkalinity in meq/L)
        theoretical_bv = (CONFIG.WAC_H_TOTAL_CAPACITY * 1000) / alkalinity_meq_L if alkalinity_meq_L > 0 else 0
        capacity_utilization = (breakthrough_bv / theoretical_bv * 100) if theoretical_bv > 0 else 0
        
        # Prepare warnings
        warnings = []
        if not breakthrough_reached:
            warnings.append("Breakthrough not reached within simulation time")
        else:
            warnings.append(f"Breakthrough triggered by: {reason}")
        
        if performance_metrics.co2_generation_mg_l > 50:
            warnings.append("High CO2 generation - decarbonator recommended")
        
        # H-form PHREEQC limitation (apply once here in the H-form branch)
        warnings.append("WAC H-form: PHREEQC breakthrough BV is an artifact (reduced pKa 2.5 vs true 4.8). Use empirical overlay capacity for sizing.")
        
        # Apply smart sampling to reduce data size
        sampled_data = self._smart_sample_breakthrough_curves(breakthrough_data, max_points=60)
        
        # Log summary
        self._log_simulation_summary({
            'status': "success" if breakthrough_reached else "warning",
            'breakthrough_bv': breakthrough_bv,
            'service_time_hours': service_time_hours,
            'breakthrough_reached': breakthrough_reached,
            'warnings': warnings
        }, 'WAC_H')
        
        # Get final values for output
        hardness_key = 'Hardness_CaCO3' if 'Hardness_CaCO3' in breakthrough_data else 'Hardness_mg/L'
        final_hardness = breakthrough_data.get(hardness_key, np.array([]))
        final_hardness_value = float(final_hardness[-1]) if len(final_hardness) > 0 else target_hardness
        
        # Handle both old and new alkalinity keys
        final_alkalinity = breakthrough_data.get('Alk_CaCO3_mg/L', breakthrough_data.get('Alk_mg/L', np.array([])))
        final_alkalinity_value = float(final_alkalinity[-1]) if len(final_alkalinity) > 0 else target_alkalinity
        
        # Prepare output
        return WACSimulationOutput(
            status="success" if breakthrough_reached else "warning",
            breakthrough_bv=breakthrough_bv,
            service_time_hours=service_time_hours,
            breakthrough_hardness_mg_l_caco3=target_hardness if "hardness" in reason.lower() else final_hardness_value,
            breakthrough_alkalinity_mg_l_caco3=target_alkalinity if "alk" in reason.lower() else final_alkalinity_value,
            breakthrough_reached=breakthrough_reached,
            warnings=warnings,
            phreeqc_capacity_factor=capacity_utilization / 100,
            capacity_utilization_percent=capacity_utilization,
            breakthrough_data={
                'bv': sampled_data.get('BV', np.array([])).tolist(),
                'hardness_mg_l': sampled_data.get(hardness_key, np.array([])).tolist(),
                'alkalinity_mg_l': sampled_data.get('Alk_mg/L_CaCO3', sampled_data.get('Alk_CaCO3_mg/L', sampled_data.get('Alk_mg/L', np.array([])))).tolist(),
                'temporary_hardness_mg_l': sampled_data.get('Temp_Hard', np.array([])).tolist(),
                'ca_mg_l': sampled_data.get('Ca_mg/L', np.array([])).tolist(),
                'mg_mg_l': sampled_data.get('Mg_mg/L', np.array([])).tolist(),
                'na_mg_l': sampled_data.get('Na_mg/L', np.array([])).tolist(),
                'ph': sampled_data.get('pH', np.array([])).tolist(),
                'co2_mg_l': sampled_data.get('CO2_mg/L', np.array([])).tolist(),
                'active_sites_percent': sampled_data.get('Active_Sites_%', np.array([])).tolist(),
                # WAC H+ specific: Na/K leakage from empirical overlay
                'na_leakage_mg_l': sampled_data.get('Na_leakage_mg/L', np.array([])).tolist(),
                'k_leakage_mg_l': sampled_data.get('K_leakage_mg/L', np.array([])).tolist()
            },
            performance_metrics=performance_metrics,
            simulation_details={
                'cells': 10,
                'max_bv': max_bv,
                'resin_type': 'WAC_H',
                'breakthrough_reason': reason,
                'alkalinity_loading_meq_L': alkalinity_meq_L,
                'theoretical_bv': max_bv / 1.2,
                'service_vessels': service_vessels,
                'system_flow_m3_hr': total_flow_m3_hr,
                'flow_per_vessel_m3_hr': flow_per_vessel_m3_hr,
                'total_bed_volume_L': vessel.bed_volume_L * service_vessels,
                'bed_volume_L_per_vessel': vessel.bed_volume_L,
                'dataset_scope': 'per_vessel'
            },
            total_cycle_time_hours=service_time_hours + regeneration_time_hours,
            regeneration_results=regen_results
        )


def simulate_wac_system(input_data: WACSimulationInput) -> WACSimulationOutput:
    """Main entry point for WAC simulation."""
    resin_type = input_data.vessel_configuration.resin_type
    
    if resin_type == "WAC_Na":
        simulator = WacNaSimulation()
    elif resin_type == "WAC_H":
        simulator = WacHSimulation()
    else:
        raise ValueError(f"Unknown resin type: {resin_type}")
    
    return simulator.run_simulation(input_data)
