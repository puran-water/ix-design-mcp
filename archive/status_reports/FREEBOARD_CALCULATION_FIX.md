# Freeboard Calculation Fix Summary

## Issue Identified
The freeboard calculation in `ix_configuration.py` was incorrect, resulting in vessels with only 25% freeboard instead of the intended 125% for WAC resins.

## Root Cause
The formula on line 274 was:
```python
freeboard_m = bed_depth * (resin_props["freeboard_percent"] / 100 - 1)
```

With `freeboard_percent = 125`, this incorrectly calculated:
- freeboard = bed_depth × (1.25 - 1) = bed_depth × 0.25 = 25% of bed depth

## Changes Made

### 1. Fixed Freeboard Formula
Changed to:
```python
freeboard_m = bed_depth * (resin_props["freeboard_percent"] / 100)
```

Now correctly calculates:
- WAC resins: freeboard = bed_depth × 1.25 = 125% of bed depth
- SAC resins: freeboard = bed_depth × 1.0 = 100% of bed depth

### 2. Updated SAC Freeboard Requirement
- Changed SAC freeboard from 125% to 100%
- SAC resins are most swollen in H+ form (regenerated state)
- They contract during service, requiring less freeboard than WAC

### 3. Added Comprehensive Documentation
Added detailed explanation of resin swelling behavior:
- WAC resins swell up to 90% when converting from H+ to Na+ form
- SAC resins behave opposite - most swollen in H+ form
- Freeboard must accommodate both swelling and backwash expansion

### 4. Improved Vessel Height Calculation
- Clarified distributor space: 0.3m bottom + 0.2m top
- Total vessel height = bed depth + freeboard + 0.5m

## Test Results
Created test script that confirms:
- WAC resins: 125% freeboard (e.g., 1.88m freeboard for 1.5m bed)
- SAC resins: 100% freeboard (e.g., 1.5m freeboard for 1.5m bed)
- Vessel height ratios are now correct

## Industry Standards Alignment
The corrected calculations now align with:
- User's experience: WAC requires 125% freeboard
- Industry practice: Freeboard typically equals bed height (100%)
- Resin manufacturer recommendations for swelling allowance

## Impact
Vessels will now be properly sized to:
1. Accommodate WAC resin swelling during service
2. Allow adequate backwash expansion (50%)
3. Prevent resin loss and operational issues
4. Match industry-standard vessel designs