# CURRENT TASK: WAC Simulation Reliability Fixes

## Status: ✅ FIXES IMPLEMENTED - Ready for Testing

**Last Updated**: 2025-11-21
**Implementation Date**: 2025-11-21
**Codex Session**: 019aa7b7-e9ec-7893-99ad-ce7b567acce6

---

## Executive Summary

After comprehensive investigation with Codex CLI, we identified and fixed **two critical bugs** that prevented WAC simulations from working reliably:

1. **WAC Na+ capacity bug**: Division by `water_per_cell_kg` reduced capacity by 200x, causing premature TRANSPORT solver failure
2. **WAC Na+ TRANSPORT convergence**: High charge density and pH spikes caused "Maximum iterations exceeded" errors
3. **WAC H+ initialization**: Direct initialization failed even with `-no_edl` due to fundamental charge balance issues

All fixes have been implemented and approved by Codex. Next step: **Validation testing**.

---

## Problem 1: WAC Na+ Capacity Bug

### Root Cause (Discovered by Codex)

**File**: `watertap_ix_transport/transport_core/wac_templates.py`

**Bug** (lines 343, 346):
```python
# WRONG - divides equivalents by water mass
lines.append(f"    NaX       {mobile_eq_per_cell / water_per_cell_kg}")
lines.append(f"    NaX       {immobile_eq_per_cell / water_per_cell_kg}")
```

**Impact**:
- Mobile: 141 eq → 0.705 eq (200x reduction!)
- Immobile: 1,269 eq → 6.345 eq (200x reduction!)
- Total capacity per cell: 1,410 eq → 7.05 eq

**Symptom**: Job 58dd3c05 (original buggy version) crashed after 15 BV with "Maximum iterations exceeded" and showed all-zero hardness values.

### Fix Applied ✅

```python
# CORRECT - use full equivalents (like H-form)
lines.append(f"    NaX       {mobile_eq_per_cell}")
lines.append(f"    NaX       {immobile_eq_per_cell}")
```

**Validation**: Capacity now correctly shows 687 eq/cell in logs (was 7 eq/cell before fix).

---

## Problem 2: WAC Na+ TRANSPORT Convergence

### Root Cause (Diagnosed by Codex)

Even with capacity fix, the corrected capacity (687 eq/cell) created **extreme charge density** that stiffened the PHREEQC TRANSPORT solver:

1. **Too few cells**: 10 cells → 69 eq mobile per cell
2. **High mobile fraction**: 0.1 → large instantaneous charge swings
3. **Fast mass transfer**: alpha = 1.7e-5 → rapid mobile/immobile exchange
4. **pH spike**: XH protonation reaction caused pH to jump to 10-11 for Na-form
5. **Missing TRANSPORT controls**: No tolerance/gamma damping

**Result**: "Maximum iterations exceeded" cascade, premature termination at 15 BV.

### Fixes Applied ✅

**File**: `watertap_ix_transport/transport_core/wac_templates.py`

1. **Increased cells**: 10 → 16 (line 37)
   - Mobile eq/cell: 69 → 43 eq

2. **Reduced mobile_fraction**: 0.1 → 0.05 (line 204)
   - Mobile eq/cell: 43 → 21 eq
   - **Net effect: 70% reduction in mobile charge density**

3. **Reduced alpha**: 1.7e-5 → 5e-6 (line 225)
   - Slows mass transfer rate
   - Reduces solver stiffness

4. **Removed XH protonation for Na-form** (lines 272-278)
   - Conditional: only includes `X- + H+ = XH` when `resin_form='H'`
   - Prevents pH spike to 10-11

5. **Improved Na-form initial solution** (lines 327-340)
   - pH: 7.0 → feed pH (7.8)
   - Na: 100 mg/L → feed Na (~200 mg/L)
   - **Added**: HCO3 matching feed alkalinity (366 mg/L)
   - Prevents pH shock when feed enters

6. **Added TRANSPORT stability controls** (lines 383-384)
   - `-tolerance 1e-10` (tighter tolerance for stiff problems)
   - `-gamma 0.35` (advection damping coefficient)
   - Prevents "Maximum iterations exceeded" cascade

**Expected outcome**: Stable convergence with realistic hardness breakthrough curve (gradual increase from ~0 to breakthrough).

---

## Problem 3: WAC H+ Direct Initialization Failure

### Root Cause

Even with `-no_edl` (which eliminated `calc_psi_avg` Donnan error), direct initialization still failed:

**Configuration**:
- Initial solution: Nearly pure water (pH 7.0, minimal ions)
- SURFACE sites: ~17,800 mol of Wac_sOH per cell
- When sites deprotonate: Massive H+ release into tiny water volume

**Error** (Job 7b534a64):
```
ERROR: Wac_s Surface mass balance has not converged. Residual: 2.927391e+03
ERROR: Mass of water is less than 1e-10 kilogram
ERROR: pH Charge balance has not converged. Residual: 3.070791e+01
```

**Codex conclusion**:
> "Direct mode is essentially unsalvageable at these site loads and low background salt. Even with `-no_edl`, the SURFACE model cannot handle direct initialization."

### Fix Applied ✅

**File**: `tools/wac_simulation.py` (lines 1442-1448)

