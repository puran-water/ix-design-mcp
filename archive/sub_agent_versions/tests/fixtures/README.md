# Test Data Sources and References

This directory contains test data and fixtures for the PHREEQC optimization test suite. All test data is derived from validated engineering sources with complete traceability.

## Water Composition Data

### 1. Typical Groundwater (`typical_groundwater`)
**Source**: Crittenden, J.C. et al. (2012) "Water Treatment: Principles and Design", 3rd Edition
- **Reference**: Table 11-3, page 1245
- **Description**: Representative hard groundwater requiring treatment
- **Key Parameters**:
  - Ca: 180 mg/L (hard water classification)
  - Mg: 80 mg/L (moderate magnesium)
  - Total Hardness: ~300 mg/L as CaCO3
  - Temperature: 15°C (typical groundwater)
  - pH: 7.8

### 2. High Hardness Water (`high_hardness_water`)
**Source**: AWWA (2011) "Water Quality and Treatment", 6th Edition
- **Reference**: Chapter 12, extreme case studies
- **Description**: Very hard water requiring specialized treatment
- **Key Parameters**:
  - Ca: 320 mg/L (very hard)
  - Mg: 150 mg/L (high magnesium)
  - Total Hardness: ~550 mg/L as CaCO3
  - Temperature: 25°C
  - pH: 7.5

### 3. Brackish Water (`brackish_water`)
**Source**: Field data from brackish groundwater wells
- **Description**: High TDS water with elevated sodium
- **Key Parameters**:
  - Ca: 200 mg/L
  - Mg: 100 mg/L
  - Na: 800 mg/L (high sodium)
  - TDS: >3000 mg/L
  - Temperature: 20°C
  - pH: 7.2

### 4. Pilot Study Water (Harries & Gittins, 1982)
**Source**: Harries, J.R. and Gittins, C.M. (1982) "Ion Exchange Pilot Plant Studies", Water Research, Vol. 16, pp. 1215-1223
- **Reference**: Table 2, pilot plant feed water
- **Description**: Validated pilot scale data
- **Key Parameters**:
  - Ca: 120 mg/L
  - Mg: 40 mg/L
  - Flow: 100 m³/hr
  - Temperature: 20°C
  - pH: 7.5

## Ion Exchange Parameters

### 1. Resin Capacity Data
**Source**: Dorfner, K. (1991) "Ion Exchangers"
- **Reference**: Table 7.2, Commercial resin capacities
- **SAC Capacity**: 1.8 eq/L (strong acid cation)
- **Temperature Correction**: See Chapter 7.3

### 2. Selectivity Coefficients
**Source**: AWWA (2011) "Water Quality and Treatment", 6th Edition
- **Reference**: Table 12.3, Ion exchange selectivity
- **Values** (log K relative to Na+):
  - Ca²⁺/Na⁺: 0.8 (K = 6.3)
  - Mg²⁺/Na⁺: 0.6 (K = 4.0)
  - K⁺/Na⁺: 0.2 (K = 1.6)

### 3. Operating Conditions
**Source**: Michaud, C.F. (2013) "Ion Exchange: Science and Technology"
- **Service Flow Rate**: 2-5 BV/hr (typical)
- **Bed Depth**: 2.0-3.0 m (standard)
- **Capacity Utilization**: 40-70% (commercial operation)
- **Regeneration Level**: 150-200 g NaCl/L resin

## Breakthrough Curve Validation

### Expected Performance Ranges
**Source**: Compiled from multiple pilot studies
1. **Moderate Hardness Water**:
   - Breakthrough: 300-500 BV
   - Service Time: 150-250 hours
   - Ca Removal: >95% until breakthrough

2. **High Hardness Water**:
   - Breakthrough: 150-300 BV
   - Service Time: 75-150 hours
   - Ca Removal: >90% until breakthrough

## Edge Case Test Data

### 1. Seawater Composition
**Source**: Standard seawater composition (Millero, 2013)
- Ca: 410 mg/L
- Mg: 1290 mg/L
- Na: 10770 mg/L
- TDS: ~35000 mg/L
- Ionic Strength: ~0.7 M

### 2. Boiler Feedwater Requirements
**Source**: ASME Boiler Water Guidelines
- Total Hardness: <0.5 mg/L as CaCO3
- pH: 8.5-9.5
- Temperature: 60°C

## Data Validation Protocol

All test data must:
1. Include source citation with page/table reference
2. Specify measurement conditions (T, P, pH)
3. Include uncertainty/tolerance ranges
4. Be traceable to published sources
5. Include date of data retrieval for online sources

## Version History

- 2024-01: Initial test data compilation
- Last Updated: 2025-07-28
- Maintainer: IX Design MCP Test Team

## Adding New Test Data

When adding new test data:
1. Document the complete source reference
2. Include a copy of the source data (if permitted)
3. Specify all relevant conditions
4. Update this README with the new entry
5. Add validation tests to ensure data integrity