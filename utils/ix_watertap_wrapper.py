"""
WaterTAP Hybrid Wrapper for IX Systems

Provides WaterTAP flowsheet structure and costing framework while using
PHREEQC for actual ion exchange chemistry calculations.
"""

import logging
from typing import Dict, Any, Optional
import os

# Set threading environment for stability before any imports
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')

# Check if WaterTAP is available without importing it
WATERTAP_AVAILABLE = False
try:
    import watertap
    import idaes
    import pyomo
    WATERTAP_AVAILABLE = True
except ImportError:
    WATERTAP_AVAILABLE = False

from utils.stdout_redirect import redirect_stdout_to_stderr

logger = logging.getLogger(__name__)


if WATERTAP_AVAILABLE:
    # Lazy imports to prevent hanging
    def get_watertap_components():
        """Import WaterTAP components when actually needed."""
        from pyomo.environ import (
            ConcreteModel, Block, Var, Constraint, Param, Set,
            NonNegativeReals, value, units as pyunits
        )
        from pyomo.common.config import ConfigBlock, ConfigValue
        from idaes.core import (
            FlowsheetBlock,
            UnitModelBlockData,
            declare_process_block_class,
        )
        from idaes.core.util.config import is_physical_parameter_block
        try:
            from idaes.core.initialization import InitializationStatus
        except ImportError:
            from idaes.core.util.initialization import InitializationStatus
        from idaes.core.solvers import get_solver
        from idaes.core.util.model_statistics import degrees_of_freedom
        from watertap.core.solvers import get_solver as get_watertap_solver
        from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock
        from watertap.costing import WaterTAPCosting
        
        return {
            'ConcreteModel': ConcreteModel,
            'Var': Var,
            'Constraint': Constraint,
            'Param': Param,
            'Set': Set,
            'NonNegativeReals': NonNegativeReals,
            'value': value,
            'pyunits': pyunits,
            'ConfigBlock': ConfigBlock,
            'ConfigValue': ConfigValue,
            'FlowsheetBlock': FlowsheetBlock,
            'UnitModelBlockData': UnitModelBlockData,
            'declare_process_block_class': declare_process_block_class,
            'is_physical_parameter_block': is_physical_parameter_block,
            'InitializationStatus': InitializationStatus,
            'get_solver': get_solver,
            'degrees_of_freedom': degrees_of_freedom,
            'get_watertap_solver': get_watertap_solver,
            'MCASParameterBlock': MCASParameterBlock,
            'WaterTAPCosting': WaterTAPCosting
        }
    
    # Import components when module loads (but isolated in function)
    wt_components = get_watertap_components()
    
    ConfigBlock = wt_components['ConfigBlock']
    ConfigValue = wt_components['ConfigValue']
    is_physical_parameter_block = wt_components['is_physical_parameter_block']
    UnitModelBlockData = wt_components['UnitModelBlockData']
    declare_process_block_class = wt_components['declare_process_block_class']
    Var = wt_components['Var']
    Param = wt_components['Param']
    Constraint = wt_components['Constraint']
    NonNegativeReals = wt_components['NonNegativeReals']
    pyunits = wt_components['pyunits']
    value = wt_components['value']
    InitializationStatus = wt_components['InitializationStatus']
    
    @declare_process_block_class("IXPlaceholderUnit")
    class IXPlaceholderUnitData(UnitModelBlockData):
        """
        Custom IX unit model that accepts external PHREEQC calculations.
        
        This placeholder unit allows injection of PHREEQC results into
        a WaterTAP flowsheet for proper stream connections and costing.
        """
        
        CONFIG = ConfigBlock()
        CONFIG.declare(
            "dynamic",
            ConfigValue(
                default=False,
                domain=bool,
                description="Dynamic model flag",
                doc="Dynamic model flag - should be False for steady state"
            )
        )
        CONFIG.declare(
            "has_holdup",
            ConfigValue(
                default=False,
                domain=bool,
                description="Holdup construction flag",
                doc="Holdup construction flag - should be False for steady state"
            )
        )
        CONFIG.declare(
            "property_package",
            ConfigValue(
                default=None,
                domain=is_physical_parameter_block,
                description="Property parameter object used to define property calculations",
                doc="""Property parameter object used to define property calculations,
                **default** - useDefault.
                **Valid values:** {
                **useDefault** - use default package from parent model or flowsheet,
                **PhysicalParameterObject** - a PhysicalParameterBlock object.}"""
            )
        )
        CONFIG.declare(
            "regenerant",
            ConfigValue(
                default="NaCl",
                domain=str,
                description="Regenerant chemical",
                doc="""Type of regenerant used: NaCl, HCl, NaOH, MeOH, single_use"""
            )
        )
        CONFIG.declare(
            "hazardous_waste",
            ConfigValue(
                default=False,
                domain=bool,
                description="Hazardous waste disposal required",
                doc="""True if regenerant requires hazardous waste disposal (acids/caustics)"""
            )
        )
        
        def build(self):
            """Build the IX placeholder unit model."""
            super().build()
            
            # Get the property package from config
            prop_pkg = self.config.property_package
            
            # Create inlet and outlet state blocks
            self.properties_in = prop_pkg.build_state_block(
                self.flowsheet().time,
                doc="Material properties at inlet",
                defined_state=True
            )
            
            self.properties_out = prop_pkg.build_state_block(
                self.flowsheet().time,
                doc="Material properties at outlet"
            )
            
            # Use built-in methods to add ports (they handle the proper referencing)
            self.add_inlet_port(name="inlet", block=self.properties_in)
            self.add_outlet_port(name="outlet", block=self.properties_out)
            
            # Add variables for IX performance (to be set from PHREEQC)
            self.removal_fraction = Var(
                prop_pkg.solute_set,
                domain=NonNegativeReals,
                bounds=(0, 1),
                doc="Removal fraction by component from PHREEQC"
            )
            
            # Add vessel sizing parameters (for costing)
            self.bed_depth = Var(
                domain=NonNegativeReals,
                units=pyunits.m,
                doc="Bed depth in meters"
            )
            
            self.column_diameter = Var(
                domain=NonNegativeReals,
                units=pyunits.m,
                doc="Column diameter in meters"
            )
            
            self.resin_volume = Var(
                domain=NonNegativeReals,
                units=pyunits.m**3,
                doc="Resin volume in cubic meters"
            )
            
            self.service_flow_rate = Var(
                domain=NonNegativeReals,
                units=pyunits.m**3/pyunits.hr,
                doc="Service flow rate"
            )
            
            # Add mass balance constraints
            @self.Constraint(self.flowsheet().time, prop_pkg.phase_list, prop_pkg.component_list)
            def mass_balance(b, t, p, j):
                """Component mass balance with removal fraction."""
                if j in prop_pkg.solute_set:
                    # Ions are partially removed based on removal_fraction
                    return b.properties_out[t].flow_mol_phase_comp[p, j] == \
                           b.properties_in[t].flow_mol_phase_comp[p, j] * (1 - b.removal_fraction[j])
                else:
                    # Water passes through unchanged
                    return b.properties_out[t].flow_mol_phase_comp[p, j] == \
                           b.properties_in[t].flow_mol_phase_comp[p, j]
            
            # Temperature and pressure pass through unchanged
            @self.Constraint(self.flowsheet().time)
            def temperature_balance(b, t):
                return b.properties_out[t].temperature == b.properties_in[t].temperature
            
            @self.Constraint(self.flowsheet().time)
            def pressure_balance(b, t):
                return b.properties_out[t].pressure == b.properties_in[t].pressure
            
            # ========== EPA-WBS Costing Attributes ==========
            # Required by WaterTAP's cost_ion_exchange function
            
            # Structural parameters
            self.number_columns = Param(
                default=2,
                mutable=True,
                doc="Number of columns in service"
            )
            
            self.number_columns_redund = Param(
                default=1,
                mutable=True,
                doc="Number of redundant columns"
            )
            
            # Resin properties
            self.resin_bulk_dens = Param(
                default=800,
                units=pyunits.kg/pyunits.m**3,
                mutable=True,
                doc="Bulk density of resin"
            )
            
            # Ion exchange type for costing
            self.ion_exchange_type = Param(
                default="cation",
                mutable=True,
                doc="Type of ion exchange: 'cation' or 'anion'"
            )
            
            # Volume calculations (as Expressions for automatic updates)
            @self.Expression(doc="Volume per column (m³)")
            def col_vol_per(b):
                import math
                return math.pi * (b.column_diameter/2)**2 * b.bed_depth
            
            @self.Expression(doc="Bed volume per column (m³)")
            def bed_vol(b):
                return b.resin_volume  # Per column
            
            @self.Expression(doc="Total bed volume (m³)")
            def bed_vol_tot(b):
                return b.bed_vol * (b.number_columns + b.number_columns_redund)
            
            # Cycle time parameters (in seconds for WaterTAP)
            self.t_cycle = Var(
                domain=NonNegativeReals,
                units=pyunits.s,
                doc="Total cycle time in seconds"
            )
            
            self.t_breakthru = Var(
                domain=NonNegativeReals,
                units=pyunits.s,
                doc="Breakthrough time in seconds"
            )
            
            self.t_bw = Var(
                domain=NonNegativeReals,
                units=pyunits.s,
                doc="Backwash time in seconds"
            )
            
            self.t_rinse = Var(
                domain=NonNegativeReals,
                units=pyunits.s,
                doc="Rinse time in seconds"
            )
            
            self.t_regen = Var(
                domain=NonNegativeReals,
                units=pyunits.s,
                doc="Regeneration time in seconds"
            )
            
            # Flow parameters for backwash and rinse
            @self.Expression(doc="Backwash flow rate (m³/s)")
            def bw_flow(b):
                # Typical backwash at 10 BV/hr
                return b.bed_vol_tot * 10 / 3600  # m³/s
            
            @self.Expression(doc="Rinse flow rate (m³/s)")
            def rinse_flow(b):
                # Rinse at service flow rate
                return b.service_flow_rate / 3600  # Convert m³/hr to m³/s
            
            # Regenerant dose (kg/m³ resin)
            self.regen_dose = Var(
                domain=NonNegativeReals,
                units=pyunits.kg/pyunits.m**3,
                doc="Regenerant dose per m³ of resin"
            )
            
            # Tank volumes
            @self.Expression(doc="Regeneration tank volume (m³)")
            def regen_tank_vol(b):
                # Tank sized for regeneration solution
                # Volume = flow rate * time
                regen_flow_m3s = b.service_flow_rate / 3600 / 4  # 1/4 of service flow
                return regen_flow_m3s * b.t_regen
            
            # Pump power expressions (kW)
            # P[kW] = (Q[m³/s] * ΔP[Pa]) / η / 1000
            self.delta_p = Param(
                default=2,  # 2 bar typical
                units=pyunits.bar,
                mutable=True,
                doc="Pressure drop across bed"
            )
            
            @self.Expression(doc="Main pump power (kW)")
            def main_pump_power(b):
                Q_m3s = b.service_flow_rate / 3600
                delta_p_pa = b.delta_p * 1e5  # bar to Pa
                eta = 0.7  # Pump efficiency
                return (Q_m3s * delta_p_pa) / eta / 1000
            
            @self.Expression(doc="Backwash pump power (kW)")
            def bw_pump_power(b):
                delta_p_pa = b.delta_p * 1e5 * 0.5  # Lower pressure for backwash
                eta = 0.7
                return (b.bw_flow * delta_p_pa) / eta / 1000
            
            @self.Expression(doc="Rinse pump power (kW)")
            def rinse_pump_power(b):
                Q_m3s = b.service_flow_rate / 3600
                delta_p_pa = b.delta_p * 1e5
                eta = 0.7
                return (Q_m3s * delta_p_pa) / eta / 1000
            
            @self.Expression(doc="Regeneration pump power (kW)")
            def regen_pump_power(b):
                Q_m3s = b.service_flow_rate / 3600 / 4  # 1/4 of service flow
                delta_p_pa = b.delta_p * 1e5 * 0.5  # Lower pressure
                eta = 0.7
                return (Q_m3s * delta_p_pa) / eta / 1000
            
            # Legacy parameters kept for compatibility
            self.regenerant_dose_kg = Var(
                domain=NonNegativeReals,
                units=pyunits.kg,
                doc="Regenerant dose per cycle (legacy)"
            )
            
            self.cycle_time = Var(
                domain=NonNegativeReals,
                units=pyunits.hr,
                doc="Total cycle time in hours (legacy)"
            )
        
        def _add_material_balance_constraints(self):
            """Add material balance constraints linking inlet to outlet."""
            
            # Get time points (usually just 0 for steady-state)
            time_points = self.flowsheet().time
            
            # Component material balance
            @self.Constraint(
                time_points,
                self.config.property_package.solute_set,
                doc="Component material balance"
            )
            def component_material_balance(b, t, j):
                """Outlet = Inlet * (1 - removal_fraction)"""
                return (
                    b.outlet.flow_mol_phase_comp[t, "Liq", j] ==
                    b.inlet.flow_mol_phase_comp[t, "Liq", j] * 
                    (1 - b.removal_fraction[j])
                )
            
            # Water balance (no water removal in IX)
            @self.Constraint(time_points, doc="Water balance")
            def water_balance(b, t):
                """Water flow unchanged"""
                return (
                    b.outlet.flow_mol_phase_comp[t, "Liq", "H2O"] ==
                    b.inlet.flow_mol_phase_comp[t, "Liq", "H2O"]
                )
        
        def initialize(self, **kwargs):
            """Initialize the IX placeholder unit."""
            # Simple initialization - just pass through
            for t in self.flowsheet().time:
                for j in self.config.property_package.component_list:
                    if j == "H2O":
                        self.outlet.flow_mol_phase_comp[t, "Liq", j].set_value(
                            value(self.inlet.flow_mol_phase_comp[t, "Liq", j])
                        )
                    else:
                        # Default to 90% removal if not set
                        if j in self.removal_fraction:
                            removal = value(self.removal_fraction[j])
                        else:
                            removal = 0.9
                        
                        self.outlet.flow_mol_phase_comp[t, "Liq", j].set_value(
                            value(self.inlet.flow_mol_phase_comp[t, "Liq", j]) * 
                            (1 - removal)
                        )
            
            return InitializationStatus.Ok


