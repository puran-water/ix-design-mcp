#!/usr/bin/env python3
"""
Extract and display BV progression data from test runs
"""

import sys
from pathlib import Path
import csv
from tabulate import tabulate

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


def read_csv_data(filepath):
    """Read PHREEQC selected output CSV file"""
    data = []
    try:
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    except:
        pass
    return data


def show_breakthrough_region(cells):
    """Show data around breakthrough for given cell count"""
    
    # Try different possible filenames
    filenames = [
        f"verified_{cells}cells.csv",
        f"final_{cells}cells.csv",
        f"sac_corrected_{cells}cells.csv",
        f"resolution_{cells}cells.csv"
    ]
    
    # Look in temp directories
    import os
    import glob
    
    # Find recent PHREEQC temp directories
    temp_base = "C:\\Users\\hvksh\\AppData\\Local\\Temp"
    phreeqc_dirs = glob.glob(os.path.join(temp_base, "phreeqc_*"))
    
    data = None
    source_file = None
    
    # Try to find the file
    for phreeqc_dir in sorted(phreeqc_dirs, reverse=True)[:10]:  # Check last 10
        for filename in filenames:
            filepath = os.path.join(phreeqc_dir, filename)
            if os.path.exists(filepath):
                data = read_csv_data(filepath)
                if data:
                    source_file = filepath
                    break
        if data:
            break
    
    # Also check current directory
    if not data:
        for filename in filenames:
            if os.path.exists(filename):
                data = read_csv_data(filename)
                if data:
                    source_file = filename
                    break
    
    if not data:
        print(f"No data found for {cells} cells")
        return None
    
    print(f"\n{cells} CELLS - Data from: {source_file}")
    print("="*60)
    
    # Extract breakthrough region data
    breakthrough_data = []
    for row in data:
        try:
            # Try different column names
            bv = float(row.get('BV_correct', row.get('BV', 0)))
            ca = float(row.get('Ca_mg/L', 0))
            
            # Only show data with BV > 100 and Ca > 0
            if bv > 100 and (ca > 0 or bv > 130):
                breakthrough_data.append({
                    'BV': bv,
                    'Ca_mg/L': ca,
                    'Ca_%': ca / 180 * 100  # As percentage of feed
                })
        except:
            continue
    
    if breakthrough_data:
        # Show every 5th point or key points
        filtered_data = []
        last_bv = 0
        
        for point in breakthrough_data:
            bv = point['BV']
            ca_pct = point['Ca_%']
            
            # Include key points
            if (bv >= last_bv + 2 or  # Every 2 BV
                abs(ca_pct - 5) < 1 or  # Near 5%
                abs(ca_pct - 50) < 1 or  # Near 50%
                ca_pct > 95):  # Near exhaustion
                filtered_data.append(point)
                last_bv = bv
        
        # Create table
        headers = ['BV', 'Ca (mg/L)', 'Ca/Ca₀ (%)']
        table_data = []
        
        for point in filtered_data[:20]:  # Limit to 20 rows
            table_data.append([
                f"{point['BV']:.1f}",
                f"{point['Ca_mg/L']:.1f}",
                f"{point['Ca_%']:.1f}"
            ])
        
        print(tabulate(table_data, headers=headers, tablefmt='grid'))
        
        # Find key breakthrough points
        ca_5_bv = None
        ca_50_bv = None
        
        for i in range(1, len(breakthrough_data)):
            prev = breakthrough_data[i-1]
            curr = breakthrough_data[i]
            
            # 5% breakthrough
            if ca_5_bv is None and prev['Ca_%'] < 5 <= curr['Ca_%']:
                # Interpolate
                frac = (5 - prev['Ca_%']) / (curr['Ca_%'] - prev['Ca_%'])
                ca_5_bv = prev['BV'] + frac * (curr['BV'] - prev['BV'])
            
            # 50% breakthrough
            if ca_50_bv is None and prev['Ca_%'] < 50 <= curr['Ca_%']:
                # Interpolate
                frac = (50 - prev['Ca_%']) / (curr['Ca_%'] - prev['Ca_%'])
                ca_50_bv = prev['BV'] + frac * (curr['BV'] - prev['BV'])
        
        return {
            'cells': cells,
            'ca_5_bv': ca_5_bv,
            'ca_50_bv': ca_50_bv,
            'data_points': len(breakthrough_data)
        }
    
    return None


def main():
    """Show BV progression for 10 and 20 cells"""
    
    print("\n" + "="*80)
    print("BV PROGRESSION DATA - ACTUAL VALUES FROM TEST RUNS")
    print("="*80)
    
    results = []
    for cells in [10, 20]:
        result = show_breakthrough_region(cells)
        if result:
            results.append(result)
    
    if len(results) == 2:
        print("\n" + "="*80)
        print("BREAKTHROUGH COMPARISON")
        print("="*80)
        
        ca_5_10 = results[0].get('ca_5_bv')
        ca_5_20 = results[1].get('ca_5_bv')
        ca_50_10 = results[0].get('ca_50_bv')
        ca_50_20 = results[1].get('ca_50_bv')
        
        if ca_5_10 and ca_5_20:
            diff = abs(ca_5_10 - ca_5_20)
            pct = diff / ca_5_10 * 100
            print(f"\nCa 5% breakthrough:")
            print(f"  10 cells: {ca_5_10:.1f} BV")
            print(f"  20 cells: {ca_5_20:.1f} BV")
            print(f"  Difference: {diff:.1f} BV ({pct:.1f}%)")
        
        if ca_50_10 and ca_50_20:
            diff = abs(ca_50_10 - ca_50_20)
            pct = diff / ca_50_10 * 100
            print(f"\nCa 50% breakthrough:")
            print(f"  10 cells: {ca_50_10:.1f} BV")
            print(f"  20 cells: {ca_50_20:.1f} BV")
            print(f"  Difference: {diff:.1f} BV ({pct:.1f}%)")
            
            if pct < 2:
                print("\n✓ EXCELLENT: Resolution independence verified!")
            elif pct < 5:
                print("\n✓ GOOD: Resolution independence achieved")


if __name__ == "__main__":
    main()