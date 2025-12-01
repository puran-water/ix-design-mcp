"""
WAC PHREEQC Template Module

Provides PHREEQC input templates for Weak Acid Cation (WAC) exchange resins.
Uses dual-domain EXCHANGE model with pH-dependent capacity.

Architecture Decisions:
- Na-form: Uses X/X- master species (standard PHREEQC exchange model)
- H-form: Uses X/X- master species with HX protonation reaction
  * Reduced effective pKa (2.5) for PHREEQC numerical stability
  * True pKa (4.8) would cause 63,000x selectivity and convergence failures
  * Full Henderson-Hasselbalch correction applied via empirical_leakage_overlay.py
  * Two-layer approach: PHREEQC for timing, empirical for accurate capacity

H-form Exchange Reactions (effective pKa = 2.5):
  X- = X-                  log_k =  0.0  (reference)
  H+ + X- = HX             log_k =  2.5  (reduced from true pKa 4.8)
  2X- + Ca+2 = CaX2        log_k =  1.3
  2X- + Mg+2 = MgX2        log_k =  1.1
  X- + Na+ = NaX           log_k =  0.0

Previous approaches (deprecated):
- SURFACE model: Failed at industrial scale due to massive H+ release (Codex 019abbed)
- XH master species: PHREEQC error "Element name should include only one element"
- X- master with log_k=4.8: Extreme selectivity caused Newton-Raphson failures
- Y/YH master species: Equilibration converted all sites to NaY despite acidic conditioning
"""

import json
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


# Small helper to tolerate legacy and new field names (pH vs ph, Cl_- vs cl_mg_l, etc.)
def _get(dct: Dict[str, Any], *keys, default: Any = 0.0):
    """Extract value from dict using multiple possible keys (tries in order)."""
    for k in keys:
        if k in dct and dct[k] is not None:
            return dct[k]
    return default


# Cache for selectivity data (loaded once)
_selectivity_cache: Dict[str, Any] = {}


def _load_wac_selectivity(resin_form: str = 'Na') -> Dict[str, Any]:
    """
    Load WAC selectivity coefficients from resin_selectivity.json.

    DRY Principle: Single source of truth for log_k values.

    Args:
        resin_form: 'Na' or 'H' form

    Returns:
        Dict with exchange species and their log_k values
    """
    global _selectivity_cache

    cache_key = f"WAC_{resin_form}"
    if cache_key in _selectivity_cache:
        return _selectivity_cache[cache_key]

    try:
        db_path = project_root / "databases" / "resin_selectivity.json"
        with open(db_path, 'r') as f:
            data = json.load(f)

        resin_key = f"WAC_{resin_form}"
        if resin_key not in data.get("resin_types", {}):
            logger.warning(f"Resin type {resin_key} not found in resin_selectivity.json, using defaults")
            # Fallback defaults (should match JSON)
            return {
                "Ca_X2": {"log_k": 1.3},
                "Mg_X2": {"log_k": 1.1},
                "Na_X": {"log_k": 0.0},
                "K_X": {"log_k": 0.25},
            }

        selectivity = data["resin_types"][resin_key]["exchange_species"]
        _selectivity_cache[cache_key] = selectivity
        logger.info(f"Loaded {resin_key} selectivity from JSON: Ca={selectivity.get('Ca_X2', {}).get('log_k')}, "
                   f"Mg={selectivity.get('Mg_X2', {}).get('log_k')}")
        return selectivity

    except Exception as e:
        logger.error(f"Failed to load selectivity from JSON: {e}")
        # Fallback defaults
        return {
            "Ca_X2": {"log_k": 1.3},
            "Mg_X2": {"log_k": 1.1},
            "Na_X": {"log_k": 0.0},
            "K_X": {"log_k": 0.25},
        }


