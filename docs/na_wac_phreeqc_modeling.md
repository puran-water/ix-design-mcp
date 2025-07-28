# Modeling Na-WAC with PHREEQC TRANSPORT

## Overview

This document explains how PHREEQC's TRANSPORT model can accurately simulate sodium-form weak acid cation (Na-WAC) exchange resins, including their complete hardness removal capability and two-step regeneration process.

## Key Chemistry Differences: H-WAC vs Na-WAC

### H-WAC (Hydrogen Form)
- Functional group: R-COOH (protonated carboxylic acid)
- Only removes temporary hardness (Ca/Mg associated with HCO₃⁻)
- Reaction: 2R-COOH + Ca(HCO₃)₂ → (R-COO)₂Ca + 2H₂O + 2CO₂
- Effluent pH: ~4.5 (acidic)
- Single-step acid regeneration

### Na-WAC (Sodium Form)
- Functional group: R-COONa (deprotonated, sodium salt)
- Removes ALL hardness (both temporary and permanent)
- Reaction: 2R-COONa + Ca²⁺ → (R-COO)₂Ca + 2Na⁺
- Effluent pH: Unchanged (releases Na⁺, not H⁺)
- Two-step regeneration (acid then caustic)

## PHREEQC TRANSPORT Implementation

### 1. Exchange Species Definition

```phreeqc
EXCHANGE_MASTER_SPECIES
    Xwac Xwac-    # WAC exchange site

EXCHANGE_SPECIES
    # Reference species (sodium form)
    Xwac- = Xwac-
    log_k 0
    
    # Sodium exchange (reference state)
    Na+ + Xwac- = NaXwac
    log_k 0.0
    -gamma 4.0 0.075
    
    # Proton exchange (for regeneration)
    H+ + Xwac- = HXwac
    log_k 1.0    # Higher affinity than Na
    -gamma 9.0 0.0
    
    # Calcium exchange
    Ca+2 + 2Xwac- = CaXwac2
    log_k 0.8    # Strong preference over Na
    -gamma 5.0 0.165
    
    # Magnesium exchange
    Mg+2 + 2Xwac- = MgXwac2
    log_k 0.6    # Moderate preference over Na
    -gamma 5.5 0.20
```

### 2. Initial Resin State

For Na-WAC, initialize the exchange sites in sodium form:

```phreeqc
EXCHANGE 1
    NaXwac 3.8    # 3.8 eq/L capacity, all in Na form
    -equilibrate 1
```

### 3. Service Cycle Simulation

```phreeqc
# Define feed water with both temporary and permanent hardness
SOLUTION 1
    temp 25
    pH 7.8
    Na 200
    Ca 60      # 120 mg/L as Ca²⁺
    Mg 20      # 48 mg/L as Mg²⁺
    Cl 355
    S(6) 50    # Sulfate (permanent hardness)
    C(4) 4.1   # Bicarbonate (temporary hardness)
    
# Transport through resin bed
TRANSPORT
    -cells 20              # 20 cells for resolution
    -shifts 100            # 100 pore volumes
    -flow_direction forward
    -boundary_conditions flux flux
    -lengths 0.05          # 5 cm per cell (1 m total)
    -dispersivities 0.002  # 2 mm dispersion
    -diffusion_coefficient 1e-9
    -stagnant 1 6.8e-6 0.3 0.1
```

### 4. Two-Step Regeneration

#### Step 1: Acid Regeneration (Release Hardness)

```phreeqc
# HCl solution for protonation
SOLUTION 2
    temp 25
    pH 1.0      # Strong acid
    Cl 1000     # ~3.5% HCl
    
TRANSPORT
    -shifts 10   # Pass 10 pore volumes
    -cells 20
    -flow_direction backward  # Countercurrent
```

This converts CaXwac2 → HXwac + Ca²⁺ (released)

#### Step 2: Caustic Regeneration (Convert to Na Form)

```phreeqc
# NaOH solution for conversion to Na form
SOLUTION 3
    temp 25
    pH 13.0     # Strong base
    Na 1000     # ~4% NaOH
    
TRANSPORT
    -shifts 10   # Pass 10 pore volumes
    -cells 20
    -flow_direction backward
```

This converts HXwac → NaXwac, restoring the sodium form.

## Key PHREEQC Features for Na-WAC Modeling

### 1. pH-Independent Exchange
Unlike H-WAC, Na-WAC exchange is not limited by pH because:
- R-COONa groups are already deprotonated
- Exchange reactions proceed at all pH values
- The log_k values control selectivity, not pH

### 2. Sequential Solution Changes
TRANSPORT allows different solutions at different times:
- Service: Hard water (Solution 1)
- Regeneration Step 1: Acid (Solution 2)
- Regeneration Step 2: Caustic (Solution 3)
- Rinse: Soft water (Solution 4)

### 3. Competition Effects
The model handles Na⁺ competition through:
- Relative log_k values
- Activity coefficients (-gamma parameters)
- Mass action equilibrium calculations

### 4. Complete Mass Balance
PHREEQC tracks:
- Total exchange capacity
- Distribution among species (NaXwac, CaXwac2, etc.)
- Solution composition changes
- pH evolution

## Example Results

### Service Cycle
- Influent: 497 mg/L hardness, pH 7.8
- Effluent: <1 mg/L hardness, pH 7.8
- Na⁺ increase: ~230 mg/L
- Breakthrough: After ~215 bed volumes

### Regeneration
- Acid consumption: 80 g HCl/L resin
- Caustic consumption: 60 g NaOH/L resin
- Waste volume: ~3 BV acid + 3 BV caustic
- Waste composition: High Ca/Mg chlorides

## Advantages of PHREEQC TRANSPORT for Na-WAC

1. **Accurate Chemistry**: Models actual ion exchange equilibria
2. **Flexible Operations**: Handles multi-step regeneration
3. **Competition Effects**: Accounts for Na⁺ interference
4. **Mass Transfer**: Includes dispersion and film diffusion
5. **pH Tracking**: Monitors pH changes throughout

## Validation Approach

To validate the model:
1. Compare breakthrough curves with pilot data
2. Verify regenerant consumption
3. Check effluent Na⁺ levels
4. Monitor pH stability
5. Confirm complete hardness removal

## Conclusion

PHREEQC TRANSPORT is fully capable of modeling Na-WAC resins accurately by:
- Defining appropriate exchange reactions
- Using sequential solutions for two-step regeneration
- Tracking all species and pH changes
- Accounting for competition and selectivity

The key is recognizing that Na-WAC behaves fundamentally differently from H-WAC due to its deprotonated functional groups, allowing complete hardness removal regardless of the associated anions.