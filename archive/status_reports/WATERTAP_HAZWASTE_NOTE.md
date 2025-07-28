# WaterTAP Hazardous Waste Disposal Cost Issue

## Problem Identified

WaterTAP's hazardous waste disposal cost parameter ($3.64/gallon) appears to be intended for concentrated hazardous waste disposal, not for neutralized ion exchange regenerant waste.

### Current WaterTAP Parameters
- `hazardous_regen_disposal`: $3.64/gallon
- `hazardous_min_cost`: $3,240/year
- `hazardous_resin_disposal`: $347.10/ton

### Issue
For a typical 100 m³/hr IX system:
- Waste volume: ~6.5 million gallons/year
- WaterTAP cost: $23.7 million/year (!)
- This represents 98% of OPEX

### Reality Check
Actual IX regenerant waste disposal costs:
- **Neutralized to sewer**: $0.005-0.02/gallon
- **Trucked disposal**: $0.10-0.50/gallon
- **Deep well injection**: $0.50-2.00/gallon
- **Hazardous landfill**: $2.00-5.00/gallon

The WaterTAP value of $3.64/gallon suggests hazardous landfill disposal of concentrated waste.

## Root Cause

WaterTAP's IX costing module appears to assume worst-case disposal:
1. No neutralization
2. No discharge permits
3. Full hazardous classification
4. Landfill disposal only

This is not representative of typical IX installations where:
1. Acid/caustic are neutralized on-site
2. Neutralized waste meets sewer discharge limits
3. Only metals/organics require special disposal

## Recommendation

For realistic IX costing:
1. Use WaterTAP for equipment and chemical costs
2. Override hazardous waste disposal with site-specific values
3. Typical values:
   - Neutralized discharge: $30-150/year per m³/hr capacity
   - Trucked disposal: $3,000-15,000/year per m³/hr capacity
   - NOT $240,000/year per m³/hr as WaterTAP calculates

## Implementation Note

The ix_economics_watertap.py module faithfully implements WaterTAP's methodology but users should be aware that hazardous waste disposal costs are likely 100-1000× higher than typical installations.