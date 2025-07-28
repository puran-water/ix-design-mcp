#!/usr/bin/env python3
"""Proper fix for DOF issue by managing mole fraction constraints"""

import sys
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def deactivate_redundant_mole_frac_constraints(model):
    """
    Deactivate redundant mole fraction constraints in property blocks
    connected by arcs. Keep only the upstream constraints active.
    """
    # The issue: When property blocks are connected by arcs, both blocks
    # have eq_mole_frac_phase_comp constraints that calculate mole fractions
    # from flow rates. This creates redundancy.
    
    # Solution: Keep constraints in feed block (the source), deactivate
    # constraints in downstream blocks that are determined by arcs
    
    count = 0
    
    # IX inlet is connected to feed by arc - deactivate its constraints
    if hasattr(model.fs.ix_sac.control_volume.properties_in[0], 'eq_mole_frac_phase_comp'):
        for idx in model.fs.ix_sac.control_volume.properties_in[0].eq_mole_frac_phase_comp:
            if model.fs.ix_sac.control_volume.properties_in[0].eq_mole_frac_phase_comp[idx].active:
                model.fs.ix_sac.control_volume.properties_in[0].eq_mole_frac_phase_comp[idx].deactivate()
                count += 1
    
    # IX outlet constraints should remain active (determined by mass transfer)
    # But let's check if they exist
    
    # Product is connected to IX outlet by arc - deactivate its constraints
    if hasattr(model.fs.product.properties[0], 'eq_mole_frac_phase_comp'):
        for idx in model.fs.product.properties[0].eq_mole_frac_phase_comp:
            if model.fs.product.properties[0].eq_mole_frac_phase_comp[idx].active:
                model.fs.product.properties[0].eq_mole_frac_phase_comp[idx].deactivate()
                count += 1
    
    return count


def main():
    from ix_cli import parse_config, build_model
    from pyomo.environ import value, Constraint, TransformationFactory
    from pyomo.network import Arc
    from idaes.core.util.model_statistics import degrees_of_freedom
    import logging
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    print("Testing proper DOF fix...")
    config = parse_config("test_config.json")
    
    print("\nBuilding model...")
    # Need to build the model manually to intercept before initialization
    
    from ix_cli import (
        ConcreteModel, FlowsheetBlock, Separator, MCAS_StateBlock,
        TransformationFactory, build_ix_unit, calculate_feed_mass_flows
    )
    
    # Build base model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Property package
    m.fs.properties = m.fs.config.property_package
    
    # Feed unit
    m.fs.feed = Separator(
        property_package=m.fs.properties,
        outlet_list=["outlet"]
    )
    
    # Product unit
    m.fs.product = MCAS_StateBlock(
        property_package=m.fs.properties
    )
    
    # Calculate and fix feed flows
    water_analysis = config['water_analysis']
    flow_mass_comp = calculate_feed_mass_flows(water_analysis)
    
    # Fix feed mass flows
    for comp, flow_value in flow_mass_comp.items():
        m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', comp].fix(flow_value)
    
    # Touch properties to construct them
    feed_prop = m.fs.feed.properties[0]
    _ = feed_prop.mole_frac_phase_comp  # This creates eq_mole_frac_phase_comp
    _ = feed_prop.conc_mass_phase_comp
    _ = feed_prop.flow_mol_phase_comp
    
    # Build IX unit
    ix_config = list(config['configuration']['ix_vessels'].values())[0]
    ix_unit = build_ix_unit(m, "ix_sac", ix_config, m.fs.properties)
    
    # Create arcs
    m.fs.s01 = Arc(source=m.fs.feed.outlet, destination=ix_unit.inlet)
    m.fs.s02 = Arc(source=ix_unit.outlet, destination=m.fs.product.inlet)
    
    # Expand arcs
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    print(f"\nDOF before fixing redundant constraints: {degrees_of_freedom(m)}")
    
    # Now deactivate redundant constraints AFTER arcs are expanded
    count = deactivate_redundant_mole_frac_constraints(m)
    print(f"Deactivated {count} redundant mole fraction constraints")
    
    print(f"DOF after fixing redundant constraints: {degrees_of_freedom(m)}")
    
    # Now we can initialize
    from ix_cli import initialize_model
    init_results = initialize_model(m, config)
    
    print(f"\nFinal DOF: {init_results['dof']}")
    
    if init_results['dof'] == 0:
        print("\n✓ DOF issue resolved!")
    else:
        print(f"\n✗ Still have DOF issue: {init_results['dof']}")


if __name__ == "__main__":
    main()