class IXWaterTAPWrapper:
    """
    Hybrid wrapper integrating PHREEQC chemistry with WaterTAP flowsheet.
    
    This class builds a WaterTAP flowsheet structure with placeholder IX unit,
    injects PHREEQC results, and applies WaterTAP costing.
    """
    
    def __init__(self):
        """Initialize the wrapper."""
        if not WATERTAP_AVAILABLE:
            raise ImportError(
                "WaterTAP is required for hybrid simulation. "
                "Install with: pip install watertap>=0.11.0"
            )

        self.model = None
        self.flowsheet = None
        self.phreeqc_results = None
        self.pricing = {}  # Store pricing parameters for LCOW calculation
    
    def build_flowsheet(
        self,
        feed_composition: Dict[str, float],
        flow_rate_m3h: float,
        vessel_config: Dict[str, Any]
    ) -> ConcreteModel:
        """
        Build WaterTAP flowsheet with IX placeholder.
        
        Args:
            feed_composition: Ion concentrations in mg/L
            flow_rate_m3h: Feed flow rate in m³/hr
            vessel_config: Vessel configuration parameters
            
        Returns:
            Pyomo ConcreteModel with flowsheet
        """
        logger.info("Building WaterTAP flowsheet for IX system")
        
        # Build model with stdout redirected
        with redirect_stdout_to_stderr():
            # Create model
            m = ConcreteModel()
            m.fs = FlowsheetBlock(dynamic=False)
            
            # Create property package
            m.fs.properties = self._build_mcas_properties(feed_composition)
            
            # Add feed
            from idaes.models.unit_models import Feed
            m.fs.feed = Feed(property_package=m.fs.properties)
            
            # Add IX placeholder unit with regenerant configuration
            # Determine regenerant type from vessel config
            regenerant = vessel_config.get('regenerant_type', 'NaCl')
            hazardous = regenerant in ['HCl', 'H2SO4', 'NaOH']
            
            m.fs.ix_unit = IXPlaceholderUnit(
                property_package=m.fs.properties,
                regenerant=regenerant,
                hazardous_waste=hazardous
            )
            
            # Add product
            from idaes.models.unit_models import Product
            m.fs.product = Product(property_package=m.fs.properties)
            
            # Connect units (simplified - no pump)
            from pyomo.network import Arc
            m.fs.feed_to_ix = Arc(
                source=m.fs.feed.outlet,
                destination=m.fs.ix_unit.inlet
            )
            m.fs.ix_to_product = Arc(
                source=m.fs.ix_unit.outlet,
                destination=m.fs.product.inlet
            )
            
            # Apply arc constraints
            from pyomo.environ import TransformationFactory
            TransformationFactory("network.expand_arcs").apply_to(m)
            
            # Set feed conditions
            self._set_feed_conditions(m, feed_composition, flow_rate_m3h)
            
            # Set IX vessel parameters from config
            m.fs.ix_unit.bed_depth.fix(vessel_config.get('bed_depth_m', 2.0))
            m.fs.ix_unit.column_diameter.fix(vessel_config.get('diameter_m', 1.5))
            m.fs.ix_unit.resin_volume.fix(vessel_config.get('resin_volume_m3', 3.5))
            m.fs.ix_unit.service_flow_rate.fix(flow_rate_m3h)
        
        self.model = m
        self.flowsheet = m.fs
        return m
    
    def _build_mcas_properties(
        self,
        feed_composition: Dict[str, float]
    ) -> MCASParameterBlock:
        """
        Build MCAS property package based on feed composition.
        
        Args:
            feed_composition: Ion concentrations in mg/L
            
        Returns:
            MCAS parameter block
        """
        # Map common ions to MCAS species
        ion_mapping = {
            'Ca_2+': 'Ca_2+',
            'Mg_2+': 'Mg_2+',
            'Na_+': 'Na_+',
            'Cl_-': 'Cl_-',
            'HCO3_-': 'HCO3_-',
            'SO4_2-': 'SO4_2-'
        }
        
        # Build solute list from feed
        solute_list = []
        for ion in feed_composition:
            if ion in ion_mapping and feed_composition[ion] > 0:
                solute_list.append(ion_mapping[ion])
        
        # Ensure we have at least Na+ and Cl- for stability
        if 'Na_+' not in solute_list:
            solute_list.append('Na_+')
        if 'Cl_-' not in solute_list:
            solute_list.append('Cl_-')
        
        # Define lookups for all possible components
        mw_lookup = {
            'Na_+': 23e-3,
            'Cl_-': 35.45e-3,
            'Ca_2+': 40.08e-3,
            'Mg_2+': 24.31e-3,
            'HCO3_-': 61.02e-3,
            'SO4_2-': 96.06e-3
        }
        
        charge_lookup = {
            'Na_+': 1,
            'Ca_2+': 2,
            'Mg_2+': 2,
            'Cl_-': -1,
            'HCO3_-': -1,
            'SO4_2-': -2
        }
        
        # Build mw_data and charge ONLY for components in solute_list
        mw_data = {'H2O': 18e-3}  # Always include water
        charge = {}
        
        for solute in solute_list:
            if solute in mw_lookup:
                mw_data[solute] = mw_lookup[solute]
            if solute in charge_lookup:
                charge[solute] = charge_lookup[solute]
        
        # Create MCAS configuration with filtered data
        mcas_config = {
            'solute_list': solute_list,
            'diffusivity_data': {
                ('Liq', s): 1e-9 for s in solute_list
            },
            'mw_data': mw_data,  # Now filtered to solute_list
            'charge': charge      # Now filtered to solute_list
        }
        
        return MCASParameterBlock(**mcas_config)
    
    def _set_feed_conditions(
        self,
        model: ConcreteModel,
        feed_composition: Dict[str, float],
        flow_rate_m3h: float
    ):
        """Set feed stream conditions."""
        # Fix temperature and pressure
        model.fs.feed.temperature.fix(298.15)  # 25°C
        model.fs.feed.pressure.fix(101325)  # 1 atm
        
        # Get molecular weights from property package or use lookup
        mw_lookup = {
            'Na_+': 23.0,     # g/mol
            'Cl_-': 35.45,    # g/mol
            'Ca_2+': 40.08,   # g/mol
            'Mg_2+': 24.31,   # g/mol
            'HCO3_-': 61.02,  # g/mol
            'SO4_2-': 96.06   # g/mol
        }
        
        # Convert flow rate to m³/s for calculations
        flow_rate_m3s = flow_rate_m3h / 3600
        
        # Set component flows
        total_solute_flow_mol_s = 0
        for comp in model.fs.properties.solute_set:
            if comp in feed_composition and feed_composition[comp] > 0:
                # Get molecular weight
                if hasattr(model.fs.properties, 'mw_comp'):
                    mw_g_per_mol = value(model.fs.properties.mw_comp[comp]) * 1000  # kg/mol to g/mol
                else:
                    mw_g_per_mol = mw_lookup.get(comp, 50.0)  # Default if not found
                
                # Convert mg/L to mol/m³
                conc_mg_L = feed_composition[comp]
                conc_g_m3 = conc_mg_L  # mg/L = g/m³
                conc_mol_m3 = conc_g_m3 / mw_g_per_mol
                
                # Calculate component flow in mol/s
                comp_flow_mol_s = conc_mol_m3 * flow_rate_m3s
                model.fs.feed.flow_mol_phase_comp[0, "Liq", comp].fix(comp_flow_mol_s)
                total_solute_flow_mol_s += comp_flow_mol_s
            else:
                model.fs.feed.flow_mol_phase_comp[0, "Liq", comp].fix(1e-8)
        
        # Calculate water flow based on total volume minus solute volume
        # Assume water density = 1000 kg/m³ and MW = 18 g/mol
        water_mass_flow_kg_s = flow_rate_m3s * 1000  # Approximate, assuming dilute solution
        water_flow_mol_s = water_mass_flow_kg_s / 0.018  # kg/s to mol/s
        
        # Set water flow
        model.fs.feed.flow_mol_phase_comp[0, "Liq", "H2O"].fix(water_flow_mol_s)
    
    def inject_phreeqc_results(
        self,
        phreeqc_results: Dict[str, Any],
        vessel_config: Optional[Dict[str, Any]] = None,
        regen_config: Optional[Dict[str, Any]] = None
    ):
        """
        Inject PHREEQC simulation results into flowsheet.
        
        Args:
            phreeqc_results: Results from PHREEQC simulation including
                            removal fractions and regeneration data
            vessel_config: Optional vessel configuration
            regen_config: Optional regeneration configuration
        """
        if self.model is None:
            raise RuntimeError("Flowsheet must be built first")
        
        logger.info("Injecting PHREEQC results into WaterTAP flowsheet")
        
        # Set removal fractions from PHREEQC
        performance = phreeqc_results.get('performance_metrics', {})
        
        # Map removal percentages to removal fractions
        removal_mapping = {
            'Ca_2+': performance.get('breakthrough_ca_removal_percent', 95) / 100,
            'Mg_2+': performance.get('breakthrough_mg_removal_percent', 95) / 100,
            'Na_+': 0,  # Na typically increases in SAC
            'Cl_-': 0,  # Anions pass through cation exchange
            'HCO3_-': 0,
            'SO4_2-': 0
        }
        
        # Set removal fractions
        for ion, removal in removal_mapping.items():
            if ion in self.model.fs.ix_unit.removal_fraction:
                self.model.fs.ix_unit.removal_fraction[ion].fix(removal)
        
        # ========== Set EPA-WBS Required Attributes ==========
        
        # Set time parameters (convert hours to seconds)
        service_results = phreeqc_results.get('service_results', {})
        self.model.fs.ix_unit.t_breakthru.fix(
            service_results.get('service_time_hours', 24) * 3600
        )
        self.model.fs.ix_unit.t_cycle.fix(
            phreeqc_results.get('regeneration_results', {}).get('total_cycle_time_hours', 48) * 3600
        )
        
        # Get regeneration configuration
        regen_results = phreeqc_results.get('regeneration_results', {})
        if regen_config is None:
            regen_config = phreeqc_results.get('regeneration_config', {})
        
        # Set regeneration time
        self.model.fs.ix_unit.t_regen.fix(
            regen_results.get('regeneration_time_hours', 2) * 3600
        )
        
        # Calculate backwash parameters
        backwash_bv = regen_config.get('backwash_bv', 3)  # Bed volumes
        backwash_flow_bv_hr = regen_config.get('backwash_flow_rate_bv_hr', 10)
        self.model.fs.ix_unit.t_bw.fix(
            (backwash_bv / backwash_flow_bv_hr) * 3600  # Convert to seconds
        )
        
        # Calculate rinse parameters (slow + fast rinse)
        slow_rinse_bv = regen_config.get('slow_rinse_bv', 2)
        fast_rinse_bv = regen_config.get('fast_rinse_bv', 4)
        total_rinse_bv = slow_rinse_bv + fast_rinse_bv
        rinse_flow_bv_hr = regen_config.get('rinse_flow_rate_bv_hr', 16)  # Service flow rate
        self.model.fs.ix_unit.t_rinse.fix(
            (total_rinse_bv / rinse_flow_bv_hr) * 3600  # Convert to seconds
        )
        
        # Set regenerant dose (kg/m³ resin)
        regen_consumed_kg = regen_results.get('regenerant_consumed_kg', 100)
        bed_vol_tot_m3 = value(self.model.fs.ix_unit.bed_vol_tot)
        if bed_vol_tot_m3 > 0:
            self.model.fs.ix_unit.regen_dose.fix(
                regen_consumed_kg / bed_vol_tot_m3
            )
        else:
            self.model.fs.ix_unit.regen_dose.fix(100)  # Default 100 kg/m³
        
        # Set pressure drop (from PHREEQC results or default)
        delta_p_bar = phreeqc_results.get('hydraulics', {}).get('delta_p_bar', 2.0)
        self.model.fs.ix_unit.delta_p.set_value(delta_p_bar)
        
        # Set structural parameters if provided
        if vessel_config:
            if 'number_columns' in vessel_config:
                self.model.fs.ix_unit.number_columns.set_value(
                    vessel_config['number_columns']
                )
            if 'number_columns_redund' in vessel_config:
                self.model.fs.ix_unit.number_columns_redund.set_value(
                    vessel_config.get('number_columns_redund', 1)
                )
        
        # Set ion exchange type based on resin
        resin_type = vessel_config.get('resin_type', 'SAC') if vessel_config else 'SAC'
        if resin_type in ['SAC', 'WAC_Na', 'WAC_H']:
            self.model.fs.ix_unit.ion_exchange_type.set_value('cation')
        elif resin_type in ['SBA', 'WBA']:
            self.model.fs.ix_unit.ion_exchange_type.set_value('anion')
        
        # Legacy parameters for compatibility
        self.model.fs.ix_unit.regenerant_dose_kg.fix(
            regen_results.get('regenerant_consumed_kg', 100)
        )
        self.model.fs.ix_unit.cycle_time.fix(
            regen_results.get('total_cycle_time_hours', 24)
        )
        
        self.phreeqc_results = phreeqc_results
    
    def solve_flowsheet(self) -> bool:
        """
        Solve the WaterTAP flowsheet.
        
        Returns:
            True if solved successfully
        """
        if self.model is None:
            raise RuntimeError("Flowsheet must be built first")
        
        logger.info("Solving WaterTAP flowsheet")
        
        with redirect_stdout_to_stderr():
            # Get solver
            solver = get_watertap_solver()
            
            # Set solver options for stability
            solver.options['max_cpu_time'] = 30  # 30 second limit
            solver.options['tol'] = 1e-6
            solver.options['acceptable_tol'] = 1e-4
            
            # Initialize flowsheet
            self.model.fs.feed.initialize()
            # No pump in simplified flowsheet
            self.model.fs.ix_unit.initialize()
            self.model.fs.product.initialize()
            
            # Check degrees of freedom
            dof = degrees_of_freedom(self.model)
            logger.info(f"Degrees of freedom: {dof}")
            
            if dof != 0:
                logger.error(f"Model has {dof} degrees of freedom - cannot solve")
                return False
            
            # Solve with timeout protection
            results = solver.solve(self.model, tee=False)
            
            from pyomo.opt import TerminationCondition
            if results.solver.termination_condition == TerminationCondition.optimal:
                logger.info("Flowsheet solved successfully")
                return True
            else:
                logger.error(f"Solve failed: {results.solver.termination_condition}")
                return False
    
    def apply_costing(
        self,
        pricing: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Apply WaterTAP costing to the flowsheet.
        
        Args:
            pricing: Optional pricing parameters
            
        Returns:
            Dictionary of costing results
        """
        if self.model is None:
            raise RuntimeError("Flowsheet must be built and solved first")
        
        logger.info("Applying WaterTAP costing")
        
        with redirect_stdout_to_stderr():
            # Add costing block
            self.model.fs.costing = WaterTAPCosting()
            
            # Set financial parameters
            self.model.fs.costing.base_currency = pyunits.USD_2020
            self.model.fs.costing.electricity_cost.fix(
                pricing.get('electricity_usd_kwh', 0.07) if pricing else 0.07
            )
            
            # Add pump costing
            # No pump costing in simplified flowsheet
            
            # Add IX costing using custom method
            self._add_ix_costing(pricing)
            
            # Calculate costs
            self.model.fs.costing.cost_process()
            
            # Extract costing results
            results = self._extract_costing_results()
        
        return results
    
    def _add_ix_costing(self, pricing: Optional[Dict[str, float]] = None):
        """Add EPA-WBS IX costing using WaterTAP's cost_ion_exchange function."""
        m = self.model

        # Store pricing parameters for LCOW calculation
        self.pricing = pricing or {}
        
        # Configurable pump parameters
        PUMP_CONFIG = {
            'service_pressure_rise_pa': 250000,  # 2.5 bar default
            'backwash_pressure_rise_pa': 300000,  # 3 bar default for bed expansion
            'backwash_flow_bv_hr': 10.0,  # Bed volumes per hour for backwash
            'pump_efficiency': 0.75  # Pump efficiency
        }
        
        # Import required costing components
        from watertap.costing import UnitModelCostingBlock
        from watertap.costing.unit_models.ion_exchange import cost_ion_exchange
        from idaes.models.unit_models.pressure_changer import Pump
        from watertap.costing.unit_models.pump import cost_pump, PumpType
        
        # Add the ion exchange costing using official WaterTAP method
        m.fs.ix_unit.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing,
            costing_method=cost_ion_exchange
        )
        
        # The cost_ion_exchange function will automatically use EPA-WBS correlations:
        # - Cation resin: 153 USD/ft³ = ~$5,403/m³
        # - Vessel cost: 1596.5 × (V_gal)^0.459
        # - Backwash tank: 308.9 × (V_gal)^0.501
        # - Regen tank: 57.0 × (V_gal)^0.729
        # - Annual resin replacement: 5%
        
        # Add pump units with proper WaterTAP costing
        # Service pump - operates continuously during service phase
        m.fs.service_pump = Pump(property_package=m.fs.properties)
        # Fix each component flow individually with error handling
        for phase in m.fs.properties.phase_list:
            for comp in m.fs.properties.component_list:
                # Try to get flow from IX unit, fallback to feed if not available
                try:
                    if hasattr(m.fs.ix_unit, 'properties_in'):
                        flow_value = value(m.fs.ix_unit.properties_in[0].flow_mol_phase_comp[phase, comp])
                    else:
                        flow_value = value(m.fs.feed.outlet.flow_mol_phase_comp[0, phase, comp])
                except (AttributeError, KeyError):
                    # Fallback to minimal flow for solutes, larger for water
                    flow_value = 1e-8 if comp != 'H2O' else self.flow_rate_m3h * 1000 / 3.6 / 18
                m.fs.service_pump.inlet.flow_mol_phase_comp[0, phase, comp].fix(flow_value)
        m.fs.service_pump.inlet.temperature.fix(298.15)  # K
        m.fs.service_pump.inlet.pressure.fix(101325)  # Pa
        m.fs.service_pump.outlet.pressure.fix(101325 + PUMP_CONFIG['service_pressure_rise_pa'])
        m.fs.service_pump.efficiency_pump.fix(PUMP_CONFIG['pump_efficiency'])
        
        # Backwash pump - sized for configurable backwash flow
        m.fs.backwash_pump = Pump(property_package=m.fs.properties)
        # Get bed volume with fallback
        if hasattr(m.fs.ix_unit, 'bed_vol_tot'):
            bed_volume_m3 = value(m.fs.ix_unit.bed_vol_tot)
        elif hasattr(m.fs, 'resin_volume'):
            bed_volume_m3 = value(m.fs.resin_volume)
        else:
            # Fallback to vessel config or default
            bed_volume_m3 = self.vessel_config.get('resin_volume_m3', 6.28)
        backwash_flow_m3s = bed_volume_m3 * PUMP_CONFIG['backwash_flow_bv_hr'] / 3600.0  # m³/s
        # Convert to molar flow assuming water density ~1000 kg/m³ and MW 18 g/mol
        backwash_flow_mol_s = backwash_flow_m3s * 1000 / 0.018  # mol/s
        m.fs.backwash_pump.inlet.flow_mol_phase_comp[0, 'Liq', 'H2O'].fix(backwash_flow_mol_s)
        # Set minimal solute flows for backwash water
        for j in m.fs.properties.solute_set:
            m.fs.backwash_pump.inlet.flow_mol_phase_comp[0, 'Liq', j].fix(1e-8)
        m.fs.backwash_pump.inlet.temperature.fix(298.15)
        m.fs.backwash_pump.inlet.pressure.fix(101325)
        m.fs.backwash_pump.outlet.pressure.fix(101325 + PUMP_CONFIG['backwash_pressure_rise_pa'])
        m.fs.backwash_pump.efficiency_pump.fix(PUMP_CONFIG['pump_efficiency'])
        
        # Initialize pumps before adding costing
        m.fs.service_pump.initialize()
        m.fs.backwash_pump.initialize()
        
        # Add pump costing using WaterTAP's low-pressure pump correlation
        m.fs.service_pump.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing,
            costing_method=cost_pump,
            costing_method_arguments={"pump_type": PumpType.low_pressure}
        )
        
        m.fs.backwash_pump.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing,
            costing_method=cost_pump,
            costing_method_arguments={"pump_type": PumpType.low_pressure}
        )
        
        # Override specific pricing if provided
        if pricing:
            if 'nacl_usd_kg' in pricing:
                # Set NaCl cost parameter in WaterTAP costing
                # This will be used automatically in OPEX calculations
                if not hasattr(m.fs.costing, 'nacl'):
                    # Create the NaCl costing parameter if it doesn't exist
                    m.fs.costing.nacl = Block()
                    m.fs.costing.nacl.cost = Param(
                        default=pricing['nacl_usd_kg'],
                        mutable=True,
                        units=pyunits.USD_2020/pyunits.kg
                    )
                else:
                    m.fs.costing.nacl.cost.set_value(pricing['nacl_usd_kg'])
            
            if 'resin_usd_m3' in pricing:
                # Convert USD/m³ to USD/ft³ for WaterTAP
                # 1 m³ = 35.3147 ft³
                resin_usd_ft3 = pricing['resin_usd_m3'] / 35.3147
                if self.model.fs.ix_unit.ion_exchange_type.value == 'cation':
                    if hasattr(m.fs.costing.ion_exchange, 'cation_exchange_resin_cost'):
                        m.fs.costing.ion_exchange.cation_exchange_resin_cost.set_value(
                            resin_usd_ft3
                        )
                else:
                    if hasattr(m.fs.costing.ion_exchange, 'anion_exchange_resin_cost'):
                        m.fs.costing.ion_exchange.anion_exchange_resin_cost.set_value(
                            resin_usd_ft3
                        )
    
    def _extract_costing_results(self) -> Dict[str, Any]:
        """Extract costing results from WaterTAP costing blocks."""
        m = self.model
        
        # Get total capital and operating costs from WaterTAP
        total_capital_cost = value(m.fs.costing.total_capital_cost) if hasattr(m.fs.costing, 'total_capital_cost') else 0
        total_operating_cost = value(m.fs.costing.total_operating_cost) if hasattr(m.fs.costing, 'total_operating_cost') else 0
        
        # Extract individual capital cost components from IX unit
        capital_cost_vessel = 0
        capital_cost_resin = 0
        capital_cost_backwash_tank = 0
        capital_cost_regen_tank = 0
        
        if hasattr(m.fs.ix_unit, 'costing'):
            # Get individual capital cost components from WaterTAP's cost_ion_exchange
            if hasattr(m.fs.ix_unit.costing, 'capital_cost_vessel'):
                capital_cost_vessel = value(m.fs.ix_unit.costing.capital_cost_vessel)
            if hasattr(m.fs.ix_unit.costing, 'capital_cost_resin'):
                capital_cost_resin = value(m.fs.ix_unit.costing.capital_cost_resin)
            if hasattr(m.fs.ix_unit.costing, 'capital_cost_backwash_tank'):
                capital_cost_backwash_tank = value(m.fs.ix_unit.costing.capital_cost_backwash_tank)
            if hasattr(m.fs.ix_unit.costing, 'capital_cost_regen_tank'):
                capital_cost_regen_tank = value(m.fs.ix_unit.costing.capital_cost_regen_tank)
        
        # Extract pump capital costs from pump units
        capital_cost_pumps = 0
        if hasattr(m.fs.service_pump, 'costing') and hasattr(m.fs.service_pump.costing, 'capital_cost'):
            capital_cost_pumps += value(m.fs.service_pump.costing.capital_cost)
        if hasattr(m.fs.backwash_pump, 'costing') and hasattr(m.fs.backwash_pump.costing, 'capital_cost'):
            capital_cost_pumps += value(m.fs.backwash_pump.costing.capital_cost)
        
        # Extract operating cost components
        # Regenerant cost - use WaterTAP's calculation if available
        regenerant_cost = 0
        if hasattr(m.fs.ix_unit.costing, 'flow_mass_regen_soln'):
            regen_flow_kg_s = value(m.fs.ix_unit.costing.flow_mass_regen_soln)
            # Use NaCl cost from WaterTAP costing block
            nacl_cost = value(m.fs.costing.nacl.cost) if hasattr(m.fs.costing, 'nacl') else 0.12
            regenerant_cost = regen_flow_kg_s * nacl_cost * 365 * 24 * 3600
        
        # Resin replacement - use WaterTAP's calculation if available
        resin_replacement_cost = 0
        if hasattr(m.fs.ix_unit.costing, 'annual_resin_replacement_cost'):
            resin_replacement_cost = value(m.fs.ix_unit.costing.annual_resin_replacement_cost)
        elif capital_cost_resin > 0:
            # WaterTAP default is 5% annual replacement
            resin_replacement_cost = capital_cost_resin * 0.05
        
        # Energy cost - calculate from pump power and WaterTAP electricity cost
        electricity_cost = value(m.fs.costing.electricity_cost) if hasattr(m.fs.costing, 'electricity_cost') else 0.07
        
        # Get pump power from pump units
        service_pump_power_kw = 0
        backwash_pump_power_kw = 0
        
        if hasattr(m.fs.service_pump, 'work_mechanical'):
            service_pump_power_kw = value(m.fs.service_pump.work_mechanical[0]) / 1000  # W to kW
        if hasattr(m.fs.backwash_pump, 'work_mechanical'):
            backwash_pump_power_kw = value(m.fs.backwash_pump.work_mechanical[0]) / 1000  # W to kW
        
        # Calculate time-weighted power (backwash is intermittent)
        # Service pump runs during service phase (t_breakthru/t_cycle fraction)
        # Backwash pump runs during backwash phase (t_bw/t_cycle fraction)
        t_breakthru = value(m.fs.ix_unit.t_breakthru) if hasattr(m.fs.ix_unit, 't_breakthru') else 43200  # 12 hrs default
        t_bw = value(m.fs.ix_unit.t_bw) if hasattr(m.fs.ix_unit, 't_bw') else 1800  # 0.5 hr default
        t_cycle = value(m.fs.ix_unit.t_cycle) if hasattr(m.fs.ix_unit, 't_cycle') else 50400  # 14 hrs default
        
        avg_pump_power_kw = (service_pump_power_kw * t_breakthru/t_cycle + 
                             backwash_pump_power_kw * t_bw/t_cycle)
        
        energy_cost = avg_pump_power_kw * 8760 * electricity_cost  # kW * hours/year * $/kWh
        
        # Calculate LCOW - use WaterTAP's value if available
        if hasattr(m.fs.costing, 'LCOW'):
            lcow = value(m.fs.costing.LCOW)
            crf = None  # WaterTAP handles CRF internally
            discount_rate = None
            plant_lifetime = None
        else:
            # Use schema parameters if provided, else defaults
            # CRF formula: r(1+r)^n / ((1+r)^n - 1)
            discount_rate = self.pricing.get('discount_rate', 0.08)
            plant_lifetime = self.pricing.get('plant_lifetime_years', 20)
            availability = self.pricing.get('availability', 0.9)

            if discount_rate <= 0:
                crf = 1.0 / plant_lifetime if plant_lifetime > 0 else 0.1
            else:
                crf = discount_rate * (1 + discount_rate) ** plant_lifetime / (
                    (1 + discount_rate) ** plant_lifetime - 1
                )

            flow_m3_year = value(m.fs.ix_unit.service_flow_rate) * 8760 * availability
            lcow = (total_capital_cost * crf + total_operating_cost) / flow_m3_year if flow_m3_year > 0 else 0
        
        # Calculate SEC (Specific Energy Consumption)
        service_flow = value(m.fs.ix_unit.service_flow_rate)
        sec = avg_pump_power_kw / service_flow if service_flow > 0 else 0.05
        
        return {
            'capital_cost_usd': total_capital_cost,
            'capital_cost_vessel': capital_cost_vessel,
            'capital_cost_resin': capital_cost_resin,
            'capital_cost_backwash_tank': capital_cost_backwash_tank,
            'capital_cost_pumps': capital_cost_pumps,
            'capital_cost_regen_tank': capital_cost_regen_tank,
            'operating_cost_usd_year': total_operating_cost,
            'regenerant_cost_usd_year': regenerant_cost,
            'resin_replacement_cost_usd_year': resin_replacement_cost,
            'energy_cost_usd_year': energy_cost,
            'lcow_usd_m3': lcow,
            'crf': crf,
            'discount_rate': discount_rate,
            'plant_lifetime_years': plant_lifetime,
            'sec_kwh_m3': sec,
            'pumping_power_kw': avg_pump_power_kw,
            'unit_costs': {
                'vessels_usd': capital_cost_vessel,
                'resin_initial_usd': capital_cost_resin,
                'backwash_tank_usd': capital_cost_backwash_tank,
                'regen_tank_usd': capital_cost_regen_tank,
                'pumps_usd': capital_cost_pumps,
                'installation_factor': None  # WaterTAP applies factors internally
            }
        }
    
    def get_stream_table(self) -> Dict[str, Any]:
        """Get inlet and outlet stream compositions."""
        if self.model is None:
            return {}
        
        m = self.model
        results = {
            'inlet': {},
            'outlet': {}
        }
        
        # Extract stream data
        for comp in m.fs.properties.solute_set:
            results['inlet'][comp] = value(
                m.fs.ix_unit.inlet.flow_mol_phase_comp[0, "Liq", comp]
            )
            results['outlet'][comp] = value(
                m.fs.ix_unit.outlet.flow_mol_phase_comp[0, "Liq", comp]
            )
        
        return results
