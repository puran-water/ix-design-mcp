"""
Derating factors for ion exchange performance.

This module calculates realistic derating factors that reduce effective
ion exchange capacity from theoretical values based on operational conditions.
"""

from dataclasses import dataclass
from typing import Dict, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class DeratingFactors:
    """Container for all derating factors affecting IX performance."""
    
    fouling_factor: float = 1.0  # 1.0 = no fouling, 0.8 = 20% capacity loss
    regeneration_efficiency: float = 1.0  # 1.0 = complete, 0.95 = 95% regenerated
    channeling_factor: float = 1.0  # 1.0 = perfect flow, 0.9 = 10% channeling
    kinetic_efficiency: float = 1.0  # 1.0 = equilibrium, 0.8 = 80% utilization
    competition_factor: float = 1.0  # 1.0 = no competition, 0.9 = 10% loss
    
    @property
    def total_capacity_factor(self) -> float:
        """Overall capacity derating factor."""
        # Fouling and competition directly reduce available sites
        return self.fouling_factor * self.competition_factor
    
    @property
    def utilization_factor(self) -> float:
        """Fraction of capacity actually utilized."""
        # Regeneration, channeling, and kinetics affect utilization
        return self.regeneration_efficiency * self.channeling_factor * self.kinetic_efficiency


