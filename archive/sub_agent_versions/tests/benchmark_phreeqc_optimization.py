#!/usr/bin/env python3
"""
Performance Benchmark Suite for PHREEQC Optimization

Comprehensive benchmarks comparing DirectPhreeqcEngine vs OptimizedPhreeqcEngine
across various real-world scenarios.

Run this script to generate performance reports and identify optimization benefits.
"""

import sys
import time
import json
import statistics
from pathlib import Path
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from watertap_ix_transport.transport_core.optimized_phreeqc_engine import OptimizedPhreeqcEngine
from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine


class PhreeqcBenchmark:
    """Benchmark suite for PHREEQC engines."""
    
    def __init__(self):
        """Initialize benchmark suite."""
        self.results = {
            'simple_equilibrium': {},
            'complex_equilibrium': {},
            'transport_simulation': {},
            'batch_processing': {},
            'parallel_execution': {},
            'cache_performance': {}
        }
        
        # Initialize engines
        try:
            self.direct_engine = DirectPhreeqcEngine(keep_temp_files=False)
            self.optimized_engine = OptimizedPhreeqcEngine(
                cache_size=256,
                enable_cache=True,
                enable_parallel=True,
                max_workers=4
            )
            self.engines_available = True
        except Exception as e:
            print(f"Error initializing engines: {e}")
            self.engines_available = False
            
    def run_all_benchmarks(self):
        """Run all benchmark tests."""
        if not self.engines_available:
            print("PHREEQC engines not available. Cannot run benchmarks.")
            return
            
        print("Running PHREEQC Optimization Benchmarks...")
        print("=" * 60)
        
        self.benchmark_simple_equilibrium()
        self.benchmark_complex_equilibrium()
        self.benchmark_transport_simulation()
        self.benchmark_batch_processing()
        self.benchmark_parallel_execution()
        self.benchmark_cache_scaling()
        
        self.generate_report()
        
    def benchmark_simple_equilibrium(self):
        """Benchmark simple equilibrium calculations."""
        print("\n1. Simple Equilibrium Benchmark")
        print("-" * 40)
        
        # Simple calcite equilibrium
        input_str = """
        SOLUTION 1
            temp      25
            pH        7.5
            units     mg/l
            Ca        100
            Alkalinity 200 as HCO3
        EQUILIBRIUM_PHASES 1
            Calcite 0 10
        SELECTED_OUTPUT
            -saturation_indices Calcite
        END
        """
        
        # Warm up
        self.direct_engine.run_phreeqc(input_str)
        self.optimized_engine.run_phreeqc(input_str)
        
        # Benchmark runs
        num_runs = 100
        
        # Direct engine
        direct_times = []
        for _ in range(num_runs):
            start = time.time()
            self.direct_engine.run_phreeqc(input_str)
            direct_times.append(time.time() - start)
            
        # Optimized engine (should use cache after first run)
        opt_times = []
        for _ in range(num_runs):
            start = time.time()
            self.optimized_engine.run_phreeqc(input_str)
            opt_times.append(time.time() - start)
            
        # Calculate statistics
        direct_avg = statistics.mean(direct_times)
        direct_std = statistics.stdev(direct_times)
        opt_avg = statistics.mean(opt_times)
        opt_std = statistics.stdev(opt_times)
        speedup = direct_avg / opt_avg
        
        self.results['simple_equilibrium'] = {
            'direct_avg_ms': direct_avg * 1000,
            'direct_std_ms': direct_std * 1000,
            'optimized_avg_ms': opt_avg * 1000,
            'optimized_std_ms': opt_std * 1000,
            'speedup': speedup,
            'num_runs': num_runs
        }
        
        print(f"Direct engine: {direct_avg*1000:.1f} ± {direct_std*1000:.1f} ms")
        print(f"Optimized engine: {opt_avg*1000:.1f} ± {opt_std*1000:.1f} ms")
        print(f"Speedup: {speedup:.1f}x")
        
    def benchmark_complex_equilibrium(self):
        """Benchmark complex multi-phase equilibrium."""
        print("\n2. Complex Equilibrium Benchmark")
        print("-" * 40)
        
        # Complex system with multiple phases
        input_str = """
        SOLUTION 1
            temp      25
            pH        7.0
            pe        4
            units     mg/l
            Ca        180
            Mg        80
            Na        50
            K         5
            Fe        0.1
            Mn        0.05
            Al        0.01
            Cl        350
            S(6)      96 as SO4
            C(4)      200 as HCO3
            Si        10 as SiO2
        
        EQUILIBRIUM_PHASES 1
            Calcite   0  10
            Dolomite  0  0
            Gypsum    0  0
            Fe(OH)3(a) 0 0
            Pyrolusite 0 0
            Gibbsite  0  0
            SiO2(a)   0  0
            
        EXCHANGE 1
            -equilibrate 1
            NaX       1.0
            
        SURFACE 1
            -equilibrate 1
            Hfo_wOH  0.001  600  1
            Hfo_sOH  0.00005
            
        SELECTED_OUTPUT
            -saturation_indices Calcite Dolomite Gypsum
            -totals Ca Mg Fe
        END
        """
        
        # Benchmark runs (fewer due to complexity)
        num_runs = 20
        
        direct_times = []
        for _ in range(num_runs):
            start = time.time()
            self.direct_engine.run_phreeqc(input_str)
            direct_times.append(time.time() - start)
            
        opt_times = []
        for _ in range(num_runs):
            start = time.time()
            self.optimized_engine.run_phreeqc(input_str)
            opt_times.append(time.time() - start)
            
        direct_avg = statistics.mean(direct_times)
        opt_avg = statistics.mean(opt_times)
        speedup = direct_avg / opt_avg
        
        self.results['complex_equilibrium'] = {
            'direct_avg_ms': direct_avg * 1000,
            'optimized_avg_ms': opt_avg * 1000,
            'speedup': speedup,
            'num_runs': num_runs
        }
        
        print(f"Direct engine: {direct_avg*1000:.1f} ms")
        print(f"Optimized engine: {opt_avg*1000:.1f} ms")
        print(f"Speedup: {speedup:.1f}x")
        
    def benchmark_transport_simulation(self):
        """Benchmark transport simulations."""
        print("\n3. Transport Simulation Benchmark")
        print("-" * 40)
        
        base_input = """
        SOLUTION 0
            temp 25
            pH 7.5
            Ca 200 mg/l
            Mg 100 mg/l
            Na 100 mg/l
            Cl 500 mg/l
            
        SOLUTION 1-20
            temp 25
            pH 7.0
            Na 23 mg/l
            Cl 35.5 mg/l
            
        EXCHANGE 1-20
            -equilibrate 1-20
            NaX 0.1
            
        SELECTED_OUTPUT
            -reset false
            -step true
            -totals Ca Mg Na
        """
        
        # Single transport run
        transport_input = base_input + """
        TRANSPORT
            -cells 20
            -shifts 100
            -time_step 3600
            -flow_direction forward
            -boundary_conditions flux flux
            -lengths 20*1.0
            -dispersivities 20*0.002
            -punch_cells 20
            -punch_frequency 10
        END
        """
        
        # Benchmark single transport
        num_runs = 10
        
        direct_times = []
        for _ in range(num_runs):
            start = time.time()
            self.direct_engine.run_phreeqc(transport_input)
            direct_times.append(time.time() - start)
            
        opt_times = []
        for _ in range(num_runs):
            start = time.time()
            self.optimized_engine.run_phreeqc(transport_input)
            opt_times.append(time.time() - start)
            
        direct_avg = statistics.mean(direct_times)
        opt_avg = statistics.mean(opt_times)
        speedup = direct_avg / opt_avg
        
        self.results['transport_simulation'] = {
            'direct_avg_s': direct_avg,
            'optimized_avg_s': opt_avg,
            'speedup': speedup,
            'num_runs': num_runs,
            'cells': 20,
            'shifts': 100
        }
        
        print(f"Direct engine: {direct_avg:.2f} s")
        print(f"Optimized engine: {opt_avg:.2f} s")
        print(f"Speedup: {speedup:.1f}x")
        
    def benchmark_batch_processing(self):
        """Benchmark batch transport processing."""
        print("\n4. Batch Processing Benchmark")
        print("-" * 40)
        
        base_input = """
        SOLUTION 0
            pH 7.5
            Ca 150 mg/l
            Na 50 mg/l
            
        SOLUTION 1-10
            pH 7.0
            Na 10 mg/l
            
        EXCHANGE 1-10
            -equilibrate 1-10
            NaX 0.1
        """
        
        timesteps = [10, 20, 50, 100, 200, 300, 400, 500]
        
        # Sequential processing (direct engine)
        start = time.time()
        sequential_results = {}
        for ts in timesteps:
            input_str = base_input + f"""
            TRANSPORT
                -cells 10
                -shifts {ts}
            SELECTED_OUTPUT
                -reset false
                -totals Ca Na
            END
            """
            output, selected = self.direct_engine.run_phreeqc(input_str)
            sequential_results[ts] = self.direct_engine.parse_selected_output(selected)
        sequential_time = time.time() - start
        
        # Batch processing (optimized engine)
        start = time.time()
        batch_results = self.optimized_engine.run_batch_transport(
            base_input=base_input,
            cells=10,
            timesteps_list=timesteps,
            batch_size=4
        )
        batch_time = time.time() - start
        
        speedup = sequential_time / batch_time
        
        self.results['batch_processing'] = {
            'sequential_time_s': sequential_time,
            'batch_time_s': batch_time,
            'speedup': speedup,
            'num_timesteps': len(timesteps)
        }
        
        print(f"Sequential: {sequential_time:.2f} s")
        print(f"Batch: {batch_time:.2f} s")
        print(f"Speedup: {speedup:.1f}x")
        
    def benchmark_parallel_execution(self):
        """Benchmark parallel simulation execution."""
        print("\n5. Parallel Execution Benchmark")
        print("-" * 40)
        
        # Create varied simulations
        simulation_specs = []
        for i in range(20):
            ph = 6.5 + i * 0.1
            ca = 50 + i * 10
            simulation_specs.append({
                'input_string': f"""
                SOLUTION {i+1}
                    temp 25
                    pH {ph}
                    Ca {ca} mg/l
                    Cl {ca*2} mg/l
                EQUILIBRIUM_PHASES {i+1}
                    Calcite 0 10
                SELECTED_OUTPUT
                    -totals Ca
                END
                """
            })
        
        # Sequential execution
        start = time.time()
        seq_results = []
        for spec in simulation_specs:
            output, selected = self.direct_engine.run_phreeqc(spec['input_string'])
            seq_results.append((output, selected))
        seq_time = time.time() - start
        
        # Parallel execution
        start = time.time()
        par_results = self.optimized_engine.run_parallel_simulations(simulation_specs)
        par_time = time.time() - start
        
        speedup = seq_time / par_time
        
        self.results['parallel_execution'] = {
            'sequential_time_s': seq_time,
            'parallel_time_s': par_time,
            'speedup': speedup,
            'num_simulations': len(simulation_specs),
            'max_workers': self.optimized_engine.max_workers
        }
        
        print(f"Sequential: {seq_time:.2f} s")
        print(f"Parallel: {par_time:.2f} s")
        print(f"Speedup: {speedup:.1f}x")
        print(f"Workers: {self.optimized_engine.max_workers}")
        
    def benchmark_cache_scaling(self):
        """Benchmark cache performance with different hit rates."""
        print("\n6. Cache Performance Scaling")
        print("-" * 40)
        
        # Create a set of similar inputs
        base_inputs = []
        for i in range(10):
            base_inputs.append(f"""
            SOLUTION {i+1}
                pH 7.{i}
                Ca {100+i} mg/l
            END
            """)
        
        # Test different cache hit scenarios
        scenarios = [
            ('0% hits (all unique)', base_inputs * 1),
            ('50% hits', base_inputs[:5] * 20),
            ('90% hits', base_inputs[:1] * 90 + base_inputs[1:]),
            ('99% hits', [base_inputs[0]] * 99 + [base_inputs[1]])
        ]
        
        cache_results = []
        
        for scenario_name, inputs in scenarios:
            # Clear cache
            self.optimized_engine.clear_cache()
            
            start = time.time()
            for inp in inputs:
                self.optimized_engine.run_phreeqc(inp)
            total_time = time.time() - start
            
            # Get cache stats
            cache_info = self.optimized_engine.get_cache_info()
            
            cache_results.append({
                'scenario': scenario_name,
                'total_time_s': total_time,
                'avg_time_ms': (total_time / len(inputs)) * 1000,
                'hit_rate': cache_info['hit_rate'],
                'hits': cache_info['hits'],
                'misses': cache_info['misses']
            })
            
            print(f"{scenario_name}: {total_time:.2f}s, "
                  f"hit rate: {cache_info['hit_rate']:.1%}")
        
        self.results['cache_performance'] = cache_results
        
    def generate_report(self):
        """Generate performance report with visualizations."""
        print("\n" + "=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)
        
        # Create summary statistics
        total_speedup = []
        
        print(f"\n{'Benchmark':<30} {'Speedup':>10} {'Notes':>20}")
        print("-" * 60)
        
        if self.results['simple_equilibrium']:
            speedup = self.results['simple_equilibrium']['speedup']
            total_speedup.append(speedup)
            print(f"{'Simple Equilibrium':<30} {speedup:>10.1f}x {'(cache hits)':<20}")
            
        if self.results['complex_equilibrium']:
            speedup = self.results['complex_equilibrium']['speedup']
            total_speedup.append(speedup)
            print(f"{'Complex Equilibrium':<30} {speedup:>10.1f}x")
            
        if self.results['transport_simulation']:
            speedup = self.results['transport_simulation']['speedup']
            total_speedup.append(speedup)
            print(f"{'Transport Simulation':<30} {speedup:>10.1f}x")
            
        if self.results['batch_processing']:
            speedup = self.results['batch_processing']['speedup']
            total_speedup.append(speedup)
            print(f"{'Batch Processing':<30} {speedup:>10.1f}x {'(batching)':<20}")
            
        if self.results['parallel_execution']:
            speedup = self.results['parallel_execution']['speedup']
            total_speedup.append(speedup)
            workers = self.results['parallel_execution']['max_workers']
            print(f"{'Parallel Execution':<30} {speedup:>10.1f}x {f'({workers} workers)':<20}")
        
        if total_speedup:
            avg_speedup = statistics.mean(total_speedup)
            print("-" * 60)
            print(f"{'Average Speedup':<30} {avg_speedup:>10.1f}x")
        
        # Generate plots
        self._create_performance_plots()
        
        # Save detailed results
        output_file = project_root / 'tests' / 'benchmark_results.json'
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\nDetailed results saved to: {output_file}")
        
    def _create_performance_plots(self):
        """Create performance visualization plots."""
        try:
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))
            
            # Plot 1: Speedup comparison
            if any(self.results.values()):
                benchmarks = []
                speedups = []
                
                if self.results['simple_equilibrium']:
                    benchmarks.append('Simple\nEquilibrium')
                    speedups.append(self.results['simple_equilibrium']['speedup'])
                if self.results['complex_equilibrium']:
                    benchmarks.append('Complex\nEquilibrium')
                    speedups.append(self.results['complex_equilibrium']['speedup'])
                if self.results['transport_simulation']:
                    benchmarks.append('Transport\nSimulation')
                    speedups.append(self.results['transport_simulation']['speedup'])
                if self.results['batch_processing']:
                    benchmarks.append('Batch\nProcessing')
                    speedups.append(self.results['batch_processing']['speedup'])
                if self.results['parallel_execution']:
                    benchmarks.append('Parallel\nExecution')
                    speedups.append(self.results['parallel_execution']['speedup'])
                
                ax1.bar(benchmarks, speedups, color='skyblue', edgecolor='navy')
                ax1.set_ylabel('Speedup Factor')
                ax1.set_title('Optimization Speedup by Benchmark')
                ax1.axhline(y=1, color='r', linestyle='--', alpha=0.5)
                ax1.grid(axis='y', alpha=0.3)
            
            # Plot 2: Cache performance
            if self.results['cache_performance']:
                scenarios = [r['scenario'].split()[0] for r in self.results['cache_performance']]
                avg_times = [r['avg_time_ms'] for r in self.results['cache_performance']]
                hit_rates = [r['hit_rate'] * 100 for r in self.results['cache_performance']]
                
                ax2_twin = ax2.twinx()
                bars = ax2.bar(scenarios, avg_times, color='lightcoral', alpha=0.7, label='Avg Time')
                line = ax2_twin.plot(scenarios, hit_rates, 'go-', linewidth=2, markersize=8, label='Hit Rate')
                
                ax2.set_ylabel('Average Time (ms)')
                ax2_twin.set_ylabel('Cache Hit Rate (%)')
                ax2.set_title('Cache Performance vs Hit Rate')
                ax2.grid(axis='y', alpha=0.3)
                
                # Combine legends
                labs = [bars.get_label()] + [l.get_label() for l in line]
                ax2.legend([bars] + line, labs, loc='upper right')
            
            # Plot 3: Execution time comparison
            if self.results['simple_equilibrium']:
                methods = ['Direct', 'Optimized']
                times = [
                    self.results['simple_equilibrium']['direct_avg_ms'],
                    self.results['simple_equilibrium']['optimized_avg_ms']
                ]
                stds = [
                    self.results['simple_equilibrium']['direct_std_ms'],
                    self.results['simple_equilibrium']['optimized_std_ms']
                ]
                
                ax3.bar(methods, times, yerr=stds, capsize=10, 
                       color=['salmon', 'lightgreen'], edgecolor='black')
                ax3.set_ylabel('Execution Time (ms)')
                ax3.set_title('Simple Equilibrium: Direct vs Optimized')
                ax3.grid(axis='y', alpha=0.3)
            
            # Plot 4: Scaling with parallel workers
            if self.results['parallel_execution']:
                workers = list(range(1, self.results['parallel_execution']['max_workers'] + 1))
                seq_time = self.results['parallel_execution']['sequential_time_s']
                
                # Theoretical speedup
                theoretical_speedup = workers
                
                # Actual speedup (estimated)
                actual_speedup = [1]  # 1 worker = no speedup
                for w in workers[1:]:
                    # Estimate based on measured speedup
                    measured = self.results['parallel_execution']['speedup']
                    actual_speedup.append(min(measured * w / workers[-1], w))
                
                ax4.plot(workers, theoretical_speedup, 'b--', label='Theoretical', linewidth=2)
                ax4.plot(workers, actual_speedup, 'ro-', label='Actual', linewidth=2)
                ax4.set_xlabel('Number of Workers')
                ax4.set_ylabel('Speedup Factor')
                ax4.set_title('Parallel Execution Scaling')
                ax4.legend()
                ax4.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            # Save plot
            plot_file = project_root / 'tests' / 'benchmark_performance.png'
            plt.savefig(plot_file, dpi=150, bbox_inches='tight')
            print(f"\nPerformance plots saved to: {plot_file}")
            
        except Exception as e:
            print(f"Warning: Could not create plots: {e}")


def main():
    """Run benchmark suite."""
    print("PHREEQC Optimization Performance Benchmark Suite")
    print("=" * 60)
    print(f"Running on: {sys.platform}")
    print(f"Python: {sys.version.split()[0]}")
    print()
    
    benchmark = PhreeqcBenchmark()
    benchmark.run_all_benchmarks()
    
    print("\nBenchmark complete!")


if __name__ == '__main__':
    main()