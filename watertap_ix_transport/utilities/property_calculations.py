"""
Property calculation utilities for IX models.

This module contains common property calculation patterns to avoid code duplication.
"""

import logging
from idaes.core.util.initialization import solve_indexed_blocks
from idaes.models.properties.modular_properties.base.generic_property import (
    GenericParameterBlock
)
from pyomo.environ import value

logger = logging.getLogger(__name__)


def fix_mole_fractions(state_block, recalculate_concentrations=True):
    """
    Fix mole fractions for a state block by calculating from constraints.
    
    This utility replaces the repeated pattern of calculating molar flows
    and mole fractions that appears multiple times across the codebase.
    
    Args:
        state_block: IDAES state block with property calculations
        recalculate_concentrations: If True, also recalculate mass concentrations
        
    Returns:
        None (modifies state_block in place)
    """
    # Get property package
    if hasattr(state_block, 'params'):
        property_package = state_block.params
    elif hasattr(state_block, 'config') and hasattr(state_block.config, 'property_package'):
        property_package = state_block.config.property_package
    else:
        logger.warning("Could not determine property package for state block")
        return
    
    # Import here to avoid circular imports
    from idaes.core.util.model_statistics import large_residuals_set, degrees_of_freedom
    from pyomo.util.calc_var_value import calculate_variable_from_constraint
    from pyomo.environ import value, SolverFactory
    
    # P1: CRITICAL - Solve property block FIRST to ensure thermodynamic consistency
    # This prevents locking in default values (e.g., water mole fraction = 0.5)
    dof = degrees_of_freedom(state_block)
    if dof == 0:
        logger.info("Solving property block to ensure consistent values before mole fraction calculations...")
        solver = SolverFactory('ipopt')
        solver.options['tol'] = 1e-8
        solver.options['print_level'] = 0  # Suppress output
        
        try:
            results = solver.solve(state_block, tee=False)
            if results.solver.termination_condition.value == 'optimal':
                logger.info("Property block solved successfully")
            else:
                logger.warning(f"Property block solve terminated with: {results.solver.termination_condition}")
        except Exception as e:
            logger.warning(f"Could not solve property block: {e}")
            # Continue anyway - calculate_variable_from_constraint may still work
    elif dof > 0:
        logger.warning(f"Property block has DOF={dof} > 0, cannot solve. Proceeding with calculations anyway.")
    else:
        logger.warning(f"Property block has DOF={dof} < 0, over-specified. This may cause issues.")
    
    # Calculate molar flows from mass flows
    if hasattr(state_block, 'eq_flow_mol_phase_comp'):
        for comp in property_package.component_list:
            idx = ('Liq', comp)
            if idx in state_block.eq_flow_mol_phase_comp:
                try:
                    calculate_variable_from_constraint(
                        state_block.flow_mol_phase_comp[idx],
                        state_block.eq_flow_mol_phase_comp[idx]
                    )
                except Exception as e:
                    logger.warning(f"Could not calculate molar flow for {comp}: {e}")
    
    # P2: Calculate mole fractions - ONLY n-1 components to avoid over-constraint
    # Leave H2O free to be determined by Σx=1 constraint
    if hasattr(state_block, 'eq_mole_frac_phase_comp'):
        for comp in property_package.component_list:
            # Skip H2O - let it be determined by sum constraint
            if comp == 'H2O':
                logger.debug("Skipping H2O mole fraction calculation (n-1 rule)")
                continue
                
            idx = ('Liq', comp)
            if idx in state_block.eq_mole_frac_phase_comp:
                try:
                    calculate_variable_from_constraint(
                        state_block.mole_frac_phase_comp[idx],
                        state_block.eq_mole_frac_phase_comp[idx]
                    )
                except Exception as e:
                    logger.warning(f"Could not calculate mole fraction for {comp}: {e}")
    
    # Additional calculations that sometimes appear
    if hasattr(state_block, 'eq_total_flow_balance'):
        try:
            calculate_variable_from_constraint(
                state_block.flow_mol,
                state_block.eq_total_flow_balance
            )
        except Exception:
            pass
    
    if hasattr(state_block, 'eq_phase_flow'):
        for phase in property_package.phase_list:
            if phase in state_block.eq_phase_flow:
                try:
                    calculate_variable_from_constraint(
                        state_block.flow_mol_phase[phase],
                        state_block.eq_phase_flow[phase]
                    )
                except Exception:
                    pass
    
    # CRITICAL: Recalculate concentrations after fixing mole fractions
    # This should no longer be needed since we solved the property block first
    if recalculate_concentrations:
        # Check if concentrations need updating by looking for 10,000 mg/L values
        needs_update = False
        if hasattr(state_block, 'conc_mass_phase_comp'):
            for comp in property_package.solute_set:
                if comp != 'H2O':
                    conc_mg_L = value(state_block.conc_mass_phase_comp['Liq', comp]) * 1000
                    if abs(conc_mg_L - 10000) < 0.1:
                        needs_update = True
                        break
        
        if needs_update:
            logger.warning("Still detecting 10,000 mg/L concentrations after property solve!")
            logger.warning("This suggests the property block solve didn't update concentrations properly.")
            # Since we already solved above, this indicates a deeper issue
            # Log details for debugging
            for comp in property_package.solute_set:
                if comp != 'H2O':
                    conc_mg_L = value(state_block.conc_mass_phase_comp['Liq', comp]) * 1000
                    if abs(conc_mg_L - 10000) < 0.1:
                        logger.warning(f"  {comp}: {conc_mg_L:.1f} mg/L (still at default)")
        else:
            logger.debug("Concentrations appear correct after mole fraction calculations")


