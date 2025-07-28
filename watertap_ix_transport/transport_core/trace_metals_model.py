"""
Trace Metals Competition Model for Ion Exchange

This module handles the impact of trace metals (Fe, Mn, Al, Ba, Sr, NH4) 
on ion exchange performance. These metals often have very high selectivity
and can significantly reduce operating capacity even at low concentrations.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TraceMetal:
    """Properties of a trace metal for ion exchange"""
    name: str
    symbol: str
    charge: int
    molecular_weight: float
    selectivity_vs_Na: float  # Selectivity coefficient relative to Na+
    fouling_potential: float  # 0-1, tendency to cause irreversible fouling
    typical_limit_mg_L: float  # Typical design limit for good performance


# Database of trace metals and their properties
TRACE_METALS = {
    'Fe2+': TraceMetal('Iron(II)', 'Fe', 2, 55.845, 500, 0.8, 0.3),
    'Fe3+': TraceMetal('Iron(III)', 'Fe', 3, 55.845, 5000, 0.9, 0.1),
    'Mn2+': TraceMetal('Manganese', 'Mn', 2, 54.938, 400, 0.7, 0.3),
    'Al3+': TraceMetal('Aluminum', 'Al', 3, 26.982, 3000, 0.8, 0.1),
    'Ba2+': TraceMetal('Barium', 'Ba', 2, 137.33, 500, 0.3, 0.05),
    'Sr2+': TraceMetal('Strontium', 'Sr', 2, 87.62, 125, 0.2, 0.1),
    'NH4+': TraceMetal('Ammonium', 'NH4', 1, 18.04, 1.5, 0.1, 1.0),
    'Cu2+': TraceMetal('Copper', 'Cu', 2, 63.546, 600, 0.6, 0.1),
    'Zn2+': TraceMetal('Zinc', 'Zn', 2, 65.38, 450, 0.5, 0.1),
    'Pb2+': TraceMetal('Lead', 'Pb', 2, 207.2, 800, 0.7, 0.01),
}


class TraceMetalsModel:
    """
    Model the competition effects of trace metals in ion exchange.
    
    Trace metals impact performance through:
    1. Direct competition for exchange sites (high selectivity)
    2. Precipitation and fouling at high pH
    3. Oxidation state changes (Fe2+ → Fe3+)
    4. Complex formation reducing effective concentration
    """
    
    def __init__(self):
        """Initialize trace metals model"""
        self.metals_db = TRACE_METALS
        
    def calculate_trace_metal_impact(self, 
                                   water_quality: Dict[str, float],
                                   resin_type: str = "SAC") -> Dict[str, float]:
        """
        Calculate the impact of trace metals on ion exchange capacity.
        
        Args:
            water_quality: Dictionary with metal concentrations in mg/L
            resin_type: Type of resin (affects selectivity)
            
        Returns:
            Dictionary with impact metrics
        """
        results = {
            'total_trace_eq_L': 0.0,
            'capacity_loss_fraction': 0.0,
            'fouling_risk': 'low',
            'critical_metals': [],
            'recommendations': []
        }
        
        # Calculate equivalent concentration of trace metals
        trace_metals_eq = []
        fouling_scores = []
        
        for metal_ion, metal_data in self.metals_db.items():
            conc_mg_L = water_quality.get(metal_ion, 0.0)
            
            if conc_mg_L > 0:
                # Convert to eq/L
                eq_L = (conc_mg_L / 1000) * metal_data.charge / metal_data.molecular_weight
                
                # Weight by selectivity (higher selectivity = more impact)
                if resin_type == "SAC":
                    selectivity_factor = np.log10(metal_data.selectivity_vs_Na + 1)
                else:  # WAC
                    # WAC has different selectivity pattern
                    selectivity_factor = np.log10(metal_data.selectivity_vs_Na + 1) * 0.7
                
                weighted_eq_L = eq_L * selectivity_factor
                trace_metals_eq.append(weighted_eq_L)
                
                # Track critical metals
                if conc_mg_L > metal_data.typical_limit_mg_L:
                    results['critical_metals'].append({
                        'metal': metal_ion,
                        'concentration': conc_mg_L,
                        'limit': metal_data.typical_limit_mg_L,
                        'ratio': conc_mg_L / metal_data.typical_limit_mg_L
                    })
                
                # Calculate fouling risk
                fouling_score = conc_mg_L * metal_data.fouling_potential
                fouling_scores.append(fouling_score)
                
                logger.info(f"{metal_ion}: {conc_mg_L} mg/L = {eq_L:.4f} eq/L "
                          f"(weighted: {weighted_eq_L:.4f} eq/L)")
        
        # Total trace metal loading
        results['total_trace_eq_L'] = sum(trace_metals_eq)
        
        # Estimate capacity loss
        # Trace metals occupy sites but don't contribute to service
        # Rule of thumb: 1 eq/L trace metals = 10-20% capacity loss
        capacity_loss = min(0.5, results['total_trace_eq_L'] * 15)
        results['capacity_loss_fraction'] = capacity_loss
        
        # Fouling risk assessment
        total_fouling_score = sum(fouling_scores)
        if total_fouling_score > 1.0:
            results['fouling_risk'] = 'high'
        elif total_fouling_score > 0.5:
            results['fouling_risk'] = 'medium'
        else:
            results['fouling_risk'] = 'low'
            
        # Generate recommendations
        results['recommendations'] = self._generate_recommendations(
            results['critical_metals'], 
            results['fouling_risk'],
            resin_type
        )
        
        return results
    
    def _generate_recommendations(self, 
                                critical_metals: List[Dict],
                                fouling_risk: str,
                                resin_type: str) -> List[str]:
        """Generate treatment recommendations based on trace metals"""
        recommendations = []
        
        # Check for specific metals
        metals_present = {m['metal'] for m in critical_metals}
        
        if any(m in metals_present for m in ['Fe2+', 'Fe3+']):
            recommendations.append("Iron removal recommended: aeration + filtration or oxidation")
            
        if 'Mn2+' in metals_present:
            recommendations.append("Manganese removal: oxidation (ClO2 or KMnO4) + filtration")
            
        if 'Al3+' in metals_present:
            recommendations.append("Aluminum control: maintain pH < 6.5 or coagulation removal")
            
        if any(m in metals_present for m in ['Ba2+', 'Sr2+']):
            recommendations.append("Barium/Strontium: consider softening pretreatment")
            
        if 'NH4+' in metals_present:
            if resin_type == "SAC":
                recommendations.append("Ammonium competes strongly with Na+, consider biological treatment")
            
        # Fouling risk recommendations
        if fouling_risk == 'high':
            recommendations.append("High fouling risk: implement aggressive pretreatment")
            recommendations.append("Consider more frequent regenerations or resin cleaning")
        elif fouling_risk == 'medium':
            recommendations.append("Medium fouling risk: monitor resin capacity closely")
            
        # General recommendations
        if len(critical_metals) > 2:
            recommendations.append("Multiple trace metals present: comprehensive pretreatment needed")
            
        return recommendations
    
    def add_trace_metals_to_phreeqc(self, feed_composition: Dict[str, float]) -> Dict[str, float]:
        """
        Add trace metals to PHREEQC feed composition with proper speciation.
        
        Args:
            feed_composition: Base feed water composition
            
        Returns:
            Updated composition with trace metals
        """
        updated = feed_composition.copy()
        
        # Add trace metals if present
        for metal_ion in self.metals_db.keys():
            if metal_ion in feed_composition and feed_composition[metal_ion] > 0:
                # Handle special cases
                if metal_ion == 'Fe2+':
                    # PHREEQC uses Fe(2) notation
                    updated['Fe(2)'] = feed_composition[metal_ion]
                elif metal_ion == 'Fe3+':
                    # PHREEQC uses Fe(3) notation
                    updated['Fe(3)'] = feed_composition[metal_ion]
                elif metal_ion == 'NH4+':
                    # PHREEQC uses Amm for ammonium
                    # Keep as NH4+ concentration
                    updated['Amm'] = feed_composition[metal_ion]
                else:
                    # Most metals use element symbol
                    element = metal_ion.rstrip('0123456789+-')
                    updated[element] = feed_composition[metal_ion]
                    
        return updated
    
    def estimate_service_life_reduction(self,
                                      trace_metal_impact: Dict[str, float],
                                      base_service_life_BV: float) -> float:
        """
        Estimate reduction in service life due to trace metals.
        
        Args:
            trace_metal_impact: Results from calculate_trace_metal_impact
            base_service_life_BV: Expected BV without trace metals
            
        Returns:
            Adjusted service life in BV
        """
        # Direct capacity loss
        capacity_factor = 1.0 - trace_metal_impact['capacity_loss_fraction']
        
        # Additional reduction for fouling risk
        fouling_factors = {
            'low': 1.0,
            'medium': 0.85,
            'high': 0.7
        }
        fouling_factor = fouling_factors[trace_metal_impact['fouling_risk']]
        
        # Combined effect
        adjusted_life = base_service_life_BV * capacity_factor * fouling_factor
        
        logger.info(f"Service life adjustment:")
        logger.info(f"  Base: {base_service_life_BV:.0f} BV")
        logger.info(f"  Capacity factor: {capacity_factor:.2f}")
        logger.info(f"  Fouling factor: {fouling_factor:.2f}")
        logger.info(f"  Adjusted: {adjusted_life:.0f} BV")
        
        return adjusted_life


def add_trace_metal_selectivity_to_phreeqc(input_lines: List[str], 
                                          resin_type: str = "SAC",
                                          metals_present: Optional[List[str]] = None) -> List[str]:
    """
    Add trace metal exchange reactions to PHREEQC input.
    
    Args:
        input_lines: Existing PHREEQC input lines
        resin_type: Type of resin
        metals_present: List of metals actually in the feed
        
    Returns:
        Updated input lines with trace metal reactions
    """
    # Find where to insert (after EXCHANGE_SPECIES)
    insert_index = None
    for i, line in enumerate(input_lines):
        if line.strip() == "EXCHANGE_SPECIES":
            # Find the last exchange reaction
            j = i + 1
            while j < len(input_lines) and input_lines[j].strip() != "":
                j += 1
            insert_index = j
            break
    
    if insert_index is None:
        return input_lines
    
    # Add trace metal reactions
    trace_reactions = []
    
    if resin_type in ["SAC", "WAC_Na"]:
        trace_reactions.append("    # Trace metal exchange reactions")
        
        # Only add reactions for metals that are present
        if metals_present is None:
            metals_present = []
            
        if 'Fe' in metals_present or 'Fe(2)' in metals_present:
            trace_reactions.extend([
                "    Fe+2 + 2X- = FeX2",
                "    log_k 2.7  # K = 500"
            ])
        if 'Mn' in metals_present:
            trace_reactions.extend([
                "    Mn+2 + 2X- = MnX2", 
                "    log_k 2.6  # K = 400"
            ])
        if 'Al' in metals_present:
            trace_reactions.extend([
                "    Al+3 + 3X- = AlX3",
                "    log_k 3.5  # K = 3000"
            ])
        if 'Ba' in metals_present:
            trace_reactions.extend([
                "    Ba+2 + 2X- = BaX2",
                "    log_k 2.7  # K = 500"
            ])
        if 'Sr' in metals_present:
            trace_reactions.extend([
                "    Sr+2 + 2X- = SrX2",
                "    log_k 2.1  # K = 125"
            ])
        if 'Amm' in metals_present:
            trace_reactions.extend([
                "    Amm+ + X- = AmmX",
                "    log_k 0.18  # K = 1.5"
            ])
    
    # Only insert if we have reactions to add
    if len(trace_reactions) > 1:  # More than just the header
        updated_lines = (input_lines[:insert_index] + 
                        trace_reactions + 
                        input_lines[insert_index:])
        return updated_lines
    else:
        return input_lines


# Example usage
if __name__ == "__main__":
    # Test water with trace metals
    water = {
        'Ca': 100,      # mg/L
        'Mg': 40,       # mg/L
        'Na': 150,      # mg/L
        'Fe2+': 0.5,    # mg/L - above limit
        'Mn2+': 0.2,    # mg/L - at limit
        'Al3+': 0.1,    # mg/L
        'NH4+': 2.0,    # mg/L - significant
    }
    
    model = TraceMetalsModel()
    impact = model.calculate_trace_metal_impact(water, resin_type="SAC")
    
    print("\nTrace Metal Impact Analysis:")
    print(f"Total trace metals: {impact['total_trace_eq_L']:.4f} eq/L")
    print(f"Capacity loss: {impact['capacity_loss_fraction']*100:.1f}%")
    print(f"Fouling risk: {impact['fouling_risk']}")
    
    if impact['critical_metals']:
        print("\nCritical metals exceeding limits:")
        for metal in impact['critical_metals']:
            print(f"  {metal['metal']}: {metal['concentration']} mg/L "
                  f"(limit: {metal['limit']} mg/L, {metal['ratio']:.1f}x)")
    
    if impact['recommendations']:
        print("\nRecommendations:")
        for rec in impact['recommendations']:
            print(f"  - {rec}")
    
    # Service life impact
    base_life = 500  # BV
    adjusted_life = model.estimate_service_life_reduction(impact, base_life)
    print(f"\nService life impact:")
    print(f"  Without trace metals: {base_life} BV")
    print(f"  With trace metals: {adjusted_life:.0f} BV")
    print(f"  Reduction: {(1 - adjusted_life/base_life)*100:.0f}%")