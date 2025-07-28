#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimized Ion Exchange Model with Realistic Industrial Parameters

Based on:
- Helfferich, Ion Exchange (1962)
- Dorfner, Ion Exchangers (1991)
- DuPont/Dow Ion Exchange Resin Technical Manuals
- EPA Design Manual: Removal of Arsenic from Drinking Water by Ion Exchange
"""

import numpy as np
import logging
from typing import Dict, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OptimizedBreakthroughPoint:
    """Breakthrough data point."""
    bed_volumes: float
    time_hours: float
    effluent_concentrations_mg_L: Dict[str, float]
    hardness_mg_L_CaCO3: float
    capacity_utilized_percent: float


class OptimizedIXModel:
    """Optimized IX model with realistic industrial parameters."""
    
    def __init__(self):
        """Initialize with industrial best practices."""
        
        # Realistic selectivity coefficients for modern SAC resins
        # Based on Purolite C100, Amberlite IR120, Dowex 50W-X8
        self.selectivity_industrial = {
            "Ca/Na": 40,    # Typical range: 30-60 at 0.01M
            "Mg/Na": 25,    # Typical range: 20-35 at 0.01M  
            "K/Na": 2.5,    # Typical range: 2-3
            "NH4/Na": 1.9,  # Typical range: 1.5-2.5
            "H/Na": 1.4,    # Typical range: 1.2-1.7
            "Fe2/Na": 50,   # Typical range: 40-70
            "Mn2/Na": 35    # Typical range: 30-45
        }
        
        # Operating efficiency factors based on industry data
        self.efficiency_factors = {
            "regeneration": 0.90,      # 90% regeneration efficiency typical
            "resin_utilization": 0.85, # 85% of sites accessible
            "channeling": 0.95,        # 5% loss to channeling
            "kinetic": 0.92            # 8% loss at typical flow rates
        }
    
    def calculate_realistic_breakthrough(self, column, feed_water: Dict[str, Any], 
                                       flow_rate_L_hr: float) -> List[OptimizedBreakthroughPoint]:
        """
        Calculate breakthrough using industrial correlations.
        
        Key improvements:
        1. Realistic selectivity coefficients
        2. Proper multicomponent equilibrium
        3. Industry-validated efficiency factors
        4. Temperature and ionic strength corrections
        """
        breakthrough_points = []
        
        # Extract water quality
        concentrations = feed_water["ion_concentrations_mg_L"]
        pH = feed_water["pH"]
        temperature = feed_water.get("temperature_celsius", 25)
        
        # Calculate loadings in eq/L
        ca_eq_L = concentrations.get("Ca_2+", 0) / 20.04 / 1000
        mg_eq_L = concentrations.get("Mg_2+", 0) / 12.15 / 1000
        na_eq_L = concentrations.get("Na_+", 0) / 22.99 / 1000
        k_eq_L = concentrations.get("K_+", 0) / 39.10 / 1000
        nh4_eq_L = concentrations.get("NH4_+", 0) / 18.04 / 1000
        
        hardness_eq_L = ca_eq_L + mg_eq_L
        total_cations_eq_L = ca_eq_L + mg_eq_L + na_eq_L + k_eq_L + nh4_eq_L
        
        # Service parameters
        service_flow_BV_hr = flow_rate_L_hr / column.resin_volume_L
        
        # Calculate ionic strength (simplified)
        ionic_strength = 0.5 * (ca_eq_L * 4 + mg_eq_L * 4 + na_eq_L + k_eq_L + nh4_eq_L)
        
        # Selectivity correction for ionic strength (Eisenman equation)
        # K decreases with increasing ionic strength
        ionic_correction = 1 / (1 + 2.5 * np.sqrt(ionic_strength))
        
        # Temperature correction (van't Hoff)
        # ΔH ≈ -2 kcal/mol for Ca/Na exchange
        temp_K = temperature + 273.15
        temp_correction = np.exp(2000/1.987 * (1/298.15 - 1/temp_K))
        
        # Corrected selectivities
        K_Ca_Na = self.selectivity_industrial["Ca/Na"] * ionic_correction * temp_correction
        K_Mg_Na = self.selectivity_industrial["Mg/Na"] * ionic_correction * temp_correction
        K_K_Na = self.selectivity_industrial["K/Na"]
        K_NH4_Na = self.selectivity_industrial["NH4/Na"]
        
        logger.info(f"Corrected selectivities: Ca/Na={K_Ca_Na:.1f}, Mg/Na={K_Mg_Na:.1f}")
        
        # Calculate equilibrium using multicomponent exchange
        # Using the approach from Helfferich for heterovalent exchange
        
        # For divalent-monovalent exchange: K = (q_M2+/q_Na+²) * (C_Na+²/C_M2+)
        # At breakthrough, assume resin is in equilibrium with feed
        
        # Solve for equivalent ionic fractions on resin
        # Using the fact that Σq_i = Q (total capacity)
        
        # Separation factors relative to total monovalent
        alpha_Ca = K_Ca_Na * np.sqrt(ca_eq_L / (na_eq_L + k_eq_L + nh4_eq_L))
        alpha_Mg = K_Mg_Na * np.sqrt(mg_eq_L / (na_eq_L + k_eq_L + nh4_eq_L))
        alpha_K = K_K_Na * k_eq_L / na_eq_L if na_eq_L > 0 else 1
        alpha_NH4 = K_NH4_Na * nh4_eq_L / na_eq_L if na_eq_L > 0 else 1
        
        # Equivalent fraction of hardness on resin at equilibrium
        sum_alpha = 2 * (alpha_Ca + alpha_Mg) + alpha_K + alpha_NH4 + 1  # +1 for Na
        
        hardness_fraction = 2 * (alpha_Ca + alpha_Mg) / sum_alpha
        
        logger.info(f"Equilibrium hardness fraction on resin: {hardness_fraction:.3f}")
        
        # Apply efficiency factors
        base_capacity = column.exchange_capacity_eq_L * column.resin_volume_L
        
        # Regeneration efficiency (incomplete regeneration)
        effective_capacity = base_capacity * self.efficiency_factors["regeneration"]
        
        # Resin utilization (not all sites accessible)
        effective_capacity *= self.efficiency_factors["resin_utilization"]
        
        # Channeling losses
        effective_capacity *= self.efficiency_factors["channeling"]
        
        # Kinetic efficiency based on flow rate
        if service_flow_BV_hr > 25:
            kinetic_eff = 0.85
        elif service_flow_BV_hr > 15:
            kinetic_eff = 0.92 - 0.007 * (service_flow_BV_hr - 15)
        else:
            kinetic_eff = self.efficiency_factors["kinetic"]
        
        effective_capacity *= kinetic_eff
        
        # Usable capacity for hardness removal
        usable_hardness_capacity = effective_capacity * hardness_fraction
        
        # Calculate breakthrough volume
        breakthrough_bv = usable_hardness_capacity / (hardness_eq_L * column.resin_volume_L)
        
        logger.info(f"Capacity breakdown:")
        logger.info(f"  Base capacity: {base_capacity:.0f} eq")
        logger.info(f"  Effective capacity: {effective_capacity:.0f} eq ({effective_capacity/base_capacity*100:.0f}%)")
        logger.info(f"  Usable for hardness: {usable_hardness_capacity:.0f} eq")
        logger.info(f"  Predicted breakthrough: {breakthrough_bv:.0f} BV")
        
        # Generate breakthrough curve
        # Using the Clark model for breakthrough curve shape
        # More realistic than simple logistic function
        
        k_clark = 0.02  # Rate constant, BV^-1 (typical for SAC resins)
        n_clark = 2.5   # Shape factor (2-3 typical for ion exchange)
        
        for bv in np.arange(0, breakthrough_bv * 1.3, 10):
            if bv == 0:
                c_c0 = 0.001
            else:
                # Clark model
                tau = bv / breakthrough_bv
                if tau < 1:
                    c_c0 = 1 - (1 + (n_clark - 1) * k_clark * breakthrough_bv * tau)**(-1/(n_clark-1))
                else:
                    c_c0 = 1 - np.exp(-k_clark * breakthrough_bv * (tau - 1))
                
                # Ensure reasonable bounds
                c_c0 = max(0.001, min(0.999, c_c0))
            
            # Calculate effluent
            effluent = {}
            for ion, conc in concentrations.items():
                if ion in ["Ca_2+", "Mg_2+", "Fe_2+", "Mn_2+"]:
                    effluent[ion] = conc * c_c0
                elif ion == "Na_+":
                    # Stoichiometric release of Na+
                    ca_removed = concentrations.get("Ca_2+", 0) * (1 - c_c0) / 20.04
                    mg_removed = concentrations.get("Mg_2+", 0) * (1 - c_c0) / 12.15
                    na_released = (ca_removed + mg_removed) * 2 * 22.99  # 2 Na+ per divalent
                    effluent[ion] = na_eq_L * 22.99 * 1000 + na_released
                else:
                    effluent[ion] = conc  # Anions pass through
            
            # Calculate hardness
            hardness = effluent.get("Ca_2+", 0) * 2.5 + effluent.get("Mg_2+", 0) * 4.1
            
            # Time and capacity
            time_hours = bv / service_flow_BV_hr
            capacity_percent = min(100, bv / breakthrough_bv * 100)
            
            breakthrough_points.append(OptimizedBreakthroughPoint(
                bed_volumes=bv,
                time_hours=time_hours,
                effluent_concentrations_mg_L=effluent,
                hardness_mg_L_CaCO3=hardness,
                capacity_utilized_percent=capacity_percent
            ))
            
            # Stop at 50 mg/L hardness
            if hardness > 50:
                break
        
        return breakthrough_points
    
    def validate_model(self, predicted_bv: float, water_quality: str) -> Dict[str, Any]:
        """Validate model predictions against typical industrial performance."""
        
        # Industrial benchmarks by water quality
        benchmarks = {
            "low_tds": {"range": (800, 1200), "tds": "<500 mg/L"},
            "medium_tds": {"range": (600, 800), "tds": "500-1000 mg/L"},
            "high_tds": {"range": (400, 600), "tds": ">1000 mg/L"}
        }
        
        benchmark = benchmarks.get(water_quality, benchmarks["medium_tds"])
        min_bv, max_bv = benchmark["range"]
        
        within_range = min_bv <= predicted_bv <= max_bv
        
        return {
            "predicted_bv": predicted_bv,
            "expected_range": benchmark["range"],
            "within_range": within_range,
            "tds_category": benchmark["tds"]
        }