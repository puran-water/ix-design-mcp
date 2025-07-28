# PHREEQC Transport Exchange Capacity Findings

## Critical Discovery

When using PHREEQC's TRANSPORT module with ion exchange, specifying water mass in SOLUTION blocks causes unexpected behavior with exchange capacity.

## Key Findings

### 1. The Multiplier Issue
- When `water` is specified in SOLUTION blocks within TRANSPORT, PHREEQC applies an unexpected multiplier to exchange capacity
- The multiplier appears to be approximately 2.5 × number of cells
- For example: 20 cells with `X 0.1` specified → 5.0 mol/cell actual (50x multiplier)

### 2. Water Mass Behavior
- PHREEQC calculates actual water mass from cell properties (length × area × porosity)
- The specified `water` value in SOLUTION is overridden during transport
- Example: `water 0.1` specified → 0.0001 kg actual (1000x reduction)

### 3. The Solution
**Don't specify water in SOLUTION blocks for TRANSPORT simulations**

```phreeqc
# WRONG - causes multiplier
SOLUTION 1-20
    water 0.02  # Don't do this in TRANSPORT!
    Na 1.0
    Cl 1.0 charge

# CORRECT - no multiplier
SOLUTION 1-20
    Na 1.0
    Cl 1.0 charge
```

### 4. Exchange Specification
- When water is NOT specified: `X` value = actual mol/cell
- When water IS specified: `X` value gets multiplied

## Correct Approach for Ion Exchange Transport

```phreeqc
# Feed solution
SOLUTION 0
    units     mg/L
    temp      25.0
    pH        7.5
    Ca        180
    Mg        80
    Na        50
    Cl        400 charge

# Initial column - NO water specification
SOLUTION 1-50
    units     mol/kgw
    temp      25.0
    pH        7.0
    Na        1.0
    Cl        1.0 charge
    # NO water line!

# Exchange - direct mol/cell
EXCHANGE 1-50
    X         0.04  # This will be 0.04 mol/cell
    -equilibrate 1-50

TRANSPORT
    -cells    50
    -shifts   300
    -lengths  0.02
    -porosities 0.4
    -dispersivities 50*0.005
    -flow_direction forward
    -boundary_conditions flux flux
```

## Verification Tests

Always verify exchange capacity with a simple test before running full simulations:

```python
# Check initial exchange in output
initial_data = [row for row in data if row.get('Step', 0) == -99]
for row in initial_data[:3]:
    cell = row.get('Cell', 0)
    x_mol = row.get('Total_X', 0)
    print(f"Cell {cell}: X = {x_mol} mol")
```

## DeepWiki References
- PHREEQC calculates water mass from cell properties in TRANSPORT
- The `water` keyword in SOLUTION is for equilibrium calculations
- Exchange capacity should be specified as total moles per cell

## Impact on Breakthrough Curves
Following this approach, breakthrough curves show:
- Realistic S-shaped profiles
- Breakthrough at expected bed volumes (~128 BV for 2 eq/L SAC)
- Proper chromatographic separation of Ca and Mg
- Reasonable Na displacement peaks (3-5x feed concentration)

## Recommendation
1. Never specify water in SOLUTION blocks for TRANSPORT
2. Use direct exchange capacity (mol/cell)
3. Verify with small test cases before full runs
4. Document this behavior in project notes

---
*Discovered through extensive testing with DeepWiki assistance*
*Date: July 2025*