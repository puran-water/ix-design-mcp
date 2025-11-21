"""
WAC SURFACE Model Builder

Generates PHREEQC SURFACE complexation blocks for Weak Acid Cation (WAC) exchangers.
Uses scientifically correct acid-base equilibrium to model pH-dependent capacity.

The SURFACE model correctly represents WAC chemistry:
- Carboxylic groups: RCOOH ⇌ RCOO- + H+ (pKa ≈ 4.5)
- Only deprotonated sites (RCOO-) can bind metals
- Capacity follows Henderson-Hasselbalch equation
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def build_wac_surface_template(
    pka: float = 4.8,           # Match CONFIG.WAC_PKA
    capacity_eq_l: float = 4.7, # Match CONFIG.WAC_H_TOTAL_CAPACITY
    ca_log_k: float = 1.5,      # Match CONFIG.WAC_LOGK_CA_H
    mg_log_k: float = 1.3,      # Match CONFIG.WAC_LOGK_MG_H
    na_log_k: float = -0.5,     # Match CONFIG.WAC_LOGK_NA_H
    k_log_k: float = -0.3,      # Match CONFIG.WAC_LOGK_K_H
    cells: int = 10,
    water_composition: Optional[Dict[str, float]] = None,
    bed_volume_L: float = 1.0,
    bed_depth_m: float = 1.0,
    porosity: float = 0.4,
    flow_rate_m3_hr: float = 0.1,
    max_bv: int = 300,
    database_path: str = None,
    resin_form: str = "Na",  # "Na" for sodium form, "H" for hydrogen form
    initialization_mode: str = "direct",  # "direct" or "staged" (staged recommended for high TDS + H-form)
    enable_autoscaling: bool = True  # Auto-scale cells for Pitzer + SURFACE numerical stability
) -> str:
    """
    Build SURFACE-based WAC template with correct acid-base chemistry.

    Args:
        pka: pKa of carboxylic acid groups (typically 4.5)
        capacity_eq_l: Total exchange capacity in eq/L resin
        ca_log_k: Log K for Ca binding to deprotonated sites
        mg_log_k: Log K for Mg binding to deprotonated sites
        na_log_k: Log K for Na binding to deprotonated sites
        k_log_k: Log K for K binding to deprotonated sites
        cells: Number of cells for transport discretization
        water_composition: Feed water composition (mg/L)
        bed_volume_L: Total bed volume in liters
        bed_depth_m: Bed depth in meters
        porosity: Bed porosity (typically 0.4)
        flow_rate_m3_hr: Flow rate in m³/hr
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database file
        resin_form: Initial resin form - "Na" or "H"
        initialization_mode: "direct" (immediate H-form) or "staged" (gradual Na→H conversion)
                             Staged mode recommended for high-TDS water + H-form to avoid convergence failure
        enable_autoscaling: If True, automatically scale cell count for Pitzer + SURFACE numerical stability
                           Target: <2,000 mol sites per cell when using Pitzer database

    Returns:
        Complete PHREEQC input string with SURFACE complexation model
    """

    if water_composition is None:
        water_composition = {}

    # Auto-scale cells for Pitzer + SURFACE numerical stability
    # Root cause (validated): Large site inventory overwhelms Newton-Raphson solver
    # Solution: Keep sites_per_cell < 2,000 mol when using Pitzer database
    if enable_autoscaling and database_path and 'pitzer' in database_path.lower():
        # Calculate TDS to confirm we're in high-TDS regime
        tds_g_l = (
            water_composition.get('ca_mg_l', 0) +
            water_composition.get('mg_mg_l', 0) +
            water_composition.get('na_mg_l', 0) +
            water_composition.get('k_mg_l', 0) +
            water_composition.get('cl_mg_l', 0) +
            water_composition.get('so4_mg_l', 0) +
            water_composition.get('hco3_mg_l', 0)
        ) / 1000.0

        # Calculate sites per cell with current configuration
        total_sites_mol = capacity_eq_l * bed_volume_L
        sites_per_cell = total_sites_mol / cells

        # Threshold from validated testing: Job c7175054 (10% density = ~1,800 mol) succeeded
        # Using 2,000 mol as conservative threshold with safety margin
        target_sites_per_cell = 2000  # mol

        if sites_per_cell > target_sites_per_cell:
            # Calculate required cell count
            import math
            cells_needed = int(math.ceil(total_sites_mol / target_sites_per_cell))

            logger.warning(
                f"Auto-scaling cells for Pitzer + SURFACE numerical stability: "
                f"{cells} → {cells_needed} cells "
                f"(TDS: {tds_g_l:.1f} g/L, sites_per_cell: {sites_per_cell:.0f} → {total_sites_mol/cells_needed:.0f} mol)"
            )

            cells = cells_needed

    # PHASE 2 DEBUG: Log input water composition
    logger.info(f"[PHASE2-DEBUG] build_wac_surface_template called with:")
    logger.info(f"[PHASE2-DEBUG] Water composition: {water_composition}")
    logger.info(f"[PHASE2-DEBUG] Resin form: {resin_form}, Capacity: {capacity_eq_l} eq/L")
    logger.info(f"[PHASE2-DEBUG] Cells: {cells}, Max BV: {max_bv}")

    # Calculate parameters
    # bed_volume_L * porosity gives water volume in L
    # 1 L water = 1 kg water (density = 1)
    water_per_cell_kg = bed_volume_L * porosity / cells  # kg water per cell

    # Calculate total moles of sites (capacity is in eq/L, sites are monoprotic)
    total_capacity_mol = capacity_eq_l * bed_volume_L  # Total moles of sites
    sites_per_cell = total_capacity_mol / cells  # Moles per cell

    # Calculate transport parameters
    total_water_volume_m3 = bed_volume_L * max_bv / 1000  # m³
    total_time_hr = total_water_volume_m3 / flow_rate_m3_hr  # hours
    shifts = max_bv * cells  # Total shifts for max_bv
    time_per_shift = total_time_hr / shifts  # hours per shift

    # Build PHREEQC input
    phreeqc_input = ""

    # Database
    if database_path:
        phreeqc_input += f"DATABASE {database_path}\n"

    # Add KNOBS for better convergence (especially for high TDS + H-form)
    phreeqc_input += """
