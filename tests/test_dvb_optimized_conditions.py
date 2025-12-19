#!/usr/bin/env python
"""
Test DVB selectivity with optimized conditions as Codex recommended:
1. Higher Na/Ca ratio (more competition)
2. Finer discretization (30+ cells)
3. Lower dispersivity
4. Tighter sampling
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force reload to get latest code
for module in ['tools.sac_simulation', 'tools.enhanced_phreeqc_generator']:
    if module in sys.modules:
        del sys.modules[module]

from tools.sac_simulation import SACSimulation, SACWaterComposition
import numpy as np

def test_dvb_with_optimized_conditions():
    """Test DVB effect with conditions that maximize selectivity differences."""

    print("\n" + "#"*60)
    print("# DVB SELECTIVITY TEST - OPTIMIZED CONDITIONS")
    print("#"*60)
    print("\nUsing Codex's recommendations:")
    print("- High Na/Ca ratio (500/50 mg/L) for competition")
    print("- 30 cells (vs default 8) for fine discretization")
    print("- Zero dispersivity to eliminate numerical smearing")
    print("- 0.1 BV sampling resolution")

    sim = SACSimulation()

    # High Na/Ca ratio water (batch test showed 11.4% effect here)
    water = SACWaterComposition(
        flow_m3_hr=10,
        ca_mg_l=50,      # Low Ca
        mg_mg_l=30,
        na_mg_l=500,     # High Na for competition
        cl_mg_l=946,     # Charge balanced
        hco3_mg_l=61,
        temperature_celsius=25,
        pH=7.5
    )

    print(f"\nWater composition:")
    print(f"  Ca: {water.ca_mg_l} mg/L")
    print(f"  Na: {water.na_mg_l} mg/L")
    print(f"  Ca/Na molar ratio: {(water.ca_mg_l/40.08)/(water.na_mg_l/22.99):.3f}")

    vessel = {
        'diameter_m': 1.0,
        'bed_depth_m': 1.5,
        'bed_volume_L': 3.14159 * 0.5**2 * 1.5 * 1000,
        'resin_capacity_eq_L': 2.0
    }

    results = {}

    for dvb_percent in [8, 16]:
        print(f"\n{'='*60}")
        print(f"Running {dvb_percent}% DVB simulation...")
        print(f"{'='*60}")

        vessel_config = vessel.copy()
        vessel_config['dvb_percent'] = dvb_percent

        try:
            # Override run_sac_simulation to use optimized parameters
            # We'll modify the PHREEQC input generation

            # Monkey-patch to use zero dispersivity
            original_create = sim._create_phreeqc_input

            def patched_create(*args, **kwargs):
                # Force optimized parameters
                kwargs['cells'] = 30  # Fine discretization
                input_str = original_create(*args, **kwargs)

                # Replace dispersivity with zero
                input_str = input_str.replace('-dispersivities 30*0.002', '-dispersivities 30*0.0')

                # Increase punch frequency for fine sampling
                input_str = input_str.replace('-punch_frequency 30', '-punch_frequency 1')
                input_str = input_str.replace('-print_frequency 30', '-print_frequency 1')

                return input_str

            sim._create_phreeqc_input = patched_create

            # Run simulation with more cells
            bv_array, curves = sim.run_sac_simulation(
                water=water,
                vessel_config=vessel_config,
                max_bv=400,  # Enough to see breakthrough
                cells=30,     # Fine discretization
                enable_enhancements=True,
                capacity_factor=1.0
            )

            # Find 5% breakthrough (2.5 mg/L Ca)
            ca_effluent = curves.get('Ca', [0] * len(bv_array))
            target_ca = water.ca_mg_l * 0.05  # 5% breakthrough

            # Find breakthrough with fine resolution
            breakthrough_idx = next((i for i, ca in enumerate(ca_effluent) if ca > target_ca), len(bv_array)-1)
            breakthrough_bv = bv_array[breakthrough_idx]

            results[dvb_percent] = {
                'breakthrough_bv': breakthrough_bv,
                'final_ca': ca_effluent[-1] if ca_effluent else 0,
                'data_points': len(bv_array)
            }

            print(f"  Breakthrough at {breakthrough_bv:.2f} BV")
            print(f"  Data points: {len(bv_array)}")
            print(f"  Resolution: {bv_array[1] - bv_array[0]:.3f} BV" if len(bv_array) > 1 else "")

            # Restore original method
            sim._create_phreeqc_input = original_create

        except Exception as e:
            print(f"  ERROR: {e}")
            results[dvb_percent] = None

    # Analyze results
    print("\n" + "="*60)
    print("RESULTS COMPARISON")
    print("="*60)

    if 8 in results and 16 in results and results[8] and results[16]:
        bv_8 = results[8]['breakthrough_bv']
        bv_16 = results[16]['breakthrough_bv']

        increase = (bv_16 - bv_8) / bv_8 * 100 if bv_8 > 0 else 0

        print(f"\n8% DVB breakthrough:  {bv_8:.2f} BV")
        print(f"16% DVB breakthrough: {bv_16:.2f} BV")
        print(f"Increase: {increase:.1f}%")

        print(f"\nBatch equilibrium predicted: ~11.4% Ca loading increase")
        print(f"Column simulation shows: {increase:.1f}% breakthrough delay")

        if increase > 8:
            print("\nSUCCESS: DVB effect now visible with optimized conditions!")
        elif increase > 5:
            print("\nPARTIAL: Some DVB effect visible")
        else:
            print("\nFAIL: DVB effect still minimal despite optimizations")

        print("\nConclusion:")
        if increase < 5:
            print("Even with optimized conditions, column hydraulics may be dominating.")
            print("Consider batch operation or KINETICS modeling for better selectivity.")
        else:
            print("Optimized conditions successfully reveal DVB selectivity differences!")
            print("Key factors: High Na/Ca ratio + fine discretization + zero dispersivity")

    else:
        print("One or both simulations failed")


if __name__ == "__main__":
    test_dvb_with_optimized_conditions()