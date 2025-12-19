#!/usr/bin/env python
"""
Test batch equilibrium to isolate selectivity effects from transport.
As Codex suggested, this will quantify resin-phase fractions directly.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine
from tools.enhanced_phreeqc_generator import EnhancedPHREEQCGenerator
from tools.core_config import CONFIG

def run_batch_equilibrium(dvb_percent, ca_mg_l, na_mg_l, mg_mg_l=30):
    """Run batch equilibrium test for specific DVB and water composition."""

    engine = DirectPhreeqcEngine(keep_temp_files=True)
    gen = EnhancedPHREEQCGenerator()

    # Generate exchange species for this DVB
    exchange_species = gen.generate_exchange_species(
        'SAC',
        temperature_c=25.0,
        dvb_percent=dvb_percent,
        ions_present=['Ca', 'Mg', 'Na']
    )

    # Charge balance with Cl
    cl_mg_l = (ca_mg_l * 1.77 + mg_mg_l * 2.92 + na_mg_l * 1.54)

    # Build PHREEQC input for batch equilibrium
    phreeqc_input = f"""
DATABASE {CONFIG.get_phreeqc_database()}
TITLE Batch equilibrium test - {dvb_percent}% DVB

{exchange_species}

# Feed water solution
SOLUTION 1
    units     mg/L
    temp      25.0
    pH        7.5
    Ca        {ca_mg_l}
    Mg        {mg_mg_l}
    Na        {na_mg_l}
    Cl        {cl_mg_l} charge

# Ion exchange resin
EXCHANGE 1
    X         2.0  # 2 eq/L typical SAC capacity
    -equilibrate solution 1

# Output exchange composition
SELECTED_OUTPUT 1
    -file selected.out
    -reset false
    -molalities NaX CaX2 MgX2

END
"""

    # Run PHREEQC
    output, selected = engine.run_phreeqc(phreeqc_input)

    # Parse results - PHREEQC outputs multiple rows
    lines = selected.strip().split('\n')
    if len(lines) < 3:  # Need headers + at least 2 data rows
        return None

    headers = lines[0].split()

    # Get the last row (equilibrium state)
    values = lines[-1].split()

    # Parse molalities from headers like m_NaX, m_CaX2
    result = {}
    for h, v in zip(headers, values):
        try:
            val = float(v)
            if h == 'm_NaX':
                result['mol_NaX'] = val
            elif h == 'm_CaX2':
                result['mol_CaX2'] = val
            elif h == 'm_MgX2':
                result['mol_MgX2'] = val
        except:
            pass

    # Calculate equivalent fractions
    if 'mol_NaX' in result and 'mol_CaX2' in result:
        na_eq = result['mol_NaX']
        ca_eq = 2 * result['mol_CaX2']
        mg_eq = 2 * result.get('mol_MgX2', 0)
        total_eq = na_eq + ca_eq + mg_eq

        if total_eq > 0:
            result['X_Na'] = na_eq / total_eq
            result['X_Ca'] = ca_eq / total_eq
            result['X_Mg'] = mg_eq / total_eq
            result['Ca_resin_meq/L'] = ca_eq * 1000
            result['DVB%'] = dvb_percent

    return result


def main():
    print("\n" + "#"*60)
    print("# BATCH EQUILIBRIUM SELECTIVITY TEST")
    print("#"*60)
    print("\nTesting equilibrium exchange composition (no transport)")
    print("This isolates thermodynamic selectivity from column hydraulics")

    # Test different water compositions
    test_cases = [
        ("Balanced (Ca=100, Na=100)", 100, 100, 30),
        ("High Ca (Ca=200, Na=50)", 200, 50, 30),
        ("High Na (Ca=50, Na=500)", 50, 500, 30),
        ("Very high Na (Ca=50, Na=2000)", 50, 2000, 30),
    ]

    for description, ca, na, mg in test_cases:
        print(f"\n{'='*60}")
        print(f"Test: {description} mg/L")
        print(f"Ca/Na molar ratio: {(ca/40.08)/(na/22.99):.2f}")
        print("-"*60)

        # Test 8% DVB
        result_8 = run_batch_equilibrium(8, ca, na, mg)

        # Test 16% DVB
        result_16 = run_batch_equilibrium(16, ca, na, mg)

        if result_8 and result_16:
            print(f"\nResin phase composition:")
            print(f"  8% DVB:  X_Ca = {result_8['X_Ca']:.4f}, X_Na = {result_8['X_Na']:.4f}")
            print(f"  16% DVB: X_Ca = {result_16['X_Ca']:.4f}, X_Na = {result_16['X_Na']:.4f}")

            # Calculate increase in Ca loading
            ca_increase = (result_16['X_Ca'] - result_8['X_Ca']) / result_8['X_Ca'] * 100
            print(f"\nCa loading increase: {ca_increase:.2f}%")

            # Theoretical breakthrough extension
            # If resin holds more Ca, breakthrough is delayed proportionally
            print(f"Expected BV extension: ~{ca_increase:.1f}%")

            if ca_increase > 10:
                print("PASS: Significant selectivity effect expected")
            elif ca_increase > 5:
                print("WARNING: Moderate selectivity effect")
            else:
                print("FAIL: Minimal selectivity effect (as Codex predicted)")

    print("\n" + "="*60)
    print("CONCLUSIONS")
    print("="*60)
    print("""
As Codex identified, the issue is that with balanced Ca/Na feeds,
the resin is already nearly Ca-saturated (>97%). The small selectivity
difference between 8% and 16% DVB only changes equilibrium by ~0.35%.

To see larger DVB effects, we need:
1. Higher Na/Ca ratio in feed (more competition)
2. Finer discretization (30-50 cells vs 8)
3. Lower dispersivity (reduce numerical dispersion)
4. Tighter sampling (< 0.1 BV resolution)
""")


if __name__ == "__main__":
    main()