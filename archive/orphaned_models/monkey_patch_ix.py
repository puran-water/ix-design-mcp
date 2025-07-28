"""
Monkey patch for IonExchangeTransport0D to fix the mole fraction issue.
This ensures mole fractions are calculated before PHREEQC calculations.
"""

import logging
from pyomo.environ import value
from pyomo.util.calc_var_value import calculate_variable_from_constraint
from idaes.core.util.model_statistics import degrees_of_freedom
from pyomo.environ import SolverFactory
import idaes.logger as idaeslog

logger = logging.getLogger(__name__)

def patched_initialize_build(self, state_args=None, outlvl=idaeslog.NOTSET, solver=None, optarg=None):
    """
    Patched version of initialize_build that fixes mole fractions before calculate_performance.
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
    inlet_state = self.control_volume.properties_in[0]
    
    # Import fix_mole_fractions utility
    try:
        from watertap_ix_transport.utilities.property_calculations import fix_mole_fractions
        fix_mole_fractions(inlet_state)
        init_log.info("Fixed inlet mole fractions before IX calculations")
    except ImportError:
        init_log.warning("Could not import fix_mole_fractions utility, doing it manually")
        
        # Fallback: manually calculate mole fractions
        # Calculate molar flows from mass flows
        if hasattr(inlet_state, 'eq_flow_mol_phase_comp'):
            for comp in self.config.property_package.component_list:
                idx = ('Liq', comp)
                if idx in inlet_state.eq_flow_mol_phase_comp:
                    try:
                        calculate_variable_from_constraint(
                            inlet_state.flow_mol_phase_comp[idx],
                            inlet_state.eq_flow_mol_phase_comp[idx]
                        )
                    except:
                        pass
        
        # Calculate mole fractions
        if hasattr(inlet_state, 'eq_mole_frac_phase_comp'):
            for comp in self.config.property_package.component_list:
                idx = ('Liq', comp)
                if idx in inlet_state.eq_mole_frac_phase_comp:
                    try:
                        calculate_variable_from_constraint(
                            inlet_state.mole_frac_phase_comp[idx],
                            inlet_state.eq_mole_frac_phase_comp[idx]
                        )
                    except:
                        pass
    
    # Validate water mole fraction
    water_mol_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
    init_log.info(f"Water mole fraction before IX calculations: {water_mol_frac:.6f}")
    
    if water_mol_frac < 0.95:
        init_log.warning(f"Low water mole fraction ({water_mol_frac:.6f}) detected")
        init_log.warning("Attempting to fix by solving property block...")
        
        # Try to solve the property block to get correct values
        inlet_dof = degrees_of_freedom(inlet_state)
        if inlet_dof > 0:
            if solver is None:
                solver = SolverFactory('ipopt')
                solver.options['tol'] = 1e-8
            results = solver.solve(inlet_state, tee=False)
            
            if results.solver.termination_condition == 'optimal':
                # Recalculate mole fractions after solve
                fix_mole_fractions(inlet_state)
                water_mol_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
                init_log.info(f"Water mole fraction after property solve: {water_mol_frac:.6f}")
        
        # If still bad, try recalculating everything
        if water_mol_frac < 0.95:
            # Force recalculation of all derived properties
            if hasattr(inlet_state, 'eq_total_flow_balance'):
                try:
                    calculate_variable_from_constraint(
                        inlet_state.flow_mol,
                        inlet_state.eq_total_flow_balance
                    )
                except:
                    pass
            
            if hasattr(inlet_state, 'eq_phase_flow'):
                try:
                    calculate_variable_from_constraint(
                        inlet_state.flow_mol_phase['Liq'],
                        inlet_state.eq_phase_flow['Liq']
                    )
                except:
                    pass
            
            # One more attempt
            fix_mole_fractions(inlet_state)
            water_mol_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
            init_log.info(f"Water mole fraction after full recalculation: {water_mol_frac:.6f}")
    
    # Continue with the original method but skip the duplicate operations we just did
    # Store the original method to call the rest of it
    original_method = type(self)._original_initialize_build
    
    # Temporarily replace calculate_performance to capture if it's being called too early
    original_calculate_performance = self.calculate_performance
    performance_called = [False]
    
    def wrapped_calculate_performance():
        water_mol_frac = value(self.control_volume.properties_in[0].mole_frac_phase_comp['Liq', 'H2O'])
        init_log.info(f"calculate_performance called with water mole fraction: {water_mol_frac:.6f}")
        performance_called[0] = True
        return original_calculate_performance()
    
    self.calculate_performance = wrapped_calculate_performance
    
    # Continue with the rest of initialization, but start from after the inlet initialization
    # We need to manually do the rest since we can't easily skip the beginning
    
    # Create state args for outlet
    if state_args is None:
        t = self.flowsheet().time.first()
        inlet_state = self.control_volume.properties_in[0]
        state_args_out = {}
        
        state_args_out['temperature'] = value(inlet_state.temperature)
        state_args_out['pressure'] = value(inlet_state.pressure)
        
        # Initialize flow rates based on ion exchange
        state_args_out['flow_mol_phase_comp'] = {}
        
        for (ph, comp) in inlet_state.flow_mol_phase_comp:
            inlet_flow = value(inlet_state.flow_mol_phase_comp[ph, comp])
            outlet_flow = inlet_flow + value(self.ion_removal_rate[t, comp])
            state_args_out['flow_mol_phase_comp'][ph, comp] = outlet_flow
    else:
        state_args_out = state_args
    
    self.control_volume.properties_out.initialize(
        outlvl=outlvl,
        optarg=optarg,
        solver=solver,
        state_args=state_args_out,
    )
    
    # Solve property blocks as in original
    if solver is None:
        solver = SolverFactory('ipopt')
        solver.options['tol'] = 1e-8
    
    # Calculate constraint-defined variables
    calculate_variable_from_constraint(self.bed_volume, self.eq_bed_volume)
    init_log.info(f"Calculated bed volume: {value(self.bed_volume):.2f} m³")
    
    calculate_variable_from_constraint(self.pressure_drop, self.eq_pressure_drop)
    
    # Now call calculate_performance with correct mole fractions
    init_log.info("Calculating ion exchange performance with PHREEQC...")
    self.calculate_performance = original_calculate_performance
    self.calculate_performance()
    
    # Calculate service time
    calculate_variable_from_constraint(self.service_time, self.eq_service_time)
    init_log.info(f"Calculated service time: {value(self.service_time):.1f} hours")
    
    # Initialize regeneration stream if present
    if hasattr(self, "regeneration_stream"):
        solver_name = solver if isinstance(solver, str) else "ipopt"
        self.regeneration_stream.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver_name,
            state_args=state_args,
        )
    
    # Release inlet state
    self.control_volume.properties_in.release_state(flags, outlvl=outlvl)
    
    init_log.info("Initialization Complete")


def apply_patch():
    """Apply the monkey patch to IonExchangeTransport0D"""
    from watertap_ix_transport import IonExchangeTransport0D
    
    # Store the original method
    IonExchangeTransport0D._original_initialize_build = IonExchangeTransport0D.initialize_build
    
    # Replace with patched version
    IonExchangeTransport0D.initialize_build = patched_initialize_build
    
    logger.info("Applied monkey patch to IonExchangeTransport0D.initialize_build")
    return True