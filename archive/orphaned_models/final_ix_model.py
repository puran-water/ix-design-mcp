#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final Ion Exchange Model - Combining Best Practices

This model combines:
1. Correct unit conversions (eq/L not meq/L)
2. Realistic industrial selectivity coefficients
3. Proper efficiency factors
4. Simple but robust breakthrough curve generation
"""

import numpy as np
import logging
from typing import Dict, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FinalBreakthroughPoint:
    """Breakthrough data point."""
    bed_volumes: float
    time_hours: float
    effluent_concentrations_mg_L: Dict[str, float]
    hardness_mg_L_CaCO3: float
    pH: float


class FinalIXModel:
    """Final IX model combining all improvements."""
    
    def __init__(self):
        """Initialize with best parameters."""
        pass
    
    def calculate_breakthrough_final(self, column, feed_water: Dict[str, Any], 
                                   flow_rate_L_hr: float, 
                                   use_industrial_K: bool = True) -> tuple:
        """
        Calculate breakthrough with all corrections applied.
        
        Returns: (breakthrough_points, summary_dict)
        """
        
        # Extract water quality
        concentrations = feed_water["ion_concentrations_mg_L"]
        pH = feed_water["pH"]
        temperature = feed_water.get("temperature_celsius", 25)
        
        # Convert to eq/L (correct units)
        ca_eq_L = concentrations.get("Ca_2+", 0) / 20.04 / 1000
        mg_eq_L = concentrations.get("Mg_2+", 0) / 12.15 / 1000
        na_eq_L = concentrations.get("Na_+", 0) / 22.99 / 1000
        k_eq_L = concentrations.get("K_+", 0) / 39.10 / 1000
        
        hardness_eq_L = ca_eq_L + mg_eq_L
        total_cations_eq_L = ca_eq_L + mg_eq_L + na_eq_L + k_eq_L
        
        # Service parameters
        service_flow_BV_hr = flow_rate_L_hr / column.resin_volume_L
        
        # Calculate ionic strength
        ionic_strength = 0.5 * (ca_eq_L * 4 + mg_eq_L * 4 + na_eq_L + k_eq_L)
        
        # Base capacity
        base_capacity_eq = column.exchange_capacity_eq_L * column.resin_volume_L
        
        # Selectivity coefficients
        if use_industrial_K:
            # Realistic industrial values
            K_Ca_Na_base = 40  # vs 5-10 in academic models
            K_Mg_Na_base = 25  # vs 3-5 in academic models
        else:
            # Conservative academic values
            K_Ca_Na_base = 5
            K_Mg_Na_base = 3
        
        # Apply corrections to selectivity
        # Ionic strength correction
        ionic_correction = 1 / (1 + 2.5 * np.sqrt(ionic_strength))
        
        # Temperature correction (van't Hoff)
        temp_K = temperature + 273.15
        temp_correction = np.exp(2000/1.987 * (1/298.15 - 1/temp_K))
        
        K_Ca_Na = K_Ca_Na_base * ionic_correction * temp_correction
        K_Mg_Na = K_Mg_Na_base * ionic_correction * temp_correction
        
        # Calculate equilibrium distribution
        # Using simplified approach for heterovalent exchange
        # At equilibrium: K = (q_Ca/q_Na²) * (C_Na²/C_Ca)
        
        # Separation factors for resin loading
        if na_eq_L > 0:
            alpha_Ca = K_Ca_Na * np.sqrt(ca_eq_L / na_eq_L)
            alpha_Mg = K_Mg_Na * np.sqrt(mg_eq_L / na_eq_L) 
        else:
            alpha_Ca = K_Ca_Na
            alpha_Mg = K_Mg_Na
        
        # Fraction of resin capacity used for hardness
        sum_alpha = alpha_Ca + alpha_Mg + 1  # +1 for Na
        hardness_fraction_resin = (alpha_Ca + alpha_Mg) / sum_alpha
        
        # Apply efficiency factors
        efficiency_factors = {
            "regeneration": 0.90,      # 90% regeneration efficiency
            "utilization": 0.85,       # 85% of sites accessible
            "channeling": 0.95,        # 5% loss to channeling
        }
        
        # Flow rate efficiency
        if service_flow_BV_hr > 25:
            flow_efficiency = 0.80
        elif service_flow_BV_hr > 20:
            flow_efficiency = 0.85
        elif service_flow_BV_hr > 15:
            flow_efficiency = 0.90
        elif service_flow_BV_hr > 10:
            flow_efficiency = 0.93
        else:
            flow_efficiency = 0.95
        
        # Total efficiency
        total_efficiency = (efficiency_factors["regeneration"] * 
                          efficiency_factors["utilization"] * 
                          efficiency_factors["channeling"] * 
                          flow_efficiency)
        
        # Effective capacity
        effective_capacity_eq = base_capacity_eq * total_efficiency
        
        # Usable capacity for hardness
        usable_capacity_eq = effective_capacity_eq * hardness_fraction_resin
        
        # Breakthrough volume
        breakthrough_bv = usable_capacity_eq / (hardness_eq_L * column.resin_volume_L)
        
        # Log calculations
        logger.info(f"\nCapacity Calculations:")
        logger.info(f"  Base capacity: {base_capacity_eq:.0f} eq")
        logger.info(f"  Total efficiency: {total_efficiency:.3f}")
        logger.info(f"  Effective capacity: {effective_capacity_eq:.0f} eq")
        logger.info(f"  Hardness fraction on resin: {hardness_fraction_resin:.3f}")
        logger.info(f"  Usable capacity: {usable_capacity_eq:.0f} eq")
        logger.info(f"  Theoretical breakthrough: {breakthrough_bv:.0f} BV")
        
        # Generate breakthrough curve
        # Using simple S-curve (logistic function)
        breakthrough_points = []
        
        # Breakthrough curve parameters
        curve_steepness = 0.05  # Controls sharpness of breakthrough
        
        for bv in np.arange(0, breakthrough_bv * 1.5, 5):
            if bv == 0:
                c_c0 = 0.001
            else:
                # Logistic function centered at breakthrough_bv
                x = (bv - breakthrough_bv) / breakthrough_bv
                c_c0 = 1 / (1 + np.exp(-x / curve_steepness))
                c_c0 = max(0.001, min(0.999, c_c0))
            
            # Calculate effluent
            effluent = {}
            ca_eff = concentrations.get("Ca_2+", 0) * c_c0
            mg_eff = concentrations.get("Mg_2+", 0) * c_c0
            
            effluent["Ca_2+"] = ca_eff
            effluent["Mg_2+"] = mg_eff
            
            # Na+ release (stoichiometric)
            ca_removed_meq = (concentrations.get("Ca_2+", 0) - ca_eff) / 20.04
            mg_removed_meq = (concentrations.get("Mg_2+", 0) - mg_eff) / 12.15
            na_released_mg = (ca_removed_meq + mg_removed_meq) * 22.99
            effluent["Na_+"] = concentrations.get("Na_+", 0) + na_released_mg
            
            # Other ions pass through
            for ion in ["K_+", "Cl_-", "SO4_2-", "HCO3_-", "NO3_-"]:
                effluent[ion] = concentrations.get(ion, 0)
            
            # Calculate hardness
            hardness = ca_eff * 2.5 + mg_eff * 4.1
            
            # pH change (slight increase)
            effluent_pH = pH + 0.2 * (1 - c_c0)
            
            # Time
            time_hours = bv / service_flow_BV_hr
            
            breakthrough_points.append(FinalBreakthroughPoint(
                bed_volumes=bv,
                time_hours=time_hours,
                effluent_concentrations_mg_L=effluent,
                hardness_mg_L_CaCO3=hardness,
                pH=effluent_pH
            ))
            
            # Stop at complete breakthrough
            if c_c0 > 0.95:
                break
        
        # Create summary
        summary = {
            "feed_hardness_eq_L": hardness_eq_L,
            "ionic_strength": ionic_strength,
            "selectivity_Ca_Na": K_Ca_Na,
            "selectivity_Mg_Na": K_Mg_Na,
            "base_capacity_eq": base_capacity_eq,
            "effective_capacity_eq": effective_capacity_eq,
            "usable_capacity_eq": usable_capacity_eq,
            "total_efficiency": total_efficiency,
            "hardness_fraction_resin": hardness_fraction_resin,
            "theoretical_breakthrough_bv": breakthrough_bv,
            "service_flow_BV_hr": service_flow_BV_hr
        }
        
        return breakthrough_points, summary