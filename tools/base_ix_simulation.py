"""
Base Ion Exchange Simulation Module

Provides common functionality for all ion exchange simulations (SAC, WAC, etc.)
following the DRY principle to eliminate code duplication.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from abc import ABC, abstractmethod

# Get project root
def get_project_root() -> Path:
    """Get project root with environment variable support."""
    import os
    if 'IX_DESIGN_MCP_ROOT' in os.environ:
        root = Path(os.environ['IX_DESIGN_MCP_ROOT'])
        if root.exists():
            return root
    return Path(__file__).resolve().parent.parent

# Add project root to path
project_root = get_project_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import PHREEQC engines
try:
    from watertap_ix_transport.transport_core.optimized_phreeqc_engine import OptimizedPhreeqcEngine
    OPTIMIZED_AVAILABLE = True
except ImportError:
    OPTIMIZED_AVAILABLE = False
    
from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine

# Import centralized configuration
from tools.core_config import CONFIG

logger = logging.getLogger(__name__)

# Constants for enhancement calculations
R_GAS_CONSTANT = 8.314  # J/(mol·K)
KELVIN_OFFSET = 273.15  # Convert °C to K


class BaseIXSimulation(ABC):
    """
    Base class for all ion exchange simulations.
    
    Provides common functionality:
    - PHREEQC engine initialization
    - Breakthrough data extraction
    - Water composition validation
    - Smart data sampling
    - Common error handling
    """
    
    def __init__(self):
        """Initialize simulation with PHREEQC engine."""
        self.engine = self._initialize_phreeqc_engine()
    
    def _initialize_phreeqc_engine(self):
        """
        Initialize PHREEQC engine with optimized fallback.
        
        Common pattern used by both SAC and WAC simulations.
        """
        # Try optimized engine first
        if OPTIMIZED_AVAILABLE:
            try:
                phreeqc_exe = CONFIG.get_phreeqc_exe()
                engine = OptimizedPhreeqcEngine(
                    phreeqc_path=str(phreeqc_exe),
                    cache_size=256,
                    max_workers=4
                )
                logger.info("Using OptimizedPhreeqcEngine for simulation")
                return engine
            except Exception as e:
                logger.warning(f"Failed to initialize OptimizedPhreeqcEngine: {e}")
        
        # Fall back to DirectPhreeqcEngine
        phreeqc_exe = CONFIG.get_phreeqc_exe()
        phreeqc_db = CONFIG.get_phreeqc_database()
        
        logger.info(f"Attempting DirectPhreeqcEngine initialization:")
        logger.info(f"  - PHREEQC exe: {phreeqc_exe}")
        logger.info(f"  - PHREEQC database: {phreeqc_db}")
        
        try:
            engine = DirectPhreeqcEngine(phreeqc_path=str(phreeqc_exe))
            # Verify the engine has a valid database path
            if not engine.default_database:
                logger.error("Engine created but has no database path")
                raise RuntimeError("Engine has no database path")
            logger.info(f"Using DirectPhreeqcEngine with database: {engine.default_database}")
            return engine
        except (FileNotFoundError, RuntimeError) as e:
            logger.warning(f"Failed to initialize PHREEQC at {phreeqc_exe}: {e}")
            # Try without specifying path (will search system)
            try:
                engine = DirectPhreeqcEngine()
                # Verify the engine has a valid database path
                if not engine.default_database:
                    logger.error("Engine created but has no database path")
                    raise RuntimeError("Engine has no database path")
                logger.info(f"Using DirectPhreeqcEngine with system PHREEQC, database: {engine.default_database}")
                return engine
            except (FileNotFoundError, RuntimeError) as e2:
                logger.error(f"Failed to find PHREEQC in system PATH: {e2}")
                # Check if PHREEQC_EXE is set but not in CONFIG's path
                import os
                env_phreeqc = os.environ.get('PHREEQC_EXE')
                if env_phreeqc and env_phreeqc != str(phreeqc_exe):
                    logger.info(f"Trying PHREEQC_EXE from environment: {env_phreeqc}")
                    engine = DirectPhreeqcEngine(phreeqc_path=env_phreeqc)
                    # Verify the engine has a valid database path
                    if not engine.default_database:
                        logger.error("Engine created but has no database path")
                        raise RuntimeError("Engine has no database path")
                    logger.info(f"Using DirectPhreeqcEngine from env, database: {engine.default_database}")
                    return engine
                else:
                    raise RuntimeError(
                        "PHREEQC executable not found. Please install PHREEQC and set PHREEQC_EXE environment variable."
                    )
    
    def _extract_breakthrough_data(self, selected_output: str) -> Dict[str, np.ndarray]:
        """
        Extract breakthrough data from PHREEQC selected output.
        
        Common data parsing logic used by all simulations.
        """
        lines = selected_output.strip().split('\n')
        if len(lines) < 2:
            return {}
        
        # Parse headers
        headers = lines[0].split('\t')
        
        # Initialize data arrays
        data = {header: [] for header in headers}
        
        # Parse data lines
        for line in lines[1:]:
            if line.strip():
                values = line.split('\t')
                for i, header in enumerate(headers):
                    if i < len(values):
                        try:
                            data[header].append(float(values[i]))
                        except ValueError:
                            data[header].append(values[i])
        
        # Convert to numpy arrays
        for key in data:
            data[key] = np.array(data[key])
        
        return data
    
    def _extract_breakthrough_data_filtered(self, selected_output: str) -> Dict[str, np.ndarray]:
        """
        Extract breakthrough data with equilibration filtering.

        Modified to preserve step 0 (initial equilibration) for diagnostics
        while still filtering out invalid steps (step < 0).
        Uses the engine's parser which properly handles header stripping.
        """
        # Use engine's parser which handles header stripping and species mapping
        parsed_data = self.engine.parse_selected_output(selected_output)

        if not parsed_data:
            logger.warning("No data returned from PHREEQC - likely convergence failure")
            return {}

        # Filter invalid rows but KEEP step 0 for initial state
        filtered_rows = []
        has_transport_steps = False
        for row in parsed_data:
            # Check for step column (engine parser strips headers)
            step_value = row.get('step', row.get('Step', 0))
            if step_value >= 0:  # Changed from > 0 to >= 0
                filtered_rows.append(row)
                if step_value > 0:
                    has_transport_steps = True

        if not filtered_rows:
            logger.error("No valid steps found - PHREEQC simulation failed completely")
            return {}

        if not has_transport_steps:
            logger.warning("Only equilibration step found (step=0) - transport did not progress")
            logger.warning("This typically indicates pH crash or convergence failure")
            logger.warning("Check PHREEQC temp files for convergence errors")
            # Still return the equilibration data for diagnostics

        def _safe_float(value: Any) -> float:
            """Best-effort conversion to float with NaN fallback."""
            if value is None:
                return float('nan')
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                stripped = value.strip()
                if stripped == "" or stripped.lower() in {"nan", "none"}:
                    return float('nan')
                try:
                    return float(stripped)
                except ValueError:
                    return float('nan')
            return float('nan')

        # Convert list of dicts to dict of numpy arrays, keeping floats when possible
        data: Dict[str, np.ndarray] = {}
        for key in filtered_rows[0].keys():
            numeric_values = [_safe_float(row.get(key)) for row in filtered_rows]

            # Determine if the column can be treated as numeric (any non-NaN values)
            has_numeric = any(not np.isnan(val) for val in numeric_values)
            if has_numeric:
                data[key] = np.array(numeric_values, dtype=float)
            else:
                # Fall back to string representations for non-numeric columns
                data[key] = np.array([
                    "" if row.get(key) is None else str(row.get(key))
                    for row in filtered_rows
                ])

        # Drop rows where step could not be parsed (NaN) to avoid downstream issues
        step_column = data.get('step', data.get('Step'))
        if step_column is not None:
            valid_mask = ~np.isnan(step_column)
            if not np.all(valid_mask):
                for key in list(data.keys()):
                    if data[key].shape == step_column.shape:
                        data[key] = data[key][valid_mask]

        logger.info(f"Filtered data: {len(parsed_data)} total rows -> {len(filtered_rows)} valid rows")
        if has_transport_steps:
            logger.info(f"Transport steps found: {len([r for r in filtered_rows if r.get('step', 0) > 0])}")
        else:
            logger.warning("No transport steps - only equilibration data available")

        return data
    
    def _validate_water_composition(self, water_composition: Dict[str, float]) -> bool:
        """
        Validate water composition including charge balance.
        
        From SAC lines 333-343.
        """
        # Calculate charge balance
        cation_meq = 0
        anion_meq = 0
        
        # Cations
        cation_meq += water_composition.get('ca_mg_l', 0) / CONFIG.CA_EQUIV_WEIGHT
        cation_meq += water_composition.get('mg_mg_l', 0) / CONFIG.MG_EQUIV_WEIGHT
        cation_meq += water_composition.get('na_mg_l', 0) / CONFIG.NA_EQUIV_WEIGHT
        cation_meq += water_composition.get('k_mg_l', 0) / CONFIG.K_EQUIV_WEIGHT
        cation_meq += water_composition.get('nh4_mg_l', 0) / CONFIG.NH4_EQUIV_WEIGHT
        cation_meq += water_composition.get('fe2_mg_l', 0) / CONFIG.FE2_EQUIV_WEIGHT
        cation_meq += water_composition.get('fe3_mg_l', 0) / CONFIG.FE3_EQUIV_WEIGHT
        
        # Anions
        anion_meq += water_composition.get('cl_mg_l', 0) / CONFIG.CL_EQUIV_WEIGHT
        anion_meq += water_composition.get('so4_mg_l', 0) / CONFIG.SO4_EQUIV_WEIGHT
        anion_meq += water_composition.get('hco3_mg_l', 0) / CONFIG.HCO3_EQUIV_WEIGHT
        anion_meq += water_composition.get('co3_mg_l', 0) / CONFIG.CO3_EQUIV_WEIGHT
        anion_meq += water_composition.get('no3_mg_l', 0) / CONFIG.NO3_EQUIV_WEIGHT
        
        # Check charge balance (within 5%)
        if cation_meq > 0 and anion_meq > 0:
            charge_error = abs((cation_meq - anion_meq) / (cation_meq + anion_meq) * 200)
            if charge_error > 5:
                logger.warning(f"Charge balance error: {charge_error:.1f}% (>5%)")
                logger.warning(f"Cations: {cation_meq:.2f} meq/L, Anions: {anion_meq:.2f} meq/L")
                return False
        
        return True
    
    def _smart_sample_breakthrough_curves(
        self, 
        data: Dict[str, np.ndarray], 
        max_points: int = 60
    ) -> Dict[str, np.ndarray]:
        """
        Intelligently sample breakthrough curves for efficient storage and plotting.
        
        From SAC lines 1836-1907. Reduces 1000+ points to ~60 with high resolution
        near breakthrough and key transition points.
        """
        if 'BV' not in data or len(data['BV']) == 0:
            return data
        
        bv_array = data['BV']
        n_points = len(bv_array)
        
        if n_points <= max_points:
            return data  # No sampling needed
        
        # Find key transition points
        key_indices = set([0, n_points - 1])  # Always include first and last
        
        # Add points near breakthrough if we have hardness data
        hardness = None
        if 'Hardness_CaCO3' in data:
            hardness = data['Hardness_CaCO3']
        elif 'Hardness_mg/L' in data:
            hardness = data['Hardness_mg/L']
        
        if hardness is not None:
            # Find rapid change points (derivative)
            if len(hardness) > 2:
                # Filter out None values before computing diff
                hardness_clean = np.array([x if x is not None else np.nan for x in hardness])
                # Only compute diff on valid values
                if not np.all(np.isnan(hardness_clean)):
                    d_hardness = np.diff(hardness_clean)
                    # Filter out NaN from diff result
                    valid_diff = d_hardness[~np.isnan(d_hardness)]
                    if len(valid_diff) > 0:
                        std_diff = np.std(valid_diff)
                        if std_diff > 0:
                            rapid_change = np.where(np.abs(d_hardness) > std_diff)[0]
                            key_indices.update(rapid_change)
        
        # Smart sampling: higher density near key points
        sampled_indices = list(key_indices)
        
        # Add evenly spaced points to fill gaps
        remaining_points = max_points - len(sampled_indices)
        if remaining_points > 0:
            # Use log spacing for early BVs (more resolution at start)
            log_indices = np.logspace(0, np.log10(n_points), remaining_points, dtype=int) - 1
            sampled_indices.extend(log_indices)
        
        # Sort and remove duplicates
        sampled_indices = sorted(list(set(sampled_indices)))[:max_points]
        
        # Sample all arrays
        sampled_data = {}
        for key, array in data.items():
            if isinstance(array, np.ndarray) and len(array) == n_points:
                sampled_data[key] = array[sampled_indices]
            else:
                sampled_data[key] = array
        
        logger.info(f"Sampled breakthrough curves: {n_points} -> {len(sampled_indices)} points")
        return sampled_data
    
    def _find_breakthrough_point(
        self,
        bv_array: np.ndarray,
        concentration_array: np.ndarray,
        target: float
    ) -> Optional[float]:
        """
        Find exact BV where concentration crosses target using interpolation.
        
        Common breakthrough detection logic with linear interpolation.
        """
        # Find where concentration exceeds target (excluding None/NaN values)
        # Convert to numeric array, replacing None with NaN
        try:
            numeric_array = np.array([float(x) if x is not None else np.nan for x in concentration_array])
        except (TypeError, ValueError):
            # If conversion fails, return None
            return None

        # Filter out NaN values
        valid_mask = ~np.isnan(numeric_array)
        if not np.any(valid_mask):
            # No valid data points
            return None

        valid_concentrations = numeric_array[valid_mask]
        valid_bv = bv_array[valid_mask]

        idx = np.where(valid_concentrations > target)[0]
        if len(idx) > 0:
            i = idx[0]
            if i > 0:
                # Linear interpolation for exact breakthrough point
                bv_breakthrough = np.interp(
                    target,
                    [valid_concentrations[i-1], valid_concentrations[i]],
                    [valid_bv[i-1], valid_bv[i]]
                )
                return float(bv_breakthrough)
            else:
                # Target exceeded from start
                return float(valid_bv[0])
        return None
    
    def _detect_breakthrough(
        self,
        data: Dict[str, np.ndarray],
        criteria: List[Tuple[str, float, str]]
    ) -> Tuple[float, bool, str]:
        """
        Detect breakthrough using multiple criteria.
        
        Args:
            data: Breakthrough data dictionary with BV and concentration arrays
            criteria: List of (column_name, target_value, comparison) tuples
                     comparison can be 'gt' (>), 'lt' (<), 'gte' (>=), 'lte' (<=)
        
        Returns:
            Tuple of (breakthrough_bv, breakthrough_reached, reason)
        """
        if 'BV' not in data or len(data['BV']) == 0:
            return 0.0, False, "No BV data available"
        
        bv_array = data['BV']
        
        for column, target, comparison in criteria:
            if column not in data or len(data[column]) == 0:
                continue
            
            conc_array = data[column]
            
            # Find breakthrough based on comparison
            if comparison == 'gt':
                breakthrough_bv = self._find_breakthrough_point(bv_array, conc_array, target)
                if breakthrough_bv is not None:
                    return breakthrough_bv, True, f"{column} > {target}"
            
            elif comparison == 'lt':
                # For less than, we need to invert the logic
                idx = np.where(conc_array < target)[0]
                if len(idx) > 0 and idx[0] > 0:
                    # Interpolate
                    i = idx[0]
                    breakthrough_bv = np.interp(
                        target,
                        [conc_array[i], conc_array[i-1]],
                        [bv_array[i], bv_array[i-1]]
                    )
                    return float(breakthrough_bv), True, f"{column} < {target}"
            
            elif comparison == 'gte':
                idx = np.where(conc_array >= target)[0]
                if len(idx) > 0:
                    return float(bv_array[idx[0]]), True, f"{column} >= {target}"
            
            elif comparison == 'lte':
                idx = np.where(conc_array <= target)[0]
                if len(idx) > 0:
                    return float(bv_array[idx[0]]), True, f"{column} <= {target}"
        
        # No breakthrough detected
        return float(bv_array[-1]) if len(bv_array) > 0 else 0.0, False, "No breakthrough detected"
    
    def _calculate_dynamic_max_bv(
        self,
        loading_meq_L: float,
        capacity_eq_L: float,
        buffer_factor: float = 3.0,  # Increased from 1.2 to ensure we see breakthrough
        min_bv: int = 200
    ) -> int:
        """
        Calculate dynamic max BV based on theoretical capacity.
        
        Args:
            loading_meq_L: Feed water loading (hardness, alkalinity, etc.) in meq/L
            capacity_eq_L: Resin working capacity in eq/L
            buffer_factor: Safety factor (default 1.2 = 20% buffer)
            min_bv: Minimum BV to simulate
            
        Returns:
            Calculated max BV for simulation
        """
        if loading_meq_L > 0:
            theoretical_bv = (capacity_eq_L * 1000) / loading_meq_L
            calculated_bv = int(theoretical_bv * buffer_factor)
            return max(calculated_bv, min_bv)
        else:
            return min_bv
    
    def _handle_phreeqc_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Common error handling for PHREEQC failures.
        
        Returns a standard error response structure.
        """
        logger.error(f"PHREEQC execution failed: {error}")
        logger.error(f"Context: {context}")
        
        return {
            "status": "error",
            "error": str(error),
            "context": context,
            "warnings": [f"PHREEQC error: {str(error)}"],
            "breakthrough_reached": False,
            "breakthrough_bv": 0,
            "service_time_hours": 0,
            "capacity_utilization_percent": 0,
            "breakthrough_data": {},
            "simulation_details": {"error": str(error)}
        }
    
    def _index_at_bv(self, data: Dict[str, np.ndarray], breakthrough_bv: float) -> int:
        """
        Find array index corresponding to a given BV value.
        
        Args:
            data: Dictionary containing breakthrough data with 'BV' key
            breakthrough_bv: The bed volume value to find index for
            
        Returns:
            Index in arrays corresponding to breakthrough_bv
            Returns last index if BV beyond range or if arrays missing
        """
        bvs = data.get('BV', data.get('bv', np.array([])))
        if len(bvs) == 0:
            logger.warning("No BV data found in breakthrough data")
            return 0

        # Filter out None values from bvs array
        if not isinstance(bvs, np.ndarray):
            bvs = np.array(bvs)

        # Remove None/NaN values
        valid_mask = np.array([x is not None and not (isinstance(x, float) and np.isnan(x)) for x in bvs])
        if not np.any(valid_mask):
            logger.warning("No valid BV data found in breakthrough data")
            return 0

        valid_indices = np.where(valid_mask)[0]
        valid_bvs = bvs[valid_mask]

        # Use searchsorted to find index where breakthrough_bv would be inserted
        idx_in_valid = np.searchsorted(valid_bvs, breakthrough_bv, side='left')

        # Map back to original index
        if idx_in_valid < len(valid_indices):
            idx = valid_indices[idx_in_valid]
        else:
            idx = valid_indices[-1] if len(valid_indices) > 0 else 0
        
        # Clamp to valid range [0, len-1]
        idx = min(max(0, idx), len(bvs) - 1)
        
        # If we're at the end but breakthrough_bv is less than last BV,
        # find the closest BV
        if idx == len(bvs) - 1 and breakthrough_bv < bvs[-1]:
            # Find closest BV value
            closest_idx = np.argmin(np.abs(bvs - breakthrough_bv))
            return closest_idx
        
        return idx
    
    # Universal Enhancement Methods
    
    def calculate_ionic_strength(self, water_composition: Dict[str, float]) -> float:
        """
        Calculate ionic strength from water composition using the formula:
        I = 0.5 * Σ(ci * zi²) where ci is molar concentration and zi is charge.
        
        Args:
            water_composition: Water composition in mg/L
            
        Returns:
            Ionic strength in mol/L
        """
        ionic_strength = 0.0
        
        # Cations with their charges
        cations = [
            ('ca_mg_l', 40.08, 2),    # Ca2+
            ('mg_mg_l', 24.305, 2),   # Mg2+
            ('na_mg_l', 22.99, 1),    # Na+
            ('k_mg_l', 39.098, 1),    # K+
            ('nh4_mg_l', 18.04, 1),   # NH4+
            ('fe2_mg_l', 55.845, 2),  # Fe2+
            ('fe3_mg_l', 55.845, 3),  # Fe3+
        ]
        
        # Anions with their charges
        anions = [
            ('cl_mg_l', 35.45, -1),     # Cl-
            ('so4_mg_l', 96.06, -2),    # SO42-
            ('hco3_mg_l', 61.02, -1),   # HCO3-
            ('co3_mg_l', 60.01, -2),    # CO32-
            ('no3_mg_l', 62.0, -1),     # NO3-
        ]
        
        # Calculate contribution from each ion
        for key, mw, charge in cations + anions:
            conc_mg_l = water_composition.get(key, 0)
            if conc_mg_l > 0:
                conc_mol_l = conc_mg_l / (mw * 1000)  # Convert mg/L to mol/L
                ionic_strength += 0.5 * conc_mol_l * charge ** 2
        
        return ionic_strength
    
    def adjust_selectivity_for_ionic_strength(
        self, 
        base_log_k: float, 
        ionic_strength: float,
        charge_product: int,
        ion_size_parameter: float = 4.5
    ) -> float:
        """
        Adjust log_k based on ionic strength using Davies equation.
        
        The Davies equation is more accurate than Debye-Hückel for I > 0.1 M:
        log γ = -A * z² * (√I / (1 + √I) - 0.3 * I)
        
        For exchange reactions: M^n+ + n*Na-X = M-Xn + n*Na+
        Δlog K = log K(I) - log K(I=0) = Σ(ν_i * z_i²) * f(I)
        
        Args:
            base_log_k: Base selectivity coefficient at I = 0
            ionic_strength: Ionic strength in mol/L
            charge_product: Product of charges involved in exchange
            ion_size_parameter: Ion size parameter (Å)
            
        Returns:
            Adjusted log_k value
        """
        if ionic_strength <= 0:
            return base_log_k
        
        # Davies equation constants
        A = 0.51  # Debye-Hückel constant at 25°C
        
        # Calculate activity coefficient correction
        sqrt_i = np.sqrt(ionic_strength)
        davies_term = A * (sqrt_i / (1 + sqrt_i) - 0.3 * ionic_strength)
        
        # For ion exchange, the correction depends on charge difference
        # For M2+ + 2NaX = MX2 + 2Na+: Δz² = 4 - 2 = 2
        correction = charge_product * davies_term
        
        return base_log_k + correction
    
    def calculate_temperature_correction(
        self, 
        base_log_k: float,
        temp_c: float,
        delta_h_kj_mol: float,
        reference_temp_c: float = 25.0
    ) -> float:
        """
        Apply van't Hoff equation for temperature correction of selectivity.
        
        log(K_T/K_ref) = -ΔH°/(R*ln(10)) * (1/T - 1/T_ref)
        
        Args:
            base_log_k: Base selectivity at reference temperature
            temp_c: Actual temperature in °C
            delta_h_kj_mol: Standard enthalpy of exchange in kJ/mol
            reference_temp_c: Reference temperature in °C (default 25°C)
            
        Returns:
            Temperature-corrected log_k value
        """
        if abs(temp_c - reference_temp_c) < 0.1:
            return base_log_k
        
        # Convert to Kelvin
        temp_k = temp_c + KELVIN_OFFSET
        ref_temp_k = reference_temp_c + KELVIN_OFFSET
        
        # Van't Hoff equation
        # Note: R in kJ/(mol·K), factor of 1000 for J to kJ conversion
        ln10 = 2.303  # ln(10)
        correction = -(delta_h_kj_mol * 1000) / (R_GAS_CONSTANT * ln10) * (1/temp_k - 1/ref_temp_k)
        
        return base_log_k + correction
    
    def calculate_mtz_length(
        self,
        flow_velocity_m_hr: float,
        particle_diameter_mm: float,
        bed_depth_m: float,
        diffusion_coefficient: float = 1e-9,
        resin_capacity_eq_l: float = 2.0,
        feed_concentration_eq_l: float = 0.005
    ) -> float:
        """
        Calculate mass transfer zone length using simplified Klinkenberg equation.
        
        MTZ length depends on:
        - Flow velocity (higher velocity = longer MTZ)
        - Particle size (larger particles = longer MTZ)
        - Diffusion rate (slower diffusion = longer MTZ)
        - Capacity/concentration ratio
        
        Args:
            flow_velocity_m_hr: Linear flow velocity in m/hr
            particle_diameter_mm: Resin particle diameter in mm
            bed_depth_m: Total bed depth in m
            diffusion_coefficient: Effective diffusion coefficient (m²/s)
            resin_capacity_eq_l: Resin capacity in eq/L
            feed_concentration_eq_l: Feed concentration in eq/L
            
        Returns:
            MTZ length in meters
        """
        # Convert units
        particle_diameter_m = particle_diameter_mm / 1000
        flow_velocity_m_s = flow_velocity_m_hr / 3600
        
        # Simplified MTZ correlation
        # Based on: Helfferich & Klein (1970), Multicomponent Chromatography
        reynolds = flow_velocity_m_s * particle_diameter_m / (diffusion_coefficient * 0.4)
        
        # MTZ length increases with Reynolds number and particle size
        mtz_factor = 5.0  # Empirical factor (typically 3-10)
        mtz_length = mtz_factor * particle_diameter_m * (1 + 0.1 * reynolds)
        
        # Adjust for capacity/concentration ratio
        capacity_factor = min(resin_capacity_eq_l / feed_concentration_eq_l, 1000)
        mtz_length *= (1 + np.log10(capacity_factor) / 10)
        
        # Limit MTZ to reasonable fraction of bed depth
        max_mtz = 0.3 * bed_depth_m  # MTZ typically 10-30% of bed
        
        return min(mtz_length, max_mtz)
    
    def apply_capacity_degradation(
        self,
        base_capacity_eq_l: float,
        capacity_factor: float = 1.0,
        cycles_operated: int = 0,
        degradation_rate_per_cycle: float = 0.001
    ) -> float:
        """
        Apply capacity reduction for aged or fouled resins.
        
        Capacity decreases due to:
        - Organic fouling
        - Oxidation damage
        - Physical attrition
        - Incomplete regeneration
        
        Args:
            base_capacity_eq_l: Fresh resin capacity in eq/L
            capacity_factor: Manual capacity factor (0-1)
            cycles_operated: Number of service cycles completed
            degradation_rate_per_cycle: Fractional loss per cycle
            
        Returns:
            Effective capacity in eq/L
        """
        # Apply manual capacity factor
        effective_capacity = base_capacity_eq_l * capacity_factor
        
        # Apply cycle-based degradation
        if cycles_operated > 0:
            cycle_factor = (1 - degradation_rate_per_cycle) ** cycles_operated
            effective_capacity *= max(cycle_factor, 0.5)  # Limit to 50% minimum
        
        return effective_capacity
    
    def calculate_h_form_leakage(
        self,
        influent_na_mg_l: float,
        influent_k_mg_l: float,
        resin_exhaustion_percent: float = 0.0,
        base_na_leakage_percent: float = 2.0,
        base_k_leakage_percent: float = 1.5,
        exhaustion_factor: float = 3.0
    ) -> Dict[str, float]:
        """
        Calculate Na/K leakage for H-form resins.
        
        H-form resins have very high selectivity for H+ but not infinite.
        Leakage increases with resin exhaustion as H+ sites are depleted.
        
        Args:
            influent_na_mg_l: Influent Na concentration in mg/L
            influent_k_mg_l: Influent K concentration in mg/L
            resin_exhaustion_percent: Percent of capacity exhausted (0-100)
            base_na_leakage_percent: Base Na leakage at fresh resin (%)
            base_k_leakage_percent: Base K leakage at fresh resin (%)
            exhaustion_factor: Multiplier for leakage at full exhaustion
            
        Returns:
            Dictionary with Na and K leakage in mg/L
        """
        # Calculate exhaustion multiplier (1.0 at fresh, exhaustion_factor at 100%)
        exhaustion_mult = 1.0 + (exhaustion_factor - 1.0) * (resin_exhaustion_percent / 100)
        
        # Calculate actual leakage percentages
        na_leakage_pct = base_na_leakage_percent * exhaustion_mult
        k_leakage_pct = base_k_leakage_percent * exhaustion_mult
        
        # Calculate leakage concentrations
        na_leakage_mg_l = influent_na_mg_l * (na_leakage_pct / 100)
        k_leakage_mg_l = influent_k_mg_l * (k_leakage_pct / 100)
        
        return {
            'na_mg_l': na_leakage_mg_l,
            'k_mg_l': k_leakage_mg_l,
            'na_leakage_percent': na_leakage_pct,
            'k_leakage_percent': k_leakage_pct,
            'total_leakage_mg_l': na_leakage_mg_l + k_leakage_mg_l
        }
    
    def track_co2_generation(
        self,
        alkalinity_removed_mg_l: float,
        ph_initial: float,
        ph_final: float,
        temperature_c: float = 25.0
    ) -> Dict[str, float]:
        """
        Calculate CO2 generation from alkalinity removal.
        
        When alkalinity (HCO3-) is removed by H-form resins:
        HCO3- + H+ -> H2O + CO2
        
        The CO2 concentration depends on pH and carbonate equilibrium.
        
        Args:
            alkalinity_removed_mg_l: Alkalinity removed as CaCO3 in mg/L
            ph_initial: Initial pH
            ph_final: Final pH after treatment
            temperature_c: Temperature in °C
            
        Returns:
            Dictionary with CO2 generation data
        """
        if alkalinity_removed_mg_l <= 0:
            return {
                'co2_generated_mg_l': 0,
                'co2_partial_pressure_atm': 0,
                'co2_saturation_percent': 0,
                'stripping_required': False
            }
        
        # Convert alkalinity as CaCO3 to HCO3- in mol/L
        # CaCO3 MW = 100.09, HCO3- MW = 61.02
        hco3_removed_mol_l = alkalinity_removed_mg_l / CONFIG.CACO3_MW / 1000
        
        # All removed HCO3- becomes CO2 in H-form exchange
        co2_generated_mol_l = hco3_removed_mol_l
        co2_generated_mg_l = co2_generated_mol_l * CONFIG.CO2_MW * 1000
        
        # Calculate CO2 partial pressure using Henry's law
        # KH for CO2 at 25°C = 29.4 atm·L/mol
        kh_co2 = 29.4 * np.exp(-2400 * (1/(temperature_c + KELVIN_OFFSET) - 1/298.15))
        co2_partial_pressure = co2_generated_mol_l * kh_co2
        
        # CO2 saturation at 1 atm and given temperature
        co2_saturation_mol_l = 1.0 / kh_co2
        co2_saturation_percent = (co2_generated_mol_l / co2_saturation_mol_l) * 100
        
        return {
            'co2_generated_mg_l': co2_generated_mg_l,
            'co2_partial_pressure_atm': co2_partial_pressure,
            'co2_saturation_percent': co2_saturation_percent,
            'stripping_required': co2_saturation_percent > 80,  # Rule of thumb
            'ph_depression': ph_initial - ph_final
        }
    
    def generate_enhanced_exchange_species(
        self,
        resin_type: str,
        water_composition: Dict[str, float],
        temperature_c: float = 25.0,
        capacity_factor: float = 1.0,
        enable_ionic_strength: bool = True,
        enable_temperature: bool = True
    ) -> str:
        """
        Generate EXCHANGE_SPECIES block with all enhancements applied.
        
        This method creates the complete EXCHANGE_SPECIES section with:
        - Ionic strength corrections
        - Temperature corrections
        - Appropriate selectivity coefficients for each resin type
        
        Args:
            resin_type: Type of resin ('SAC', 'WAC_Na', 'WAC_H')
            water_composition: Feed water composition for ionic strength
            temperature_c: Operating temperature
            capacity_factor: Capacity degradation factor
            enable_ionic_strength: Apply ionic strength corrections
            enable_temperature: Apply temperature corrections
            
        Returns:
            Complete EXCHANGE_SPECIES block as string
        """
        # Calculate ionic strength if enabled
        ionic_strength = 0.0
        if enable_ionic_strength:
            ionic_strength = self.calculate_ionic_strength(water_composition)
            logger.info(f"Calculated ionic strength: {ionic_strength:.4f} mol/L")
        
        # Start building EXCHANGE_SPECIES block
        exchange_species = "# Enhanced exchange reactions with corrections\n"
        exchange_species += "EXCHANGE_SPECIES\n"
        
        # Get exchange enthalpies from CONFIG
        enthalpies = CONFIG.get_exchange_enthalpies()
        
        # Define base reactions and selectivities based on resin type
        if resin_type == 'SAC':
            # SAC uses Na+ as reference (log_k = 0)
            reactions = [
                ("X- = X-", 0.0, 0, 0),  # Identity reaction for master species
                ("Na+ + X- = NaX", 0.0, 0, 0),  # Reference
                ("Ca+2 + 2X- = CaX2", 0.8, 2, enthalpies.get('Ca_Na', -8.0)),  # PHREEQC database value
                ("Mg+2 + 2X- = MgX2", 0.6, 2, enthalpies.get('Mg_Na', -6.0)),  # PHREEQC database value
                ("K+ + X- = KX", 1.5, 0, enthalpies.get('K_Na', -2.0)),   # Moderate selectivity for K
                ("H+ + X- = HX", 1.3, 0, enthalpies.get('H_Na', -3.0)),   # Moderate selectivity for H
            ]
            
        elif resin_type == 'WAC_Na':
            # WAC Na-form uses Na+ as reference
            reactions = [
                ("X- = X-", 0.0, 0, 0),  # Identity reaction for master species
                ("Na+ + X- = NaX", 0.0, 0, 0),  # Reference
                ("Ca+2 + 2X- = CaX2", CONFIG.WAC_LOGK_CA_NA, 2, enthalpies.get('Ca_Na', -8.0)),
                ("Mg+2 + 2X- = MgX2", CONFIG.WAC_LOGK_MG_NA, 2, enthalpies.get('Mg_Na', -6.0)),
                ("K+ + X- = KX", CONFIG.WAC_LOGK_K_NA, 0, enthalpies.get('K_Na', -2.0)),
                ("H+ + X- = HX", CONFIG.WAC_LOGK_H_NA, 0, enthalpies.get('H_Na', -12.0)),
            ]
            
        elif resin_type == 'WAC_H':
            # WAC H-form uses H+ as reference
            reactions = [
                ("X- = X-", 0.0, 0, 0),  # Identity reaction for master species
                ("H+ + X- = HX", 0.0, 0, 0),  # Reference
                ("Ca+2 + 2HX = CaX2 + 2H+", CONFIG.WAC_LOGK_CA_H, 2, enthalpies.get('Ca_H', 4.0)),
                ("Mg+2 + 2HX = MgX2 + 2H+", CONFIG.WAC_LOGK_MG_H, 2, enthalpies.get('Mg_H', 3.0)),
                ("Na+ + HX = NaX + H+", CONFIG.WAC_LOGK_NA_H, 0, enthalpies.get('Na_H', 3.0)),
                ("K+ + HX = KX + H+", CONFIG.WAC_LOGK_K_H, 0, enthalpies.get('K_H', 2.0)),
            ]
        else:
            raise ValueError(f"Unknown resin type: {resin_type}")
        
        # Generate each reaction with corrections
        for reaction, base_log_k, charge_product, delta_h in reactions:
            log_k = base_log_k
            
            # Apply ionic strength correction
            if enable_ionic_strength and ionic_strength > 0.001:
                log_k = self.adjust_selectivity_for_ionic_strength(
                    log_k, ionic_strength, charge_product
                )
            
            # Apply temperature correction
            if enable_temperature and abs(temperature_c - 25.0) > 0.1:
                log_k = self.calculate_temperature_correction(
                    log_k, temperature_c, delta_h
                )
            
            # Write reaction
            exchange_species += f"    {reaction}\n"
            exchange_species += f"        log_k {log_k:.3f}\n"
            
            # Add activity coefficient parameters for major ions
            if "Ca" in reaction:
                exchange_species += "        -gamma 5.0 0.165\n"
            elif "Mg" in reaction:
                exchange_species += "        -gamma 5.5 0.2\n"
            elif "K" in reaction:
                exchange_species += "        -gamma 3.5 0.015\n"
            elif "Na" in reaction and resin_type != 'SAC':  # SAC Na is reference
                exchange_species += "        -gamma 4.0 0.075\n"
            elif "H" in reaction and resin_type != 'WAC_H':  # WAC_H H is reference
                exchange_species += "        -gamma 9.0 0.0\n"
            
            exchange_species += "\n"
        
        return exchange_species
    
    @abstractmethod
    def run_simulation(self, input_data: Any) -> Any:
        """
        Run the specific ion exchange simulation.
        
        Must be implemented by subclasses (SAC, WAC_Na, WAC_H, etc.)
        """
        pass
    
    def _log_simulation_summary(self, result: Dict[str, Any], resin_type: str):
        """Log simulation results summary."""
        logger.info(f"{resin_type} simulation complete:")
        logger.info(f"  Status: {result.get('status', 'unknown')}")
        logger.info(f"  Breakthrough: {result.get('breakthrough_bv', 0):.1f} BV")
        logger.info(f"  Service time: {result.get('service_time_hours', 0):.1f} hours")
        logger.info(f"  Breakthrough reached: {result.get('breakthrough_reached', False)}")
        
        if result.get('warnings'):
            for warning in result['warnings']:
                logger.warning(f"  {warning}")
