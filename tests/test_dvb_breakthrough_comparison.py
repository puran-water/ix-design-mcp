#!/usr/bin/env python
"""
Test to compare breakthrough volumes for different DVB percentages.
This will help diagnose if the enhanced exchange species are actually affecting the results.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sac_simulation import SACSimulation, SACWaterComposition

def test_dvb_breakthrough():
    """Compare breakthrough for 8% vs 16% DVB."""

    # Create simulation instance
    sim = SACSimulation()

    # Define water composition
    water = SACWaterComposition(
        flow_m3_hr=10,
        ca_mg_l=100,
        mg_mg_l=30,
        na_mg_l=100,
        cl_mg_l=300,
        hco3_mg_l=61,
        temperature_celsius=25,
        pH=7.5
    )

    # Base vessel config
    base_vessel = {
        'diameter_m': 1.0,
        'bed_depth_m': 1.5,
        'bed_volume_L': 3.14159 * 0.5**2 * 1.5 * 1000,  # ~1178 L
        'resin_capacity_eq_L': 2.0
    }

    print("\n" + "="*60)
    print("DVB BREAKTHROUGH COMPARISON TEST")
    print("="*60)
    print(f"\nWater composition:")
    print(f"  Ca: {water.ca_mg_l} mg/L")
    print(f"  Mg: {water.mg_mg_l} mg/L")
    print(f"  Na: {water.na_mg_l} mg/L")
    print(f"  pH: {water.pH}")

    results = {}

    # Test 8% DVB
    vessel_8 = base_vessel.copy()
    vessel_8['dvb_percent'] = 8

    print(f"\n[TEST] Running with 8% DVB...")
    try:
        bv_array_8, curves_8 = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_8,
            max_bv=300,  # Enough to see breakthrough
            cells=10,     # More cells for accuracy
            enable_enhancements=True,
            capacity_factor=1.0
        )

        # Find breakthrough point (5 mg/L as CaCO3 = 2 mg/L Ca)
        ca_effluent_8 = curves_8.get('Ca', [0] * len(bv_array_8))
        breakthrough_idx_8 = next((i for i, ca in enumerate(ca_effluent_8) if ca > 2.0), len(bv_array_8)-1)
        breakthrough_bv_8 = bv_array_8[breakthrough_idx_8]

        results['8% DVB'] = breakthrough_bv_8
        print(f"  Breakthrough at: {breakthrough_bv_8:.1f} BV")
        print(f"  Final Ca: {ca_effluent_8[-1]:.2f} mg/L")

    except Exception as e:
        print(f"  FAILED: {e}")
        results['8% DVB'] = None

    # Test 16% DVB
    vessel_16 = base_vessel.copy()
    vessel_16['dvb_percent'] = 16

    print(f"\n[TEST] Running with 16% DVB...")
    try:
        bv_array_16, curves_16 = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_16,
            max_bv=300,
            cells=10,
            enable_enhancements=True,
            capacity_factor=1.0
        )

        # Find breakthrough point
        ca_effluent_16 = curves_16.get('Ca', [0] * len(bv_array_16))
        breakthrough_idx_16 = next((i for i, ca in enumerate(ca_effluent_16) if ca > 2.0), len(bv_array_16)-1)
        breakthrough_bv_16 = bv_array_16[breakthrough_idx_16]

        results['16% DVB'] = breakthrough_bv_16
        print(f"  Breakthrough at: {breakthrough_bv_16:.1f} BV")
        print(f"  Final Ca: {ca_effluent_16[-1]:.2f} mg/L")

    except Exception as e:
        print(f"  FAILED: {e}")
        results['16% DVB'] = None

    # Compare results
    print("\n" + "-"*60)
    print("COMPARISON RESULTS:")
    print("-"*60)

    if results['8% DVB'] and results['16% DVB']:
        bv_8 = results['8% DVB']
        bv_16 = results['16% DVB']
        increase = (bv_16 - bv_8) / bv_8 * 100

        print(f"8% DVB breakthrough:  {bv_8:.1f} BV")
        print(f"16% DVB breakthrough: {bv_16:.1f} BV")
        print(f"Increase: {increase:.1f}%")

        # Our database shows Ca selectivity increases ~41% from 8% to 16%
        # But actual effect on breakthrough should be less due to competition
        print(f"\nExpected increase (from selectivity): ~15-20%")

        if increase > 5:
            print("\nPASS: DVB effect observed!")
        else:
            print("\nFAIL: No significant DVB effect")
            print("\nPossible issues:")
            print("1. Selectivity values may be wrong (Li+ vs Na+ reference)")
            print("2. Exchange species may override native database incorrectly")
            print("3. Competition effects may mask DVB differences")
    else:
        print("One or both simulations failed")

    return results


if __name__ == "__main__":
    test_dvb_breakthrough()