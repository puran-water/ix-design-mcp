"""
Core Configuration Module for IX Design MCP Server

Centralizes all configuration constants to prevent duplication and divergence.
All physical constants, design parameters, and paths are defined here.
"""

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Optional


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
    
    # Regeneration parameters
    REGENERANT_DOSE_KG_M3: float = 125.0  # NaCl dose (kg/m³ bed volume)
    REGENERANT_CONCENTRATION_PERCENT: float = 10.0  # Brine concentration
    RINSE_VOLUME_BV: float = 4.0  # Rinse water requirement (bed volumes)
    REGENERANT_FLOW_BV_HR: float = 4.0  # Slow flow for regeneration
    
    # Simulation parameters
    DEFAULT_TOLERANCE: float = 1e-6  # Numerical tolerance for convergence
    DEFAULT_CELLS: int = 10  # Number of cells for column discretization
    DEFAULT_MAX_BV: int = 200  # Maximum bed volumes to simulate
    
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
    def get_phreeqc_database(self) -> Path:
        """Get PHREEQC database path from environment or use default."""
        env_path = os.getenv('PHREEQC_DATABASE')
        if env_path and os.path.exists(env_path):
            return Path(env_path)
        
        # Try common locations
        common_paths = [
            r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\database\phreeqc.dat",
            r"C:\Program Files\USGS\phreeqc-3.8.6-17096-x64\database\phreeqc.dat",
            r"C:\Program Files\USGS\phreeqc\database\phreeqc.dat",
            r"C:\Program Files (x86)\USGS\phreeqc\database\phreeqc.dat",
            r"C:\phreeqc\database\phreeqc.dat",
            "/usr/local/share/phreeqc/database/phreeqc.dat",
            "/usr/share/phreeqc/database/phreeqc.dat",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return Path(path)
        
        # Return first default if nothing found
        return Path(common_paths[0])
    
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


# Create singleton instance
CONFIG = CoreConfig()


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