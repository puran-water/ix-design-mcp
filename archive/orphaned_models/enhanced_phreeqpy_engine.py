"""
Enhanced PhreeqPy Engine with Sophisticated Ion Exchange Modeling

Implements activity coefficient corrections, multi-site kinetics, and pH-dependent selectivity
for more accurate breakthrough predictions.
"""

import numpy as np
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)

@dataclass
class EnhancedBreakthroughPoint:
    """Enhanced breakthrough data with additional metrics."""
    bed_volumes: float
    time_hours: float
    effluent_concentrations_mg_L: Dict[str, float]
    pH: float
    capacity_utilized_eq: float
    ionic_strength: float
    activity_coefficients: Dict[str, float]
    selectivity_coefficients: Dict[str, float]
    resin_loading: Dict[str, float]  # Fraction of each ion on resin


class EnhancedIXModel:
    """Enhanced ion exchange model with sophisticated calculations."""
    
    def __init__(self):
        """Initialize enhanced model."""
        # Ion charges for activity calculations
        self.ion_charges = {
            "H_+": 1, "Na_+": 1, "K_+": 1, "NH4_+": 1,
            "Ca_2+": 2, "Mg_2+": 2, "Fe_2+": 2, "Mn_2+": 2,
            "Al_3+": 3, "Fe_3+": 3,
            "Cl_-": -1, "NO3_-": -1, "F_-": -1, "OH_-": -1,
            "SO4_2-": -2, "CO3_2-": -2,
            "PO4_3-": -3
        }
        
        # Base selectivity coefficients at 25°C, I=0
        # Using Gaines-Thomas convention (log K values)
        self.base_selectivity = {
            "Ca/Na": 0.8,   # log K for 2Na+ + CaX2 = Ca2+ + 2NaX
            "Mg/Na": 0.6,   # log K for 2Na+ + MgX2 = Mg2+ + 2NaX
            "K/Na": 0.7,    # log K for Na+ + KX = K+ + NaX
            "H/Na": 0.95,   # log K for Na+ + HX = H+ + NaX
            "NH4/Na": 0.9,  # log K for Na+ + NH4X = NH4+ + NaX
            "Fe/Na": 1.0    # log K for 2Na+ + FeX2 = Fe2+ + 2NaX
        }
        
        # Temperature coefficients (ΔH in cal/mol)
        self.enthalpy_exchange = {
            "Ca/Na": -2000,  # Exothermic
            "Mg/Na": -1800,
            "K/Na": -500,
            "H/Na": -3000,
            "NH4/Na": -1000,
            "Fe/Na": -2500
        }
        
    def calculate_ionic_strength(self, concentrations_mg_L: Dict[str, float]) -> float:
        """Calculate ionic strength of solution."""
        ionic_strength = 0.0
        
        for ion, conc_mg_L in concentrations_mg_L.items():
            if ion in self.ion_charges:
                # Convert mg/L to mol/L
                mw = self._get_molecular_weight(ion)
                conc_mol_L = conc_mg_L / (mw * 1000)
                
                # I = 0.5 * Σ(ci * zi²)
                charge = self.ion_charges[ion]
                ionic_strength += 0.5 * conc_mol_L * charge**2
        
        return ionic_strength
    
    def calculate_activity_coefficients(self, concentrations_mg_L: Dict[str, float], 
                                      temperature_C: float = 25) -> Dict[str, float]:
        """Calculate activity coefficients using extended Debye-Hückel equation."""
        ionic_strength = self.calculate_ionic_strength(concentrations_mg_L)
        activity_coeffs = {}
        
        # Temperature-dependent parameters
        T_K = temperature_C + 273.15
        A = 0.5085 * (78.54 / (78.54 * (1 - 0.004579 * (T_K - 298.15))))**0.5 * (T_K / 298.15)**(-1.5)
        B = 0.3281 * (78.54 / (78.54 * (1 - 0.004579 * (T_K - 298.15))))**0.5 * (T_K / 298.15)**(-0.5)
        
        for ion in concentrations_mg_L:
            if ion in self.ion_charges:
                charge = abs(self.ion_charges[ion])
                
                # Ion size parameter (angstroms)
                if charge == 1:
                    a = 4.0
                elif charge == 2:
                    a = 6.0
                else:
                    a = 9.0
                
                # Extended Debye-Hückel equation
                if ionic_strength < 0.1:
                    log_gamma = -A * charge**2 * np.sqrt(ionic_strength) / (1 + B * a * np.sqrt(ionic_strength))
                else:
                    # Davies equation for higher ionic strength
                    log_gamma = -A * charge**2 * (np.sqrt(ionic_strength) / (1 + np.sqrt(ionic_strength)) - 0.3 * ionic_strength)
                
                activity_coeffs[ion] = 10**log_gamma
        
        return activity_coeffs
    
    def correct_selectivity_coefficients(self, base_selectivity: Dict[str, float],
                                       activity_coeffs: Dict[str, float],
                                       temperature_C: float = 25) -> Dict[str, float]:
        """Correct selectivity coefficients for activity and temperature."""
        corrected = {}
        T_K = temperature_C + 273.15
        
        for exchange_pair, log_K_base in base_selectivity.items():
            ions = exchange_pair.split('/')
            ion1, ion2 = ions[0], ions[1]
            
            # Temperature correction using Van't Hoff equation
            if exchange_pair in self.enthalpy_exchange:
                delta_H = self.enthalpy_exchange[exchange_pair]
                log_K_T = log_K_base - (delta_H / (2.303 * 1.987)) * (1/T_K - 1/298.15)
            else:
                log_K_T = log_K_base
            
            # Activity coefficient correction
            # For exchange: νA·A + νB·B̄ ⇌ νA·Ā + νB·B
            # K_corrected = K * (γ_A^νA * γ_B̄^νB) / (γ_Ā^νA * γ_B^νB)
            
            # Simplified for common exchanges
            if ion1 in ['Ca', 'Mg', 'Fe'] and ion2 == 'Na':
                # Divalent-monovalent exchange
                gamma_correction = (activity_coeffs.get('Na_+', 1)**2) / activity_coeffs.get(f'{ion1}_2+', 1)
            else:
                # Monovalent-monovalent exchange
                gamma_correction = activity_coeffs.get('Na_+', 1) / activity_coeffs.get(f'{ion1}_+', 1)
            
            corrected[exchange_pair] = 10**log_K_T * gamma_correction
        
        return corrected
    
    def multisite_breakthrough_model(self, column, feed_water: Dict[str, Any], 
                                   flow_rate_L_hr: float) -> List[EnhancedBreakthroughPoint]:
        """
        Enhanced breakthrough model with:
        - Multi-site kinetics (fast and slow sites)
        - Activity coefficient corrections
        - pH-dependent selectivity
        - Temperature effects
        """
        breakthrough_points = []
        
        # Extract parameters
        concentrations = feed_water["ion_concentrations_mg_L"]
        pH = feed_water["pH"]
        temperature = feed_water.get("temperature_celsius", 25)
        
        # Calculate ionic strength and activity coefficients
        ionic_strength = self.calculate_ionic_strength(concentrations)
        activity_coeffs = self.calculate_activity_coefficients(concentrations, temperature)
        
        # Correct selectivity coefficients
        selectivity = self.correct_selectivity_coefficients(
            self.base_selectivity, activity_coeffs, temperature
        )
        
        # pH-dependent H+ competition
        if pH < 7:
            H_conc_mol_L = 10**(-pH)
            H_conc_mg_L = H_conc_mol_L * 1008  # mg/L
            selectivity["H/Na"] *= (1 + 10**(7 - pH))  # Enhanced H+ selectivity at low pH
        else:
            H_conc_mg_L = 0.001
        
        # Multi-site model: 5% fast sites, 95% slow sites (more realistic for quality resin)
        fast_site_fraction = 0.05
        slow_site_fraction = 0.95
        
        # Kinetic factors based on flow rate
        service_flow_BV_hr = flow_rate_L_hr / column.resin_volume_L
        
        # Film diffusion control at high flow rates
        if service_flow_BV_hr > 15:
            fast_kinetic_factor = 0.9
            slow_kinetic_factor = 15 / service_flow_BV_hr  # Reduces with flow
        else:
            fast_kinetic_factor = 1.0
            slow_kinetic_factor = 0.95
        
        # Calculate individual ion loadings
        ca_feed = concentrations.get("Ca_2+", 0)
        mg_feed = concentrations.get("Mg_2+", 0)
        na_feed = concentrations.get("Na_+", 0)
        k_feed = concentrations.get("K_+", 0)
        
        # Convert mg/L to eq/L (using equivalent weight = MW/charge)
        ca_eq_L = (ca_feed / 20.04 / 1000) if ca_feed > 0 else 0  # MW=40.08, charge=2
        mg_eq_L = (mg_feed / 12.15 / 1000) if mg_feed > 0 else 0  # MW=24.31, charge=2
        na_eq_L = (na_feed / 22.99 / 1000) if na_feed > 0 else 0  # MW=22.99, charge=1
        k_eq_L = (k_feed / 39.10 / 1000) if k_feed > 0 else 0    # MW=39.10, charge=1
        h_eq_L = (H_conc_mg_L / 1.008 / 1000) if H_conc_mg_L > 0 else 0  # MW=1.008, charge=1
        
        total_cation_eq_L = ca_eq_L + mg_eq_L + na_eq_L + k_eq_L + h_eq_L
        
        # Resin capacity
        total_capacity_eq = column.exchange_capacity_eq_L * column.resin_volume_L
        fast_capacity = total_capacity_eq * fast_site_fraction
        slow_capacity = total_capacity_eq * slow_site_fraction
        
        # Calculate breakthrough for each site type
        # Fast sites - lower selectivity, quick saturation
        # BV = capacity (eq) / (loading per BV) = capacity (eq) / (concentration (eq/L) * volume per BV (L))
        fast_breakthrough_bv = fast_capacity / (total_cation_eq_L * column.resin_volume_L) * fast_kinetic_factor
        
        # Slow sites - higher selectivity, slower saturation
        # Apply multicomponent competition
        competition_factor = self._calculate_multicomponent_competition(
            ca_eq_L, mg_eq_L, na_eq_L, k_eq_L, h_eq_L, selectivity
        )
        slow_breakthrough_bv = slow_capacity / (total_cation_eq_L * column.resin_volume_L) * slow_kinetic_factor * competition_factor
        
        # Debug logging
        logger.info(f"Total cation eq/L: {total_cation_eq_L:.6f}")
        logger.info(f"Fast capacity: {fast_capacity:.1f} eq, Slow capacity: {slow_capacity:.1f} eq")
        logger.info(f"Fast breakthrough BV: {fast_breakthrough_bv:.1f}, Slow breakthrough BV: {slow_breakthrough_bv:.1f}")
        logger.info(f"Competition factor: {competition_factor:.3f}")
        
        # Generate composite breakthrough curve
        for bv in np.arange(0, 1200, 5):
            # Fast site breakthrough (sharp)
            if bv < fast_breakthrough_bv * 0.5:
                fast_breakthrough = 0.01
            elif bv < fast_breakthrough_bv * 1.5:
                x = (bv - fast_breakthrough_bv * 0.5) / fast_breakthrough_bv
                fast_breakthrough = 0.5 * (1 + np.tanh(6 * (x - 0.5)))
            else:
                fast_breakthrough = 0.99
            
            # Slow site breakthrough (gradual)
            if bv < slow_breakthrough_bv * 0.7:
                slow_breakthrough = 0.005
            elif bv < slow_breakthrough_bv * 2.0:
                x = (bv - slow_breakthrough_bv * 0.7) / (slow_breakthrough_bv * 1.3)
                slow_breakthrough = 0.5 * (1 + np.tanh(3 * (x - 0.5)))
            else:
                slow_breakthrough = 0.995
            
            # Composite breakthrough
            total_breakthrough = (fast_site_fraction * fast_breakthrough + 
                                slow_site_fraction * slow_breakthrough)
            
            # Calculate effluent concentrations
            effluent = {}
            resin_loading = {}
            
            for ion, feed_conc in concentrations.items():
                if ion in ["Ca_2+", "Mg_2+", "K_+", "Fe_2+"]:
                    # Cations are partially removed
                    effluent[ion] = feed_conc * total_breakthrough
                    resin_loading[ion] = (1 - total_breakthrough)
                elif ion == "Na_+":
                    # Sodium is released from resin
                    removed_hardness_eq = (ca_eq_L + mg_eq_L) * (1 - total_breakthrough) * column.resin_volume_L
                    released_na_mg = removed_hardness_eq * 22.99 * 1000  # eq to mg
                    effluent[ion] = na_feed + released_na_mg / (column.resin_volume_L)
                    resin_loading[ion] = -removed_hardness_eq / total_capacity_eq
                else:
                    # Anions pass through
                    effluent[ion] = feed_conc
                    resin_loading[ion] = 0
            
            # Calculate pH change due to H+ exchange
            if h_eq_L > 0 and pH < 7:
                h_removed = h_eq_L * (1 - total_breakthrough) * 0.3  # 30% H+ exchange
                new_h_mol_L = 10**(-pH) - h_removed
                effluent_pH = -np.log10(max(new_h_mol_L, 1e-10))
            else:
                effluent_pH = pH + 0.5 * (1 - total_breakthrough)  # Slight pH increase
            
            # Time calculation
            time_hours = bv * column.resin_volume_L / flow_rate_L_hr
            
            # Capacity utilization
            capacity_used = total_cation_eq_L * bv * column.resin_volume_L
            
            breakthrough_points.append(EnhancedBreakthroughPoint(
                bed_volumes=bv,
                time_hours=time_hours,
                effluent_concentrations_mg_L=effluent,
                pH=effluent_pH,
                capacity_utilized_eq=min(capacity_used, total_capacity_eq),
                ionic_strength=ionic_strength,
                activity_coefficients=activity_coeffs,
                selectivity_coefficients=selectivity,
                resin_loading=resin_loading
            ))
            
            # Check for breakthrough
            hardness = effluent.get("Ca_2+", 0) * 2.5 + effluent.get("Mg_2+", 0) * 4.1
            if hardness > 5 and bv > 50:  # Ignore very early breakthrough
                logger.info(f"Enhanced model breakthrough at {bv} BV")
                break
        
        return breakthrough_points
    
    def _calculate_multicomponent_competition(self, ca_eq_L: float, mg_eq_L: float,
                                            na_eq_L: float, k_eq_L: float, h_eq_L: float,
                                            selectivity: Dict[str, float]) -> float:
        """Calculate competition factor for multicomponent system using separation factors."""
        
        if ca_eq_L + mg_eq_L == 0:
            return 1.0
            
        # Get selectivity values with defaults
        K_Ca_Na = selectivity.get("Ca/Na", 6.3)
        K_Mg_Na = selectivity.get("Mg/Na", 4.0)
        K_K_Na = selectivity.get("K/Na", 5.0)
        K_H_Na = selectivity.get("H/Na", 8.0)
        
        # Calculate separation factors (relative to Na+)
        # For divalent ions: α = (K * C_divalent)^0.5 / C_monovalent
        # This accounts for the stoichiometry of heterovalent exchange
        
        total_hardness_eq = ca_eq_L + mg_eq_L
        
        # Effective competition considering selectivity
        # Higher selectivity means less competition (ion is preferred)
        ca_factor = (K_Ca_Na * ca_eq_L)**0.5 if ca_eq_L > 0 else 0
        mg_factor = (K_Mg_Na * mg_eq_L)**0.5 if mg_eq_L > 0 else 0
        hardness_factor = ca_factor + mg_factor
        
        # Monovalent competition (reduces capacity)
        na_factor = na_eq_L  # Reference ion
        k_factor = k_eq_L / K_K_Na if k_eq_L > 0 else 0  # Less competitive if K_K_Na > 1
        h_factor = h_eq_L / K_H_Na if h_eq_L > 0 else 0  # Less competitive if K_H_Na > 1
        
        monovalent_factor = na_factor + k_factor + h_factor
        
        # Competition factor: preference for hardness vs monovalent ions
        if hardness_factor + monovalent_factor > 0:
            competition_factor = hardness_factor / (hardness_factor + monovalent_factor)
            # Adjust for high ionic strength effects
            if na_eq_L > 0.005:  # High Na+ reduces selectivity
                competition_factor *= (1 - 0.3 * min(na_eq_L / 0.05, 1))  # Up to 30% reduction
        else:
            competition_factor = 0.5
        
        return min(max(competition_factor, 0.3), 0.95)  # Bound between 0.3 and 0.95
    
    def _get_molecular_weight(self, ion: str) -> float:
        """Get molecular weight of ion."""
        mw_dict = {
            "H_+": 1.008, "Na_+": 22.99, "K_+": 39.10, "NH4_+": 18.04,
            "Ca_2+": 40.08, "Mg_2+": 24.31, "Fe_2+": 55.85, "Mn_2+": 54.94,
            "Al_3+": 26.98, "Fe_3+": 55.85,
            "Cl_-": 35.45, "NO3_-": 62.00, "F_-": 19.00, "OH_-": 17.01,
            "SO4_2-": 96.06, "CO3_2-": 60.01, "HCO3_-": 61.02,
            "PO4_3-": 94.97, "SiO2": 60.08
        }
        return mw_dict.get(ion, 100.0)  # Default 100 if not found