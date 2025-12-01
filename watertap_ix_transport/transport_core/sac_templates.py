"""
SAC PHREEQC Template Module with Dual-Domain Transport

Provides PHREEQC input templates for Strong Acid Cation (SAC) exchange resins.
Supports dual-domain EXCHANGE model for mass transfer limitations.

Dual-domain transport provides:
- Mass transfer limitations between mobile/immobile zones
- More realistic breakthrough curves (gradual S-curve)
- Better handling of high-capacity industrial systems

Key Parameters:
- mobile_fraction: Fraction of resin in mobile zone (default 10% for gel resins)
- alpha: Mass transfer coefficient 1/s (default 5e-6 for gel resins)

SAC Exchange Reactions (standard selectivity):
  2X- + Ca+2 = CaX2    log_k = 0.416  (Ca/Na)
  2X- + Mg+2 = MgX2    log_k = 0.221  (Mg/Na)
  X- + Na+ = NaX       log_k = 0.0    (reference)
  X- + K+ = KX         log_k = 0.12   (K/Na)

References:
- Helfferich (1962) "Ion Exchange"
- PHREEQC manual, section 5.5 (Stagnant zones)
"""

import json
import logging
from typing import Dict, Any, Optional
import numpy as np
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.core_config import CONFIG


def _get(dct: Dict[str, Any], *keys, default: Any = 0.0):
    """Extract value from dict using multiple possible keys (tries in order)."""
    for k in keys:
        if k in dct and dct[k] is not None:
            return dct[k]
    return default


# Cache for selectivity data
_selectivity_cache: Dict[str, Any] = {}


def _load_sac_selectivity() -> Dict[str, Any]:
    """
    Load SAC selectivity coefficients from resin_selectivity.json.

    Returns:
        Dict with exchange species and their log_k values
    """
    global _selectivity_cache

    cache_key = "SAC"
    if cache_key in _selectivity_cache:
        return _selectivity_cache[cache_key]

    try:
        db_path = project_root / "databases" / "resin_selectivity.json"
        with open(db_path, 'r') as f:
            data = json.load(f)

        if "SAC" not in data.get("resin_types", {}):
            logger.warning("SAC not found in resin_selectivity.json, using defaults")
            return {
                "Ca_X2": {"log_k": 0.416},
                "Mg_X2": {"log_k": 0.221},
                "Na_X": {"log_k": 0.0},
                "K_X": {"log_k": 0.12},
            }

        selectivity = data["resin_types"]["SAC"]["exchange_species"]
        _selectivity_cache[cache_key] = selectivity
        logger.info(f"Loaded SAC selectivity from JSON: Ca={selectivity.get('Ca_X2', {}).get('log_k')}, "
                   f"Mg={selectivity.get('Mg_X2', {}).get('log_k')}")
        return selectivity

    except Exception as e:
        logger.warning(f"Could not load resin_selectivity.json: {e}, using defaults")
        return {
            "Ca_X2": {"log_k": 0.416},
            "Mg_X2": {"log_k": 0.221},
            "Na_X": {"log_k": 0.0},
            "K_X": {"log_k": 0.12},
        }