**Changed from**:
```python
# Conditional staged initialization (only for TDS > 10 g/L OR I > 0.2 M)
needs_staged_init = tds_g_l > 10.0 or ionic_strength > 0.2
init_mode = 'staged' if needs_staged_init else 'direct'
```

**Changed to**:
```python
# ALWAYS use staged initialization for WAC H-form SURFACE model
# Rationale: Even with -no_edl, direct initialization dumps massive H+
# causing catastrophic charge imbalance and convergence failure
init_mode = 'staged'
```

**Expected outcome**: WAC H+ simulations converge successfully via Na-form pre-equilibration followed by gradual HCl conversion.

---

## Implementation Summary

### Files Modified

1. **watertap_ix_transport/transport_core/wac_templates.py** (8 changes)
   - Fixed capacity bug (removed `/water_per_cell_kg`)
   - Increased cells: 10 → 16
   - Reduced mobile_fraction: 0.1 → 0.05
   - Reduced alpha: 1.7e-5 → 5e-6
   - Removed XH protonation for Na-form
   - Improved Na-form initial solution (feed pH, Na, HCO3)
   - Added TRANSPORT stability controls (tolerance, gamma)

2. **tools/wac_simulation.py** (1 change)
   - Forced staged initialization for ALL WAC H+ runs

3. **tools/wac_surface_builder.py** (1 change - previous session)
   - Changed `-donnan` → `-no_edl` to eliminate `calc_psi_avg` errors

### Codex Approval ✅

From Codex session 019aa7b7-e9ec-7893-99ad-ce7b567acce6:

**Findings:**
> "WAC Na changes line up with the prior recommendations: more cells, lower mobile_fraction, lower alpha, remove XH protonation in Na runs, and initial solution at feed pH/Na. Net effect should cut per-cell charge swings and avoid the pH 10–11 spike."

> "WAC H always-staged initialization matches the earlier 'direct is unsalvageable' guidance."

**Approval:**
> "Proceed to a WAC Na regression run with those added TRANSPORT controls (and feed alkalinity in the initial solution) to confirm you now see realistic leakage and breakthrough. For WAC H, staged initialization is good—run a single high-I case to verify convergence with the new defaults."

---

## Next Steps: Validation Testing

### Test 1: SAC Regression (Baseline)
**Purpose**: Verify no regression from changes
**Expected**: 117 BV, 99.3% hardness removal, 81.7% utilization

### Test 2: WAC Na+ Full Validation
**Purpose**: Verify capacity fix + TRANSPORT stability fixes work correctly
**Water**: Ca=180, Mg=60, Na=200, HCO3=366 mg/L (same as previous tests)
**Expected outcome**:
- ✅ Stable convergence (no "Maximum iterations exceeded")
- ✅ Realistic hardness breakthrough curve (gradual increase)
- ✅ Breakthrough at 150-250 BV (similar to SAC)
- ✅ Initial leakage: <1 mg/L (not all zeros!)
- ✅ Gradual increase to breakthrough (not premature termination)

### Test 3: WAC H+ Convergence Validation
**Purpose**: Verify forced staged initialization works
**Water**: Ca=180, Mg=60, Na=200, HCO3=366 mg/L
**Expected outcome**:
- ✅ No convergence errors (no "Surface mass balance has not converged")
- ✅ Simulation completes successfully
- ✅ pH-dependent hardness leakage observable
- ✅ Breakthrough at 50-150 BV (lower than Na+ due to pH dependence)

### Success Criteria

✅ **All three simulations complete without convergence errors**
✅ **WAC Na+ shows realistic hardness breakthrough curve (not all zeros)**
✅ **WAC H+ converges with staged initialization**
✅ **Hardness removal percentages are consistent with breakthrough data**

---

## Test Execution Plan

1. Run all three simulations in sequence
2. Monitor stderr logs for convergence warnings
3. Verify breakthrough data shows realistic leakage
4. Compare results with theory (selectivity-based leakage calculations)
5. Update CHANGELOG.md with final test results

---

## Historical Context

### Previous Issue: Site Density Numerical Instability

This task builds on previous work that resolved site density issues with Pitzer database:

**Problem** (v2.2.0): Large site inventory (~18,000 mol) overwhelmed Newton-Raphson solver with Pitzer database
**Solution** (v2.2.1): Implemented auto-scaling to increase cell count when sites_per_cell > 2,000 mol

That solution addressed **WAC H+ SURFACE model** convergence with Pitzer database. The current fixes address **WAC Na+ EXCHANGE model** reliability and ensure **WAC H+ always uses staged initialization**.

---

## Key Files for Testing

- Input artifacts: `results/ix_input_*.json`
- Job logs: `jobs/{job_id}/stderr.log`
- Breakthrough data: Available via `get_breakthrough_data(job_id)` MCP tool
- Results: `jobs/{job_id}/results.json`

---

## References

- **Codex Session 019aa7b7-e9ec**: Primary analysis and recommendations
- **Previous work**: Site density auto-scaling (v2.2.1)
- **Test jobs**:
  - SAC (bae752e3): Baseline validation (completed)
  - WAC Na+ (58dd3c05): Buggy version showing capacity issue
  - WAC H+ (7b534a64): Failed direct initialization

---

**BOTTOM LINE**: All identified bugs have been fixed and approved by Codex. The code is ready for comprehensive validation testing to confirm WAC Na+ and WAC H+ simulations work reliably.
