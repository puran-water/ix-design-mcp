#!/usr/bin/env python3
"""
Performance Benchmark for IX Model

Measures execution time and memory usage for various IX model configurations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import psutil
import numpy as np
from pyomo.environ import ConcreteModel, value
from idaes.core import FlowsheetBlock
from idaes.models.unit_models import Feed, Product
from pyomo.network import Arc
from pyomo.environ import TransformationFactory
from idaes.core.util.initialization import propagate_state

# Performance tracking
benchmarks = []

def measure_performance(func):
    """Decorator to measure function performance"""
    def wrapper(*args, **kwargs):
        # Memory before
        process = psutil.Process()
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        
        # Time execution
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        # Memory after
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        
        # Record benchmark
        benchmark = {
            'function': func.__name__,
            'time_seconds': end_time - start_time,
            'memory_mb': mem_after - mem_before,
            'args': str(args),
            'kwargs': str(kwargs)
        }
        benchmarks.append(benchmark)
        print(f"{func.__name__}: {benchmark['time_seconds']:.3f}s, {benchmark['memory_mb']:.1f}MB")
        
        return result
    return wrapper

@measure_performance
def benchmark_basic_ix_model(resin_type='SAC', number_of_beds=1):
    """Benchmark basic IX model creation and solve"""
    from watertap_ix_transport import IonExchangeTransport0D, ResinType, RegenerantChem
    from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis
    
    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Property package
    m.fs.properties = MCASParameterBlock(
        solute_list=["Ca_2+", "Mg_2+", "Na_+", "Cl_-", "HCO3_-"],
        material_flow_basis=MaterialFlowBasis.mass
    )
    
    # Create IX unit
    m.fs.ix_unit = IonExchangeTransport0D(
        property_package=m.fs.properties,
        resin_type=getattr(ResinType, resin_type),
        regenerant=RegenerantChem.NaCl,
        number_of_beds=number_of_beds
    )
    
    # Set parameters
    m.fs.ix_unit.bed_depth.set_value(2.0)
    m.fs.ix_unit.bed_diameter.set_value(1.5)
    
    # Create feed
    m.fs.feed = Feed(property_package=m.fs.properties)
    
    # Set feed conditions
    flow_rate_m3s = 100/3600
    m.fs.feed.outlet.temperature[0].fix(298.15)
    m.fs.feed.outlet.pressure[0].fix(101325)
    
    # Component flows
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Ca_2+'].fix(180 * flow_rate_m3s * 1e-3)
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Mg_2+'].fix(80 * flow_rate_m3s * 1e-3)
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Na_+'].fix(50 * flow_rate_m3s * 1e-3)
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Cl_-'].fix(350 * flow_rate_m3s * 1e-3)
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'HCO3_-'].fix(300 * flow_rate_m3s * 1e-3)
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(flow_rate_m3s * 1000 - 0.96)
    
    # Connect units
    m.fs.arc1 = Arc(source=m.fs.feed.outlet, destination=m.fs.ix_unit.inlet)
    
    # Create product
    m.fs.product = Product(property_package=m.fs.properties)
    m.fs.arc2 = Arc(source=m.fs.ix_unit.outlet, destination=m.fs.product.inlet)
    
    # Expand arcs
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    # Initialize and solve
    m.fs.feed.initialize()
    propagate_state(m.fs.arc1)
    m.fs.ix_unit.initialize()
    propagate_state(m.fs.arc2)
    m.fs.product.initialize()
    
    return m

@measure_performance  
def benchmark_phreeqc_calculation(model):
    """Benchmark PHREEQC performance calculation"""
    model.fs.ix_unit.calculate_performance()
    return model

@measure_performance
def benchmark_large_system():
    """Benchmark large IX system with multiple beds"""
    return benchmark_basic_ix_model(resin_type='SAC', number_of_beds=4)

@measure_performance
def benchmark_kinetics_calculation():
    """Benchmark IX model with kinetics"""
    from watertap_ix_transport import IonExchangeTransport0D, ResinType, RegenerantChem
    from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis
    
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    m.fs.properties = MCASParameterBlock(
        solute_list=["Ca_2+", "Mg_2+", "Na_+", "Cl_-"],
        material_flow_basis=MaterialFlowBasis.mass
    )
    
    # Create IX unit with kinetics enabled
    m.fs.ix_unit = IonExchangeTransport0D(
        property_package=m.fs.properties,
        resin_type=ResinType.SAC,
        regenerant=RegenerantChem.NaCl,
        include_kinetics=True
    )
    
    return m

def generate_report():
    """Generate performance report"""
    print("\n" + "="*60)
    print("IX MODEL PERFORMANCE BENCHMARK REPORT")
    print("="*60)
    
    # Summary statistics
    total_time = sum(b['time_seconds'] for b in benchmarks)
    total_memory = sum(b['memory_mb'] for b in benchmarks)
    
    print(f"\nTotal execution time: {total_time:.3f} seconds")
    print(f"Total memory usage: {total_memory:.1f} MB")
    print(f"Number of benchmarks: {len(benchmarks)}")
    
    # Detailed results
    print("\nDetailed Results:")
    print("-"*60)
    print(f"{'Function':<30} {'Time (s)':<10} {'Memory (MB)':<12}")
    print("-"*60)
    
    for b in benchmarks:
        print(f"{b['function']:<30} {b['time_seconds']:<10.3f} {b['memory_mb']:<12.1f}")
    
    # Performance recommendations
    print("\nPerformance Analysis:")
    slowest = max(benchmarks, key=lambda x: x['time_seconds'])
    print(f"  Slowest operation: {slowest['function']} ({slowest['time_seconds']:.3f}s)")
    
    memory_heavy = max(benchmarks, key=lambda x: x['memory_mb'])
    print(f"  Most memory intensive: {memory_heavy['function']} ({memory_heavy['memory_mb']:.1f}MB)")
    
    # Check for performance issues
    if total_time > 30:
        print("\n⚠ WARNING: Total execution time exceeds 30 seconds")
        print("  Consider optimizing PHREEQC calculations or using parallel processing")
    
    if total_memory > 500:
        print("\n⚠ WARNING: High memory usage detected")
        print("  Consider reducing model complexity or using sparse matrices")

def main():
    """Run all benchmarks"""
    print("Starting IX Model Performance Benchmarks...")
    print(f"System: {sys.platform}")
    print(f"Python: {sys.version}")
    print(f"CPU cores: {psutil.cpu_count()}")
    print(f"Total RAM: {psutil.virtual_memory().total / 1024**3:.1f} GB")
    print()
    
    # Run benchmarks
    model1 = benchmark_basic_ix_model('SAC', 1)
    benchmark_phreeqc_calculation(model1)
    
    model2 = benchmark_basic_ix_model('WAC_H', 2)
    
    benchmark_large_system()
    
    benchmark_kinetics_calculation()
    
    # Generate report
    generate_report()
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)