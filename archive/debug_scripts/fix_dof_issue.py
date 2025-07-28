#!/usr/bin/env python3
"""Fix DOF issue by deactivating redundant mole fraction constraints"""

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

def main():
    from ix_cli import parse_config, build_model, initialize_model
    from pyomo.environ import value, Constraint
    from idaes.core.util.model_statistics import degrees_of_freedom
    
    print("Testing DOF fix...")
    config = parse_config("test_config.json")
    
    print("\nBuilding model...")
    model, metadata = build_model(config)
    
    print(f"DOF after build: {degrees_of_freedom(model)}")
    
    # The issue: When we have arcs connecting property blocks, and each block
    # has eq_mole_frac_phase_comp constraints, we get over-constrained.
    # Solution: Deactivate mole fraction constraints in downstream blocks
    # (they'll be determined by mass flows from upstream)
    
    print("\nDeactivating redundant mole fraction constraints...")
    
    # Keep feed block constraints active (it's the source)
    # Deactivate constraints in IX inlet (connected by arc to feed)
    if hasattr(model.fs.ix_sac.control_volume.properties_in[0], 'eq_mole_frac_phase_comp'):
        for idx in model.fs.ix_sac.control_volume.properties_in[0].eq_mole_frac_phase_comp:
            model.fs.ix_sac.control_volume.properties_in[0].eq_mole_frac_phase_comp[idx].deactivate()
        print("  Deactivated IX inlet mole fraction constraints")
    
    # Deactivate constraints in IX outlet (determined by mass transfer)
    if hasattr(model.fs.ix_sac.control_volume.properties_out[0], 'eq_mole_frac_phase_comp'):
        for idx in model.fs.ix_sac.control_volume.properties_out[0].eq_mole_frac_phase_comp:
            model.fs.ix_sac.control_volume.properties_out[0].eq_mole_frac_phase_comp[idx].deactivate()
        print("  Deactivated IX outlet mole fraction constraints")
    
    # Deactivate constraints in product (connected by arc to IX outlet)
    if hasattr(model.fs.product.properties[0], 'eq_mole_frac_phase_comp'):
        for idx in model.fs.product.properties[0].eq_mole_frac_phase_comp:
            model.fs.product.properties[0].eq_mole_frac_phase_comp[idx].deactivate()
        print("  Deactivated product mole fraction constraints")
    
    print(f"\nDOF after deactivation: {degrees_of_freedom(model)}")
    
    print("\nInitializing model...")
    init_results = initialize_model(model, config)
    
    print(f"\nFinal DOF: {init_results['dof']}")
    
    if init_results['dof'] == 0:
        print("\n✓ DOF issue resolved!")
        
        # Try to solve
        from pyomo.environ import SolverFactory
        solver = SolverFactory('ipopt')
        solver.options['tol'] = 1e-6
        
        print("\nSolving model...")
        results = solver.solve(model, tee=True)
        
        if results.solver.termination_condition == 'optimal':
            print("\n✓ Model solved successfully!")
            
            # Show results
            ca_removal = -value(model.fs.ix_sac.ion_removal_rate[0, 'Ca_2+']) / 0.005 * 100
            mg_removal = -value(model.fs.ix_sac.ion_removal_rate[0, 'Mg_2+']) / 0.002222 * 100
            
            print(f"\nResults:")
            print(f"  Ca removal: {ca_removal:.1f}%")
            print(f"  Mg removal: {mg_removal:.1f}%")
        else:
            print(f"\n✗ Solve failed: {results.solver.termination_condition}")
    else:
        print(f"\n✗ Still have DOF issue: {init_results['dof']}")


if __name__ == "__main__":
    main()