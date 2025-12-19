#!/usr/bin/env python
"""
Simple test of DVB selectivity with high Na/Ca ratio.
Based on batch equilibrium showing 11.4% effect.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sac_simulation import SACSimulation, SACWaterComposition

def main():
    print("\n" + "#"*60)
    print("# DVB TEST WITH HIGH NA/CA RATIO")
    print("#"*60)

    sim = SACSimulation()

    # High Na/Ca ratio (batch test showed 11.4% increase)
    water = SACWaterComposition(
        flow_m3_hr=10,
        ca_mg_l=50,
        mg_mg_l=30,
        na_mg_l=500,
        cl_mg_l=946,
        hco3_mg_l=61,
        temperature_celsius=25,
        pH=7.5
    )

    print(f"\nWater: Ca={water.ca_mg_l} mg/L, Na={water.na_mg_l} mg/L")
    print(f"Ca/Na molar ratio: {(water.ca_mg_l/40.08)/(water.na_mg_l/22.99):.3f}")
    print("(Batch equilibrium showed 11.4% Ca loading increase for this water)")

    vessel = {
        'diameter_m': 1.0,
        'bed_depth_m': 1.5,
        'bed_volume_L': 1178,
        'resin_capacity_eq_L': 2.0
    }

    # Test both DVB levels with more cells
    for dvb in [8, 16]:
        print(f"\n{'='*40}")
        print(f"Testing {dvb}% DVB with 20 cells...")

        vessel_config = vessel.copy()
        vessel_config['dvb_percent'] = dvb

        try:
            bv_array, curves = sim.run_sac_simulation(
                water=water,
                vessel_config=vessel_config,
                max_bv=400,
                cells=20,  # More cells than default 8
                enable_enhancements=True
            )

            ca_effluent = curves.get('Ca', [])
            if len(ca_effluent) > 0:  # Fix: Check length instead of truthiness
                # Find 5% breakthrough
                target = water.ca_mg_l * 0.05
                breakthrough_idx = next((i for i, ca in enumerate(ca_effluent) if ca > target), len(bv_array)-1)
                breakthrough_bv = bv_array[breakthrough_idx]
                print(f"  Breakthrough at {breakthrough_bv:.1f} BV")

                # Store for comparison
                if dvb == 8:
                    bv_8 = breakthrough_bv
                else:
                    bv_16 = breakthrough_bv

        except Exception as e:
            print(f"  Error: {e}")

    # Compare
    try:
        increase = (bv_16 - bv_8) / bv_8 * 100
        print(f"\n{'='*40}")
        print(f"RESULTS:")
        print(f"  8% DVB:  {bv_8:.1f} BV")
        print(f"  16% DVB: {bv_16:.1f} BV")
        print(f"  Increase: {increase:.1f}%")

        if increase > 8:
            print("\nSUCCESS: Significant DVB effect visible!")
        elif increase > 4:
            print("\nPARTIAL: Some DVB effect visible")
        else:
            print("\nLIMITED: DVB effect still small in column mode")
            print("(Numerical dispersion may still be masking the effect)")
    except:
        print("\nCould not compare results")


if __name__ == "__main__":
    main()