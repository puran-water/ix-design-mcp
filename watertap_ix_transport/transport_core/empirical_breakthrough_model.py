"""
Empirical breakthrough model for ion exchange
Used as alternative to PHREEQC when exchange modeling fails
"""

import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class EmpiricalBreakthroughModel:
    """
    Empirical model for ion exchange breakthrough curves
    Uses Thomas model and mass balance calculations
    """
    
    def __init__(self, resin_type: str):
        self.resin_type = resin_type
        
        # Default parameters for different resin types
        self.resin_params = {
            'SAC': {
                'capacity_eq_L': 2.0,
                'k_thomas': 0.001,  # L/(mg*min)
                'selectivity': {'Ca/Na': 5.16, 'Mg/Na': 3.29}
            },
            'WAC_Na': {
                'capacity_eq_L': 4.0,
                'k_thomas': 0.0008,
                'selectivity': {'Ca/Na': 50.0, 'Mg/Na': 25.0}
            },
            'WAC_H': {
                'capacity_eq_L': 4.0,
                'k_thomas': 0.0012,
                'selectivity': {'Ca/H': 1000.0, 'Mg/H': 500.0}
            }
        }
        
        self.params = self.resin_params.get(resin_type, self.resin_params['SAC'])
    
    def calculate_breakthrough(self, 
                             column_params: Dict,
                             feed_composition: Dict,
                             num_points: int = 500) -> Dict:
        """
        Calculate breakthrough curves using Thomas model
        
        Args:
            column_params: Column design parameters
            feed_composition: Feed water composition
            num_points: Number of points in breakthrough curve
            
        Returns:
            Dict with breakthrough results
        """
        # Extract parameters
        bed_volume_m3 = column_params.get('bed_volume_m3', 0.785)
        flow_rate_m3_hr = column_params.get('flow_rate_m3_hr', 10.0)
        porosity = column_params.get('porosity', 0.4)
        
        # Feed concentrations
        Ca_feed = feed_composition.get('Ca', 40.0)  # mg/L
        Mg_feed = feed_composition.get('Mg', 12.0)  # mg/L
        Na_feed = feed_composition.get('Na', 50.0)  # mg/L
        
        # Calculate resin volume and capacity
        resin_volume_L = bed_volume_m3 * (1 - porosity) * 1000  # L
        total_capacity_eq = resin_volume_L * self.params['capacity_eq_L']
        
        # Calculate equivalent feed concentration
        Ca_meq_L = Ca_feed / 20.04  # mg/L to meq/L
        Mg_meq_L = Mg_feed / 12.15
        total_hardness_meq_L = Ca_meq_L + Mg_meq_L
        
        # Theoretical breakthrough (stoichiometric)
        theoretical_BV = total_capacity_eq / (total_hardness_meq_L * bed_volume_m3)
        
        # Generate bed volume points
        max_BV = min(theoretical_BV * 2, 1000)  # Cap at 1000 BV
        bed_volumes = np.linspace(0, max_BV, num_points)
        
        # Thomas model parameters
        k_Ca = self.params['k_thomas'] * self.params['selectivity']['Ca/Na']
        k_Mg = self.params['k_thomas'] * self.params['selectivity']['Mg/Na']
        
        # Mass of resin
        resin_mass_g = resin_volume_L * 800  # Assume 800 g/L bulk density
        
        # Calculate breakthrough curves
        Ca_effluent = []
        Mg_effluent = []
        Na_effluent = []
        
        for BV in bed_volumes:
            # Volume treated
            V_L = BV * bed_volume_m3 * 1000
            
            # Thomas model: C/C0 = 1 / (1 + exp(k*q0*m/Q - k*C0*V/Q))
            # where q0 = max capacity, m = mass resin, Q = flow rate, V = volume
            
            # For Ca
            exponent_Ca = k_Ca * self.params['capacity_eq_L'] * 1000 * resin_mass_g / (flow_rate_m3_hr * 1000) - k_Ca * Ca_feed * V_L / (flow_rate_m3_hr * 1000)
            C_Ca_ratio = 1 / (1 + np.exp(exponent_Ca))
            Ca_effluent.append(Ca_feed * C_Ca_ratio)
            
            # For Mg
            exponent_Mg = k_Mg * self.params['capacity_eq_L'] * 1000 * resin_mass_g / (flow_rate_m3_hr * 1000) - k_Mg * Mg_feed * V_L / (flow_rate_m3_hr * 1000)
            C_Mg_ratio = 1 / (1 + np.exp(exponent_Mg))
            Mg_effluent.append(Mg_feed * C_Mg_ratio)
            
            # For Na (release)
            # Assume stoichiometric release based on hardness removal
            hardness_removed = (Ca_feed - Ca_effluent[-1]) / 20.04 + (Mg_feed - Mg_effluent[-1]) / 12.15
            Na_released = hardness_removed * 23.0  # meq/L to mg/L Na
            Na_effluent.append(Na_feed + Na_released)
        
        # Find breakthrough points (5% of feed)
        Ca_breakthrough_BV = None
        Mg_breakthrough_BV = None
        
        for i, BV in enumerate(bed_volumes):
            if Ca_breakthrough_BV is None and Ca_effluent[i] > 0.05 * Ca_feed:
                Ca_breakthrough_BV = BV
            if Mg_breakthrough_BV is None and Mg_effluent[i] > 0.05 * Mg_feed:
                Mg_breakthrough_BV = BV
        
        # Create concentration profile
        concentration_profile = []
        time_hours = bed_volumes * bed_volume_m3 / flow_rate_m3_hr
        
        for i in range(len(bed_volumes)):
            concentration_profile.append({
                'bed_volumes': bed_volumes[i],
                'time_hours': time_hours[i],
                'Ca': Ca_effluent[i],
                'Mg': Mg_effluent[i],
                'Na': Na_effluent[i]
            })
        
        results = {
            'bed_volumes': bed_volumes.tolist(),
            'time_hours': time_hours.tolist(),
            'effluent_Ca_mg_L': Ca_effluent,
            'effluent_Mg_mg_L': Mg_effluent,
            'effluent_Na_mg_L': Na_effluent,
            'concentration_profile': concentration_profile,
            'Ca_breakthrough_BV': Ca_breakthrough_BV,
            'Mg_breakthrough_BV': Mg_breakthrough_BV,
            'theoretical_breakthrough_BV': theoretical_BV,
            'model_type': 'EMPIRICAL_THOMAS',
            'resin_type': self.resin_type
        }
        
        logger.info(f"Empirical breakthrough calculation complete")
        logger.info(f"  Ca breakthrough: {Ca_breakthrough_BV:.1f} BV" if Ca_breakthrough_BV else "  Ca breakthrough: Not detected")
        logger.info(f"  Mg breakthrough: {Mg_breakthrough_BV:.1f} BV" if Mg_breakthrough_BV else "  Mg breakthrough: Not detected")
        logger.info(f"  Theoretical: {theoretical_BV:.1f} BV")
        
        return results
    
    def calculate_regeneration_efficiency(self,
                                        regenerant_params: Dict,
                                        column_params: Dict) -> Dict:
        """
        Calculate regeneration efficiency based on empirical correlations
        
        Args:
            regenerant_params: Regeneration parameters
            column_params: Column parameters
            
        Returns:
            Dict with regeneration efficiency
        """
        # Extract parameters
        chemical = regenerant_params.get('chemical', 'NaCl')
        concentration = regenerant_params.get('concentration_percent', 10.0)
        dose_kg_m3 = regenerant_params.get('dose_kg_m3_resin', 120.0)
        
        bed_volume_m3 = column_params.get('bed_volume_m3', 0.785)
        porosity = column_params.get('porosity', 0.4)
        
        # Resin volume
        resin_volume_m3 = bed_volume_m3 * (1 - porosity)
        
        # Empirical efficiency correlations
        if chemical == 'NaCl':
            # For SAC: efficiency = 0.4 + 0.02 * conc - 0.001 * dose
            base_efficiency = 0.4
            conc_factor = 0.02 * concentration
            dose_factor = -0.001 * dose_kg_m3
            efficiency = min(0.95, max(0.3, base_efficiency + conc_factor + dose_factor))
            
        elif chemical == 'HCl':
            # For WAC: higher efficiency with acid
            efficiency = min(0.98, 0.7 + 0.03 * concentration)
            
        else:
            # Default
            efficiency = 0.5
        
        # Calculate regenerant usage
        total_regenerant_kg = dose_kg_m3 * resin_volume_m3
        
        results = {
            'regeneration_efficiency': efficiency,
            'regenerant_usage_kg': total_regenerant_kg,
            'regenerant_volume_m3': total_regenerant_kg / (concentration * 10),  # kg / (g/L)
            'model_type': 'EMPIRICAL'
        }
        
        return results