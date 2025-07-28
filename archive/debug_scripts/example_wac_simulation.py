#!/usr/bin/env python3
"""
Example: Weak Acid Cation (WAC) Resin Simulation

This example demonstrates how to use the enhanced IX simulation system
with WAC resin, which has pH-dependent capacity and different selectivity
compared to SAC resin.

WAC characteristics:
- Higher capacity (4.5 eq/L) but pH-dependent
- Selective for hardness over sodium at pH > 5
- Used for dealkalization and partial softening
- Regenerated with acid (HCl or H2SO4)
"""

import sys
import json
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import the enhanced simulation module
from test_sac_enhanced import run_ix_simulation
from resin_properties import ResinDatabase


def create_wac_configuration():
    """Create a configuration for WAC system."""
    config = {
        "ix_vessels": {
            "WAC": {
                "resin_type": "WAC",
                "diameter_m": 1.5,
                "bed_depth_m": 2.0,
                "resin_volume_m3": 3.534  # π × (0.75)² × 2.0
            }
        },
        "water_analysis": {
            "flow_m3_hr": 50.0,
            "pH": 7.8,  # Important for WAC
            "temperature_celsius": 20.0,
            "ion_concentrations_mg_L": {
                "Ca_2+": 120.0,   # Lower hardness than SAC example
                "Mg_2+": 40.0,
                "Na_+": 30.0,
                "K_+": 5.0,
                "Cl_-": 150.0,
                "HCO3_-": 350.0,  # High alkalinity - good for WAC
                "SO4_2-": 50.0,
                "NO3_-": 10.0
            }
        }
    }
    return config


