"""
Calculate actual operating capacity based on regeneration level
and selectivity effects.
"""
import numpy as np
from tools.selectivity_coefficients import SelectivityCoefficients
from tools.equilibrium_leakage import EquilibriumLeakageCalculator


class CapacityDerating:
    """
    Derate theoretical capacity based on:
    1. Regeneration efficiency
    2. Selectivity effects
    3. Incomplete utilization
    """

    def __init__(self):
        self.selectivity = SelectivityCoefficients()
        self.equilibrium_calc = EquilibriumLeakageCalculator()

    def sac_operating_capacity(self,
                              total_capacity_eq_L,
                              regen_dose_g_L,
                              ca_fraction,
                              mg_fraction,
                              na_fraction):
        """
        Calculate operating capacity accounting for:
        - Incomplete regeneration of divalent sites
        - Selectivity-based capacity reduction

        Based on equilibrium and mass action from literature.

        Args:
            total_capacity_eq_L: Total exchange capacity (eq/L)
            regen_dose_g_L: NaCl regeneration dose (g/L resin)
            ca_fraction: Fraction of Ca in feed (equivalent basis)
            mg_fraction: Fraction of Mg in feed (equivalent basis)
            na_fraction: Fraction of Na in feed (equivalent basis)

        Returns:
            Operating capacity in eq/L
        """
        # Base regeneration efficiency from literature
        # Derived from Mass Transfer text regeneration curves
        # and Helfferich Chapter 9 on column operations
        if regen_dose_g_L <= 60:
            base_efficiency = 0.50
        elif regen_dose_g_L <= 100:
            # Linear interpolation 60-100 g/L
            base_efficiency = 0.50 + (regen_dose_g_L - 60) * 0.005
        elif regen_dose_g_L <= 150:
            # Linear interpolation 100-150 g/L
            base_efficiency = 0.70 + (regen_dose_g_L - 100) * 0.003
        else:
            # Diminishing returns above 150 g/L
            base_efficiency = 0.85 + (regen_dose_g_L - 150) * 0.0003
            base_efficiency = min(base_efficiency, 0.95)  # Cap at 95%

        # Divalent content effect
        divalent_fraction = ca_fraction + mg_fraction

        # Get selectivity coefficients
        K_Ca_Na = self.selectivity.SAC_8DVB['Ca_Na']
        K_Mg_Na = self.selectivity.SAC_8DVB['Mg_Na']

        # Weighted average selectivity for divalents
        if divalent_fraction > 0:
            K_divalent = (ca_fraction * K_Ca_Na + mg_fraction * K_Mg_Na) / divalent_fraction
        else:
            K_divalent = 1.0

        # Regeneration conditions
        # 10% NaCl ≈ 100 g/L ≈ 1.7 N
        # Calculate normality of regenerant
        nacl_mw = 58.44  # g/mol
        brine_concentration_percent = min(10, regen_dose_g_L / 10)  # Approximate
        brine_normality = brine_concentration_percent * 10 / nacl_mw

        # Equilibrium calculation for Na-form conversion
        # At high Na concentration during regeneration
        # Based on mass action: R-Ca + 2Na+ ⇌ R-Na2 + Ca2+
        # Fraction of sites that can be converted to Na form
        if divalent_fraction > 0 and K_divalent > 0:
            # Account for unfavorable equilibrium for divalent displacement
            na_form_fraction = brine_normality**2 / (brine_normality**2 + divalent_fraction * K_divalent)
            # Adjust for incomplete equilibration
            na_form_fraction = 0.5 + 0.5 * na_form_fraction  # Empirical adjustment
        else:
            na_form_fraction = 1.0

        # Calculate operating capacity
        operating_capacity = total_capacity_eq_L * base_efficiency * na_form_fraction

        return operating_capacity

    def calculate_leakage(self, ca_mg_l, mg_mg_l, na_mg_l, K_Ca_Na=5.16, K_Mg_Na=3.29, f_active=0.10):
        """
        Calculate hardness leakage from feed water composition using
        Gaines-Thomas equilibrium.

        REPLACED OLD MODEL: Previously calculated leakage from regeneration
        dose, which is fundamentally wrong. Leakage is controlled by feed
        water composition via mass action equilibrium (Helfferich Ch. 5).

        Args:
            ca_mg_l: Feed calcium concentration (mg/L)
            mg_mg_l: Feed magnesium concentration (mg/L)
            na_mg_l: Feed sodium concentration (mg/L)
            K_Ca_Na: Ca²⁺/Na⁺ selectivity coefficient (default 5.16)
            K_Mg_Na: Mg²⁺/Na⁺ selectivity coefficient (default 3.29)
            f_active: Fraction of bed in active mass transfer zone (0.08-0.15)

        Returns:
            Hardness leakage in mg/L as CaCO3
        """
        result = self.equilibrium_calc.calculate_sac_equilibrium_leakage(
            ca_mg_l, mg_mg_l, na_mg_l, K_Ca_Na, K_Mg_Na, f_active
        )
        return result['hardness_leakage_mg_l_caco3']

    def calculate_dose_for_leakage(self, target_leakage_mg_L, ca_mg_l, mg_mg_l, na_mg_l, K_Ca_Na=5.16, K_Mg_Na=3.29):
        """
        Calculate f_active parameter required to achieve target hardness leakage.

        REPLACED OLD MODEL: Previously calculated regeneration dose for target
        leakage, which is fundamentally wrong. Regeneration dose controls
        CAPACITY, not leakage. Leakage is controlled by feed composition.

        This function now tunes the f_active parameter (mass transfer zone
        fraction) to match the target leakage.

        Args:
            target_leakage_mg_L: Desired hardness leakage (mg/L as CaCO3)
            ca_mg_l: Feed calcium concentration (mg/L)
            mg_mg_l: Feed magnesium concentration (mg/L)
            na_mg_l: Feed sodium concentration (mg/L)
            K_Ca_Na: Ca²⁺/Na⁺ selectivity coefficient
            K_Mg_Na: Mg²⁺/Na⁺ selectivity coefficient

        Returns:
            Required f_active parameter (typically 0.08-0.15)
        """
        return self.equilibrium_calc.calibrate_f_active(
            target_leakage_mg_L, ca_mg_l, mg_mg_l, na_mg_l, K_Ca_Na, K_Mg_Na
        )

    def wac_capacity_vs_pH(self, total_capacity_eq_L, pH, pKa=4.5):
        """
        Calculate WAC capacity as function of pH.

        Henderson-Hasselbalch equation for weak acid groups.

        Args:
            total_capacity_eq_L: Total capacity at high pH (eq/L)
            pH: Solution pH
            pKa: Acid dissociation constant (default 4.5 for carboxylic)

        Returns:
            Operating capacity at given pH (eq/L)
        """
        # Fraction of groups ionized (capable of exchange)
        alpha = 1 / (1 + 10**(pKa - pH))

        # Operating capacity
        operating_capacity = total_capacity_eq_L * alpha

        return operating_capacity

    def calculate_rinse_requirement(self, regen_dose_g_L, bed_volume_L):
        """
        Calculate rinse water requirement.

        Based on literature data for NaCl removal.

        Args:
            regen_dose_g_L: Regenerant dose (g/L resin)
            bed_volume_L: Bed volume in liters

        Returns:
            Rinse volume in bed volumes
        """
        # Base rinse requirement
        # From literature: 2-5 BV typical
        if regen_dose_g_L <= 80:
            rinse_BV = 2.0
        elif regen_dose_g_L <= 120:
            rinse_BV = 3.0
        else:
            rinse_BV = 4.0

        return rinse_BV