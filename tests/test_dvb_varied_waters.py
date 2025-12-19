#!/usr/bin/env python
"""
Test DVB selectivity with varied water compositions.
Tests with different Na/Ca ratios to isolate selectivity effects.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force reload for fresh database
if 'tools.enhanced_phreeqc_generator' in sys.modules:
    del sys.modules['tools.enhanced_phreeqc_generator']
if 'tools.sac_simulation' in sys.modules:
    del sys.modules['tools.sac_simulation']

from tools.sac_simulation import SACSimulation, SACWaterComposition

def test_water_composition(water_desc, ca_mg_l, na_mg_l, mg_mg_l=30):
    """Test DVB effect with a specific water composition."""

    print(f"\n{'='*60}")
    print(f"Testing: {water_desc}")
    print(f"Ca: {ca_mg_l} mg/L, Na: {na_mg_l} mg/L, Mg: {mg_mg_l} mg/L")
    print(f"{'='*60}")

    sim = SACSimulation()

    water = SACWaterComposition(
        flow_m3_hr=10,
        ca_mg_l=ca_mg_l,
        mg_mg_l=mg_mg_l,
        na_mg_l=na_mg_l,
        cl_mg_l=(ca_mg_l * 1.77 + mg_mg_l * 2.92 + na_mg_l * 1.54),  # Charge balance
        hco3_mg_l=61,
        temperature_celsius=25,
        pH=7.5
    )

    base_vessel = {
        'diameter_m': 1.0,
        'bed_depth_m': 1.5,
        'bed_volume_L': 3.14159 * 0.5**2 * 1.5 * 1000,
        'resin_capacity_eq_L': 2.0
    }

    results = {}

    # Test 8% DVB
    vessel_8 = base_vessel.copy()
    vessel_8['dvb_percent'] = 8

    try:
        bv_array_8, curves_8 = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_8,
            max_bv=400,  # Higher to ensure breakthrough
            cells=10,
            enable_enhancements=True,
            capacity_factor=1.0
        )

        ca_effluent_8 = curves_8.get('Ca', [0] * len(bv_array_8))
        # Find 5% breakthrough
        target_ca = ca_mg_l * 0.05
        breakthrough_idx_8 = next((i for i, ca in enumerate(ca_effluent_8) if ca > target_ca), len(bv_array_8)-1)
        results['8% DVB'] = bv_array_8[breakthrough_idx_8]

    except Exception as e:
        print(f"  8% DVB failed: {e}")
        results['8% DVB'] = None

    # Test 16% DVB
    vessel_16 = base_vessel.copy()
    vessel_16['dvb_percent'] = 16

    try:
        bv_array_16, curves_16 = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_16,
            max_bv=400,
            cells=10,
            enable_enhancements=True,
            capacity_factor=1.0
        )

        ca_effluent_16 = curves_16.get('Ca', [0] * len(bv_array_16))
        target_ca = ca_mg_l * 0.05
        breakthrough_idx_16 = next((i for i, ca in enumerate(ca_effluent_16) if ca > target_ca), len(bv_array_16)-1)
        results['16% DVB'] = bv_array_16[breakthrough_idx_16]

    except Exception as e:
        print(f"  16% DVB failed: {e}")
        results['16% DVB'] = None

    # Calculate improvement
    if results['8% DVB'] and results['16% DVB']:
        bv_8 = results['8% DVB']
        bv_16 = results['16% DVB']
        increase = (bv_16 - bv_8) / bv_8 * 100

        print(f"\nResults:")
        print(f"  8% DVB:  {bv_8:.1f} BV")
        print(f"  16% DVB: {bv_16:.1f} BV")
        print(f"  Increase: {increase:.1f}%")

        # Expected increase based on selectivity
        # Ca selectivity: 2.61 (8%) vs 3.07 (16%) = 17.7% increase
        # But actual effect depends on competition
        if na_mg_l < 50:  # Low Na competition
            expected = "15-20%"
        elif na_mg_l < 200:  # Moderate Na
            expected = "10-15%"
        else:  # High Na
            expected = "5-10%"

        print(f"  Expected: {expected}")
        return increase
    else:
        return 0


def main():
    """Test various water compositions."""

    print("\n" + "#"*60)
    print("# DVB SELECTIVITY TEST WITH VARIED WATERS")
    print("#"*60)

    # Test different Na/Ca ratios
    test_cases = [
        ("Low Na, High Ca (minimal competition)", 200, 20),      # Ca dominates
        ("Moderate Na, Moderate Ca", 100, 100),                   # Balanced
        ("High Na, Low Ca (strong competition)", 50, 500),        # Na dominates
        ("Seawater-like (extreme competition)", 400, 10000, 1200) # Very high TDS
    ]

    results_summary = []
    for desc, ca, na, *mg in test_cases:
        mg_val = mg[0] if mg else 30
        increase = test_water_composition(desc, ca, na, mg_val)
        results_summary.append((desc, increase))

    # Summary
    print("\n" + "#"*60)
    print("# SUMMARY")
    print("#"*60)

    for desc, increase in results_summary:
        status = "PASS" if increase > 5 else "FAIL"
        print(f"{desc[:40]:<40}: {increase:5.1f}% [{status}]")

    avg_increase = sum(r[1] for r in results_summary) / len(results_summary)
    print(f"\nAverage DVB effect: {avg_increase:.1f}%")

    if avg_increase > 10:
        print("\nOVERALL: PASS - DVB selectivity is working")
    elif avg_increase > 5:
        print("\nOVERALL: PARTIAL - Some DVB effect observed")
    else:
        print("\nOVERALL: FAIL - DVB selectivity not effective")


if __name__ == "__main__":
    main()