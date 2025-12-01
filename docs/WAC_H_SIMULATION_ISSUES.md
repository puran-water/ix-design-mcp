# WAC H-form Simulation Issues

## Current Status

**Date**: 2025-11-29
**PHREEQC Convergence**: SOLVED
**Chemistry Model**: VALIDATED (standalone tests)
**Two-Layer Overlay**: ✅ IMPLEMENTED (Phase 1 complete)
**Kinetic Mode**: R&D (requires pilot data calibration)

---

## Phase 1 Solution: Henderson-Hasselbalch Empirical Overlay (IMPLEMENTED)

### The Problem

WAC H-form carboxylic acid sites have pKa ~4.8. At typical feed pH 7.8:
- Henderson-Hasselbalch predicts: α = 1/(1 + 10^(pH-pKa)) = 1/(1 + 10^3) ≈ 0.001
- This means 99.9% of sites are deprotonated at equilibrium
- Equilibrium-based models (PHREEQC EXCHANGE/SURFACE) predict **no capacity**

Real WAC H-form columns work because:
1. Sites start 100% protonated from acid regeneration
2. Protonation is **kinetically trapped** - sites only convert through physical cation displacement
3. This is NOT an equilibrium process

### The Solution: Two-Layer Architecture

**Layer 1: PHREEQC EXCHANGE** handles:
- Transport and dispersion
- Competitive ion effects
- Breakthrough curve shape and timing

**Layer 2: Empirical Overlay** corrects for:
- Henderson-Hasselbalch capacity discrepancy
- Kinetic trap factor (operational capacity vs equilibrium)
- Realistic leakage prediction

### Implementation Details

**Files Modified:**
- `tools/empirical_leakage_overlay.py` - Henderson-Hasselbalch capacity model
- `tools/wac_simulation.py` - Integration with WAC workflow

**New Functions:**
```python
# Calculate effective capacity with kinetic trapping
capacity, diagnostics = overlay.calculate_wac_h_effective_capacity(
    feed_ph=7.8,
    feed_alkalinity_mg_l_caco3=200.0
)

# Calculate leakage with H-H model
result = overlay.calculate_wac_h_leakage(
    feed_hardness_mg_l_caco3=300.0,
    feed_alkalinity_mg_l_caco3=200.0,
    feed_ph=7.8,
    feed_tds_mg_l=1500.0
)
```

**Key Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `wac_h_pka` | 4.8 | pKa of carboxylic acid sites |
| `wac_h_theoretical_capacity_eq_l` | 4.7 | Theoretical capacity (eq/L resin) |
| `wac_h_kinetic_trap_factor` | 0.85 | Kinetically trapped fraction (0.0-1.0) |
| `wac_h_ph_floor` | 4.2 | Minimum pH during acid phase |

**Kinetic Trap Factor Guidance:**
- 0.85-0.95: Fresh resin, well-regenerated (counter-current HCl/H2SO4)
- 0.70-0.85: Typical operation, good regeneration
- 0.50-0.70: Older resin, partial regeneration, some fouling
- <0.50: Degraded resin, poor regeneration, significant fouling

### Test Results

```
Feed: 300 mg/L hardness, pH 7.8
H-H equilibrium capacity: 0.0047 eq/L (near zero - what PHREEQC predicts)
Kinetic capacity (ktf=0.85): 4.0 eq/L (operational reality)
Expected leakage: 24.1 mg/L as CaCO3

Sensitivity analysis:
ktf=0.0  → leakage=151.6 mg/L (no capacity, pure equilibrium)
ktf=0.85 → leakage=24.1 mg/L (typical operation)
ktf=1.0  → leakage=1.6 mg/L (perfect regeneration)
```

### Unit Tests

20 tests in `tests/test_wac_h_henderson_hasselbalch.py`:
- Capacity calculation (6 tests)
- Leakage prediction (6 tests)
- Convenience function (3 tests)
- Edge cases (4 tests)
- Calibration loading (1 test)

### Usage