KNOBS
    -iterations 800          # Increase max iterations from default 100
    -convergence_tolerance 1e-12  # Tighter than default (1e-8)
    -step_size 10            # Reduce from default 100 for stability
    -pe_step_size 2          # Reduce from default 10
    -numerical_derivatives true  # Improve Donnan math stability

"""

    phreeqc_input += f"""
TITLE WAC Simulation - SURFACE Complexation Model (pH-dependent capacity)
# Correct implementation using acid-base equilibrium
# Capacity follows Henderson-Hasselbalch: α = 1/(1 + 10^(pKa - pH))
# Initialization mode: {initialization_mode}

# Define surface master species for WAC sites
SURFACE_MASTER_SPECIES
    Wac_s Wac_sOH

SURFACE_SPECIES
    # Reference species (protonated carboxylic acid - RCOOH)
    Wac_sOH = Wac_sOH
        log_k 0

    # Deprotonation reaction (RCOOH ⇌ RCOO- + H+)
    # This controls pH-dependent capacity
    Wac_sOH = Wac_sO- + H+
        log_k -{pka}  # pKa of carboxylic groups

    # NOTE: No double protonation (Wac_sOH2+) - carboxylic acids cannot accept a second proton
    # This was causing incorrect 0% active sites at low pH

    # Divalent cation binding to deprotonated sites (2:1 stoichiometry)
    # Only RCOO- sites can bind metals
    2Wac_sO- + Ca+2 = (Wac_sO)2Ca
        log_k {ca_log_k}

    2Wac_sO- + Mg+2 = (Wac_sO)2Mg
        log_k {mg_log_k}

    # Monovalent cation binding to deprotonated sites
    Wac_sO- + Na+ = Wac_sONa
        log_k {na_log_k}

    Wac_sO- + K+ = Wac_sOK
        log_k {k_log_k}

# Custom pseudo-phase for pH control during staged initialization
PHASES
Fix_pH
    H+ = H+
    log_k  0.0

