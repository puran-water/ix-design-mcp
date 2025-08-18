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
from ..species_alias import phreeqc_to_pyomo, pyomo_to_phreeqc

logger = logging.getLogger(__name__)


class DirectPhreeqcEngine:
    """
    Direct interface to PHREEQC executable, bypassing Python wrapper
    """
    
    def __init__(self, phreeqc_path: Optional[str] = None, keep_temp_files: bool = False):
        """
        Initialize direct PHREEQC interface
        
        Args:
            phreeqc_path: Path to PHREEQC executable. If None, searches common locations
            keep_temp_files: If True, don't delete temporary files (for debugging)
        """
        self.phreeqc_exe = self._find_phreeqc_executable(phreeqc_path)
        if not self.phreeqc_exe:
            raise RuntimeError("PHREEQC executable not found. Please install PHREEQC or provide path.")
        
        self.keep_temp_files = keep_temp_files
        self.temp_dirs = []  # Track temporary directories for cleanup
        logger.info(f"Using PHREEQC executable: {self.phreeqc_exe}")
        
        # Database paths
        self.database_dir = self._find_database_dir()
        if self.database_dir and os.path.exists(os.path.join(self.database_dir, "phreeqc.dat")):
            self.default_database = os.path.join(self.database_dir, "phreeqc.dat")
        else:
            # Fallback to standard location
            self.default_database = r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\database\phreeqc.dat"
        
    def _find_phreeqc_executable(self, custom_path: Optional[str] = None) -> Optional[str]:
        """Find PHREEQC executable in common locations"""
        if custom_path and os.path.exists(custom_path):
            return custom_path
        
        # Common locations to search
        search_paths = [
            r"C:\Program Files\USGS\phreeqc\bin\phreeqc.bat",
            r"C:\Program Files (x86)\USGS\phreeqc\bin\phreeqc.bat",
            r"C:\phreeqc\bin\phreeqc.bat",
            r"C:\Program Files\phreeqc\phreeqc.exe",
            r"C:\Program Files (x86)\phreeqc\phreeqc.exe",
            "/home/hvksh/process/phreeqc/bin/phreeqc",
            "/usr/local/bin/phreeqc",
            "/usr/bin/phreeqc",
            "phreeqc",  # Try PATH
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        # Try using 'which' or 'where' command
        try:
            result = subprocess.run(["where" if os.name == 'nt' else "which", "phreeqc"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Failed to find phreeqc via system path: {e}")
            pass
        
        return None
    
    def _find_database_dir(self) -> str:
        """Find PHREEQC database directory"""
        # Common database locations
        search_dirs = [
            r"C:\Program Files\USGS\phreeqc\database",
            r"C:\Program Files (x86)\USGS\phreeqc\database",
            r"C:\phreeqc\database",
            "/usr/local/share/phreeqc/database",
            "/usr/share/phreeqc/database",
            os.path.dirname(self.phreeqc_exe),  # Same dir as executable
        ]
        
        for dir_path in search_dirs:
            if os.path.exists(dir_path) and os.path.exists(os.path.join(dir_path, "phreeqc.dat")):
                return dir_path
        
        # Default to executable directory
        return os.path.dirname(self.phreeqc_exe)
    
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
    
    def run_phreeqc(self, input_string: str, database: Optional[str] = None) -> Tuple[str, str]:
        """
        Run PHREEQC with given input string
        
        Args:
            input_string: PHREEQC input commands
            database: Path to database file (uses default if None)
            
        Returns:
            Tuple of (output_string, selected_output_string)
        """
        # Use default database if none specified
        if database is None:
            database = self.default_database
        
        # Create temporary directory and files
        temp_dir = tempfile.mkdtemp(prefix='phreeqc_')
        # Track for cleanup
        self.temp_dirs.append(temp_dir)
        
        # Write input file with UTF-8 encoding
        input_path = os.path.join(temp_dir, 'input.pqi')
        with open(input_path, 'w', encoding='utf-8') as f:
            f.write(input_string)
        
        # Log input for debugging
        logger.debug("PHREEQC input:")
        for i, line in enumerate(input_string.split('\n')[:50]):  # First 50 lines
            logger.debug(f"  {i+1:3d}: {line}")
        
        output_path = os.path.join(temp_dir, 'output.pqo')
        
        # PHREEQC will create selected output based on SELECTED_OUTPUT filename
        # We need to check what filename was specified in the input
        selected_filename = 'transport.sel'  # Default
        if '-file' in input_string:
            # Extract filename from SELECTED_OUTPUT block
            import re
            match = re.search(r'-file\s+(\S+)', input_string)
            if match:
                selected_filename = match.group(1)
        
        selected_path = os.path.join(temp_dir, selected_filename)
        
        try:
            # Change to temp directory and run PHREEQC
            # This ensures PHREEQC creates files in the right place
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            
            try:
                # Run PHREEQC with relative paths
                cmd = [self.phreeqc_exe, 'input.pqi', 'output.pqo', database]
                
                logger.debug(f"Running in {temp_dir}: {' '.join(cmd)}")
                logger.debug(f"Input file exists: {os.path.exists('input.pqi')}")
                logger.debug(f"Database exists: {os.path.exists(database)}")
                
                # Use shell=True on Windows for .bat files
                shell = os.name == 'nt' and self.phreeqc_exe.endswith('.bat')
                result = subprocess.run(cmd, capture_output=True, text=True, shell=shell)
            finally:
                os.chdir(original_dir)
            
            logger.debug(f"Return code: {result.returncode}")
            if result.stdout:
                logger.debug(f"Stdout: {result.stdout[:200]}")
            if result.stderr:
                logger.debug(f"Stderr: {result.stderr[:200]}")
            
            if result.returncode != 0:
                logger.error(f"PHREEQC error: {result.stderr}")
                raise RuntimeError(f"PHREEQC failed: {result.stderr}")
            
            # Check what files were created
            logger.debug(f"Files in temp dir after PHREEQC:")
            for f in os.listdir(temp_dir):
                logger.debug(f"  - {f} ({os.path.getsize(os.path.join(temp_dir, f))} bytes)")
            
            # Read output
            output_string = ""
            if os.path.exists(output_path):
                with open(output_path, 'r', errors='ignore') as f:
                    output_string = f.read()
                logger.debug(f"Output file size: {len(output_string)} chars")
            else:
                logger.warning(f"Output file not found: {output_path}")
            
            # Read selected output
            selected_string = ""
            if os.path.exists(selected_path):
                with open(selected_path, 'r', errors='ignore') as f:
                    selected_string = f.read()
                logger.debug(f"Selected output found: {len(selected_string)} chars")
            else:
                logger.warning(f"No selected output found at {selected_path}")
            
            return output_string, selected_string
            
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
def get_phreeqc_engine(keep_temp_files: bool = False) -> DirectPhreeqcEngine:
    """
    Get singleton PHREEQC engine instance.
    
    This ensures only one PHREEQC engine is created per process,
    preventing multiple DLL/executable instances and reducing resource usage.
    
    Args:
        keep_temp_files: If True, don't delete temporary files (for debugging)
        
    Returns:
        Singleton DirectPhreeqcEngine instance
    """
    # Try to get PHREEQC path from centralized config
    try:
        from watertap_ix_transport.transport_core.tools.core_config import CONFIG
        phreeqc_path = str(CONFIG.get_phreeqc_exe())
    except ImportError:
        # Fallback if core_config not available
        phreeqc_path = None
    
    return DirectPhreeqcEngine(
        phreeqc_path=phreeqc_path,
        keep_temp_files=keep_temp_files
    )