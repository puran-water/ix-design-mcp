"""
Ion Exchange Transport 0D Model with GrayBox Integration

This version uses the PHREEQC GrayBox model for proper integration
with IDAES/WaterTAP's optimization framework.
"""

from pyomo.environ import (
    Block,
    NonNegativeReals,
    Var,
    value,
    units as pyunits,
    Constraint,
    ConcreteModel,
    TransformationFactory,
    check_optimal_termination,
    assert_optimal_termination,
)
from pyomo.common.config import ConfigBlock, ConfigValue, In
from pyomo.util.calc_var_value import calculate_variable_from_constraint
from pyomo.network import Port, Arc

import idaes.core.util.exceptions as idaes_exceptions
import idaes.core.util.scaling as iscale
import idaes.logger as idaeslog
from idaes.core import (
    ControlVolume0DBlock,
    UnitModelBlockData,
    declare_process_block_class,
    MaterialBalanceType,
    MomentumBalanceType,
    useDefault,
    FlowsheetBlock,
)
from enum import Enum

class InitializationStatus(Enum):
    """Simple initialization status enum"""
    Ok = "optimal"
    Error = "error"
from idaes.core.solvers import get_solver
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.tables import create_stream_table_dataframe
from idaes.core.util.initialization import propagate_state

# Import the GrayBox model
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phreeqc_pse.blocks.phreeqc_ix_block import PhreeqcIXBlock

import logging

_log = idaeslog.getLogger(__name__)
init_log = idaeslog.getInitLogger(__name__, level=logging.INFO)

__author__ = "Hunter Barber, Xiangyu Bi, Kurban Sitterley"


