# PHREEQC Exchange Species Configuration Guide

## Based on DeepWiki Research Findings

### Key Issues Identified

1. **100% Removal Until Breakthrough**
   - Caused by default activity coefficient assumptions (activity = equivalent fraction)
   - Results in ideal exchange behavior with sharp breakthrough curves
   - No gradual leakage as resin approaches saturation

2. **H+ WAC Not Removing Only Temporary Hardness**
   - EXCHANGE models alone don't capture pH-dependent capacity
   - Need explicit H+ release reactions or SURFACE complexation
   - Must model the pKa behavior of carboxylic acid groups

3. **Lack of Ion Competition Effects**
   - High selectivity coefficients alone don't create realistic competition
   - Need activity coefficient corrections for non-ideal behavior
   - Dispersivity and kinetics also play important roles

### Proper Configuration Guidelines

#### 1. SAC (Strong Acid Cation) Resins

```phreeqc
EXCHANGE_SPECIES
    # Reference species
    Na+ + X- = NaX
        log_k  0.0
        -gamma 4.08 0.082  # Activity coefficient parameters
    
    # Divalent cations with selectivity
    Ca+2 + 2X- = CaX2
        log_k  0.8  # Gives Ca/Na selectivity ~5
        -gamma 5.0 0.165
    
    Mg+2 + 2X- = MgX2
        log_k  0.6  # Gives Mg/Na selectivity ~3.3
        -gamma 5.5 0.2
```

**Key Points:**
- Always include `-gamma` parameters for activity coefficients
- Activity = equivalent_fraction × gamma
- Parameters from standard databases (phreeqc.dat)

#### 2. WAC H+ (Weak Acid Cation - H+ Form)

**Option A: Modified EXCHANGE approach**
```phreeqc
EXCHANGE_SPECIES
    # H+ form as reference
    H+ + X- = HX
        log_k  0.0
    
    # Ca exchange releases H+ explicitly
    Ca+2 + 2HX = CaX2 + 2H+
        log_k  -3.0  # pH dependent
    
    Mg+2 + 2HX = MgX2 + 2H+
        log_k  -3.5
```

**Option B: SURFACE complexation (recommended)**
```phreeqc
SURFACE_MASTER_SPECIES
    Wac   Wac_OH

SURFACE_SPECIES
    # Identity
    Wac_OH = Wac_OH
        log_k  0.0
    
    # Protonation (inactive at low pH)
    Wac_OH + H+ = Wac_OH2+
        log_k  4.8  # pKa of carboxylic acid
    
    # Deprotonation (active at high pH)
    Wac_OH = Wac_O- + H+
        log_k  -4.8
    
    # Metal binding to deprotonated sites
    2Wac_O- + Ca+2 = (Wac_O)2Ca
        log_k  3.0
```

**Key Points:**
- SURFACE complexation better models pH dependence
- Only active above pH ~6 (pKa + 1)
- Automatically limits to temporary hardness

#### 3. Transport Configuration for Realistic Curves

```phreeqc
TRANSPORT
    -cells    20
    -shifts   200
    -time_step 300
    -flow_direction forward
    -boundary_conditions flux flux
    -lengths  0.1
    -dispersivities 20*0.01  # Non-zero for S-shaped curves
    -diffusion_coefficient 1e-9  # Include diffusion
    -print_frequency 1
```

**Key Parameters:**
- **Dispersivity**: Controls breakthrough curve spreading
  - 0 = sharp curves
  - 0.01-0.1 = realistic S-shaped curves
- **Number of cells**: More cells = less numerical dispersion
- **Time step**: Smaller = more accurate but slower

### Activity Coefficient Parameters

From PHREEQC databases, typical `-gamma` parameters:

| Ion    | Debye-Hückel a | Debye-Hückel b |
|--------|----------------|----------------|
| Na+    | 4.08          | 0.082          |
| K+     | 3.5           | 0.015          |
| NH4+   | 2.5           | 0.0            |
| Ca+2   | 5.0           | 0.165          |
| Mg+2   | 5.5           | 0.2            |
| Fe+2   | 6.0           | 0.0            |
| Al+3   | 9.0           | 0.0            |

### Expected Behavior with Proper Configuration

1. **Gradual Leakage**
   - Small amounts of hardness in effluent even before main breakthrough
   - Leakage increases as resin approaches saturation
   - Activity coefficients enable this non-ideal behavior

2. **S-Shaped Breakthrough Curves**
   - 10% to 90% breakthrough spread over several bed volumes
   - Dispersivity controls the curve shape
   - More realistic than step-change breakthrough

3. **Ion Competition**
   - High Na reduces effective capacity
   - Earlier breakthrough with competing ions
   - Mg typically breaks through before Ca

4. **WAC H+ Behavior**
   - pH drops as H+ is released
   - Alkalinity consumed
   - Only temporary hardness removed
   - Permanent hardness passes through

### Implementation Checklist

- [ ] Define EXCHANGE_MASTER_SPECIES
- [ ] Add all EXCHANGE_SPECIES with proper log_k values
- [ ] Include -gamma parameters for activity coefficients
- [ ] For WAC: Use SURFACE or explicit H+ release reactions
- [ ] Set non-zero dispersivity in TRANSPORT
- [ ] Use sufficient cells (>10) for numerical accuracy
- [ ] Include multicomponent diffusion if needed
- [ ] Verify with test runs showing gradual leakage

### References

- PHREEQC database files (phreeqc.dat, iso.dat, stimela.dat)
- Appelo & Postma (2005) - Geochemistry, groundwater and pollution
- Parkhurst & Appelo (2013) - PHREEQC User's Guide
- Ion exchange resin manufacturer data (Dow, Purolite, Lanxess)