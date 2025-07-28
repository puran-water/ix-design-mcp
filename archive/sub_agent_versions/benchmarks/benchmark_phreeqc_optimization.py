#!/usr/bin/env python3
"""
Performance Benchmarks for PHREEQC Optimization

Measures real-world performance improvements using actual engineering calculations.
Compares optimized vs direct engine performance across various scenarios.

Results are output in both human-readable and JSON formats for tracking.
"""

import sys
import time
import json
import psutil
import statistics
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import concurrent.futures

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from watertap_ix_transport.transport_core.optimized_phreeqc_engine_refactored import OptimizedPhreeqcEngine
from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine


class PhreeqcBenchmark:
    """Comprehensive benchmarking suite for PHREEQC optimization."""
    
    def __init__(self):
        """Initialize benchmark suite."""
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'system_info': self._get_system_info(),
            'benchmarks': {}
        }
        
        # Initialize engines
        self.direct_engine = DirectPhreeqcEngine(keep_temp_files=False)
        self.optimized_engine = OptimizedPhreeqcEngine(
            cache_size=256,
            enable_cache=True,
            enable_parallel=True,
            max_workers=4
        )
        
    def _get_system_info(self) -> Dict[str, Any]:
        """Collect system information."""
        return {
            'platform': sys.platform,
            'python_version': sys.version,
            'cpu_count': psutil.cpu_count(),
            'memory_gb': psutil.virtual_memory().total / (1024**3),
            'cpu_percent': psutil.cpu_percent(interval=1)
        }
    
    def _measure_execution(self, engine, method: str, *args, **kwargs) -> Dict[str, float]:
        """Measure execution time and memory usage."""
        process = psutil.Process()
        
        # Memory before
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        
        # Execute and time
        start_time = time.perf_counter()
        result = getattr(engine, method)(*args, **kwargs)
        end_time = time.perf_counter()
        
        # Memory after
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        
        return {
            'execution_time': end_time - start_time,
            'memory_delta_mb': mem_after - mem_before,
            'result': result
        }
    
    def benchmark_single_calculation(self) -> Dict[str, Any]:
        """Benchmark single PHREEQC calculation."""
        print("\n📊 Benchmarking single calculation...")
        
        # Real water composition
        phreeqc_input = """
        SOLUTION 1 Municipal Water Supply
            temp      25
            pH        7.8
            pe        4
            units     mg/l
            density   1
            Ca        180
            Mg        80
            Na        120
            K         8
            Cl        350
            Alkalinity 280 as HCO3
            S(6)      96 as SO4
            N(5)      15 as NO3
            
        EXCHANGE 1
            -equilibrate 1
            NaX       1.8
            
        EXCHANGE_SPECIES
            Na+ + X- = NaX
                log_k     0.0
            Ca+2 + 2X- = CaX2
                log_k     0.8
            Mg+2 + 2X- = MgX2
                log_k     0.6
            K+ + X- = KX
                log_k     0.7
                
        SELECTED_OUTPUT
            -reset false
            -totals Ca Mg Na K
            -molalities CaX2 MgX2 NaX KX
            -activities Ca+2 Mg+2 Na+ K+
        END
        """
        
        results = {'name': 'single_calculation'}
        
        # Warm up
        self.direct_engine.run_phreeqc(phreeqc_input)
        self.optimized_engine.run_phreeqc(phreeqc_input)
        
        # Benchmark direct engine (10 runs)
        direct_times = []
        for _ in range(10):
            metrics = self._measure_execution(
                self.direct_engine, 'run_phreeqc', phreeqc_input
            )
            direct_times.append(metrics['execution_time'])
        
        # Clear cache for fair comparison
        self.optimized_engine.clear_cache()
        
        # Benchmark optimized engine - first run (cache miss)
        opt_first = self._measure_execution(
            self.optimized_engine, 'run_phreeqc', phreeqc_input
        )
        
        # Benchmark optimized engine - subsequent runs (cache hits)
        opt_cached_times = []
        for _ in range(9):
            metrics = self._measure_execution(
                self.optimized_engine, 'run_phreeqc', phreeqc_input
            )
            opt_cached_times.append(metrics['execution_time'])
        
        # Calculate statistics
        results['direct'] = {
            'mean_time': statistics.mean(direct_times),
            'std_dev': statistics.stdev(direct_times),
            'min_time': min(direct_times),
            'max_time': max(direct_times)
        }
        
        results['optimized_first_run'] = {
            'time': opt_first['execution_time'],
            'memory_mb': opt_first['memory_delta_mb']
        }
        
        results['optimized_cached'] = {
            'mean_time': statistics.mean(opt_cached_times),
            'std_dev': statistics.stdev(opt_cached_times),
            'min_time': min(opt_cached_times),
            'max_time': max(opt_cached_times)
        }
        
        # Calculate speedup
        results['speedup_cached'] = results['direct']['mean_time'] / results['optimized_cached']['mean_time']
        
        print(f"  Direct engine: {results['direct']['mean_time']:.3f}s ± {results['direct']['std_dev']:.3f}s")
        print(f"  Optimized (first): {results['optimized_first_run']['time']:.3f}s")
        print(f"  Optimized (cached): {results['optimized_cached']['mean_time']:.3f}s ± {results['optimized_cached']['std_dev']:.3f}s")
        print(f"  ✓ Speedup (cached): {results['speedup_cached']:.1f}x")
        
        return results
    
    def benchmark_batch_transport(self) -> Dict[str, Any]:
        """Benchmark batch transport calculations."""
        print("\n📊 Benchmarking batch transport...")
        
        # Base configuration for column simulation
        base_input = """
        SOLUTION 0 Feed Water
            temp      25
            pH        7.5
            units     mg/l
            Ca        200
            Mg        100
            Na        150
            Cl        500
            
        SOLUTION 1-20 Initial Column
            temp      25
            pH        7.0
            units     mg/l
            Na        23
            Cl        35.5
            
        EXCHANGE 1-20
            -equilibrate 1-20
            NaX       1.5
            
        EXCHANGE_SPECIES
            Na+ + X- = NaX
                log_k     0.0
            Ca+2 + 2X- = CaX2
                log_k     0.8
            Mg+2 + 2X- = MgX2
                log_k     0.6
        """
        
        # Test different batch sizes
        timesteps_list = list(range(10, 510, 10))  # 50 timesteps
        batch_sizes = [1, 5, 10, 20]
        
        results = {
            'name': 'batch_transport',
            'total_timesteps': len(timesteps_list),
            'batch_results': {}
        }
        
        for batch_size in batch_sizes:
            print(f"  Testing batch size: {batch_size}")
            
            # Direct engine (always batch size 1)
            if batch_size == 1:
                direct_start = time.perf_counter()
                direct_results = {}
                for ts in timesteps_list:
                    output, selected = self.direct_engine.run_phreeqc(
                        self._create_single_transport_input(base_input, 20, ts)
                    )
                    direct_results[ts] = self.direct_engine.parse_selected_output(selected)
                direct_time = time.perf_counter() - direct_start
                results['direct_time'] = direct_time
                print(f"    Direct engine: {direct_time:.2f}s")
            
            # Optimized engine with batching
            opt_start = time.perf_counter()
            opt_results = self.optimized_engine.run_batch_transport(
                base_input=base_input,
                cells=20,
                timesteps_list=timesteps_list,
                batch_size=batch_size
            )
            opt_time = time.perf_counter() - opt_start
            
            results['batch_results'][batch_size] = {
                'time': opt_time,
                'speedup': results.get('direct_time', opt_time) / opt_time
            }
            
            print(f"    Optimized (batch={batch_size}): {opt_time:.2f}s")
            print(f"    Speedup: {results['batch_results'][batch_size]['speedup']:.1f}x")
        
        return results
    
    def _create_single_transport_input(self, base_input: str, cells: int, timesteps: int) -> str:
        """Create PHREEQC input for single transport calculation."""
        return f"""{base_input}
        
        SELECTED_OUTPUT
            -reset false
            -step true
            -totals Ca Mg Na
            
        TRANSPORT
            -cells {cells}
            -shifts {timesteps}
            -time_step 1.0
            -flow_direction forward
            -boundary_conditions flux flux
            -lengths {cells}*1.0
            -dispersivities {cells}*0.002
            -punch_cells {cells}
            -punch_frequency {max(1, timesteps // 10)}
        END
        """
    
    def benchmark_parallel_execution(self) -> Dict[str, Any]:
        """Benchmark parallel execution capabilities."""
        print("\n📊 Benchmarking parallel execution...")
        
        # Create varied water compositions
        water_compositions = []
        for i in range(20):
            ca = 100 + i * 10  # 100-290 mg/L
            mg = 40 + i * 5    # 40-135 mg/L
            na = 50 + i * 3    # 50-107 mg/L
            
            input_str = f"""
            SOLUTION {i+1}
                temp      25
                pH        7.{i%5}
                units     mg/l
                Ca        {ca}
                Mg        {mg}
                Na        {na}
                Cl        {ca*2 + mg*2 + na}
                
            EXCHANGE {i+1}
                -equilibrate {i+1}
                NaX       1.8
                
            SELECTED_OUTPUT
                -reset false
                -totals Ca Mg Na
            END
            """
            water_compositions.append({'input_string': input_str})
        
        results = {
            'name': 'parallel_execution',
            'total_simulations': len(water_compositions)
        }
        
        # Sequential execution
        seq_start = time.perf_counter()
        seq_results = []
        for spec in water_compositions:
            output, selected = self.direct_engine.run_phreeqc(spec['input_string'])
            seq_results.append((output, selected))
        seq_time = time.perf_counter() - seq_start
        
        results['sequential'] = {
            'time': seq_time,
            'per_simulation': seq_time / len(water_compositions)
        }
        
        print(f"  Sequential: {seq_time:.2f}s ({results['sequential']['per_simulation']:.3f}s per sim)")
        
        # Parallel execution with different worker counts
        for workers in [2, 4, 8]:
            if workers > psutil.cpu_count():
                continue
                
            engine = OptimizedPhreeqcEngine(
                enable_parallel=True,
                max_workers=workers,
                enable_cache=False  # Disable cache for fair comparison
            )
            
            par_start = time.perf_counter()
            par_results = engine.run_parallel_simulations(water_compositions)
            par_time = time.perf_counter() - par_start
            
            results[f'parallel_{workers}'] = {
                'time': par_time,
                'speedup': seq_time / par_time,
                'efficiency': (seq_time / par_time) / workers * 100
            }
            
            print(f"  Parallel ({workers} workers): {par_time:.2f}s")
            print(f"    Speedup: {results[f'parallel_{workers}']['speedup']:.1f}x")
            print(f"    Efficiency: {results[f'parallel_{workers}']['efficiency']:.0f}%")
        
        return results
    
    def benchmark_cache_effectiveness(self) -> Dict[str, Any]:
        """Benchmark cache effectiveness with realistic query patterns."""
        print("\n📊 Benchmarking cache effectiveness...")
        
        # Create a realistic mix of water compositions
        # 80% will be variations of common compositions (cache hits expected)
        # 20% will be unique (cache misses)
        
        common_templates = [
            # Soft water
            {'Ca': 20, 'Mg': 10, 'Na': 30, 'pH': 7.2},
            # Moderate hardness
            {'Ca': 100, 'Mg': 40, 'Na': 50, 'pH': 7.5},
            # Hard water
            {'Ca': 200, 'Mg': 80, 'Na': 100, 'pH': 7.8},
            # Very hard water
            {'Ca': 300, 'Mg': 120, 'Na': 150, 'pH': 8.0}
        ]
        
        queries = []
        for i in range(1000):
            if i % 5 == 0:  # 20% unique
                comp = {
                    'Ca': 50 + i,
                    'Mg': 20 + i // 2,
                    'Na': 40 + i // 3,
                    'pH': 6.5 + (i % 20) / 10
                }
            else:  # 80% common with small variations
                template = common_templates[i % len(common_templates)]
                comp = template.copy()
                # Add small variation
                comp['Ca'] += (i % 10) - 5
                
            input_str = f"""
            SOLUTION 1
                temp      25
                pH        {comp['pH']}
                units     mg/l
                Ca        {comp['Ca']}
                Mg        {comp['Mg']}
                Na        {comp['Na']}
                Cl        {comp['Ca']*2 + comp['Mg']*2 + comp['Na']}
                
            EXCHANGE 1
                -equilibrate 1
                NaX       1.8
            END
            """
            queries.append(input_str)
        
        # Clear cache and metrics
        self.optimized_engine.clear_cache()
        
        # Run queries
        start_time = time.perf_counter()
        for query in queries:
            self.optimized_engine.run_phreeqc(query)
        total_time = time.perf_counter() - start_time
        
        # Get cache statistics
        metrics = self.optimized_engine.get_metrics()
        cache_stats = metrics['cache']
        
        results = {
            'name': 'cache_effectiveness',
            'total_queries': len(queries),
            'total_time': total_time,
            'avg_time_per_query': total_time / len(queries),
            'cache_stats': cache_stats,
            'expected_hit_rate': 0.7,  # Due to pattern
            'actual_hit_rate': cache_stats['hit_rate']
        }
        
        print(f"  Total queries: {results['total_queries']}")
        print(f"  Total time: {results['total_time']:.2f}s")
        print(f"  Average per query: {results['avg_time_per_query']*1000:.1f}ms")
        print(f"  Cache hit rate: {results['actual_hit_rate']:.1%}")
        print(f"  Cache size: {cache_stats['size']}/{cache_stats['max_size']}")
        
        return results
    
    def benchmark_memory_usage(self) -> Dict[str, Any]:
        """Benchmark memory usage patterns."""
        print("\n📊 Benchmarking memory usage...")
        
        process = psutil.Process()
        results = {
            'name': 'memory_usage',
            'measurements': []
        }
        
        # Baseline memory
        baseline_mb = process.memory_info().rss / 1024 / 1024
        results['baseline_mb'] = baseline_mb
        
        # Test with increasing cache sizes
        cache_sizes = [0, 50, 100, 200, 500]
        
        for cache_size in cache_sizes:
            # Create new engine with specific cache size
            engine = OptimizedPhreeqcEngine(
                cache_size=cache_size,
                enable_cache=cache_size > 0
            )
            
            # Fill cache with diverse calculations
            for i in range(min(cache_size, 100) if cache_size > 0 else 50):
                input_str = f"""
                SOLUTION {i}
                    temp 25
                    pH {7 + i*0.01}
                    Ca {100 + i} mg/l
                    Na {50 + i//2} mg/l
                    Cl {300 + i*2} mg/l
                EXCHANGE {i}
                    -equilibrate {i}
                    NaX 1.8
                END
                """
                engine.run_phreeqc(input_str)
            
            # Measure memory
            current_mb = process.memory_info().rss / 1024 / 1024
            delta_mb = current_mb - baseline_mb
            
            measurement = {
                'cache_size': cache_size,
                'memory_mb': current_mb,
                'delta_mb': delta_mb,
                'mb_per_entry': delta_mb / cache_size if cache_size > 0 else 0
            }
            results['measurements'].append(measurement)
            
            print(f"  Cache size {cache_size}: {current_mb:.1f}MB (+{delta_mb:.1f}MB)")
            if cache_size > 0:
                print(f"    ~{measurement['mb_per_entry']:.2f}MB per cache entry")
        
        return results
    
    def run_all_benchmarks(self) -> None:
        """Run all benchmarks and save results."""
        print("🚀 Starting PHREEQC Optimization Benchmarks")
        print("=" * 60)
        
        # Run benchmarks
        self.results['benchmarks']['single_calculation'] = self.benchmark_single_calculation()
        self.results['benchmarks']['batch_transport'] = self.benchmark_batch_transport()
        self.results['benchmarks']['parallel_execution'] = self.benchmark_parallel_execution()
        self.results['benchmarks']['cache_effectiveness'] = self.benchmark_cache_effectiveness()
        self.results['benchmarks']['memory_usage'] = self.benchmark_memory_usage()
        
        # Save results
        output_file = Path(__file__).parent / f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print("\n" + "=" * 60)
        print("📊 Benchmark Summary")
        print("=" * 60)
        
        # Print summary
        for name, data in self.results['benchmarks'].items():
            print(f"\n{name}:")
            if 'speedup' in data:
                print(f"  Speedup: {data['speedup']:.1f}x")
            elif 'speedup_cached' in data:
                print(f"  Speedup (cached): {data['speedup_cached']:.1f}x")
            elif name == 'cache_effectiveness':
                print(f"  Hit rate: {data['actual_hit_rate']:.1%}")
            elif name == 'memory_usage':
                print(f"  Peak memory: {max(m['memory_mb'] for m in data['measurements']):.1f}MB")
        
        print(f"\n✓ Results saved to: {output_file}")
        
        # Performance recommendations
        print("\n💡 Performance Recommendations:")
        
        # Cache recommendation
        cache_data = self.results['benchmarks']['cache_effectiveness']
        if cache_data['actual_hit_rate'] < 0.5:
            print("  ⚠ Low cache hit rate - consider increasing cache size or TTL")
        else:
            print("  ✓ Good cache hit rate achieved")
        
        # Batch recommendation
        batch_data = self.results['benchmarks']['batch_transport']['batch_results']
        optimal_batch = max(batch_data.items(), key=lambda x: x[1]['speedup'])[0]
        print(f"  ✓ Optimal batch size: {optimal_batch}")
        
        # Memory recommendation
        memory_data = self.results['benchmarks']['memory_usage']
        mb_per_entry = memory_data['measurements'][-1]['mb_per_entry']
        if mb_per_entry > 1.0:
            print("  ⚠ High memory usage per cache entry - consider reducing cache size")
        else:
            print("  ✓ Memory usage is reasonable")


def main():
    """Run benchmarks."""
    benchmark = PhreeqcBenchmark()
    benchmark.run_all_benchmarks()
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)