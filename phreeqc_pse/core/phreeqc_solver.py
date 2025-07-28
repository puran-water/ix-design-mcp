"""
PHREEQC Solver wrapper for GrayBox integration
"""

from typing import Dict, Tuple, Optional, Any
import numpy as np
import logging
from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine
from watertap_ix_transport.transport_core.phreeqc_transport_engine import PhreeqcTransportEngine

logger = logging.getLogger(__name__)


class PhreeqcSolver:
    """
    Solver class that wraps PHREEQC calculations for use in GrayBox models
    """
    
    def __init__(self, 
                 resin_type: str = 'SAC',
                 database: str = 'phreeqc.dat',
                 use_direct_phreeqc: bool = True):
        """
        Initialize PHREEQC solver
        
        Args:
            resin_type: Type of resin ('SAC', 'WAC_H', 'WAC_Na')
            database: PHREEQC database file
            use_direct_phreeqc: Whether to use DirectPhreeqcEngine
        """
        self.resin_type = resin_type
        self.database = database
        self.use_direct_phreeqc = use_direct_phreeqc
        
        # Initialize engines
        if use_direct_phreeqc:
            self.phreeqc_engine = DirectPhreeqcEngine()
        else:
            raise NotImplementedError("Only DirectPhreeqcEngine is currently supported")
        
        # Initialize transport engine for IX calculations
        self.transport_engine = PhreeqcTransportEngine(resin_type=resin_type)
        
        # Cache for performance
        self.last_inputs = None
        self.last_results = None
        
    def solve(self, inputs: Dict[str, float]) -> Dict[str, float]:
        """
        Solve IX equilibrium problem with PHREEQC
        
        Args:
            inputs: Dictionary of input values, expected keys:
                - Flow rates: 'Ca_in', 'Mg_in', 'Na_in', etc. (kg/s)
                - System: 'temperature' (K), 'pressure' (Pa), 'pH'
                - Column: 'bed_volume' (m³), 'flow_rate' (m³/s)
                
        Returns:
            Dictionary of output values:
                - Outlet flows: 'Ca_out', 'Mg_out', 'Na_out', etc. (kg/s)
                - Removal rates: 'Ca_removal', 'Mg_removal', etc. (kg/s)
                - Properties: 'pH_out', 'breakthrough_time' (hours)
        """
        
        # Check cache
        if self.last_inputs == inputs and self.last_results is not None:
            return self.last_results
        
        try:
            # Convert inputs to format expected by transport engine
            column_params, feed_composition = self._prepare_inputs(inputs)
            
            # Run PHREEQC simulation
            phreeqc_results = self.transport_engine.simulate_breakthrough(
                column_params=column_params,
                feed_composition=feed_composition,
                use_direct_phreeqc=self.use_direct_phreeqc
            )
            
            # Process results
            results = self._process_results(inputs, phreeqc_results)
            
            # Update cache
            self.last_inputs = inputs.copy()
            self.last_results = results
            
            return results
            
        except Exception as e:
            logger.error(f"PHREEQC solver failed: {e}")
            # Return safe default values
            return self._get_default_results(inputs)
    
    def _prepare_inputs(self, inputs: Dict[str, float]) -> Tuple[Dict, Dict]:
        """Convert solver inputs to PHREEQC format"""
        
        # Extract system conditions
        temperature = inputs.get('temperature', 298.15) - 273.15  # K to °C
        pressure = inputs.get('pressure', 101325) / 101325  # Pa to atm
        pH = inputs.get('pH', 7.0)
        
        # Extract column parameters
        column_params = {
            'bed_volume_m3': inputs.get('bed_volume', 1.0),
            'diameter_m': inputs.get('bed_diameter', 1.0),
            'bed_depth_m': inputs.get('bed_depth', 1.0),
            'flow_rate_m3_hr': inputs.get('flow_rate', 0.001) * 3600,  # m³/s to m³/hr
            'porosity': inputs.get('porosity', 0.4)
        }
        
        # Extract feed composition (convert kg/s to mg/L)
        flow_rate_m3_s = inputs.get('flow_rate', 0.001)
        if flow_rate_m3_s <= 0:
            flow_rate_m3_s = 0.001
        
        feed_composition = {
            'temperature': temperature,
            'pressure': pressure,
            'pH': pH
        }
        
        # Convert mass flows to concentrations
        for ion in ['Ca', 'Mg', 'Na', 'Cl', 'SO4', 'HCO3']:
            flow_key = f'{ion}_in'
            if flow_key in inputs:
                mass_flow_kg_s = inputs[flow_key]
                # Convert to mg/L: (kg/s) / (m³/s) * 1e6 mg/kg
                conc_mg_L = (mass_flow_kg_s / flow_rate_m3_s) * 1e6
                feed_composition[ion] = conc_mg_L
        
        return column_params, feed_composition
    
    def _process_results(self, inputs: Dict[str, float], 
                        phreeqc_results: Dict[str, Any]) -> Dict[str, float]:
        """Process PHREEQC results into solver outputs"""
        
        results = {}
        
        # Get flow rate for conversions
        flow_rate_m3_s = inputs.get('flow_rate', 0.001)
        
        # Extract outlet concentrations and convert to mass flows
        if 'effluent_concentrations' in phreeqc_results:
            # Use average effluent concentration
            for ion in ['Ca', 'Mg', 'Na', 'Cl', 'SO4', 'HCO3']:
                conc_key = f'effluent_{ion}_mg_L'
                if conc_key in phreeqc_results:
                    conc_array = phreeqc_results[conc_key]
                    if len(conc_array) > 0:
                        # Use concentration after initial breakthrough
                        avg_conc = np.mean(conc_array[1:10]) if len(conc_array) > 10 else np.mean(conc_array)
                        # Convert mg/L to kg/s
                        mass_flow = (avg_conc * flow_rate_m3_s) / 1e6
                        results[f'{ion}_out'] = mass_flow
                        
                        # Calculate removal
                        inlet_flow = inputs.get(f'{ion}_in', 0)
                        results[f'{ion}_removal'] = inlet_flow - mass_flow
        
        # Extract breakthrough time
        if 'Ca_breakthrough_BV' in phreeqc_results:
            bv = phreeqc_results['Ca_breakthrough_BV']
            if bv is not None:
                # Convert BV to hours
                bed_volume = inputs.get('bed_volume', 1.0)
                flow_rate_m3_hr = flow_rate_m3_s * 3600
                results['breakthrough_time'] = (bv * bed_volume) / flow_rate_m3_hr
            else:
                results['breakthrough_time'] = 100.0  # Default high value
        
        # pH (assume slight change for now)
        results['pH_out'] = inputs.get('pH', 7.0) - 0.1
        
        return results
    
    def _get_default_results(self, inputs: Dict[str, float]) -> Dict[str, float]:
        """Return default results when solver fails"""
        
        results = {}
        
        # Pass through most flows with small removal
        for ion in ['Ca', 'Mg', 'Na', 'Cl', 'SO4', 'HCO3']:
            inlet_key = f'{ion}_in'
            if inlet_key in inputs:
                inlet_flow = inputs[inlet_key]
                
                # Apply small removal for cations in SAC
                if self.resin_type == 'SAC' and ion in ['Ca', 'Mg']:
                    removal = 0.1 * inlet_flow
                elif self.resin_type == 'SAC' and ion == 'Na':
                    removal = -0.05 * inlet_flow  # Release
                else:
                    removal = 0
                
                results[f'{ion}_out'] = inlet_flow - removal
                results[f'{ion}_removal'] = removal
        
        results['breakthrough_time'] = 24.0  # Default 24 hours
        results['pH_out'] = inputs.get('pH', 7.0)
        
        return results
    
    def calculate_jacobian(self, inputs: Dict[str, float], 
                          step_size: float = 1e-6) -> np.ndarray:
        """
        Calculate Jacobian matrix for current inputs
        
        Args:
            inputs: Current input values
            step_size: Finite difference step size
            
        Returns:
            Jacobian matrix (n_outputs x n_inputs)
        """
        # This would implement analytical or numerical Jacobian
        # For now, let the GrayBox handle numerical differentiation
        return None