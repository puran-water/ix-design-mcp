#!/usr/bin/env python
"""
Fix selectivity database to use correct values converted from Li+ to Na+ reference.

Literature values (Helfferich, Table 5-12) are given with Li+ as reference.
We need to convert them to Na+ reference for PHREEQC.

Conversion: K_ion/Na = K_ion/Li / K_Na/Li

Where K_ion/Li are the literature values and K_Na/Li is the Na selectivity relative to Li.
"""

import json
import math
from pathlib import Path

# Literature values from Helfferich (Li+ = 1.00 reference)
HELFFERICH_DATA = {
    '4% DVB': {
        'Li': 1.00,
        'Na': 1.58,
        'K': 2.27,
        'Rb': 2.46,
        'Cs': 2.67,
        'NH4': 1.90,
        'Ca': 4.15,
        'Mg': 2.95,
        'Sr': 4.70,
        'Ba': 7.47,
        'Zn': 3.13,
        'Cu': 3.29,
        'Cd': 3.37,
        'Ni': 3.45,
        'Co': 3.23,
        'Pb': 6.56
    },
    '8% DVB': {
        'Li': 1.00,
        'H': 1.27,  # From Myers & Boyd
        'Na': 1.98,
        'K': 2.90,
        'Rb': 3.16,
        'Cs': 3.25,
        'NH4': 2.55,
        'Ca': 5.16,
        'Mg': 3.29,
        'Sr': 6.51,
        'Ba': 11.5,
        'Zn': 3.47,
        'Cu': 3.85,
        'Cd': 3.88,
        'Ni': 3.93,
        'Co': 3.74,
        'Pb': 9.91,
        'Ag': 8.51
    },
    '16% DVB': {
        'Li': 1.00,
        'H': 1.47,
        'Na': 2.37,
        'K': 4.50,
        'Rb': 4.62,
        'Cs': 4.66,
        'NH4': 3.34,
        'Ca': 7.27,
        'Mg': 3.51,
        'Sr': 10.1,
        'Ba': 20.8,
        'Zn': 3.78,
        'Cu': 4.46,
        'Cd': 4.95,
        'Ni': 4.06,
        'Co': 3.81,
        'Pb': 18.0,
        'Ag': 22.9
    }
}

def convert_to_na_reference(dvb_percent, ion, k_ion_li):
    """Convert selectivity from Li+ reference to Na+ reference."""
    # Get Na selectivity relative to Li
    k_na_li = HELFFERICH_DATA[f'{dvb_percent}% DVB']['Na']

    # Convert: K_ion/Na = K_ion/Li / K_Na/Li
    k_ion_na = k_ion_li / k_na_li

    # Convert to log_k for PHREEQC
    log_k = math.log10(k_ion_na)

    return log_k