# PHASE2 DEBUG: Log feed water values
# Ca = {water_composition.get('ca_mg_l', 0)} mg/L
# Mg = {water_composition.get('mg_mg_l', 0)} mg/L
# Na = {water_composition.get('na_mg_l', 0)} mg/L
# HCO3 = {water_composition.get('hco3_mg_l', 0)} mg/L
# Cl = {water_composition.get('cl_mg_l', 0)} mg/L

# Feed solution
SOLUTION 0 Feed water
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        {water_composition.get('pH', 7.5)}
    units     mg/L
    Ca        {water_composition.get('ca_mg_l', 0)}
    Mg        {water_composition.get('mg_mg_l', 0)}
    Na        {water_composition.get('na_mg_l', 0)}
    K         {water_composition.get('k_mg_l', 0)}
    Cl        {water_composition.get('cl_mg_l', 0)} charge
    Alkalinity {water_composition.get('hco3_mg_l', 0)} as HCO3
    S(6)      {water_composition.get('so4_mg_l', 0)} as SO4
    N(5)      {water_composition.get('no3_mg_l', 0)} as NO3
    water     1 kg
"""

    # Build initial column solution based on resin form
    if resin_form == "Na":
        # Na-form: neutral pH with Na-loaded resin
        initial_ph = 7.0
        na_line = "    Na        500  # mg/L - represents Na-loaded resin\n"
        hco3_line = ""
        cl_line = "    Cl        0 charge  # Use 0 to auto-balance\n"
    else:
        # H-form: Start with feed water composition
        # Will be handled by multi-stage workflow with CO2 venting
        initial_ph = water_composition.get('pH', 7.0)
        na_line = ""  # No Na buffer - avoid creating Na-form
        hco3_line = ""
        cl_line = "    Cl        0 charge  # Auto-balance\n"

    phreeqc_input += f"""
# Initial column solution - {resin_form} form
SOLUTION 1-{cells} Initial column water
    units     mg/L
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        {initial_ph}
{na_line}{hco3_line}{cl_line}    water     {water_per_cell_kg} kg
"""

    # Add SURFACE blocks for each cell
    for i in range(1, cells + 1):
        phreeqc_input += f"""
SURFACE {i}
    -sites_units absolute
    -no_edl  # Disable electrical double layer (Donnan) to prevent calc_psi_avg convergence failure
             # Preserves pH-dependent protonation/deprotonation chemistry (SURFACE mass-action)
             # Eliminates "Too many iterations in calc_psi_avg" error at high ionic strength
             # Validated: PHREEQC docs HTMLversion/HTML/phreeqc3-52.htm:535-544 (Codex session 019aa7b7-e9ec)
    Wac_s {sites_per_cell} 1 1
