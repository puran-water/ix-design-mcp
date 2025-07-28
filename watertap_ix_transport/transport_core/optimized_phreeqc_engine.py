"""
Optimized PHREEQC Engine - Batch processing and caching for better performance

Wraps DirectPhreeqcEngine with optimizations:
- Batch multiple timesteps into single PHREEQC calls
- Cache results for identical inputs
- Reuse temporary directories when possible
"""

import os
import logging
import hashlib
import json
from typing import Dict, List, Optional, Tuple, Any
from functools import lru_cache
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

from .direct_phreeqc_engine import DirectPhreeqcEngine

logger = logging.getLogger(__name__)


class OptimizedPhreeqcEngine:
    """
    Optimized PHREEQC interface with batch processing and caching
    
    Key optimizations:
    - Batch multiple timesteps/cells into single PHREEQC calls
    - LRU cache for repeated calculations
    - Process pool for parallel execution
    - Minimized file I/O overhead
    """
    
    def __init__(
        self, 
        phreeqc_path: Optional[str] = None,
        cache_size: int = 128,
        max_workers: Optional[int] = None
    ):
        """
        Initialize optimized engine
        
        Args:
            phreeqc_path: Path to PHREEQC executable
            cache_size: Number of cached results to keep
            max_workers: Max parallel workers (None = CPU count)
        """
        self.base_engine = DirectPhreeqcEngine(
            phreeqc_path=phreeqc_path,
            keep_temp_files=False
        )
        self.cache_size = cache_size
        self.max_workers = max_workers
        
        # Set up caching
        self._setup_cache()
        
    def _setup_cache(self):
        """Set up LRU cache for results"""
        # Create cached version of run_phreeqc
        @lru_cache(maxsize=self.cache_size)
        def _cached_run(input_hash: str, database: str) -> Tuple[str, str]:
            # Reconstruct input from hash lookup
            input_string = self._hash_to_input.get(input_hash, "")
            if not input_string:
                raise ValueError("Input hash not found in cache")
            return self.base_engine.run_phreeqc(input_string, database)
        
        self._cached_run = _cached_run
        self._hash_to_input = {}
    
    def _hash_input(self, input_string: str) -> str:
        """Create hash of PHREEQC input for caching"""
        # Normalize whitespace and line endings
        normalized = '\n'.join(line.strip() for line in input_string.strip().split('\n'))
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def run_phreeqc(self, input_string: str, database: Optional[str] = None) -> Tuple[str, str]:
        """
        Run PHREEQC with caching
        
        Args:
            input_string: PHREEQC input commands
            database: Path to database file
            
        Returns:
            Tuple of (output_string, selected_output_string)
        """
        # Create hash for caching
        input_hash = self._hash_input(input_string)
        
        # Store input for hash lookup
        self._hash_to_input[input_hash] = input_string
        
        # Use cached result if available
        try:
            return self._cached_run(input_hash, database or "")
        except ValueError:
            # Not in cache, run normally
            return self.base_engine.run_phreeqc(input_string, database)
    
    def run_batch_transport(
        self,
        base_input: str,
        cells: int,
        timesteps_list: List[int],
        database: Optional[str] = None,
        batch_size: int = 10
    ) -> Dict[int, List[Dict]]:
        """
        Run transport simulation for multiple timestep values in batches
        
        Args:
            base_input: Base PHREEQC input (without TRANSPORT block)
            cells: Number of cells
            timesteps_list: List of timestep values to simulate
            database: Database path
            batch_size: Number of timesteps per batch
            
        Returns:
            Dict mapping timesteps to results
        """
        results = {}
        
        # Sort timesteps for incremental simulation
        sorted_timesteps = sorted(timesteps_list)
        
        # Process in batches
        for i in range(0, len(sorted_timesteps), batch_size):
            batch = sorted_timesteps[i:i + batch_size]
            
            # Create batch input with multiple TRANSPORT blocks
            batch_input = self._create_batch_transport_input(
                base_input, cells, batch
            )
            
            # Run batch
            output, selected = self.run_phreeqc(batch_input, database)
            
            # Parse results for each timestep
            parsed_data = self.base_engine.parse_selected_output(selected)
            
            # Distribute results to appropriate timesteps
            if parsed_data:
                rows_per_timestep = len(parsed_data) // len(batch)
                for j, timesteps in enumerate(batch):
                    start_idx = j * rows_per_timestep
                    end_idx = (j + 1) * rows_per_timestep
                    results[timesteps] = parsed_data[start_idx:end_idx]
        
        return results
    
    def _create_batch_transport_input(
        self,
        base_input: str,
        cells: int,
        timesteps_list: List[int]
    ) -> str:
        """Create PHREEQC input with multiple TRANSPORT blocks"""
        lines = [base_input.strip()]
        
        # Add SELECTED_OUTPUT if not present
        if "SELECTED_OUTPUT" not in base_input:
            lines.append("\nSELECTED_OUTPUT")
            lines.append("    -reset false")
            lines.append("    -step true")
            lines.append("    -totals Ca Mg Na Cl")
        
        # Add TRANSPORT blocks for each timestep
        for i, timesteps in enumerate(timesteps_list):
            lines.append(f"\nUSER_PUNCH {i+1}")
            lines.append(f"    -head timestep_{timesteps}")
            lines.append(f"    10 PUNCH {timesteps}")
            
            lines.append(f"\nTRANSPORT")
            lines.append(f"    -cells {cells}")
            lines.append(f"    -shifts {timesteps}")
            lines.append(f"    -time_step 1.0")
            lines.append(f"    -flow_direction forward")
            lines.append(f"    -boundary_conditions flux flux")
            lines.append(f"    -lengths {cells}*1.0")
            lines.append(f"    -dispersivities {cells}*0.0")
            lines.append(f"    -punch_cells {cells}")
            lines.append(f"    -punch_frequency {max(1, timesteps // 10)}")
            
            # Save state after this transport
            if i < len(timesteps_list) - 1:
                lines.append("\nSAVE solution 1-" + str(cells))
                lines.append("SAVE exchange 1-" + str(cells))
        
        lines.append("\nEND")
        return '\n'.join(lines)
    
    def run_parallel_simulations(
        self,
        simulation_specs: List[Dict[str, Any]],
        database: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """
        Run multiple independent simulations in parallel
        
        Args:
            simulation_specs: List of dicts with 'input_string' key
            database: Database path
            
        Returns:
            List of (output, selected_output) tuples
        """
        results = [None] * len(simulation_specs)
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            future_to_index = {}
            for i, spec in enumerate(simulation_specs):
                future = executor.submit(
                    self._run_single_simulation,
                    spec['input_string'],
                    database
                )
                future_to_index[future] = i
            
            # Collect results
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    logger.error(f"Simulation {index} failed: {e}")
                    results[index] = ("", "")
        
        return results
    
    def _run_single_simulation(
        self,
        input_string: str,
        database: Optional[str]
    ) -> Tuple[str, str]:
        """Run single simulation (for parallel execution)"""
        # Create new engine instance for process isolation
        engine = DirectPhreeqcEngine(keep_temp_files=False)
        return engine.run_phreeqc(input_string, database)
    
    def parse_selected_output(self, selected_string: str) -> List[Dict]:
        """Parse selected output (delegate to base engine)"""
        return self.base_engine.parse_selected_output(selected_string)
    
    def clear_cache(self):
        """Clear the results cache"""
        self._cached_run.cache_clear()
        self._hash_to_input.clear()
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics"""
        info = self._cached_run.cache_info()
        return {
            'hits': info.hits,
            'misses': info.misses,
            'maxsize': info.maxsize,
            'currsize': info.currsize,
            'hit_rate': info.hits / (info.hits + info.misses) if (info.hits + info.misses) > 0 else 0
        }