"""
Simplified Degasser Model for WaterTAP

This model simulates acid addition and CO2 stripping in a degasser unit.
Uses a simplified approach with direct mass transfer terms.
"""

from pyomo.environ import (
    Var, Param, Constraint, 
    units as pyunits, value,
    NonNegativeReals
)
from pyomo.common.config import ConfigBlock, ConfigValue, In

from idaes.core import (
    declare_process_block_class,
    MaterialBalanceType,
    EnergyBalanceType,
    MomentumBalanceType,
    UnitModelBlockData,
)
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.exceptions import ConfigurationError
import idaes.core.util.scaling as iscale
import idaes.logger as idaeslog

from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock
from watertap.unit_models.cstr_injection import CSTR_InjectionData


@declare_process_block_class("SimpleDegasser")
class SimpleDegasserData(CSTR_InjectionData):
    """
    Simplified degasser model using CSTR_Injection as base.
    
    This model:
    1. Adds acid (H+) to reduce pH
    2. Removes HCO3- (as CO2 stripping)
    3. Tracks alkalinity changes
    """
    
    # No need to modify CONFIG here - we'll pass options during instantiation
    
    def build(self):
        """Build the simplified degasser model."""
        super().build()
        
        # Check property package
        if not isinstance(self.config.property_package, MCASParameterBlock):
            raise ConfigurationError(
                "SimpleDegasser requires MCAS property package"
            )
        
        # Check required species
        required_species = {'H2O', 'H_+', 'HCO3_-'}
        available = set(self.config.property_package.component_list)
        
        if not required_species.issubset(available):
            missing = required_species - available
            raise ConfigurationError(
                f"Property package missing required species: {missing}"
            )
        
        # Operating parameters
        self.acid_dose = Var(
            initialize=0.001,
            bounds=(0, 0.01),
            units=pyunits.mol/pyunits.L,
            doc="Acid dose (mol/L)"
        )
        
        self.co2_removal_fraction = Var(
            initialize=0.9,
            bounds=(0, 1),
            units=pyunits.dimensionless,
            doc="Fraction of HCO3 removed as CO2"
        )
        
        # Performance variables
        self.alkalinity_in = Var(
            initialize=100,
            bounds=(0, 1000),
            units=pyunits.mg/pyunits.L,
            doc="Inlet alkalinity as CaCO3"
        )
        
        self.alkalinity_out = Var(
            initialize=10,
            bounds=(0, 1000),
            units=pyunits.mg/pyunits.L,
            doc="Outlet alkalinity as CaCO3"
        )
        
        # Constraints
        @self.Constraint(self.flowsheet().time)
        def acid_addition(b, t):
            """Add acid to the system."""
            # Get inlet flow rate
            flow_vol = b.control_volume.properties_in[t].flow_vol_phase['Liq']
            
            # Calculate moles of H+ to add (mol/s)
            h_added_mol = b.acid_dose * flow_vol
            
            # Convert to mass basis (kg/s)
            # MW of H+ = 0.001 kg/mol
            h_added_mass = h_added_mol * 0.001
            
            # Set mass transfer term for H+
            return b.control_volume.mass_transfer_term[t, 'Liq', 'H_+'] == h_added_mass
        
        @self.Constraint(self.flowsheet().time)
        def co2_stripping(b, t):
            """Remove HCO3 as CO2."""
            # Get inlet HCO3 concentration
            hco3_conc = b.control_volume.properties_in[t].conc_mol_phase_comp['Liq', 'HCO3_-']
            flow_vol = b.control_volume.properties_in[t].flow_vol_phase['Liq']
            
            # Calculate HCO3 removal rate (mol/s)
            hco3_removed_mol = b.co2_removal_fraction * hco3_conc * flow_vol / 1000
            
            # Convert to mass basis (kg/s)
            # MW of HCO3- = 0.061 kg/mol
            hco3_removed_mass = hco3_removed_mol * 0.061
            
            # Set mass transfer term for HCO3- (negative for removal)
            return b.control_volume.mass_transfer_term[t, 'Liq', 'HCO3_-'] == -hco3_removed_mass
        
        @self.Constraint(self.flowsheet().time)
        def alkalinity_in_calc(b, t):
            """Calculate inlet alkalinity."""
            # Simplified: alkalinity ≈ [HCO3-] in mg/L as CaCO3
            hco3_conc = b.control_volume.properties_in[t].conc_mol_phase_comp['Liq', 'HCO3_-']
            
            # Convert mol/m³ to mg/L as CaCO3
            # 1 mol/m³ HCO3- = 50 mg/L as CaCO3
            return b.alkalinity_in == hco3_conc * 50
        
        @self.Constraint(self.flowsheet().time)
        def alkalinity_out_calc(b, t):
            """Calculate outlet alkalinity."""
            hco3_conc = b.control_volume.properties_out[t].conc_mol_phase_comp['Liq', 'HCO3_-']
            return b.alkalinity_out == hco3_conc * 50
        
        # Set initial values
        self._set_initial_values()
    
    def _set_initial_values(self):
        """Set initial values for variables."""
        self.acid_dose.set_value(0.002)
        self.co2_removal_fraction.set_value(0.9)
    
    def initialize_build(
        self,
        state_args=None,
        outlvl=idaeslog.NOTSET,
        solver=None,
        optarg=None,
    ):
        """
        Initialize the degasser model.
        
        Uses parent class initialization which handles the control volume.
        """
        # Set reasonable defaults for mass transfer if not initialized
        for t in self.flowsheet().time:
            if hasattr(self.control_volume, 'mass_transfer_term'):
                self.control_volume.mass_transfer_term[t, 'Liq', 'H_+'].set_value(1e-6)
                self.control_volume.mass_transfer_term[t, 'Liq', 'HCO3_-'].set_value(-1e-6)
        
        # Call parent initialization
        super().initialize_build(
            state_args=state_args,
            outlvl=outlvl,
            solver=solver,
            optarg=optarg
        )