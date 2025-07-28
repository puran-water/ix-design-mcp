# Theoretical BV Calculation Corrected

## The Correct Formula

**Theoretical BV = Resin Capacity (eq/L) / Hardness (meq/L) × 1000**

This formula gives the theoretical number of bed volumes that can be treated before breakthrough.

## Why This Formula?

1. **Resin Capacity** (2.0 eq/L) is the total exchange capacity per liter of bed volume
2. **Hardness** (meq/L) is the contaminant load per liter of water
3. **1000** converts from equivalents to milliequivalents

## Examples

### Example 1: Standard Water
- Ca: 80 mg/L = 4.0 meq/L
- Mg: 24 mg/L = 2.0 meq/L
- Total hardness: 6.0 meq/L
- Theoretical BV = 2.0 / 6.0 × 1000 = **333 BV**

### Example 2: High Hardness
- Ca: 200 mg/L = 10.0 meq/L
- Mg: 100 mg/L = 8.2 meq/L
- Total hardness: 18.2 meq/L
- Theoretical BV = 2.0 / 18.2 × 1000 = **110 BV**

### Example 3: Soft Water
- Ca: 10 mg/L = 0.5 meq/L
- Mg: 5 mg/L = 0.4 meq/L
- Total hardness: 0.9 meq/L
- Theoretical BV = 2.0 / 0.9 × 1000 = **2,222 BV**

## Implementation in Code

```python
# Correct implementation
resin_capacity_eq_L = 2.0  # Standard SAC capacity per L of bed volume
theoretical_bv = (resin_capacity_eq_L / hardness_meq_L * 1000) if hardness_meq_L > 0 else 0
```

## Key Points

1. **Capacity is per bed volume**, not resin volume
2. **No bed volume term** in the theoretical BV formula
3. **Result is dimensionless** bed volumes (BV)
4. **Actual BV will be less** due to:
   - Sodium competition
   - Kinetic limitations
   - Flow maldistribution
   - Target hardness leakage

## Simulation Buffer

The simulation runs to `theoretical_bv * 1.2` to ensure breakthrough is captured:
- Provides 20% safety margin
- Accounts for competition effects
- Ensures target hardness breakthrough is found

This corrected formula ensures accurate predictions and proper simulation sizing.