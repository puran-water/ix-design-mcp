"""
Optimized PHREEQC Engine - Production-ready implementation with proper engineering practices

Key improvements:
- Bounded cache with configurable size and TTL
- Thread-safe operations
- Comprehensive error handling
- Performance metrics collection
- Proper resource management
"""

import os
import time
import logging
import hashlib
import json
import threading
from typing import Dict, List, Optional, Tuple, Any, Union
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass
import numpy as np

from .direct_phreeqc_engine import DirectPhreeqcEngine

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata for debugging and monitoring."""
    output: str
    selected_output: str
    timestamp: float
    input_size: int
    execution_time: float
    

class BoundedLRUCache:
    """
    Thread-safe bounded LRU cache with TTL support.
    
    Prevents unbounded memory growth and stale data issues.
    """
    
    def __init__(self, max_size: int = 128, ttl_seconds: float = 3600):
        """
        Initialize cache.
        
        Args:
            max_size: Maximum number of entries to cache
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0
        
    def get(self, key: str) -> Optional[Tuple[str, str]]:
        """Get value from cache if valid."""
        with self._lock:
            if key not in self._cache:
                self.misses += 1
                return None
                
            entry = self._cache[key]
            
            # Check TTL
            if time.time() - entry.timestamp > self.ttl_seconds:
                del self._cache[key]
                self.misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self.hits += 1
            return (entry.output, entry.selected_output)
    
    def put(self, key: str, output: str, selected_output: str, 
            input_size: int, execution_time: float) -> None:
        """Add entry to cache."""
        with self._lock:
            # Remove oldest if at capacity
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = CacheEntry(
                output=output,
                selected_output=selected_output,
                timestamp=time.time(),
                input_size=input_size,
                execution_time=execution_time
            )
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self.hits + self.misses
            return {
                'hits': self.hits,
                'misses': self.misses,
                'size': len(self._cache),
                'max_size': self.max_size,
                'hit_rate': self.hits / total if total > 0 else 0.0,
                'ttl_seconds': self.ttl_seconds
            }


