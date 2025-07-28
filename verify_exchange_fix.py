#!/usr/bin/env python3
"""Verify the exchange capacity fix."""

import sys

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

print("Verifying Exchange Capacity Calculation")
print("="*40)

# Test values
bed_volume_L = 6250
porosity = 0.4
cells = 10
resin_capacity_eq_L = 2.0

# Old calculation (wrong)
pore_volume_L = bed_volume_L * porosity
water_per_cell_kg = pore_volume_L / cells
total_capacity_eq = resin_capacity_eq_L * bed_volume_L / 1000
old_exchange = total_capacity_eq / cells / water_per_cell_kg

print(f"Old calculation (wrong):")
print(f"  Total capacity: {total_capacity_eq} eq")
print(f"  Water per cell: {water_per_cell_kg} kg")
print(f"  Exchange per kg water: {old_exchange:.6f} mol/kg")
print(f"  This is way too low!")

# New calculation (correct)
bed_volume_per_cell_L = bed_volume_L / cells
exchange_per_cell_eq = resin_capacity_eq_L * bed_volume_per_cell_L / 1000
new_exchange = exchange_per_cell_eq / water_per_cell_kg

print(f"\nNew calculation (correct):")
print(f"  Bed volume per cell: {bed_volume_per_cell_L} L")
print(f"  Exchange per cell: {exchange_per_cell_eq} eq")
print(f"  Water per cell: {water_per_cell_kg} kg")
print(f"  Exchange per kg water: {new_exchange:.6f} mol/kg")

# Expected value check
# Each cell has 625 L bed volume with 2.0 eq/L = 1.25 eq
# Each cell has 250 kg water
# So exchange = 1.25 / 250 = 0.005 mol/kg
expected = 1.25 / 250
print(f"\nExpected: {expected:.6f} mol/kg")
print(f"Match: {abs(new_exchange - expected) < 0.0001}")

# But wait, this is the same as the old calculation!
# The issue must be elsewhere...

print("\n" + "="*40)
print("WAIT - The calculations give the same result!")
print("The issue must be in the PHREEQC input or interpretation.")
print("\nLet me check the actual capacity distribution...")

# The real issue might be that we need more exchange sites
# SAC resin in Na form initially should have enough sites
print(f"\nTotal exchange sites in column: {resin_capacity_eq_L * bed_volume_L / 1000} eq")
print(f"Hardness load per BV: {6 * 1} meq = 0.006 eq")
print(f"Theoretical BVs: {(resin_capacity_eq_L * bed_volume_L / 1000) / 0.006:.0f}")
print("\nThe math checks out, so the issue must be in PHREEQC equilibration...")