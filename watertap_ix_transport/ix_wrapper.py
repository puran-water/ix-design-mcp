"""
Wrapper for IonExchangeTransport0D that fixes the mole fraction initialization issue.
"""

import logging
from pyomo.environ import value
from watertap_ix_transport import IonExchangeTransport0D as OriginalIX
from watertap_ix_transport.utilities.property_calculations import fix_mole_fractions
import idaes.logger as idaeslog

logger = logging.getLogger(__name__)


class FixedIonExchangeTransport0D(OriginalIX):
    """
    Fixed version of IonExchangeTransport0D that ensures proper mole fraction calculation
    before PHREEQC calculations.
    """
    
    def calculate_performance(self):
        """
        Override calculate_performance to ensure mole fractions are correct first.
        """
        # Get inlet conditions
        inlet_state = self.control_volume.properties_in[0]
        
        # Check water mole fraction
        water_mole_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
        
        if water_mole_frac < 0.95:
            logger.warning(f"Low water mole fraction detected: {water_mole_frac:.6f}")
            logger.info("Fixing mole fractions before PHREEQC calculations...")
            
            # Fix mole fractions
            fix_mole_fractions(inlet_state)
            
            # Check again
            water_mole_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
            logger.info(f"Water mole fraction after fix: {water_mole_frac:.6f}")
            
            # If still bad, try solving the property block
            if water_mole_frac < 0.95:
                from pyomo.environ import SolverFactory
                from idaes.core.util.model_statistics import degrees_of_freedom
                
                inlet_dof = degrees_of_freedom(inlet_state)
                if inlet_dof > 0:
                    solver = SolverFactory('ipopt')
                    solver.options['tol'] = 1e-8
                    results = solver.solve(inlet_state, tee=False)
                    
                    if results.solver.termination_condition == 'optimal':
                        fix_mole_fractions(inlet_state)
                        water_mole_frac = value(inlet_state.mole_frac_phase_comp['Liq', 'H2O'])
                        logger.info(f"Water mole fraction after solve: {water_mole_frac:.6f}")
        
        # Now call the original method with correct mole fractions
        super().calculate_performance()
    
    def initialize_build(self, state_args=None, outlvl=idaeslog.NOTSET, solver=None, optarg=None):
        """
        Override initialize_build to ensure mole fractions are fixed early.
        """
        init_log = idaeslog.getInitLogger(self.name, outlvl, tag="unit")
        
        # Call parent method
        super().initialize_build(state_args=state_args, outlvl=outlvl, solver=solver, optarg=optarg)
        
        # After initialization, double-check the results
        inlet_state = self.control_volume.properties_in[0]
        outlet_state = self.control_volume.properties_out[0]
        
        # Check if hardness increased (sign of the problem)
        inlet_ca = value(inlet_state.conc_mass_phase_comp['Liq', 'Ca_2+']) * 1000
        outlet_ca = value(outlet_state.conc_mass_phase_comp['Liq', 'Ca_2+']) * 1000
        
        if outlet_ca > inlet_ca:
            init_log.warning(f"Hardness increased: {inlet_ca:.1f} → {outlet_ca:.1f} mg/L")
            init_log.warning("This indicates the IX model received incorrect water composition")
            init_log.warning("Attempting to recalculate with correct mole fractions...")
            
            # Fix inlet mole fractions again
            fix_mole_fractions(inlet_state)
            
            # Recalculate performance
            self.calculate_performance()
            
            # Update removal rates
            self._update_removal_rates()
            
            # Check again
            outlet_ca_new = value(outlet_state.conc_mass_phase_comp['Liq', 'Ca_2+']) * 1000
            if outlet_ca_new < outlet_ca:
                init_log.info(f"Fixed! New outlet Ca: {outlet_ca_new:.1f} mg/L")
            else:
                init_log.error("Unable to fix hardness increase issue")