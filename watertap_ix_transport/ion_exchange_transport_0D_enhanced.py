"""
Enhanced Ion Exchange Transport 0D Model

This provides a cleaner interface to the IonExchangeTransport0D model
with the mass transfer fix already integrated and tested.
"""

from .ion_exchange_transport_0D import (
    IonExchangeTransport0D,
    IonExchangeTransport0DData,
    ResinType,
    RegenerantChem
)
from pyomo.environ import value
import logging

logger = logging.getLogger(__name__)


class IonExchangeTransport0DEnhanced(IonExchangeTransport0D):
    """
    Enhanced version of IonExchangeTransport0D with automatic PHREEQC integration
    
    This version:
    - Follows the proven 3-step pattern: initialize → calculate_performance → solve
    - Automatically calls PHREEQC calculations during initialization
    - Avoids constraint deactivation issues found in earlier versions
    - Provides detailed performance reporting
    - Ensures mass transfer is properly propagated through control volume
    
    Usage:
        ix_unit = IonExchangeTransport0DEnhanced(...)
        ix_unit.initialize_enhanced()  # Handles all 3 steps automatically
    """
    
    def initialize_enhanced(self, **kwargs):
        """
        Enhanced initialization that follows the 3-step pattern:
        1. Initialize the IX unit
        2. Calculate PHREEQC performance (always)
        3. Solve to propagate mass transfer
        
        This simplified approach avoids constraint deactivation and follows
        the pattern that works in production notebooks.
        """
        # STEP 1: Initialize IX unit
        logger.info("Step 1: Initializing IX unit...")
        self.initialize(**kwargs)
        
        # STEP 2: Calculate PHREEQC performance (ALWAYS)
        logger.info("Step 2: Calculating PHREEQC performance...")
        self.calculate_performance()
        
        # STEP 3: Solve to propagate mass transfer
        logger.info("Step 3: Solving to propagate mass transfer...")
        from pyomo.environ import SolverFactory
        solver = SolverFactory('ipopt')
        solver.options['tol'] = 1e-6
        solver.options['constr_viol_tol'] = 1e-6
        solver.options['max_iter'] = 100
        
        results = solver.solve(self, tee=False)
        
        # Check solver status
        from pyomo.opt import TerminationCondition
        if results.solver.termination_condition == TerminationCondition.optimal:
            logger.info("Successfully solved IX model with mass transfer")
        else:
            logger.warning(f"Solve terminated with: {results.solver.termination_condition}")
            logger.warning("Mass transfer may not be fully propagated")
        
        # Report results
        self.report_performance()
        
    def calculate_performance(self):
        """
        Calculate ion exchange performance using PHREEQC
        """
        # This calls the existing _update_removal_rates which:
        # 1. Runs DirectPhreeqcEngine
        # 2. Updates ion_removal_rate variables
        # 3. Fixes them to prevent optimizer changes
        t = self.flowsheet().time.first()
        self._update_removal_rates(t)
        
    def report_performance(self):
        """
        Report key performance metrics
        """
        t = self.flowsheet().time.first()
        
        # Get inlet/outlet states
        inlet_state = self.control_volume.properties_in[t]
        outlet_state = self.control_volume.properties_out[t]
        
        # Calculate removal percentages
        logger.info("\nIon Exchange Performance:")
        
        for ion in ["Ca_2+", "Mg_2+", "Na_+"]:
            if ion in self.config.property_package.component_list:
                inlet_conc = value(inlet_state.conc_mass_phase_comp["Liq", ion]) * 1000  # mg/L
                outlet_conc = value(outlet_state.conc_mass_phase_comp["Liq", ion]) * 1000  # mg/L
                
                if inlet_conc > 0:
                    removal = (inlet_conc - outlet_conc) / inlet_conc * 100
                    logger.info(f"  {ion}: {inlet_conc:.1f} → {outlet_conc:.1f} mg/L ({removal:.1f}% removal)")
                else:
                    logger.info(f"  {ion}: {inlet_conc:.1f} → {outlet_conc:.1f} mg/L")
        
        # Report hardness
        ca_inlet = value(inlet_state.conc_mass_phase_comp["Liq", "Ca_2+"]) * 1000 if "Ca_2+" in self.config.property_package.component_list else 0
        mg_inlet = value(inlet_state.conc_mass_phase_comp["Liq", "Mg_2+"]) * 1000 if "Mg_2+" in self.config.property_package.component_list else 0
        ca_outlet = value(outlet_state.conc_mass_phase_comp["Liq", "Ca_2+"]) * 1000 if "Ca_2+" in self.config.property_package.component_list else 0
        mg_outlet = value(outlet_state.conc_mass_phase_comp["Liq", "Mg_2+"]) * 1000 if "Mg_2+" in self.config.property_package.component_list else 0
        
        hardness_in = ca_inlet * 2.5 + mg_inlet * 4.1  # as CaCO3
        hardness_out = ca_outlet * 2.5 + mg_outlet * 4.1
        
        if hardness_in > 0:
            hardness_removal = (hardness_in - hardness_out) / hardness_in * 100
            logger.info(f"\nTotal Hardness:")
            logger.info(f"  Inlet: {hardness_in:.1f} mg/L as CaCO3")
            logger.info(f"  Outlet: {hardness_out:.1f} mg/L as CaCO3")
            logger.info(f"  Removal: {hardness_removal:.1f}%")
        
        # Report breakthrough time if available
        if hasattr(self, "breakthrough_time"):
            bt = value(self.breakthrough_time)
            logger.info(f"\nBreakthrough time: {bt:.1f} hours")
            
        # Report mass transfer enforcement
        fixed_count = sum(1 for j in self.config.property_package.component_list
                         if self.ion_removal_rate[t, j].fixed and 
                         abs(value(self.ion_removal_rate[t, j])) > 1e-10)
        logger.info(f"\nMass balance enforcement: {fixed_count} ion removal rates fixed")
        
    def get_performance_summary(self):
        """
        Return a dictionary of key performance metrics
        """
        t = self.flowsheet().time.first()
        inlet_state = self.control_volume.properties_in[t]
        outlet_state = self.control_volume.properties_out[t]
        
        # Calculate metrics
        ca_inlet = value(inlet_state.conc_mass_phase_comp["Liq", "Ca_2+"]) * 1000 if "Ca_2+" in self.config.property_package.component_list else 0
        mg_inlet = value(inlet_state.conc_mass_phase_comp["Liq", "Mg_2+"]) * 1000 if "Mg_2+" in self.config.property_package.component_list else 0
        ca_outlet = value(outlet_state.conc_mass_phase_comp["Liq", "Ca_2+"]) * 1000 if "Ca_2+" in self.config.property_package.component_list else 0
        mg_outlet = value(outlet_state.conc_mass_phase_comp["Liq", "Mg_2+"]) * 1000 if "Mg_2+" in self.config.property_package.component_list else 0
        
        hardness_in = ca_inlet * 2.5 + mg_inlet * 4.1
        hardness_out = ca_outlet * 2.5 + mg_outlet * 4.1
        hardness_removal = (hardness_in - hardness_out) / hardness_in * 100 if hardness_in > 0 else 0
        
        return {
            "ca_removal_percent": (ca_inlet - ca_outlet) / ca_inlet * 100 if ca_inlet > 0 else 0,
            "mg_removal_percent": (mg_inlet - mg_outlet) / mg_inlet * 100 if mg_inlet > 0 else 0,
            "hardness_removal_percent": hardness_removal,
            "hardness_outlet_mg_L": hardness_out,
            "breakthrough_hours": value(self.breakthrough_time) if hasattr(self, "breakthrough_time") else None,
            "phreeqc_engine": "DirectPhreeqcEngine",
            "mass_balance_enforced": True
        }