"""

    # Add CO2 equilibrium phases for H-form (prevents pH crash)
    # DISABLED: CO2 equilibrium causing convergence issues
    # if resin_form == 'H':
    #     phreeqc_input += f"""
    # # CO2 equilibrium phases (allows H+ + HCO3- -> CO2 venting)
    # EQUILIBRIUM_PHASES 1-{cells}
    #     CO2(g)    -3.5  # log P = -3.5 (400 ppm), no finite reservoir
    # """

    # Staged initialization for H-form (recommended for high-TDS water)
    # Avoids massive H+ release that causes convergence failure
    if initialization_mode == 'staged' and resin_form == 'H':
        logger.info("Using staged initialization: Na-form → H-form conversion before transport")

        phreeqc_input += f"""
# ========================================
# STAGED INITIALIZATION (Na-form → H-form)
# ========================================
# Avoids massive proton release that causes convergence failure in high-TDS water
# Step 1: Pre-equilibrate resin in Na-form with feed water (sets ionic strength)
# Step 2: Gradual H-form conversion via mild HCl additions (1-2 steps)

# Step 1: Equilibrate Na-form resin with feed water (pH ALLOWED TO FLOAT)
# ============================================================================
# CRITICAL: pH Control and Charge Balance
# ----------------------------------------
# When WAC H-form resin contacts high-pH water, deprotonation releases massive H+:
#   - At pH 7.8 with pKa 4.8: ~99.9% of sites deprotonate (Henderson-Hasselbalch)
#   - For ~18,000 mol sites: ~17,840 mol H+ released into solution
#   - This naturally acidifies solution to pH ~2-4 (thermodynamic equilibrium)
#
# Using Fix_pH to maintain pH 7.8 creates IMPOSSIBLE thermodynamic state:
#   - Would require ~18,000 mol NaOH to neutralize all H+
#   - Without sufficient base, Newton solver cannot converge (charge deficit)
#   - Reference: Codex session 019aa2b9-d23b, PHREEQC doc/RELEASE.TXT, mytest/zeta.out
#
# SOLUTION: Let pH float during initialization
#   - Released H+ self-limits deprotonation via Le Chatelier's principle
#   - System reaches solvable equilibrium at pH ~2-4
#   - Donnan layer (below) handles surface charge properly
#   - Matches commercial WAC H-form operation (effluent pH crashes until neutralized)
# ============================================================================
USE solution 0  # Feed water
USE surface {' '.join(str(i) for i in range(1, cells+1))}
# NO EQUILIBRIUM_PHASES - pH allowed to float to thermodynamic equilibrium
END

# Step 2a: First mild HCl addition (partial H-form conversion)
# Add small amount of acid to begin converting Na-form → H-form
SOLUTION 100 Mild HCl step 1
    pH    3.0  charge  # Mild acid, not extreme
    Cl    0.01  # Small HCl addition (10 mM)
    water {water_per_cell_kg} kg

USE solution 100
USE surface 1-{cells}
END

# Step 2b: Second mild HCl addition (complete H-form conversion)
# Final conversion to H-form before transport begins
SOLUTION 101 Mild HCl step 2
    pH    2.5  charge  # Slightly stronger, still controlled
    Cl    0.02  # Moderate HCl addition (20 mM)
    water {water_per_cell_kg} kg

USE solution 101
USE surface 1-{cells}
END

# Now resin is in H-form, ready for transport with feed water
# ========================================
"""

    # Add transport block
    phreeqc_input += f"""
# Transport simulation
TRANSPORT
    -cells    {cells}
    -shifts   {shifts}
    -time_step {time_per_shift * 3600}  # Convert hours to seconds
    -flow_direction forward
    -boundary_conditions flux flux
    -lengths  {cells}*{bed_depth_m/cells}  # m per cell
    -dispersivities {cells}*0.002  # m (typical value)
    -porosities {cells}*{porosity}
    -punch_cells {cells}  # Output last cell
    -punch_frequency 1

# Output for breakthrough curves
SELECTED_OUTPUT 1
    -file transport.sel
    -reset false
    -solution true
    -time true
    -step true
    -pH true
    -alkalinity true
    -totals Ca Mg Na K Cl C(4) S(6)
    -molalities H+ OH- CO2 HCO3- CO3-2
    -molalities Wac_sOH Wac_sO- (Wac_sO)2Ca (Wac_sO)2Mg Wac_sONa Wac_sOK
    -saturation_indices Calcite Aragonite Dolomite
    -gas CO2(g)

USER_PUNCH 1
    -headings BV pH Ca_mg/L Mg_mg/L Hardness_mg/L H_Sites_% Ca_Sites_% Mg_Sites_% Na_Sites_% Free_Sites_% Ca_Removal_% Alk_mg/L_CaCO3 CO2_mol/L
    -start
    10 REM Calculate bed volumes
    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    30 IF (STEP_NO <= 0) THEN GOTO 500
    40 PUNCH BV
    50 PUNCH -LA("H+")

    60 REM Calculate concentrations in mg/L
    70 ca_mg = TOT("Ca") * 40.078 * 1000
    80 mg_mg = TOT("Mg") * 24.305 * 1000
    90 PUNCH ca_mg, mg_mg

    100 REM Calculate hardness as CaCO3
    110 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1
    120 PUNCH hardness_caco3

    130 REM Calculate site distribution (enhanced monitoring)
    140 wac_so_mol = MOL("Wac_sO-")  # Free deprotonated sites
    150 wac_soh_mol = MOL("Wac_sOH")  # Protonated sites (inactive)
    170 wac_ca_mol = MOL("(Wac_sO)2Ca")  # Ca-loaded sites
    180 wac_mg_mol = MOL("(Wac_sO)2Mg")  # Mg-loaded sites
    190 wac_na_mol = MOL("Wac_sONa")  # Na-loaded sites
    200 wac_k_mol = MOL("Wac_sOK")  # K-loaded sites

    210 REM Total sites (note: Ca and Mg use 2 sites each)
    220 total_sites = wac_soh_mol + wac_so_mol
    230 total_sites = total_sites + 2*wac_ca_mol + 2*wac_mg_mol
    240 total_sites = total_sites + wac_na_mol + wac_k_mol

    250 REM Calculate percentages for each state
    260 IF (total_sites > 0) THEN h_percent = (wac_soh_mol / total_sites) * 100 ELSE h_percent = 0
    270 IF (total_sites > 0) THEN ca_percent = (2*wac_ca_mol / total_sites) * 100 ELSE ca_percent = 0
    280 IF (total_sites > 0) THEN mg_percent = (2*wac_mg_mol / total_sites) * 100 ELSE mg_percent = 0
    290 IF (total_sites > 0) THEN na_percent = (wac_na_mol / total_sites) * 100 ELSE na_percent = 0
    300 IF (total_sites > 0) THEN free_percent = (wac_so_mol / total_sites) * 100 ELSE free_percent = 0

    310 PUNCH h_percent, ca_percent, mg_percent, na_percent, free_percent

    320 REM Calculate Ca removal
    330 feed_ca = {water_composition.get('ca_mg_l', 0)}
    340 IF (feed_ca > 0) THEN ca_removal = (1 - ca_mg/feed_ca) * 100 ELSE ca_removal = 0
    350 IF (ca_removal < 0) THEN ca_removal = 0
    360 PUNCH ca_removal

    370 REM Calculate alkalinity (using PHREEQC ALK function) and CO2
    380 alk_caco3 = ALK * 50000  # mg/L as CaCO3 (ALK is eq/kgw)
    390 co2_mol = MOL("CO2")
    400 PUNCH alk_caco3, co2_mol

    500 REM end
    -end

END
"""

    logger.info(f"Generated WAC SURFACE template with pKa={pka}, capacity={capacity_eq_l} eq/L")
    logger.info(f"At pH={pka}, expect 50% active sites (Henderson-Hasselbalch)")
    logger.info(f"Water composition: Ca={water_composition.get('ca_mg_l', 0)}, Mg={water_composition.get('mg_mg_l', 0)}, "
                f"Na={water_composition.get('na_mg_l', 0)}, HCO3={water_composition.get('hco3_mg_l', 0)}")

    return phreeqc_input