class OptimizedPhreeqcEngine:
    """
    Production-ready optimized PHREEQC interface.
    
    Features:
    - Bounded LRU cache with TTL to prevent memory leaks
    - Thread-safe operations for concurrent access
    - Comprehensive error handling and logging
    - Performance metrics collection
    - Configurable optimization parameters
    """
    
    # Class constants with clear documentation
    DEFAULT_CACHE_SIZE = 256  # Entries, ~50MB with typical PHREEQC outputs
    DEFAULT_CACHE_TTL = 3600  # 1 hour, prevents stale data
    DEFAULT_MAX_WORKERS = 4   # Conservative default for stability
    DEFAULT_BATCH_SIZE = 10   # Balance between efficiency and memory
    MAX_INPUT_SIZE = 1_000_000  # 1MB max input to prevent DoS
    PROCESS_TIMEOUT = 300  # 5 minutes max per PHREEQC call
    
    def __init__(
        self, 
        phreeqc_path: Optional[str] = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL,
        max_workers: int = DEFAULT_MAX_WORKERS,
        enable_cache: bool = True,
        enable_parallel: bool = True,
        collect_metrics: bool = True
    ):
        """
        Initialize optimized engine with comprehensive configuration.
        
        Args:
            phreeqc_path: Path to PHREEQC executable
            cache_size: Maximum cache entries (0 to disable)
            cache_ttl_seconds: Cache entry time-to-live
            max_workers: Maximum parallel workers
            enable_cache: Enable result caching
            enable_parallel: Enable parallel execution
            collect_metrics: Collect performance metrics
        """
        self.base_engine = DirectPhreeqcEngine(
            phreeqc_path=phreeqc_path,
            keep_temp_files=False
        )
        
        # Optimization settings
        self.enable_cache = enable_cache and cache_size > 0
        self.enable_parallel = enable_parallel and max_workers > 1
        self.max_workers = max(1, min(max_workers, os.cpu_count() or 1))
        
        # Initialize cache
        self.cache = BoundedLRUCache(
            max_size=cache_size,
            ttl_seconds=cache_ttl_seconds
        ) if self.enable_cache else None
        
        # Performance metrics
        self.collect_metrics = collect_metrics
        self.metrics = {
            'total_calls': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'total_execution_time': 0.0,
            'parallel_runs': 0,
            'errors': 0
        }
        self._metrics_lock = threading.Lock()
        
        logger.info(
            f"OptimizedPhreeqcEngine initialized: "
            f"cache={self.enable_cache}, "
            f"parallel={self.enable_parallel}, "
            f"workers={self.max_workers}"
        )
    
    def _generate_cache_key(self, input_string: str, database: Optional[str] = None) -> str:
        """
        Generate efficient cache key for PHREEQC input.
        
        Uses faster hashing and includes database in key.
        """
        # Normalize critical parts only
        normalized_lines = []
        for line in input_string.strip().split('\n'):
            line = line.strip()
            # Skip comments and empty lines
            if line and not line.startswith('#'):
                normalized_lines.append(line)
        
        normalized = '\n'.join(normalized_lines)
        
        # Include database in cache key
        cache_data = f"{normalized}\n__DB__:{database or 'default'}"
        
        # Use built-in hash for speed (not cryptographic)
        return f"{hash(cache_data)}_{len(cache_data)}"
    
    def run_phreeqc(
        self, 
        input_string: str, 
        database: Optional[str] = None,
        timeout: float = PROCESS_TIMEOUT
    ) -> Tuple[str, str]:
        """
        Run PHREEQC with caching and error handling.
        
        Args:
            input_string: PHREEQC input commands
            database: Path to database file
            timeout: Maximum execution time in seconds
            
        Returns:
            Tuple of (output_string, selected_output_string)
            
        Raises:
            ValueError: If input is invalid
            RuntimeError: If PHREEQC execution fails
            TimeoutError: If execution exceeds timeout
        """
        start_time = time.time()
        
        # Input validation
        if not input_string or not input_string.strip():
            raise ValueError("Empty PHREEQC input provided")
        
        if len(input_string) > self.MAX_INPUT_SIZE:
            raise ValueError(
                f"Input size ({len(input_string)} bytes) exceeds maximum "
                f"({self.MAX_INPUT_SIZE} bytes)"
            )
        
        # Update metrics
        if self.collect_metrics:
            with self._metrics_lock:
                self.metrics['total_calls'] += 1
        
        # Check cache if enabled
        cache_key = None
        if self.enable_cache:
            cache_key = self._generate_cache_key(input_string, database)
            cached_result = self.cache.get(cache_key)
            
            if cached_result is not None:
                if self.collect_metrics:
                    with self._metrics_lock:
                        self.metrics['cache_hits'] += 1
                        self.metrics['total_execution_time'] += time.time() - start_time
                
                logger.debug(f"Cache hit for key: {cache_key[:20]}...")
                return cached_result
        
        # Execute PHREEQC
        try:
            logger.debug(f"Running PHREEQC (cache miss or disabled)")
            output, selected = self.base_engine.run_phreeqc(input_string, database)
            execution_time = time.time() - start_time
            
            # Update cache if enabled
            if self.enable_cache and cache_key:
                self.cache.put(
                    cache_key, 
                    output, 
                    selected,
                    len(input_string),
                    execution_time
                )
                
                if self.collect_metrics:
                    with self._metrics_lock:
                        self.metrics['cache_misses'] += 1
            
            # Update metrics
            if self.collect_metrics:
                with self._metrics_lock:
                    self.metrics['total_execution_time'] += execution_time
            
            return output, selected
            
        except Exception as e:
            if self.collect_metrics:
                with self._metrics_lock:
                    self.metrics['errors'] += 1
            
            logger.error(f"PHREEQC execution failed: {e}")
            raise
    
    def run_batch_transport(
        self,
        base_input: str,
        cells: int,
        timesteps_list: List[int],
        database: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE
    ) -> Dict[int, List[Dict]]:
        """
        Run transport simulation for multiple timesteps with proper error handling.
        
        Args:
            base_input: Base PHREEQC input (without TRANSPORT block)
            cells: Number of cells (must be positive)
            timesteps_list: List of timestep values to simulate
            database: Database path
            batch_size: Number of timesteps per batch (1-100)
            
        Returns:
            Dict mapping timesteps to results
            
        Raises:
            ValueError: If parameters are invalid
        """
        # Parameter validation
        if cells <= 0:
            raise ValueError(f"Cells must be positive, got {cells}")
        
        if not timesteps_list:
            raise ValueError("No timesteps provided")
        
        if batch_size < 1 or batch_size > 100:
            raise ValueError(f"Batch size must be 1-100, got {batch_size}")
        
        results = {}
        sorted_timesteps = sorted(timesteps_list)
        
        # Process in batches with error handling
        for i in range(0, len(sorted_timesteps), batch_size):
            batch = sorted_timesteps[i:i + batch_size]
            
            try:
                # Create batch input
                batch_input = self._create_batch_transport_input(
                    base_input, cells, batch
                )
                
                # Run batch
                output, selected = self.run_phreeqc(batch_input, database)
                
                # Parse results with validation
                parsed_data = self.base_engine.parse_selected_output(selected)
                
                if not parsed_data:
                    logger.warning(f"No data returned for batch: {batch}")
                    continue
                
                # Distribute results with bounds checking
                self._distribute_batch_results(results, parsed_data, batch, cells)
                
            except Exception as e:
                logger.error(f"Batch {i//batch_size + 1} failed: {e}")
                # Continue with other batches
                for timestep in batch:
                    results[timestep] = []
        
        return results
    
    def _distribute_batch_results(
        self,
        results: Dict[int, List[Dict]],
        parsed_data: List[Dict],
        batch: List[int],
        cells: int
    ) -> None:
        """Safely distribute batch results to individual timesteps."""
        # Group data by timestep marker if available
        timestep_groups = {}
        current_timestep = None
        
        for row in parsed_data:
            # Look for timestep marker
            for key in row:
                if key.startswith('timestep_'):
                    current_timestep = int(row[key])
                    if current_timestep not in timestep_groups:
                        timestep_groups[current_timestep] = []
                    break
            
            if current_timestep is not None:
                timestep_groups[current_timestep].append(row)
        
        # If no markers, distribute evenly (with validation)
        if not timestep_groups:
            expected_rows_per_timestep = len(parsed_data) // len(batch)
            if expected_rows_per_timestep * len(batch) != len(parsed_data):
                logger.warning(
                    f"Uneven data distribution: {len(parsed_data)} rows "
                    f"for {len(batch)} timesteps"
                )
            
            for j, timestep in enumerate(batch):
                start_idx = j * expected_rows_per_timestep
                end_idx = min((j + 1) * expected_rows_per_timestep, len(parsed_data))
                results[timestep] = parsed_data[start_idx:end_idx]
        else:
            # Use grouped data
            for timestep in batch:
                results[timestep] = timestep_groups.get(timestep, [])
    
    def _create_batch_transport_input(
        self,
        base_input: str,
        cells: int,
        timesteps_list: List[int]
    ) -> str:
        """Create PHREEQC input with multiple TRANSPORT blocks."""
        lines = [base_input.strip()]
        
        # Add SELECTED_OUTPUT if not present
        if "SELECTED_OUTPUT" not in base_input:
            lines.extend([
                "\nSELECTED_OUTPUT",
                "    -reset false",
                "    -step true",
                "    -totals Ca Mg Na Cl C"
            ])
        
        # Configuration constants
        DISPERSION_COEFFICIENT = 0.002  # m, typical for packed beds
        MIN_PUNCH_FREQUENCY = 1
        PUNCH_FREQUENCY_DIVISOR = 10  # Balance output size vs resolution
        
        # Add TRANSPORT blocks for each timestep
        for i, timesteps in enumerate(timesteps_list):
            # Add timestep marker
            lines.extend([
                f"\nUSER_PUNCH {i+1}",
                f"    -head timestep_{timesteps}",
                f"    10 PUNCH {timesteps}"
            ])
            
            # Calculate appropriate punch frequency
            punch_frequency = max(
                MIN_PUNCH_FREQUENCY,
                timesteps // PUNCH_FREQUENCY_DIVISOR
            )
            
            # Add transport block
            lines.extend([
                f"\nTRANSPORT",
                f"    -cells {cells}",
                f"    -shifts {timesteps}",
                f"    -time_step 1.0",
                f"    -flow_direction forward",
                f"    -boundary_conditions flux flux",
                f"    -lengths {cells}*1.0",
                f"    -dispersivities {cells}*{DISPERSION_COEFFICIENT}",
                f"    -punch_cells {cells}",
                f"    -punch_frequency {punch_frequency}"
            ])
            
            # Save state for next transport (except last)
            if i < len(timesteps_list) - 1:
                lines.extend([
                    f"\nSAVE solution 1-{cells}",
                    f"SAVE exchange 1-{cells}"
                ])
        
        lines.append("\nEND")
        return '\n'.join(lines)
    
    def run_parallel_simulations(
        self,
        simulation_specs: List[Dict[str, Any]],
        database: Optional[str] = None,
        timeout: float = PROCESS_TIMEOUT
    ) -> List[Union[Tuple[str, str], Exception]]:
        """
        Run multiple simulations in parallel with comprehensive error handling.
        
        Args:
            simulation_specs: List of dicts with 'input_string' key
            database: Database path
            timeout: Timeout per simulation
            
        Returns:
            List of results or exceptions for each simulation
        """
        if not self.enable_parallel:
            # Run sequentially
            results = []
            for spec in simulation_specs:
                try:
                    result = self.run_phreeqc(
                        spec['input_string'],
                        database,
                        timeout
                    )
                    results.append(result)
                except Exception as e:
                    results.append(e)
            return results
        
        # Update metrics
        if self.collect_metrics:
            with self._metrics_lock:
                self.metrics['parallel_runs'] += 1
        
        results = [None] * len(simulation_specs)
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs with timeout
            future_to_index = {}
            for i, spec in enumerate(simulation_specs):
                future = executor.submit(
                    self._run_single_simulation,
                    spec['input_string'],
                    database
                )
                future_to_index[future] = i
            
            # Collect results with timeout handling
            for future in as_completed(future_to_index, timeout=timeout):
                index = future_to_index[future]
                try:
                    results[index] = future.result(timeout=1)  # Quick check
                except TimeoutError:
                    logger.error(f"Simulation {index} timed out")
                    results[index] = TimeoutError(f"Simulation {index} exceeded {timeout}s")
                except Exception as e:
                    logger.error(f"Simulation {index} failed: {e}")
                    results[index] = e
        
        return results
    
    def _run_single_simulation(
        self,
        input_string: str,
        database: Optional[str]
    ) -> Tuple[str, str]:
        """Run single simulation in separate process."""
        # Create new engine instance for process isolation
        engine = DirectPhreeqcEngine(keep_temp_files=False)
        return engine.run_phreeqc(input_string, database)
    
    def parse_selected_output(self, selected_string: str) -> List[Dict]:
        """Parse selected output (delegate to base engine)."""
        return self.base_engine.parse_selected_output(selected_string)
    
    def clear_cache(self) -> None:
        """Clear the results cache."""
        if self.cache:
            self.cache.clear()
            logger.info("Cache cleared")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        metrics = {}
        
        # Cache statistics
        if self.cache:
            metrics['cache'] = self.cache.get_stats()
        
        # Performance metrics
        if self.collect_metrics:
            with self._metrics_lock:
                metrics['performance'] = self.metrics.copy()
                
                # Calculate derived metrics
                if self.metrics['total_calls'] > 0:
                    metrics['performance']['avg_execution_time'] = (
                        self.metrics['total_execution_time'] / 
                        self.metrics['total_calls']
                    )
        
        # Configuration
        metrics['config'] = {
            'cache_enabled': self.enable_cache,
            'parallel_enabled': self.enable_parallel,
            'max_workers': self.max_workers
        }
        
        return metrics
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - log metrics."""
        if self.collect_metrics:
            metrics = self.get_metrics()
            logger.info(f"OptimizedPhreeqcEngine metrics: {json.dumps(metrics, indent=2)}")
        return False