"""
Carbonate Chemistry Calculations for Degasser Model

This module provides direct calculations for acid addition and CO2 stripping
without relying on external chemistry packages.
"""

import numpy as np
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class DegasserChemistry:
    """
    Calculate carbonate chemistry for degasser operations.
    
    Based on carbonate equilibrium:
    CO2(aq) + H2O <-> H2CO3 <-> H+ + HCO3- <-> H+ + CO3^2-
    """
    
    def __init__(self):
        """Initialize with equilibrium constants at 25°C."""
        # Equilibrium constants at 25°C
        self.K1 = 10**-6.35   # First dissociation constant of carbonic acid
        self.K2 = 10**-10.33  # Second dissociation constant
        self.Kw = 10**-14     # Water dissociation constant
        self.Kh = 10**-1.47   # Henry's constant for CO2 (mol/L/atm)
        
        # Molecular weights (g/mol)
        self.MW = {
            'HCO3': 61.02,
            'CO2': 44.01,
            'CaCO3': 100.09,
            'H': 1.008,
            'Cl': 35.45,
            'SO4': 96.06
        }
    
    def calculate_carbonate_speciation(self, pH: float, total_carbonate_mol_L: float) -> Dict[str, float]:
        """
        Calculate distribution of carbonate species at given pH.
        
        Args:
            pH: Solution pH
            total_carbonate_mol_L: Total carbonate concentration (mol/L)
            
        Returns:
            Dict with concentrations of CO2, HCO3-, CO3^2- in mol/L
        """
        H = 10**(-pH)
        
        # Calculate alpha fractions
        denominator = H**2 + H*self.K1 + self.K1*self.K2
        alpha0 = H**2 / denominator          # CO2 fraction
        alpha1 = H*self.K1 / denominator     # HCO3- fraction
        alpha2 = self.K1*self.K2 / denominator  # CO3^2- fraction
        
        return {
            'CO2': alpha0 * total_carbonate_mol_L,
            'HCO3': alpha1 * total_carbonate_mol_L,
            'CO3': alpha2 * total_carbonate_mol_L
        }
    
    def alkalinity_to_carbonate(self, alkalinity_mg_L_CaCO3: float, pH: float) -> float:
        """
        Convert alkalinity to total carbonate concentration.
        
        Args:
            alkalinity_mg_L_CaCO3: Alkalinity as mg/L CaCO3
            pH: Solution pH
            
        Returns:
            Total carbonate concentration in mol/L
        """
        # Convert alkalinity to eq/L
        alk_eq_L = alkalinity_mg_L_CaCO3 / 50000  # mg/L CaCO3 to eq/L
        
        # Calculate carbonate contribution to alkalinity
        # Alk = [HCO3-] + 2[CO3^2-] + [OH-] - [H+]
        H = 10**(-pH)
        OH = self.Kw / H
        
        # For typical pH (6-9), we can approximate:
        # Alk ≈ [HCO3-] + 2[CO3^2-]
        # Using alpha fractions:
        denominator = H**2 + H*self.K1 + self.K1*self.K2
        alpha1 = H*self.K1 / denominator
        alpha2 = self.K1*self.K2 / denominator
        
        # Total carbonate from alkalinity
        Ct = alk_eq_L / (alpha1 + 2*alpha2)
        
        return Ct
    
    def calculate_acid_addition(self, 
                              initial_pH: float,
                              alkalinity_mg_L_CaCO3: float,
                              acid_dose_mmol_L: float,
                              acid_type: str = 'HCl') -> Dict[str, float]:
        """
        Calculate water chemistry after acid addition.
        
        Args:
            initial_pH: Initial pH
            alkalinity_mg_L_CaCO3: Initial alkalinity as mg/L CaCO3
            acid_dose_mmol_L: Acid dose in mmol/L
            acid_type: Type of acid ('HCl' or 'H2SO4')
            
        Returns:
            Dict with final pH, alkalinity, and species concentrations
        """
        # Convert to consistent units
        acid_eq_L = acid_dose_mmol_L / 1000  # mmol/L to eq/L
        if acid_type == 'H2SO4':
            acid_eq_L *= 2  # H2SO4 provides 2 H+
        
        # Initial carbonate system
        Ct_initial = self.alkalinity_to_carbonate(alkalinity_mg_L_CaCO3, initial_pH)
        
        # After acid addition, solve for new pH
        # This requires iterative solution of charge balance
        pH_final = self._solve_pH_after_acid(Ct_initial, alkalinity_mg_L_CaCO3/50000, acid_eq_L)
        
        # Calculate new speciation
        species = self.calculate_carbonate_speciation(pH_final, Ct_initial)
        
        # Calculate new alkalinity
        H = 10**(-pH_final)
        OH = self.Kw / H
        new_alk_eq_L = species['HCO3'] + 2*species['CO3'] + OH - H
        new_alk_mg_L = new_alk_eq_L * 50000
        
        # CO2 generated (that can be stripped)
        co2_generated_mol_L = species['CO2'] - self.calculate_carbonate_speciation(initial_pH, Ct_initial)['CO2']
        
        return {
            'pH': pH_final,
            'alkalinity_mg_L_CaCO3': new_alk_mg_L,
            'CO2_mol_L': species['CO2'],
            'HCO3_mol_L': species['HCO3'],
            'CO3_mol_L': species['CO3'],
            'CO2_generated_mol_L': co2_generated_mol_L,
            'CO2_generated_mg_L': co2_generated_mol_L * self.MW['CO2'] * 1000
        }
    
    def _solve_pH_after_acid(self, Ct: float, initial_alk: float, acid_added: float, 
                           tol: float = 1e-6, max_iter: int = 100) -> float:
        """
        Solve for pH after acid addition using charge balance.
        
        Uses Newton-Raphson iteration.
        """
        # Initial guess - use approximate formula
        pH = -np.log10(acid_added) if acid_added > 1e-7 else 7.0
        
        for i in range(max_iter):
            H = 10**(-pH)
            
            # Calculate species
            denominator = H**2 + H*self.K1 + self.K1*self.K2
            alpha1 = H*self.K1 / denominator
            alpha2 = self.K1*self.K2 / denominator
            
            # Charge balance: [H+] + acid_added = Alk_initial + [OH-]
            # Where Alk = [HCO3-] + 2[CO3^2-] + [OH-] - [H+]
            OH = self.Kw / H
            alk_calc = Ct * (alpha1 + 2*alpha2) + OH - H
            
            # Function to zero: charge imbalance
            f = H + acid_added - initial_alk - OH
            
            # Derivative
            df_dpH = -np.log(10) * H * (1 + self.Kw/H**2)
            
            # Newton step
            delta_pH = -f / df_dpH
            pH_new = pH + delta_pH
            
            # Ensure reasonable bounds
            pH_new = max(0, min(14, pH_new))
            
            if abs(delta_pH) < tol:
                return pH_new
            
            pH = pH_new
        
        logger.warning(f"pH iteration did not converge after {max_iter} iterations")
        return pH
    
    def calculate_co2_stripping(self,
                              pH: float,
                              alkalinity_mg_L_CaCO3: float,
                              pCO2_atm: float = 10**-3.5,
                              removal_efficiency: float = 0.9) -> Dict[str, float]:
        """
        Calculate water chemistry after CO2 stripping.
        
        Args:
            pH: Current pH
            alkalinity_mg_L_CaCO3: Current alkalinity
            pCO2_atm: Atmospheric CO2 partial pressure (atm)
            removal_efficiency: Fraction of excess CO2 removed
            
        Returns:
            Dict with final chemistry
        """
        # Get current carbonate system
        Ct = self.alkalinity_to_carbonate(alkalinity_mg_L_CaCO3, pH)
        species = self.calculate_carbonate_speciation(pH, Ct)
        
        # Equilibrium CO2 concentration with atmosphere
        CO2_eq = self.Kh * pCO2_atm  # mol/L
        
        # Current excess CO2
        excess_CO2 = species['CO2'] - CO2_eq
        
        if excess_CO2 <= 0:
            # Already at or below equilibrium
            return {
                'pH': pH,
                'alkalinity_mg_L_CaCO3': alkalinity_mg_L_CaCO3,
                'CO2_mol_L': species['CO2'],
                'HCO3_mol_L': species['HCO3'],
                'CO3_mol_L': species['CO3'],
                'CO2_removed_mol_L': 0,
                'CO2_removed_mg_L': 0
            }
        
        # Remove CO2
        CO2_removed = excess_CO2 * removal_efficiency
        CO2_final = species['CO2'] - CO2_removed
        
        # New total carbonate (CO2 leaves the system)
        Ct_new = Ct - CO2_removed
        
        # Calculate new pH from CO2 concentration
        # [CO2] = Ct * alpha0 = Ct * H^2 / (H^2 + H*K1 + K1*K2)
        # Solve for H
        pH_final = self._solve_pH_from_CO2(CO2_final, Ct_new)
        
        # New speciation
        species_final = self.calculate_carbonate_speciation(pH_final, Ct_new)
        
        # Alkalinity doesn't change during CO2 stripping
        # (HCO3- and CO3^2- don't change in eq/L)
        
        return {
            'pH': pH_final,
            'alkalinity_mg_L_CaCO3': alkalinity_mg_L_CaCO3,
            'CO2_mol_L': species_final['CO2'],
            'HCO3_mol_L': species_final['HCO3'],
            'CO3_mol_L': species_final['CO3'],
            'CO2_removed_mol_L': CO2_removed,
            'CO2_removed_mg_L': CO2_removed * self.MW['CO2'] * 1000
        }
    
    def _solve_pH_from_CO2(self, CO2_target: float, Ct: float, 
                          tol: float = 1e-8, max_iter: int = 100) -> float:
        """Solve for pH given CO2 concentration and total carbonate."""
        # Initial guess
        pH = 6.5
        
        for i in range(max_iter):
            H = 10**(-pH)
            
            # Calculate CO2 from current pH
            alpha0 = H**2 / (H**2 + H*self.K1 + self.K1*self.K2)
            CO2_calc = alpha0 * Ct
            
            # Error
            error = CO2_calc - CO2_target
            
            # Derivative of CO2 w.r.t. pH
            d_alpha0_dH = (2*H*(H*self.K1 + self.K1*self.K2) - H**2*(self.K1)) / (H**2 + H*self.K1 + self.K1*self.K2)**2
            d_CO2_dpH = -np.log(10) * H * Ct * d_alpha0_dH
            
            # Newton step
            delta_pH = -error / d_CO2_dpH
            pH_new = pH + delta_pH
            
            # Bounds
            pH_new = max(3, min(11, pH_new))
            
            if abs(delta_pH) < tol:
                return pH_new
            
            pH = pH_new
        
        logger.warning(f"pH from CO2 iteration did not converge")
        return pH
    
    def full_degasser_calculation(self,
                                initial_pH: float,
                                alkalinity_mg_L_CaCO3: float,
                                acid_dose_mmol_L: float,
                                acid_type: str = 'HCl',
                                co2_removal_efficiency: float = 0.9) -> Dict[str, float]:
        """
        Complete degasser calculation: acid addition followed by CO2 stripping.
        
        Returns complete water chemistry before and after treatment.
        """
        # Initial state
        initial_Ct = self.alkalinity_to_carbonate(alkalinity_mg_L_CaCO3, initial_pH)
        initial_species = self.calculate_carbonate_speciation(initial_pH, initial_Ct)
        
        # Step 1: Acid addition
        after_acid = self.calculate_acid_addition(
            initial_pH, alkalinity_mg_L_CaCO3, acid_dose_mmol_L, acid_type
        )
        
        # Step 2: CO2 stripping
        final = self.calculate_co2_stripping(
            after_acid['pH'], 
            after_acid['alkalinity_mg_L_CaCO3'],
            removal_efficiency=co2_removal_efficiency
        )
        
        # Summary
        return {
            'initial': {
                'pH': initial_pH,
                'alkalinity_mg_L_CaCO3': alkalinity_mg_L_CaCO3,
                'HCO3_mg_L': initial_species['HCO3'] * self.MW['HCO3'] * 1000,
                'CO2_mg_L': initial_species['CO2'] * self.MW['CO2'] * 1000
            },
            'after_acid': {
                'pH': after_acid['pH'],
                'alkalinity_mg_L_CaCO3': after_acid['alkalinity_mg_L_CaCO3'],
                'HCO3_mg_L': after_acid['HCO3_mol_L'] * self.MW['HCO3'] * 1000,
                'CO2_mg_L': after_acid['CO2_mol_L'] * self.MW['CO2'] * 1000,
                'CO2_generated_mg_L': after_acid['CO2_generated_mg_L']
            },
            'final': {
                'pH': final['pH'],
                'alkalinity_mg_L_CaCO3': final['alkalinity_mg_L_CaCO3'],
                'HCO3_mg_L': final['HCO3_mol_L'] * self.MW['HCO3'] * 1000,
                'CO2_mg_L': final['CO2_mol_L'] * self.MW['CO2'] * 1000,
                'CO2_removed_mg_L': final['CO2_removed_mg_L']
            },
            'performance': {
                'alkalinity_reduction_percent': (1 - final['alkalinity_mg_L_CaCO3']/alkalinity_mg_L_CaCO3) * 100,
                'HCO3_reduction_percent': (1 - final['HCO3_mol_L']/initial_species['HCO3']) * 100,
                'total_CO2_removed_mg_L': after_acid['CO2_generated_mg_L'] + final['CO2_removed_mg_L']
            }
        }