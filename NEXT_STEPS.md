# Ion Exchange Design Tool - Next Steps

**Date**: 2025-09-26
**Status**: SAC equilibrium leakage model completed and validated

---

## Recently Completed ✅

### Week 1 - HIGH PRIORITY (DONE)
1. ✅ Extracted USEPA Gaines-Thomas equilibrium solver
   - Created `tools/equilibrium_leakage.py` (290 lines)
   - Full USEPA attribution and literature references
   - Iterative solver with mass balance normalization

2. ✅ Replaced fundamentally flawed SAC leakage model
   - **OLD**: Leakage = f(regeneration dose only) ❌
   - **NEW**: Leakage = f(feed Ca/Mg/Na composition via Gaines-Thomas) ✅
   - Modified `tools/capacity_derating.py` and `tools/breakthrough_calculator.py`

3. ✅ Created comprehensive test suite
   - 9 tests covering basic functionality, edge cases, physics validation
   - All tests passing (0.20 sec runtime)
   - Added Gaines-Thomas relationship verification (±0.001% accuracy)

4. ✅ Codex code review completed
   - Fixed inverse solver bug (selectivity coefficients now multiply correctly)
   - Enhanced calibration robustness with adaptive bracketing
   - Added physics regression tests

---

## Critical Finding from Implementation

### f_active Parameter Physical Reality

**Observation**: Achieving typical RO pretreatment hardness targets (2-5 mg/L as CaCO₃) requires:
- `f_active ≈ 0.005-0.02` (0.5-2% of bed actively exchanging)
- Our initial assumption was `f_active = 0.08-0.15` (8-15%)

**Possible Explanations**:
1. **High TDS effect**: Test case uses brackish water (840 mg/L Na)
   - High ionic strength → reduced divalent selectivity (Helfferich Ch. 5)
   - May require very sharp breakthrough for low leakage targets

2. **Parameterization may need refinement**:
   - f_active might need flow rate dependence
   - Bed depth effects not captured
   - May need separate MTZ length parameter

3. **Physical interpretation**:
   - Very low f_active could represent "plug flow" with minimal dispersion
   - Or indicates we need a different parameterization approach

**Action Required**: PHREEQC calibration (Task 6) will clarify if this is physically correct.

---

## Immediate Next Steps (Week 2)

### Task 6: Calibrate f_active with PHREEQC ⏭️ **START HERE**

**Objective**: Run 10-15 PHREEQC validation cases to:
1. Determine realistic f_active values for different water types
2. Validate ±20-30% accuracy target
3. Develop f_active correlation (if flow/bed-depth dependent)

**Test Matrix**:

| Water Type | TDS (mg/L) | Ca (mg/L) | Mg (mg/L) | Na (mg/L) | Expected f_active |
|------------|------------|-----------|-----------|-----------|-------------------|
| Freshwater Low Hardness | 200 | 20 | 5 | 30 | ? |
| Freshwater High Hardness | 400 | 120 | 40 | 50 | ? |
| Brackish Low Hardness | 2000 | 60 | 20 | 600 | ? |
| Brackish High Hardness | 2000 | 150 | 50 | 500 | ? |
| Seawater Dilute (10%) | 3500 | 40 | 130 | 1080 | ? |
| High Na/Ca Ratio | 1500 | 40 | 10 | 800 | ? (like test case) |

**PHREEQC Simulation Parameters**:
- Resin: SAC, capacity 2.0 eq/L, K_Ca_Na = 5.16, K_Mg_Na = 3.29
- Regeneration: 120 g/L NaCl
- Flow rate: 16 BV/hr
- Bed depth: 1.5 m
- Target: Hardness leakage at 90% breakthrough (10% hardness slip)

**Deliverables**:
1. Table of calibrated f_active vs water chemistry
2. Correlation equation (if pattern emerges)
3. Recommended default f_active by water type
4. Documentation of accuracy (predicted vs PHREEQC)

**Implementation**:
```python
# tools/phreeqc_calibration.py
def calibrate_f_active_matrix():
    test_cases = [
        {"name": "freshwater_low", "ca": 20, "mg": 5, "na": 30, ...},
        {"name": "brackish_high", "ca": 150, "mg": 50, "na": 500, ...},
        # ... 10-15 cases
    ]

    results = []
    for case in test_cases:
        # Run PHREEQC simulation
        phreeqc_leakage = run_phreeqc_sac(case)

        # Calibrate f_active
        calc = EquilibriumLeakageCalculator()
        f_active = calc.calibrate_f_active(
            phreeqc_leakage,
            case['ca'], case['mg'], case['na']
        )

        results.append({
            "water_type": case['name'],
            "phreeqc_leakage": phreeqc_leakage,
            "calibrated_f_active": f_active,
            "TDS": case['ca'] + case['mg'] + case['na'],
            "Na_fraction": case['na'] / (case['ca'] + case['mg'] + case['na'])
        })

    return analyze_correlation(results)
```

