"""
WAC PHREEQC Template Module

Provides PHREEQC input templates for Weak Acid Cation (WAC) exchange resins.
Uses SURFACE complexation model for scientifically correct pH-dependent capacity.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from pathlib import Path
import sys

# Define logger FIRST before using it
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.core_config import CONFIG
from tools.base_ix_simulation import BaseIXSimulation

# Import SURFACE builder
try:
    from tools.wac_surface_builder import build_wac_surface_template
    SURFACE_BUILDER_AVAILABLE = True
except ImportError:
    SURFACE_BUILDER_AVAILABLE = False
    logger.error("WAC SURFACE builder not available - WAC simulations will fail")


# Small helper to tolerate legacy and new field names (pH vs ph, Cl_- vs cl_mg_l, etc.)
def _get(dct: Dict[str, Any], *keys, default: Any = 0.0):
    """Extract value from dict using multiple possible keys (tries in order)."""
    for k in keys:
        if k in dct and dct[k] is not None:
            return dct[k]
    return default


def create_wac_na_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 16,  # Increased from 10 to improve TRANSPORT stability (Codex 019aa7b7)
    max_bv: int = 300,
    database_path: Optional[str] = None,
    enable_enhancements: bool = True,
    capacity_factor: float = 1.0,
    use_dual_domain: bool = True  # NEW: Feature flag for dual-domain model
) -> str:
    """
    Create PHREEQC input for WAC Na-form simulation.

    Uses dual-domain EXCHANGE model by default to prevent pH crash.
    Can fall back to SURFACE complexation model if needed.

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        use_dual_domain: If True, use dual-domain EXCHANGE model (recommended)

    Returns:
        PHREEQC input string
    """
    # Check if dual-domain is requested (default)
    if use_dual_domain:
        logger.info("Using dual-domain EXCHANGE model for WAC_Na (prevents pH crash)")
        return _create_wac_dual_domain_input(
            water_composition=water_composition,
            vessel_config=vessel_config,
            cells=cells,
            max_bv=max_bv,
            database_path=database_path,
            capacity_factor=capacity_factor,
            resin_form='Na'
        )

    # Fallback to SURFACE model (legacy)
    if not SURFACE_BUILDER_AVAILABLE:
        raise ImportError("WAC SURFACE builder required for WAC simulations")

    # Get database path
    if database_path is None:
        database_path = str(CONFIG.get_phreeqc_database())

    # Extract parameters
    bed_volume_L = vessel_config['bed_volume_L']
    bed_depth_m = vessel_config.get('bed_depth_m', 1.5)
    flow_rate_m3_hr = water_composition.get('flow_m3_hr', 0.1)

    # WAC Na-form capacity
    capacity_eq_L = CONFIG.WAC_NA_WORKING_CAPACITY * capacity_factor

    logger.info(f"Creating WAC Na-form SURFACE model: capacity={capacity_eq_L} eq/L, pKa=4.5")

    # Build SURFACE-based template
    phreeqc_input = build_wac_surface_template(
        pka=4.5,  # Carboxylic acid pKa
        capacity_eq_l=capacity_eq_L,
        ca_log_k=1.0,  # Ca binding constant
        mg_log_k=0.8,  # Mg binding constant
        na_log_k=-0.5,  # Na reference (lower than divalent)
        k_log_k=-0.3,  # K slightly higher than Na
        cells=cells,
        water_composition=water_composition,
        bed_volume_L=bed_volume_L,
        bed_depth_m=bed_depth_m,
        porosity=0.4,
        flow_rate_m3_hr=flow_rate_m3_hr,
        max_bv=max_bv,
        database_path=database_path,
        resin_form="Na"  # Na-form WAC
    )

    return phreeqc_input


def create_wac_h_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 10,
    max_bv: int = 300,
    database_path: Optional[str] = None,
    enable_enhancements: bool = True,
    capacity_factor: float = 1.0,
    use_multistage: bool = False,
    use_dual_domain: bool = False  # DEPRECATED - always use kinetic model
) -> str:
    """
    Create PHREEQC input for WAC H-form simulation.

    Uses SURFACE complexation with dual-domain transport to prevent pH crash.
    Implements Henderson-Hasselbalch pH dependence with mass transfer control.

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        enable_enhancements: Not used (kept for compatibility)
        capacity_factor: Capacity adjustment factor
        use_multistage: Not used (deprecated)
        use_dual_domain: Not used (deprecated)

    Returns:
        PHREEQC input string
    """
    # Use dual-domain EXCHANGE model (same proven approach as WAC_Na)
    logger.info("Using dual-domain EXCHANGE model for WAC_H (prevents pH crash)")
    return _create_wac_dual_domain_input(
        water_composition=water_composition,
        vessel_config=vessel_config,
        cells=cells,
        max_bv=max_bv,
        database_path=database_path,
        capacity_factor=capacity_factor,
        resin_form='H'
    )


def _create_wac_dual_domain_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int,
    max_bv: int,
    database_path: Optional[str],
    capacity_factor: float,
    resin_form: str
) -> str:
    """
    Create PHREEQC input using dual-domain EXCHANGE model.

    This prevents pH crash by limiting instantaneous H+ release through
    mass transfer limitations between mobile and immobile zones.

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        capacity_factor: Capacity adjustment factor
        resin_form: 'H' or 'Na' form

    Returns:
        PHREEQC input string
    """
    # Get database path
    if database_path is None:
        database_path = str(CONFIG.get_phreeqc_database())

    # Extract parameters
    bed_volume_L = vessel_config['bed_volume_L']
    bed_depth_m = vessel_config.get('bed_depth_m', 1.5)

    # Capacity based on resin form
    if resin_form == 'H':
        base_capacity = CONFIG.WAC_H_TOTAL_CAPACITY
    else:  # Na form
        base_capacity = CONFIG.WAC_NA_WORKING_CAPACITY

    capacity_eq_L = base_capacity * capacity_factor

    # Dual-domain parameters
    # Reduced from 0.1 to 0.05 for TRANSPORT stability (Codex 019aa7b7)
    # Lower mobile fraction reduces instantaneous charge change in mobile zone
    mobile_fraction = 0.05
    porosity = 0.4

    # Calculate exchange capacity distribution
    wet_resin_volume_L = bed_volume_L * (1 - porosity)
    total_capacity_eq = capacity_eq_L * wet_resin_volume_L

    # Split between mobile and immobile
    mobile_capacity_eq = total_capacity_eq * mobile_fraction
    immobile_capacity_eq = total_capacity_eq * (1 - mobile_fraction)

    # Auto-refine cells for Na-form to limit per-cell capacity and stiffness
    if resin_form == 'Na':
        target_mobile_eq = 1.0   # eq per cell (mobile)
        target_immobile_eq = 10.0  # eq per cell (immobile)
        cells_needed = max(
            cells,
            int(np.ceil(mobile_capacity_eq / target_mobile_eq)) if mobile_capacity_eq > 0 else cells,
            int(np.ceil(immobile_capacity_eq / target_immobile_eq)) if immobile_capacity_eq > 0 else cells,
        )
        if cells_needed != cells:
            logger.info(f"Auto-adjusting cells for Na-form: {cells} -> {cells_needed} to limit per-cell capacity")
            cells = cells_needed

    # Per cell calculations
    mobile_eq_per_cell = mobile_capacity_eq / cells
    immobile_eq_per_cell = immobile_capacity_eq / cells

    # Water per cell
    water_volume_L = bed_volume_L * porosity
    water_per_cell_kg = water_volume_L / cells

    # Mass transfer coefficient (reduced from 1.7e-5 for TRANSPORT stability - Codex 019aa7b7)
    # Lower alpha reduces mass transfer rate between mobile/immobile zones
    alpha = 5e-6  # 1/s

    # Calculate shifts for max_bv
    shifts = int(max_bv * bed_volume_L / water_per_cell_kg)

    # Cell length
    cell_length_m = bed_depth_m / cells

    logger.info(f"Dual-domain WAC {resin_form}-form: capacity={capacity_eq_L} eq/L, "
                f"mobile={mobile_fraction*100}%, alpha={alpha}")
    logger.info(f"Mobile: {mobile_eq_per_cell:.2f} eq/cell, "
                f"Immobile: {immobile_eq_per_cell:.2f} eq/cell")

    # Build PHREEQC input
    lines = []

    # Database
    lines.append(f"DATABASE {database_path}")
    lines.append("LOGFILE wac_h_debug.log")  # Debug logging
    lines.append("")

    # Title
    lines.append(f"TITLE WAC {resin_form}-form dual-domain simulation")
    lines.append(f"# Prevents pH crash through mass transfer limitations")
    lines.append(f"# Total capacity: {capacity_eq_L} eq/L")
    lines.append(f"# Mobile fraction: {mobile_fraction*100}%")
    lines.append("")

    # Convergence parameters (validated against usgs-coupled/phreeqc3 via Codex 019aa7b7)
    # These KNOBS controls improve stability for stiff dual-domain chemistry
    lines.append("KNOBS")
    lines.append("    -iterations 400")  # Increased for difficult convergence
    lines.append("    -convergence_tolerance 1e-8")  # Relaxed for stiff ion-exchange gradients
    lines.append("    -step_size 5")  # Smaller steps for stability
    lines.append("    -pe_step_size 1")  # Conservative redox steps
    lines.append("    -diagonal_scale true")  # Improves conditioning for stiff problems
    lines.append("")

    # Define exchange master species and reactions
    lines.append("EXCHANGE_MASTER_SPECIES")
    lines.append("    X  X-")
    lines.append("")

    lines.append("EXCHANGE_SPECIES")
    lines.append("    # Reference species")
    lines.append("    X- = X-")
    lines.append("        log_k  0.0")
    lines.append("")

    # Only include protonation reaction for H-form
    # For Na-form, this causes pH spike to 10-11 and stiffens TRANSPORT solver (Codex 019aa7b7)
    if resin_form == 'H':
        lines.append("    # Protonation (H-form)")
        lines.append("    X- + H+ = XH")
        lines.append("        log_k  4.8  # pKa for acrylic WAC resin (literature: 4.8 +/- 0.1)")
        lines.append("")

    lines.append("    # Calcium exchange")
    lines.append("    2X- + Ca+2 = CaX2")
    lines.append("        log_k  2.0  # From resin_selectivity.json; net Ca/H = 2.0 - 9.6 = -7.6")
    lines.append("")
    lines.append("    # Magnesium exchange")
    lines.append("    2X- + Mg+2 = MgX2")
    lines.append("        log_k  1.8  # From resin_selectivity.json; slightly lower than Ca")
    lines.append("")
    lines.append("    # Sodium exchange")
    lines.append("    X- + Na+ = NaX")
    lines.append("        log_k  0.0  # Reference")
    lines.append("")

    # Calculate immobile water mass (used by both H-form and Na-form)
    immobile_water_kg = water_per_cell_kg * (1 - porosity) / porosity

    if resin_form == 'H':
        # ------------------------------------------------------------------
        # H-form: single-run initialization (unchanged logic)
        # ------------------------------------------------------------------

        # Feed solution
        lines.append("SOLUTION 0  # Feed water")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {_get(water_composition, 'temperature_celsius', default=25)}")
        lines.append(f"    pH        {_get(water_composition, 'pH', 'ph', default=7.8)}")
        lines.append(f"    Ca        {_get(water_composition, 'ca_mg_l', default=0)}")
        lines.append(f"    Mg        {_get(water_composition, 'mg_mg_l', default=0)}")
        lines.append(f"    Na        {_get(water_composition, 'na_mg_l', 'Na_1+', 'Na_+', default=0)}")
        lines.append(f"    K         {_get(water_composition, 'k_mg_l', default=0)}")
        lines.append(f"    Cl        {_get(water_composition, 'cl_mg_l', 'Cl_1-', 'Cl_-', default=0)}")
        lines.append(f"    C(4)      {_get(water_composition, 'hco3_mg_l', 'HCO3_1-', 'HCO3_-', default=0)} as HCO3")
        lines.append(f"    S(6)      {_get(water_composition, 'so4_mg_l', 'SO4_2-', default=0)} as SO4")
        lines.append("")

        # Initial solutions in column (equilibrated with resin)
        lines.append(f"SOLUTION 1-{cells}  # Initial column - H form")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {water_composition.get('temperature_celsius', 25)}")
        lines.append("    pH        3.5")
        lines.append("    Cl        1e-6 charge  # Trace for equilibration")
        lines.append(f"    water     {water_per_cell_kg} kg")
        lines.append("")

        # Immobile cells: contiguous numbering (Codex 019aab6b)
        lines.append(f"SOLUTION {cells+1}-{2*cells}  # Immobile - H form")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {water_composition.get('temperature_celsius', 25)}")
        lines.append("    pH        3.5")
        lines.append("    Cl        1e-6 charge  # Trace for equilibration")
        lines.append(f"    water     {immobile_water_kg} kg")
        lines.append("")

        # Exchange sites - split between mobile and immobile
        lines.append(f"EXCHANGE 1-{cells}  # Mobile sites")
        lines.append(f"    XH        {mobile_eq_per_cell}")
        lines.append(f"    -equilibrate with solution 1-{cells}")
        lines.append("")
        lines.append(f"EXCHANGE {cells+1}-{2*cells}  # Immobile sites")
        lines.append(f"    XH        {immobile_eq_per_cell}")
        lines.append(f"    -equilibrate with solution {cells+1}-{2*cells}")
        lines.append("")

        # CO2 equilibrium for pH buffering (small finite amount)
        lines.append(f"EQUILIBRIUM_PHASES 1-{cells}")
        lines.append("    CO2(g)    -3.5  0.01  # Small CO2 reservoir for pH buffering")
        lines.append("")

        # DUMP for debugging initial state (contiguous numbering)
        lines.append("DUMP")
        lines.append(f"    -solution 1-{2*cells}")
        lines.append(f"    -exchange 1-{2*cells}")
        lines.append("")

        # Transport with stagnant zones
        lines.append("TRANSPORT")
        lines.append(f"    -cells    {cells}")
        lines.append(f"    -shifts   {shifts}")
        lines.append(f"    -lengths  {cell_length_m}")
        lines.append(f"    -dispersivities {cells}*0.002")
        lines.append(f"    -porosities {porosity}")
        lines.append("    -flow_direction forward")
        lines.append("    -boundary_conditions flux flux")
        lines.append(f"    -stagnant 1 {alpha} {porosity * mobile_fraction} {porosity * (1 - mobile_fraction)}")  # Key: mass transfer
        lines.append(f"    -print_frequency {cells}")
        lines.append(f"    -punch_frequency {cells}")
        lines.append(f"    -punch_cells {cells}")
        lines.append("")

    else:
        # ------------------------------------------------------------------
        # Na-form: two-stage approach to allow Na-saturated resin with
        # realistic low-Na pore water.
        # Stage 1: Pre-saturate exchanger with a brine, SAVE exchange.
        # Stage 2: USE saved exchange with low-Na porewater and run TRANSPORT.
        # ------------------------------------------------------------------

        # Stage 1: Brine preload to fully occupy exchanger (SAVE solution+exchange)
        feed_ph = _get(water_composition, 'pH', 'ph', default=7.8)
        max_eq_per_water = max(
            mobile_eq_per_cell / water_per_cell_kg,
            immobile_eq_per_cell / immobile_water_kg
        )
        preload_na_mg_l = max_eq_per_water * 23000 * 1.2  # 20% safety factor

        lines.append("# Stage 1: Pre-saturate exchanger with high-Na solution")
        lines.append(f"SOLUTION 1-{cells}  # Mobile brine preload")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {_get(water_composition, 'temperature_celsius', default=25)}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {preload_na_mg_l:.1f}")
        lines.append(f"    Cl        {preload_na_mg_l:.1f} charge")
        lines.append(f"    water     {water_per_cell_kg} kg")
        lines.append("")

        lines.append(f"SOLUTION {cells+1}-{2*cells}  # Immobile brine preload")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {_get(water_composition, 'temperature_celsius', default=25)}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {preload_na_mg_l:.1f}")
        lines.append(f"    Cl        {preload_na_mg_l:.1f} charge")
        lines.append(f"    water     {immobile_water_kg} kg")
        lines.append("")

        lines.append(f"EXCHANGE 1-{cells}  # Mobile capacity preset")
        lines.append(f"    NaX       {mobile_eq_per_cell}")
        lines.append(f"    -equilibrate 1-{cells}")
        lines.append("")
        lines.append(f"EXCHANGE {cells+1}-{2*cells}  # Immobile capacity preset")
        lines.append(f"    NaX       {immobile_eq_per_cell}")
        lines.append(f"    -equilibrate {cells+1}-{2*cells}")
        lines.append("")
        lines.append(f"SAVE solution 1-{2*cells}")
        lines.append(f"SAVE exchange 1-{2*cells}")
        lines.append("")
        lines.append("END")
        lines.append("")

        # Stage 2: Actual transport run with realistic porewater (loaded from SAVE)
        lines.append("# Stage 2: Conditioning transport with brine feed (smooths gradient)")

        # Use the same high-Na brine as feed for conditioning
        lines.append("SOLUTION 0  # Conditioning feed (brine)")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {_get(water_composition, 'temperature_celsius', default=25)}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {preload_na_mg_l:.1f}")
        lines.append(f"    Cl        {preload_na_mg_l:.1f} charge")
        lines.append("")

        # Load pre-equilibrated porewater and exchanger (from Stage 1)
        lines.append(f"USE solution 1-{2*cells}")
        lines.append(f"USE exchange 1-{2*cells}")
        lines.append("")

        # Conditioning transport run (short)
        conditioning_shifts = max(5, int(0.1 * shifts))  # ~10% of total shifts or minimum 5
        lines.append("TRANSPORT")
        lines.append(f"    -cells    {cells}")
        lines.append(f"    -shifts   {conditioning_shifts}")
        lines.append(f"    -lengths  {cell_length_m}")
        lines.append(f"    -dispersivities {cells}*0.002")
        lines.append(f"    -porosities {porosity}")
        lines.append("    -flow_direction forward")
        lines.append("    -boundary_conditions flux flux")
        lines.append(f"    -stagnant 1 {alpha} {porosity * mobile_fraction} {porosity * (1 - mobile_fraction)}")
        lines.append(f"    -print_frequency {max(1, cells//10)}")
        lines.append(f"    -punch_frequency {max(1, cells//10)}")
        lines.append(f"    -punch_cells {cells}")
        lines.append("")

        # Save conditioned state
        lines.append(f"SAVE solution 1-{2*cells}")
        lines.append(f"SAVE exchange 1-{2*cells}")
        lines.append("")
        lines.append("END")
        lines.append("")

        # Stage 3: Production transport using low-Na feed
        lines.append("# Stage 3: Production transport with low-Na feed")

        lines.append("SOLUTION 0  # Production feed (low Na)")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {_get(water_composition, 'temperature_celsius', default=25)}")
        lines.append(f"    pH        {_get(water_composition, 'pH', 'ph', default=7.8)}")
        lines.append(f"    Ca        {_get(water_composition, 'ca_mg_l', default=0)}")
        lines.append(f"    Mg        {_get(water_composition, 'mg_mg_l', default=0)}")
        lines.append(f"    Na        {_get(water_composition, 'na_mg_l', 'Na_1+', 'Na_+', default=0)}")
        lines.append(f"    K         {_get(water_composition, 'k_mg_l', default=0)}")
        lines.append(f"    Cl        {_get(water_composition, 'cl_mg_l', 'Cl_1-', 'Cl_-', default=0)}")
        lines.append(f"    C(4)      {_get(water_composition, 'hco3_mg_l', 'HCO3_1-', 'HCO3_-', default=0)} as HCO3")
        lines.append(f"    S(6)      {_get(water_composition, 'so4_mg_l', 'SO4_2-', default=0)} as SO4")
        lines.append("")

        # Load conditioned state
        lines.append(f"USE solution 1-{2*cells}")
        lines.append(f"USE exchange 1-{2*cells}")
        lines.append("")

        # DUMP for debugging initial state (contiguous numbering)
        lines.append("DUMP")
        lines.append(f"    -solution 1-{2*cells}")
        lines.append(f"    -exchange 1-{2*cells}")
        lines.append("")

        # Production transport with stagnant zones
        lines.append("TRANSPORT")
        lines.append(f"    -cells    {cells}")
        lines.append(f"    -shifts   {shifts}")
        lines.append(f"    -lengths  {cell_length_m}")
        lines.append(f"    -dispersivities {cells}*0.002")
        lines.append(f"    -porosities {porosity}")
        lines.append("    -flow_direction forward")
        lines.append("    -boundary_conditions flux flux")
        lines.append(f"    -stagnant 1 {alpha} {porosity * mobile_fraction} {porosity * (1 - mobile_fraction)}")
        lines.append(f"    -print_frequency {cells}")
        lines.append(f"    -punch_frequency {cells}")
        lines.append(f"    -punch_cells {cells}")
        lines.append("")

    # CO2 equilibrium for pH buffering (small finite amount)
    if resin_form == 'H':
        pass  # already added above
    else:
        pass  # Na-form does not use CO2 buffer in this template

    # Selected output
    lines.append("SELECTED_OUTPUT 1")
    lines.append("    -file transport.sel")
    lines.append("    -reset false")
    lines.append("    -solution true")
    lines.append("    -time true")
    lines.append("    -step true")
    lines.append("    -pH true")
    lines.append("    -alkalinity true")
    lines.append("    -totals Ca Mg Na K Cl C(4) S(6)")
    lines.append("    -molalities H+ OH- CO2 HCO3- CO3-2")
    lines.append("    -saturation_indices Calcite Aragonite Dolomite")
    lines.append("")

    # User punch for breakthrough curves
    lines.append("USER_PUNCH 1")
    lines.append("    -headings BV pH Ca_mg/L Mg_mg/L Hardness_mg/L Alk_mg/L CO2_mol/L Ca_Removal_%")
    lines.append("    -start")
    lines.append("    10 REM Calculate bed volumes")
    lines.append(f"    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}")
    lines.append("    30 IF (STEP_NO < 0) THEN GOTO 500  # Skip initial equilibration")
    lines.append("    40 PUNCH BV")
    lines.append("    50 PUNCH -LA(\"H+\")")
    lines.append("")
    lines.append("    60 REM Calculate concentrations in mg/L")
    lines.append("    70 ca_mg = TOT(\"Ca\") * 40.078 * 1000")
    lines.append("    80 mg_mg = TOT(\"Mg\") * 24.305 * 1000")
    lines.append("    90 PUNCH ca_mg, mg_mg")
    lines.append("")
    lines.append("    100 REM Calculate hardness as CaCO3")
    lines.append("    110 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1")
    lines.append("    120 PUNCH hardness_caco3")
    lines.append("")
    lines.append("    130 REM Calculate alkalinity and CO2")
    lines.append("    140 alk_mg = TOT(\"C(4)\") * 61.017 * 1000  # as HCO3")
    lines.append("    150 co2_mol = MOL(\"CO2\")")
    lines.append("    160 PUNCH alk_mg, co2_mol")
    lines.append("")
    lines.append("    170 REM Calculate Ca removal")
    lines.append(f"    180 feed_ca = {water_composition.get('ca_mg_l', 0)}")
    lines.append("    190 IF (feed_ca > 0) THEN ca_removal = (1 - ca_mg/feed_ca) * 100 ELSE ca_removal = 0")
    lines.append("    200 IF (ca_removal < 0) THEN ca_removal = 0")
    lines.append("    210 PUNCH ca_removal")
    lines.append("")
    lines.append("    500 REM end")
    lines.append("    -end")
    lines.append("")
    lines.append("END")

    return "\n".join(lines)
