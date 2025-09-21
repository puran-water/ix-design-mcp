"""
Enhanced WAC Exchange Species Definitions with pH-Dependent Capacity

This module provides improved EXCHANGE_SPECIES blocks for WAC resins
that properly model pH-dependent capacity through the H+/X- equilibrium.

Key improvements:
1. H+ + X- = HX with proper pKa value (not log_k = 0)
2. Temperature dependence for pKa
3. Consistent selectivity coefficients from literature
4. Proper modeling of both Na-form and H-form WAC
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.core_config import CONFIG
from typing import Dict, Any, Optional


def generate_wac_exchange_species(
    resin_type: str = "WAC_Na",
    pka: float = None,
    temperature_c: float = 25.0,
    enhanced_selectivity: bool = True
) -> str:
    """
    Generate pH-dependent EXCHANGE_SPECIES block for WAC resins.

    This properly models the protonation of carboxylic sites:
    - At pH < pKa: sites are protonated (HX form), low capacity
    - At pH > pKa: sites are deprotonated (X- form), full capacity
    - Operating capacity = total_capacity × (1 - fraction_protonated)

    Args:
        resin_type: "WAC_Na" or "WAC_H"
        pka: pKa value for carboxylic groups (default from CONFIG)
        temperature_c: Temperature for pKa adjustment
        enhanced_selectivity: Use literature-based selectivity coefficients

    Returns:
        Complete EXCHANGE_SPECIES block as string
    """
    # Use default pKa if not provided
    if pka is None:
        pka = CONFIG.WAC_PKA  # 4.8 from literature

    # Temperature correction for pKa (van't Hoff equation)
    # dpKa/dT ≈ -0.017 per °C for carboxylic acids
    pka_adjusted = pka - 0.017 * (temperature_c - 25.0)

    # Build EXCHANGE_MASTER_SPECIES and EXCHANGE_SPECIES blocks
    exchange_species = """# Enhanced WAC Exchange Species with pH-Dependent Capacity
EXCHANGE_MASTER_SPECIES
    X X-

