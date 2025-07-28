"""
Patch for ion_exchange_transport_0D.py to fix the mole fraction issue.
This shows the fix that needs to be applied to the initialize_build method.
"""

# The issue is in the initialize_build method around line 740-793
# The fix is to ensure mole fractions are calculated BEFORE calling calculate_performance

def initialize_build_fixed(self, state_args=None, outlvl=idaeslog.NOTSET, solver=None, optarg=None):
    """
    Fixed version of initialize_build that ensures mole fractions are correct
    before calling calculate_performance.
    """
    init_log = idaeslog.getInitLogger(self.name, outlvl, tag="unit")
    solve_log = idaeslog.getSolveLogger(self.name, outlvl, tag="unit")
    
    # Initialize control volume
    flags = self.control_volume.properties_in.initialize(
        outlvl=outlvl,
        optarg=optarg,
        solver=solver,
        state_args=state_args,
        hold_state=True,
    )
    
    # === CRITICAL FIX: Ensure inlet mole fractions are correct ===
    # This must happen BEFORE calculate_performance
    inlet_state = self.control_volume.properties_in[0]
    
    # Import fix_mole_fractions utility
    try:
        from watertap_ix_transport.utilities.property_calculations import fix_mole_fractions
        fix_mole_fractions(inlet_state)
        init_log.info("Fixed inlet mole fractions before IX calculations")
    except ImportError:
        init_log.warning("Could not import fix_mole_fractions utility")
        
        # Fallback: manually calculate mole fractions
        from pyomo.util.calc_var_value import calculate_variable_from_constraint
        
        # Calculate molar flows from mass flows
        if hasattr(inlet_state, 'eq_flow_mol_phase_comp'):
            for comp in self.config.property_package.component_list:
                idx = ('Liq', comp)
                if idx in inlet_state.eq_flow_mol_phase_comp:
                    calculate_variable_from_constraint(
                        inlet_state.flow_mol_phase_comp[idx],
                        inlet_state.eq_flow_mol_phase_comp[idx]
                    )
        
        # Calculate mole fractions
        if hasattr(inlet_state, 'eq_mole_frac_phase_comp'):
            for comp in self.config.property_package.component_list:
                idx = ('Liq', comp)
                if idx in inlet_state.eq_mole_frac_phase_comp:
                    calculate_variable_from_constraint(
                        inlet_state.mole_frac_phase_comp[idx],
                        inlet_state.eq_mole_frac_phase_comp[idx]
                    )
    
    # Validate water mole fraction
    water_mol_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
    init_log.info(f"Water mole fraction before IX calculations: {water_mol_frac:.6f}")
    
    if water_mol_frac < 0.95:
        init_log.warning(f"Low water mole fraction ({water_mol_frac:.6f}) detected")
        init_log.warning("This will cause incorrect IX performance calculations")
        
        # Try to solve the property block to get correct values
        from pyomo.environ import SolverFactory
        from idaes.core.util.model_statistics import degrees_of_freedom
        
        inlet_dof = degrees_of_freedom(inlet_state)
        if inlet_dof > 0:
            solver = SolverFactory('ipopt')
            solver.options['tol'] = 1e-8
            results = solver.solve(inlet_state, tee=False)
            
            if results.solver.termination_condition == 'optimal':
                # Recalculate mole fractions after solve
                fix_mole_fractions(inlet_state)
                water_mol_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
                init_log.info(f"Water mole fraction after property solve: {water_mol_frac:.6f}")
    
    # === Continue with rest of initialization ===
    
    # Create state args for outlet based on inlet and expected changes
    if state_args is None:
        # ... rest of the initialization code ...
        pass
    
    # ... rest of the method ...
    
    # NOW we can safely call calculate_performance with correct inlet composition
    init_log.info("Calculating ion exchange performance with PHREEQC...")
    self.calculate_performance()
    
    # ... rest of the method ...