@declare_process_block_class("IonExchangeTransport0D")
class IonExchangeTransport0DData(UnitModelBlockData):
    """
    0D Ion Exchange Transport Model using PHREEQC GrayBox Integration
    """

    CONFIG = ConfigBlock()
    
    CONFIG.declare("dynamic", ConfigValue(
        domain=In([False]),
        default=False,
        description="Dynamic model flag - must be False",
        doc="This is a steady-state model, dynamic=False",
    ))
    
    CONFIG.declare("has_holdup", ConfigValue(
        default=False,
        domain=In([False]),
        description="Holdup construction flag - must be False",
        doc="This is a 0D model, has_holdup=False",
    ))
    
    CONFIG.declare("property_package", ConfigValue(
        default=useDefault,
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="Property package instance for the control volume",
    ))
    
    CONFIG.declare("property_package_args", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="A ConfigBlock with arguments to be passed to a property block(s)",
    ))
    
    CONFIG.declare("material_balance_type", ConfigValue(
        default=MaterialBalanceType.useDefault,
        domain=In(MaterialBalanceType),
        description="Material balance construction flag",
        doc="Material balance type for the control volume",
    ))
    
    CONFIG.declare("momentum_balance_type", ConfigValue(
        default=MomentumBalanceType.pressureTotal,
        domain=In(MomentumBalanceType),
        description="Momentum balance construction flag",
        doc="Momentum balance type (default: pressureTotal)",
    ))
    
    CONFIG.declare("has_pressure_change", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Pressure change term construction flag",
        doc="Whether to include pressure change (default: False)",
    ))
    
    CONFIG.declare("resin_type", ConfigValue(
        default="SAC",
        domain=In(["SAC", "WAC_H", "WAC_Na"]),
        description="Type of ion exchange resin",
        doc="Resin type: SAC (strong acid cation), WAC_H (weak acid cation, H form), WAC_Na (weak acid cation, Na form)",
    ))
    
    CONFIG.declare("exchange_capacity", ConfigValue(
        default=2.0,
        domain=float,
        description="Ion exchange capacity (eq/L)",
        doc="Total exchange capacity of the resin",
    ))
    
    CONFIG.declare("column_parameters", ConfigValue(
        default={},
        domain=dict,
        description="Column design parameters",
        doc="Dictionary with bed_volume_m3, diameter_m, bed_depth_m, flow_rate_m3_hr",
    ))
    
    CONFIG.declare("include_breakthrough", ConfigValue(
        default=False,
        domain=bool,
        description="Include breakthrough calculations",
        doc="Whether to calculate breakthrough time",
    ))
    
    CONFIG.declare("use_direct_phreeqc", ConfigValue(
        default=True,
        domain=bool,
        description="Use DirectPhreeqcEngine",
        doc="Whether to use direct PHREEQC execution (recommended)",
    ))

    def build(self):
        """Build the ion exchange model with GrayBox integration"""
        super().build()
        
        # Create control volume
        self.control_volume = ControlVolume0DBlock(
            dynamic=False,
            has_holdup=False,
            property_package=self.config.property_package,
            property_package_args=self.config.property_package_args,
        )
        
        self.control_volume.add_state_blocks(has_phase_equilibrium=False)
        
        # Add material balances (no mass transfer - handled by GrayBox)
        self.control_volume.add_material_balances(
            balance_type=self.config.material_balance_type,
            has_mass_transfer=False
        )
        
        # Add momentum balances
        self.control_volume.add_momentum_balances(
            balance_type=self.config.momentum_balance_type,
            has_pressure_change=self.config.has_pressure_change
        )
        
        # Add ports
        self.add_inlet_port(name="inlet", block=self.control_volume)
        self.add_outlet_port(name="outlet", block=self.control_volume)
        
        # Determine target ions based on resin type
        if self.config.resin_type in ["SAC", "WAC_H", "WAC_Na"]:
            target_ions = ["Ca", "Mg"]
            regenerant_ion = "Na"
        else:
            raise ValueError(f"Unsupported resin type: {self.config.resin_type}")
        
        # Create PHREEQC GrayBox block
        self.phreeqc_ix = PhreeqcIXBlock(
            resin_type=self.config.resin_type,
            exchange_capacity=self.config.exchange_capacity,
            target_ions=target_ions,
            regenerant_ion=regenerant_ion,
            column_parameters=self.config.column_parameters,
            include_breakthrough=self.config.include_breakthrough,
            use_direct_phreeqc=self.config.use_direct_phreeqc,
        )
        
        # Link inlet state to GrayBox inputs
        self._create_inlet_links()
        
        # Link GrayBox outputs to outlet state
        self._create_outlet_links()
        
        # Add any additional constraints
        self._add_constraints()
        
        init_log.info("IonExchangeTransport0D with GrayBox integration built successfully")

    def _create_inlet_links(self):
        """Create constraints linking inlet state to GrayBox inputs"""
        
        @self.Constraint(self.flowsheet().time)
        def link_temperature_in(b, t):
            return b.phreeqc_ix.inputs.temperature == b.control_volume.properties_in[t].temperature
        
        @self.Constraint(self.flowsheet().time)
        def link_pressure_in(b, t):
            return b.phreeqc_ix.inputs.pressure == b.control_volume.properties_in[t].pressure
        
        # Component name mapping (MCAS uses charge notation)
        component_map = {
            'Ca_2+': 'Ca',
            'Mg_2+': 'Mg', 
            'Na_+': 'Na',
            'Cl_-': 'Cl',
            'SO4_2-': 'SO4',
            'HCO3_-': 'HCO3'
        }
        
        # Link component flows
        @self.Constraint(self.flowsheet().time, 
                        self.config.property_package.component_list)
        def link_flow_in(b, t, j):
            # Map component names
            phreeqc_name = component_map.get(j, j)
            if hasattr(b.phreeqc_ix.inputs, f"{phreeqc_name}_in"):
                return getattr(b.phreeqc_ix.inputs, f"{phreeqc_name}_in") == \
                       b.control_volume.properties_in[t].flow_mass_phase_comp['Liq', j]
            else:
                return Constraint.Skip
        
        # Calculate and link pH if available
        if hasattr(self.control_volume.properties_in[0], "pH"):
            @self.Constraint(self.flowsheet().time)
            def link_pH_in(b, t):
                return b.phreeqc_ix.inputs.pH == b.control_volume.properties_in[t].pH
        else:
            # Fix default pH
            self.phreeqc_ix.inputs.pH.fix(7.0)
        
        # Link column parameters if provided
        if self.config.column_parameters:
            if "bed_volume_m3" in self.config.column_parameters:
                self.phreeqc_ix.inputs.bed_volume.fix(
                    self.config.column_parameters["bed_volume_m3"]
                )
            if "flow_rate_m3_hr" in self.config.column_parameters:
                # Convert to m³/s
                flow_m3_s = self.config.column_parameters["flow_rate_m3_hr"] / 3600
                self.phreeqc_ix.inputs.flow_rate.fix(flow_m3_s)

    def _create_outlet_links(self):
        """Create constraints linking GrayBox outputs to outlet state"""
        
        # Component name mapping (MCAS uses charge notation)
        component_map = {
            'Ca_2+': 'Ca',
            'Mg_2+': 'Mg', 
            'Na_+': 'Na',
            'Cl_-': 'Cl',
            'SO4_2-': 'SO4',
            'HCO3_-': 'HCO3'
        }
        
        # Link component flows
        @self.Constraint(self.flowsheet().time, 
                        self.config.property_package.component_list)
        def link_flow_out(b, t, j):
            # Map component names
            phreeqc_name = component_map.get(j, j)
            if hasattr(b.phreeqc_ix.outputs, f"{phreeqc_name}_out"):
                return b.control_volume.properties_out[t].flow_mass_phase_comp['Liq', j] == \
                       getattr(b.phreeqc_ix.outputs, f"{phreeqc_name}_out")
            else:
                # For components not handled by PHREEQC (like H2O), pass through
                return b.control_volume.properties_out[t].flow_mass_phase_comp['Liq', j] == \
                       b.control_volume.properties_in[t].flow_mass_phase_comp['Liq', j]
        
        # Temperature and pressure pass through (no change in IX)
        @self.Constraint(self.flowsheet().time)
        def eq_temperature_out(b, t):
            return b.control_volume.properties_out[t].temperature == \
                   b.control_volume.properties_in[t].temperature
        
        @self.Constraint(self.flowsheet().time)
        def eq_pressure_out(b, t):
            return b.control_volume.properties_out[t].pressure == \
                   b.control_volume.properties_in[t].pressure
        
        # Link pH if available
        if hasattr(self.phreeqc_ix.outputs, "pH_out") and \
           hasattr(self.control_volume.properties_out[0], "pH"):
            @self.Constraint(self.flowsheet().time)
            def link_pH_out(b, t):
                return b.control_volume.properties_out[t].pH == b.phreeqc_ix.outputs.pH_out

    def _add_constraints(self):
        """Add any additional constraints"""
        
        # Material balance is handled by the GrayBox model
        # The control volume material balance should be satisfied automatically
        # through the inlet/outlet links
        
        # Add performance tracking variables
        self.hardness_removal_fraction = Var(
            self.flowsheet().time,
            bounds=(0, 1),
            initialize=0.9,
            doc="Fraction of hardness removed"
        )
        
        @self.Constraint(self.flowsheet().time)
        def eq_hardness_removal_fraction(b, t):
            if hasattr(b.phreeqc_ix, "hardness_removal_percent"):
                return b.hardness_removal_fraction[t] == b.phreeqc_ix.hardness_removal_percent / 100
            else:
                return b.hardness_removal_fraction[t] == 0.9  # Default

    def initialize_build(
        self,
        state_args=None,
        outlvl=idaeslog.NOTSET,
        solver=None,
        optarg=None,
    ):
        """
        Initialize the ion exchange unit with GrayBox
        
        Args:
            state_args: Initial state for property initialization
            outlvl: Output level for logging
            solver: Solver to use for initialization
            optarg: Solver options
        """
        init_log = idaeslog.getInitLogger(self.name, outlvl, tag="unit")
        solve_log = idaeslog.getSolveLogger(self.name, outlvl, tag="unit")
        
        if solver is None:
            solver = get_solver()
        
        # Initialize inlet state block
        self.control_volume.properties_in.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            state_args=state_args,
        )
        
        init_log.info("Inlet properties initialized")
        
        # Initialize outlet state block
        if state_args is None:
            state_args_out = {}
        else:
            state_args_out = state_args.copy()
        
        self.control_volume.properties_out.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            state_args=state_args_out,
        )
        
        init_log.info("Outlet properties initialized")
        
        # Initialize the GrayBox model
        init_log.info("Initializing PHREEQC GrayBox model...")
        self.phreeqc_ix.initialize_build()
        
        # Solve the integrated model
        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = solver.solve(self, tee=slc.tee)
        
        init_log.info(f"Initialization complete: {res.solver.termination_condition}")
        
        if check_optimal_termination(res):
            return InitializationStatus.Ok
        else:
            return InitializationStatus.Error

    def calculate_scaling_factors(self):
        """Calculate scaling factors for the ion exchange unit"""
        super().calculate_scaling_factors()
        
        # Scale the GrayBox block
        if hasattr(self.phreeqc_ix, "calculate_scaling_factors"):
            self.phreeqc_ix.calculate_scaling_factors()

    def _get_performance_contents(self, time_point=0):
        """Get performance metrics for reporting"""
        var_dict = {}
        
        # Get hardness removal
        var_dict["Hardness Removal (%)"] = value(
            self.hardness_removal_fraction[time_point] * 100
        )
        
        # Get breakthrough time if available
        if hasattr(self.phreeqc_ix.outputs, "breakthrough_time"):
            var_dict["Breakthrough Time (hr)"] = value(
                self.phreeqc_ix.outputs.breakthrough_time
            )
        
        # Get resin utilization if available
        if hasattr(self.phreeqc_ix, "resin_utilization"):
            var_dict["Resin Utilization (%)"] = value(
                self.phreeqc_ix.resin_utilization * 100
            )
        
        return {"vars": var_dict}

    def _get_stream_table_contents(self, time_point=0):
        """Get stream table contents for reporting"""
        return create_stream_table_dataframe(
            {
                "Inlet": self.inlet,
                "Outlet": self.outlet,
            },
            time_point=time_point,
        )

    def report(self, time_point=0, dof=False, ostream=None, prefix=""):
        """Generate unit operation report"""
        if ostream is None:
            ostream = sys.stdout
        
        # Get stream table
        stream_table = self._get_stream_table_contents(time_point=time_point)
        
        # Print unit header
        ostream.write(f"\n{prefix}Unit : {self.name}\n")
        if dof:
            ostream.write(f"{prefix}Degrees of Freedom: {degrees_of_freedom(self)}\n")
        ostream.write(f"\n{prefix}Stream Table\n")
        ostream.write(stream_table.to_string(index=True))
        ostream.write("\n")
        
        # Print performance metrics
        perf_dict = self._get_performance_contents(time_point=time_point)
        if perf_dict["vars"]:
            ostream.write(f"\n{prefix}Performance Metrics\n")
            ostream.write(f"{prefix}{'-'*50}\n")
            for k, v in perf_dict["vars"].items():
                ostream.write(f"{prefix}{k}: {v:.2f}\n")
        
        # Call the GrayBox report
        ostream.write(f"\n{prefix}PHREEQC Ion Exchange Details\n")
        ostream.write(f"{prefix}{'-'*50}\n")
        self.phreeqc_ix.report(stream=lambda msg: ostream.write(f"{prefix}{msg}\n"))