```python
from tools.empirical_leakage_overlay import calculate_wac_h_leakage

leakage, diagnostics = calculate_wac_h_leakage(
    feed_hardness_mg_l_caco3=300,
    feed_alkalinity_mg_l_caco3=200,
    feed_ph=7.8,
    feed_tds_mg_l=1500,
    kinetic_trap_factor=0.85  # Tune based on regen quality
)

print(f"Expected leakage: {leakage:.1f} mg/L as CaCO3")
print(f"Equilibrium capacity: {diagnostics['equilibrium_capacity_eq_l']:.4f} eq/L")
print(f"Kinetic capacity: {diagnostics['kinetic_capacity_eq_l']:.2f} eq/L")
```

### Why This Approach is Correct

This two-layer architecture mirrors commercial IX software:
- **DuPont WAVE**: Uses selectivity + empirical capacity corrections
- **Purolite PRSM**: Uses empirical curves calibrated from pilot data
- **Lanxess LewaPlus**: Combines thermodynamics with operational factors

Pure thermodynamic models cannot capture WAC H-form behavior because the process is inherently non-equilibrium. The kinetic trap factor bridges this gap.

### Known Limitations (Codex Review 2025-12-01)

**PHREEQC Layer Artifacts:**
- Uses reduced pKa (2.5) instead of true pKa (4.8) for Newton-Raphson convergence stability
- Initialization now forces HX with strong-acid placeholder (pH ~0.5, explicit HX load); previous pH 3.0 conditioning underloaded the resin (~24% protonated)
- Even with full HX load, equilibrium log_k=2.5 collapses capacity at feed pH 7.8; hardness removal in PHREEQC remains a kinetic-trap artifact
- Breakthrough at ~1 BV from the PHREEQC layer is still non-physical and should not be used for sizing
- **Do NOT use raw PHREEQC hardness removal or breakthrough values for sizing**

**Authoritative Values:**

| Metric | Source | Use For |
|--------|--------|---------|
| Breakthrough BV | Overlay (ktf-adjusted) | Sizing, service life |
| Leakage mg/L | Overlay (H-H model) | Water quality prediction |
| Capacity eq/L | Overlay (4.0 with ktf=0.85) | Regenerant dosing |
| pH trends | PHREEQC (qualitative) | Front shape, speciation trends |
| Absolute pH | Neither (biased by reduced pKa) | Requires pilot validation |

**Future Improvements:**
1. **Option A**: Restore true pKa (4.8) with NR damping/convergence fixes
2. **Option B (implemented)**: Force PHREEQC initialization to 100% HX (strong-acid placeholder) to remove under-acid artifact
3. Label PHREEQC hardness removal as "artifact" in outputs to prevent misinterpretation

---

## Kinetic HX Displacement Test Results (2025-11-28)

### New Approach Tested: HX as Kinetic Pool (Not Exchange Species)

Based on the second Codex brainstorming session (session ID: `019acbca-501e-7c73-984b-597591e22b12`), we tested a fundamentally different approach: define HX as a **kinetic pool** rather than an exchange species.

**Key Innovation**: HX cannot deprotonate by equilibrium because it's NOT an exchange species. Depletion only happens through kinetic displacement.

**PHREEQC Pattern:**
```phreeqc
EXCHANGE_SPECIES
    X- = X-               log_k 0
    2X- + Ca+2 = CaX2     log_k 1.3
    2X- + Mg+2 = MgX2     log_k 1.1
    X- + Na+ = NaX        log_k 0.0
    # NO HX protonation reaction - prevents equilibrium deprotonation

EXCHANGE 1
    X- 1e-9  # Seed exchange phase only

RATES
HX_Ca_Displacement
    -start
10 k = PARM(1)           # Rate constant (1/s)
20 kh = PARM(2)          # Half-saturation (mol/kgw)
30 hx_pool = M           # Remaining HX capacity (kinetic reactant)
40 ca_aq = TOT("Ca")
50 driver = ca_aq / (ca_aq + kh)
60 rate = k * hx_pool * driver
70 IF (rate * TIME > hx_pool) THEN rate = hx_pool / TIME
80 SAVE rate * TIME
    -end

KINETICS 1-10
    HX_Ca_Displacement
        -m0 0.20           # Moles HX capacity per cell
        -parms 3e-4 5e-6   # k, kh
        -formula CaX2 1 Ca+2 -1 H+ 2   # Creates CaX2, releases 2H+
```

