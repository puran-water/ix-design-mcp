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
    pka: float = 4.5,
    capacity_eq_l: float = 3.5,
    ca_log_k: float = 4.0,
    mg_log_k: float = 3.2,
    na_log_k: float = -0.5,  # Lower affinity than divalent
    k_log_k: float = -0.3,   # Slightly higher than Na
    cells: int = 10,
    water_composition: Optional[Dict[str, float]] = None,
    bed_volume_L: float = 1.0,
    bed_depth_m: float = 1.0,
    porosity: float = 0.4,
    flow_rate_m3_hr: float = 0.1,
    max_bv: int = 300,
    database_path: str = None,
    resin_form: str = "Na"  # "Na" for sodium form, "H" for hydrogen form
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

    Returns:
        Complete PHREEQC input string with SURFACE complexation model
    """

    if water_composition is None:
        water_composition = {}

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

    phreeqc_input += f"""
TITLE WAC Simulation - SURFACE Complexation Model (pH-dependent capacity)
# Correct implementation using acid-base equilibrium
# Capacity follows Henderson-Hasselbalch: α = 1/(1 + 10^(pKa - pH))

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
    -no_edl  # No electrical double layer (simpler model)
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
    -headings BV pH Ca_mg/L Mg_mg/L Hardness_mg/L H_Sites_% Ca_Sites_% Mg_Sites_% Na_Sites_% Free_Sites_% Ca_Removal_% Alk_mg/L CO2_mol/L
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

    370 REM Calculate alkalinity and CO2
    380 alk_mg = TOT("C(4)") * 61.017 * 1000  # as HCO3
    390 co2_mol = MOL("CO2")
    400 PUNCH alk_mg, co2_mol

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
