"""
Direct PHREEQC Engine - Calls PHREEQC executable directly via subprocess
Bypasses PhreeqPython wrapper to avoid exchange modeling issues
"""

import subprocess
import tempfile
import os
import re
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
import functools
import platform
import sys
from ..species_alias import phreeqc_to_pyomo, pyomo_to_phreeqc

logger = logging.getLogger(__name__)


class DirectPhreeqcEngine:
    """
    Direct interface to PHREEQC executable, bypassing Python wrapper
    """
    
    @staticmethod
    def get_platform_path(path: str) -> str:
        """
        Convert paths for platform compatibility.
        
        Args:
            path: Path to convert
            
        Returns:
            Platform-appropriate path
        """
        if not path:
            return path
            
        # Check if we're in WSL
        is_wsl = 'microsoft' in platform.uname().release.lower() if hasattr(platform.uname(), 'release') else False
        
        if sys.platform == 'win32':
            # Running on Windows - use as-is
            return path
        elif is_wsl:
            # Running in WSL - convert Windows paths if needed
            if path.startswith('C:\\') or path.startswith('c:\\'):
                # Convert C:\path to /mnt/c/path
                converted = path.replace('C:\\', '/mnt/c/').replace('c:\\', '/mnt/c/').replace('\\', '/')
                logger.debug(f"Converted Windows path to WSL: {path} -> {converted}")
                return converted
        
        # Unix/Linux or already correct path
        return path
    
    def __init__(self, phreeqc_path: Optional[str] = None, keep_temp_files: bool = False, default_timeout_s: int = 600):
        """
        Initialize direct PHREEQC interface
        
        Args:
            phreeqc_path: Path to PHREEQC executable. If None, searches common locations
            keep_temp_files: If True, don't delete temporary files (for debugging)
            default_timeout_s: Default timeout for PHREEQC subprocess calls (seconds). 
                Default is 600s (10 minutes) for complex simulations
        """
        # Get timeout from environment or use default
        self.default_timeout_s = int(os.environ.get('PHREEQC_RUN_TIMEOUT_S', str(default_timeout_s)))
        logger.info(f"PHREEQC subprocess timeout: {self.default_timeout_s} seconds")
        
        self.phreeqc_exe = self._find_phreeqc_executable(phreeqc_path)
        if not self.phreeqc_exe:
            raise RuntimeError("PHREEQC executable not found. Please install PHREEQC or provide path.")
        
        self.keep_temp_files = keep_temp_files
        self.temp_dirs = []  # Track temporary directories for cleanup
        logger.info(f"Using PHREEQC executable: {self.phreeqc_exe}")
        
        # Database paths
        self.default_database = self._find_database_path()
        
        # Fallback to CONFIG if database not found
        if not self.default_database:
            logger.warning("Database not found via standard paths, trying CONFIG")
            try:
                from tools.core_config import CONFIG
                config_db = str(CONFIG.get_phreeqc_database())
                if config_db and self._path_exists_compatible(config_db):
                    self.default_database = config_db
                    logger.info(f"Found database via CONFIG: {self.default_database}")
            except Exception as e:
                logger.warning(f"Failed to get database from CONFIG: {e}")
        
        if self.default_database:
            logger.info(f"Using PHREEQC database: {self.default_database}")
        else:
            raise RuntimeError(
                "PHREEQC database not found. Please set PHREEQC_DATABASE environment variable "
                "to the full path of phreeqc.dat"
            )
        
    def _is_windows_path(self, path: str) -> bool:
        """Check if path is a Windows-style path"""
        if not path:
            return False
        # Check for drive letter or common Windows executable extensions
        return bool(re.match(r'^[A-Za-z]:\\', path)) or path.lower().endswith(('.exe', '.bat', '.cmd'))
    
    def _is_posix_path(self, path: str) -> bool:
        """Check if path is a POSIX-style path"""
        if not path:
            return False
        return path.startswith('/')
    
    def _path_exists_compatible(self, path: str) -> bool:
        """Check if path exists and is compatible with current OS"""
        if not path:
            return False
        
        # Check if we're in WSL
        is_wsl = 'microsoft' in platform.uname().release.lower() if hasattr(platform.uname(), 'release') else False
        
        if is_wsl:
            # WSL can handle both Windows and Unix paths
            # Convert Windows paths to WSL format if needed
            check_path = self.get_platform_path(path)
        elif os.name == 'nt':
            # On Windows, reject POSIX paths
            if self._is_posix_path(path):
                logger.debug(f"Rejecting POSIX path on Windows: {path}")
                return False
            check_path = path
        else:
            # On Unix/Linux, reject Windows paths
            if self._is_windows_path(path):
                logger.debug(f"Rejecting Windows path on Unix: {path}")
                return False
            check_path = path
        
        # Check if path actually exists
        exists = os.path.exists(check_path)
        if not exists:
            logger.debug(f"Path does not exist: {check_path}")
        return exists
    
    def _find_phreeqc_executable(self, custom_path: Optional[str] = None) -> Optional[str]:
        """Find PHREEQC executable in common locations (OS-aware)"""
        candidates = []
        
        # Add custom path if provided
        if custom_path:
            candidates.append(custom_path)
        
        # Check PHREEQC_EXE environment variable
        env_phreeqc = os.environ.get('PHREEQC_EXE')
        if env_phreeqc:
            candidates.append(env_phreeqc)
        
        # Add OS-specific search paths
        if os.name == 'nt':
            # Windows paths
            candidates.extend([
                r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\bin\phreeqc.bat",
                r"C:\Program Files\USGS\phreeqc-3.8.6-17096-x64\bin\phreeqc.bat",
                r"C:\Program Files\USGS\phreeqc\bin\phreeqc.bat",
                r"C:\Program Files (x86)\USGS\phreeqc\bin\phreeqc.bat",
                r"C:\phreeqc\bin\phreeqc.bat",
                r"C:\Program Files\phreeqc\phreeqc.exe",
            ])
        else:
            # Unix/Linux/WSL paths
            # Get home directory dynamically
            home_dir = os.path.expanduser("~")
            candidates.extend([
                # User symlinks (highest priority for WSL)
                os.path.join(home_dir, "phreeqc", "bin", "phreeqc"),
                # Standard Unix locations
                "/usr/local/bin/phreeqc",
                "/usr/bin/phreeqc",
                # Legacy location
                "/home/hvksh/process/phreeqc/bin/phreeqc",
                # Direct Windows path from WSL (fallback)
                "/mnt/c/Program Files/USGS/phreeqc-3.8.6-17100-x64/bin/Release/phreeqc.exe",
            ])
        
        # Check each candidate
        for candidate in candidates:
            if candidate and self._path_exists_compatible(candidate):
                logger.info(f"Found PHREEQC executable: {candidate}")
                return candidate
        
        # Try system PATH as last resort
        try:
            cmd = "where" if os.name == 'nt' else "which"
            result = subprocess.run([cmd, "phreeqc"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                path = result.stdout.strip()
                if self._path_exists_compatible(path):
                    logger.info(f"Found PHREEQC in PATH: {path}")
                    return path
        except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.debug(f"Failed to find phreeqc via {cmd}: {e}")
        
        # No valid executable found
        logger.error(
            f"PHREEQC executable not found for {os.name} platform. "
            f"Please set PHREEQC_EXE environment variable to a valid executable path."
        )
        return None
    
    def _find_database_path(self) -> Optional[str]:
        """Find PHREEQC database file (OS-aware)"""
        candidates = []
        
        # Check PHREEQC_DATABASE environment variable first
        env_database = os.environ.get('PHREEQC_DATABASE')
        if env_database:
            candidates.append(env_database)
        
        # Add OS-specific database paths
        if os.name == 'nt':
            # Windows paths
            candidates.extend([
                r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\database\phreeqc.dat",
                r"C:\Program Files\USGS\phreeqc-3.8.6-17096-x64\database\phreeqc.dat",
                r"C:\Program Files\USGS\phreeqc\database\phreeqc.dat",
                r"C:\Program Files (x86)\USGS\phreeqc\database\phreeqc.dat",
                r"C:\phreeqc\database\phreeqc.dat",
            ])
            # Try relative to executable if found
            if self.phreeqc_exe:
                exe_dir = os.path.dirname(self.phreeqc_exe)
                candidates.append(os.path.join(exe_dir, "..", "database", "phreeqc.dat"))
        else:
            # Unix/Linux/WSL paths
            # Get home directory dynamically
            home_dir = os.path.expanduser("~")
            candidates.extend([
                # User symlinks (highest priority for WSL)
                os.path.join(home_dir, "phreeqc", "database", "phreeqc.dat"),
                # Standard Unix locations
                "/usr/local/share/phreeqc/database/phreeqc.dat",
                "/usr/share/phreeqc/database/phreeqc.dat",
                # Legacy location
                "/home/hvksh/process/phreeqc/share/doc/phreeqc/database/phreeqc.dat",
                # Direct Windows path from WSL (fallback)
                "/mnt/c/Program Files/USGS/phreeqc-3.8.6-17100-x64/database/phreeqc.dat",
            ])
        
        # Check each candidate
        for candidate in candidates:
            if candidate and self._path_exists_compatible(candidate):
                logger.info(f"Found PHREEQC database: {candidate}")
                return candidate
        
        # No valid database found
        logger.error(
            f"PHREEQC database not found for {os.name} platform. "
            f"Please set PHREEQC_DATABASE environment variable to the full path of phreeqc.dat"
        )
        return None
    
    def __enter__(self):
        """Context manager entry - returns self for use in 'with' statements."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup of all temporary directories."""
        self.cleanup()
        # Don't suppress exceptions
        return False
    
    def cleanup(self):
        """Clean up all temporary directories created during this session."""
        import shutil
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")
        self.temp_dirs.clear()
    
    def run_phreeqc(self, input_string: str, database: Optional[str] = None, timeout_s: Optional[int] = None) -> Tuple[str, str]:
        """
        Run PHREEQC with given input string
        
        Args:
            input_string: PHREEQC input commands
            database: Path to database file (uses default if None)
            timeout_s: Timeout in seconds (uses default if None)
            
        Returns:
            Tuple of (output_string, selected_output_string)
        """
        # Use default database if none specified
        if database is None:
            database = self.default_database
        
        # Additional validation for empty database string
        if not database or database == "":
            logger.error("Database path is empty, attempting to re-fetch from CONFIG")
            try:
                from tools.core_config import CONFIG
                database = str(CONFIG.get_phreeqc_database())
                logger.info(f"Re-fetched database path: {database}")
            except Exception as e:
                logger.error(f"Failed to re-fetch database: {e}")
                database = None
        
        # Validate database exists and is compatible with OS
        if not self._path_exists_compatible(database):
            raise FileNotFoundError(
                f"PHREEQC database not found or incompatible with {os.name}: {database}\n"
                f"Please set PHREEQC_DATABASE environment variable to a valid database path."
            )
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix='phreeqc_')
        self.temp_dirs.append(temp_dir)
        
        # Write input file with UTF-8 encoding
        input_path = os.path.join(temp_dir, 'input.pqi')
        with open(input_path, 'w', encoding='utf-8') as f:
            f.write(input_string)
        
        # Log input for debugging (first 20 lines only)
        logger.debug("PHREEQC input (first 20 lines):")
        for i, line in enumerate(input_string.split('\n')[:20]):
            logger.debug(f"  {i+1:3d}: {line}")
        
        output_path = os.path.join(temp_dir, 'output.pqo')
        
        # Determine selected output filename
        selected_filename = 'transport.sel'  # Default
        if '-file' in input_string:
            match = re.search(r'-file\s+(\S+)', input_string)
            if match:
                selected_filename = match.group(1)
        
        selected_path = os.path.join(temp_dir, selected_filename)
        
        try:
            # Prepare command based on OS
            # IMPORTANT: Never use os.chdir() - use cwd parameter instead
            if os.name == 'nt' and self.phreeqc_exe.lower().endswith('.bat'):
                # Windows .bat file - use shell=True with proper quoting
                cmd = f'"{self.phreeqc_exe}" "{input_path}" "{output_path}" "{database}"'
                shell = True
            else:
                # Unix or Windows .exe - use list format
                cmd = [self.phreeqc_exe, input_path, output_path, database]
                shell = False
            
            # Determine timeout
            run_timeout = timeout_s or self.default_timeout_s
            
            logger.debug(f"Running PHREEQC with timeout={run_timeout}s in {temp_dir}")
            logger.debug(f"Command: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
            
            # Run PHREEQC with cwd set to temp directory (no os.chdir!)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=shell,
                cwd=temp_dir,  # Critical: use cwd instead of os.chdir()
                timeout=run_timeout,
                encoding='latin-1' if os.name == 'nt' else 'utf-8'  # Use latin-1 on Windows
            )
            
            logger.debug(f"Return code: {result.returncode}")
            if result.stdout:
                logger.debug(f"Stdout (first 200 chars): {result.stdout[:200]}")
            if result.stderr:
                logger.debug(f"Stderr (first 200 chars): {result.stderr[:200]}")
            
            if result.returncode != 0:
                logger.error(f"PHREEQC failed with return code {result.returncode}")
                logger.error(f"Stderr: {result.stderr}")
                raise RuntimeError(f"PHREEQC failed (code {result.returncode}): {result.stderr}")
            
            # Check what files were created
            logger.debug(f"Files created in temp directory:")
            for f in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, f)
                if os.path.isfile(file_path):
                    logger.debug(f"  - {f} ({os.path.getsize(file_path)} bytes)")
            
            # Read output files with appropriate encoding
            encoding = 'latin-1' if os.name == 'nt' else 'utf-8'
            
            output_string = ""
            if os.path.exists(output_path):
                with open(output_path, 'r', encoding=encoding, errors='ignore') as f:
                    output_string = f.read()
                logger.debug(f"Output file read: {len(output_string)} characters")
            else:
                logger.warning(f"Output file not found: {output_path}")
            
            selected_string = ""
            if os.path.exists(selected_path):
                with open(selected_path, 'r', encoding=encoding, errors='ignore') as f:
                    selected_string = f.read()
                logger.debug(f"Selected output read: {len(selected_string)} characters")
            else:
                logger.warning(f"Selected output file not found: {selected_path}")
            
            return output_string, selected_string
        
        except subprocess.TimeoutExpired:
            logger.error(f"PHREEQC subprocess timed out after {run_timeout} seconds")
            raise RuntimeError(
                f"PHREEQC simulation timed out after {run_timeout} seconds. "
                f"This is normal for complex ion exchange simulations which can take 5+ minutes. "
                f"Set PHREEQC_RUN_TIMEOUT_S environment variable to a higher value (e.g., 600 for 10 minutes)."
            )
            
        finally:
            # Clean up temporary files (unless debugging)
            if not self.keep_temp_files:
                # Remove from tracking list and clean up immediately
                if temp_dir in self.temp_dirs:
                    self.temp_dirs.remove(temp_dir)
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                except (OSError, PermissionError) as e:
                    logger.debug(f"Failed to clean up temp directory {temp_dir}: {e}")
                    # Re-add to list for later cleanup attempt
                    self.temp_dirs.append(temp_dir)
            else:
                logger.info(f"Temp files kept in: {temp_dir}")
    
    def parse_selected_output(self, selected_string: str) -> List[Dict]:
        """
        Parse PHREEQC selected output into list of dictionaries
        
        Args:
            selected_string: Selected output string from PHREEQC
            
        Returns:
            List of dictionaries with column headers as keys
        """
        if not selected_string.strip():
            return []
        
        lines = selected_string.strip().split('\n')
        if len(lines) < 2:
            return []
        
        # First line is headers
        headers = lines[0].strip().split('\t')
        
        # Apply species mapping to headers
        from ..species_alias import PHREEQC_TO_PYOMO
        mapped_headers = []
        for header in headers:
            # Strip leading/trailing spaces from fixed-width PHREEQC headers
            header = header.strip()
            
            # Check if header contains a species name that needs mapping
            # Headers might be like "Ca+2_mg/L" or just "Ca+2"
            mapped_header = header
            for phreeqc_species, pyomo_species in PHREEQC_TO_PYOMO.items():
                if phreeqc_species in header:
                    mapped_header = header.replace(phreeqc_species, pyomo_species)
                    break
            mapped_headers.append(mapped_header)
        
        # Parse data lines
        data = []
        for line in lines[1:]:
            if line.strip():
                values = line.strip().split('\t')
                # Handle cases where values might have fewer entries than headers
                # (e.g., USER_PUNCH values might be missing)
                row = {}
                for i, header in enumerate(mapped_headers):
                    if i < len(values) and values[i].strip():
                        try:
                            # Try to convert to float
                            row[header] = float(values[i])
                        except ValueError:
                            # Keep as string
                            row[header] = values[i]
                    else:
                        # Missing value - set to None
                        row[header] = None
                data.append(row)
        
        return data
    
    def extract_exchange_composition(self, output_string: str) -> Dict:
        """
        Extract exchange composition from PHREEQC output
        
        Args:
            output_string: Full PHREEQC output
            
        Returns:
            Dictionary with exchange species and their moles
        """
        exchange_data = {}
        
        # Look for Exchange composition section
        lines = output_string.split('\n')
        in_exchange = False
        
        for i, line in enumerate(lines):
            if "Exchange composition" in line:
                in_exchange = True
                continue
            
            if in_exchange:
                # Look for end of section
                if line.strip() == "" or "Solution composition" in line:
                    break
                
                # Parse exchange species lines
                # Format: "X             1.000e-01 mol"
                # or:     "NaX           9.876e-02"
                match = re.match(r'\s*(\w+)\s+([\d.e+-]+)', line)
                if match:
                    species = match.group(1)
                    moles = float(match.group(2))
                    exchange_data[species] = moles
        
        return exchange_data
    
    def run_ix_simulation(self, 
                         input_string: str,
                         feed_ca: float,
                         feed_mg: float) -> Dict:
        """
        Run ion exchange simulation and extract results
        
        Args:
            input_string: PHREEQC input with TRANSPORT block
            feed_ca: Feed Ca concentration (mg/L)
            feed_mg: Feed Mg concentration (mg/L)
            
        Returns:
            Dictionary with breakthrough results
        """
        # Run PHREEQC
        output, selected = self.run_phreeqc(input_string)
        
        # Parse selected output
        data = self.parse_selected_output(selected)
        
        if not data:
            logger.error("No selected output data from PHREEQC")
            return {'error': 'No output data'}
        
        # Extract breakthrough curves
        bed_volumes = []
        ca_effluent = []
        mg_effluent = []
        na_effluent = []
        
        for row in data:
            # Skip initial equilibration rows (step=-99)
            if 'step' in row and row['step'] == -99:
                logger.debug(f"Skipping initial equilibration row: step={row['step']}")
                continue
                
            # Headers are now stripped, so check for exact 'BV' key
            if 'BV' in row:
                bed_volumes.append(row['BV'])
                # Look for mapped Pyomo format (Ca_2+_mg/L) first, then PHREEQC format, then simple format
                ca_value = row.get('Ca_2+_mg/L', row.get('Ca+2_mg/L', row.get('Ca_mg/L', 0)))
                mg_value = row.get('Mg_2+_mg/L', row.get('Mg+2_mg/L', row.get('Mg_mg/L', 0)))
                na_value = row.get('Na_+_mg/L', row.get('Na+_mg/L', row.get('Na_mg/L', 0)))
                
                ca_effluent.append(ca_value)
                mg_effluent.append(mg_value)
                na_effluent.append(na_value)
                
                # Debug logging to understand what columns we have
                if len(bed_volumes) == 1:  # Only log once
                    logger.debug(f"Available columns in row: {list(row.keys())}")
                    logger.debug(f"Ca value found: {ca_value}, Mg value found: {mg_value}")
        
        # Find breakthrough points (5% of feed)
        ca_breakthrough = None
        mg_breakthrough = None
        
        for i, bv in enumerate(bed_volumes):
            if ca_breakthrough is None and ca_effluent[i] > 0.05 * feed_ca:
                ca_breakthrough = bv
            if mg_breakthrough is None and mg_effluent[i] > 0.05 * feed_mg:
                mg_breakthrough = bv
        
        # Extract exchange composition
        exchange_comp = self.extract_exchange_composition(output)
        
        results = {
            'bed_volumes': bed_volumes,
            'effluent_Ca_mg_L': ca_effluent,
            'effluent_Mg_mg_L': mg_effluent,
            'effluent_Na_mg_L': na_effluent,
            'Ca_breakthrough_BV': ca_breakthrough,
            'Mg_breakthrough_BV': mg_breakthrough,
            'exchange_composition': exchange_comp,
            'model_type': 'DIRECT_PHREEQC'
        }
        
        return results


# Singleton pattern for PHREEQC engine
@functools.lru_cache(maxsize=1)
def get_phreeqc_engine(keep_temp_files: bool = False, default_timeout_s: int = 600) -> DirectPhreeqcEngine:
    """
    Get singleton PHREEQC engine instance.
    
    This ensures only one PHREEQC engine is created per process,
    preventing multiple DLL/executable instances and reducing resource usage.
    
    Args:
        keep_temp_files: If True, don't delete temporary files (for debugging)
        default_timeout_s: Default timeout for PHREEQC subprocess calls
        
    Returns:
        Singleton DirectPhreeqcEngine instance
    """
    # Try to get PHREEQC path from centralized config
    try:
        from tools.core_config import CONFIG
        phreeqc_path = str(CONFIG.get_phreeqc_exe())
    except ImportError:
        # Fallback - let DirectPhreeqcEngine find it
        phreeqc_path = None
    
    return DirectPhreeqcEngine(
        phreeqc_path=phreeqc_path,
        keep_temp_files=keep_temp_files,
        default_timeout_s=default_timeout_s
    )