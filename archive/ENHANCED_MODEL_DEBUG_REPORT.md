# Enhanced IX Model Debug Report

## Summary

The `IonExchangeTransport0DEnhanced` model was created to provide a cleaner interface to the base `IonExchangeTransport0D` model with automatic PHREEQC integration. However, testing revealed critical issues with outlet property calculations.

## Key Findings

### 1. Core Issue: Outlet Properties Not Updated

The outlet concentrations remain at MCAS default values (~10,000 mg/L or higher) even after:
- Ion removal rates are correctly calculated by PHREEQC
- Mass transfer terms are properly linked
- Ion removal rate variables are fixed

**Root Cause**: After fixing the `ion_removal_rate` variables, the outlet property block needs to be re-solved to reflect the mass balance constraints with the mass transfer terms. The current implementation doesn't do this.

### 2. pH Calculation Issue

The feed pH is being calculated as 0.30 instead of ~7.5. This appears to be related to how H+ and OH- concentrations are set in the feed.

### 3. Water Mole Fraction Issues

Even with proper mass flow specification, the water mole fraction initially calculates to 0.5 instead of >0.99. The `fix_mole_fractions` utility helps but needs to be called at the right time.

## Test Results

### Enhanced Model Test Output
```
Ca removal: -16776.4%  (negative means outlet > inlet!)
Mg removal: -21915.3%
Outlet hardness: 129,513 mg/L as CaCO3 (inlet was 705 mg/L)
```

### Mass Balance Check
- Ca removed: Correctly calculated based on fixed ion_removal_rate
- Na released: Correctly calculated based on stoichiometry
- Charge balance error: 0% (mass balance is enforced)

But outlet concentrations don't reflect these removal rates!

## Solution Approach

The enhanced model needs to:

1. After calling `calculate_performance()` and fixing ion removal rates
2. Re-solve the outlet property block with mass balance constraints active
3. Ensure outlet concentrations reflect the mass transfer

## Recommendation

For immediate use, the notebook should:
1. Use the base `IonExchangeTransport0D` model (which works correctly)
2. Call `calculate_performance()` after initialization if needed
3. Solve the full model to ensure outlet properties are updated

The enhanced model needs significant revision to properly handle the outlet property update sequence.

## Code That Needs Fixing

In `ion_exchange_transport_0D_enhanced.py`, the `initialize_enhanced` method should:

```python
def initialize_enhanced(self, **kwargs):
    # Standard initialization
    self.initialize(**kwargs)
    
    # Calculate PHREEQC equilibrium
    self.calculate_performance()
    
    # CRITICAL: Re-solve outlet properties after mass transfer is set
    from pyomo.environ import SolverFactory
    solver = SolverFactory('ipopt')
    solver.solve(self.control_volume.properties_out[0])
    
    # Then report performance
    self.report_performance()
```

## Alternative: Use Base Model

The base `IonExchangeTransport0D` model with the mass transfer fix already works correctly. The enhanced wrapper may not be necessary if users understand to:
1. Initialize the model
2. Call `calculate_performance()` if PHREEQC results are needed
3. Solve the model to propagate mass transfer effects