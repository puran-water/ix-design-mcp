"""
Core Configuration Module for IX Design MCP Server

Centralizes all configuration constants to prevent duplication and divergence.
All physical constants, design parameters, and paths are defined here.
"""

from dataclasses import dataclass
from pathlib import Path
import os
import sys
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

# Get project root with robust approach
def get_project_root() -> Path:
    """Get project root with environment variable support."""
    # Strategy 1: Environment variable (most reliable for MCP clients)
    if 'IX_DESIGN_MCP_ROOT' in os.environ:
        root = Path(os.environ['IX_DESIGN_MCP_ROOT'])
        if root.exists():
            return root
    
    # Strategy 2: Relative to this file (fallback)
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CoreConfig:
    """
    Centralized configuration for IX design system.
    
    This class contains all physical constants, design parameters,
    and system configurations used throughout the application.
    Using frozen=True ensures these values cannot be modified at runtime.
    """
    
    # Physical constants for resin and water
    RESIN_CAPACITY_EQ_L: float = 2.0  # Standard SAC capacity (eq/L bed volume)
    BED_POROSITY: float = 0.4  # Standard porosity for IX resins
    WATER_DENSITY_KG_L: float = 1.0  # Water density at 25°C
    
    # Hydraulic design parameters
    MAX_BED_VOLUME_PER_HOUR: float = 16.0  # Maximum service flow rate (BV/hr)
    MIN_LINEAR_VELOCITY_M_HR: float = 5.0   # Minimum linear velocity (m/hr) to prevent maldistribution
    MAX_LINEAR_VELOCITY_M_HR: float = 25.0  # Maximum linear velocity (m/hr)
    MIN_BED_DEPTH_M: float = 0.75  # Minimum bed depth for proper distribution
    FREEBOARD_PERCENT: float = 100.0  # SAC resins need 100% freeboard for expansion
    MAX_VESSEL_DIAMETER_M: float = 2.4  # Shipping container constraint
    
    # Element equivalent weights for meq/L conversions (mg/meq)
    CA_EQUIV_WEIGHT: float = 20.04  # Ca2+: 40.08/2
    MG_EQUIV_WEIGHT: float = 12.15  # Mg2+: 24.305/2
    NA_EQUIV_WEIGHT: float = 23.0   # Na+: 22.99/1
    K_EQUIV_WEIGHT: float = 39.1    # K+: 39.098/1
    NH4_EQUIV_WEIGHT: float = 18.04 # NH4+: 18.04/1
    FE2_EQUIV_WEIGHT: float = 27.92 # Fe2+: 55.845/2
    FE3_EQUIV_WEIGHT: float = 18.62 # Fe3+: 55.845/3
    CL_EQUIV_WEIGHT: float = 35.45  # Cl-: 35.45/1
    HCO3_EQUIV_WEIGHT: float = 61.02 # HCO3-: 61.02/1
    SO4_EQUIV_WEIGHT: float = 48.03 # SO4-2: 96.06/2
    CO3_EQUIV_WEIGHT: float = 30.0  # CO3-2: 60.01/2
    NO3_EQUIV_WEIGHT: float = 62.0  # NO3-: 62.00/1
    PO4_EQUIV_WEIGHT: float = 31.67 # PO4-3: 94.97/3
    F_EQUIV_WEIGHT: float = 19.0    # F-: 19.00/1
    OH_EQUIV_WEIGHT: float = 17.0   # OH-: 17.01/1

    # SAC selectivity coefficients (log K values for 8% DVB standard resin)
    SAC_LOGK_CA_NA: float = 0.416   # Ca/Na selectivity for SAC (8% DVB)
    SAC_LOGK_MG_NA: float = 0.221   # Mg/Na selectivity for SAC (8% DVB)

    # WAC-specific constants
    ALKALINITY_EQUIV_WEIGHT: float = 50.04  # Alkalinity as CaCO3: 100.09/2
    H_EQUIV_WEIGHT: float = 1.008   # H+: 1.008/1
    CO2_MW: float = 44.01           # CO2 molecular weight
    CACO3_MW: float = 100.09        # CaCO3 molecular weight for alkalinity
    
    # WAC resin parameters
    WAC_PKA: float = 4.8            # pKa for carboxylic acid groups
    WAC_NA_TOTAL_CAPACITY: float = 4.7  # Total capacity in eq/L
    WAC_H_TOTAL_CAPACITY: float = 4.7   # eq/L - Total theoretical capacity
    WAC_NA_WORKING_CAPACITY: float = 1.8  # Working capacity in eq/L
    WAC_H_WORKING_CAPACITY: float = 1.6   # eq/L - Typical working capacity at pH 4.5 leakage
    
    # WAC selectivity coefficients (log K values)
    WAC_LOGK_CA_NA: float = 1.30    # Ca/Na selectivity for WAC
    WAC_LOGK_MG_NA: float = 1.10    # Mg/Na selectivity for WAC
    WAC_LOGK_K_NA: float = 0.25     # K/Na selectivity for WAC
    WAC_LOGK_H_NA: float = 3.0      # H/Na selectivity for WAC (H+ >> all other cations)
    
    # WAC H-form selectivity (HX is reference, log_k = 0.0)
    WAC_LOGK_CA_H: float = 1.5      # Ca+2 binding to deprotonated sites (SURFACE model)
    WAC_LOGK_MG_H: float = 1.3      # Mg+2 binding to deprotonated sites (SURFACE model)
    WAC_LOGK_NA_H: float = -0.5     # Na+ weakly binds to deprotonated sites
    WAC_LOGK_K_H: float = -0.3      # K+ weakly binds to deprotonated sites
    
    # WAC regeneration parameters
    WAC_ACID_DOSE_G_L: float = 100.0   # Acid dose for WAC regeneration (g/L resin)
    WAC_CAUSTIC_DOSE_G_L: float = 80.0 # Caustic dose for Na-form conversion (g/L resin)
    WAC_RINSE_BV: float = 5.0          # Total rinse volume for WAC (BV)
    
    # WAC performance thresholds
    WAC_MIN_ACTIVE_SITES_PERCENT: float = 10.0  # Minimum active sites for H-form WAC
    WAC_ALKALINITY_LEAK_MG_L: float = 5.0       # Alkalinity leak threshold (mg/L as CaCO3)

    # WAC H-form kinetic model parameters (SURFACE + KINETICS)
    WAC_H_DEPROTONATION_RATE: float = 1e-4      # Rate constant (1/s) for H+ release control
    WAC_H_INITIAL_PROTONATION: float = 0.6      # Initial fraction of sites protonated (60%)
    WAC_H_TARGET_PH_RECOVERY_BV: float = 20.0   # Target BV for pH recovery
    WAC_H_USE_CVODE: bool = True                # Use CVODE for accurate kinetic integration

    # Universal Enhancement Parameters
    
    # Enhancement control flags
    ENABLE_IONIC_STRENGTH_CORRECTION: bool = True
    ENABLE_TEMPERATURE_CORRECTION: bool = True
    ENABLE_MTZ_MODELING: bool = True
    ENABLE_CAPACITY_DEGRADATION: bool = True
    ENABLE_H_FORM_LEAKAGE: bool = True
    ENABLE_CO2_TRACKING: bool = True
    
    # Ionic strength parameters
    DAVIES_EQUATION_A: float = 0.51  # Davies equation constant at 25°C
    
    # MTZ (Mass Transfer Zone) parameters
    DEFAULT_PARTICLE_DIAMETER_MM: float = 0.65  # Standard resin bead size
    DEFAULT_DIFFUSION_COEFFICIENT: float = 1e-9  # m²/s for ions in resin
    MTZ_EMPIRICAL_FACTOR: float = 5.0  # Empirical factor for MTZ length (3-10)
    MAX_MTZ_FRACTION: float = 0.3  # Maximum MTZ as fraction of bed depth
    
    # H-form leakage parameters
    BASE_NA_LEAKAGE_PERCENT: float = 2.0  # Base Na+ leakage for fresh H-form resin
    BASE_K_LEAKAGE_PERCENT: float = 1.5   # Base K+ leakage for fresh H-form resin
    LEAKAGE_EXHAUSTION_FACTOR: float = 3.0  # Leakage multiplier at full exhaustion
    
    # Capacity degradation parameters
    DEFAULT_CAPACITY_FACTOR: float = 1.0  # Fresh resin = 1.0, fouled < 1.0
    DEGRADATION_RATE_PER_CYCLE: float = 0.001  # 0.1% capacity loss per cycle
    MIN_CAPACITY_FACTOR: float = 0.5  # Minimum capacity after degradation
    
    # CO2 generation parameters
    CO2_HENRY_CONSTANT_25C: float = 29.4  # Henry's constant at 25°C (atm·L/mol)
    CO2_TEMP_COEFFICIENT: float = -2400  # Temperature dependency factor (K)
    CO2_STRIPPING_THRESHOLD: float = 80.0  # % saturation requiring stripping
    
    # Regeneration parameters
    REGENERANT_DOSE_KG_M3: float = 125.0  # NaCl dose (kg/m³ bed volume)
    REGENERANT_CONCENTRATION_PERCENT: float = 10.0  # Brine concentration
    RINSE_VOLUME_BV: float = 4.0  # Rinse water requirement (bed volumes)
    REGENERANT_FLOW_BV_HR: float = 4.0  # Slow flow for regeneration
    
    # Simulation parameters
    DEFAULT_TOLERANCE: float = 1e-6  # Numerical tolerance for convergence
    DEFAULT_CELLS: int = 8  # Number of cells for column discretization
    DEFAULT_MAX_BV: int = 200  # Maximum bed volumes to simulate

    # Dynamic BV calculation safety limits
    # These are EXTREME safety caps for pathological bugs only - NOT operational limits
    # Normal simulations run to completion via JobManager; users can terminate if too slow
    MAX_SIMULATION_BV: int = 10000  # Extreme safety cap (should never be hit in practice)

    # PHREEQC database selection
    PHREEQC_DATABASE_NAME: str = "phreeqc.dat"  # Options: phreeqc.dat | pitzer.dat | sit.dat
    HIGH_TDS_THRESHOLD_G_L: float = 10.0  # TDS threshold for Pitzer database recommendation

    # PHREEQC executable path (from environment or default)
    def get_phreeqc_exe(self) -> Path:
        """Get PHREEQC executable path from environment or use default."""
        env_path = os.getenv('PHREEQC_EXE')
        if env_path and os.path.exists(env_path):
            return Path(env_path)
        
        # Try common locations
        common_paths = [
            r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\bin\phreeqc.bat",
            r"C:\Program Files\USGS\phreeqc-3.8.6-17096-x64\bin\phreeqc.bat",
            r"C:\Program Files\USGS\phreeqc\bin\phreeqc.bat",
            r"C:\Program Files (x86)\USGS\phreeqc\bin\phreeqc.bat",
            r"C:\phreeqc\bin\phreeqc.bat",
            "/usr/local/bin/phreeqc",
            "/usr/bin/phreeqc",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return Path(path)
        
        # Return first default if nothing found
        return Path(common_paths[0])
    
    # PHREEQC database path (from environment or default)
    def get_phreeqc_database(self, db_name: Optional[str] = None) -> Path:
        """Get PHREEQC database path from environment or use default.

        Args:
            db_name: Database filename (e.g., 'phreeqc.dat', 'pitzer.dat').
                     If None, uses PHREEQC_DATABASE_NAME from config.

        Returns:
            Path to the database file

        Search order:
            1. PHREEQC_DATABASE environment variable
            2. Virtual environment site-packages/phreeqpython/database/
            3. System PHREEQC installations
        """
        if db_name is None:
            db_name = self.PHREEQC_DATABASE_NAME

        # 1. Check environment variable (highest priority)
        env_path = os.getenv('PHREEQC_DATABASE')
        if env_path and os.path.exists(env_path):
            logger.debug(f"Using PHREEQC database from PHREEQC_DATABASE env: {env_path}")
            return Path(env_path)

        # 2. Try common system installation locations (fast path - check before importing phreeqpython)
        common_dirs = [
            r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\database",
            r"C:\Program Files\USGS\phreeqc-3.8.6-17096-x64\database",
            r"C:\Program Files\USGS\phreeqc\database",
            r"C:\Program Files (x86)\USGS\phreeqc\database",
            r"C:\phreeqc\database",
            "/usr/local/share/phreeqc/database",
            "/usr/share/phreeqc/database",
        ]

        for dir_path in common_dirs:
            full_path = Path(dir_path) / db_name
            if full_path.exists():
                logger.debug(f"Using PHREEQC database from system path: {full_path}")
                return full_path

        # 3. Fall back to phreeqpython package (SLOW - only use if system paths not found)
        logger.warning("PHREEQC database not found in system paths, falling back to phreeqpython import (may be slow)")
        try:
            import phreeqpython
            phreeqpy_db = Path(phreeqpython.__file__).parent / "database" / db_name
            if phreeqpy_db.exists():
                logger.debug(f"Using PHREEQC database from phreeqpython: {phreeqpy_db}")
                return phreeqpy_db
        except ImportError:
            logger.warning("phreeqpython not available and database not found in system paths")
            pass

        # Return default path (may not exist - caller should handle)
        logger.warning(f"Database {db_name} not found in any location, returning default")
        return Path(common_dirs[0]) / db_name
    
    def get_equiv_weight(self, ion: str) -> float:
        """
        Get equivalent weight for an ion.
        
        Args:
            ion: Ion name (e.g., 'Ca', 'Mg', 'Na')
            
        Returns:
            Equivalent weight in mg/meq
            
        Raises:
            ValueError: If ion is not recognized
        """
        equiv_weights = {
            'Ca': self.CA_EQUIV_WEIGHT,
            'Mg': self.MG_EQUIV_WEIGHT,
            'Na': self.NA_EQUIV_WEIGHT,
            'K': self.K_EQUIV_WEIGHT,
            'NH4': self.NH4_EQUIV_WEIGHT,
            'Fe2': self.FE2_EQUIV_WEIGHT,
            'Fe3': self.FE3_EQUIV_WEIGHT,
            'Cl': self.CL_EQUIV_WEIGHT,
            'HCO3': self.HCO3_EQUIV_WEIGHT,
            'SO4': self.SO4_EQUIV_WEIGHT,
            'CO3': self.CO3_EQUIV_WEIGHT,
            'NO3': self.NO3_EQUIV_WEIGHT,
            'PO4': self.PO4_EQUIV_WEIGHT,
            'F': self.F_EQUIV_WEIGHT,
            'OH': self.OH_EQUIV_WEIGHT,
        }
        
        if ion not in equiv_weights:
            raise ValueError(f"Unknown ion: {ion}. Known ions: {list(equiv_weights.keys())}")
        
        return equiv_weights[ion]
    
    def get_ion_size_parameters(self) -> Dict[str, float]:
        """Get ion size parameters for Davies equation calculations."""
        return {
            'Ca': 6.0,   # Hydrated Ca2+ radius in Angstroms
            'Mg': 8.0,   # Hydrated Mg2+ radius in Angstroms
            'Na': 4.5,   # Hydrated Na+ radius in Angstroms
            'K': 3.5,    # Hydrated K+ radius in Angstroms
            'H': 9.0,    # Hydrated H+ (H3O+) radius in Angstroms
            'NH4': 3.3,  # NH4+ radius in Angstroms
            'Cl': 3.3,   # Cl- radius in Angstroms
            'SO4': 4.0,  # SO42- radius in Angstroms
            'HCO3': 4.5, # HCO3- radius in Angstroms
        }
    
    def get_exchange_enthalpies(self) -> Dict[str, float]:
        """
        Get standard enthalpies of exchange for temperature correction.
        
        Negative values = exothermic (selectivity decreases with temperature)
        Positive values = endothermic (selectivity increases with temperature)
        """
        return {
            'Ca_Na': -8.0,   # Ca2+ replacing Na+ on resin
            'Mg_Na': -6.0,   # Mg2+ replacing Na+ on resin
            'K_Na': -2.0,    # K+ replacing Na+ on resin
            'H_Na': -12.0,   # H+ replacing Na+ on resin (strongly exothermic)
            'Ca_H': 4.0,     # Ca2+ replacing H+ on resin (endothermic)
            'Mg_H': 3.0,     # Mg2+ replacing H+ on resin (endothermic)
            'Na_H': 3.0,     # Na+ replacing H+ on resin (endothermic)
            'K_H': 2.0,      # K+ replacing H+ on resin (endothermic)
        }
    
    def check_tds_for_pitzer(self, tds_g_l: float) -> tuple[bool, str]:
        """Check if water TDS requires Pitzer database.

        Args:
            tds_g_l: Total dissolved solids in g/L

        Returns:
            Tuple of (requires_pitzer: bool, message: str)
        """
        if tds_g_l > self.HIGH_TDS_THRESHOLD_G_L:
            msg = (
                f"High TDS detected ({tds_g_l:.1f} g/L > {self.HIGH_TDS_THRESHOLD_G_L} g/L). "
                f"Recommend using Pitzer database for accurate activity coefficients. "
                f"Set PHREEQC_DATABASE_NAME='pitzer.dat' in config or use get_phreeqc_database('pitzer.dat')"
            )
            return True, msg
        return False, ""

    def get_merged_database_path(self, db_name: Optional[str] = None) -> Path:
        """Get path to merged database, creating if needed.

        Args:
            db_name: Base database to use (e.g., 'phreeqc.dat', 'pitzer.dat').
                     If None, uses PHREEQC_DATABASE_NAME from config.

        Returns:
            Path to merged database file
        """
        if db_name is None:
            db_name = self.PHREEQC_DATABASE_NAME

        project_root = get_project_root()
        # Create different merged files for different base databases
        db_basename = db_name.replace('.dat', '')
        merged_path = project_root / "databases" / f"{db_basename}_merged.dat"

        if not merged_path.exists():
            logger.info(f"Creating merged PHREEQC database from {db_name}...")
            setup_merged_database(db_name)

        return merged_path


# Create singleton instance
CONFIG = CoreConfig()


# Database setup functions
def setup_merged_database(db_name: Optional[str] = None):
    """Create merged PHREEQC database with exchange reactions included.

    Args:
        db_name: Base database filename (e.g., 'phreeqc.dat', 'pitzer.dat').
                 If None, uses PHREEQC_DATABASE_NAME from config.

    Returns:
        Path to merged database file
    """
    if db_name is None:
        db_name = CONFIG.PHREEQC_DATABASE_NAME

    project_root = get_project_root()
    db_dir = project_root / "databases"
    db_dir.mkdir(exist_ok=True)

    # Create database-specific merged file
    db_basename = db_name.replace('.dat', '')
    merged_path = db_dir / f"{db_basename}_merged.dat"

    # Read base database
    phreeqc_path = CONFIG.get_phreeqc_database(db_name)
    logger.info(f"Reading base database from: {phreeqc_path}")
    with open(phreeqc_path, 'r') as f:
        base_content = f.read()

    # Verify exchange section exists
    if 'EXCHANGE_MASTER_SPECIES' not in base_content:
        raise RuntimeError(f"Base database {db_name} missing EXCHANGE_MASTER_SPECIES")

    # For now, use base database as-is (future: could add custom reactions)
    merged_content = base_content

    # Write merged database
    with open(merged_path, 'w') as f:
        f.write(merged_content)

    # Verify
    verify_merged_database(merged_path)

    logger.info(f"Created merged database at {merged_path}")
    return merged_path


def verify_merged_database(db_path: Path):
    """Unit test to verify database has exchange reactions"""
    with open(db_path, 'r') as f:
        content = f.read()
    
    required_sections = [
        'EXCHANGE_MASTER_SPECIES',
        'EXCHANGE_SPECIES',
        'X X-'
    ]
    
    for section in required_sections:
        if section not in content:
            raise RuntimeError(f"Database missing required section: {section}")
    
    logger.info(f"Verified merged database at {db_path}")


# Validation functions
def validate_config():
    """
    Validate configuration values are reasonable.
    Called on module import to catch configuration errors early.
    """
    # Check physical constants
    assert CONFIG.RESIN_CAPACITY_EQ_L > 0, "Resin capacity must be positive"
    assert 0 < CONFIG.BED_POROSITY < 1, "Bed porosity must be between 0 and 1"
    
    # Check design parameters
    assert CONFIG.MAX_BED_VOLUME_PER_HOUR > 0, "Max BV/hr must be positive"
    assert CONFIG.MAX_LINEAR_VELOCITY_M_HR > 0, "Max velocity must be positive"
    assert CONFIG.MIN_BED_DEPTH_M > 0, "Min bed depth must be positive"
    assert CONFIG.FREEBOARD_PERCENT >= 0, "Freeboard must be non-negative"
    assert CONFIG.MAX_VESSEL_DIAMETER_M > 0, "Max diameter must be positive"
    
    # Check equivalent weights
    for attr_name in dir(CONFIG):
        if attr_name.endswith('_EQUIV_WEIGHT'):
            value = getattr(CONFIG, attr_name)
            assert value > 0, f"{attr_name} must be positive"
    
    # Check paths exist or can be created
    phreeqc_exe = CONFIG.get_phreeqc_exe()
    if not phreeqc_exe.exists():
        import warnings
        warnings.warn(f"PHREEQC executable not found at {phreeqc_exe}. Set PHREEQC_EXE environment variable.")


# Run validation on import
validate_config()
