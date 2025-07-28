"""
Ion Exchange Transport 0D Model - FIXED VERSION

This file contains the fix for the mass balance issue where removal rates
are calculated but not applied to the outlet concentrations.
"""

# Key changes to fix the issue:
# 1. Initialize outlet state properly BEFORE PHREEQC calculations
# 2. Ensure mass_transfer_terms are unfixed
# 3. Fix outlet mole fractions early in the process

# The main fix is in the initialize_build method around line 700-750
# Look for the comment "FIX: Initialize outlet state properly"

# Additional fix in _update_removal_rates around line 1050
# Look for "FIX: Ensure mass_transfer_terms are not fixed"

"""
IMPLEMENTATION NOTE:

The fix involves modifying the initialize_build method to:

1. After control volume initialization, immediately set outlet flows:
   ```python
   # FIX: Initialize outlet state properly
   outlet_state = self.control_volume.properties_out[0]
   inlet_state = self.control_volume.properties_in[0]
   
   # Set outlet flows based on inlet (before IX calculations)
   for comp in self.config.property_package.component_list:
       outlet_state.flow_mass_phase_comp['Liq', comp].set_value(
           value(inlet_state.flow_mass_phase_comp['Liq', comp])
       )
   
   # Fix outlet mole fractions NOW, not later
   fix_mole_fractions(outlet_state, recalculate_concentrations=True)
   ```

2. In _update_removal_rates, ensure mass_transfer_terms are unfixed:
   ```python
   # FIX: Ensure mass_transfer_terms are not fixed (except H2O)
   for j in self.config.property_package.component_list:
       if j != 'H2O' and (t, 'Liq', j) in self.control_volume.mass_transfer_term:
           self.control_volume.mass_transfer_term[t, 'Liq', j].unfix()
   ```

3. After calculating removal rates, solve the model to enforce constraints:
   ```python
   # FIX: Solve to enforce mass balance constraints
   solver = SolverFactory('ipopt')
   solver.options['tol'] = 1e-8
   results = solver.solve(self, tee=False)
   
   if results.solver.termination_condition != 'optimal':
       logger.warning(f"Failed to converge mass balance: {results.solver.termination_condition}")
   ```

This ensures that:
- Outlet state starts with reasonable values (not 10,000 mg/L)
- Mass transfer terms can be adjusted by constraints
- Material balance is enforced: outlet = inlet + mass_transfer
"""