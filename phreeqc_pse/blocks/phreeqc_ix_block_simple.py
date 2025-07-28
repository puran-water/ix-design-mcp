"""
Simple PHREEQC Ion Exchange Block
A simplified implementation that works directly with DirectPhreeqcEngine
"""

from pyomo.environ import (
    Block, Var, Constraint, Param, Set as PyomoSet, Expression,
    Reference, units as pyunits, value, exp, log
)
from pyomo.common.config import ConfigBlock, ConfigValue, In
from idaes.core import declare_process_block_class, ProcessBlockData
from idaes.core.util.initialization import fix_state_vars, revert_state_vars
import idaes.logger as idaeslog

from watertap_ix_transport.transport_core.direct_phreeqc_engine import DirectPhreeqcEngine

import logging

logger = logging.getLogger(__name__)
init_logger = idaeslog.getInitLogger(__name__)


@declare_process_block_class("PhreeqcIXBlockSimple")
class PhreeqcIXBlockSimpleData(ProcessBlockData):
    """
    Simple PHREEQC Ion Exchange Block for direct use
    
    This block directly calls DirectPhreeqcEngine for ion exchange calculations
    without the complexity of the full GrayBox infrastructure.
    """
    
    CONFIG = ConfigBlock()
    
    CONFIG.declare("resin_type", ConfigValue(
        default="SAC",
        domain=In(["SAC", "WAC_H", "WAC_Na"]),
        description="Type of ion exchange resin"
    ))
    
    CONFIG.declare("exchange_capacity", ConfigValue(
        default=2.0,
        domain=float,
        description="Ion exchange capacity (eq/L)"
    ))
    
    CONFIG.declare("target_ions", ConfigValue(
        default=["Ca", "Mg"],
        domain=list,
        description="List of target ions for removal"
    ))
    
    CONFIG.declare("regenerant_ion", ConfigValue(
        default="Na",
        domain=str,
        description="Regenerant ion"
    ))
    
    CONFIG.declare("column_parameters", ConfigValue(
        default={},
        domain=dict,
        description="Column design parameters"
    ))
    
    def build(self):
        """
        Build the simplified ion exchange block
        """
        super().build()
        
        # Create DirectPhreeqcEngine
        self.phreeqc_engine = DirectPhreeqcEngine()
        
        # Define components
        self.component_list = PyomoSet(
            initialize=['Ca', 'Mg', 'Na', 'Cl', 'SO4', 'HCO3']
        )
        
        # Create input variables (kg/s)
        self.inputs = Block()
        
        # Flow inputs for each component
        for comp in self.component_list:
            var = Var(
                initialize=0.001,
                bounds=(0, None),
                units=pyunits.kg/pyunits.s,
                doc=f"{comp} inlet flow"
            )
            setattr(self.inputs, f"{comp}_in", var)
        
        # System inputs
        self.inputs.temperature = Var(
            initialize=298.15,
            bounds=(273, 373),
            units=pyunits.K,
            doc="Temperature"
        )
        
        self.inputs.pressure = Var(
            initialize=101325,
            bounds=(50000, 1000000),
            units=pyunits.Pa,
            doc="Pressure"
        )
        
        self.inputs.pH = Var(
            initialize=7.0,
            bounds=(0, 14),
            units=pyunits.dimensionless,
            doc="pH"
        )
        
        self.inputs.flow_rate = Var(
            initialize=0.001,
            bounds=(0, None),
            units=pyunits.m**3/pyunits.s,
            doc="Volumetric flow rate"
        )
        
        self.inputs.bed_volume = Var(
            initialize=1.0,
            bounds=(0.1, 100),
            units=pyunits.m**3,
            doc="Bed volume"
        )
        
        # Create output variables (kg/s)
        self.outputs = Block()
        
        # Flow outputs for each component
        for comp in self.component_list:
            var = Var(
                initialize=0.001,
                bounds=(0, None),
                units=pyunits.kg/pyunits.s,
                doc=f"{comp} outlet flow"
            )
            setattr(self.outputs, f"{comp}_out", var)
        
        # System outputs
        self.outputs.pH = Var(
            initialize=7.0,
            bounds=(0, 14),
            units=pyunits.dimensionless,
            doc="Outlet pH"
        )
        
        self.outputs.ionic_strength = Var(
            initialize=0.01,
            bounds=(0, None),
            units=pyunits.mol/pyunits.L,
            doc="Ionic strength"
        )
        
        # Performance outputs
        self.outputs.breakthrough_time = Var(
            initialize=24,
            bounds=(0, None),
            units=pyunits.hour,
            doc="Breakthrough time"
        )
        
        # Add constraints that enforce PHREEQC equilibrium
        @self.Constraint(self.component_list)
        def phreeqc_equilibrium(b, comp):
            # This constraint will be updated by solve_phreeqc
            return getattr(b.outputs, f"{comp}_out") == getattr(b.inputs, f"{comp}_in")
        
        # Add performance metrics
        self._add_performance_metrics()
        
        logger.info(f"PhreeqcIXBlockSimple built for {self.config.resin_type} resin")
    
    def _add_performance_metrics(self):
        """Add IX performance metrics"""
        
        # Hardness calculations
        @self.Expression()
        def hardness_in(b):
            mw_caco3 = 100.09  # g/mol
            hardness = 0
            if hasattr(b.inputs, 'Ca_in'):
                hardness += b.inputs.Ca_in * mw_caco3 / 40.08
            if hasattr(b.inputs, 'Mg_in'):
                hardness += b.inputs.Mg_in * mw_caco3 / 24.31
            return hardness
        
        @self.Expression()
        def hardness_out(b):
            mw_caco3 = 100.09  # g/mol
            hardness = 0
            if hasattr(b.outputs, 'Ca_out'):
                hardness += b.outputs.Ca_out * mw_caco3 / 40.08
            if hasattr(b.outputs, 'Mg_out'):
                hardness += b.outputs.Mg_out * mw_caco3 / 24.31
            return hardness
        
        @self.Expression()
        def hardness_removal_percent(b):
            if value(b.hardness_in) > 0:
                return (b.hardness_in - b.hardness_out) / b.hardness_in * 100
            else:
                return 0
        
        # Bed volumes to breakthrough
        @self.Expression()
        def bed_volumes_to_breakthrough(b):
            if value(b.inputs.bed_volume) > 0 and value(b.inputs.flow_rate) > 0:
                return (b.outputs.breakthrough_time * 3600 * b.inputs.flow_rate) / b.inputs.bed_volume
            else:
                return 100  # Default
    
    def solve_phreeqc(self):
        """
        Call DirectPhreeqcEngine to solve ion exchange equilibrium
        """
        # Get current input values
        T_K = value(self.inputs.temperature)
        P_Pa = value(self.inputs.pressure)
        pH = value(self.inputs.pH)
        flow_m3_s = value(self.inputs.flow_rate)
        
        # Convert component flows to concentrations (mg/L)
        feed_composition = {
            'temperature': T_K - 273.15,  # °C
            'pH': pH
        }
        
        # Component molecular weights (g/mol)
        mw = {'Ca': 40.08, 'Mg': 24.31, 'Na': 22.99, 'Cl': 35.45, 'SO4': 96.06, 'HCO3': 61.02}
        
        for comp in self.component_list:
            if comp in mw:
                flow_kg_s = value(getattr(self.inputs, f"{comp}_in"))
                conc_mg_L = flow_kg_s / flow_m3_s * 1000  # mg/L
                feed_composition[comp] = conc_mg_L
        
        # Get resin parameters
        resin_map = {
            'SAC': ('Na', 2.0),
            'WAC_H': ('H', 4.0),
            'WAC_Na': ('Na', 3.5)
        }
        exchange_form, capacity = resin_map[self.config.resin_type]
        
        # Build PHREEQC input for equilibrium calculation
        phreeqc_input = f"""
SOLUTION 1
    temp      {feed_composition['temperature']}
    pH        {feed_composition['pH']}
    units     mg/L
"""
        
        # Calculate charge balance to determine which ion needs CHARGE keyword
        # Simple charge balance calculation
        cation_charge = 0
        anion_charge = 0
        
        # Molecular weights and charges
        ion_data = {
            'Ca': (40.08, 2), 'Mg': (24.31, 2), 'Na': (22.99, 1),
            'Cl': (35.45, -1), 'SO4': (96.06, -2), 'HCO3': (61.02, -1)
        }
        
        for comp, conc in feed_composition.items():
            if comp in ion_data and conc > 0:
                mw, charge = ion_data[comp]
                meq_L = conc / mw * abs(charge)
                if charge > 0:
                    cation_charge += meq_L
                else:
                    anion_charge += meq_L
        
        # Determine which ion to balance on
        charge_imbalance = cation_charge - anion_charge
        if abs(charge_imbalance) > 0.1:
            if charge_imbalance > 0:  # Need more anions
                balance_ion = 'Cl'
                logger.info(f"Using Cl for charge balance (imbalance: +{charge_imbalance:.1f} meq/L)")
            else:  # Need more cations
                balance_ion = 'Na'
                logger.info(f"Using Na for charge balance (imbalance: {charge_imbalance:.1f} meq/L)")
        else:
            balance_ion = None
        
        # Add components with CHARGE keyword as needed
        for comp, conc in feed_composition.items():
            if comp not in ['temperature', 'pH'] and conc > 0:
                if comp == balance_ion:
                    phreeqc_input += f"    {comp}        {conc} charge\n"
                else:
                    phreeqc_input += f"    {comp}        {conc}\n"
        
        phreeqc_input += f"""
EXCHANGE 1
    {exchange_form}X    {capacity}
    -equilibrate 1
SELECTED_OUTPUT 1
    -file transport.sel
    -reset false
    -solution true
    -pH true
    -molalities Ca+2 Mg+2 Na+ Cl- SO4-2 HCO3- CaX2 MgX2 NaX
END
"""
        
        # Run PHREEQC
        try:
            output, selected_output = self.phreeqc_engine.run_phreeqc(phreeqc_input)
            
            # Debug output
            logger.debug(f"PHREEQC output length: {len(output)}")
            logger.debug(f"Selected output length: {len(selected_output)}")
            
            # Parse selected output
            data = self.phreeqc_engine.parse_selected_output(selected_output)
            
            if not data:
                logger.error("PHREEQC output:")
                logger.error(output[:1000])  # First 1000 chars
                raise RuntimeError("No data returned from PHREEQC")
                
            # Get the last row (equilibrium state)
            results = data[-1]
            
            # Update output variables based on molalities
            # Map molality keys to components
            molality_map = {
                'm_Ca+2': 'Ca',
                'm_Mg+2': 'Mg', 
                'm_Na+': 'Na',
                'm_Cl-': 'Cl',
                'm_SO4-2': 'SO4',
                'm_HCO3-': 'HCO3'
            }
            
            # Molecular weights (g/mol)
            mw = {'Ca': 40.08, 'Mg': 24.31, 'Na': 22.99, 'Cl': 35.45, 'SO4': 96.06, 'HCO3': 61.02}
            
            for mol_key, comp in molality_map.items():
                if mol_key in results:
                    molality = results[mol_key]  # mol/kg H2O
                    # Convert to mg/L (assume density ~1 kg/L)
                    conc_mg_L = molality * mw[comp] * 1000
                    flow_kg_s = conc_mg_L * flow_m3_s / 1000
                    getattr(self.outputs, f"{comp}_out").set_value(flow_kg_s)
                else:
                    # Keep same as inlet if not in results
                    inlet_flow = value(getattr(self.inputs, f"{comp}_in"))
                    getattr(self.outputs, f"{comp}_out").set_value(inlet_flow)
            
            # Update pH
            if 'pH' in results:
                self.outputs.pH.set_value(results['pH'])
            
            # Calculate breakthrough (simplified)
            bed_volume = value(self.inputs.bed_volume)
            capacity_eq = capacity * bed_volume * 1000  # eq total
            
            # Calculate hardness loading
            ca_removed = value(self.inputs.Ca_in - self.outputs.Ca_out)  # kg/s
            mg_removed = value(self.inputs.Mg_in - self.outputs.Mg_out)  # kg/s
            
            ca_eq_s = ca_removed / 0.02004  # eq/s (Ca MW/2)
            mg_eq_s = mg_removed / 0.01215  # eq/s (Mg MW/2) 
            total_eq_s = ca_eq_s + mg_eq_s
            
            if total_eq_s > 0:
                breakthrough_s = capacity_eq / total_eq_s
                breakthrough_hr = breakthrough_s / 3600
                self.outputs.breakthrough_time.set_value(breakthrough_hr)
            
            # Fix output variables to enforce equilibrium
            for comp in self.component_list:
                getattr(self.outputs, f"{comp}_out").fix()
            self.outputs.pH.fix()
            
            logger.info(f"PHREEQC equilibrium solved: {value(self.hardness_removal_percent):.1f}% hardness removal")
            
        except Exception as e:
            logger.error(f"Error in PHREEQC calculation: {e}")
            raise
    
    def initialize_build(self, state_args=None, outlvl=idaeslog.NOTSET,
                        solver=None, optarg=None):
        """
        Custom initialization with PHREEQC
        """
        init_log = idaeslog.getInitLogger(self.name, outlvl, tag="unit")
        
        # Store which variables were fixed
        fixed_vars = []
        for var in self.inputs.component_objects(Var, descend_into=True):
            if var.fixed:
                fixed_vars.append((var, True))
            else:
                var.fix()
                fixed_vars.append((var, False))
        
        # Solve PHREEQC equilibrium
        init_log.info("Solving PHREEQC equilibrium...")
        self.solve_phreeqc()
        
        # Revert fixed status
        for var, was_fixed in fixed_vars:
            if not was_fixed:
                var.unfix()
        
        init_log.info("Initialization complete.")
    
    def report(self, index=0):
        """Generate performance report"""
        print("=" * 60)
        print(f"Ion Exchange Block Report ({self.config.resin_type})")
        print("=" * 60)
        
        print("\nSystem Conditions:")
        print(f"  Temperature: {value(self.inputs.temperature):.1f} K")
        print(f"  Flow rate: {value(self.inputs.flow_rate)*3600:.1f} m³/hr")
        print(f"  pH: {value(self.inputs.pH):.2f}")
        
        print("\nPerformance:")
        print(f"  Hardness In: {value(self.hardness_in)*1000:.1f} g/s as CaCO3")
        print(f"  Hardness Out: {value(self.hardness_out)*1000:.1f} g/s as CaCO3")
        print(f"  Hardness Removal: {value(self.hardness_removal_percent):.1f}%")
        print(f"  Breakthrough: {value(self.outputs.breakthrough_time):.1f} hours")
        print(f"  Bed volumes: {value(self.bed_volumes_to_breakthrough):.0f} BV")
        
        print("=" * 60)