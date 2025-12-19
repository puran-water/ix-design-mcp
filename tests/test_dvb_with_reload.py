#!/usr/bin/env python
"""
Test DVB selectivity with forced reload of the database.
This ensures we're using the corrected selectivity values.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import importlib

def test_dvb_with_reload():
    """Test DVB effect with fresh database load."""

    # Force reload of modules to pick up new database values
    if 'tools.enhanced_phreeqc_generator' in sys.modules:
        del sys.modules['tools.enhanced_phreeqc_generator']
    if 'tools.sac_simulation' in sys.modules:
        del sys.modules['tools.sac_simulation']

    # Now import with fresh database
    from tools.enhanced_phreeqc_generator import EnhancedPHREEQCGenerator

    print("\n" + "="*60)
    print("VERIFYING CORRECTED DATABASE VALUES")
    print("="*60)

    gen = EnhancedPHREEQCGenerator()

    # Check 8% DVB values
    species_8 = gen.generate_exchange_species('SAC', dvb_percent=8)
    print("\n8% DVB exchange species (first 500 chars):")
    print(species_8[:500])

    # Check for correct Ca log_k
    if 'log_k 0.416' in species_8 or 'log_k 0.42' in species_8:
        print("PASS: 8% DVB has correct Ca log_k (~0.416)")
    else:
        print("FAIL: 8% DVB has wrong Ca log_k")
        # Extract actual value
        import re
        match = re.search(r'Ca\+2.*?CaX2.*?\n.*?log_k\s+([\d.-]+)', species_8, re.DOTALL)
        if match:
            print(f"  Found log_k: {match.group(1)}")

    # Check 16% DVB values
    species_16 = gen.generate_exchange_species('SAC', dvb_percent=16)
    print("\n16% DVB exchange species (first 500 chars):")
    print(species_16[:500])

    if 'log_k 0.487' in species_16 or 'log_k 0.49' in species_16:
        print("PASS: 16% DVB has correct Ca log_k (~0.487)")
    else:
        print("FAIL: 16% DVB has wrong Ca log_k")
        # Extract actual value
        match = re.search(r'Ca\+2.*?CaX2.*?\n.*?log_k\s+([\d.-]+)', species_16, re.DOTALL)
        if match:
            print(f"  Found log_k: {match.group(1)}")

    # Now run actual breakthrough test
    print("\n" + "="*60)
    print("RUNNING BREAKTHROUGH TEST WITH RELOADED DATABASE")
    print("="*60)

    from tools.sac_simulation import SACSimulation, SACWaterComposition

    sim = SACSimulation()

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

    print("\nTesting 8% DVB...")
    try:
        bv_array_8, curves_8 = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_8,
            max_bv=300,
            cells=10,
            enable_enhancements=True,
            capacity_factor=1.0
        )

        ca_effluent_8 = curves_8.get('Ca', [0] * len(bv_array_8))
        breakthrough_idx_8 = next((i for i, ca in enumerate(ca_effluent_8) if ca > 2.0), len(bv_array_8)-1)
        breakthrough_bv_8 = bv_array_8[breakthrough_idx_8]
        results['8% DVB'] = breakthrough_bv_8
        print(f"  Breakthrough: {breakthrough_bv_8:.1f} BV")

    except Exception as e:
        print(f"  FAILED: {e}")
        results['8% DVB'] = None

    # Test 16% DVB
    vessel_16 = base_vessel.copy()
    vessel_16['dvb_percent'] = 16

    print("\nTesting 16% DVB...")
    try:
        bv_array_16, curves_16 = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel_16,
            max_bv=300,
            cells=10,
            enable_enhancements=True,
            capacity_factor=1.0
        )

        ca_effluent_16 = curves_16.get('Ca', [0] * len(bv_array_16))
        breakthrough_idx_16 = next((i for i, ca in enumerate(ca_effluent_16) if ca > 2.0), len(bv_array_16)-1)
        breakthrough_bv_16 = bv_array_16[breakthrough_idx_16]
        results['16% DVB'] = breakthrough_bv_16
        print(f"  Breakthrough: {breakthrough_bv_16:.1f} BV")

    except Exception as e:
        print(f"  FAILED: {e}")
        results['16% DVB'] = None

    # Compare results
    print("\n" + "="*60)
    print("RESULTS WITH RELOADED DATABASE")
    print("="*60)

    if results['8% DVB'] and results['16% DVB']:
        bv_8 = results['8% DVB']
        bv_16 = results['16% DVB']
        increase = (bv_16 - bv_8) / bv_8 * 100

        print(f"8% DVB:  {bv_8:.1f} BV")
        print(f"16% DVB: {bv_16:.1f} BV")
        print(f"Increase: {increase:.1f}%")
        print(f"Expected: ~15-17% (from 17.7% selectivity increase)")

        if increase > 10:
            print("\nPASS: DVB effect observed with corrected database!")
        else:
            print("\nFAIL: DVB effect still not significant")

    return results


if __name__ == "__main__":
    test_dvb_with_reload()