### Test Results (v3 - 200 mg/L alkalinity)

| BV | pH | Ca (mg/L) | Hardness | Alk (mg/L) | HX_Ca | Phase |
|----|-----|-----------|----------|------------|-------|-------|
| 0.5 | 7.83 | **0.0005** | 0.002 | 159 | 0.200 | **SERVICE** |
| 0.7 | 11.36 | 0.48 | 1.9 | 155 | 0.197 | pH spike |
| 1.0 | 3.00 | 9.3 | 39 | -55 | 0.187 | Acid breakthrough |
| 5.0 | 2.83 | 20.5 | 87 | -83 | 0.092 | HX depleting |
| 9.0 | **5.26** | 34.5 | 143 | **+3.4** | 0.045 | Alk recovering |
| 15.0 | **8.08** | 66.2 | 262 | 123 | 0.015 | Near feed |

### Key Finding: Kinetic HX Displacement WORKS

**Positive Results:**
- ✅ **Service window exists**: BV 0.5 shows near-complete hardness removal (0.002 mg/L CaCO3)
- ✅ **HX depletes over time**: 0.200 → 0.015 mol (92% utilization)
- ✅ **pH behavior shows acid phase**: Drops from 7.8 → 3.0 → recovers to 8.0
- ✅ **Alkalinity consumed then recovered**: Goes negative during acid phase
- ✅ **Breakthrough curve shape**: S-curve from 0 → feed hardness

**Issues Requiring Calibration:**
- ❌ **pH spike to 11+** at BV 0.7 is unrealistic (PHREEQC numerical artifact)
- ❌ **Service window too short** (~0.5 BV vs expected 50-100 BV)
- ❌ **Acid period too severe** (pH 2.5-3 vs expected 4-5)

### Conclusion: Kinetic Approach is Viable

The kinetic HX displacement approach produces **qualitatively correct behavior**:
1. Initial service with near-zero hardness
2. Acid phase with alkalinity consumption
3. Breakthrough with HX depletion
4. Recovery to feed conditions

**Calibration needed:**
- Scale up HX capacity (`-m0`) by ~100x for industrial scale
- Tune rate constant (`k`) and half-saturation (`kh`) against pilot data
- May still need empirical overlay for pH profile correction

### Recommendation

**Two viable paths forward:**

1. **Production (Short-term)**: Continue with two-layer architecture
   - PHREEQC EXCHANGE for transport timing
   - Empirical overlay for H-form pH behavior
   - Well-understood, matches commercial tools (WAVE, PRSM)

2. **R&D (Long-term)**: Develop kinetic HX displacement model
   - More mechanistically accurate
   - Requires calibration against pilot data
   - Could eliminate need for empirical overlay

---

## Codex Brainstorming Session Results (2025-11-28)

### Approach Tested: KINETICS + SURFACE with Linear Driving Force (LDF)

Based on Codex CLI consultation, we tested a KINETICS-throttled SURFACE model to create realistic breakthrough behavior. The hypothesis was that kinetics could slow down the approach to equilibrium and create a service window.

**PHREEQC Template Used:**
```phreeqc
SURFACE_MASTER_SPECIES
    Wac    WacOH

SURFACE_SPECIES
    WacOH = WacOH                    log_k 0.0
    WacOH = WacO- + H+               log_k -4.8   # True pKa
    WacOH + Ca+2 = WacOCa+ + H+      log_k 1.0
    WacOH + Mg+2 = WacOMg+ + H+      log_k 0.8
    WacOH + Na+ = WacONa + H+        log_k 0.5

RATES
WacCa_LDF
    -start
    # Linear Driving Force: rate = k * (q_eq - q_now)
    # Computes equilibrium surface composition from mass action
    # Throttles approach to equilibrium
    -end

KINETICS 1
    WacCa_LDF
        -formula WacOCa+ 1 WacOH -1 Ca+2 -1 H+ 1
        -parms 1e-6   # Rate constant (1/s)
```

