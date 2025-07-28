#!/usr/bin/env python3
"""
Verify standard SAC capacity calculations and scale test results
"""

import sys
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def analyze_capacities():
    """Analyze and compare different capacity representations"""
    
    print("STANDARD SAC RESIN CAPACITY ANALYSIS")
    print("=" * 60)
    
    # Standard SAC parameters
    resin_capacity_eq_L_resin = 2.0  # eq/L of resin
    porosity = 0.4
    
    print(f"Standard SAC resin: {resin_capacity_eq_L_resin} eq/L resin")
    print(f"Bed porosity: {porosity}")
    print()
    
    # Per cubic meter of bed
    bed_volume_m3 = 1.0
    bed_volume_L = bed_volume_m3 * 1000
    resin_volume_L = bed_volume_L * (1 - porosity)
    water_volume_L = bed_volume_L * porosity
    
    print("Per m³ of bed:")
    print(f"  Resin volume: {resin_volume_L:.0f} L")
    print(f"  Water volume: {water_volume_L:.0f} L")
    
    # Total capacity
    total_capacity_eq = resin_capacity_eq_L_resin * resin_volume_L
    print(f"  Total capacity: {total_capacity_eq:.0f} eq")
    
    # Different ways to express capacity
    capacity_eq_L_bed = total_capacity_eq / bed_volume_L
    capacity_mol_kg_water = total_capacity_eq / water_volume_L  # assuming 1 kg/L water
    
    print()
    print("Capacity expressed different ways:")
    print(f"  {resin_capacity_eq_L_resin:.1f} eq/L resin")
    print(f"  {capacity_eq_L_bed:.1f} eq/L bed")
    print(f"  {capacity_mol_kg_water:.1f} mol/kg water")
    
    # Feed water analysis
    print("\n" + "-" * 60)
    print("FEED WATER ANALYSIS:")
    
    ca_mg_L = 180
    mg_mg_L = 80
    na_mg_L = 200
    
    ca_meq_L = ca_mg_L / 20.04
    mg_meq_L = mg_mg_L / 12.15
    na_meq_L = na_mg_L / 23.0
    total_hardness_meq_L = ca_meq_L + mg_meq_L
    
    print(f"  Ca: {ca_mg_L} mg/L = {ca_meq_L:.2f} meq/L")
    print(f"  Mg: {mg_mg_L} mg/L = {mg_meq_L:.2f} meq/L")
    print(f"  Na: {na_mg_L} mg/L = {na_meq_L:.2f} meq/L")
    print(f"  Total hardness: {total_hardness_meq_L:.2f} meq/L")
    
    # Theoretical breakthrough
    print("\n" + "-" * 60)
    print("THEORETICAL BREAKTHROUGH VOLUMES:")
    
    # Method 1: Using eq/L bed
    theoretical_bv_1 = capacity_eq_L_bed * 1000 / total_hardness_meq_L
    print(f"\nMethod 1 (eq/L bed basis):")
    print(f"  {capacity_eq_L_bed:.1f} eq/L × 1000 ÷ {total_hardness_meq_L:.2f} meq/L = {theoretical_bv_1:.1f} BV")
    
    # Method 2: Using total capacity
    theoretical_bv_2 = total_capacity_eq / total_hardness_meq_L
    print(f"\nMethod 2 (total capacity basis):")
    print(f"  {total_capacity_eq:.0f} eq/m³ ÷ {total_hardness_meq_L:.2f} eq/m³ = {theoretical_bv_2:.1f} BV")
    
    # Test results analysis
    print("\n" + "-" * 60)
    print("TEST RESULTS ANALYSIS:")
    
    test_scenarios = [
        {
            'name': 'Comprehensive Test',
            'capacity_mol_kg': 0.015,
            'actual_bv_0': 0.80,
            'actual_bv_1000': 0.70
        },
        {
            'name': 'Low Capacity Test',
            'capacity_mol_kg': 0.01,
            'actual_bv_0': 2.2,
            'actual_bv_1000': 1.6
        }
    ]
    
    for test in test_scenarios:
        print(f"\n{test['name']}:")
        
        # Calculate equivalent resin capacity
        test_total_eq = test['capacity_mol_kg'] * water_volume_L
        test_resin_eq_L = test_total_eq / resin_volume_L
        
        print(f"  Test capacity: {test['capacity_mol_kg']:.3f} mol/kg water")
        print(f"  Equivalent to: {test_resin_eq_L:.3f} eq/L resin")
        print(f"  Ratio to standard: {test_resin_eq_L/resin_capacity_eq_L_resin*100:.1f}%")
        
        # Scale results
        scale_factor = resin_capacity_eq_L_resin / test_resin_eq_L
        scaled_bv_0 = test['actual_bv_0'] * scale_factor
        scaled_bv_1000 = test['actual_bv_1000'] * scale_factor
        
        print(f"  Scaled to 2.0 eq/L:")
        print(f"    0 mg/L Na: {test['actual_bv_0']:.2f} → {scaled_bv_0:.0f} BV")
        print(f"    1000 mg/L Na: {test['actual_bv_1000']:.2f} → {scaled_bv_1000:.0f} BV")
        
        # Calculate utilization
        test_theoretical = test_resin_eq_L * 600 / total_hardness_meq_L  # 600 L resin/m³
        util_0 = test['actual_bv_0'] / test_theoretical * 100
        util_1000 = test['actual_bv_1000'] / test_theoretical * 100
        
        print(f"  Utilization:")
        print(f"    0 mg/L Na: {util_0:.0f}%")
        print(f"    1000 mg/L Na: {util_1000:.0f}%")
    
    # Industrial expectations
    print("\n" + "-" * 60)
    print("INDUSTRIAL EXPECTATIONS:")
    
    typical_utilization = 0.4  # 40% typical
    
    print(f"\nFor standard SAC (2.0 eq/L) with this water:")
    print(f"  Theoretical (100%): {theoretical_bv_1:.0f} BV")
    print(f"  Typical (40%): {theoretical_bv_1 * typical_utilization:.0f} BV")
    print(f"  Conservative (30%): {theoretical_bv_1 * 0.3:.0f} BV")
    
    print("\nWith sodium competition:")
    competition_factors = {
        0: 1.0,
        200: 0.95,
        500: 0.85,
        1000: 0.70
    }
    
    for na, factor in competition_factors.items():
        expected_bv = theoretical_bv_1 * typical_utilization * factor
        print(f"  {na:4d} mg/L Na: {expected_bv:.0f} BV (factor: {factor})")

if __name__ == "__main__":
    analyze_capacities()