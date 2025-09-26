"""
Calculate breakthrough using literature models and derating factors.
"""
import numpy as np
import math
from tools.capacity_derating import CapacityDerating
from tools.selectivity_coefficients import SelectivityCoefficients


class BreakthroughCalculator:
    """
    Calculate breakthrough bed volumes using:
    1. Operating capacity from derating
    2. Mass transfer zone from LUB concept
    3. Thomas model kinetics
    """

    def __init__(self):
        self.derating = CapacityDerating()
        self.selectivity = SelectivityCoefficients()

    def calculate_sac_breakthrough(self,
                                  water_analysis,
                                  regen_dose_g_L=None,
                                  total_capacity_eq_L=2.0):
        """
        Calculate SAC breakthrough accounting for all factors.

        Can work in two modes:
        1. Given regen_dose_g_L → calculate leakage
        2. Given target_hardness_mg_L → calculate required dose

        Args:
            water_analysis: Dict with ca_mg_l, mg_mg_l, na_mg_l, flow_m3_hr, flow_BV_hr
                          Optionally: target_hardness_mg_L for leakage-driven mode
            regen_dose_g_L: NaCl regeneration dose (g/L resin), optional if target specified
            total_capacity_eq_L: Total exchange capacity (default 2.0 for SAC)

        Returns:
            Dict with breakthrough parameters
        """
        # Water composition
        ca_mg_L = water_analysis.get('ca_mg_l', 0)
        mg_mg_L = water_analysis.get('mg_mg_l', 0)
        na_mg_L = water_analysis.get('na_mg_l', 0)

        # Convert to eq/L
        # Ca²⁺: MW = 40.078, valence = 2
        ca_eq_L = ca_mg_L * 2 / 40.078 / 1000
        # Mg²⁺: MW = 24.305, valence = 2
        mg_eq_L = mg_mg_L * 2 / 24.305 / 1000
        # Na⁺: MW = 22.990, valence = 1
        na_eq_L = na_mg_L / 22.990 / 1000

        total_cations = ca_eq_L + mg_eq_L + na_eq_L

        # Ion fractions (equivalent basis)
        if total_cations > 0:
            ca_fraction = ca_eq_L / total_cations
            mg_fraction = mg_eq_L / total_cations
            na_fraction = na_eq_L / total_cations
        else:
            ca_fraction = mg_fraction = na_fraction = 0

        K_Ca_Na = self.selectivity.SAC_8DVB['Ca_Na']
        K_Mg_Na = self.selectivity.SAC_8DVB['Mg_Na']

        target_hardness = water_analysis.get('target_hardness_mg_L')
        if regen_dose_g_L is None and target_hardness is not None:
            f_active = self.derating.calculate_dose_for_leakage(
                target_hardness, ca_mg_L, mg_mg_L, na_mg_L, K_Ca_Na, K_Mg_Na
            )
            regen_dose_g_L = 120
        else:
            if regen_dose_g_L is None:
                regen_dose_g_L = 120
            f_active = 0.10

        operating_capacity = self.derating.sac_operating_capacity(
            total_capacity_eq_L,
            regen_dose_g_L,
            ca_fraction,
            mg_fraction,
            na_fraction
        )

        # Calculate hardness
        hardness_eq_L = ca_eq_L + mg_eq_L
        hardness_mg_L_CaCO3 = hardness_eq_L * 50000  # eq/L to mg/L as CaCO3

        # Calculate theoretical bed volumes
        if hardness_eq_L > 0:
            BV_theoretical = operating_capacity / hardness_eq_L
        else:
            BV_theoretical = 0

        # Apply LUB correction (Length of Unused Bed)
        # From Mass Transfer texts: LUB = f(flow rate, MTZ)
        flow_BV_hr = water_analysis.get('flow_BV_hr', 16)

        # LUB calculation based on mass transfer zone
        # Higher flow = larger MTZ = larger LUB
        # From literature: LUB/L = 0.1-0.25 for typical operations
        if flow_BV_hr <= 10:
            LUB_fraction = 0.10
        elif flow_BV_hr <= 20:
            LUB_fraction = 0.10 + 0.005 * (flow_BV_hr - 10)
        elif flow_BV_hr <= 40:
            LUB_fraction = 0.15 + 0.0025 * (flow_BV_hr - 20)
        else:
            LUB_fraction = 0.20 + 0.00125 * (flow_BV_hr - 40)

        # Cap at reasonable maximum
        LUB_fraction = min(LUB_fraction, 0.30)

        # Column utilization
        utilization = 1 - LUB_fraction

        # Actual breakthrough
        BV_actual = BV_theoretical * utilization

        leakage_mg_L = self.derating.calculate_leakage(
            ca_mg_L, mg_mg_L, na_mg_L, K_Ca_Na, K_Mg_Na, f_active
        )

        # Run length in hours
        if flow_BV_hr > 0:
            run_length_hrs = BV_actual / flow_BV_hr
        else:
            run_length_hrs = 0

        return {
            'BV_breakthrough': BV_actual,
            'BV_theoretical': BV_theoretical,
            'operating_capacity_eq_L': operating_capacity,
            'utilization': utilization,
            'LUB_fraction': LUB_fraction,
            'hardness_feed_mg_L': hardness_mg_L_CaCO3,
            'hardness_leakage_mg_L': leakage_mg_L,
            'theoretical_capacity_eq_L': total_capacity_eq_L,
            'derating_factor': operating_capacity / total_capacity_eq_L,
            'run_length_hrs': run_length_hrs,
            'regenerant_dose_g_L': regen_dose_g_L,
            'ion_fractions': {
                'Ca': ca_fraction,
                'Mg': mg_fraction,
                'Na': na_fraction
            }
        }

    def calculate_pH_from_alkalinity(self, alkalinity_mg_L_CaCO3, temperature_C=25):
        """
        Calculate pH that corresponds to a given residual alkalinity.

        Uses carbonate equilibrium at the pH floor where most alkalinity
        is in the form of dissolved CO2.

        Args:
            alkalinity_mg_L_CaCO3: Target residual alkalinity (5-20 typical)
            temperature_C: Temperature for pKa adjustment

        Returns:
            pH_floor: pH at which this alkalinity is achieved
        """
        # Temperature correction for pKa (approximately -0.01 pH units/°C)
        pKa1_carbonic = 6.35 - 0.01 * (temperature_C - 25)

        # At low pH (4-5), alkalinity is mostly HCO3-
        # Alkalinity (mg/L as CaCO3) = 50,000 * [HCO3-] (mol/L)
        # At pH << pKa1, [HCO3-]/CT ≈ 10^(pH - pKa1)

        if alkalinity_mg_L_CaCO3 <= 5:
            # Very low alkalinity target - pH floor near pKa of resin
            return 4.0
        elif alkalinity_mg_L_CaCO3 >= 50:
            # High alkalinity - limited removal
            return 5.5
        else:
            # Empirical correlation for typical range
            # Based on carbonate equilibrium at low pH
            pH_floor = 4.0 + 0.04 * alkalinity_mg_L_CaCO3
            return min(pH_floor, 5.5)

    def calculate_wac_h_breakthrough(self,
                                    water_analysis,
                                    total_capacity_eq_L=4.7):
        """
        Calculate WAC-H breakthrough for alkalinity removal.

        Uses pH floor concept: target alkalinity leakage determines
        the pH floor, which sets the usable capacity.

        Args:
            water_analysis: Dict with alkalinity_mg_L_CaCO3, pH, flow_BV_hr,
                          and target_alkalinity_mg_L_CaCO3
            total_capacity_eq_L: Total capacity (default 4.7 for WAC)

        Returns:
            Dict with breakthrough parameters
        """
        alkalinity_mg_L = water_analysis.get('alkalinity_mg_L_CaCO3', 100)
        pH_feed = water_analysis.get('pH', 7.8)
        flow_BV_hr = water_analysis.get('flow_BV_hr', 16)
        temperature_C = water_analysis.get('temperature_C', 25)

        # Get target alkalinity leakage (default 10 mg/L)
        target_alkalinity = water_analysis.get('target_alkalinity_mg_L_CaCO3', 10)

        # pH-dependent capacity (Henderson-Hasselbalch)
        pKa = 4.5  # Carboxylic acid groups from literature
        # Temperature correction
        pKa = pKa - 0.01 * (temperature_C - 25)

        # Calculate pH floor from target alkalinity leakage
        # This is the key innovation - target drives capacity!
        pH_floor = self.calculate_pH_from_alkalinity(target_alkalinity, temperature_C)

        # Calculate fraction of sites still active at pH floor
        # This IS the derating mechanism for WAC_H
        alpha = 1 / (1 + 10**(pKa - pH_floor))

        # Operating capacity determined by pH floor
        operating_capacity = total_capacity_eq_L * alpha

        # Alkalinity in eq/L
        # 1 eq/L = 50,000 mg/L as CaCO3, so mg/L ÷ 50 = meq/L, ÷ 1000 = eq/L
        alkalinity_eq_L = alkalinity_mg_L / 50 / 1000  # mg/L as CaCO3 to eq/L

        # Theoretical BV
        if alkalinity_eq_L > 0:
            BV_theoretical = operating_capacity / alkalinity_eq_L
        else:
            BV_theoretical = 0

        # LUB for WAC
        # Typically smaller than SAC due to favorable equilibrium
        # From literature: 5-10% for WAC
        if flow_BV_hr <= 10:
            LUB_fraction = 0.05
        elif flow_BV_hr <= 20:
            LUB_fraction = 0.05 + 0.003 * (flow_BV_hr - 10)
        else:
            LUB_fraction = 0.08 + 0.001 * (flow_BV_hr - 20)

        # Cap at reasonable maximum
        LUB_fraction = min(LUB_fraction, 0.15)

        utilization = 1 - LUB_fraction

        # Actual breakthrough
        BV_actual = BV_theoretical * utilization

        # CO2 generation (stoichiometric)
        # HCO3⁻ + H⁺ → H2O + CO2
        # MW CO2 = 44.01, MW CaCO3 = 100.09
        CO2_mg_L = alkalinity_mg_L * 44.01 / 100.09

        # pH profile - now using calculated pH floor
        # Initial effluent pH is at the floor
        pH_effluent_initial = pH_floor
        # At breakthrough, pH starts rising toward feed pH
        pH_effluent_breakthrough = min(pH_floor + 1.0, pH_feed - 0.5)

        # Run length
        if flow_BV_hr > 0:
            run_length_hrs = BV_actual / flow_BV_hr
        else:
            run_length_hrs = 0

        return {
            'BV_alkalinity': BV_actual,
            'BV_theoretical': BV_theoretical,
            'operating_capacity_eq_L': operating_capacity,
            'pH_dependent_capacity_fraction': alpha,
            'CO2_generation_mg_L': CO2_mg_L,
            'pH_profile': {
                'feed': pH_feed,
                'effluent_initial': pH_effluent_initial,
                'effluent_breakthrough': pH_effluent_breakthrough,
                'pH_floor': pH_floor  # Actual calculated floor, not pKa
            },
            'utilization': utilization,
            'LUB_fraction': LUB_fraction,
            'alkalinity_feed_mg_L': alkalinity_mg_L,
            'alkalinity_effluent_mg_L': target_alkalinity,  # Target = expected effluent
            'run_length_hrs': run_length_hrs,
            'theoretical_capacity_eq_L': total_capacity_eq_L,
            'derating_factor': alpha  # pH-based derating from target
        }

    def calculate_wac_na_breakthrough(self,
                                     water_analysis,
                                     total_capacity_eq_L=4.0):
        """
        Calculate WAC-Na breakthrough for partial softening.

        WAC-Na removes temporary hardness (Ca/Mg associated with alkalinity).

        Args:
            water_analysis: Dict with water quality parameters
            total_capacity_eq_L: Total capacity (default 4.0 for WAC-Na)

        Returns:
            Dict with breakthrough parameters
        """
        # Water composition
        ca_mg_L = water_analysis.get('ca_mg_l', 0)
        mg_mg_L = water_analysis.get('mg_mg_l', 0)
        alkalinity_mg_L = water_analysis.get('alkalinity_mg_L_CaCO3', 100)
        pH_feed = water_analysis.get('pH', 7.8)
        flow_BV_hr = water_analysis.get('flow_BV_hr', 16)

        # WAC-Na primarily removes temporary hardness
        # Limited by alkalinity
        # Convert mg/L as CaCO3 to eq/L: 1 eq/L = 50,000 mg/L as CaCO3
        alkalinity_eq_L = alkalinity_mg_L / 50 / 1000  # mg/L as CaCO3 to eq/L
        hardness_eq_L = (ca_mg_L * 2 / 40.078 + mg_mg_L * 2 / 24.305) / 1000

        # Removable hardness = min(hardness, alkalinity)
        removable_hardness_eq_L = min(hardness_eq_L, alkalinity_eq_L)

        # Operating capacity at feed pH
        # WAC-Na has good capacity above pH 7
        if pH_feed >= 7:
            capacity_fraction = 0.75  # 75% of total
        elif pH_feed >= 6:
            capacity_fraction = 0.50
        else:
            capacity_fraction = 0.25

        operating_capacity = total_capacity_eq_L * capacity_fraction

        # Theoretical BV
        if removable_hardness_eq_L > 0:
            BV_theoretical = operating_capacity / removable_hardness_eq_L
        else:
            BV_theoretical = 0

        # LUB similar to WAC-H
        if flow_BV_hr <= 10:
            LUB_fraction = 0.06
        elif flow_BV_hr <= 20:
            LUB_fraction = 0.06 + 0.004 * (flow_BV_hr - 10)
        else:
            LUB_fraction = 0.10 + 0.002 * (flow_BV_hr - 20)

        LUB_fraction = min(LUB_fraction, 0.20)
        utilization = 1 - LUB_fraction

        # Actual breakthrough
        BV_actual = BV_theoretical * utilization

        # Run length
        if flow_BV_hr > 0:
            run_length_hrs = BV_actual / flow_BV_hr
        else:
            run_length_hrs = 0

        return {
            'BV_breakthrough': BV_actual,
            'BV_theoretical': BV_theoretical,
            'operating_capacity_eq_L': operating_capacity,
            'removable_hardness_mg_L': removable_hardness_eq_L * 50000,
            'utilization': utilization,
            'LUB_fraction': LUB_fraction,
            'run_length_hrs': run_length_hrs,
            'capacity_fraction': capacity_fraction,
            'pH_limitation': pH_feed < 7
        }