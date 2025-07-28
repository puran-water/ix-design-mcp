#!/usr/bin/env python3
"""Add pressure constraint deactivation to unified template notebook."""

import json
import sys

def add_pressure_fix_to_notebook():
    """Add pressure constraint deactivation after expand_arcs."""
    
    # Read the notebook
    with open('notebooks/ix_simulation_unified_template.ipynb', 'r') as f:
        notebook = json.load(f)
    
    # Find the cell with expand_arcs
    expand_arcs_idx = None
    for i, cell in enumerate(notebook['cells']):
        if cell['cell_type'] == 'code' and 'expand_arcs' in ''.join(cell['source']):
            expand_arcs_idx = i
            break
    
    if expand_arcs_idx is None:
        print("ERROR: Could not find expand_arcs cell")
        return False
    
    # Create new cell with pressure constraint fixes
    pressure_fix_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# FIX: Deactivate pressure-related constraints to avoid infeasibility\n",
            "# This fix is based on DeepWiki insights about IDAES control volume pressure balance conflicts\n",
            "logger.info(\"Deactivating pressure constraints to avoid infeasibility...\")\n",
            "\n",
            "for unit_name, ix_unit in ix_units.items():\n",
            "    # Deactivate pressure drop constraints\n",
            "    if hasattr(ix_unit, 'eq_pressure_drop'):\n",
            "        ix_unit.eq_pressure_drop.deactivate()\n",
            "        logger.info(f\"  Deactivated {unit_name}.eq_pressure_drop\")\n",
            "    \n",
            "    if hasattr(ix_unit, 'eq_deltaP'):\n",
            "        ix_unit.eq_deltaP.deactivate()\n",
            "        logger.info(f\"  Deactivated {unit_name}.eq_deltaP\")\n",
            "    \n",
            "    # Deactivate control volume pressure balance\n",
            "    if hasattr(ix_unit.control_volume, 'pressure_balance'):\n",
            "        ix_unit.control_volume.pressure_balance.deactivate()\n",
            "        logger.info(f\"  Deactivated {unit_name}.control_volume.pressure_balance\")\n",
            "    \n",
            "    # Fix pressure_drop to 0\n",
            "    if hasattr(ix_unit, 'pressure_drop'):\n",
            "        ix_unit.pressure_drop.fix(0)\n",
            "        logger.info(f\"  Fixed {unit_name}.pressure_drop to 0\")\n",
            "\n",
            "# Set all pressures to consistent value (100 kPa)\n",
            "pressure_value = 100000  # Pa\n",
            "logger.info(f\"Setting all pressures to {pressure_value} Pa...\")\n",
            "\n",
            "# Fix feed pressure\n",
            "m.fs.feed.outlet.pressure[0].fix(pressure_value)\n",
            "\n",
            "# Fix all IX unit pressures\n",
            "for unit_name, ix_unit in ix_units.items():\n",
            "    if hasattr(ix_unit.inlet, 'pressure'):\n",
            "        ix_unit.inlet.pressure[0].fix(pressure_value)\n",
            "    if hasattr(ix_unit.outlet, 'pressure'):\n",
            "        ix_unit.outlet.pressure[0].fix(pressure_value)\n",
            "\n",
            "# Fix degasser pressures if present\n",
            "if degasser_unit:\n",
            "    if hasattr(degasser_unit.inlet, 'pressure'):\n",
            "        degasser_unit.inlet.pressure[0].fix(pressure_value)\n",
            "    if hasattr(degasser_unit.outlet, 'pressure'):\n",
            "        degasser_unit.outlet.pressure[0].fix(pressure_value)\n",
            "\n",
            "# Fix product pressure\n",
            "m.fs.product.inlet.pressure[0].fix(pressure_value)\n",
            "\n",
            "logger.info(\"Pressure constraints deactivated and pressures fixed consistently\")"
        ]
    }
    
    # Insert the new cell after expand_arcs
    notebook['cells'].insert(expand_arcs_idx + 1, pressure_fix_cell)
    
    # Write the updated notebook
    with open('notebooks/ix_simulation_unified_template.ipynb', 'w') as f:
        json.dump(notebook, f, indent=1)
    
    print(f"Successfully added pressure constraint fix after cell {expand_arcs_idx}")
    return True

if __name__ == "__main__":
    success = add_pressure_fix_to_notebook()
    sys.exit(0 if success else 1)