"""
PHREEQC TRANSPORT Engine for Ion Exchange Column Modeling

This module implements a transport-based ion exchange model using PHREEQC's
TRANSPORT capabilities for more accurate breakthrough curve prediction.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
import json
from pathlib import Path
from dataclasses import dataclass
from phreeqpython import PhreeqPython
import re
import logging
from .kinetic_model import KineticModel, KineticParameters
from .trace_metals_model import TraceMetalsModel, add_trace_metal_selectivity_to_phreeqc
from .direct_phreeqc_engine import DirectPhreeqcEngine
from .empirical_breakthrough_model import EmpiricalBreakthroughModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TransportParameters:
    """Parameters for PHREEQC TRANSPORT simulation"""
    cells: int = 20  # Number of cells for discretization
    shifts: int = 100  # Number of time steps
    time_step: float = 360  # Time per step (seconds)
    dispersivity: float = 0.01  # Dispersivity (m)
    diffusion_coefficient: float = 1e-9  # Diffusion coefficient (m2/s)
    porosity: float = 0.4  # Bed porosity
    
    # Stagnant zone parameters (dual porosity)
    stagnant_enabled: bool = False
    stagnant_alpha: float = 6.8e-6  # Exchange factor
    stagnant_mobile_porosity: float = 0.3
    stagnant_immobile_porosity: float = 0.1


class PhreeqcTransportEngine:
    """PHREEQC TRANSPORT-based ion exchange model"""
    
    def __init__(self, resin_type: str = "SAC"):
        """
        Initialize transport engine with resin type
        
        Args:
            resin_type: Type of resin (SAC, WAC_H, WAC_Na)
        """
        self.pp = PhreeqPython()
        self.resin_type = resin_type
        self.load_resin_parameters()
        
    def load_resin_parameters(self):
        """Load resin parameters from JSON database"""
        param_file = Path(__file__).parent.parent / "data" / "resin_parameters.json"
        with open(param_file, 'r') as f:
            params = json.load(f)
        
        # Extract parameters from nested structure
        resin_data = params['resin_types'][self.resin_type]
        
        # Create simplified parameter structure for the engine
        self.resin_params = {
            'capacity_eq_L': resin_data['exchange_capacity_eq_L']['gel'],
            'selectivity': resin_data['selectivity_coefficients'],
            'pH_range': resin_data['operating_pH_range'],
            'regenerant': resin_data['regenerant'],
            'kinetic_factor': resin_data['kinetic_factor']
        }
        
        logger.info(f"Loaded parameters for {self.resin_type} resin")
        
    def generate_transport_input(self, 
                               column_params: Dict,
                               feed_composition: Dict,
                               transport_params: Optional[TransportParameters] = None) -> str:
        """Generate PHREEQC input string with TRANSPORT block"""
        
        if transport_params is None:
            transport_params = TransportParameters()
            
        # Extract column parameters
        bed_volume_m3 = column_params.get('bed_volume_m3', 0.001)
        diameter_m = column_params.get('diameter_m', 0.05)
        flow_rate_m3_hr = column_params.get('flow_rate_m3_hr', 0.1)
        bed_depth_m = column_params.get('bed_depth_m', 1.5)
        
        # Apply kinetic adjustments if enabled
        if column_params.get('apply_kinetics', True):
            kinetic_params = KineticParameters(
                flow_rate_m3_hr=flow_rate_m3_hr,
                bed_volume_m3=bed_volume_m3,
                bed_diameter_m=diameter_m,
                temperature_celsius=feed_composition.get('temperature', 25)
            )
            
            kinetic_model = KineticModel()
            adjustments = kinetic_model.adjust_transport_parameters(
                kinetic_params,
                base_dispersivity=transport_params.dispersivity,
                base_diffusion=transport_params.diffusion_coefficient
            )
            
            # Apply adjustments
            transport_params.dispersivity = adjustments['dispersivity']
            transport_params.diffusion_coefficient = adjustments['diffusion_coefficient']
            
            logger.info(f"Applied kinetic adjustments: efficiency={adjustments['efficiency']:.0%}, "
                       f"mechanism={adjustments['mechanism']}")
        
        # Calculate derived parameters
        cross_section = np.pi * (diameter_m/2)**2
        linear_velocity = flow_rate_m3_hr / cross_section / 3600  # m/s
        cell_length = bed_depth_m / transport_params.cells  # m/cell
        
        # Calculate actual time step to match flow rate
        pore_volume = bed_volume_m3 * transport_params.porosity
        residence_time = pore_volume / (flow_rate_m3_hr / 3600)  # seconds
        time_per_shift = residence_time / transport_params.cells  # s/shift
        
        input_str = []
        
        # Title
        input_str.append(f"TITLE Ion Exchange Column - {self.resin_type} Resin")
        input_str.append(f"# Bed Volume: {bed_volume_m3*1000:.1f} L")
        input_str.append(f"# Flow Rate: {flow_rate_m3_hr*1000:.1f} L/hr")
        input_str.append(f"# Linear Velocity: {linear_velocity*3600:.2f} m/hr")
        input_str.append("")
        
        # Define feed solution (Solution 0)
        input_str.append("SOLUTION 0  # Feed water")
        input_str.append("    units mg/L")
        input_str.append(f"    temp {feed_composition.get('temperature', 25)}")
        input_str.append(f"    pH {feed_composition.get('pH', 7.0)}")
        input_str.append(f"    pe 4")
        
        # Process trace metals if enabled
        if column_params.get('include_trace_metals', True):
            trace_model = TraceMetalsModel()
            feed_with_traces = trace_model.add_trace_metals_to_phreeqc(feed_composition)
        else:
            feed_with_traces = feed_composition.copy()
        
        # Calculate charge balance to determine which ion needs CHARGE keyword
        # Import translator for charge balance calculation
        from ..phreeqc_translator import MCASPhreeqcTranslator
        translator = MCASPhreeqcTranslator()
        
        # Convert feed composition to check charge balance
        phreeqc_concs = {}
        for ion, conc in feed_with_traces.items():
            if ion not in ['temperature', 'pH', 'alkalinity'] and not ion.endswith('+'):
                # Map to PHREEQC species format for charge calculation
                if ion == 'Ca':
                    phreeqc_concs['Ca+2'] = conc
                elif ion == 'Mg':
                    phreeqc_concs['Mg+2'] = conc
                elif ion == 'Na':
                    phreeqc_concs['Na+'] = conc
                elif ion == 'Cl':
                    phreeqc_concs['Cl-'] = conc
                elif ion == 'SO4' or ion == 'S(6)':
                    phreeqc_concs['SO4-2'] = conc
                elif ion == 'HCO3' or ion == 'C(4)':
                    phreeqc_concs['HCO3-'] = conc
        
        # Check charge balance
        is_neutral, charge_imbalance = translator.check_electroneutrality(phreeqc_concs)
        
        # Decide which ion to use for charge balance
        if abs(charge_imbalance) > 0.1:  # Only adjust if significant imbalance
            if charge_imbalance > 0:  # Excess positive charge - need more anions
                balance_ion = 'Cl'  # Adjust Cl- upward
                logger.info(f"Charge imbalance: +{charge_imbalance:.2f} meq/L, using Cl for balance")
            else:  # Excess negative charge - need more cations
                balance_ion = 'Na'  # Adjust Na+ upward
                logger.info(f"Charge imbalance: {charge_imbalance:.2f} meq/L, using Na for balance")
        else:
            balance_ion = None  # No adjustment needed
            logger.info("Solution is already charge balanced")
        
        # Add feed components with CHARGE keyword as needed
        for ion, conc in feed_with_traces.items():
            if ion not in ['temperature', 'pH', 'alkalinity'] and not ion.endswith('+'):
                if ion == balance_ion:
                    input_str.append(f"    {ion} {conc} charge")
                else:
                    input_str.append(f"    {ion} {conc}")
                
        if 'alkalinity' in feed_composition:
            input_str.append(f"    Alkalinity {feed_composition['alkalinity']} as HCO3")
            
        input_str.append("")
        
        # Define initial column solutions (all cells start with Na-rich water for proper equilibration)
        input_str.append("SOLUTION 1-20  # Initial column water")
        input_str.append("    units mg/L")
        input_str.append(f"    temp {feed_composition.get('temperature', 25)}")
        input_str.append("    pH 7.0")
        input_str.append("    Na 1000  # High Na to ensure resin starts in Na form")
        input_str.append("    Cl 1540  # Balance charge")
        input_str.append("")
        
        # Define exchanger for each cell
        # PHREEQC uses exchanger amount per kg of water IN EACH CELL
        # Need to distribute total column capacity across all cells
        
        capacity_eq_L = self.resin_params['capacity_eq_L']  # eq/L of resin
        
        # Calculate per-cell values
        cell_volume_m3 = cell_length * cross_section  # m3
        cell_resin_volume_L = cell_volume_m3 * 1000 * (1 - transport_params.porosity)  # L
        cell_water_volume_L = cell_volume_m3 * 1000 * transport_params.porosity  # L
        cell_water_kg = cell_water_volume_L  # kg (density ~1)
        
        # Exchange capacity per cell
        cell_capacity_eq = capacity_eq_L * cell_resin_volume_L  # eq
        
        # Exchanger per kg water in each cell
        exchanger_mol_per_kg = cell_capacity_eq / cell_water_kg
        
        logger.info(f"Exchanger calculation (per cell):")
        logger.info(f"  Cell volume: {cell_volume_m3*1000:.3f} L")
        logger.info(f"  Cell resin volume: {cell_resin_volume_L:.3f} L")
        logger.info(f"  Cell water volume: {cell_water_volume_L:.3f} L")
        logger.info(f"  Cell exchange capacity: {cell_capacity_eq:.3f} eq")
        logger.info(f"  Exchanger/kg water: {exchanger_mol_per_kg:.3f} mol/kg")
        
        input_str.append(f"EXCHANGE 1-{transport_params.cells}")
        input_str.append(f"    X {exchanger_mol_per_kg}")
        input_str.append("    -equilibrate 1")  # Equilibrate with initial solution
        input_str.append("")
        
        # Define exchange reactions with resin-specific selectivity
        input_str.append("EXCHANGE_SPECIES")
        
        # Base exchange reactions
        if self.resin_type in ["SAC", "WAC_Na"]:
            input_str.append("    Na+ + X- = NaX")
            input_str.append("    log_k 0.0")
            
            # Ca exchange with resin-specific selectivity
            K_Ca_Na = self.resin_params['selectivity']['Ca/Na']
            log_k_ca = np.log10(K_Ca_Na)
            input_str.append("    Ca+2 + 2X- = CaX2")
            input_str.append(f"    log_k {log_k_ca:.2f}")
            input_str.append("    -gamma 5.0 0.165  # Activity coefficient")
            
            # Mg exchange
            K_Mg_Na = self.resin_params['selectivity']['Mg/Na']
            log_k_mg = np.log10(K_Mg_Na)
            input_str.append("    Mg+2 + 2X- = MgX2")
            input_str.append(f"    log_k {log_k_mg:.2f}")
            input_str.append("    -gamma 5.5 0.2  # Activity coefficient")
            
        elif self.resin_type == "WAC_H":
            # H-form WAC resin
            input_str.append("    H+ + X- = HX")
            input_str.append("    log_k 0.0")
            
            K_Ca_H = self.resin_params['selectivity']['Ca/H']
            log_k_ca = np.log10(K_Ca_H)
            input_str.append("    Ca+2 + 2X- = CaX2")
            input_str.append(f"    log_k {log_k_ca:.2f}")
            
            K_Mg_H = self.resin_params['selectivity']['Mg/H']
            log_k_mg = np.log10(K_Mg_H)
            input_str.append("    Mg+2 + 2X- = MgX2")
            input_str.append(f"    log_k {log_k_mg:.2f}")
            
        input_str.append("")
        
        # TRANSPORT block
        input_str.append("TRANSPORT")
        input_str.append(f"    -cells {transport_params.cells}")
        input_str.append(f"    -shifts {transport_params.shifts}")
        input_str.append(f"    -time_step {time_per_shift:.1f}  # seconds")
        input_str.append("    -flow_direction forward")
        input_str.append("    -boundary_conditions flux flux")
        input_str.append(f"    -lengths {cell_length}")
        input_str.append(f"    -dispersivities {transport_params.dispersivity}")
        input_str.append(f"    -diffusion_coefficient {transport_params.diffusion_coefficient}")
        
        if transport_params.stagnant_enabled:
            input_str.append(f"    -stagnant 1 {transport_params.stagnant_alpha} "
                           f"{transport_params.stagnant_mobile_porosity} "
                           f"{transport_params.stagnant_immobile_porosity}")
        
        input_str.append(f"    -punch_cells {transport_params.cells}")  # Only punch effluent cell
        input_str.append("    -punch_frequency 1  # Punch every shift")
        input_str.append("")
        
        # Output definitions  
        input_str.append("SELECTED_OUTPUT 1")
        input_str.append("    -file transport_output.csv")
        input_str.append("    -reset false")
        input_str.append("    -time true")
        input_str.append("    -distance true")
        input_str.append("    -step true")
        input_str.append("    -totals Ca Mg Na Cl")
        input_str.append("    -molalities CaX2 MgX2 NaX HX")
        input_str.append("    -saturation_indices Calcite Gypsum")
        input_str.append("")
        
        # Custom output for effluent monitoring
        input_str.append("USER_PUNCH 1")
        input_str.append("    -headings BV Ca_mg/L Mg_mg/L Na_mg/L Fe_mg/L Mn_mg/L")
        # Resolution-independent BV calculation
        # Calculate total pore volume for BV calculation
        total_pore_volume_L = bed_volume_m3 * 1000 * transport_params.porosity
        input_str.append(f"    10 total_pore_vol = {total_pore_volume_L:.3f}  # L")
        input_str.append("    20 w = POR()  # Get water mass in this cell (kg)")
        input_str.append("    30 bed_vol = STEP_NO * w / total_pore_vol")
        input_str.append("    40 PUNCH bed_vol")
        input_str.append("    50 PUNCH TOT(\"Ca\") * 40080  # Convert mol/kgw to mg/L")
        input_str.append("    60 PUNCH TOT(\"Mg\") * 24305")
        input_str.append("    70 PUNCH TOT(\"Na\") * 22990")
        input_str.append("    80 PUNCH TOT(\"Fe\") * 55845")
        input_str.append("    90 PUNCH TOT(\"Mn\") * 54938")
        input_str.append("")
        
        input_str.append("END")
        
        # Add trace metal selectivity if needed
        if column_params.get('include_trace_metals', True):
            input_lines = input_str
            # Get list of metals present in the feed
            metals_present = list(feed_with_traces.keys())
            input_lines = add_trace_metal_selectivity_to_phreeqc(input_lines, self.resin_type, metals_present)
            return '\n'.join(input_lines)
        else:
            return '\n'.join(input_str)
        
    def run_transport_simulation(self, 
                               column_params: Dict,
                               feed_composition: Dict,
                               transport_params: Optional[TransportParameters] = None) -> Dict:
        """Run TRANSPORT simulation and parse results"""
        
        # Generate input
        input_string = self.generate_transport_input(
            column_params, feed_composition, transport_params
        )
        
        logger.info("Running PHREEQC TRANSPORT simulation...")
        logger.debug(f"Input:\n{input_string}")
        
        # Run simulation
        try:
            self.pp.ip.run_string(input_string)
            logger.info("PHREEQC simulation completed")
        except Exception as e:
            logger.error(f"PHREEQC simulation failed: {e}")
            error_string = self.pp.ip.get_error_string()
            logger.error(f"PHREEQC Error: {error_string}")
            return {'error': 'PHREEQC simulation failed', 'error_detail': str(e)}
        
        # Get selected output
        output = self.pp.ip.get_selected_output_array()
        
        # Debug output
        logger.debug(f"Output shape: {output.shape if hasattr(output, 'shape') else 'No shape'}")
        if output is not None and len(output) > 0:
            logger.debug(f"Headers: {output[0] if len(output) > 0 else 'No headers'}")
        
        # Parse results
        if output is None or len(output) < 2:
            logger.warning("No output data from PHREEQC")
            return {'error': 'No output data', 'bed_volumes': [], 'effluent_Ca_mg_L': []}
            
        results = self.parse_transport_output(output, column_params)
        
        return results
        
    def parse_transport_output(self, output: np.ndarray, column_params: Dict) -> Dict:
        """Parse PHREEQC TRANSPORT output to extract breakthrough curves"""
        
        # Extract column headers - convert to list if needed
        headers = output[0]
        if isinstance(headers, np.ndarray):
            headers = headers.tolist()
        
        # Convert headers to list for easier searching
        header_list = [str(h) for h in headers]
        
        # Find indices using list operations
        try:
            time_idx = header_list.index('time')
        except ValueError:
            try:
                time_idx = header_list.index('Time')
            except ValueError:
                logger.error(f"Cannot find time column. Available headers: {header_list}")
                return {'error': 'Missing time column', 'bed_volumes': [], 'effluent_Ca_mg_L': []}
        
        # Look for our custom output columns first
        try:
            bv_idx = header_list.index('BV')
            ca_mg_idx = header_list.index('Ca_mg/L')
            mg_mg_idx = header_list.index('Mg_mg/L')
            na_mg_idx = header_list.index('Na_mg/L')
            use_custom_output = True
        except ValueError:
            # Fall back to standard columns
            use_custom_output = False
            try:
                ca_idx = header_list.index('Ca(mol/kgw)')
                mg_idx = header_list.index('Mg(mol/kgw)')
                na_idx = header_list.index('Na(mol/kgw)')
            except ValueError:
                logger.error(f"Cannot find concentration columns. Headers: {header_list}")
                return {'error': 'Missing concentration columns', 'bed_volumes': [], 'effluent_Ca_mg_L': []}
        
        # Extract data (skip header row)
        data = output[1:]
        
        if use_custom_output:
            # Filter to get unique bed volumes (remove duplicates from multiple cells)
            # PHREEQC outputs data for each cell at each shift, we only want effluent
            unique_data = []
            seen_bvs = set()
            
            for row in data:
                bv = row[bv_idx]
                # Only keep the row if we haven't seen this BV before
                # This ensures we get the effluent cell data (last cell printed)
                if bv not in seen_bvs or bv == 0:  # Keep all BV=0 for initial state
                    if bv != 0:  # For non-zero BV, replace previous entry
                        # Remove previous entry with same BV if exists
                        unique_data = [r for r in unique_data if r[bv_idx] != bv]
                    unique_data.append(row)
                    seen_bvs.add(bv)
            
            # Use filtered data
            data = unique_data
            
            # Extract arrays from filtered data
            bed_volumes = np.array([row[bv_idx] for row in data], dtype=float)
            ca_mg_L = np.array([row[ca_mg_idx] for row in data], dtype=float)
            mg_mg_L = np.array([row[mg_mg_idx] for row in data], dtype=float)
            na_mg_L = np.array([row[na_mg_idx] for row in data], dtype=float)
            times = np.array([row[time_idx] for row in data], dtype=float) / 3600  # Convert to hours
        else:
            # Calculate from standard columns
            bed_volume_m3 = column_params.get('bed_volume_m3', 0.001)
            flow_rate_m3_hr = column_params.get('flow_rate_m3_hr', 0.1)
            
            times = np.array([row[time_idx] for row in data], dtype=float) / 3600  # Convert to hours
            volumes_m3 = times * flow_rate_m3_hr
            bed_volumes = volumes_m3 / bed_volume_m3
            
            # Extract concentrations (mol/kgw -> mg/L)
            ca_mol_kg = np.array([row[ca_idx] for row in data], dtype=float)
            mg_mol_kg = np.array([row[mg_idx] for row in data], dtype=float)
            na_mol_kg = np.array([row[na_idx] for row in data], dtype=float)
            
            # Convert to mg/L
            ca_mg_L = ca_mol_kg * 40.08 * 1000  # MW of Ca
            mg_mg_L = mg_mol_kg * 24.31 * 1000  # MW of Mg
            na_mg_L = na_mol_kg * 22.99 * 1000  # MW of Na
        
        results = {
            'bed_volumes': bed_volumes.tolist(),
            'time_hours': times.tolist(),
            'effluent_Ca_mg_L': ca_mg_L.tolist(),
            'effluent_Mg_mg_L': mg_mg_L.tolist(),
            'effluent_Na_mg_L': na_mg_L.tolist(),
            'model_type': 'PHREEQC_TRANSPORT',
            'resin_type': self.resin_type
        }
        
        # Find breakthrough points (C/C0 > 0.05)
        feed_ca = column_params.get('feed_Ca_mg_L', 0)
        feed_mg = column_params.get('feed_Mg_mg_L', 0)
        
        if feed_ca > 0:
            # Find breakthrough, but skip the initial BV=0 data point
            # which represents the feed entering the column
            ca_ratio = ca_mg_L / feed_ca
            valid_indices = np.where(bed_volumes > 0)[0]
            if len(valid_indices) > 0:
                ca_breakthrough_idx = np.where(ca_ratio[valid_indices] > 0.05)[0]
                if len(ca_breakthrough_idx) > 0:
                    actual_idx = valid_indices[ca_breakthrough_idx[0]]
                    results['Ca_breakthrough_BV'] = bed_volumes[actual_idx]
                else:
                    results['Ca_breakthrough_BV'] = None
            else:
                results['Ca_breakthrough_BV'] = None
                
        if feed_mg > 0:
            # Find breakthrough, but skip the initial BV=0 data point
            mg_ratio = mg_mg_L / feed_mg
            valid_indices = np.where(bed_volumes > 0)[0]
            if len(valid_indices) > 0:
                mg_breakthrough_idx = np.where(mg_ratio[valid_indices] > 0.05)[0]
                if len(mg_breakthrough_idx) > 0:
                    actual_idx = valid_indices[mg_breakthrough_idx[0]]
                    results['Mg_breakthrough_BV'] = bed_volumes[actual_idx]
                else:
                    results['Mg_breakthrough_BV'] = None
            else:
                results['Mg_breakthrough_BV'] = None
                
        return results
        
    def simulate_breakthrough(self, 
                            column_params: Dict,
                            feed_composition: Dict,
                            transport_params: Optional[TransportParameters] = None,
                            use_direct_phreeqc: bool = True) -> Dict:
        """Main entry point for breakthrough simulation
        
        Args:
            column_params: Column design parameters
            feed_composition: Feed water composition
            transport_params: Transport simulation parameters
            use_direct_phreeqc: If True, use direct PHREEQC executable instead of wrapper
        """
        
        # Add feed composition to column params for breakthrough analysis
        column_params['feed_Ca_mg_L'] = feed_composition.get('Ca', 0)
        column_params['feed_Mg_mg_L'] = feed_composition.get('Mg', 0)
        
        if use_direct_phreeqc:
            logger.info("Using direct PHREEQC executable for simulation")
            try:
                # Initialize direct PHREEQC engine
                direct_engine = DirectPhreeqcEngine()
                
                # Generate PHREEQC input
                if transport_params is None:
                    transport_params = TransportParameters()
                    
                input_string = self._generate_direct_phreeqc_input(
                    column_params, feed_composition, transport_params
                )
                
                # Run simulation
                results = direct_engine.run_ix_simulation(
                    input_string,
                    feed_ca=feed_composition.get('Ca', 0),
                    feed_mg=feed_composition.get('Mg', 0)
                )
                
                logger.info(f"Direct PHREEQC simulation complete. Ca breakthrough at {results.get('Ca_breakthrough_BV', 'N/A')} BV")
                return results
                
            except Exception as e:
                logger.warning(f"Direct PHREEQC failed: {e}. Falling back to empirical model.")
                # Fall back to empirical model
                empirical_model = EmpiricalBreakthroughModel(self.resin_type)
                results = empirical_model.calculate_breakthrough(column_params, feed_composition)
                return results
        else:
            # Use PhreeqPython wrapper (original method)
            results = self.run_transport_simulation(
                column_params, feed_composition, transport_params
            )
            
            logger.info(f"Simulation complete. Ca breakthrough at {results.get('Ca_breakthrough_BV', 'N/A')} BV")
            
            return results
    
    def _generate_direct_phreeqc_input(self,
                                     column_params: Dict,
                                     feed_composition: Dict,
                                     transport_params: TransportParameters) -> str:
        """
        Generate PHREEQC input for direct execution (not using wrapper)
        
        Args:
            column_params: Column parameters
            feed_composition: Feed composition
            transport_params: Transport parameters
            
        Returns:
            PHREEQC input string
        """
        # Extract parameters
        bed_volume_m3 = column_params.get('bed_volume_m3', 0.785)
        diameter_m = column_params.get('diameter_m', 1.0)
        bed_depth_m = column_params.get('bed_depth_m', 1.0)
        flow_rate_m3_hr = column_params.get('flow_rate_m3_hr', 10.0)
        porosity = transport_params.porosity
        
        # Calculate parameters
        cross_section = np.pi * (diameter_m/2)**2
        linear_velocity = flow_rate_m3_hr / cross_section / 3600  # m/s
        cell_length = bed_depth_m / transport_params.cells
        
        # Time for 1 BV
        time_for_1_bv = bed_volume_m3 / (flow_rate_m3_hr / 3600)  # seconds
        time_per_shift = time_for_1_bv / transport_params.cells
        
        # Exchange capacity
        capacity_eq_L = self.resin_params['capacity_eq_L']
        exchanger_mol_kg = capacity_eq_L * (1 - porosity) / porosity
        
        input_str = []
        
        # Title
        input_str.append(f"TITLE Ion Exchange - {self.resin_type} Resin")
        input_str.append("")
        
        # Define exchange master species and reactions
        input_str.append("EXCHANGE_MASTER_SPECIES")
        input_str.append("    X     X-")
        input_str.append("")
        
        input_str.append("EXCHANGE_SPECIES")
        input_str.append("    X- = X-")
        input_str.append("        log_k     0.0")
        input_str.append("")
        input_str.append("    Na+ + X- = NaX")
        input_str.append("        log_k     0.0")
        input_str.append("")
        
        # Ca and Mg with selectivity
        K_Ca_Na = self.resin_params['selectivity'].get('Ca/Na', 5.16)
        K_Mg_Na = self.resin_params['selectivity'].get('Mg/Na', 3.29)
        
        input_str.append("    Ca+2 + 2X- = CaX2")
        input_str.append(f"        log_k     {np.log10(K_Ca_Na):.2f}")
        input_str.append("")
        input_str.append("    Mg+2 + 2X- = MgX2")
        input_str.append(f"        log_k     {np.log10(K_Mg_Na):.2f}")
        input_str.append("")
        
        # Feed solution
        input_str.append("SOLUTION 0  # Feed water")
        input_str.append("    units mg/L")
        input_str.append(f"    temp {feed_composition.get('temperature', 25)}")
        input_str.append(f"    pH {feed_composition.get('pH', 7.5)}")
        input_str.append(f"    pe 4")
        
        # Calculate charge balance to determine which ion needs CHARGE keyword
        # Import translator for charge balance calculation
        from ..phreeqc_translator import MCASPhreeqcTranslator
        translator = MCASPhreeqcTranslator()
        
        # Convert to PHREEQC species format for charge calculation
        phreeqc_concs = {}
        ion_mapping = {
            'Ca': 'Ca+2', 'Mg': 'Mg+2', 'Na': 'Na+', 'K': 'K+',
            'Cl': 'Cl-', 'SO4': 'SO4-2', 'HCO3': 'HCO3-'
        }
        
        for ion, phreeqc_species in ion_mapping.items():
            if ion in feed_composition and feed_composition[ion] > 0:
                phreeqc_concs[phreeqc_species] = feed_composition[ion]
        
        # Check charge balance
        is_neutral, charge_imbalance = translator.check_electroneutrality(phreeqc_concs)
        
        # Decide which ion to use for charge balance
        if abs(charge_imbalance) > 0.1:  # Only adjust if significant imbalance
            if charge_imbalance > 0:  # Excess positive charge - need more anions
                balance_ion = 'Cl'  # Adjust Cl- upward
                logger.info(f"Charge imbalance: +{charge_imbalance:.2f} meq/L, using Cl- for balance")
            else:  # Excess negative charge - need more cations
                balance_ion = 'Na'  # Adjust Na+ upward
                logger.info(f"Charge imbalance: {charge_imbalance:.2f} meq/L, using Na+ for balance")
        else:
            balance_ion = None  # No adjustment needed
            logger.info("Solution is already charge balanced")
        
        # Add ions with CHARGE keyword as needed
        phreeqc_mapping = {
            'Ca': 'Ca', 'Mg': 'Mg', 'Na': 'Na', 'K': 'K',
            'Cl': 'Cl', 'SO4': 'S(6)', 'HCO3': 'C(4)'
        }
        
        for ion, phreeqc_name in phreeqc_mapping.items():
            if ion in feed_composition and feed_composition[ion] > 0:
                if ion == balance_ion:
                    input_str.append(f"    {phreeqc_name} {feed_composition[ion]} charge")
                else:
                    input_str.append(f"    {phreeqc_name} {feed_composition[ion]}")
        
        input_str.append("")
        
        # Initial column solution (Na form)
        input_str.append(f"SOLUTION 1-{transport_params.cells}  # Initial column")
        input_str.append("    units mg/L")
        input_str.append(f"    temp {feed_composition.get('temperature', 25)}")
        input_str.append("    pH 7.0")
        input_str.append("    Na 1000")
        input_str.append("    Cl 1540")
        input_str.append("")
        
        # Exchange
        input_str.append(f"EXCHANGE 1-{transport_params.cells}")
        input_str.append(f"    X {exchanger_mol_kg}")
        input_str.append("    -equilibrate 1")
        input_str.append("")
        
        # Transport
        input_str.append("TRANSPORT")
        input_str.append(f"    -cells {transport_params.cells}")
        input_str.append(f"    -shifts {transport_params.shifts}")
        input_str.append(f"    -time_step {time_per_shift:.1f}")
        input_str.append("    -flow_direction forward")
        input_str.append("    -boundary_conditions flux flux")
        input_str.append(f"    -lengths {cell_length}")
        input_str.append(f"    -dispersivities {transport_params.dispersivity}")
        input_str.append(f"    -diffusion_coefficient {transport_params.diffusion_coefficient}")
        input_str.append(f"    -punch_cells {transport_params.cells}")
        input_str.append("    -punch_frequency 1")
        input_str.append("")
        
        # Selected output - include transport-related identifiers
        input_str.append("SELECTED_OUTPUT 1")
        input_str.append("    -file transport.sel")  # Explicit file name
        input_str.append("    -reset false")
        input_str.append("    -sim true")
        input_str.append("    -state true")
        input_str.append("    -dist true")
        input_str.append("    -time true")
        input_str.append("    -step true")
        input_str.append("    -totals Ca Mg Na K Cl S(6) C(4)")
        input_str.append("    -molalities Ca+2 Mg+2 Na+ K+ Cl- SO4-2 HCO3-")
        input_str.append("    -equilibrium_phases")
        input_str.append("")
        
        # User punch for BV and concentrations in mg/L
        input_str.append("USER_PUNCH 1")
        input_str.append("    -headings BV Ca+2_mg/L Mg+2_mg/L Na+_mg/L")
        input_str.append(f"    10 BV = STEP_NO / {transport_params.cells}")
        input_str.append("    20 PUNCH BV")
        input_str.append('    30 PUNCH TOT("Ca") * 40080')
        input_str.append('    40 PUNCH TOT("Mg") * 24305')
        input_str.append('    50 PUNCH TOT("Na") * 22990')
        input_str.append("")
        
        input_str.append("PRINT")
        input_str.append("    -exchange true")
        input_str.append("")
        
        input_str.append("END")
        
        return '\n'.join(input_str)