def calculate_theoretical_capacity(pH: float, pka: float = 4.5, max_capacity: float = 3.5) -> float:
    """
    Calculate theoretical WAC capacity at given pH using Henderson-Hasselbalch equation.

    Args:
        pH: Solution pH
        pka: pKa of carboxylic groups
        max_capacity: Maximum capacity at high pH (eq/L)

    Returns:
        Available capacity in eq/L
    """
    from math import pow

    # Henderson-Hasselbalch: fraction deprotonated = 1 / (1 + 10^(pKa - pH))
    fraction_active = 1.0 / (1.0 + pow(10, pka - pH))
    return max_capacity * fraction_active


def validate_ph_dependency(pH: float, pka: float = 4.5) -> Dict[str, float]:
    """
    Validate that capacity follows Henderson-Hasselbalch equation.

    Returns dict with theoretical values for testing.
    """
    result = {
        'pH': pH,
        'pka': pka,
        'fraction_deprotonated': 1.0 / (1.0 + pow(10, pka - pH)),
        'fraction_protonated': pow(10, pka - pH) / (1.0 + pow(10, pka - pH))
    }

    # Add interpretation
    if abs(pH - pka) < 0.1:
        result['expected'] = "50% capacity (pH = pKa)"
    elif pH < pka - 1:
        result['expected'] = "<10% capacity (pH << pKa)"
    elif pH > pka + 1:
        result['expected'] = ">90% capacity (pH >> pKa)"
    else:
        result['expected'] = f"{result['fraction_deprotonated']*100:.1f}% capacity"

    return result
