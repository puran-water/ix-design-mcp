#!/usr/bin/env python3
"""Verify theoretical BV calculation is correct."""

import sys

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

print("Theoretical BV Calculation Verification")
print("="*40)

# Example 1: Standard water
ca_mg_l = 80.06
mg_mg_l = 24.29
hardness_meq_l = ca_mg_l/20.04 + mg_mg_l/12.15
resin_capacity_eq_L = 2.0

theoretical_bv = (resin_capacity_eq_L / hardness_meq_l * 1000)

print(f"\nExample 1: Standard water")
print(f"  Ca: {ca_mg_l} mg/L = {ca_mg_l/20.04:.2f} meq/L")
print(f"  Mg: {mg_mg_l} mg/L = {mg_mg_l/12.15:.2f} meq/L")
print(f"  Total hardness: {hardness_meq_l:.2f} meq/L")
print(f"  Resin capacity: {resin_capacity_eq_L} eq/L")
print(f"  Theoretical BV = {resin_capacity_eq_L} / {hardness_meq_l:.2f} * 1000 = {theoretical_bv:.1f} BV")

# Example 2: High hardness water
ca_mg_l2 = 200
mg_mg_l2 = 100
hardness_meq_l2 = ca_mg_l2/20.04 + mg_mg_l2/12.15

theoretical_bv2 = (resin_capacity_eq_L / hardness_meq_l2 * 1000)

print(f"\nExample 2: High hardness water")
print(f"  Ca: {ca_mg_l2} mg/L = {ca_mg_l2/20.04:.2f} meq/L")
print(f"  Mg: {mg_mg_l2} mg/L = {mg_mg_l2/12.15:.2f} meq/L")
print(f"  Total hardness: {hardness_meq_l2:.2f} meq/L")
print(f"  Resin capacity: {resin_capacity_eq_L} eq/L")
print(f"  Theoretical BV = {resin_capacity_eq_L} / {hardness_meq_l2:.2f} * 1000 = {theoretical_bv2:.1f} BV")

# Example 3: Soft water
ca_mg_l3 = 10
mg_mg_l3 = 5
hardness_meq_l3 = ca_mg_l3/20.04 + mg_mg_l3/12.15

theoretical_bv3 = (resin_capacity_eq_L / hardness_meq_l3 * 1000)

print(f"\nExample 3: Soft water")
print(f"  Ca: {ca_mg_l3} mg/L = {ca_mg_l3/20.04:.2f} meq/L")
print(f"  Mg: {mg_mg_l3} mg/L = {mg_mg_l3/12.15:.2f} meq/L")
print(f"  Total hardness: {hardness_meq_l3:.2f} meq/L")
print(f"  Resin capacity: {resin_capacity_eq_L} eq/L")
print(f"  Theoretical BV = {resin_capacity_eq_L} / {hardness_meq_l3:.2f} * 1000 = {theoretical_bv3:.1f} BV")

print("\n✓ Formula: Theoretical BV = Capacity (eq/L) / Hardness (meq/L) * 1000")
print("  This gives bed volumes of water that can be treated")