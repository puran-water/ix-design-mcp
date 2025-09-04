"""
Core configuration constants for ion exchange design calculations.
"""
import os
from pathlib import Path

class CONFIG:
    """Central configuration for ion exchange design parameters"""
    
    # Equivalent weights (mg/meq) for ionic species
    CA_EQUIV_WEIGHT = 20.04  # Ca2+ MW=40.08, valence=2
    MG_EQUIV_WEIGHT = 12.15  # Mg2+ MW=24.31, valence=2  
    NA_EQUIV_WEIGHT = 23.00  # Na+ MW=23.00, valence=1
    K_EQUIV_WEIGHT = 39.10   # K+ MW=39.10, valence=1
    NH4_EQUIV_WEIGHT = 18.04 # NH4+ MW=18.04, valence=1
    FE2_EQUIV_WEIGHT = 27.92 # Fe2+ MW=55.85, valence=2
    FE3_EQUIV_WEIGHT = 18.62 # Fe3+ MW=55.85, valence=3
    
    HCO3_EQUIV_WEIGHT = 61.02 # HCO3- MW=61.02, valence=1
    SO4_EQUIV_WEIGHT = 48.03  # SO42- MW=96.06, valence=2
    CO3_EQUIV_WEIGHT = 30.00  # CO32- MW=60.01, valence=2
    CL_EQUIV_WEIGHT = 35.45   # Cl- MW=35.45, valence=1
    NO3_EQUIV_WEIGHT = 62.00  # NO3- MW=62.00, valence=1
    PO4_EQUIV_WEIGHT = 31.67  # PO43- MW=94.97, valence=3
    F_EQUIV_WEIGHT = 19.00    # F- MW=19.00, valence=1
    OH_EQUIV_WEIGHT = 17.01   # OH- MW=17.01, valence=1
    
    # Hydraulic design parameters
    MAX_BED_VOLUME_PER_HOUR = 20.0  # BV/hr - Maximum service flow rate
    MAX_LINEAR_VELOCITY_M_HR = 50.0  # m/hr - Maximum linear velocity
    MAX_VESSEL_DIAMETER_M = 3.658    # m - Maximum single vessel diameter (12 ft)
    MIN_BED_DEPTH_M = 0.6            # m - Minimum bed depth
    FREEBOARD_PERCENT = 75           # % - Freeboard as percentage of bed depth
    
    # Resin and bed properties
    BED_POROSITY = 0.35             # Typical bed porosity for ion exchange resins
    RESIN_CAPACITY_EQ_L = 2.0       # eq/L - Typical SAC resin capacity
    
    # Modeling parameters
    ENABLE_MTZ_MODELING = False                    # Mass transfer zone modeling
    ENABLE_IONIC_STRENGTH_CORRECTION = True        # Ionic strength effects
    ENABLE_TEMPERATURE_CORRECTION = False          # Temperature effects
    DEFAULT_PARTICLE_DIAMETER_MM = 0.65            # mm - Typical resin particle size
    DEFAULT_DIFFUSION_COEFFICIENT = 1e-9           # m²/s - Typical diffusion coefficient
    
    # Regeneration parameters
    REGENERANT_DOSE_KG_M3 = 160.0       # kg NaCl/m³ resin
    REGENERANT_CONCENTRATION_PERCENT = 10.0  # % NaCl concentration
    RINSE_VOLUME_BV = 3.0               # Bed volumes of rinse water
    REGENERANT_FLOW_BV_HR = 4.0         # BV/hr regenerant flow rate
    
    @staticmethod
    def get_phreeqc_exe():
        """Get PHREEQC executable path from environment or default locations."""
        # Check environment variable first
        env_phreeqc = os.environ.get('PHREEQC_EXE')
        if env_phreeqc and Path(env_phreeqc).exists():
            return Path(env_phreeqc)
        
        # Check common installation paths
        common_paths = [
            Path('C:/Program Files/USGS/phreeqc-3.8.6-17100-x64/bin/Release/phreeqc.exe'),
            Path('/usr/local/bin/phreeqc'),
            Path('/usr/bin/phreeqc'),
        ]
        
        for path in common_paths:
            if path.exists():
                return path
        
        # Return None if not found (will trigger fallback in calling code)
        return None