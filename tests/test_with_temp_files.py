#!/usr/bin/env python
"""
Test with keep_temp_files=True to inspect PHREEQC input/output.
This will help verify if our custom exchange species are being used.
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force reload
for module in ['tools.sac_simulation', 'tools.wac_simulation',
               'watertap_ix_transport.transport_core.direct_phreeqc_engine']:
    if module in sys.modules:
        del sys.modules[module]

from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine
from tools.sac_simulation import SACSimulation, SACWaterComposition
from tools.simulate_ix_hybrid import simulate_ix_hybrid

def test_sac_with_temp_files():
    """Test SAC with temp files kept for inspection."""

    print("\n" + "="*60)
    print("TESTING SAC WITH TEMP FILE RETENTION")
    print("="*60)

    # Create engine with keep_temp_files
    engine = DirectPhreeqcEngine(keep_temp_files=True)
    print(f"Keep temp files: {engine.keep_temp_files}")

    # Create simulation
    sim = SACSimulation()
    sim.engine = engine  # Override with our debug engine

    water = SACWaterComposition(
        flow_m3_hr=10,
        ca_mg_l=100,
        mg_mg_l=30,
        na_mg_l=100,
        cl_mg_l=300,
        hco3_mg_l=61,
        temperature_celsius=25,
        pH=7.5
    )

    vessel = {
        'diameter_m': 1.0,
        'bed_depth_m': 1.5,
        'bed_volume_L': 3.14159 * 0.5**2 * 1.5 * 1000,
        'resin_capacity_eq_L': 2.0,
        'dvb_percent': 16  # High DVB for maximum effect
    }

    print("\nRunning SAC simulation with 16% DVB...")
    try:
        bv_array, curves = sim.run_sac_simulation(
            water=water,
            vessel_config=vessel,
            max_bv=50,  # Short run for quick inspection
            cells=5,
            enable_enhancements=True
        )
        print(f"  Simulation completed, {len(bv_array)} data points")

        # Check temp files
        if engine.temp_dirs:
            temp_path = Path(engine.temp_dirs[-1])  # Most recent temp dir
        else:
            import tempfile
            temp_path = Path(tempfile.gettempdir()) / "phreeqc_test"

        if temp_path.exists():
            files = list(temp_path.glob("*"))
            print(f"\nTemp files created ({len(files)}):")
            for f in files[:10]:  # Show first 10
                print(f"  - {f.name}")

            # Read input file
            input_file = temp_path / "input.pqi"
            if input_file.exists():
                with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Check for our custom exchange species
                print("\nChecking PHREEQC input for custom species:")
                if "EXCHANGE_MASTER_SPECIES" in content:
                    print("  ✓ EXCHANGE_MASTER_SPECIES found")
                else:
                    print("  ✗ EXCHANGE_MASTER_SPECIES NOT found")

                if "EXCHANGE_SPECIES" in content:
                    print("  ✓ EXCHANGE_SPECIES found")
                    # Extract Ca exchange log_k
                    import re
                    match = re.search(r'Ca\+2.*?CaX2.*?\n.*?log_k\s+([\d.-]+)', content, re.DOTALL)
                    if match:
                        log_k = float(match.group(1))
                        print(f"  ✓ Ca log_k = {log_k:.3f}")
                        if abs(log_k - 0.487) < 0.01:
                            print("  ✓ Correct 16% DVB value!")
                        else:
                            print(f"  ✗ Wrong value (expected 0.487)")
                else:
                    print("  ✗ EXCHANGE_SPECIES NOT found")

                # Save a copy for inspection
                debug_file = Path("debug_sac_input.pqi")
                with open(debug_file, 'w') as f:
                    f.write(content[:5000])  # First 5000 chars
                print(f"\nSaved first 5000 chars to {debug_file}")

    except Exception as e:
        print(f"  ERROR: {e}")

    return engine.temp_dirs[-1] if engine.temp_dirs else None


def test_wac_with_temp_files():
    """Test WAC with temp files kept."""

    print("\n" + "="*60)
    print("TESTING WAC WITH TEMP FILE RETENTION")
    print("="*60)

    # Monkey-patch DirectPhreeqcEngine to keep temp files
    original_init = DirectPhreeqcEngine.__init__

    def patched_init(self, *args, **kwargs):
        kwargs['keep_temp_files'] = True
        original_init(self, *args, **kwargs)
        print(f"[Patched] Keep temp files: {self.keep_temp_files}")

    DirectPhreeqcEngine.__init__ = patched_init

    test_input = {
        "schema_version": "1.0.0",
        "resin_type": "WAC_Na",
        "water": {
            "flow_m3h": 10,
            "temperature_c": 25,
            "ph": 4.0,  # Low pH to test protonation
            "ions_mg_l": {
                "Ca_2+": 120,
                "Mg_2+": 40,
                "Na_+": 100,
                "HCO3_-": 300,
                "Cl_-": 200
            }
        },
        "vessel": {
            "diameter_m": 1.0,
            "bed_depth_m": 1.5,
            "number_in_service": 1
        },
        "targets": {
            "hardness_mg_l_caco3": 10.0
        },
        "engine": "phreeqc"
    }

    print("\nRunning WAC simulation at pH 4.0...")
    try:
        result = simulate_ix_hybrid(test_input, write_artifacts=False)

        if result["status"] == "success":
            print(f"  Service BV: {result['performance'].get('service_bv_to_target', 0):.1f}")

            # Find temp files (they should be in a recent temp dir)
            import tempfile
            temp_base = Path(tempfile.gettempdir())
            phreeqc_dirs = sorted(temp_base.glob("phreeqc_*"), key=lambda p: p.stat().st_mtime)

            if phreeqc_dirs:
                latest_dir = phreeqc_dirs[-1]
                print(f"\nFound temp dir: {latest_dir}")

                input_file = latest_dir / "input.pqi"
                if input_file.exists():
                    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    print("\nChecking WAC PHREEQC input:")
                    import re
                    if "H+ + X- = HX" in content:
                        print("  ✓ H+ protonation reaction found")
                        match = re.search(r'H\+ \+ X- = HX.*?\n.*?log_k\s+([\d.-]+)', content, re.DOTALL)
                        if match:
                            log_k = float(match.group(1))
                            print(f"  ✓ pKa (log_k) = {log_k:.2f}")
                    else:
                        print("  ✗ H+ protonation reaction NOT found")

                    # Save for inspection
                    with open("debug_wac_input.pqi", 'w') as f:
                        f.write(content[:5000])
                    print("  Saved to debug_wac_input.pqi")

    except Exception as e:
        print(f"  ERROR: {e}")

    # Restore original
    DirectPhreeqcEngine.__init__ = original_init


def main():
    print("\n" + "#"*60)
    print("# PHREEQC TEMP FILE INSPECTION")
    print("#"*60)

    sac_temp = test_sac_with_temp_files()
    test_wac_with_temp_files()

    print("\n" + "="*60)
    print("ANALYSIS")
    print("="*60)
    print("Check the following files for full PHREEQC input:")
    print("  - debug_sac_input.pqi (SAC with DVB)")
    print("  - debug_wac_input.pqi (WAC with pH)")
    if sac_temp:
        print(f"  - {sac_temp}/ (full temp directory)")


if __name__ == "__main__":
    main()