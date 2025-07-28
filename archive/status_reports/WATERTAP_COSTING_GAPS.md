# WaterTAP Costing Gaps for IX Design

## Important Missing Costs Not Available in WaterTAP

### 1. Degasser/CO2 Stripping Column ⚠️ CRITICAL GAP

WaterTAP does NOT provide costing functions for:
- Packed tower degassers
- CO2 stripping columns
- Air blowers/fans for stripping
- Packing material costs

**Impact**: Cannot properly cost 2 out of 3 recommended flowsheets:
- H-WAC → Degasser → Na-WAC
- SAC → Na-WAC → Degasser

**Typical Cost Range** (not from WaterTAP):
- Tower: $100-200K for 100 m³/hr system
- Blower: $30-50K
- Installation: $150-300K total

### 2. Non-Hazardous Brine Disposal

WaterTAP only includes hazardous waste disposal costs for acid regeneration.
Missing costs for:
- NaCl regeneration waste (brine)
- Rinse water disposal
- Non-hazardous liquid waste

**Impact**: Underestimates OPEX for SAC systems by 50-70%

**Typical Cost**: $5-20/m³ depending on location and regulations

### 3. System Integration Costs

WaterTAP IX costing is unit-specific and doesn't include:
- Inter-stage piping
- Common headers and manifolds
- Integrated control systems
- Common chemical feed systems
- Shared waste collection

**Impact**: 10-15% of total project cost not captured

### 4. Site-Specific Factors

WaterTAP uses fixed installation factor (1.65×) but doesn't account for:
- Site accessibility
- Indoor vs outdoor installation
- Seismic requirements
- Cold weather protection
- Chemical containment requirements

## How These Gaps Are Addressed

1. **Current Implementation**: The ix_economics_watertap.py module uses exclusively WaterTAP functions where available and notes gaps in the output.

2. **User Notification**: When degasser is present, the system returns a warning that degasser costing is not included.

3. **Documentation**: This file serves as the official record of what costs are NOT included when using WaterTAP costing.

## Recommendation for Users

When using IX Design MCP economics:
1. Budget additional 20-30% for degasser systems
2. Add site-specific waste disposal costs
3. Include 10-15% for system integration
4. Adjust installation factors for site conditions

The WaterTAP costing provides accurate costs for:
- IX vessels
- Resin
- Backwash/regeneration tanks
- Chemicals
- Basic O&M

But requires supplemental estimates for complete system costing.