### Test Results

| BV Range | pH | Ca (mg/L) | Alk (mg/L) | Behavior |
|----------|-----|-----------|------------|----------|
| 0.1-1.0 | 2.3-2.5 | 34-53 | -230 to -167 | Initial acid spike |
| 1.0-2.0 | 2.4→7.4 | 53→80 | -230→94 | Feed neutralizes acid |
| 2.0-20 | 7.8 | 80 | 99 | **Feed passthrough - NO removal** |

### Key Finding

**KINETICS does NOT solve the fundamental thermodynamics problem.**

Once equilibrium is reached (~BV 2), effluent matches feed quality with **zero hardness removal**. The kinetics only slow the approach to equilibrium; they don't change the equilibrium position.

**Root Cause:** At feed pH 7.8 with pKa 4.8:
- Henderson-Hasselbalch: α = 1/(1 + 10^(4.8-7.8)) = 99.9% deprotonated
- Equilibrium strongly favors deprotonated sites (WacO⁻)
- WacO⁻ + Ca²⁺ → WacOCa⁺ is cation exchange without H⁺ release
- No sustained hardness removal possible at equilibrium

### Consensus: WAC H-form is Inherently Non-Equilibrium

Real WAC H-form columns work because:
1. **Sites start 100% protonated** from acid regeneration
2. **Protonation is kinetically trapped** - sites remain protonated until physically displaced
3. **This is NOT an equilibrium process** - thermodynamics favor deprotonation at pH 7-8
4. **Service window exists** because kinetics of cation binding are faster than deprotonation

**Implication:** Pure equilibrium-based PHREEQC models (EXCHANGE or SURFACE) cannot accurately capture WAC H-form behavior. The empirical overlay approach is scientifically correct because it accounts for the non-equilibrium nature of the process.

### Recommended Approach

1. **Use EXCHANGE-based PHREEQC model** for transport timing and breakthrough shape
2. **Apply Henderson-Hasselbalch correction** via empirical_leakage_overlay.py
3. **Enforce temporary hardness removal** based on min(feed hardness, feed alkalinity)
4. **This two-layer approach is appropriate** because:
   - PHREEQC handles: dispersion, transport, competitive ion effects
   - Empirical overlay handles: pH-dependent capacity, non-equilibrium behavior

---

## Fix Implemented: Reduced pKa HX Approach (2025-11-26)

### Solution Summary

The H-form template now uses a **reduced effective pKa (2.5 instead of 4.8)** for numerical stability:

1. **EXCHANGE_MASTER_SPECIES**: `X / X-` (same as Na-form)
2. **HX Protonation Reaction**: `H+ + X- = HX` with `log_k = 2.5`
3. **Exchanger Initialization**: `HX` at pH 3.0 acidic conditioning
4. **Architecture**: Two-layer - PHREEQC for thermodynamics + empirical overlay for realistic behavior

### Validated via Standalone PHREEQC Tests

```
Test 1: HX Persistence at pH 3.0
- HX sites: 99.35% retained (vs 100% NaY with Y/YH approach)
- NaX sites: 0.65% (minimal Na loading)

Test 2: Cation Exchange with Hard Water (pH 7.8)
- Feed pH: 7.8 → Effluent pH: 2.18 (H+ released!)
- Ca removal: 62%
- Mg removal: 51%
- Alkalinity consumed (negative total alkalinity)
```

### What Works
- HX protonation with reduced pKa converges
- H+ release during Ca²⁺/Mg²⁺ exchange
- pH drop and alkalinity consumption
- Standalone batch reactions behave as expected