def create_sac_dual_domain_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 16,
    max_bv: int = 300,
    database_path: Optional[str] = None,
    mobile_fraction: float = 0.10,
    alpha: float = 5e-6,
    capacity_eq_L: float = 2.0
) -> str:
    """
    Create PHREEQC input with dual-domain transport for SAC.

    Dual-domain provides:
    - Mass transfer limitations between mobile/immobile zones
    - More realistic breakthrough curves (gradual S-curve)
    - Better handling of high-capacity industrial systems

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration (bed_depth_m, diameter_m, bed_volume_L)
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        mobile_fraction: Fraction of resin in mobile zone (default 10%)
        alpha: Mass transfer coefficient 1/s (default 5e-6 for gel resins)
        capacity_eq_L: Resin capacity in eq/L (default 2.0)

    Returns:
        PHREEQC input string
    """
    logger.info("Creating dual-domain SAC PHREEQC input")

    # Database path
    if database_path is None:
        database_path = str(CONFIG.DATABASE_PATH)

    # Extract vessel parameters
    bed_depth_m = vessel_config.get('bed_depth_m', 2.0)
    bed_volume_L = vessel_config.get('bed_volume_L', 1000)
    porosity = vessel_config.get('porosity', 0.4)

    # Extract water composition
    ca_mg_l = _get(water_composition, 'ca_mg_l', 'Ca_2+', default=80)
    mg_mg_l = _get(water_composition, 'mg_mg_l', 'Mg_2+', default=40)
    na_mg_l = _get(water_composition, 'na_mg_l', 'Na_1+', 'Na_+', default=100)
    k_mg_l = _get(water_composition, 'k_mg_l', 'K_1+', 'K_+', default=5)
    cl_mg_l = _get(water_composition, 'cl_mg_l', 'Cl_1-', 'Cl_-', default=0)
    hco3_mg_l = _get(water_composition, 'hco3_mg_l', 'HCO3_1-', 'HCO3_-', default=100)
    so4_mg_l = _get(water_composition, 'so4_mg_l', 'SO4_2-', default=50)
    feed_ph = _get(water_composition, 'pH', 'ph', default=7.8)
    temperature = _get(water_composition, 'temperature_celsius', 'temperature_C', default=25)

    logger.info(f"Feed water: Ca={ca_mg_l}, Mg={mg_mg_l}, Na={na_mg_l}, pH={feed_ph}")

    # Calculate exchange capacity distribution
    wet_resin_volume_L = bed_volume_L * (1 - porosity)
    total_capacity_eq = capacity_eq_L * wet_resin_volume_L

    # Split between mobile and immobile
    mobile_capacity_eq = total_capacity_eq * mobile_fraction
    immobile_capacity_eq = total_capacity_eq * (1 - mobile_fraction)

    # Auto-refine cells for numerical stability
    original_cells = cells
    target_mobile_eq = 10.0   # eq per cell (mobile zone)
    target_immobile_eq = 50.0  # eq per cell (immobile zone)

    cells_needed = max(
        cells,
        int(np.ceil(mobile_capacity_eq / target_mobile_eq)) if mobile_capacity_eq > 0 else cells,
        int(np.ceil(immobile_capacity_eq / target_immobile_eq)) if immobile_capacity_eq > 0 else cells,
    )
    cells_needed = min(cells_needed, 100)  # Cap for TRANSPORT convergence

    if cells_needed != cells:
        logger.info(f"Auto-adjusting cells: {cells} -> {cells_needed}")
        cells = cells_needed

    # Per cell calculations
    mobile_eq_per_cell = mobile_capacity_eq / cells
    immobile_eq_per_cell = immobile_capacity_eq / cells

    # Water per cell
    water_volume_L = bed_volume_L * porosity
    water_per_cell_kg = water_volume_L / cells

    # Shifts
    shifts = int(np.ceil(max_bv))
    max_shifts = 5000
    if shifts > max_shifts:
        logger.warning(f"Capping shifts: {shifts} -> {max_shifts}")
        shifts = max_shifts

    # Cell length
    cell_length_m = bed_depth_m / cells

    logger.info(f"Dual-domain SAC: capacity={capacity_eq_L} eq/L, "
                f"mobile={mobile_fraction*100}%, alpha={alpha}")
    logger.info(f"Mobile: {mobile_eq_per_cell:.2f} eq/cell, "
                f"Immobile: {immobile_eq_per_cell:.2f} eq/cell")

    # Load selectivity coefficients
    selectivity = _load_sac_selectivity()
    ca_log_k = selectivity.get('Ca_X2', {}).get('log_k', 0.416)
    mg_log_k = selectivity.get('Mg_X2', {}).get('log_k', 0.221)
    na_log_k = selectivity.get('Na_X', {}).get('log_k', 0.0)
    k_log_k = selectivity.get('K_X', {}).get('log_k', 0.12)

    # Build PHREEQC input
    lines = []

    # Database
    lines.append(f"DATABASE {database_path}")
    lines.append("")

    # Title
    lines.append("TITLE SAC dual-domain simulation with mass transfer limitations")
    lines.append(f"# Total capacity: {capacity_eq_L} eq/L")
    lines.append(f"# Mobile fraction: {mobile_fraction*100}%")
    lines.append(f"# Mass transfer alpha: {alpha} 1/s")
    lines.append("")

    # Convergence parameters
    lines.append("KNOBS")
    lines.append("    -iterations 400")
    lines.append("    -convergence_tolerance 1e-5")
    lines.append("    -diagonal_scale true")
    lines.append("")

    # Exchange master species (SAC uses standard PHREEQC X/X- convention)
    lines.append("EXCHANGE_MASTER_SPECIES")
    lines.append("    X  X-")
    lines.append("")

    # Exchange species with SAC selectivity
    lines.append("EXCHANGE_SPECIES")
    lines.append("    X- = X-")
    lines.append("        log_k  0.0")
    lines.append(f"    Ca+2 + 2X- = CaX2")
    lines.append(f"        log_k  {ca_log_k}")
    lines.append(f"    Mg+2 + 2X- = MgX2")
    lines.append(f"        log_k  {mg_log_k}")
    lines.append(f"    Na+ + X- = NaX")
    lines.append(f"        log_k  {na_log_k}")
    lines.append(f"    K+ + X- = KX")
    lines.append(f"        log_k  {k_log_k}")
    lines.append("")

    # Two-stage approach: condition exchanger, then run transport

    # Stage 1: Condition exchanger with NaCl solution
    conditioning_na_mg_l = 500.0
    conditioning_cl_mg_l = 500.0

    lines.append("# Stage 1: Condition exchanger with NaCl solution")
    lines.append("SOLUTION 0  # Conditioning solution")
    lines.append("    units     mg/L")
    lines.append(f"    temp      {temperature}")
    lines.append(f"    pH        {feed_ph}")
    lines.append(f"    Na        {conditioning_na_mg_l:.1f}")
    lines.append(f"    Cl        {conditioning_cl_mg_l:.1f}  charge")
    lines.append("")

    # Define exchangers (mobile and immobile)
    lines.append(f"EXCHANGE 1-{cells}  # Mobile sites")
    lines.append(f"    NaX       {mobile_eq_per_cell}")
    lines.append("    -equilibrate with solution 0")
    lines.append("")
    lines.append(f"EXCHANGE {cells+1}-{2*cells}  # Immobile sites")
    lines.append(f"    NaX       {immobile_eq_per_cell}")
    lines.append("    -equilibrate with solution 0")
    lines.append("")

    # Save exchange
    lines.append(f"SAVE exchange 1-{2*cells}")
    lines.append("")
    lines.append("END")
    lines.append("")

    # Stage 2: Production transport with conditioned exchanger
    lines.append("# Stage 2: Production transport with conditioned exchanger")

    # Porewater (initially similar to conditioning for stability)
    initial_na_mg_l = 500.0
    lines.append(f"SOLUTION 1-{cells}  # Mobile porewater")
    lines.append("    units     mg/L")
    lines.append(f"    temp      {temperature}")
    lines.append(f"    pH        {feed_ph}")
    lines.append(f"    Na        {initial_na_mg_l:.1f}")
    lines.append(f"    Cl        {initial_na_mg_l * 1.54:.1f}  charge")
    lines.append(f"    water     {water_per_cell_kg} kg")
    lines.append("")

    # Immobile porewater
    lines.append(f"SOLUTION {cells+1}-{2*cells}  # Immobile porewater")
    lines.append("    units     mg/L")
    lines.append(f"    temp      {temperature}")
    lines.append(f"    pH        {feed_ph}")
    lines.append(f"    Na        {initial_na_mg_l:.1f}")
    lines.append(f"    Cl        {initial_na_mg_l * 1.54:.1f}  charge")
    lines.append(f"    water     {water_per_cell_kg} kg")
    lines.append("")

    # Use saved exchange
    lines.append(f"USE exchange 1-{2*cells}")
    lines.append("")

    # Feed solution (production)
    lines.append("SOLUTION 0  # Production feed (replaces conditioning)")
    lines.append("    units     mg/L")
    lines.append(f"    temp      {temperature}")
    lines.append(f"    pH        {feed_ph}")
    lines.append(f"    Ca        {ca_mg_l}")
    lines.append(f"    Mg        {mg_mg_l}")
    lines.append(f"    Na        {na_mg_l}")
    lines.append(f"    K         {k_mg_l}")
    if hco3_mg_l > 0:
        lines.append(f"    Alkalinity {hco3_mg_l} as HCO3")
    if so4_mg_l > 0:
        lines.append(f"    S(6)      {so4_mg_l} as SO4")
    if cl_mg_l > 0:
        lines.append(f"    Cl        {cl_mg_l}")
    else:
        lines.append("    Cl        1 charge")
    lines.append("")

    # TRANSPORT with dual-domain (stagnant zones)
    lines.append("TRANSPORT")
    lines.append(f"    -cells    {cells}")
    lines.append(f"    -shifts   {shifts}")
    lines.append(f"    -lengths  {cell_length_m}")
    lines.append(f"    -dispersivities {cells}*0.002")
    lines.append(f"    -porosities {porosity}")
    lines.append("    -flow_direction forward")
    lines.append("    -boundary_conditions flux flux")
    # Critical: dual-domain stagnant zones
    lines.append(f"    -stagnant 1 {alpha} {porosity * mobile_fraction} {porosity * (1 - mobile_fraction)}")
    lines.append(f"    -print_frequency {cells}")
    lines.append(f"    -punch_frequency {cells}")
    lines.append(f"    -punch_cells {cells}")
    lines.append("")

    # Selected output
    lines.append("SELECTED_OUTPUT 1")
    lines.append("    -file transport.sel")
    lines.append("    -reset false")
    lines.append("    -step true")
    lines.append("    -totals Ca Mg Na K")
    lines.append("    -molalities CaX2 MgX2 NaX KX")
    lines.append("")

    # User punch for output
    lines.append("USER_PUNCH 1")
    lines.append("    -headings Step BV Ca_mg_L Mg_mg_L Na_mg_L K_mg_L Hardness_CaCO3")
    lines.append("    -start")
    lines.append("    10 PUNCH STEP_NO")
    lines.append("    20 BV = STEP_NO")
    lines.append("    30 PUNCH BV")
    lines.append("    # Convert mol/kg to mg/L")
    lines.append("    40 ca_mg = TOT(\"Ca\") * 40.078 * 1000")
    lines.append("    50 mg_mg = TOT(\"Mg\") * 24.305 * 1000")
    lines.append("    60 na_mg = TOT(\"Na\") * 22.990 * 1000")
    lines.append("    70 k_mg = TOT(\"K\") * 39.098 * 1000")
    lines.append("    80 PUNCH ca_mg")
    lines.append("    90 PUNCH mg_mg")
    lines.append("    100 PUNCH na_mg")
    lines.append("    110 PUNCH k_mg")
    lines.append("    # Calculate hardness as CaCO3")
    lines.append("    120 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1")
    lines.append("    130 PUNCH hardness_caco3")
    lines.append("    -end")
    lines.append("")

    lines.append("END")
    lines.append("")

    return "\n".join(lines)


def create_sac_single_domain_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 16,
    max_bv: int = 300,
    database_path: Optional[str] = None,
    capacity_eq_L: float = 2.0
) -> str:
    """
    Create PHREEQC input with single-domain transport for SAC (legacy mode).

    This is the traditional single-domain approach without mass transfer
    limitations. Retained for backward compatibility.

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration
        cells: Number of cells
        max_bv: Maximum bed volumes
        database_path: Database path
        capacity_eq_L: Resin capacity

    Returns:
        PHREEQC input string
    """
    logger.info("Creating single-domain SAC PHREEQC input (legacy mode)")

    # Use dual-domain with mobile_fraction=1.0 (effectively single domain)
    return create_sac_dual_domain_input(
        water_composition=water_composition,
        vessel_config=vessel_config,
        cells=cells,
        max_bv=max_bv,
        database_path=database_path,
        mobile_fraction=1.0,  # No immobile zone
        alpha=0.0,  # No mass transfer
        capacity_eq_L=capacity_eq_L
    )
