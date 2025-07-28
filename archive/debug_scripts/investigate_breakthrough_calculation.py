#!/usr/bin/env python3
"""
Investigate why actual breakthrough > theoretical
Check our calculations and PHREEQC behavior
"""

import sys
from pathlib import Path
import subprocess
import tempfile

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def test_simple_exchange():
    """Test a very simple exchange case to understand PHREEQC behavior"""
    
    print("INVESTIGATING BREAKTHROUGH CALCULATION")
    print("=" * 60)
    
    # Create simple test input
    phreeqc_input = """
# Simple 1-cell test to understand exchange capacity
SOLUTION 1
    units     mg/L
    temp      25
    pH        7.0
    Na        1000
    Cl        1540 charge
    water     1 kg

EXCHANGE 1
    X         0.015  # mol/kg water
    -equilibrate solution 1

SAVE exchange 1
SAVE solution 1

END

# Now flow Ca solution through
USE solution 1
USE exchange 1

SOLUTION 0  # Inlet solution
    units     mg/L
    temp      25
    pH        7.0
    Ca        180
    Mg        80
    Cl        420 charge
    water     1 kg

TRANSPORT
    -cells    1
    -shifts   10
    -timest   1
    -flow_direction forward
    -boundary_conditions flux flux
    -diffc    0
    -dispersivity 0
    -stagnant 0

SELECTED_OUTPUT
    -reset false
    -file breakthrough_test.tsv
    -simulation true
    -state true
    -solution true
    -exchange true
    -time true
    -step true
    -reaction false
    -temperature false
    -pe false
    -ionic_strength false
    -water false
    -charge_balance false
    -percent_error false
    -totals Ca Mg Na
    -molalities Ca+2 Mg+2 Na+ CaX2 MgX2 NaX

END
"""
    
    # Run PHREEQC
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pqi', delete=False) as f:
        f.write(phreeqc_input)
        input_file = f.name
    
    print(f"Created input file: {input_file}")
    
    result = subprocess.run(
        ["phreeqc", input_file],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"PHREEQC error: {result.stderr}")
        return
    
    print("\nPHREEQC output:")
    print(result.stdout)
    
    # Analyze the exchange capacity
    print("\n" + "=" * 60)
    print("CAPACITY ANALYSIS:")
    print("-" * 60)
    
    # Feed water
    ca_mg_L = 180
    mg_mg_L = 80
    ca_mol_L = ca_mg_L / 40.08 / 1000  # mol/L
    mg_mol_L = mg_mg_L / 24.305 / 1000  # mol/L
    ca_eq_L = ca_mol_L * 2  # eq/L
    mg_eq_L = mg_mol_L * 2  # eq/L
    total_hardness_eq_L = ca_eq_L + mg_eq_L
    
    print(f"Feed water:")
    print(f"  Ca: {ca_mg_L} mg/L = {ca_eq_L*1000:.2f} meq/L")
    print(f"  Mg: {mg_mg_L} mg/L = {mg_eq_L*1000:.2f} meq/L")
    print(f"  Total hardness: {total_hardness_eq_L*1000:.2f} meq/L")
    
    # Exchange capacity
    exchange_mol_kg = 0.015
    water_kg = 1.0
    total_exchange_eq = exchange_mol_kg * water_kg  # equivalents
    
    print(f"\nExchange capacity:")
    print(f"  {exchange_mol_kg} mol/kg × {water_kg} kg = {total_exchange_eq} mol X⁻")
    print(f"  = {total_exchange_eq} equivalents")
    
    # Theoretical volumes to saturate
    volumes_to_saturate = total_exchange_eq / total_hardness_eq_L
    
    print(f"\nTheoretical volumes to 100% saturation:")
    print(f"  {total_exchange_eq} eq / {total_hardness_eq_L:.5f} eq/L = {volumes_to_saturate:.2f} L")
    
    print("\nNote: With 10 shifts of 1 L each, we process 10 L total")
    print(f"This is {10/volumes_to_saturate:.1f}x the theoretical capacity")
    
    # Now test with explicit volume tracking
    print("\n" + "=" * 60)
    print("TESTING WITH EXPLICIT VOLUME TRACKING:")
    print("-" * 60)
    
    # Multi-cell test with volume tracking
    cells = 5
    water_per_cell = 0.2  # kg
    
    phreeqc_input2 = f"""
# Multi-cell test with explicit volume tracking
SOLUTION 1-{cells}
    units     mg/L
    temp      25
    pH        7.0
    Na        1000
    Cl        1540 charge
    water     {water_per_cell} kg

EXCHANGE 1-{cells}
    X         {exchange_mol_kg}  # mol/kg water
    -equilibrate solution 1-{cells}

SOLUTION 0  # Inlet solution
    units     mg/L
    temp      25
    pH        7.0
    Ca        180
    Mg        80
    Cl        420 charge
    water     {water_per_cell} kg

TRANSPORT
    -cells    {cells}
    -shifts   50
    -timest   1
    -flow_direction forward
    -boundary_conditions flux flux
    -diffc    0
    -dispersivity 0
    -stagnant 0

SELECTED_OUTPUT 1
    -reset true
    -file volume_tracking.tsv
    -step true
    -reaction false
    -totals Ca Mg Na
    
USER_PUNCH 1
    -headings Shift BV_processed Ca_cell5 Ca_frac
    -start
10 shifts = GET(1)
20 total_water = {water_per_cell} * {cells}
30 bv_processed = shifts * {water_per_cell} / total_water
40 ca_in = 180
50 ca_out = TOT("Ca") * 40.08 * 1000  # mg/L in last cell
60 ca_frac = ca_out / ca_in
70 PUNCH shifts, bv_processed, ca_out, ca_frac
    -end

END
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pqi', delete=False) as f:
        f.write(phreeqc_input2)
        input_file2 = f.name
    
    result2 = subprocess.run(
        ["phreeqc", input_file2],
        capture_output=True,
        text=True
    )
    
    if result2.returncode == 0:
        print("Multi-cell test completed successfully")
        
        # Calculate theoretical for this setup
        total_water = water_per_cell * cells
        total_exchange = exchange_mol_kg * total_water
        theoretical_bv = total_exchange / (total_hardness_eq_L * total_water)
        
        print(f"\nTheoretical breakthrough for {cells}-cell system:")
        print(f"  Total water: {total_water} kg")
        print(f"  Total exchange: {total_exchange} eq")
        print(f"  Theoretical BV: {theoretical_bv:.2f}")
        
        print("\nKey insight: Are we counting the initial pore water?")
        print("If PHREEQC counts BV from when we START flowing new solution,")
        print("then the initial Na-rich water doesn't count toward BV.")
        print("But if it counts total volume processed INCLUDING displacement")
        print("of initial water, that could explain higher BV.")

if __name__ == "__main__":
    test_simple_exchange()