**Expected Outcome**:
- If f_active correlates with TDS or Na fraction → add to model
- If f_active is constant per water type → document ranges
- If f_active < 0.01 is common → update documentation/expectations

---

## Pending Tasks (Weeks 2-4)

### Task 7: Add USEPA Full Model as Tier 2 Validation (Medium Priority)

**Objective**: Integrate full USEPA HSDMIX model for detailed breakthrough curves (10-60 sec simulation time).

**Approach**:
1. Create `tools/usepa_simulator.py` wrapper
2. Convert our configuration → USEPA Excel input format
3. Run USEPA model, parse breakthrough curves
4. Add MCP tool: `simulate_ix_usepa()`

**Benefits**:
- Users can validate configuration without 5-min PHREEQC run
- Provides full breakthrough curves (not just single-point leakage)
- Cross-validation between equilibrium model (Tier 1) and transport model (Tier 2)

**Estimated Effort**: 1-2 weeks

---

### Task 8: Implement WAC_Na Alkalinity-Limited Capacity Model

**Status**: WAC-H (H-form, alkalinity removal) is complete ✅
**Remaining**: WAC-Na (Na-form, temporary hardness removal)

**Key Differences from SAC**:
- Removes only temporary hardness (limited by alkalinity)
- Two-step regeneration: HCl → H-form, then NaOH → Na-form
- pH-dependent capacity (like WAC-H)
- Bed expansion during regeneration (50% Na-form, 100% H-form)

**Files to Create/Modify**:
- `tools/wac_na_equilibrium.py` - Similar to equilibrium_leakage.py
- `tools/knowledge_based_config.py` - Implement `configure_wac_na()` (already has stub)
- `tools/wac_configuration.py` - Hydraulic sizing for WAC-Na vessels

**Reference Implementation**:
- `tools/breakthrough_calculator.py:283-361` - `calculate_wac_na_breakthrough()` already exists
- Needs integration with MCP tools

**Estimated Effort**: 3-4 days

---

### Task 9: Fix Vessel L/D Ratio Calculations

**Current Issue**: Diameter and bed depth calculated separately, L/D ratio not constrained.

**Requirement**: Iterate to achieve L/D = 1.2-2.0 (industry standard).

**Files to Modify**:
- `tools/sac_configuration.py:196-209` - Add L/D iteration
- `tools/wac_configuration.py` - Same fix needed

**Algorithm**:
```python
target_LD_min = 1.2
target_LD_max = 2.0

for iteration in range(10):
    diameter = calculate_diameter_from_velocity(...)
    bed_depth = calculate_depth_from_volume(...)

    LD_ratio = bed_depth / diameter

    if target_LD_min <= LD_ratio <= target_LD_max:
        break

    if LD_ratio < target_LD_min:
        # Too shallow, increase depth constraint
        min_bed_depth = diameter * target_LD_min
    elif LD_ratio > target_LD_max:
        # Too tall, increase diameter
        diameter = bed_depth / target_LD_max
```

**Estimated Effort**: 2-3 hours

---

### Task 10: Integrate WAC_Na into MCP

**Depends on**: Task 8 (WAC_Na implementation)

**Work Required**:
1. Add `configure_wac_ix()` MCP tool
2. Add `simulate_wac_watertap()` (if WaterTAP supports)
3. Update documentation
4. Add WAC_Na test cases

**Estimated Effort**: 1 day (after Task 8)

---

### Task 11: Remove Economics from knowledge_based_config.py

**Issue**: Economics calculations in configuration tool should be moved to separate module.

**Rationale**:
- Configuration tool should focus on sizing/performance
- Economics (CAPEX/OPEX/LCOW) should be separate analysis step
- WaterTAP costing integration should handle this

**Files to Modify**:
- `tools/knowledge_based_config.py:342-376` - Move `_estimate_sac_economics()`
- Create `tools/economics.py` - Dedicated economics module
- Update callers to separate config from costing

**Estimated Effort**: 2-3 hours

---