def create_wac_na_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 16,  # Increased from 10 to improve TRANSPORT stability (Codex 019aa7b7)
    max_bv: int = 300,
    database_path: Optional[str] = None,
    enable_enhancements: bool = True,
    capacity_factor: float = 1.0,
    use_dual_domain: bool = True  # Always True - SURFACE model deprecated
) -> str:
    """
    Create PHREEQC input for WAC Na-form simulation.

    Uses dual-domain EXCHANGE model for numerical stability at industrial scale.

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        use_dual_domain: Always True (SURFACE model deprecated)

    Returns:
        PHREEQC input string
    """
    logger.info("Using dual-domain EXCHANGE model for WAC_Na")
    logger.info(f"[DEBUG] water_composition keys: {list(water_composition.keys())}")
    logger.info(f"[DEBUG] ca_mg_l={water_composition.get('ca_mg_l')}, mg_mg_l={water_composition.get('mg_mg_l')}")

    return _create_wac_dual_domain_input(
        water_composition=water_composition,
        vessel_config=vessel_config,
        cells=cells,
        max_bv=max_bv,
        database_path=database_path,
        capacity_factor=capacity_factor,
        resin_form='Na'
    )


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

    # Load selectivity coefficients from JSON (DRY principle)
    selectivity = _load_wac_selectivity(resin_form)
    ca_log_k = selectivity.get("Ca_X2", {}).get("log_k", 1.3)
    mg_log_k = selectivity.get("Mg_X2", {}).get("log_k", 1.1)
    na_log_k = selectivity.get("Na_X", {}).get("log_k", 0.0)

    # Extract parameters
    bed_volume_L = vessel_config['bed_volume_L']
    bed_depth_m = vessel_config.get('bed_depth_m', 1.5)

    # Capacity based on resin form
    # -------------------------------------------------------------------------
    # PHREEQC NUMERICAL STABILITY NOTE:
    # Both forms use working capacity (1.8 eq/L) for PHREEQC simulations.
    # H-form theoretical capacity (4.7 eq/L) creates 2.6x higher per-cell
    # exchanger load, causing Newton-Raphson convergence failures during TRANSPORT.
    #
    # The higher H-form capacity effects are modeled via empirical_leakage_overlay.py
    # which applies pH-dependent Henderson-Hasselbalch corrections.
    # -------------------------------------------------------------------------
    base_capacity = CONFIG.WAC_NA_WORKING_CAPACITY  # Use working capacity for PHREEQC stability

    capacity_eq_L = base_capacity * capacity_factor

    # Dual-domain parameters
    # -------------------------------------------------------------------------
    # TWO-LAYER ARCHITECTURE NOTE:
    # Layer 1 (PHREEQC): Thermodynamic equilibrium for breakthrough timing
    # Layer 2 (Empirical): Realistic leakage overlay (see empirical_leakage_overlay.py)
    #
    # PHREEQC's thermodynamic equilibrium correctly predicts near-zero leakage.
    # Real leakage (0.5-5 mg/L) comes from incomplete regeneration, TDS effects,
    # and kinetic limitations - modeled by the empirical overlay layer.
    #
    # These dual-domain parameters control TRANSPORT mass transfer, NOT leakage.
    # mobile_fraction: ~10% is typical for gel-type resins (particle core is immobile)
    # alpha: mass transfer coefficient (1/s) controls equilibration speed
    # -------------------------------------------------------------------------
    mobile_fraction = 0.10  # Standard gel-type resin: 10% mobile (typical value)
    porosity = 0.4

    # Calculate exchange capacity distribution
    wet_resin_volume_L = bed_volume_L * (1 - porosity)
    total_capacity_eq = capacity_eq_L * wet_resin_volume_L

    # Split between mobile and immobile
    mobile_capacity_eq = total_capacity_eq * mobile_fraction
    immobile_capacity_eq = total_capacity_eq * (1 - mobile_fraction)

    # Save original cells for shift scaling
    original_cells = cells

    # Auto-refine cells to limit per-cell capacity for PHREEQC numerical stability
    # -------------------------------------------------------------------------
    # PHREEQC EXCHANGE model can fail if eq/cell is too high. However, too many
    # cells (>100) causes TRANSPORT convergence issues due to system stiffness.
    #
    # Balance: Moderate eq/cell with reasonable cell count
    # Using same thresholds as SAC/WAC_Na for consistency
    # -------------------------------------------------------------------------
    target_mobile_eq = 10.0   # eq per cell (mobile zone) - balanced for stability
    target_immobile_eq = 50.0  # eq per cell (immobile zone) - 5x mobile

    cells_needed = max(
        cells,
        int(np.ceil(mobile_capacity_eq / target_mobile_eq)) if mobile_capacity_eq > 0 else cells,
        int(np.ceil(immobile_capacity_eq / target_immobile_eq)) if immobile_capacity_eq > 0 else cells,
    )

    # Cap at reasonable maximum to avoid TRANSPORT convergence issues
    # Too many cells (>100) creates stiff systems that fail during TRANSPORT
    cells_needed = min(cells_needed, 100)

    if cells_needed != cells:
        logger.info(f"Auto-adjusting cells for {resin_form}-form: {cells} -> {cells_needed} to limit per-cell capacity")
        cells = cells_needed

    # Per cell calculations
    mobile_eq_per_cell = mobile_capacity_eq / cells
    immobile_eq_per_cell = immobile_capacity_eq / cells

    # Water per cell
    water_volume_L = bed_volume_L * porosity
    water_per_cell_kg = water_volume_L / cells

    # Mass transfer coefficient - controls equilibration between zones
    # Standard value for gel-type resins (particle diffusion limited)
    # Leakage prediction is handled by empirical_leakage_overlay.py, NOT alpha
    alpha = 5e-6  # 1/s - standard for particle diffusion (Helfferich 1962)

    # Calculate shifts for max_bv
    # PHREEQC -shifts represents pore volumes (bed volumes), NOT cell movements
    # Each shift = one pore volume of water through the entire column
    # Increasing cells provides finer spatial discretization, not more throughput
    #
    # CRITICAL FIX (daed169): shifts = max_bv, independent of cell count
    # Old buggy formula (shifts = max_bv * cells / original_cells) caused
    # computational explosion when cells were auto-scaled from 8 → 100
    shifts = int(np.ceil(max_bv))

    # Cap shifts at reasonable maximum to prevent extremely long runtimes
    # 5,000 shifts takes ~2-5 minutes in PHREEQC; 50,000 is impractical
    # Empirical overlay will provide breakthrough prediction regardless
    max_shifts = 5000  # Reduced from 50000 for practical runtime
    if shifts > max_shifts:
        logger.warning(f"Capping shifts: {shifts} -> {max_shifts} (max_bv capped to {max_shifts})")
        shifts = max_shifts

    logger.info(f"Shifts set: {shifts} (independent of cell count, cells={cells})")

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
    lines.append("")

    # Title
    lines.append(f"TITLE WAC {resin_form}-form dual-domain simulation")
    lines.append(f"# Prevents pH crash through mass transfer limitations")
    lines.append(f"# Total capacity: {capacity_eq_L} eq/L")
    lines.append(f"# Mobile fraction: {mobile_fraction*100}%")
    lines.append("")

    # Convergence parameters
    # NOTE: -step_size 1 causes convergence failure on initial solution speciation
    # Use default step size (larger values) for initial speciation, smaller for transport
    # Convergence parameters - same for both forms for consistency
    # -------------------------------------------------------------------------
    # PHREEQC NUMERICAL STABILITY NOTE:
    # Using 1e-5 tolerance for both H-form and Na-form.
    # Tighter tolerance (1e-8) causes convergence failures with EXCHANGE model.
    # -------------------------------------------------------------------------
    lines.append("KNOBS")
    lines.append("    -iterations 400")  # Increased for difficult convergence
    lines.append("    -convergence_tolerance 1e-5")  # Softer tolerance for EXCHANGE stability
    lines.append("    -diagonal_scale true")  # Improves conditioning for stiff problems
    lines.append("")

    # Define exchange master species and reactions (FORM-SPECIFIC)
    # -------------------------------------------------------------------------
    # Both forms use X/X- master species for PHREEQC compatibility.
    #
    # H-form: Adds HX protonation reaction with reduced effective pKa (2.5)
    #   - True pKa (4.8) causes 63,000x selectivity and convergence failures
    #   - Reduced pKa enables H+ release while maintaining numerical stability
    #   - Full Henderson-Hasselbalch correction applied via empirical overlay
    #   - Exchanger initialized as fully HX-loaded (strong acid placeholder) to avoid under-acidification
    #
    # Na-form: Standard exchange model (no HX reaction)
    #   - Exchanger initialized as NaX
    # -------------------------------------------------------------------------

    if resin_form == 'H':
        # H-form: X/X- master with HX protonation reaction (reduced pKa for stability)
        # True pKa = 4.8 causes 63,000x selectivity and convergence failures
        # Use reduced effective pKa = 2.5 for PHREEQC stability
        # Full Henderson-Hasselbalch correction applied via empirical_leakage_overlay.py
        effective_pka = 2.5  # Reduced from 4.8 for numerical stability

        lines.append("EXCHANGE_MASTER_SPECIES")
        lines.append("    X  X-")
        lines.append("")

        lines.append("EXCHANGE_SPECIES")
        lines.append("    # Reference species")
        lines.append("    X- = X-")
        lines.append("        log_k  0.0")
        lines.append("")
        lines.append("    # H-form protonation (reduced pKa for stability)")
        lines.append("    H+ + X- = HX")
        lines.append(f"        log_k  {effective_pka}  # Effective pKa (true=4.8, reduced for stability)")
        lines.append("        -gamma 9.0 0.0")
        lines.append("")
        lines.append("    # Calcium exchange")
        lines.append("    2X- + Ca+2 = CaX2")
        lines.append(f"        log_k  {ca_log_k}  # From resin_selectivity.json")
        lines.append("")
        lines.append("    # Magnesium exchange")
        lines.append("    2X- + Mg+2 = MgX2")
        lines.append(f"        log_k  {mg_log_k}  # From resin_selectivity.json")
        lines.append("")
        lines.append("    # Sodium exchange")
        lines.append("    X- + Na+ = NaX")
        lines.append(f"        log_k  {na_log_k}  # Reference")
        lines.append("")
    else:
        # Na-form: X/X- master species (standard exchange model)
        lines.append("EXCHANGE_MASTER_SPECIES")
        lines.append("    X  X-")
        lines.append("")

        lines.append("EXCHANGE_SPECIES")
        lines.append("    # Reference species")
        lines.append("    X- = X-")
        lines.append("        log_k  0.0")
        lines.append("")
        lines.append("    # Calcium exchange")
        lines.append("    2X- + Ca+2 = CaX2")
        lines.append(f"        log_k  {ca_log_k}  # From resin_selectivity.json")
        lines.append("")
        lines.append("    # Magnesium exchange")
        lines.append("    2X- + Mg+2 = MgX2")
        lines.append(f"        log_k  {mg_log_k}  # From resin_selectivity.json")
        lines.append("")
        lines.append("    # Sodium exchange")
        lines.append("    X- + Na+ = NaX")
        lines.append(f"        log_k  {na_log_k}  # Reference")
        lines.append("")

    # Calculate immobile water mass (used by both H-form and Na-form)
    immobile_water_kg = water_per_cell_kg * (1 - porosity) / porosity

    if resin_form == 'H':
        # ------------------------------------------------------------------
        # H-form: Two-stage initialization (same pattern as Na-form)
        #
        # KEY INSIGHT: At industrial scale, exchanger capacity (~13 eq/cell)
        # vastly exceeds porewater ionic content (~4 mM Na). Without
        # pre-equilibration, PHREEQC fails during TRANSPORT initialization.
        #
        # Stage 1: Pre-load exchanger as HX (strong-acid placeholder, no Na)
        # Stage 2: USE saved exchange with production porewater
        # ------------------------------------------------------------------

        feed_ph = _get(water_composition, 'pH', 'ph', default=7.8)
        prod_temp = _get(water_composition, 'temperature_celsius', default=25)
        prod_ca = _get(water_composition, 'ca_mg_l', default=0)
        prod_mg = _get(water_composition, 'mg_mg_l', default=0)
        prod_na = _get(water_composition, 'na_mg_l', 'Na_1+', 'Na_+', default=0)
        prod_k = _get(water_composition, 'k_mg_l', default=0)
        prod_cl = _get(water_composition, 'cl_mg_l', 'Cl_1-', 'Cl_-', default=0)
        prod_hco3 = _get(water_composition, 'hco3_mg_l', 'HCO3_1-', 'HCO3_-', default=0)
        prod_so4 = _get(water_composition, 'so4_mg_l', 'SO4_2-', default=0)

        logger.info(f"[DEBUG] H-form production feed: Ca={prod_ca}, Mg={prod_mg}, Na={prod_na}, HCO3={prod_hco3}")
        logger.info(f"H-form two-stage init: direct HX load -> production porewater")

        # ------------------------------------------------------------------
        # STAGE 1: Explicit HX load with strong-acid placeholder
        # Uses HX (protonated sites) for H-form behavior without Na seeding
        # Reduced effective pKa (2.5) still used for PHREEQC stability
        # ------------------------------------------------------------------
        conditioning_ph = 0.5  # Far below effective pKa (2.5) to keep >99% HX
        conditioning_cl_mg_l = 11200.0  # ~0.316 M Cl- to balance pH 0.5 as HCl

        logger.info("H-form conditioning: force 100% HX (no Na seeding, strong acid placeholder)")

        lines.append("# Stage 1: Force exchanger to fully protonated HX (no Na seeding)")
        lines.append("# Explicit HX load avoids pH-based under-acidification during initialization")
        lines.append("SOLUTION 0  # Strong-acid placeholder to keep HX protonated")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {conditioning_ph}  # << effective pKa to keep HX ~100%")
        lines.append(f"    Cl        {conditioning_cl_mg_l:.1f}  charge  # HCl only, no Na+")
        lines.append("")

        # Define exchangers as HX (protonated H-form sites)
        lines.append(f"EXCHANGE 1-{cells}  # Mobile sites")
        lines.append(f"    HX        {mobile_eq_per_cell}")
        lines.append("    -equilibrate with solution 0  # Placeholder equilibrium only; HX defined explicitly")
        lines.append("")
        lines.append(f"EXCHANGE {cells+1}-{2*cells}  # Immobile sites")
        lines.append(f"    HX        {immobile_eq_per_cell}")
        lines.append("    -equilibrate with solution 0  # Placeholder equilibrium only; HX defined explicitly")
        lines.append("")

        # Save ONLY the exchange (not the conditioning solution)
        lines.append(f"SAVE exchange 1-{2*cells}")
        lines.append("")
        lines.append("END")
        lines.append("")

        # ------------------------------------------------------------------
        # STAGE 2: Define production porewater and run TRANSPORT
        # ------------------------------------------------------------------
        lines.append("# Stage 2: Production transport with conditioned exchanger")

        # Define actual porewater (moderate Na for stability)
        initial_na_mg_l = 500.0
        lines.append(f"SOLUTION 1-{cells}  # Mobile porewater")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {initial_na_mg_l}")
        lines.append(f"    Cl        {initial_na_mg_l} charge")
        lines.append(f"    water     {water_per_cell_kg} kg")
        lines.append("")

        lines.append(f"SOLUTION {cells+1}-{2*cells}  # Immobile porewater")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {initial_na_mg_l}")
        lines.append(f"    Cl        {initial_na_mg_l} charge")
        lines.append(f"    water     {immobile_water_kg} kg")
        lines.append("")

        # USE the pre-conditioned exchange (H-form with HX sites)
        lines.append(f"USE exchange 1-{2*cells}")
        lines.append("")

        # Feed solution for transport
        lines.append("SOLUTION 0  # Production feed")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Ca        {prod_ca}")
        lines.append(f"    Mg        {prod_mg}")
        lines.append(f"    Na        {prod_na}")
        lines.append(f"    K         {prod_k}")
        lines.append(f"    Cl        {prod_cl} charge")
        if prod_hco3 > 0:
            lines.append(f"    C(4)      {prod_hco3} as HCO3")
        if prod_so4 > 0:
            lines.append(f"    S(6)      {prod_so4} as SO4")
        lines.append("")

        logger.info(f"H-form production shifts: {shifts}")

        # Main transport block
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

    else:
        # ------------------------------------------------------------------
        # Na-form: two-stage approach to allow Na-saturated resin with
        # realistic low-Na pore water.
        # Stage 1: Pre-saturate exchanger with a brine, SAVE exchange.
        # Stage 2: USE saved exchange with low-Na porewater and run TRANSPORT.
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # Na-form: Simple direct initialization approach
        #
        # KEY INSIGHT: We define NaX directly on the exchanger WITHOUT
        # equilibration. This avoids the need for concentrated brine solutions
        # that exceed PHREEQC's activity model validity (~0.5M ionic strength).
        #
        # The porewater is set to match production feed chemistry, so there's
        # no gradient shock when production begins.
        # ------------------------------------------------------------------
        feed_ph = _get(water_composition, 'pH', 'ph', default=7.8)
        prod_temp = _get(water_composition, 'temperature_celsius', default=25)
        prod_ca = _get(water_composition, 'ca_mg_l', default=0)
        prod_mg = _get(water_composition, 'mg_mg_l', default=0)
        prod_na = _get(water_composition, 'na_mg_l', 'Na_1+', 'Na_+', default=0)
        prod_k = _get(water_composition, 'k_mg_l', default=0)
        prod_cl = _get(water_composition, 'cl_mg_l', 'Cl_1-', 'Cl_-', default=0)
        prod_hco3 = _get(water_composition, 'hco3_mg_l', 'HCO3_1-', 'HCO3_-', default=0)
        prod_so4 = _get(water_composition, 'so4_mg_l', 'SO4_2-', default=0)

        # Debug: log production feed values
        logger.info(f"[DEBUG] Production feed: Ca={prod_ca}, Mg={prod_mg}, Na={prod_na}, HCO3={prod_hco3}")
        logger.info(f"Na-form two-stage init: conditioning brine -> production porewater")

        # ------------------------------------------------------------------
        # STAGE 1: Condition exchanger with moderate NaCl solution
        #
        # KEY INSIGHT: We equilibrate EXCHANGE with a separate "conditioning"
        # solution (solution 0), then SAVE only the exchange. This prevents
        # auto-equilibration with the production porewater.
        #
        # Using -equilibrate 0 explicitly tells PHREEQC to equilibrate with
        # solution 0, not with solutions 1-N.
        # ------------------------------------------------------------------

        # Use dilute NaCl solution for conditioning - PHREEQC equilibrates exchanger
        # even with minimal solution Na, since exchange is defined directly
        # Using 500 mg/L matches the porewater and avoids speciation issues
        conditioning_na_mg_l = 500.0
        conditioning_cl_mg_l = 500.0  # Use charge balance

        logger.info(f"Na-form conditioning: {conditioning_na_mg_l:.0f} mg/L Na (dilute)")

        lines.append("# Stage 1: Condition exchanger with dilute NaCl solution")
        lines.append("# Exchanger is defined directly as NaX, solution just provides aqueous phase")
        lines.append("SOLUTION 0  # Conditioning solution (dilute)")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {conditioning_na_mg_l:.1f}")
        lines.append(f"    Cl        {conditioning_cl_mg_l:.1f}  charge")
        lines.append("")

        # Define exchangers and equilibrate with conditioning solution 0
        lines.append(f"EXCHANGE 1-{cells}  # Mobile sites")
        lines.append(f"    NaX       {mobile_eq_per_cell}")
        lines.append("    -equilibrate with solution 0")
        lines.append("")
        lines.append(f"EXCHANGE {cells+1}-{2*cells}  # Immobile sites")
        lines.append(f"    NaX       {immobile_eq_per_cell}")
        lines.append("    -equilibrate with solution 0")
        lines.append("")

        # Save ONLY the exchange (not the conditioning solution)
        lines.append(f"SAVE exchange 1-{2*cells}")
        lines.append("")
        lines.append("END")
        lines.append("")

        # ------------------------------------------------------------------
        # STAGE 2: Define production porewater and run TRANSPORT
        #
        # The saved exchange is in Na-form. When we USE it with new solutions,
        # it's already equilibrated and won't auto-equilibrate again.
        # ------------------------------------------------------------------
        lines.append("# Stage 2: Production transport with conditioned exchanger")

        # Define actual porewater (dilute, matching feed chemistry approximately)
        initial_na_mg_l = 500.0  # Moderate Na for stability
        lines.append(f"SOLUTION 1-{cells}  # Mobile porewater")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {initial_na_mg_l}")
        lines.append(f"    Cl        {initial_na_mg_l} charge")
        lines.append(f"    water     {water_per_cell_kg} kg")
        lines.append("")

        lines.append(f"SOLUTION {cells+1}-{2*cells}  # Immobile porewater")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Na        {initial_na_mg_l}")
        lines.append(f"    Cl        {initial_na_mg_l} charge")
        lines.append(f"    water     {immobile_water_kg} kg")
        lines.append("")

        # USE the pre-conditioned exchange (already in Na-form)
        lines.append(f"USE exchange 1-{2*cells}")
        lines.append("")

        # Feed solution for transport
        lines.append("SOLUTION 0  # Production feed")
        lines.append("    units     mg/L")
        lines.append(f"    temp      {prod_temp}")
        lines.append(f"    pH        {feed_ph}")
        lines.append(f"    Ca        {prod_ca}")
        lines.append(f"    Mg        {prod_mg}")
        lines.append(f"    Na        {prod_na}")
        lines.append(f"    K         {prod_k}")
        lines.append(f"    Cl        {prod_cl} charge")  # Balance charge on Cl
        if prod_hco3 > 0:
            lines.append(f"    C(4)      {prod_hco3} as HCO3")
        if prod_so4 > 0:
            lines.append(f"    S(6)      {prod_so4} as SO4")
        lines.append("")

        logger.info(f"Na-form production shifts: {shifts}")

        # Main transport block
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
    lines.append("    -headings BV pH Ca_mg/L Mg_mg/L Hardness_mg/L Alk_CaCO3_mg/L CO2_mol/L Ca_Removal_%")
    lines.append("    -start")
    lines.append("    10 REM Calculate bed volumes")
    lines.append("    20 BV = STEP_NO  # Each shift represents one pore volume at the inlet")
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
    lines.append("    135 REM ALK returns total alkalinity in eq/kgw (decreases when HCO3- -> CO2)")
    lines.append("    140 alk_caco3 = ALK * 50000  # eq/kgw to mg/L as CaCO3")
    lines.append("    150 co2_mol = MOL(\"CO2\")")
    lines.append("    160 PUNCH alk_caco3, co2_mol")
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
