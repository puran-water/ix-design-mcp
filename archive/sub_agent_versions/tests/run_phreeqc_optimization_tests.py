#!/usr/bin/env python3
"""
Test Runner for PHREEQC Optimization Test Suite

Executes all PHREEQC optimization tests and generates a comprehensive report.
Follows the PowerShell execution guidelines from CLAUDE.md.
"""

import sys
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestRunner:
    """Runs all PHREEQC optimization tests and collects results."""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'platform': sys.platform,
            'python_version': sys.version.split()[0],
            'tests': {}
        }
        self.test_files = [
            'test_phreeqc_optimization_real_data.py',
            'test_optimized_phreeqc_integration.py',
            'test_optimized_phreeqc_engine.py',  # Existing mock-based tests
            'test_phreeqc_engineering_validation.py',  # Existing validation tests
        ]
        
    def run_all_tests(self):
        """Run all test files and collect results."""
        print("PHREEQC Optimization Test Suite")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Platform: {sys.platform}")
        print(f"Python: {sys.version.split()[0]}")
        print()
        
        total_start = time.time()
        
        for test_file in self.test_files:
            self.run_test_file(test_file)
            
        # Run benchmarks separately
        self.run_benchmarks()
        
        total_time = time.time() - total_start
        self.results['total_time_seconds'] = total_time
        
        # Generate report
        self.generate_report()
        
    def run_test_file(self, test_file: str):
        """Run a single test file."""
        print(f"\nRunning {test_file}...")
        print("-" * 60)
        
        test_path = project_root / 'tests' / test_file
        if not test_path.exists():
            print(f"✗ Test file not found: {test_path}")
            self.results['tests'][test_file] = {
                'status': 'not_found',
                'time_seconds': 0
            }
            return
            
        start_time = time.time()
        
        if sys.platform == 'win32':
            # Use PowerShell with venv312 as specified in CLAUDE.md
            cmd = [
                'powershell.exe',
                '-Command',
                f'cd C:\\Users\\hvksh\\mcp-servers\\ix-design-mcp; '
                f'C:\\Users\\hvksh\\mcp-servers\\venv312\\Scripts\\python.exe '
                f'tests\\{test_file} -v'
            ]
        else:
            # Linux/Mac
            cmd = [sys.executable, str(test_path), '-v']
            
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per test file
            )
            
            duration = time.time() - start_time
            
            # Parse test results
            output_lines = result.stdout.split('\n')
            stderr_lines = result.stderr.split('\n')
            
            # Look for test summary
            tests_run = 0
            failures = 0
            errors = 0
            skipped = 0
            
            for line in output_lines + stderr_lines:
                if 'Ran ' in line and ' test' in line:
                    # Parse "Ran X tests in Y.Zs"
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == 'Ran':
                        tests_run = int(parts[1])
                elif 'FAILED' in line:
                    # Parse "FAILED (failures=X, errors=Y)"
                    if 'failures=' in line:
                        failures = int(line.split('failures=')[1].split(',')[0].split(')')[0])
                    if 'errors=' in line:
                        errors = int(line.split('errors=')[1].split(',')[0].split(')')[0])
                elif 'OK' in line and '(skipped=' in line:
                    # Parse "OK (skipped=X)"
                    skipped = int(line.split('skipped=')[1].split(')')[0])
                    
            success = result.returncode == 0
            
            self.results['tests'][test_file] = {
                'status': 'success' if success else 'failed',
                'time_seconds': duration,
                'tests_run': tests_run,
                'failures': failures,
                'errors': errors,
                'skipped': skipped,
                'return_code': result.returncode
            }
            
            # Print summary
            if success:
                print(f"✓ {test_file}: {tests_run} tests passed in {duration:.2f}s")
                if skipped > 0:
                    print(f"  (skipped {skipped} tests)")
            else:
                print(f"✗ {test_file}: FAILED - {failures} failures, {errors} errors")
                print(f"  Return code: {result.returncode}")
                
            # Print any warnings or important messages
            for line in output_lines:
                if 'warning' in line.lower() or 'error' in line.lower():
                    print(f"  ! {line.strip()}")
                    
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"✗ {test_file}: TIMEOUT after {duration:.2f}s")
            self.results['tests'][test_file] = {
                'status': 'timeout',
                'time_seconds': duration
            }
        except Exception as e:
            duration = time.time() - start_time
            print(f"✗ {test_file}: ERROR - {str(e)}")
            self.results['tests'][test_file] = {
                'status': 'error',
                'time_seconds': duration,
                'error': str(e)
            }
            
    def run_benchmarks(self):
        """Run performance benchmarks."""
        print(f"\nRunning Performance Benchmarks...")
        print("-" * 60)
        
        benchmark_file = 'benchmark_phreeqc_optimization.py'
        benchmark_path = project_root / 'tests' / benchmark_file
        
        if not benchmark_path.exists():
            print(f"✗ Benchmark file not found: {benchmark_path}")
            return
            
        start_time = time.time()
        
        if sys.platform == 'win32':
            cmd = [
                'powershell.exe',
                '-Command',
                f'cd C:\\Users\\hvksh\\mcp-servers\\ix-design-mcp; '
                f'C:\\Users\\hvksh\\mcp-servers\\venv312\\Scripts\\python.exe '
                f'tests\\{benchmark_file}'
            ]
        else:
            cmd = [sys.executable, str(benchmark_path)]
            
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for benchmarks
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                print(f"✓ Benchmarks completed in {duration:.2f}s")
                
                # Try to load benchmark results
                results_file = project_root / 'tests' / 'benchmark_results.json'
                if results_file.exists():
                    with open(results_file, 'r') as f:
                        benchmark_data = json.load(f)
                    self.results['benchmarks'] = benchmark_data
                    
                    # Print key metrics
                    print("\nKey Performance Metrics:")
                    if 'simple_equilibrium' in benchmark_data:
                        speedup = benchmark_data['simple_equilibrium'].get('speedup', 0)
                        print(f"  - Simple equilibrium speedup: {speedup:.1f}x")
                    if 'batch_processing' in benchmark_data:
                        speedup = benchmark_data['batch_processing'].get('speedup', 0)
                        print(f"  - Batch processing speedup: {speedup:.1f}x")
                    if 'parallel_execution' in benchmark_data:
                        speedup = benchmark_data['parallel_execution'].get('speedup', 0)
                        print(f"  - Parallel execution speedup: {speedup:.1f}x")
            else:
                print(f"✗ Benchmarks failed with return code: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"✗ Benchmarks: TIMEOUT after {duration:.2f}s")
        except Exception as e:
            print(f"✗ Benchmarks: ERROR - {str(e)}")
            
    def generate_report(self):
        """Generate comprehensive test report."""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        # Count results
        total_tests = len(self.test_files)
        passed = sum(1 for t in self.results['tests'].values() 
                    if t['status'] == 'success')
        failed = sum(1 for t in self.results['tests'].values() 
                    if t['status'] == 'failed')
        timeout = sum(1 for t in self.results['tests'].values() 
                     if t['status'] == 'timeout')
        not_found = sum(1 for t in self.results['tests'].values() 
                       if t['status'] == 'not_found')
        
        print(f"\nTotal test files: {total_tests}")
        print(f"✓ Passed: {passed}")
        print(f"✗ Failed: {failed}")
        print(f"⏱ Timeout: {timeout}")
        print(f"? Not found: {not_found}")
        
        # Detailed results
        print(f"\nDetailed Results:")
        print(f"{'Test File':<45} {'Status':<10} {'Time':>8} {'Tests':>6}")
        print("-" * 75)
        
        for test_file, result in self.results['tests'].items():
            status = result['status']
            time_str = f"{result['time_seconds']:.2f}s"
            tests_str = str(result.get('tests_run', '-'))
            
            # Color coding for terminal (if supported)
            if status == 'success':
                status_str = '✓ PASS'
            elif status == 'failed':
                status_str = '✗ FAIL'
            elif status == 'timeout':
                status_str = '⏱ TIME'
            else:
                status_str = '? ' + status.upper()[:4]
                
            print(f"{test_file:<45} {status_str:<10} {time_str:>8} {tests_str:>6}")
            
        # Total time
        total_time = self.results.get('total_time_seconds', 0)
        print("-" * 75)
        print(f"{'Total Time:':<45} {'':<10} {total_time:>8.2f}s")
        
        # Save detailed report
        report_file = project_root / 'tests' / 'test_report.json'
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\nDetailed report saved to: {report_file}")
        
        # Check for optimization benefits
        if 'benchmarks' in self.results:
            print("\n" + "=" * 60)
            print("OPTIMIZATION BENEFITS")
            print("=" * 60)
            
            avg_speedups = []
            benchmarks = self.results['benchmarks']
            
            for bench_name, bench_data in benchmarks.items():
                if isinstance(bench_data, dict) and 'speedup' in bench_data:
                    speedup = bench_data['speedup']
                    avg_speedups.append(speedup)
                    print(f"{bench_name}: {speedup:.1f}x faster")
                    
            if avg_speedups:
                overall_speedup = sum(avg_speedups) / len(avg_speedups)
                print(f"\nOverall average speedup: {overall_speedup:.1f}x")
                
        print("\n" + "=" * 60)
        print(f"Test suite completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    """Run the test suite."""
    runner = TestRunner()
    runner.run_all_tests()


if __name__ == '__main__':
    main()