### Task 12: Cross-Validate USEPA vs PHREEQC for SAC

**Depends on**: Task 6 (PHREEQC calibration), Task 7 (USEPA integration)

**Objective**: Compare three approaches:
- Tier 1: Equilibrium model (our implementation) - <1 sec
- Tier 2: USEPA HSDMIX (full transport) - 10-60 sec
- Tier 3: PHREEQC (benchmark chemistry) - 5+ min

**Test Matrix**: Same 10-15 cases from Task 6

**Deliverable**: Accuracy table showing:
- Equilibrium vs PHREEQC: Expected ±20-30%
- USEPA vs PHREEQC: Expected ±10-20%
- Speed comparison

**Estimated Effort**: 1 week (after Tasks 6 & 7)

---

## Files Modified in Last Session

### New Files
1. `tools/equilibrium_leakage.py` - Core equilibrium solver (290 lines)
2. `tests/test_equilibrium_leakage.py` - Test suite (195 lines, 9 tests)

### Modified Files
1. `tools/capacity_derating.py`
   - Lines 6-7: Added equilibrium_leakage import
   - Lines 17-18: Added equilibrium calculator to __init__
   - Lines 96-127: Replaced `calculate_leakage()` - now takes feed composition
   - Lines 132-173: Replaced `calculate_dose_for_leakage()` - now calibrates f_active

2. `tools/breakthrough_calculator.py`
   - Lines 65-79: Updated to pass feed composition to leakage model
   - Lines 116-117: Call new leakage calculation with composition

### Files Ready for Next Steps
- `tools/phreeqc_calibration.py` - Create this for Task 6
- `tools/usepa_simulator.py` - Create this for Task 7
- `tools/wac_na_equilibrium.py` - Create this for Task 8

---

## Key Learnings from This Session

1. **Mass action equilibrium is critical** - Can't approximate with dose-based correlations
2. **USEPA code is production-ready** - Worth extracting and adapting
3. **Parameterization matters** - f_active needs careful calibration
4. **Physics validation is essential** - Gaines-Thomas relationship test caught solver bug
5. **Codex review is valuable** - Found critical inverse solver bug we missed

---

## Questions for Next Session

1. **What is realistic f_active range for each water type?**
   - Answer via Task 6 (PHREEQC calibration)

2. **Should f_active depend on flow rate or bed depth?**
   - Analyze correlation in Task 6 results

3. **Is equilibrium model appropriate for all SAC applications?**
   - Cross-validate with USEPA (Task 12)

4. **Can we achieve <5 mg/L hardness for brackish water without unrealistically low f_active?**
   - May need different parameterization or accept that brackish is challenging

5. **Should we add activity coefficient corrections for high TDS?**
   - Gaines-Thomas uses equivalent fractions, not activities
   - PHREEQC handles activities - compare predictions

---

## Session Artifacts

**Test Results**: All 9 tests passing (0.20 sec)
```
test_basic_sac_leakage_calculation PASSED
test_high_sodium_fraction_affects_equilibrium PASSED
test_f_active_increases_leakage PASSED
test_resin_composition_sums_to_one PASSED
test_effluent_fractions_sum_to_one PASSED
test_gaines_thomas_relationship_satisfied PASSED (NEW - Codex added)
test_calibrate_f_active PASSED
test_calibrate_f_active_expands_bounds_for_low_target PASSED (NEW - Codex added)
test_zero_hardness_feed PASSED
```

**Python Environment**: `/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe`

**Git Status**:
- Modified: `tools/capacity_derating.py`, `tools/breakthrough_calculator.py`, `tools/equilibrium_leakage.py`, `tests/test_equilibrium_leakage.py`
- New: `tools/equilibrium_leakage.py`, `tests/test_equilibrium_leakage.py`
- Ready to commit

---

## References

### Literature
- Helfferich, F. (1962). *Ion Exchange*. McGraw-Hill. Chapter 5: Equilibria.
- Crittenden et al. (2012). *MWH's Water Treatment*. Chapter on Ion Exchange.
- USEPA (2024). *Water Treatment Models*. github.com/USEPA/Water_Treatment_Models

### Repositories
- USEPA/Water_Treatment_Models: `IonExchangeModel/ixpy/hsdmix.py`
- watertap-org/watertap: IonExchange0D (single-ion only, can't do multicomponent)

### Our Implementation
- Based on USEPA `calc_Ceq_dv()` function
- Enhanced with f_active parameterization
- Validated to ±0.001% on Gaines-Thomas relationship