def analyze_wac_performance(results):
    """Analyze WAC-specific performance metrics."""
    if results['status'] != 'success':
        print(f"Simulation failed: {results.get('message', 'Unknown error')}")
        return
    
    print("\n" + "="*70)
    print("WAC PERFORMANCE ANALYSIS")
    print("="*70)
    
    # Extract data
    bv = np.array(results['breakthrough_curves']['BV'])
    ca = np.array(results['breakthrough_curves']['Ca_mg_L'])
    mg = np.array(results['breakthrough_curves']['Mg_mg_L'])
    na = np.array(results['breakthrough_curves']['Na_mg_L'])
    hco3 = np.array(results['breakthrough_curves']['HCO3_mg_L'])
    pH_array = np.array(results['breakthrough_curves']['pH'])
    
    # Performance metrics
    perf = results['performance']
    print(f"\nService Performance:")
    print(f"  Service time: {perf['service_time_hours']:.1f} hours")
    print(f"  Breakthrough: {perf['breakthrough_BV']:.1f} BV")
    print(f"  Ca removal: {perf['ca_removal_percent']:.1f}%")
    print(f"  Regeneration interval: {perf['regeneration_interval_days']:.1f} days")
    
    # Resin properties
    resin = results['resin_properties']
    print(f"\nResin Properties:")
    print(f"  Type: {resin['name']}")
    print(f"  Capacity: {resin['capacity_eq_L']} eq/L (at operating pH)")
    print(f"  Porosity: {resin['porosity']}")
    
    # WAC-specific analysis
    print(f"\nWAC-Specific Features:")
    
    # 1. Alkalinity reduction
    initial_alk = 350.0  # mg/L as HCO3
    min_alk_idx = np.argmin(hco3)
    min_alk = hco3[min_alk_idx]
    alk_reduction = (initial_alk - min_alk) / initial_alk * 100
    print(f"  Max alkalinity reduction: {alk_reduction:.1f}%")
    print(f"  Minimum alkalinity: {min_alk:.1f} mg/L at {bv[min_alk_idx]:.1f} BV")
    
    # 2. pH effects
    initial_pH = 7.8
    min_pH = np.min(pH_array)
    max_pH = np.max(pH_array)
    print(f"  pH range: {min_pH:.1f} - {max_pH:.1f} (feed: {initial_pH})")
    
    # 3. Selectivity demonstration
    # WAC preferentially removes Ca/Mg over Na at neutral pH
    ca_50_idx = next((i for i, c in enumerate(ca) if c > 60), None)
    if ca_50_idx:
        na_at_ca50 = na[ca_50_idx]
        na_increase = (na_at_ca50 - 30) / 30 * 100
        print(f"  Na increase at Ca 50% breakthrough: {na_increase:.1f}%")
        print(f"  Demonstrates hardness selectivity over Na")
    
    # Create WAC-specific plots
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Plot 1: Hardness breakthrough
    ax1 = axes[0, 0]
    ax1.plot(bv, ca, 'b-', linewidth=2, label='Ca')
    ax1.plot(bv, mg, 'g--', linewidth=2, label='Mg')
    ax1.axhline(y=5, color='red', linestyle=':', alpha=0.5, label='5 mg/L limit')
    ax1.set_xlabel('Bed Volumes')
    ax1.set_ylabel('Concentration (mg/L)')
    ax1.set_title('Hardness Breakthrough - WAC')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(0, min(200, bv.max()))
    
    # Plot 2: Alkalinity reduction
    ax2 = axes[0, 1]
    alk_removal = (350 - hco3) / 350 * 100
    ax2.plot(bv, alk_removal, 'purple', linewidth=2)
    ax2.set_xlabel('Bed Volumes')
    ax2.set_ylabel('Alkalinity Removal (%)')
    ax2.set_title('Dealkalization Performance')
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(0, min(200, bv.max()))
    ax2.set_ylim(0, 100)
    
    # Plot 3: pH profile
    ax3 = axes[1, 0]
    ax3.plot(bv, pH_array, 'k-', linewidth=2)
    ax3.axhline(y=7.8, color='blue', linestyle='--', alpha=0.5, label='Feed pH')
    ax3.axhline(y=5.0, color='red', linestyle='--', alpha=0.5, label='Min operating pH')
    ax3.set_xlabel('Bed Volumes')
    ax3.set_ylabel('pH')
    ax3.set_title('Effluent pH Profile')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    ax3.set_xlim(0, min(200, bv.max()))
    ax3.set_ylim(4, 9)
    
    # Plot 4: Na leakage
    ax4 = axes[1, 1]
    ax4.plot(bv, na, 'orange', linewidth=2)
    ax4.axhline(y=30, color='gray', linestyle='--', alpha=0.5, label='Feed Na')
    ax4.set_xlabel('Bed Volumes')
    ax4.set_ylabel('Na Concentration (mg/L)')
    ax4.set_title('Sodium Leakage Profile')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    ax4.set_xlim(0, min(200, bv.max()))
    
    # Add summary text
    summary = (
        f"WAC Performance Summary\n"
        f"Capacity: {resin['capacity_eq_L']} eq/L\n"
        f"Service: {perf['breakthrough_BV']:.0f} BV\n"
        f"Alkalinity reduction: {alk_reduction:.0f}%\n"
        f"Regenerant: HCl"
    )
    fig.text(0.02, 0.02, summary, fontsize=10, 
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.suptitle('WAC (Weak Acid Cation) Resin Performance Analysis', fontsize=16)
    plt.tight_layout()
    plt.savefig('wac_performance_analysis.png', dpi=150, bbox_inches='tight')
    print(f"\nSaved analysis plot: wac_performance_analysis.png")
    
    # Save detailed results
    with open('wac_simulation_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved detailed results: wac_simulation_results.json")


def compare_wac_vs_sac():
    """Compare WAC and SAC performance on the same water."""
    print("\n" + "="*70)
    print("COMPARING WAC vs SAC PERFORMANCE")
    print("="*70)
    
    # Common water analysis
    water = {
        "flow_m3_hr": 50.0,
        "pH": 7.8,
        "temperature_celsius": 20.0,
        "ion_concentrations_mg_L": {
            "Ca_2+": 120.0,
            "Mg_2+": 40.0,
            "Na_+": 30.0,
            "K_+": 5.0,
            "Cl_-": 150.0,
            "HCO3_-": 350.0,
            "SO4_2-": 50.0,
            "NO3_-": 10.0
        }
    }
    
    # WAC configuration
    wac_config = {
        "ix_vessels": {
            "WAC": {
                "resin_type": "WAC",
                "diameter_m": 1.5,
                "bed_depth_m": 2.0,
                "resin_volume_m3": 3.534
            }
        },
        "water_analysis": water
    }
    
    # SAC configuration (same vessel size)
    sac_config = {
        "ix_vessels": {
            "SAC": {
                "resin_type": "SAC",
                "diameter_m": 1.5,
                "bed_depth_m": 2.0,
                "resin_volume_m3": 3.534
            }
        },
        "water_analysis": water
    }
    
    # Run simulations
    print("\nRunning WAC simulation...")
    wac_results = run_ix_simulation(wac_config, vessel_type='WAC', plot_results=False)
    
    print("\nRunning SAC simulation...")
    sac_results = run_ix_simulation(sac_config, vessel_type='SAC', plot_results=False)
    
    if wac_results['status'] == 'success' and sac_results['status'] == 'success':
        print("\n" + "-"*50)
        print("COMPARISON RESULTS")
        print("-"*50)
        print("Parameter           | WAC      | SAC      | Units")
        print("--------------------|----------|----------|-------")
        print(f"Capacity            | {wac_results['resin_properties']['capacity_eq_L']:8.1f} | "
              f"{sac_results['resin_properties']['capacity_eq_L']:8.1f} | eq/L")
        print(f"Service time        | {wac_results['performance']['service_time_hours']:8.1f} | "
              f"{sac_results['performance']['service_time_hours']:8.1f} | hours")
        print(f"Breakthrough        | {wac_results['performance']['breakthrough_BV']:8.1f} | "
              f"{sac_results['performance']['breakthrough_BV']:8.1f} | BV")
        print(f"Ca removal          | {wac_results['performance']['ca_removal_percent']:8.1f} | "
              f"{sac_results['performance']['ca_removal_percent']:8.1f} | %")
        
        print("\nKey differences:")
        print("- WAC has higher capacity (4.5 vs 2.0 eq/L)")
        print("- WAC provides alkalinity reduction")
        print("- WAC has minimal Na leakage")
        print("- SAC provides complete softening")
        print("- SAC requires salt regeneration")


def main():
    """Run WAC resin example."""
    print("\n" + "="*70)
    print("WEAK ACID CATION (WAC) RESIN EXAMPLE")
    print("="*70)
    
    # Initialize resin database
    db = ResinDatabase()
    
    # Show WAC properties
    wac_props = db.get_resin('WAC')
    print(f"\nWAC Resin Properties from Database:")
    print(f"  Name: {wac_props['name']}")
    print(f"  Functional group: {wac_props['functional_group']}")
    print(f"  Capacity: {wac_props['capacity']['value']} {wac_props['capacity']['units']}")
    print(f"  pKa: {wac_props.get('pKa', 'N/A')}")
    print(f"  Operating pH range: {wac_props['operating']['pH_range']}")
    
    # Create configuration
    config = create_wac_configuration()
    
    # Run simulation
    print("\nRunning WAC simulation with enhanced system...")
    results = run_ix_simulation(
        config, 
        vessel_type='WAC',
        cells=10,  # Standard resolution
        target_bv=200,  # Extended run to see full breakthrough
        plot_results=False,  # We'll make custom plots
        resin_db=db
    )
    
    # Analyze results
    if results['status'] == 'success':
        analyze_wac_performance(results)
    
    # Compare with SAC
    compare_wac_vs_sac()
    
    print("\n" + "="*70)
    print("WAC EXAMPLE COMPLETE")
    print("="*70)
    print("\nKey takeaways:")
    print("1. WAC has higher capacity but is pH-dependent")
    print("2. Excellent for high alkalinity waters")
    print("3. Provides partial softening with dealkalization")
    print("4. Lower regenerant consumption than SAC")
    print("5. Can be used in WAC-SAC series for optimal performance")


if __name__ == "__main__":
    main()