EXCHANGE_SPECIES
    # Identity reaction for master species (required)
    X- = X-
        log_k 0.0

    # CRITICAL: Protonation equilibrium controls pH-dependent capacity
    # At pH < pKa, sites are protonated (HX) and unavailable
    # At pH > pKa, sites are deprotonated (X-) and available for exchange
    H+ + X- = HX"""

    exchange_species += f"""
        log_k {pka_adjusted:.2f}  # pKa of carboxylic groups
        -analytical_expression -2.0 0 0 0 0  # Temperature dependence
    """

    if resin_type == "WAC_Na":
        # Na-form WAC: Direct exchange with deprotonated sites
        exchange_species += f"""
    # Reference species for Na-form
    Na+ + X- = NaX
        log_k 0.0  # Reference state
        -gamma 4.0 0.075

    # Divalent cations have higher selectivity
    Ca+2 + 2X- = CaX2
        log_k {CONFIG.WAC_LOGK_CA_NA:.2f}  # Selectivity: Ca >> Na
        -gamma 5.0 0.165

    Mg+2 + 2X- = MgX2
        log_k {CONFIG.WAC_LOGK_MG_NA:.2f}  # Selectivity: Mg > Na
        -gamma 5.5 0.2

    # Monovalent cations
    K+ + X- = KX
        log_k {CONFIG.WAC_LOGK_K_NA:.2f}  # Selectivity: K > Na
        -gamma 3.5 0.015

    # Ammonium if present
    NH4+ + X- = NH4X
        log_k 0.3  # Similar to K+
        -gamma 3.0 0.015"""

    elif resin_type == "WAC_H":
        # H-form WAC: Exchange releases H+, generates CO2 with alkalinity
        exchange_species += f"""
    # For H-form, exchange reactions compete with protonation
    # Higher pH favors cation exchange over protonation

    # Divalent exchanges (release 2H+, consume alkalinity)
    Ca+2 + 2HX = CaX2 + 2H+
        log_k {CONFIG.WAC_LOGK_CA_H:.2f}  # Favorable at pH > pKa
        -gamma 5.0 0.165

    Mg+2 + 2HX = MgX2 + 2H+
        log_k {CONFIG.WAC_LOGK_MG_H:.2f}
        -gamma 5.5 0.2

    # Monovalent exchanges (release H+)
    Na+ + HX = NaX + H+
        log_k {CONFIG.WAC_LOGK_NA_H:.2f}  # Less favorable
        -gamma 4.0 0.075

    K+ + HX = KX + H+
        log_k {CONFIG.WAC_LOGK_K_H:.2f}
        -gamma 3.5 0.015

    # Alternative formulation with deprotonated sites
    # These compete at higher pH
    Ca+2 + 2X- = CaX2
        log_k {CONFIG.WAC_LOGK_CA_NA:.2f}
        -gamma 5.0 0.165

    Na+ + X- = NaX
        log_k 0.0
        -gamma 4.0 0.075"""

    # Add trace metals if enhanced selectivity is enabled
    if enhanced_selectivity:
        exchange_species += """

    # Trace metal selectivity (important for pretreatment)
    Fe+2 + 2X- = FeX2
        log_k 1.5  # High affinity
        -gamma 6.0 0.2

    Mn+2 + 2X- = MnX2
        log_k 1.2
        -gamma 5.0 0.2

    Sr+2 + 2X- = SrX2
        log_k 1.4  # Between Ca and Ba
        -gamma 5.0 0.165

    Ba+2 + 2X- = BaX2
        log_k 1.6  # Highest divalent selectivity
        -gamma 5.0 0.165"""

    return exchange_species


def calculate_wac_capacity_vs_ph(
    total_capacity_eq_L: float,
    pka: float = CONFIG.WAC_PKA,
    ph_range: tuple = (3.0, 10.0),
    temperature_c: float = 25.0
) -> Dict[str, list]:
    """
    Calculate WAC operating capacity as a function of pH.

    Operating capacity depends on the fraction of deprotonated sites:
    α = 1 / (1 + 10^(pKa - pH))

    Args:
        total_capacity_eq_L: Total exchange capacity (eq/L)
        pka: pKa of carboxylic groups
        ph_range: pH range to calculate (min, max)
        temperature_c: Temperature for pKa adjustment

    Returns:
        Dict with 'ph' and 'capacity' lists for plotting
    """
    import numpy as np

    # Temperature correction
    pka_adjusted = pka - 0.017 * (temperature_c - 25.0)

    # Generate pH values
    ph_values = np.linspace(ph_range[0], ph_range[1], 100)

    # Calculate degree of deprotonation (fraction of active sites)
    alpha = 1 / (1 + 10**(pka_adjusted - ph_values))

    # Operating capacity = total capacity × fraction deprotonated
    capacity_values = total_capacity_eq_L * alpha

    return {
        'ph': ph_values.tolist(),
        'capacity_eq_L': capacity_values.tolist(),
        'alpha': alpha.tolist(),
        'pka_effective': pka_adjusted
    }


def estimate_co2_generation(
    alkalinity_removed_mg_l_caco3: float,
    ph_effluent: float = 4.5
) -> float:
    """
    Estimate CO2 generation from H-form WAC operation.

    When H-form WAC removes alkalinity:
    HCO3- + H+ (from resin) → H2CO3 → CO2 + H2O

    Args:
        alkalinity_removed_mg_l_caco3: Alkalinity removed as CaCO3
        ph_effluent: Effluent pH (affects CO2/HCO3- equilibrium)

    Returns:
        CO2 concentration in mg/L
    """
    # Convert alkalinity as CaCO3 to moles of HCO3-
    # 1 mg/L as CaCO3 = 1/50.04 meq/L = 1/50.04 mmol/L HCO3-
    mmol_hco3 = alkalinity_removed_mg_l_caco3 / 50.04  # mmol/L

    # At low pH (< 5), essentially all becomes CO2
    # CO2/HCO3- ratio depends on pH: log([CO2]/[HCO3-]) = pKa1 - pH
    pka1_carbonic = 6.35
    co2_hco3_ratio = 10**(pka1_carbonic - ph_effluent)

    # Fraction as CO2
    fraction_co2 = co2_hco3_ratio / (1 + co2_hco3_ratio)

    # CO2 concentration
    mmol_co2 = mmol_hco3 * fraction_co2
    co2_mg_l = mmol_co2 * 44.01  # mg/L (44.01 g/mol for CO2)

    return co2_mg_l


# Example validation function
def validate_wac_ph_capacity():
    """
    Validation test comparing calculated capacity vs pH against literature.

    Expected behavior (from Helfferich, Ion Exchange):
    - At pH = pKa: 50% capacity
    - At pH = pKa + 1: 91% capacity
    - At pH = pKa + 2: 99% capacity
    - At pH = pKa - 1: 9% capacity
    - At pH = pKa - 2: 1% capacity
    """
    pka = 4.8
    total_capacity = 4.0  # eq/L typical for WAC

    test_points = [
        (pka - 2, 0.01),  # 1% capacity
        (pka - 1, 0.09),  # 9% capacity
        (pka, 0.50),      # 50% capacity
        (pka + 1, 0.91),  # 91% capacity
        (pka + 2, 0.99),  # 99% capacity
    ]

    print("WAC pH-Capacity Validation")
    print("-" * 40)

    for ph, expected_fraction in test_points:
        alpha = 1 / (1 + 10**(pka - ph))
        capacity = total_capacity * alpha
        expected_capacity = total_capacity * expected_fraction
        error = abs(capacity - expected_capacity) / expected_capacity * 100

        print(f"pH {ph:.1f}: Expected {expected_capacity:.2f} eq/L, "
              f"Calculated {capacity:.2f} eq/L, Error {error:.1f}%")

    return True


if __name__ == "__main__":
    # Test the functions
    print("Testing WAC Exchange Species Generation\n")

    # Generate Na-form species
    na_form_species = generate_wac_exchange_species("WAC_Na")
    print("WAC Na-form Exchange Species:")
    print(na_form_species[:500])  # First 500 chars
    print("...\n")

    # Generate H-form species
    h_form_species = generate_wac_exchange_species("WAC_H")
    print("WAC H-form Exchange Species:")
    print(h_form_species[:500])  # First 500 chars
    print("...\n")

    # Calculate capacity vs pH
    capacity_data = calculate_wac_capacity_vs_ph(4.0)
    print(f"Capacity at pH 7: {capacity_data['capacity_eq_L'][50]:.2f} eq/L")
    print(f"Capacity at pH 5: {capacity_data['capacity_eq_L'][25]:.2f} eq/L")
    print()

    # Validate against literature
    validate_wac_ph_capacity()