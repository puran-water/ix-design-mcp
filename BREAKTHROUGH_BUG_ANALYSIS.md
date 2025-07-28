# Breakthrough Bug Analysis

## The Issue
After the MCP fixes, the tool shows breakthrough at 0.4-0.8 BV instead of ~167 BV (50% of theoretical) for high sodium water.

## Root Cause Analysis

### 1. Capacity Calculation Change
**Original**: `total_capacity_eq = resin_capacity_eq_L * resin_volume_L`
**Changed to**: `total_capacity_eq = resin_capacity_eq_L * bed_volume_L / 1000`

This was intended to fix the industry standard (2.0 eq/L refers to bed volume), but it created inconsistency.

### 2. The Real Problem
The issue is NOT the capacity calculation itself, but how we interpret `resin_capacity_eq_L`:

**Option A (Original code assumption)**:
- 2.0 eq/L means per liter of RESIN particles
- With 40% porosity: 3750 L resin in 6250 L bed
- Total capacity = 2.0 * 3750 = 7500 eq

**Option B (Industry standard)**:
- 2.0 eq/L means per liter of BED VOLUME
- Total capacity = 2.0 * 6250 = 12,500 eq
- But this means resin has 12,500/3750 = 3.33 eq/L resin

### 3. Why Early Breakthrough?
The exchange calculation in PHREEQC depends on getting the right amount of exchange sites per kg water. If we use bed volume for capacity but the exchange sites are distributed based on resin volume assumptions, we get mismatched calculations.

### 4. Additional Issues Found

#### A. Initial Na Concentration
- Changed from 1000 to 10,000 mg/L
- This might help with driving force but doesn't fix the core issue

#### B. Breakthrough Detection
- Fixed to skip initial transient (good fix)
- But exposed the underlying capacity issue

## Solution
We need to be consistent about whether 2.0 eq/L refers to:
1. Bed volume (industry standard) 
2. Resin volume (what the original code assumed)

The safest approach is to revert to the original calculation since it was producing reasonable results (~50% of theoretical with high Na competition).

## Verification
With 839 mg/L Na and 6 meq/L hardness:
- Theoretical: 333 BV
- Expected with competition: ~167 BV (50%)
- Current (broken): 0.4-0.8 BV
- Original: ~133-167 BV ✓