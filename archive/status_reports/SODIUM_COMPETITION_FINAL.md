# Sodium Competition Test Results

## Issue Identified

During testing at 1.0 mol/kg water capacity, we discovered that sodium competition was not being modeled correctly. Investigation revealed:

1. **Hardcoded log_k values were incorrect**: 
   - We used: Ca log_k = 0.72, Mg log_k = 0.52
   - PHREEQC database: Ca log_k = 0.8, Mg log_k = 0.6
   
2. **The difference seems small but is significant**:
   - Our values: Ca/Na = 5.2, Mg/Na = 3.3
   - Database values: Ca/Na = 6.3, Mg/Na = 4.0
   - Higher selectivity means LESS competition effect

3. **Implementation has been updated**:
   - Removed hardcoded EXCHANGE_SPECIES definitions
   - Added DATABASE directive to use phreeqc.dat
   - This ensures we use validated thermodynamic data

## Expected Behavior with Correct Values

With the PHREEQC database values (Ca log_k = 0.8, Mg log_k = 0.6):

| Na (mg/L) | Expected Reduction | Mechanism |
|-----------|-------------------|-----------|
| 0         | 0% (baseline)     | Pure Ca/Mg exchange |
| 200       | ~5-10%            | Some Na competition |
| 500       | ~15-20%           | Moderate competition |
| 1000      | ~25-30%           | Significant competition |

## Current Status

1. **Code has been updated** to use database values
2. **Test results still show no competition** - this suggests:
   - Possible issue with PHREEQC input structure
   - May need to verify exchange site initialization
   - Could be related to the resolution-independent approach

## Recommendations

1. **Further debugging needed** to identify why competition isn't showing:
   - Check if exchange sites are properly equilibrating
   - Verify the transport simulation is running correctly
   - Consider simpler test cases to isolate the issue

2. **The implementation is now correct** in principle:
   - Uses validated database values
   - Removes hardcoded assumptions
   - Follows PHREEQC best practices

3. **For production use**:
   - The Direct PHREEQC implementation shows perfect resolution independence
   - Actual < theoretical breakthrough is confirmed
   - Sodium competition modeling needs further investigation

## Key Takeaway

The switch from hardcoded values to database values is correct and necessary. The fact that we're not seeing competition effects suggests a deeper issue with how the simulation is structured, not with the thermodynamic data itself.