### Remaining Issue
Full TRANSPORT simulation via MCP times out or fails with "PHREEQC failed: None". This may be due to:
- Convergence issues at industrial capacity (~13 eq/cell)
- Path handling in MCP environment
- Long-running TRANSPORT (expected ~45 min) timing out

### Files Modified
- `watertap_ix_transport/transport_core/wac_templates.py` - Core H-form template
- `tools/wac_simulation.py` - Fixed WACPerformanceMetrics validation

---

## Previous State (2025-11-25)

The WAC H-form PHREEQC TRANSPORT simulation converged successfully (45-minute run, 15,525 shifts, no errors), but the chemistry model did not properly represent H-form weak acid cation exchange behavior.

---

## Problem Summary

### What Works
- PHREEQC TRANSPORT convergence (no Newton-Raphson failures)
- Two-stage initialization pattern (conditioning → production)
- Dual-domain EXCHANGE model structure
- Output parsing and results generation

### What Doesn't Work
- **No hardness removal occurring** - effluent equals feed throughout entire run
- Exchanger acts like exhausted Na-form, not fresh H-form
- No pH-dependent capacity (Henderson-Hasselbalch)
- No alkalinity consumption / CO2 generation

---

## Test Results (Run ID: 20251125_172608_cb2c6aee)

### Breakthrough Data (15,456 BV simulated)
| Parameter | Feed | Effluent | Expected H-form Behavior |
|-----------|------|----------|-------------------------|
| Ca | 80 mg/L | 61 mg/L (constant) | Should decrease then break through |
| Mg | 24 mg/L | 11.2 mg/L (constant) | Should decrease then break through |
| Hardness | ~260 mg/L as CaCO3 | ~198 mg/L as CaCO3 (constant) | Should be near-zero initially |
| pH | 7.8 | 7.87 (constant) | Should drop as alkalinity exhausted |
| Alkalinity | 122 mg/L | 122 mg/L (constant) | Should be consumed by H+ release |

### Key Metrics
- **Service BV to Target**: 1.0 (immediate breakthrough - hardness never < 5 mg/L)
- **Capacity Utilization**: 0.04% (effectively zero)
- **Hardness Removal**: 0% during service (only initial equilibration effect)

---

## Root Cause Analysis

### Current Implementation Flaw

The H-form template uses **Na+ conditioning** identical to Na-form:

```
Stage 1: EXCHANGE 1-{cells}
    NaX       {capacity}
    -equilibrate with solution 0  # Solution 0 is dilute NaCl

Stage 2: USE exchange 1-{cells}
    # Production feed with Ca/Mg/Na
```

This creates an exchanger pre-loaded with Na+, which:
1. Has similar selectivity to Ca²⁺/Mg²⁺ in the current model
2. Does not release H+ when Ca²⁺/Mg²⁺ exchanges
3. Cannot consume alkalinity (no H+ generated)
4. Behaves like exhausted SAC, not fresh WAC H-form

### Missing H-form Chemistry

True WAC H-form operation requires:
1. **Protonated sites (XH or HX)** that release H+ when cations exchange
2. **Henderson-Hasselbalch pH dependence** - capacity decreases as pH drops
3. **Alkalinity consumption**: H+ + HCO3- → H2O + CO2
4. **pH-triggered breakthrough** - when alkalinity exhausted, pH crashes → hardness leakage

---

## Previous Approaches Attempted

### 1. HX Protonation Reaction (FAILED - convergence)
```phreeqc
EXCHANGE_SPECIES
    X- + H+ = HX
        log_k  4.8  # pKa for acrylic WAC
```
**Problem**: log_k = 4.8 creates 63,000x selectivity, causing Newton-Raphson failures.

### 2. XH Master Species Transformation (NOT IMPLEMENTED)
Transform master species from X- to XH, absorbing pKa into displacement reactions:
```phreeqc
EXCHANGE_MASTER_SPECIES
    XH  XH

EXCHANGE_SPECIES
    XH = XH
        log_k  0.0
    XH + Na+ = NaX + H+
        log_k  -4.8  # = 0 - pKa
    2XH + Ca+2 = CaX2 + 2H+
        log_k  -8.3  # = 1.3 - 2*pKa
```
**Status**: Planned but not implemented. See previous plan file.

