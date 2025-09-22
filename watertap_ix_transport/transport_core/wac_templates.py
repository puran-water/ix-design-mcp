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


def create_wac_na_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 10,
    max_bv: int = 300,
    database_path: Optional[str] = None,
    enable_enhancements: bool = True,
    capacity_factor: float = 1.0
) -> str:
    """
    Create PHREEQC input for WAC Na-form simulation.

    Uses SURFACE complexation model with acid-base chemistry for pH-dependent capacity.

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database

    Returns:
        PHREEQC input string
    """
    # Use SURFACE complexation model for scientifically correct WAC chemistry
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
        database_path=database_path
    )

    return phreeqc_input


def create_wac_h_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 10,
    max_bv: int = 300,
    database_path: Optional[str] = None,
    enable_enhancements: bool = True,
    capacity_factor: float = 1.0
) -> str:
    """
    Create PHREEQC input for WAC H-form simulation.

    Uses SURFACE complexation model with acid-base chemistry.
    Models alkalinity removal through proton release from RCOOH groups.

    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database

    Returns:
        PHREEQC input string
    """
    # Use SURFACE complexation model for scientifically correct WAC chemistry
    if not SURFACE_BUILDER_AVAILABLE:
        raise ImportError("WAC SURFACE builder required for WAC simulations")

    # Get database path
    if database_path is None:
        database_path = str(CONFIG.get_phreeqc_database())

    # Extract parameters
    bed_volume_L = vessel_config['bed_volume_L']
    bed_depth_m = vessel_config.get('bed_depth_m', 1.5)
    flow_rate_m3_hr = water_composition.get('flow_m3_hr', 0.1)

    # WAC H-form capacity
    capacity_eq_L = CONFIG.WAC_H_TOTAL_CAPACITY * capacity_factor

    logger.info(f"Creating WAC H-form SURFACE model: capacity={capacity_eq_L} eq/L, pKa=4.5")

    # Build SURFACE-based template
    # H-form starts with sites protonated (RCOOH)
    phreeqc_input = build_wac_surface_template(
        pka=4.5,  # Carboxylic acid pKa
        capacity_eq_l=capacity_eq_L,
        ca_log_k=1.2,  # Slightly higher for H-form
        mg_log_k=1.0,  # Slightly higher for H-form
        na_log_k=-0.3,  # Na reference
        k_log_k=-0.1,  # K slightly higher than Na
        cells=cells,
        water_composition=water_composition,
        bed_volume_L=bed_volume_L,
        bed_depth_m=bed_depth_m,
        porosity=0.4,
        flow_rate_m3_hr=flow_rate_m3_hr,
        max_bv=max_bv,
        database_path=database_path
    )

    return phreeqc_input