class DeratingCalculator:
    """Calculate derating factors based on water quality and operating conditions."""
    
    def __init__(self):
        """Initialize with typical derating correlations."""
        # Industry typical values
        self.fouling_rates = {
            'low': 0.02,  # 2% per year
            'moderate': 0.05,  # 5% per year
            'high': 0.10,  # 10% per year
        }
        
    def calculate_fouling_factor(self, 
                                feed_composition: Dict,
                                resin_age_years: float = 0,
                                fouling_potential: str = 'moderate') -> float:
        """
        Calculate fouling factor based on feed water quality and resin age.
        
        Args:
            feed_composition: Feed water composition (mg/L)
            resin_age_years: Age of resin in years
            fouling_potential: 'low', 'moderate', or 'high'
            
        Returns:
            Fouling factor (0-1)
        """
        # Estimate fouling based on organics, iron, turbidity
        base_fouling_rate = self.fouling_rates.get(fouling_potential, 0.05)
        
        # Adjust for specific foulants
        if 'TOC' in feed_composition:
            toc = feed_composition['TOC']
            if toc > 5:  # High organic content
                base_fouling_rate *= 1.5
        
        if 'Fe' in feed_composition:
            fe = feed_composition['Fe']
            if fe > 0.3:  # Iron fouling risk
                base_fouling_rate *= 1.2
                
        # Calculate cumulative fouling
        fouling_factor = 1.0 - (base_fouling_rate * resin_age_years)
        fouling_factor = max(0.5, fouling_factor)  # Minimum 50% capacity
        
        logger.info(f"Fouling factor: {fouling_factor:.2f} (age={resin_age_years:.1f} years)")
        return fouling_factor
    
    def calculate_regeneration_efficiency(self,
                                        regenerant_dose_actual: float,
                                        regenerant_dose_design: float = 120.0,
                                        regeneration_level: str = 'standard') -> float:
        """
        Calculate regeneration efficiency based on regenerant dose.
        
        Args:
            regenerant_dose_actual: Actual regenerant dose (kg/m³ resin)
            regenerant_dose_design: Design dose (kg/m³ resin)
            regeneration_level: 'economy', 'standard', or 'thorough'
            
        Returns:
            Regeneration efficiency (0-1)
        """
        # Base efficiency from regeneration level
        base_efficiency = {
            'economy': 0.85,  # Lower dose, some sites remain occupied
            'standard': 0.95,  # Normal operation
            'thorough': 0.98,  # High dose, nearly complete
        }.get(regeneration_level, 0.95)
        
        # Adjust for actual vs design dose
        dose_ratio = regenerant_dose_actual / regenerant_dose_design
        if dose_ratio < 1.0:
            # Reduced efficiency with lower dose
            efficiency = base_efficiency * (0.7 + 0.3 * dose_ratio)
        else:
            # Diminishing returns above design dose
            efficiency = base_efficiency + (1 - base_efficiency) * (1 - np.exp(-2 * (dose_ratio - 1)))
            
        efficiency = min(0.99, efficiency)  # Max 99% efficiency
        
        logger.info(f"Regeneration efficiency: {efficiency:.2f} (dose ratio={dose_ratio:.2f})")
        return efficiency
    
    def calculate_channeling_factor(self,
                                   bed_depth_m: float,
                                   bed_diameter_m: float,
                                   distributor_quality: str = 'good') -> float:
        """
        Calculate channeling factor based on bed geometry and distributor.
        
        Args:
            bed_depth_m: Bed depth in meters
            bed_diameter_m: Bed diameter in meters
            distributor_quality: 'poor', 'good', or 'excellent'
            
        Returns:
            Channeling factor (0-1)
        """
        # Aspect ratio affects channeling
        aspect_ratio = bed_depth_m / bed_diameter_m
        
        # Base channeling from distributor quality
        base_channeling = {
            'poor': 0.20,  # 20% of bed bypassed
            'good': 0.10,  # 10% bypassed
            'excellent': 0.05,  # 5% bypassed
        }.get(distributor_quality, 0.10)
        
        # Adjust for aspect ratio (optimal around 1.5-3.0)
        if aspect_ratio < 1.0:
            # Shallow bed, more channeling
            channeling = base_channeling * 1.5
        elif aspect_ratio > 4.0:
            # Very deep bed, wall effects
            channeling = base_channeling * 1.2
        else:
            channeling = base_channeling
            
        channeling_factor = 1.0 - channeling
        
        logger.info(f"Channeling factor: {channeling_factor:.2f} (L/D={aspect_ratio:.1f})")
        return channeling_factor
    
    def calculate_competition_factor(self,
                                   feed_composition: Dict,
                                   target_ions: list = ['Ca_2+', 'Mg_2+']) -> float:
        """
        Calculate competition factor from non-target ions.
        
        Args:
            feed_composition: Feed water composition (mg/L)
            target_ions: Ions we want to remove
            
        Returns:
            Competition factor (0-1)
        """
        # Calculate total ionic strength
        target_meq = 0
        total_meq = 0
        
        # Common ion charges and molecular weights
        # Handle both MCAS notation (Ca_2+) and simple notation (Ca)
        ion_data = {
            'Ca_2+': (2, 40.08),
            'Ca': (2, 40.08),
            'Mg_2+': (2, 24.31),
            'Mg': (2, 24.31),
            'Na_+': (1, 22.99),
            'Na': (1, 22.99),
            'K_+': (1, 39.10),
            'K': (1, 39.10),
            'NH4_+': (1, 18.04),
            'NH4': (1, 18.04),
            'Fe_2+': (2, 55.85),
            'Fe': (2, 55.85),
            'Mn_2+': (2, 54.94),
            'Mn': (2, 54.94),
            'Ba_2+': (2, 137.33),
            'Ba': (2, 137.33),
            'Sr_2+': (2, 87.62),
            'Sr': (2, 87.62),
        }
        
        for ion, conc in feed_composition.items():
            if ion in ion_data:
                charge, mw = ion_data[ion]
                meq_L = conc * charge / mw
                total_meq += meq_L
                # Check if this ion matches target (handle notation differences)
                is_target = False
                for target in target_ions:
                    if ion == target or ion.split('_')[0] == target.split('_')[0]:
                        is_target = True
                        break
                if is_target:
                    target_meq += meq_L
                    
        if total_meq > 0:
            # Competition reduces effective capacity for target ions
            target_fraction = target_meq / total_meq
            # Higher competition with more non-target ions
            competition_factor = 0.7 + 0.3 * target_fraction
        else:
            competition_factor = 1.0
            
        logger.info(f"Competition factor: {competition_factor:.2f} "
                   f"(target={target_meq:.1f}, total={total_meq:.1f} meq/L)")
        return competition_factor
    
    def calculate_all_factors(self,
                            feed_composition: Dict,
                            column_params: Dict,
                            operating_conditions: Optional[Dict] = None) -> DeratingFactors:
        """
        Calculate all derating factors.
        
        Args:
            feed_composition: Feed water composition
            column_params: Column design parameters
            operating_conditions: Optional operating conditions
            
        Returns:
            DeratingFactors object with all factors
        """
        if operating_conditions is None:
            operating_conditions = {}
            
        # Extract parameters
        bed_depth = column_params.get('bed_depth_m', 2.0)
        bed_diameter = column_params.get('bed_diameter_m', 1.0)
        
        # Calculate individual factors
        fouling = self.calculate_fouling_factor(
            feed_composition,
            operating_conditions.get('resin_age_years', 0),
            operating_conditions.get('fouling_potential', 'moderate')
        )
        
        regeneration = self.calculate_regeneration_efficiency(
            operating_conditions.get('regenerant_dose_actual', 120),
            operating_conditions.get('regenerant_dose_design', 120),
            operating_conditions.get('regeneration_level', 'standard')
        )
        
        channeling = self.calculate_channeling_factor(
            bed_depth,
            bed_diameter,
            operating_conditions.get('distributor_quality', 'good')
        )
        
        competition = self.calculate_competition_factor(
            feed_composition,
            operating_conditions.get('target_ions', ['Ca_2+', 'Mg_2+'])
        )
        
        # Kinetic efficiency already handled by kinetic_model.py
        kinetic = operating_conditions.get('kinetic_efficiency', 1.0)
        
        factors = DeratingFactors(
            fouling_factor=fouling,
            regeneration_efficiency=regeneration,
            channeling_factor=channeling,
            kinetic_efficiency=kinetic,
            competition_factor=competition
        )
        
        logger.info(f"Total capacity factor: {factors.total_capacity_factor:.2f}")
        logger.info(f"Utilization factor: {factors.utilization_factor:.2f}")
        logger.info(f"Effective capacity: {factors.total_capacity_factor * factors.utilization_factor:.2f}")
        
        return factors