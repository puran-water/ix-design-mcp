#!/usr/bin/env python3
"""
Minimal patch to fix IonExchangeTransport0D mass transfer issue

This script contains the key fixes that need to be applied to make 
ion removal rates properly propagate to outlet concentrations.
"""

# Fix 1: Replace the constraint to use the correct control volume variable
# This replaces the eq_mass_transfer constraint around line 580-590

def create_correct_mass_transfer_constraint(self):
    """
    Create constraint that links ion_removal_rate to the correct CV variable
    """
    @self.Constraint(
        self.flowsheet().time,
        self.config.property_package.component_list,
        doc="Link ion removal to CV mass transfer"
    )
    def eq_mass_transfer(b, t, j):
        # Check if this component participates in mass transfer
        if (t, "Liq", j) not in b.control_volume.mass_transfer_phase_comp:
            # Skip if not a mass transfer component
            return Constraint.Skip
        
        # Link to the correct variable with proper sign
        # CV expects positive values for sink terms (removal from liquid)
        # ion_removal_rate is negative for removal, so negate it
        return b.control_volume.mass_transfer_phase_comp[t, "Liq", j] == -b.ion_removal_rate[t, j]


# Fix 2: Ensure outlet flow variables are unfixed before solving
# This should be added after ion_removal_rate calculations in _update_removal_rates

def unfix_outlet_flows(self):
    """
    Unfix outlet flow variables to allow solver to update them
    """
    t = self.flowsheet().time.first()
    outlet_state = self.control_volume.properties_out[t]
    
    # Unfix all component flows except H2O
    for j in self.config.property_package.component_list:
        if j != 'H2O' and hasattr(outlet_state.flow_mass_phase_comp, '__getitem__'):
            if ('Liq', j) in outlet_state.flow_mass_phase_comp:
                if outlet_state.flow_mass_phase_comp['Liq', j].fixed:
                    outlet_state.flow_mass_phase_comp['Liq', j].unfix()
                    print(f"Unfixed outlet flow for {j}")


# Fix 3: Add proper scaling factors
# This should be added to the calculate_scaling_factors method

def add_mass_transfer_scaling(self):
    """
    Add scaling factors for mass transfer variables
    """
    # Scale mass transfer terms similar to flow rates
    for (t, p, j), var in self.control_volume.mass_transfer_phase_comp.items():
        if j != 'H2O':
            # Use same scaling as component flows
            if hasattr(self, 'scaling_factor'):
                inlet_flow = value(self.control_volume.properties_in[t].flow_mass_phase_comp[p, j])
                if inlet_flow > 0:
                    self.scaling_factor[var] = 1.0 / inlet_flow


# Complete fix implementation in _update_removal_rates
def fixed_update_removal_rates(self):
    """
    Updated version of _update_removal_rates with all fixes applied
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Starting fixed _update_removal_rates...")
    
    t = self.flowsheet().time.first()
    
    # Initialize all rates to zero
    for j in self.config.property_package.component_list:
        self.ion_removal_rate[t, j].set_value(0)
    
    # Calculate removal for target ions
    inlet_state = self.control_volume.properties_in[t]
    
    for ion in self.target_ion_set:
        if hasattr(inlet_state, 'flow_mass_phase_comp') and ('Liq', ion) in inlet_state.flow_mass_phase_comp:
            inlet_flow = value(inlet_state.flow_mass_phase_comp['Liq', ion])  # kg/s
            
            # Remove based on operating capacity
            removal_fraction = value(self.operating_capacity)
            removal_rate = -inlet_flow * removal_fraction  # Negative for removal
            
            logger.info(f"Ion {ion}: inlet_flow={inlet_flow:.6e} kg/s, removal_fraction={removal_fraction}, removal_rate={removal_rate:.6e} kg/s")
            self.ion_removal_rate[t, ion].set_value(removal_rate)
            
            # Handle counter-ion release for SAC resin
            if self.config.resin_type == ResinType.SAC and self.config.regenerant == RegenerantChem.NaCl:
                # Calculate Na+ release based on charge balance
                # ... existing Na release logic ...
                pass
    
    # FIX: Unfix outlet flows before solving
    logger.info("Unfixing outlet flows...")
    outlet_state = self.control_volume.properties_out[t]
    for j in self.config.property_package.component_list:
        if j != 'H2O' and hasattr(outlet_state.flow_mass_phase_comp, '__getitem__'):
            if ('Liq', j) in outlet_state.flow_mass_phase_comp:
                if outlet_state.flow_mass_phase_comp['Liq', j].fixed:
                    outlet_state.flow_mass_phase_comp['Liq', j].unfix()
                    logger.info(f"Unfixed outlet flow for {j}")
    
    # FIX: Force a solve to propagate mass transfer
    logger.info("Solving to enforce mass balance with removal rates...")
    from pyomo.environ import SolverFactory
    solver = SolverFactory('ipopt')
    solver.options['tol'] = 1e-8
    solver.options['max_iter'] = 100
    
    results = solver.solve(self, tee=False)
    if results.solver.termination_condition == 'optimal':
        logger.info("Successfully enforced mass balance with removal rates")
    else:
        logger.warning(f"Failed to converge after setting removal rates: {results.solver.termination_condition}")


# Summary of changes needed:
print("""
MINIMAL PATCH IMPLEMENTATION GUIDE
==================================

1. In the constraint definition (around line 580-590), replace:
   
   OLD:
   return b.control_volume.mass_transfer_term[t, "Liq", j] == b.ion_removal_rate[t, j]
   
   NEW:
   return b.control_volume.mass_transfer_phase_comp[t, "Liq", j] == -b.ion_removal_rate[t, j]

2. In _update_removal_rates (after removal calculations), add:
   
   # Unfix outlet flows
   outlet_state = self.control_volume.properties_out[t]
   for j in self.config.property_package.component_list:
       if j != 'H2O' and ('Liq', j) in outlet_state.flow_mass_phase_comp:
           if outlet_state.flow_mass_phase_comp['Liq', j].fixed:
               outlet_state.flow_mass_phase_comp['Liq', j].unfix()

3. Add a solve step at the end of _update_removal_rates:
   
   solver = SolverFactory('ipopt')
   solver.options['tol'] = 1e-8
   results = solver.solve(self, tee=False)

4. In calculate_scaling_factors, add scaling for mass_transfer_phase_comp:
   
   for (t, p, j), var in self.control_volume.mass_transfer_phase_comp.items():
       if j != 'H2O' and inlet_flow > 0:
           self.scaling_factor[var] = 1.0 / inlet_flow

These minimal changes will make the outlet concentrations reflect the removal rates.
""")