def set_feed_pH(feed_state, target_pH, flow_rate_m3_s):
    """
    Set H+ and OH- concentrations to achieve target pH in feed stream.
    
    This utility correctly sets the mass flows of H+ and OH- based on the
    target pH and flow rate, ensuring proper unit conversions from mol/L
    to kg/s for MCAS property package with MaterialFlowBasis.mass.
    
    Args:
        feed_state: IDAES state block for feed stream (e.g., m.fs.feed.properties[0])
        target_pH: Target pH value (typically 6-9)
        flow_rate_m3_s: Flow rate in m³/s (NOT L/s)
        
    Returns:
        dict: Dictionary with results including:
            - h_conc_mol_L: H+ concentration in mol/L
            - oh_conc_mol_L: OH- concentration in mol/L
            - h_mass_flow_kg_s: H+ mass flow in kg/s
            - oh_mass_flow_kg_s: OH- mass flow in kg/s
            
    Example:
        # For a 100 m³/hr flow at pH 7.5:
        flow_m3_s = 100 / 3600  # Convert to m³/s
        set_feed_pH(m.fs.feed.properties[0], 7.5, flow_m3_s)
    """
    # Calculate H+ and OH- concentrations from pH
    h_conc_mol_L = 10**(-target_pH)  # mol/L
    oh_conc_mol_L = 1e-14 / h_conc_mol_L  # mol/L from Kw = [H+][OH-]
    
    # Convert mol/L to kg/s
    # mol/L × m³/s × 1000 L/m³ × MW g/mol × 1 kg/1000 g = kg/s
    # Simplified: mol/L × m³/s × MW = kg/s
    h_mass_flow = h_conc_mol_L * flow_rate_m3_s * 1.008  # kg/s (MW of H+ = 1.008)
    oh_mass_flow = oh_conc_mol_L * flow_rate_m3_s * 17.008  # kg/s (MW of OH- = 17.008)
    
    # Fix the mass flows in the feed state
    if hasattr(feed_state, 'flow_mass_phase_comp'):
        # Fix H+ flow
        if ('Liq', 'H_+') in feed_state.flow_mass_phase_comp:
            feed_state.flow_mass_phase_comp['Liq', 'H_+'].fix(h_mass_flow)
            logger.info(f"Set H+ mass flow to {h_mass_flow:.2e} kg/s for pH {target_pH}")
        else:
            logger.warning("H_+ not found in component list")
            
        # Fix OH- flow
        if ('Liq', 'OH_-') in feed_state.flow_mass_phase_comp:
            feed_state.flow_mass_phase_comp['Liq', 'OH_-'].fix(oh_mass_flow)
            logger.info(f"Set OH- mass flow to {oh_mass_flow:.2e} kg/s for pH {target_pH}")
        else:
            logger.warning("OH_- not found in component list")
    else:
        raise AttributeError("feed_state does not have flow_mass_phase_comp attribute")
    
    # Return calculation results for verification
    return {
        'h_conc_mol_L': h_conc_mol_L,
        'oh_conc_mol_L': oh_conc_mol_L,
        'h_mass_flow_kg_s': h_mass_flow,
        'oh_mass_flow_kg_s': oh_mass_flow,
        'target_pH': target_pH,
        'flow_rate_m3_s': flow_rate_m3_s
    }