### 3. Na+ Conditioning Workaround (CURRENT - converges but wrong chemistry)
Condition with Na+ instead of H+, use empirical overlay for pH effects.
**Problem**: Exchanger never acts as H-form; no ion exchange during production.

---

## Recommended Solution: Staged Activation

From Codex consultation, use DUMP/INCLUDE$ for multi-stage capacity activation:

1. **Stage 1**: Initialize with ~30% capacity, equilibrate
2. **DUMP** exchanger state to file
3. **Stage 2**: INCLUDE$ dump, add remaining 70% capacity
4. **Continue TRANSPORT** with full capacity

This allows:
- Gradual capacity introduction (avoids convergence issues)
- True H-form sites (XH) at vendor-specified capacity (4.7 eq/L)
- Accurate breakthrough timing

---

## Files Involved

### Primary Template Generation
- `watertap_ix_transport/transport_core/wac_templates.py`
  - `create_wac_h_phreeqc_input()` - lines 145-186
  - `_create_wac_dual_domain_input()` - lines 189-726
  - H-form specific: lines 404-527

### PHREEQC Engine
- `watertap_ix_transport/transport_core/direct_phreeqc_engine.py`
  - Subprocess execution, temp file management
  - Would need modification for multi-run DUMP/INCLUDE$

### Simulation Entry Points
- `tools/wac_simulation.py` - WAC simulator class
- `tools/simulate_ix_hybrid.py` - Hybrid engine orchestration

### Configuration
- `tools/core_config.py`
  - `WAC_H_TOTAL_CAPACITY = 4.7` eq/L (true capacity)
  - `WAC_NA_WORKING_CAPACITY = 1.8` eq/L (convergence workaround)

### Selectivity Data
- `databases/resin_selectivity.json` - Ca/Mg/Na/K log_k values

---

## Upstream Reference

**PHREEQC Repository**: https://github.com/usgs-coupled/phreeqc3

Key PHREEQC documentation:
- EXCHANGE keyword: https://wwwbrr.cr.usgs.gov/projects/GWC_coupled/phreeqc/phreeqc3-html/phreeqc3-43.htm
- TRANSPORT keyword: https://wwwbrr.cr.usgs.gov/projects/GWC_coupled/phreeqc/phreeqc3-html/phreeqc3-68.htm
- DUMP keyword: https://wwwbrr.cr.usgs.gov/projects/GWC_coupled/phreeqc/phreeqc3-html/phreeqc3-36.htm
- INCLUDE$ keyword: https://wwwbrr.cr.usgs.gov/projects/GWC_coupled/phreeqc/phreeqc3-html/phreeqc3-41.htm

---

## Success Criteria for Fix

1. **Hardness removal** > 90% initially, decreasing to breakthrough
2. **pH profile**: Starts at feed pH (~7.8), drops as alkalinity consumed
3. **Alkalinity consumption**: Should decrease over service cycle
4. **Breakthrough BV**: Should match theoretical based on 4.7 eq/L capacity
5. **Capacity utilization**: Should approach 80-90% at breakthrough

---

## Related Documents

- `CLAUDE.md` - Codex CLI usage instructions
- `CURRENT_TASK.md` - Task tracking
- `/home/hvksh/.claude/plans/polymorphic-herding-acorn.md` - Previous XH master species plan

---

## Quick Start for New Session

```bash
# View current H-form template generation
grep -n "resin_form == 'H'" watertap_ix_transport/transport_core/wac_templates.py

# View working Na-form for comparison
grep -n "resin_form == 'Na'" watertap_ix_transport/transport_core/wac_templates.py

# Run test simulation
python utils/simulate_ix_cli.py --resin WAC_H --flow 100 --ca 80 --mg 24 --na 839 --hco3 122 --ph 7.8
```
