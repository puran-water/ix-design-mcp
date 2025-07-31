#!/usr/bin/env python3
"""
Visualize chromatographic behavior in breakthrough curves
"""

import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from pathlib import Path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tools.sac_simulation import simulate_sac_phreeqc, SACSimulationInput, RegenerationConfig
from tools.sac_configuration import SACWaterComposition, SACVesselConfiguration

print("Visualizing Chromatographic Behavior")
print("=" * 70)

# Create test water composition
water = SACWaterComposition(
    flow_m3_hr=100.0,
    temperature_celsius=25.0,
    pH=7.5,
    pressure_bar=1.0,
    ca_mg_l=80.0,
    mg_mg_l=25.0,
    na_mg_l=800.0,
    cl_mg_l=1400.0,
    hco3_mg_l=120.0
)

# Create vessel configuration
vessel = SACVesselConfiguration(
    bed_volume_L=1000.0,
    service_flow_rate_bv_hr=16.0,
    vessel_id="SAC-001",
    number_service=1,
    number_standby=1,
    diameter_m=1.5,
    bed_depth_m=2.0,
    resin_volume_m3=1.0,
    freeboard_m=0.5,
    vessel_height_m=2.5
)

# Create regeneration config
regen_config = RegenerationConfig(
    enabled=True,
    regenerant_type="NaCl",
    concentration_percent=11.0,
    flow_rate_bv_hr=2.5,
    regenerant_bv=3.5,
    mode="staged_fixed",
    regeneration_stages=5
)

# Create simulation input
sim_input = SACSimulationInput(
    water_analysis=water,
    vessel_configuration=vessel,
    target_hardness_mg_l_caco3=5.0,
    regeneration_config=regen_config
)

# Run simulation
print("\nRunning simulation...")
result = simulate_sac_phreeqc(sim_input)

# Get breakthrough data
bd = result.breakthrough_data
breakthrough_bv = bd.get('breakthrough_bv', result.breakthrough_bv)

# Filter for service phase only
service_mask = [p == 'SERVICE' for p in bd['phases']]
service_bv = [bd['bed_volumes'][i] for i, m in enumerate(service_mask) if m]
service_ca_pct = [bd['ca_pct'][i] for i, m in enumerate(service_mask) if m]
service_mg_pct = [bd['mg_pct'][i] for i, m in enumerate(service_mask) if m]
service_na_mg_l = [bd['na_mg_l'][i] for i, m in enumerate(service_mask) if m]

# Create figure
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

# Plot 1: Ca and Mg breakthrough showing chromatographic separation
ax1.plot(service_bv, service_ca_pct, 'b-', linewidth=2, label='Ca²⁺')
ax1.plot(service_bv, service_mg_pct, 'g-', linewidth=2, label='Mg²⁺')

# Add vertical line at breakthrough
ax1.axvline(x=breakthrough_bv, color='red', linestyle='--', linewidth=1.5, 
            label=f'Target Hardness Breakthrough ({breakthrough_bv:.1f} BV)')

# Highlight Mg spike region
mg_spike_start = breakthrough_bv * 1.1
mg_spike_end = breakthrough_bv * 1.5
ax1.axvspan(mg_spike_start, mg_spike_end, alpha=0.2, color='green', 
            label='Expected Mg Spike Region')

ax1.set_xlabel('Bed Volumes')
ax1.set_ylabel('Concentration (% of Feed)')
ax1.set_title('Chromatographic Separation: Ca and Mg Breakthrough')
ax1.grid(True, alpha=0.3)
ax1.legend()
ax1.set_xlim(0, max(service_bv))
ax1.set_ylim(0, 200)  # Allow for Mg spike above 100%

# Plot 2: Na behavior
ax2.plot(service_bv, service_na_mg_l, 'orange', linewidth=2, label='Na⁺')
ax2.axhline(y=water.na_mg_l, color='orange', linestyle=':', linewidth=1, 
            label=f'Feed Na ({water.na_mg_l} mg/L)')
ax2.axvline(x=breakthrough_bv, color='red', linestyle='--', linewidth=1.5)

# Highlight initial Na spike region
ax2.axvspan(0, 10, alpha=0.2, color='orange', label='Na Spike Region (Regenerant Flush)')

ax2.set_xlabel('Bed Volumes')
ax2.set_ylabel('Na Concentration (mg/L)')
ax2.set_title('Na Release During Service')
ax2.grid(True, alpha=0.3)
ax2.legend()
ax2.set_xlim(0, max(service_bv))

plt.tight_layout()

# Save plot
output_file = Path("chromatographic_behavior_plot.png")
plt.savefig(output_file, dpi=150, bbox_inches='tight')
print(f"\n✓ Plot saved to {output_file}")

# Print summary
print("\n=== CHROMATOGRAPHIC FEATURES SUMMARY ===")
print(f"1. Na spike at start: {max(service_na_mg_l[:10]):.1f} mg/L (feed: {water.na_mg_l} mg/L)")
mg_spike_indices = [i for i, bv in enumerate(service_bv) if mg_spike_start <= bv <= mg_spike_end]
if mg_spike_indices:
    mg_spike_values = [service_mg_pct[i] for i in mg_spike_indices]
    print(f"2. Mg spike maximum: {max(mg_spike_values):.1f}% of feed")
else:
    print("2. Mg spike: No data in expected region")
print(f"3. Service data extends to: {max(service_bv):.1f} BV (breakthrough at {breakthrough_bv:.1f} BV)")
print(f"4. Data points: {len(service_bv)} (after smart sampling)")