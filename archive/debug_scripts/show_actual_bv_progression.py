#!/usr/bin/env python3
"""
Show Actual BV Progression - Corrected Approach

This demonstrates the actual BV values during breakthrough
using the correct resolution-independent approach.
"""

import sys
from pathlib import Path
import numpy as np

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine
from watertap_ix_transport.utilities.phreeqc_helpers import calculate_bv_parameters


def run_corrected_breakthrough(cells):
    """Run with corrected approach and show detailed progression"""
    
    engine = DirectPhreeqcEngine(keep_temp_files=False)
    
    # Parameters
    diameter_m = 0.1
    bed_depth_m = 1.0
    porosity = 0.4
    
    # Calculate parameters
    params = calculate_bv_parameters(bed_depth_m, diameter_m, porosity, cells)
    
    # Feed
    feed_ca = 180.0  # mg/L
    feed_mg = 80.0   # mg/L
    
    # Resin
    resin_capacity_eq_L = 2.0
    total_capacity_eq = resin_capacity_eq_L * params['resin_volume_L']
    
    # Key calculations
    water_per_cell_kg = params['water_per_cell_kg']
    exchange_mol_per_cell = total_capacity_eq / cells
    exchange_per_kg_water = exchange_mol_per_cell / water_per_cell_kg
    
    # Run to 135 BV
    shifts = int(135 * cells)
    
    # Output frequently around breakthrough
    punch_freq = max(1, cells // 10)  # Every 0.1 BV
    
    print(f"\n{'='*70}")
    print(f"{cells} CELLS - CORRECTED APPROACH")
    print(f"{'='*70}")
    print(f"Water per cell: {water_per_cell_kg:.3f} kg")
    print(f"Total pore volume: {params['total_pore_volume_L']:.3f} L") 
    print(f"Exchange per kg water: {exchange_per_kg_water:.3f} mol/kg")
    print(f"Total capacity: {total_capacity_eq:.2f} eq")
    
    phreeqc_input = f"""
TITLE Corrected BV Progression - {cells} cells

EXCHANGE_SPECIES
    Na+ + X- = NaX
        log_k   0.0
    Ca+2 + 2X- = CaX2
        log_k   1.6
    Mg+2 + 2X- = MgX2
        log_k   1.3

SOLUTION 0  # Feed
    units     mg/L
    temp      25.0
    pH        7.5
    Ca        {feed_ca}
    Mg        {feed_mg}
    Na        50
    Cl        400 charge
    C(4)      300 as HCO3

# CRITICAL: Specify exact water amount
SOLUTION 1-{cells}
    units     mg/L
    temp      25.0
    pH        7.0
    Na        1000
    Cl        1540 charge
    water     {water_per_cell_kg} kg

EXCHANGE 1-{cells}
    X         {exchange_per_kg_water}  # mol/kg water
    -equilibrate with solution 1-{cells}

TRANSPORT
    -cells    {cells}
    -shifts   {shifts}
    -lengths  {params['cell_length_m']}
    -dispersivities {cells}*0.005
    -porosities {porosity}
    -flow_direction forward
    -boundary_conditions flux flux
    -print_frequency {shifts//20}
    -punch_frequency {punch_freq}
    -punch_cells {cells}

SELECTED_OUTPUT 1
    -file bv_progression_{cells}.csv
    -reset false
    -step true
    -totals Ca Mg Na

USER_PUNCH 1
    -headings Step BV Ca_mg/L Ca_pct
    -start
    10 PUNCH STEP_NO
    # Correct BV calculation
    20 BV = STEP_NO * {water_per_cell_kg} / {params['total_pore_volume_L']}
    30 PUNCH BV
    40 ca_mg = TOT("Ca") * 40.078 * 1000
    50 PUNCH ca_mg
    60 PUNCH ca_mg / {feed_ca} * 100
    -end

END
"""
    
    try:
        output, selected = engine.run_phreeqc(phreeqc_input)
        data = engine.parse_selected_output(selected)
        
        if data:
            # Extract effluent data
            effluent = [row for row in data if row.get('Step', 0) > 0]
            
            # Show progression around breakthrough
            print(f"\nBV PROGRESSION (showing key points):")
            print(f"{'BV':>8} {'Ca (mg/L)':>12} {'Ca/Ca₀ (%)':>12} {'Status':>20}")
            print("-" * 60)
            
            last_shown_bv = 0
            ca_5_shown = False
            ca_50_shown = False
            
            for row in effluent:
                bv = row.get('BV', 0)
                ca_mg = row.get('Ca_mg/L', 0)
                ca_pct = row.get('Ca_pct', 0)
                
                # Determine what to show
                show = False
                status = ""
                
                if bv < 100 and bv >= last_shown_bv + 10:
                    show = True
                    status = "Pre-breakthrough"
                elif 100 <= bv < 120 and bv >= last_shown_bv + 5:
                    show = True
                    status = "Approaching"
                elif 120 <= bv < 130 and bv >= last_shown_bv + 1:
                    show = True
                    if ca_pct < 1:
                        status = "Early breakthrough"
                    elif ca_pct < 10:
                        status = "Breakthrough"
                    else:
                        status = "Rapid rise"
                elif bv >= 130 and bv >= last_shown_bv + 2:
                    show = True
                    status = "Exhausted"
                
                # Always show 5% and 50% points
                if not ca_5_shown and ca_pct >= 5:
                    show = True
                    status = "→ 5% breakthrough"
                    ca_5_shown = True
                elif not ca_50_shown and ca_pct >= 50:
                    show = True
                    status = "→ 50% breakthrough"
                    ca_50_shown = True
                
                if show:
                    print(f"{bv:>8.1f} {ca_mg:>12.1f} {ca_pct:>12.1f} {status:>20}")
                    last_shown_bv = bv
            
            # Find exact breakthrough points
            ca_5_bv = None
            ca_50_bv = None
            
            for i in range(1, len(effluent)):
                prev = effluent[i-1]
                curr = effluent[i]
                
                prev_pct = prev.get('Ca_pct', 0)
                curr_pct = curr.get('Ca_pct', 0)
                prev_bv = prev.get('BV', 0)
                curr_bv = curr.get('BV', 0)
                
                # 5% breakthrough
                if ca_5_bv is None and prev_pct < 5 <= curr_pct:
                    frac = (5 - prev_pct) / (curr_pct - prev_pct)
                    ca_5_bv = prev_bv + frac * (curr_bv - prev_bv)
                
                # 50% breakthrough
                if ca_50_bv is None and prev_pct < 50 <= curr_pct:
                    frac = (50 - prev_pct) / (curr_pct - prev_pct)
                    ca_50_bv = prev_bv + frac * (curr_bv - prev_bv)
            
            print("\n" + "="*60)
            print("BREAKTHROUGH SUMMARY:")
            print("="*60)
            if ca_5_bv:
                print(f"Ca 5% breakthrough:  {ca_5_bv:>6.1f} BV")
            if ca_50_bv:
                print(f"Ca 50% breakthrough: {ca_50_bv:>6.1f} BV")
            
            return {
                'cells': cells,
                'ca_5_bv': ca_5_bv,
                'ca_50_bv': ca_50_bv
            }
            
    except Exception as e:
        print(f"Error: {e}")
        return None


def main():
    """Show actual BV progression for both resolutions"""
    
    print("\n" + "="*80)
    print("ACTUAL BV PROGRESSION - RESOLUTION COMPARISON")
    print("="*80)
    print("\nUsing CORRECTED approach:")
    print("- Explicit water specification in SOLUTION blocks")
    print("- Exchange capacity as mol/kg water")
    print("- BV = STEP_NO * water_per_cell / total_pore_volume")
    print("\nExpected Ca 50% breakthrough: ~128 BV")
    
    # Run both resolutions
    results = []
    for cells in [10, 20]:
        result = run_corrected_breakthrough(cells)
        if result:
            results.append(result)
    
    # Final comparison
    if len(results) == 2:
        print("\n" + "="*80)
        print("RESOLUTION INDEPENDENCE VERIFICATION")
        print("="*80)
        
        ca_5_10 = results[0].get('ca_5_bv')
        ca_5_20 = results[1].get('ca_5_bv')
        ca_50_10 = results[0].get('ca_50_bv')
        ca_50_20 = results[1].get('ca_50_bv')
        
        if ca_50_10 and ca_50_20:
            diff = abs(ca_50_10 - ca_50_20)
            pct = diff / ca_50_10 * 100
            
            print(f"\nCa 50% breakthrough comparison:")
            print(f"  10 cells: {ca_50_10:.1f} BV")
            print(f"  20 cells: {ca_50_20:.1f} BV")
            print(f"  Difference: {diff:.1f} BV ({pct:.1f}%)")
            
            if pct < 2:
                print("\n✓ EXCELLENT: Resolution independence achieved!")
                print("  The corrected approach ensures consistent breakthrough")
                print("  regardless of the number of cells used.")
            elif pct < 5:
                print("\n✓ GOOD: Resolution independence achieved")
                print("  Minor variation is within acceptable limits.")
            else:
                print("\n⚠ WARNING: Significant variation detected")
                print("  Check the implementation.")


if __name__ == "__main__":
    main()