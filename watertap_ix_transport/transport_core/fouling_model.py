"""
Fouling Model for Ion Exchange Resins

This module implements physical fouling models based on water quality parameters
like TOC, TSS, and other measurable factors that reduce ion exchange capacity.
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FoulingFactors:
    """Factors that contribute to resin fouling"""
    TOC_mg_L: float = 0.0  # Total Organic Carbon
    UV254_abs_cm: float = 0.0  # UV absorbance at 254nm (aromatic organics)
    TSS_mg_L: float = 0.0  # Total Suspended Solids
    Fe_mg_L: float = 0.0  # Iron (causes precipitation)
    Al_mg_L: float = 0.0  # Aluminum (causes precipitation)
    oil_grease_mg_L: float = 0.0  # Oil and grease
    oxidant_exposure_mg_L_days: float = 0.0  # Cumulative chlorine exposure
    resin_age_years: float = 0.0  # Age of resin


class FoulingModel:
    """
    Calculate capacity reduction due to fouling based on water quality.
    
    This model uses empirical correlations from literature and field data
    to estimate how various contaminants reduce effective resin capacity.
    """
    
    def __init__(self):
        """Initialize fouling model with default parameters"""
        # Fouling coefficients (based on literature review)
        self.toc_coefficient = 0.04  # 4% capacity loss per mg/L TOC
        self.tss_coefficient = 0.02  # 2% capacity loss per mg/L TSS
        self.iron_coefficient = 0.10  # 10% capacity loss per mg/L Fe
        self.oil_coefficient = 0.20  # 20% capacity loss per mg/L oil
        self.age_coefficient = 0.03  # 3% capacity loss per year
        
        # Maximum fouling limits
        self.max_toc_fouling = 0.40  # 40% max from TOC
        self.max_tss_fouling = 0.20  # 20% max from TSS
        self.max_iron_fouling = 0.30  # 30% max from iron
        self.max_total_fouling = 0.70  # 70% max total fouling
        
    def calculate_fouling_factor(self, 
                                factors: FoulingFactors,
                                resin_type: str = "SAC") -> float:
        """
        Calculate overall fouling factor (0-1) based on water quality.
        
        Args:
            factors: Water quality and operational factors
            resin_type: Type of resin (affects fouling susceptibility)
            
        Returns:
            Fouling factor (1.0 = no fouling, 0.3 = 70% fouled)
        """
        fouling_components = {}
        
        # Organic fouling (TOC and UV254)
        toc_fouling = min(
            factors.TOC_mg_L * self.toc_coefficient,
            self.max_toc_fouling
        )
        
        # UV254 indicates aromatic organics (worse foulers)
        if factors.UV254_abs_cm > 0:
            aromatic_factor = min(factors.UV254_abs_cm / 0.1, 2.0)  # Double impact for high UV254
            toc_fouling *= aromatic_factor
            
        fouling_components['organic'] = toc_fouling
        
        # Suspended solids fouling
        tss_fouling = min(
            factors.TSS_mg_L * self.tss_coefficient,
            self.max_tss_fouling
        )
        fouling_components['solids'] = tss_fouling
        
        # Iron/aluminum precipitation fouling
        metal_fouling = min(
            factors.Fe_mg_L * self.iron_coefficient + 
            factors.Al_mg_L * self.iron_coefficient * 1.5,  # Al is worse
            self.max_iron_fouling
        )
        fouling_components['metals'] = metal_fouling
        
        # Oil and grease fouling (very severe)
        oil_fouling = min(
            factors.oil_grease_mg_L * self.oil_coefficient,
            0.50  # 50% max from oil
        )
        fouling_components['oil'] = oil_fouling
        
        # Oxidative degradation
        oxidation_fouling = 0.0
        if factors.oxidant_exposure_mg_L_days > 0:
            # SAC resins are more resistant to oxidation
            oxidation_rate = 0.0001 if resin_type == "SAC" else 0.0002
            oxidation_fouling = min(
                factors.oxidant_exposure_mg_L_days * oxidation_rate,
                0.30  # 30% max from oxidation
            )
        fouling_components['oxidation'] = oxidation_fouling
        
        # Age-related capacity loss
        age_fouling = min(
            factors.resin_age_years * self.age_coefficient,
            0.20  # 20% max from age
        )
        fouling_components['age'] = age_fouling
        
        # Resin-type specific adjustments
        if resin_type == "WAC_H" or resin_type == "WAC_Na":
            # WAC resins are more resistant to organic fouling
            fouling_components['organic'] *= 0.7
            # But more susceptible to metal fouling
            fouling_components['metals'] *= 1.3
            
        # Calculate total fouling (not simply additive)
        # Use root-sum-square for combined effect
        total_fouling_squared = sum(f**2 for f in fouling_components.values())
        total_fouling = min(total_fouling_squared**0.5, self.max_total_fouling)
        
        # Log detailed breakdown
        logger.info(f"Fouling breakdown for {resin_type}:")
        for component, value in fouling_components.items():
            if value > 0:
                logger.info(f"  {component}: {value*100:.1f}% capacity loss")
        logger.info(f"  Total fouling: {total_fouling*100:.1f}% capacity loss")
        
        # Return capacity retention factor
        return 1.0 - total_fouling
        
    def calculate_effective_capacity(self,
                                   total_capacity_eq_L: float,
                                   factors: FoulingFactors,
                                   resin_type: str = "SAC") -> float:
        """
        Calculate effective capacity after fouling.
        
        Args:
            total_capacity_eq_L: Clean resin total capacity
            factors: Fouling factors
            resin_type: Type of resin
            
        Returns:
            Effective capacity in eq/L
        """
        fouling_factor = self.calculate_fouling_factor(factors, resin_type)
        return total_capacity_eq_L * fouling_factor
        
    def recommend_pretreatment(self, factors: FoulingFactors) -> Dict[str, str]:
        """
        Recommend pretreatment based on fouling factors.
        
        Args:
            factors: Water quality factors
            
        Returns:
            Dictionary of recommendations
        """
        recommendations = {}
        
        if factors.TOC_mg_L > 5:
            recommendations['organics'] = "Consider activated carbon or coagulation for TOC removal"
            
        if factors.TSS_mg_L > 5:
            recommendations['solids'] = "Install multimedia filter for TSS < 5 mg/L"
            
        if factors.Fe_mg_L > 0.3:
            recommendations['iron'] = "Add iron removal (oxidation + filtration)"
            
        if factors.oil_grease_mg_L > 1:
            recommendations['oil'] = "Critical: Install oil removal system"
            
        if factors.UV254_abs_cm > 0.1:
            recommendations['aromatics'] = "High aromatic content - consider advanced oxidation"
            
        return recommendations


def estimate_fouling_from_basic_parameters(water_quality: Dict[str, float]) -> FoulingFactors:
    """
    Estimate fouling factors from basic water quality parameters.
    
    When detailed analysis isn't available, estimate fouling potential
    from commonly measured parameters.
    
    Args:
        water_quality: Basic water quality dict
        
    Returns:
        Estimated fouling factors
    """
    factors = FoulingFactors()
    
    # Estimate TOC from source type
    source = water_quality.get('source_type', 'surface')
    if source == 'surface':
        factors.TOC_mg_L = water_quality.get('TOC_mg_L', 3.0)  # Typical surface water
    elif source == 'groundwater':
        factors.TOC_mg_L = water_quality.get('TOC_mg_L', 1.0)  # Typical groundwater
    else:  # industrial
        factors.TOC_mg_L = water_quality.get('TOC_mg_L', 5.0)  # Conservative estimate
        
    # Estimate TSS
    turbidity = water_quality.get('turbidity_NTU', 1.0)
    factors.TSS_mg_L = water_quality.get('TSS_mg_L', turbidity * 1.5)  # Rough correlation
    
    # Get metals if available
    factors.Fe_mg_L = water_quality.get('Fe_mg_L', 0.0)
    factors.Al_mg_L = water_quality.get('Al_mg_L', 0.0)
    
    # Industrial indicators
    if water_quality.get('industrial', False):
        factors.oil_grease_mg_L = water_quality.get('oil_grease_mg_L', 0.5)
        
    # Age estimate
    factors.resin_age_years = water_quality.get('resin_age_years', 2.0)  # Assume 2 years if unknown
    
    return factors


# Example usage
if __name__ == "__main__":
    # Test with typical industrial water
    industrial_factors = FoulingFactors(
        TOC_mg_L=8.0,
        UV254_abs_cm=0.15,
        TSS_mg_L=10.0,
        Fe_mg_L=0.5,
        resin_age_years=3.0
    )
    
    model = FoulingModel()
    fouling_factor = model.calculate_fouling_factor(industrial_factors, "SAC")
    print(f"\nFouling factor: {fouling_factor:.2f}")
    print(f"Capacity retained: {fouling_factor*100:.0f}%")
    
    # Calculate effective capacity
    total_capacity = 2.0  # eq/L for SAC
    effective = model.calculate_effective_capacity(total_capacity, industrial_factors, "SAC")
    print(f"\nTotal capacity: {total_capacity} eq/L")
    print(f"Effective capacity: {effective:.2f} eq/L")
    
    # Get recommendations
    recommendations = model.recommend_pretreatment(industrial_factors)
    if recommendations:
        print("\nPretreatment recommendations:")
        for issue, solution in recommendations.items():
            print(f"  {issue}: {solution}")