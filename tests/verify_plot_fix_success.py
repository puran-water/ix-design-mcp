#!/usr/bin/env python3
"""
Final verification that plot fixes are working correctly
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

from tools.sac_simulation import simulate_sac_phreeqc, SACSimulationInput, RegenerationConfig
from tools.sac_configuration import SACWaterComposition, SACVesselConfiguration

print("Final Verification of Plot Fix")
print("=" * 70)

# Create test water
water = SACWaterComposition(
    flow_m3_hr=100.0,
    temperature_celsius=25.0,
    pH=7.5,
    pressure_bar=1.0,
    ca_mg_l=80.0,
    mg_mg_l=25.0,
    na_mg_l=800.0,  # High Na
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

# Find indices for different phases (check both uppercase and lowercase)
service_idx = [i for i, p in enumerate(bd['phases']) if p.lower() == 'service']
regen_idx = [i for i, p in enumerate(bd['phases']) if p.lower() == 'regeneration']

print("\n=== VERIFICATION RESULTS ===")
print(f"Total data points: {len(bd['bed_volumes'])}")
print(f"Service points: {len(service_idx)}")
print(f"Regeneration points: {len(regen_idx)}")

# Check service phase
if service_idx:
    print("\n1. SERVICE PHASE (first 10 points):")
    for i in service_idx[:10]:
        print(f"   BV={bd['bed_volumes'][i]:6.1f}: Ca={bd['ca_mg_l'][i]:6.2f} mg/L, "
              f"Mg={bd['mg_mg_l'][i]:6.2f} mg/L, Na={bd['na_mg_l'][i]:7.1f} mg/L")
    
    # Check Na values
    na_values = [bd['na_mg_l'][i] for i in service_idx[:20]]
    na_avg = sum(na_values) / len(na_values)
    print(f"\n   Average Na in early service: {na_avg:.1f} mg/L")
    print(f"   Expected Na (feed): {water.na_mg_l} mg/L")
    print(f"   {'✓ PASS' if abs(na_avg - water.na_mg_l) < 50 else '✗ FAIL'}: Na values are {'correct' if abs(na_avg - water.na_mg_l) < 50 else 'STILL WRONG'}!")

# Check regeneration phase
if regen_idx:
    print("\n2. REGENERATION PHASE (sample points):")
    sample_indices = regen_idx[::len(regen_idx)//5] if len(regen_idx) > 5 else regen_idx
    for i in sample_indices:
        print(f"   BV={bd['bed_volumes'][i]:6.1f}: Ca={bd['ca_mg_l'][i]:7.1f} mg/L, "
              f"Mg={bd['mg_mg_l'][i]:7.1f} mg/L, Na={bd['na_mg_l'][i]:8.1f} mg/L")
    
    # Check Na in regeneration
    na_regen_max = max(bd['na_mg_l'][i] for i in regen_idx)
    print(f"\n   Max Na in regeneration: {na_regen_max:.1f} mg/L")
    print(f"   Expected Na (11% NaCl): ~42,000 mg/L")
    print(f"   {'✓ PASS' if na_regen_max > 20000 else '✗ FAIL'}: Na regeneration values are {'correct' if na_regen_max > 20000 else 'STILL WRONG'}!")

# Check for hardcoded multipliers
print("\n3. CHECKING FOR HARDCODED MULTIPLIERS:")
if service_idx:
    # Check if Ca values are multiplied by 180
    ca_early = [bd['ca_mg_l'][i] for i in service_idx[:5]]
    ca_suspicious = any(ca > 100 for ca in ca_early)  # Early service should have low Ca
    print(f"   Early service Ca values: {[f'{ca:.2f}' for ca in ca_early]}")
    print(f"   {'✗ FAIL' if ca_suspicious else '✓ PASS'}: Ca values {'appear to be multiplied by 180' if ca_suspicious else 'are reasonable'}!")
    
    # Check if Mg values are multiplied by 80
    mg_early = [bd['mg_mg_l'][i] for i in service_idx[:5]]
    mg_suspicious = any(mg > 50 for mg in mg_early)  # Early service should have low Mg
    print(f"   Early service Mg values: {[f'{mg:.2f}' for mg in mg_early]}")
    print(f"   {'✗ FAIL' if mg_suspicious else '✓ PASS'}: Mg values {'appear to be multiplied by 80' if mg_suspicious else 'are reasonable'}!")

# Overall result
print("\n=== OVERALL RESULT ===")
all_checks_pass = (
    service_idx and 
    abs(na_avg - water.na_mg_l) < 50 and  # Na correct
    not ca_suspicious and  # Ca not multiplied
    not mg_suspicious and  # Mg not multiplied
    na_regen_max > 20000  # Regeneration Na high
)

if all_checks_pass:
    print("✓ ALL CHECKS PASSED! The plotting fix is working correctly.")
    print("  - Na shows actual feed concentration (~800 mg/L) during service")
    print("  - Ca/Mg are NOT multiplied by hardcoded factors")
    print("  - Regeneration shows high Na concentration from brine")
else:
    print("✗ Some checks failed. The fix may not be complete.")