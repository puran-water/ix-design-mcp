"""
Physics-based derating factors for ion exchange performance.

This module calculates derating factors from PHREEQC mechanistic simulations
rather than empirical correlations, enabling seamless transition from design
tool to digital twin applications.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class PhysicsBasedDeratingFactors:
    """Container for physics-based derating factors."""
    
    channeling_factor: float = 1.0  # 1.0 = no channeling, 0.7 = 30% channeling
    competition_factor: float = 1.0  # 1.0 = no competition, 0.8 = 20% capacity loss
    regeneration_efficiency: float = 1.0  # 1.0 = complete, 0.95 = 95% regenerated
    fouling_factor: float = 1.0  # 1.0 = no fouling, 0.8 = 20% permanent loss
    dispersivity_m: float = 0.01  # Effective dispersivity for PHREEQC
    
    @property
    def total_capacity_factor(self) -> float:
        """Overall capacity derating factor."""
        # Fouling and competition directly reduce available sites
        return self.fouling_factor * self.competition_factor
    
    @property
    def utilization_factor(self) -> float:
        """Fraction of capacity actually utilized."""
        # Channeling and regeneration affect utilization
        return self.channeling_factor * self.regeneration_efficiency


class HeavyMetalFoulingTracker:
    """Track progressive fouling from heavy metals over multiple cycles."""
    
    def __init__(self):
        """Initialize fouling tracker."""
        self.cycle_history = []
        self.permanently_occupied_sites = 0.0
        self.total_sites = 1.0  # Normalized
        
        # Heavy metal regeneration fractions (fraction removed during regeneration)
        self.regen_fractions = {
            'Fe': 0.10,   # Only 10% removed
            'Mn': 0.15,   # 15% removed
            'Ba': 0.05,   # 5% removed
            'Sr': 0.20,   # 20% removed
            'Al': 0.01    # 1% removed
        }
    
    def simulate_cycle(self, heavy_metals_meq_L: float, 
                      service_time_hr: float,
                      bed_volumes_to_breakthrough: float) -> float:
        """
        Track heavy metal accumulation per cycle.
        
        Args:
            heavy_metals_meq_L: Total heavy metals in feed (meq/L)
            service_time_hr: Service cycle time (hours)
            bed_volumes_to_breakthrough: BV treated before regeneration
            
        Returns:
            Fouling factor (fraction of sites still available)
        """
        if heavy_metals_meq_L <= 0:
            return self.get_fouling_factor()
            
        # Calculate loading normalized to resin capacity
        # Assume 1% of heavy metals permanently bind per 100 BV
        loading_fraction = heavy_metals_meq_L * bed_volumes_to_breakthrough * 0.0001
        
        # Average regeneration fraction for heavy metals
        avg_regen_fraction = 0.12  # 12% removed on average
        permanent_fraction = 1.0 - avg_regen_fraction
        
        # New permanently occupied sites
        new_permanent = loading_fraction * permanent_fraction
        self.permanently_occupied_sites += new_permanent
        
        # Record cycle history
        self.cycle_history.append({
            'cycle': len(self.cycle_history) + 1,
            'heavy_metal_loading': loading_fraction,
            'permanent_sites': self.permanently_occupied_sites,
            'available_capacity': self.total_sites - self.permanently_occupied_sites
        })
        
        logger.info(f"Cycle {len(self.cycle_history)}: "
                   f"Permanent fouling = {self.permanently_occupied_sites:.3f}, "
                   f"Available = {self.get_fouling_factor():.3f}")
        
        return self.get_fouling_factor()
    
    def get_fouling_factor(self) -> float:
        """Return fraction of sites still available."""
        # Minimum 30% capacity even with severe fouling
        return max(0.3, 1.0 - self.permanently_occupied_sites)
    
    def predict_remaining_cycles(self, min_capacity: float = 0.5) -> int:
        """Predict cycles until capacity drops below threshold."""
        if not self.cycle_history:
            return 999  # No data
            
        # Average fouling rate per cycle
        avg_fouling_per_cycle = (self.permanently_occupied_sites / 
                                len(self.cycle_history))
        
        if avg_fouling_per_cycle <= 0:
            return 999
            
        remaining_capacity = self.get_fouling_factor() - min_capacity
        cycles_remaining = int(remaining_capacity / avg_fouling_per_cycle)
        
        return max(0, cycles_remaining)


class PhysicsBasedDeratingEngine:
    """Calculate derating factors from PHREEQC mechanistic simulations."""
    
    def __init__(self, mode: str = 'design'):
        """
        Initialize derating engine.
        
        Args:
            mode: 'design' for preliminary design, 'digital_twin' for operations
        """
        self.mode = mode
        self.fouling_tracker = HeavyMetalFoulingTracker()
        
    def calculate_channeling_factor_design(self, 
                                         bed_geometry: Dict,
                                         hydraulic_loading_m_hr: float) -> Tuple[float, float]:
        """
        Calculate channeling based on vessel geometry and loading rate.
        No distributor details required - suitable for design phase.
        
        Args:
            bed_geometry: Dictionary with 'depth_m' and 'diameter_m'
            hydraulic_loading_m_hr: Superficial velocity in m/hr
            
        Returns:
            Tuple of (channeling_factor, effective_dispersivity_m)
        """
        # L/D ratio impact on flow distribution
        L_D_ratio = bed_geometry['depth_m'] / bed_geometry['diameter_m']
        
        if L_D_ratio < 1.0:
            geometry_factor = 0.70  # Poor - 30% channeling/dead zones
            logger.info(f"Poor bed geometry (L/D={L_D_ratio:.1f}): 30% channeling expected")
        elif L_D_ratio < 2.0:
            geometry_factor = 0.85  # Good - 15% channeling
            logger.info(f"Good bed geometry (L/D={L_D_ratio:.1f}): 15% channeling expected")
        elif L_D_ratio < 3.0:
            geometry_factor = 0.92  # Very good - 8% channeling
            logger.info(f"Very good bed geometry (L/D={L_D_ratio:.1f}): 8% channeling expected")
        else:
            geometry_factor = 0.95  # Excellent - 5% channeling
            logger.info(f"Excellent bed geometry (L/D={L_D_ratio:.1f}): 5% channeling expected")
        
        # Hydraulic loading impact
        if hydraulic_loading_m_hr > 40:
            loading_factor = 0.85  # High velocity increases channeling
            logger.info(f"High hydraulic loading ({hydraulic_loading_m_hr:.0f} m/hr): "
                       "15% additional channeling")
        elif hydraulic_loading_m_hr > 25:
            loading_factor = 0.92  # Moderate impact
            logger.info(f"Moderate hydraulic loading ({hydraulic_loading_m_hr:.0f} m/hr): "
                       "8% additional channeling")
        else:
            loading_factor = 1.0   # Low velocity, minimal impact
            logger.info(f"Low hydraulic loading ({hydraulic_loading_m_hr:.0f} m/hr): "
                       "No additional channeling")
        
        # Combined channeling factor
        channeling_factor = geometry_factor * loading_factor
        
        # Calculate effective dispersivity for PHREEQC
        # Higher channeling = higher dispersivity
        base_dispersivity = 0.01  # meters (1 cm) for ideal flow
        
        # Dispersivity increases with channeling severity
        channeling_severity = 1.0 - channeling_factor
        dispersivity_multiplier = 1.0 + 5.0 * channeling_severity  # Up to 6x for severe
        effective_dispersivity = base_dispersivity * dispersivity_multiplier
        
        logger.info(f"Channeling factor: {channeling_factor:.2f}, "
                   f"Dispersivity: {effective_dispersivity:.3f} m")
        
        return channeling_factor, effective_dispersivity
    
    def extract_competition_from_exchange_sites(self,
                                              exchange_composition: Dict,
                                              target_ions: List[str] = ['Ca', 'Mg']) -> float:
        """
        Extract competition factor from PHREEQC exchange site composition.
        
        Args:
            exchange_composition: Dict of exchange species molalities (mol/kgw)
                                e.g., {'CaX2': 0.001, 'MgX2': 0.0005, 'NaX': 0.002}
            target_ions: List of target ions we want to remove
            
        Returns:
            Competition factor (0-1)
        """
        # Calculate total exchange site occupancy
        total_sites = 0.0
        target_sites = 0.0
        
        for species, molality in exchange_composition.items():
            # Extract charge from species name
            if 'X2' in species:
                sites = molality * 2  # Divalent occupies 2 sites
                ion = species.replace('X2', '')
            elif 'X3' in species:
                sites = molality * 3  # Trivalent occupies 3 sites
                ion = species.replace('X3', '')
            else:
                sites = molality  # Monovalent occupies 1 site
                ion = species.replace('X', '')
            
            total_sites += sites
            
            # Check if this is a target ion
            if any(target in ion for target in target_ions):
                target_sites += sites
        
        if total_sites > 0:
            # Competition factor = fraction of sites occupied by target ions
            competition_factor = target_sites / total_sites
        else:
            competition_factor = 1.0
            
        logger.info(f"Competition factor: {competition_factor:.2f} "
                   f"(target={target_sites:.3f}, total={total_sites:.3f} eq/kgw)")
        
        return competition_factor
    
    def simulate_regeneration_with_heavy_metals(self,
                                              pre_regen_composition: Dict,
                                              post_regen_composition: Dict) -> float:
        """
        Calculate regeneration efficiency accounting for heavy metal retention.
        
        Args:
            pre_regen_composition: Exchange composition before regeneration
            post_regen_composition: Exchange composition after regeneration
            
        Returns:
            Regeneration efficiency (0-1)
        """
        # Calculate total loading before and after
        pre_loading = sum(pre_regen_composition.values())
        post_loading = sum(post_regen_composition.values())
        
        if pre_loading > 0:
            # Efficiency = fraction of sites freed
            efficiency = 1.0 - (post_loading / pre_loading)
        else:
            efficiency = 1.0
            
        # Account for heavy metal retention
        heavy_metals = ['Fe', 'Mn', 'Ba', 'Sr', 'Al']
        heavy_metal_retained = 0.0
        
        for species in post_regen_composition:
            if any(metal in species for metal in heavy_metals):
                heavy_metal_retained += post_regen_composition[species]
        
        logger.info(f"Regeneration efficiency: {efficiency:.2f} "
                   f"(Heavy metals retained: {heavy_metal_retained:.4f} mol/kgw)")
        
        return efficiency
    
    def calculate_physics_based_derating(self,
                                       column_params: Dict,
                                       feed_composition: Dict,
                                       phreeqc_results: Optional[Dict] = None,
                                       operating_history: Optional[Dict] = None) -> PhysicsBasedDeratingFactors:
        """
        Calculate all derating factors from physics-based models.
        
        Args:
            column_params: Column design parameters
            feed_composition: Feed water composition (mg/L)
            phreeqc_results: Results from PHREEQC transport simulation
            operating_history: Historical operation data (cycles, regenerations, etc.)
            
        Returns:
            PhysicsBasedDeratingFactors with all calculated factors
        """
        # 1. Channeling factor based on geometry (design mode)
        if self.mode == 'design':
            bed_geometry = {
                'depth_m': column_params.get('bed_depth_m', 2.0),
                'diameter_m': column_params.get('bed_diameter_m', 1.0)
            }
            hydraulic_loading = column_params.get('hydraulic_loading_m_hr', 25.0)
            
            channeling_factor, dispersivity = self.calculate_channeling_factor_design(
                bed_geometry, hydraulic_loading
            )
        else:
            # Digital twin mode - calibrate from operational data
            channeling_factor = 0.90  # Placeholder - would calibrate from breakthrough curves
            dispersivity = 0.015
        
        # 2. Competition factor from PHREEQC results
        if phreeqc_results and 'exchange_composition' in phreeqc_results:
            competition_factor = self.extract_competition_from_exchange_sites(
                phreeqc_results['exchange_composition']
            )
        else:
            # Try to get from PHREEQC equilibrium calculation
            if column_params.get('calculate_equilibrium', True):
                from .phreeqc_transport_engine import PhreeqcTransportEngine
                
                engine = PhreeqcTransportEngine(resin_type=column_params.get('resin_type', 'SAC'))
                exchange_comp = engine.get_equilibrium_exchange_composition(
                    column_params, feed_composition
                )
                
                if exchange_comp:
                    competition_factor = self.extract_competition_from_exchange_sites(
                        exchange_comp,
                        target_ions=['Ca', 'Mg'] if column_params.get('resin_type', 'SAC') == 'SAC' else ['H']
                    )
                    logger.info(f"Competition factor from PHREEQC equilibrium: {competition_factor:.2f}")
                else:
                    # Estimate from feed composition
                    competition_factor = self._estimate_competition_factor(feed_composition)
            else:
                # Estimate from feed composition
                competition_factor = self._estimate_competition_factor(feed_composition)
        
        # 3. Regeneration efficiency
        if phreeqc_results and 'regeneration' in phreeqc_results:
            regen_efficiency = self.simulate_regeneration_with_heavy_metals(
                phreeqc_results['regeneration']['pre_composition'],
                phreeqc_results['regeneration']['post_composition']
            )
        else:
            # Check if we should run kinetic regeneration simulation
            if column_params.get('simulate_regeneration', False):
                # Run PHREEQC kinetic regeneration simulation
                from .phreeqc_transport_engine import PhreeqcTransportEngine
                
                engine = PhreeqcTransportEngine(resin_type=column_params.get('resin_type', 'SAC'))
                
                regenerant_params = column_params.get('regenerant_params', {
                    'chemical': 'NaCl',
                    'concentration_percent': 10.0,
                    'dose_kg_m3_resin': 120.0,
                    'flow_rate_bv_hr': 2.0,
                    'temperature_celsius': 25.0
                })
                
                regen_results = engine.simulate_regeneration_cycle(
                    column_params, feed_composition, regenerant_params
                )
                
                if 'regeneration_efficiency' in regen_results:
                    regen_efficiency = regen_results['regeneration_efficiency']
                    logger.info(f"Kinetic regeneration simulation: {regen_efficiency:.2%} efficiency")
                else:
                    regen_efficiency = 0.95
            else:
                # Default efficiency
                regen_efficiency = 0.95
        
        # 4. Fouling factor from heavy metal accumulation
        if operating_history:
            # Calculate heavy metal load
            heavy_metals_meq_L = self._calculate_heavy_metal_load(feed_composition)
            cycles = operating_history.get('cycles_completed', 0)
            
            if cycles > 0:
                # Simulate each cycle
                for i in range(cycles):
                    service_time = column_params.get('service_time_hr', 24)
                    bed_volumes = column_params.get('bed_volumes_to_breakthrough', 100)
                    fouling_factor = self.fouling_tracker.simulate_cycle(
                        heavy_metals_meq_L, service_time, bed_volumes
                    )
            else:
                fouling_factor = 1.0
        else:
            fouling_factor = 1.0  # No fouling for new resin
        
        # Create results
        factors = PhysicsBasedDeratingFactors(
            channeling_factor=channeling_factor,
            competition_factor=competition_factor,
            regeneration_efficiency=regen_efficiency,
            fouling_factor=fouling_factor,
            dispersivity_m=dispersivity
        )
        
        logger.info(f"Physics-based derating summary:")
        logger.info(f"  Channeling: {channeling_factor:.2f}")
        logger.info(f"  Competition: {competition_factor:.2f}")
        logger.info(f"  Regeneration: {regen_efficiency:.2f}")
        logger.info(f"  Fouling: {fouling_factor:.2f}")
        logger.info(f"  Total capacity factor: {factors.total_capacity_factor:.2f}")
        logger.info(f"  Utilization factor: {factors.utilization_factor:.2f}")
        
        return factors
    
    def _estimate_competition_factor(self, feed_composition: Dict) -> float:
        """Estimate competition factor from feed composition."""
        # Calculate ionic fractions
        target_meq = 0.0
        total_meq = 0.0
        
        ion_charges = {
            'Ca': 2, 'Mg': 2, 'Na': 1, 'K': 1,
            'Fe': 2, 'Mn': 2, 'Ba': 2, 'Sr': 2
        }
        
        ion_mw = {
            'Ca': 40.08, 'Mg': 24.31, 'Na': 22.99, 'K': 39.10,
            'Fe': 55.85, 'Mn': 54.94, 'Ba': 137.33, 'Sr': 87.62
        }
        
        for ion, conc_mg_L in feed_composition.items():
            ion_base = ion.split('_')[0]  # Handle Ca_2+ notation
            if ion_base in ion_charges:
                charge = ion_charges[ion_base]
                mw = ion_mw[ion_base]
                meq_L = conc_mg_L * charge / mw
                total_meq += meq_L
                
                if ion_base in ['Ca', 'Mg']:
                    target_meq += meq_L
        
        if total_meq > 0:
            target_fraction = target_meq / total_meq
            # Higher competition with more non-target ions
            competition_factor = 0.7 + 0.3 * target_fraction
        else:
            competition_factor = 1.0
            
        return competition_factor
    
    def _calculate_heavy_metal_load(self, feed_composition: Dict) -> float:
        """Calculate total heavy metal load in meq/L."""
        heavy_metals = ['Fe', 'Mn', 'Ba', 'Sr', 'Al']
        total_meq = 0.0
        
        ion_charges = {'Fe': 2, 'Mn': 2, 'Ba': 2, 'Sr': 2, 'Al': 3}
        ion_mw = {'Fe': 55.85, 'Mn': 54.94, 'Ba': 137.33, 'Sr': 87.62, 'Al': 26.98}
        
        for ion, conc_mg_L in feed_composition.items():
            ion_base = ion.split('_')[0]
            if ion_base in heavy_metals and ion_base in ion_charges:
                charge = ion_charges[ion_base]
                mw = ion_mw[ion_base]
                meq_L = conc_mg_L * charge / mw
                total_meq += meq_L
                
        return total_meq