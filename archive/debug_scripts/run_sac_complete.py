#!/usr/bin/env python3
"""
Complete SAC simulation with proper data extraction and plotting
"""

import sys
import json
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from test_sac_with_config import run_sac_simulation

# Configuration
config = {
    "ix_vessels": {
        "SAC": {
            "diameter_m": 0.1,
            "bed_depth_m": 2.0,
            "resin_volume_m3": 0.0157
        }
    },
    "water_analysis": {
        "flow_m3_hr": 0.2,
        "ion_concentrations_mg_L": {
            "Ca_2+": 180.0,
            "Mg_2+": 80.0,
            "Na_+": 50.0,
            "Cl_-": 400.0,
            "HCO3_-": 300.0
        }
    }
}

print("Running complete SAC simulation...")
print("This will take a few minutes...")

# Run simulation
results = run_sac_simulation(
    config=config,
    cells=10,
    target_bv=250,
    plot_results=False  # We'll make our own plot
)

if results['status'] == 'success':
    print("\n[SUCCESS] Simulation completed!")
    
    # Save results
    with open('sac_complete_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("Saved results to sac_complete_results.json")
    
    # Extract data
    bv = np.array(results['breakthrough_curves']['BV'])
    ca = np.array(results['breakthrough_curves']['Ca_mg_L'])
    mg = np.array(results['breakthrough_curves']['Mg_mg_L'])
    na = np.array(results['breakthrough_curves']['Na_mg_L'])
    
    # Data summary
    print(f"\nData summary:")
    print(f"  Data points: {len(bv)}")
    print(f"  BV range: {bv.min():.1f} to {bv.max():.1f}")
    print(f"  Ca range: {ca.min():.3f} to {ca.max():.1f} mg/L")
    print(f"  Service time: {results['performance']['service_time_hours']:.1f} hours")
    print(f"  Breakthrough: {results['performance']['breakthrough_BV']:.1f} BV")
    
    # Create improved plot
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Plot 1: Breakthrough curves (absolute concentrations)
    ax1.plot(bv, ca, 'b-', linewidth=2.5, label='Ca')
    ax1.plot(bv, mg, 'g--', linewidth=2.5, label='Mg')
    
    # Mark key points
    ax1.axhline(y=180, color='blue', linestyle=':', alpha=0.3, label='Ca feed (180 mg/L)')
    ax1.axhline(y=80, color='green', linestyle=':', alpha=0.3, label='Mg feed (80 mg/L)')
    ax1.axhline(y=5, color='red', linestyle='-', alpha=0.5, linewidth=2, label='5 mg/L threshold')
    
    # Mark breakthrough
    breakthrough_bv = results['performance']['breakthrough_BV']
    ax1.axvline(x=breakthrough_bv, color='red', linestyle='--', alpha=0.7, 
               linewidth=2, label=f'Service: {breakthrough_bv:.1f} BV')
    
    ax1.set_xlabel('Bed Volumes', fontsize=12)
    ax1.set_ylabel('Concentration (mg/L)', fontsize=12)
    ax1.set_title('Ion Exchange Breakthrough Curves', fontsize=14)
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(0, 250)
    ax1.set_ylim(0, 200)
    
    # Plot 2: Normalized breakthrough with Na
    ca_norm = ca / 180
    mg_norm = mg / 80
    
    ax2_twin = ax2.twinx()  # Secondary y-axis for Na
    
    # Plot normalized hardness
    ax2.plot(bv, ca_norm, 'b-', linewidth=2.5, label='Ca (C/C₀)')
    ax2.plot(bv, mg_norm, 'g--', linewidth=2.5, label='Mg (C/C₀)')
    ax2.axhline(y=0.5, color='gray', linestyle=':', alpha=0.5)
    ax2.axhline(y=0.05, color='red', linestyle=':', alpha=0.5)
    
    # Plot Na on secondary axis
    ax2_twin.plot(bv, na, 'r-', linewidth=2, alpha=0.7, label='Na')
    ax2_twin.set_ylabel('Na Concentration (mg/L)', fontsize=12, color='red')
    ax2_twin.tick_params(axis='y', labelcolor='red')
    
    ax2.set_xlabel('Bed Volumes', fontsize=12)
    ax2.set_ylabel('Normalized Concentration (C/C₀)', fontsize=12)
    ax2.set_title('Normalized Breakthrough & Na Release', fontsize=14)
    ax2.legend(loc='upper left')
    ax2_twin.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(0, 250)
    ax2.set_ylim(0, 1.1)
    
    # Add configuration info
    config_text = (
        f"Column: {config['ix_vessels']['SAC']['diameter_m']:.1f}m Ø × "
        f"{config['ix_vessels']['SAC']['bed_depth_m']:.1f}m\n"
        f"Flow: {config['water_analysis']['flow_m3_hr']:.1f} m³/hr\n"
        f"Service: {results['performance']['service_time_hours']:.1f} hrs\n"
        f"Ca removal: {results['performance']['ca_removal_percent']:.1f}%"
    )
    ax1.text(0.02, 0.98, config_text, transform=ax1.transAxes, 
            verticalalignment='top', horizontalalignment='left',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
            fontsize=10)
    
    plt.suptitle('SAC Ion Exchange Performance - Complete Analysis', fontsize=16)
    plt.tight_layout()
    
    # Save plot
    output_file = 'sac_breakthrough_complete.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\nSaved comprehensive plot: {output_file}")
    
    # Create zoomed plot for breakthrough region
    fig2, ax = plt.subplots(figsize=(10, 6))
    
    # Find breakthrough region
    breakthrough_region = (bv >= 180) & (bv <= 220)
    
    ax.plot(bv[breakthrough_region], ca[breakthrough_region], 'bo-', 
            linewidth=2, markersize=6, label='Ca')
    ax.plot(bv[breakthrough_region], mg[breakthrough_region], 'gs-', 
            linewidth=2, markersize=6, label='Mg')
    
    ax.axhline(y=5, color='red', linestyle='-', linewidth=2, 
               label='5 mg/L service threshold')
    ax.axhline(y=90, color='blue', linestyle='--', alpha=0.5, 
               label='50% Ca breakthrough')
    ax.axvline(x=breakthrough_bv, color='red', linestyle='--', linewidth=2,
               label=f'Service end: {breakthrough_bv:.1f} BV')
    
    ax.set_xlabel('Bed Volumes', fontsize=12)
    ax.set_ylabel('Concentration (mg/L)', fontsize=12)
    ax.set_title('Breakthrough Region Detail', fontsize=14)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('sac_breakthrough_zoom.png', dpi=150, bbox_inches='tight')
    print(f"Saved zoomed plot: sac_breakthrough_zoom.png")
    
else:
    print(f"\n[ERROR] Simulation failed: {results.get('message', 'Unknown error')}")
    print("Check the log output above for details.")