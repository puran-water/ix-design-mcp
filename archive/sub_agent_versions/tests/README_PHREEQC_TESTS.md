# PHREEQC Optimization Test Suite

Comprehensive test suite for validating the OptimizedPhreeqcEngine implementation with real water chemistry data and engineering benchmarks.

## Test Files

### 1. `test_phreeqc_optimization_real_data.py`
**Purpose**: Tests using real water compositions from literature
- ✓ Validates correctness against DirectPhreeqcEngine
- ✓ Tests cache performance and correctness
- ✓ Verifies batch transport processing
- ✓ Tests parallel execution capabilities
- ✓ Validates mass and charge balance
- ✓ Tests edge cases (high TDS, low pH, etc.)

**Key Test Classes**:
- `TestRealWaterChemistry`: Real water composition tests
- `TestCacheCorrectnessValidation`: Cache integrity tests
- `TestErrorHandlingAndRecovery`: Error scenario tests
- `TestPerformanceBenchmarks`: Performance validation

### 2. `test_optimized_phreeqc_integration.py`
**Purpose**: Integration tests with SAC simulation workflow
- ✓ Complete SAC simulation with optimization
- ✓ Performance comparison (direct vs optimized)
- ✓ Batch vessel sizing optimization
- ✓ Process isolation via CLI
- ✓ Concurrent simulation stress tests
- ✓ Real-world scenarios (seawater, boiler feedwater)

**Key Test Classes**:
- `TestSACSimulationIntegration`: SAC workflow integration
- `TestOptimizationFeatures`: Specific optimization features
- `TestRealWorldScenarios`: Edge cases and special applications

### 3. `benchmark_phreeqc_optimization.py`
**Purpose**: Performance benchmark suite
- ✓ Simple equilibrium calculations
- ✓ Complex multi-phase equilibrium
- ✓ Transport simulations
- ✓ Batch processing performance
- ✓ Parallel execution scaling
- ✓ Cache performance with varying hit rates

**Output**:
- `benchmark_results.json`: Detailed performance metrics
- `benchmark_performance.png`: Performance visualization plots

### 4. `run_phreeqc_optimization_tests.py`
**Purpose**: Test runner with PowerShell integration
- ✓ Executes all tests in proper environment
- ✓ Follows CLAUDE.md PowerShell guidelines
- ✓ Generates comprehensive test report
- ✓ Collects performance metrics

**Output**:
- `test_report.json`: Complete test results and metrics

## Running the Tests

### Windows (PowerShell with venv312)
```powershell
# Run all tests
powershell.exe -Command "cd C:\Users\hvksh\mcp-servers\ix-design-mcp; C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe tests\run_phreeqc_optimization_tests.py"

# Run individual test file
powershell.exe -Command "cd C:\Users\hvksh\mcp-servers\ix-design-mcp; C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe tests\test_phreeqc_optimization_real_data.py -v"

# Run benchmarks only
powershell.exe -Command "cd C:\Users\hvksh\mcp-servers\ix-design-mcp; C:\Users\hvksh\mcp-servers\venv312\Scripts\python.exe tests\benchmark_phreeqc_optimization.py"
```

### Linux/Mac
```bash
# Run all tests
python tests/run_phreeqc_optimization_tests.py

# Run individual test file
python tests/test_phreeqc_optimization_real_data.py -v

# Run benchmarks only
python tests/benchmark_phreeqc_optimization.py
```

## Test Data Sources

All test data comes from validated engineering sources:

1. **Crittenden et al. (2012)**: "Water Treatment: Principles and Design"
   - Typical groundwater compositions
   - Ion exchange design parameters

2. **AWWA (2011)**: "Water Quality and Treatment"
   - Ion exchange equilibria and kinetics
   - Selectivity coefficients

3. **Harries & Gittins (1982)**: "Ion Exchange Pilot Plant Studies"
   - Pilot scale validation data
   - Breakthrough curve validation

4. **Dorfner (1991)**: "Ion Exchangers"
   - Resin capacity data
   - Temperature corrections

See `tests/fixtures/README.md` for complete source documentation.

## Key Validation Points

### 1. Correctness Validation
- Results must match DirectPhreeqcEngine within numerical precision
- Mass balance error < 0.1%
- Charge balance maintained

### 2. Performance Targets
- Simple equilibrium with cache: >50x speedup
- Batch transport: >2x speedup vs sequential
- Parallel execution: >1.5x speedup with 4 workers

### 3. Engineering Accuracy
- Ca removal: 95-98% for typical groundwater
- Breakthrough: 300-500 BV for moderate hardness
- Capacity utilization: 40-70% range

## Test Requirements

### Required Software
- Python 3.12+ (venv312)
- PHREEQC executable (3.7.3 or later)
- PowerShell (Windows)

### Python Dependencies
- pytest
- numpy
- matplotlib
- All dependencies from main project

## Continuous Integration

Tests should be run:
1. Before any release
2. After PHREEQC engine modifications
3. When updating water chemistry models
4. For performance regression testing

## Troubleshooting

### Common Issues

1. **PHREEQC not found**
   - Verify PHREEQC installation
   - Check path in `tools/core_config.py`

2. **Cache test failures**
   - Clear cache before testing
   - Check file permissions

3. **Parallel test failures**
   - Reduce max_workers if system limited
   - Check process limits

4. **Unicode errors on Windows**
   - Ensure UTF-8 encoding setup
   - Use PowerShell, not cmd.exe

## Contributing

When adding new tests:
1. Use real data with citations
2. No mock values or arbitrary numbers
3. Document all data sources
4. Include engineering validation
5. Update this README