def fix_database():
    """Fix the selectivity database with correct values."""
    db_path = Path(__file__).parent.parent / "databases" / "resin_selectivity.json"

    # Load existing database
    with open(db_path, 'r') as f:
        db = json.load(f)

    print("Fixing selectivity database...")
    print("Converting from Li+ reference to Na+ reference")
    print("="*60)

    # Update 4% DVB
    if 'SAC_4DVB' in db['resin_types']:
        print("\n4% DVB corrections:")
        data_4 = HELFFERICH_DATA['4% DVB']
        for ion, k_li in data_4.items():
            if ion in ['Li', 'Na']:
                continue
            log_k = convert_to_na_reference(4, ion, k_li)

            # Map ion names to database keys
            if ion in ['Ca', 'Mg', 'Sr', 'Ba', 'Zn', 'Cu', 'Cd', 'Ni', 'Co', 'Pb']:
                key = f"{ion}_X2"
            else:
                key = f"{ion}_X"

            if key in db['resin_types']['SAC_4DVB']['exchange_species']:
                old_val = db['resin_types']['SAC_4DVB']['exchange_species'][key]['log_k']
                db['resin_types']['SAC_4DVB']['exchange_species'][key]['log_k'] = round(log_k, 3)
                print(f"  {ion}: {old_val:.3f} -> {log_k:.3f}")

    # Update 8% DVB
    if 'SAC_8DVB' in db['resin_types']:
        print("\n8% DVB corrections:")
        data_8 = HELFFERICH_DATA['8% DVB']
        for ion, k_li in data_8.items():
            if ion in ['Li', 'Na']:
                continue
            log_k = convert_to_na_reference(8, ion, k_li)

            # Map ion names
            if ion in ['Ca', 'Mg', 'Sr', 'Ba', 'Zn', 'Cu', 'Cd', 'Ni', 'Co', 'Pb']:
                key = f"{ion}_X2"
            elif ion == 'NH4':
                key = "NH4_X"
            elif ion == 'H':
                key = "H_X"
            elif ion == 'Ag':
                key = "Ag_X"
            else:
                key = f"{ion}_X"

            if key in db['resin_types']['SAC_8DVB']['exchange_species']:
                old_val = db['resin_types']['SAC_8DVB']['exchange_species'][key]['log_k']
                db['resin_types']['SAC_8DVB']['exchange_species'][key]['log_k'] = round(log_k, 3)
                print(f"  {ion}: {old_val:.3f} -> {log_k:.3f}")

    # Update 16% DVB
    if 'SAC_16DVB' in db['resin_types']:
        print("\n16% DVB corrections:")
        data_16 = HELFFERICH_DATA['16% DVB']
        for ion, k_li in data_16.items():
            if ion in ['Li', 'Na']:
                continue
            log_k = convert_to_na_reference(16, ion, k_li)

            # Map ion names
            if ion in ['Ca', 'Mg', 'Sr', 'Ba']:
                key = f"{ion}_X2"
            elif ion == 'Ag':
                key = "Ag_X"
            else:
                key = f"{ion}_X"

            if key in db['resin_types']['SAC_16DVB']['exchange_species']:
                old_val = db['resin_types']['SAC_16DVB']['exchange_species'][key]['log_k']
                db['resin_types']['SAC_16DVB']['exchange_species'][key]['log_k'] = round(log_k, 3)
                print(f"  {ion}: {old_val:.3f} -> {log_k:.3f}")

    # Add Li+ values
    for dvb in [4, 8, 16]:
        key = f'SAC_{dvb}DVB'
        if key in db['resin_types']:
            # Li selectivity relative to Na
            k_li_na = 1.0 / HELFFERICH_DATA[f'{dvb}% DVB']['Na']
            log_k_li = math.log10(k_li_na)

            if 'Li_X' not in db['resin_types'][key]['exchange_species']:
                db['resin_types'][key]['exchange_species']['Li_X'] = {
                    'log_k': round(log_k_li, 3),
                    'gamma': [6.0, 0.0]
                }
            else:
                db['resin_types'][key]['exchange_species']['Li_X']['log_k'] = round(log_k_li, 3)

    # Update reference note
    db['reference_conditions'] = "25°C, Na+ as reference (log_k = 0), converted from Li+ reference (Helfferich)"

    # Save corrected database
    with open(db_path, 'w') as f:
        json.dump(db, f, indent=2)

    print("\n" + "="*60)
    print("Database fixed and saved!")
    print(f"Location: {db_path}")

    # Show key comparisons
    print("\nKey selectivity ratios (Ca/Na):")
    for dvb in [4, 8, 16]:
        ca_li = HELFFERICH_DATA[f'{dvb}% DVB']['Ca']
        na_li = HELFFERICH_DATA[f'{dvb}% DVB']['Na']
        ca_na = ca_li / na_li
        log_k = math.log10(ca_na)
        print(f"  {dvb:2d}% DVB: Ca/Na = {ca_na:.2f}, log_k = {log_k:.3f}")

    print("\nExpected breakthrough increase:")
    ca_na_8 = HELFFERICH_DATA['8% DVB']['Ca'] / HELFFERICH_DATA['8% DVB']['Na']
    ca_na_16 = HELFFERICH_DATA['16% DVB']['Ca'] / HELFFERICH_DATA['16% DVB']['Na']
    increase = (ca_na_16 / ca_na_8 - 1) * 100
    print(f"  8% to 16% DVB: {increase:.1f}% increase in Ca selectivity")


if __name__ == "__main__":
    fix_database()