# WAC SURFACE Complexation Model

## Overview
This document describes the SURFACE complexation model used for Weak Acid Cation (WAC) exchange resins in the IX Design MCP server. The SURFACE model correctly represents the pH-dependent capacity of WAC resins through acid-base equilibrium chemistry.

## Key Concepts

### Why SURFACE Instead of EXCHANGE?
WAC resins contain carboxylic acid functional groups (RCOOH) that must deprotonate to RCOO- before they can bind metal cations. This pH-dependent behavior is fundamentally different from strong acid cation (SAC) resins:

- **SAC resins**: Always deprotonated (RSO3-), constant capacity across pH range
- **WAC resins**: pH-dependent deprotonation (RCOOH ⇌ RCOO- + H+), variable capacity

### The Problem with EXCHANGE Models
Using PHREEQC's EXCHANGE block for WAC incorrectly models H+ as a highly selective exchangeable cation:
```
# WRONG: Makes H+ appear 63,000× more selective than Na+
H+ + X- = HX
    log_k 4.8  # This is incorrect!
```

This approach fails because:
1. H+ appears to outcompete all other cations
2. Capacity doesn't follow Henderson-Hasselbalch equation
3. Sites remain "occupied" by H+ rather than being unavailable

### The SURFACE Solution
The SURFACE complexation model correctly represents acid-base equilibrium:
```
# CORRECT: Acid-base equilibrium controls site availability
Wac_sOH = Wac_sO- + H+
    log_k -4.5  # pKa of carboxylic groups
```

## Henderson-Hasselbalch Equation
WAC capacity follows the Henderson-Hasselbalch equation:

```
α = 1 / (1 + 10^(pKa - pH))
```

Where:
- α = fraction of sites available for exchange (deprotonated)
- pKa = 4.5 for typical carboxylic acid groups
- pH = solution pH

### Capacity vs pH
| pH | % Active Sites | Practical Implications |
|----|----------------|------------------------|
| 3.5 | ~9% | Very low capacity, not practical |
| 4.0 | ~24% | Limited capacity |
| 4.5 | 50% | Half capacity (pH = pKa) |
| 5.0 | ~76% | Good capacity |
| 5.5 | ~91% | Near full capacity |
| 6.5 | ~99% | Full capacity |

## PHREEQC Implementation

### Surface Master Species
```
SURFACE_MASTER_SPECIES
    Wac_s Wac_sOH
```

### Surface Species Reactions
```
SURFACE_SPECIES
    # Reference species (protonated form)
    Wac_sOH = Wac_sOH
        log_k 0

    # Deprotonation (controls capacity)
    Wac_sOH = Wac_sO- + H+
        log_k -4.5  # pKa

    # Divalent cation binding (2:1 stoichiometry)
    2Wac_sO- + Ca+2 = (Wac_sO)2Ca
        log_k 1.0

    2Wac_sO- + Mg+2 = (Wac_sO)2Mg
        log_k 0.8

    # Monovalent cation binding
    Wac_sO- + Na+ = Wac_sONa
        log_k -0.5
```

### Important Notes
1. **No double protonation**: Carboxylic acids cannot accept a second proton (no Wac_sOH2+)
2. **Only deprotonated sites bind metals**: Metal binding requires RCOO- sites
3. **Use -no_edl**: Electrical double layer not needed for resin beads

## Validation Tests
The model has been validated to ensure:
1. Capacity follows Henderson-Hasselbalch equation at all pH values
2. Model works correctly with alkalinity present
3. Metals only bind to deprotonated sites

Test results show excellent agreement with theory:
- At pH 3.5: 9.7% active (theory: 9.1%)
- At pH 4.5: 51.9% active (theory: 50.0%)
- At pH 5.5: 91.5% active (theory: 90.9%)

## Migration from EXCHANGE Model
The IX Design MCP server has completely migrated from the incorrect EXCHANGE model to the SURFACE model. Key changes:

1. **Removed**: `tools/wac_enhanced_species.py` (contained wrong EXCHANGE model)
2. **Added**: `tools/wac_surface_builder.py` (implements SURFACE model)
3. **Updated**: WAC templates now use SURFACE exclusively
4. **Fixed**: Water mass calculations and invalid reactions

## Usage in Simulations
The SURFACE model is automatically used for all WAC simulations:
- WAC Na-form: Uses pKa = 4.5, capacity = 3.5 eq/L
- WAC H-form: Uses pKa = 4.5, capacity = 4.5 eq/L

The model correctly predicts:
- pH-dependent capacity
- Alkalinity removal (H-form)
- CO2 generation (H-form)
- Competitive ion exchange between deprotonated sites

## Bug Fixes - September 2025

### Critical Cl Charge Syntax Bug
**Issue**: WAC simulations were failing with "Concentration data error for cl in solution input"
**Root Cause**: Invalid PHREEQC syntax `Cl charge` without numeric value
**Fix Applied**:
1. Changed `Cl charge` to `Cl 0 charge` for Na-form WAC
2. Added `units mg/L` declaration to SOLUTION blocks
3. Updated pH initialization: Na-form uses pH 7.0, H-form uses feed pH

**Results After Fix**:
- WAC Na-form: ~92.8 BV breakthrough (previously 0 BV)
- Proper pH-dependent capacity following Henderson-Hasselbalch equation
- No PHREEQC syntax errors

## References
1. PHREEQC Manual - SURFACE complexation modeling
2. Henderson, L.J. (1908). "The theory of neutrality regulation"
3. Hasselbalch, K.A. (1917). "Die Berechnung der Wasserstoffzahl des Blutes"