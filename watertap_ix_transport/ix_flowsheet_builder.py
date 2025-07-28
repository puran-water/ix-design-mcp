"""
Ion Exchange flowsheet building utilities for WaterTAP models.

This module provides functions to build complete IX flowsheets with pumps,
similar to the RO flowsheet builder.
"""

import logging
from typing import Dict, Any, Optional
from pyomo.environ import (
    ConcreteModel, 
    Constraint, 
    value, 
    units as pyunits,
    Var,
    NonNegativeReals
)
from pyomo.network import Arc
from idaes.core import FlowsheetBlock
from idaes.models.unit_models import Feed, Product
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.solvers import get_solver
from idaes.core.util.initialization import propagate_state
from idaes.core.base.costing_base import UnitModelCostingBlock
from watertap.unit_models.pressure_changer import Pump
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis

# Import local IX model
from .ion_exchange_transport_0D import IonExchangeTransport0D, ResinType, RegenerantChem

logger = logging.getLogger(__name__)


def build_ix_flowsheet(
    feed_composition: Dict[str, float],
    flow_rate_m3h: float = 100.0,
    temperature_c: float = 25.0,
    resin_type: ResinType = ResinType.SAC,
    regenerant: RegenerantChem = RegenerantChem.NaCl,
    number_of_beds: int = 2,
    bed_depth_m: float = 2.0,
    bed_diameter_m: float = 2.0,
    target_hardness_removal: float = 0.9,
    include_feed_pump: bool = True,
    feed_pressure_bar: float = 4.0,  # Typical IX operating pressure
) -> ConcreteModel:
    """
    Build a complete ion exchange flowsheet with optional feed pump.
    
    Args:
        feed_composition: Ion concentrations in mg/L (e.g., {'Ca2+': 100, 'Mg2+': 50, ...})
        flow_rate_m3h: Feed flow rate in m³/hr
        temperature_c: Feed temperature in °C
        resin_type: Type of IX resin (SAC, WAC_H, WAC_Na)
        regenerant: Regenerant chemical
        number_of_beds: Number of IX beds in parallel
        bed_depth_m: Depth of each bed
        bed_diameter_m: Diameter of each bed
        target_hardness_removal: Target removal fraction for hardness ions
        include_feed_pump: Whether to include a feed pump
        feed_pressure_bar: Feed pressure if pump is included
    
    Returns:
        Pyomo ConcreteModel with complete IX flowsheet
    """
    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Build MCAS property configuration from feed composition
    solute_list = list(feed_composition.keys())
    if 'H2O' in solute_list:
        solute_list.remove('H2O')
    
    # Create MCAS property package with mass basis
    m.fs.properties = MCASParameterBlock(
        solute_list=solute_list,
        material_flow_basis=MaterialFlowBasis.mass
    )
    
    # Calculate feed mass flows
    flow_rate_m3s = flow_rate_m3h / 3600  # Convert to m³/s
    
    # Estimate density (simplified - could be improved)
    tds_mg_L = sum(feed_composition.values())
    density_kg_m3 = 1000 + tds_mg_L / 1000  # Rough approximation
    
    total_mass_flow = flow_rate_m3s * density_kg_m3  # kg/s
    
    # Calculate component mass flows
    flow_mass_comp = {}
    for comp, conc_mg_L in feed_composition.items():
        # Convert mg/L to kg/s
        # mass_flow = conc (mg/L) * flow (m³/s) * 1e-6 (kg/mg)
        mass_flow_kg_s = conc_mg_L * flow_rate_m3s * 1e-6
        flow_mass_comp[('Liq', comp)] = mass_flow_kg_s
    
    # Calculate water flow
    solute_mass_flow = sum(flow_mass_comp.values())
    flow_mass_comp[('Liq', 'H2O')] = total_mass_flow - solute_mass_flow
    
    # Create feed
    m.fs.feed = Feed(property_package=m.fs.properties)
    
    # Create feed pump if requested
    if include_feed_pump:
        m.fs.feed_pump = Pump(property_package=m.fs.properties)
        m.fs.feed_to_pump = Arc(source=m.fs.feed.outlet, destination=m.fs.feed_pump.inlet)
        
        # Create IX unit
        m.fs.ix_unit = IonExchangeTransport0D(
            property_package=m.fs.properties,
            resin_type=resin_type,
            regenerant=regenerant,
            number_of_beds=number_of_beds
        )
        
        m.fs.pump_to_ix = Arc(source=m.fs.feed_pump.outlet, destination=m.fs.ix_unit.inlet)
    else:
        # Direct connection without pump
        m.fs.ix_unit = IonExchangeTransport0D(
            property_package=m.fs.properties,
            resin_type=resin_type,
            regenerant=regenerant,
            number_of_beds=number_of_beds
        )
        
        m.fs.feed_to_ix = Arc(source=m.fs.feed.outlet, destination=m.fs.ix_unit.inlet)
    
    # Create product streams
    m.fs.treated_water = Product(property_package=m.fs.properties)
    m.fs.ix_to_product = Arc(source=m.fs.ix_unit.outlet, destination=m.fs.treated_water.inlet)
    
    # Create regeneration waste stream if not single-use
    if regenerant != RegenerantChem.single_use:
        m.fs.regen_waste = Product(property_package=m.fs.properties)
        m.fs.ix_to_regen = Arc(source=m.fs.ix_unit.regen_outlet, destination=m.fs.regen_waste.inlet)
    
    # Set feed conditions
    m.fs.feed.outlet.temperature[0].fix(temperature_c + 273.15)  # Convert to K
    m.fs.feed.outlet.pressure[0].fix(101325)  # 1 atm
    
    for comp_phase, flow in flow_mass_comp.items():
        m.fs.feed.outlet.flow_mass_phase_comp[0, comp_phase[0], comp_phase[1]].fix(flow)
    
    # Assert electroneutrality for multi-ion systems
    if len(solute_list) > 2:  # More than just Na+/Cl-
        try:
            # Use Cl- as adjustment ion if present
            if 'Cl_-' in solute_list:
                m.fs.feed.properties[0].assert_electroneutrality(
                    defined_state=True,
                    adjust_by_ion='Cl_-',
                    tol=1e-8
                )
                logger.info("Asserted electroneutrality by adjusting Cl_-")
            elif 'Na_+' in solute_list:
                # Use Na+ as adjustment ion
                m.fs.feed.properties[0].assert_electroneutrality(
                    defined_state=True,
                    adjust_by_ion='Na_+',
                    tol=1e-8
                )
                logger.info("Asserted electroneutrality by adjusting Na_+")
        except Exception as e:
            logger.warning(f"Could not assert electroneutrality: {e}")
    
    # Set IX unit parameters
    m.fs.ix_unit.bed_depth.set_value(bed_depth_m)
    m.fs.ix_unit.bed_diameter.set_value(bed_diameter_m)
    
    # Fix operating capacity based on target removal
    m.fs.ix_unit.operating_capacity.fix(target_hardness_removal)
    
    # Set pump parameters if included
    if include_feed_pump:
        m.fs.feed_pump.outlet.pressure[0].fix(feed_pressure_bar * 1e5)  # Convert to Pa
        m.fs.feed_pump.efficiency_pump.fix(0.8)
    
    # Expand arcs to create connections
    from pyomo.environ import TransformationFactory
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    logger.info(f"Built IX flowsheet with {number_of_beds} beds, "
                f"treating {flow_rate_m3h} m³/hr")
    
    return m


def initialize_ix_flowsheet(
    model: ConcreteModel,
    verbose: bool = True
) -> None:
    """
    Initialize an IX flowsheet with proper sequencing.
    
    Args:
        model: IX flowsheet model to initialize
        verbose: Print detailed initialization info
    """
    import idaes.logger as idaeslog
    from idaes.core.util.initialization import propagate_state
    
    if verbose:
        logger.info("Initializing IX flowsheet...")
    
    # Initialize feed
    model.fs.feed.initialize(outlvl=idaeslog.NOTSET)
    
    # Ensure feed properties are calculated correctly (especially mole fractions)
    from .utilities.property_calculations import fix_mole_fractions
    feed_state = model.fs.feed.properties[0]
    fix_mole_fractions(feed_state)
    
    # Verify water mole fraction
    water_mol_frac = value(feed_state.mole_frac_phase_comp['Liq', 'H2O'])
    if water_mol_frac < 0.95:
        logger.warning(f"Feed water mole fraction ({water_mol_frac:.4f}) is too low for IX model")
    
    if hasattr(model.fs, 'feed_pump'):
        # Propagate to pump
        propagate_state(model.fs.feed_to_pump)
        
        # Initialize pump
        model.fs.feed_pump.initialize(outlvl=idaeslog.NOTSET)
        
        # Propagate to IX
        propagate_state(model.fs.pump_to_ix)
        
        # After propagation, ensure IX inlet properties are calculated
        ix_inlet = model.fs.ix_unit.control_volume.properties_in[0]
        
        # Calculate molar flows and mole fractions for IX inlet
        fix_mole_fractions(ix_inlet)
        
        # Log water mole fraction after calculation
        water_mol_frac = value(ix_inlet.mole_frac_phase_comp['Liq', 'H2O'])
        logger.info(f"IX inlet water mole fraction after constraint calculation: {water_mol_frac:.6f}")
    else:
        # Direct propagation to IX
        propagate_state(model.fs.feed_to_ix)
    
    # After propagation, ensure IX inlet properties are calculated
    # This is needed because propagate_state only copies fixed variables
    ix_inlet = model.fs.ix_unit.control_volume.properties_in[0]
    
    # Calculate molar flows and mole fractions for IX inlet
    # Simply touch the constraints to ensure they're evaluated
    if hasattr(ix_inlet, 'eq_flow_mol_phase_comp'):
        for comp in model.fs.properties.component_list:
            idx = ('Liq', comp)
            if idx in ix_inlet.eq_flow_mol_phase_comp:
                # Touch the constraint to ensure it's evaluated
                _ = value(ix_inlet.eq_flow_mol_phase_comp[idx])
    
    if hasattr(ix_inlet, 'eq_mole_frac_phase_comp'):
        for comp in model.fs.properties.component_list:
            idx = ('Liq', comp)
            if idx in ix_inlet.eq_mole_frac_phase_comp:
                # Touch the constraint to ensure it's evaluated
                _ = value(ix_inlet.eq_mole_frac_phase_comp[idx])
    
    # Log water mole fraction after calculation
    water_mol_frac = value(ix_inlet.mole_frac_phase_comp['Liq', 'H2O'])
    logger.info(f"IX inlet water mole fraction after constraint calculation: {water_mol_frac:.6f}")
    
    # Initialize IX unit - it has its own sophisticated initialization
    model.fs.ix_unit.initialize(outlvl=idaeslog.NOTSET)
    
    # Propagate to products
    propagate_state(model.fs.ix_to_product)
    model.fs.treated_water.initialize(outlvl=idaeslog.NOTSET)
    
    if hasattr(model.fs, 'regen_waste'):
        propagate_state(model.fs.ix_to_regen)
        model.fs.regen_waste.initialize(outlvl=idaeslog.NOTSET)
    
    # Check degrees of freedom
    dof = degrees_of_freedom(model)
    if verbose:
        logger.info(f"Degrees of freedom after initialization: {dof}")
    
    if dof != 0:
        logger.warning(f"Model has {dof} degrees of freedom - may need additional specifications")


def add_costing_to_flowsheet(model, 
                           vessel_material="FRP",
                           include_resin=True,
                           instrumentation_level="basic"):
    """
    Add costing to an IX flowsheet.
    
    Args:
        model: Flowsheet model
        vessel_material: Vessel material (FRP, RubberLinedSteel, etc.)
        include_resin: Whether to include initial resin cost
        instrumentation_level: "basic" or "advanced"
    """
    from idaes.models.costing.base import FlowsheetCostingBlock
    from .costing import (
        build_ix_costing_param_block,
        cost_ion_exchange,
        cost_feed_pump,
        VesselMaterial
    )
    
    # Create flowsheet costing block
    model.fs.costing = FlowsheetCostingBlock(
        flowsheet_costing_block=model.fs,
        costing_blocks={
            "ion_exchange": build_ix_costing_param_block
        }
    )
    
    # Convert string to enum
    if isinstance(vessel_material, str):
        vessel_material = VesselMaterial[vessel_material]
    
    # Cost IX unit
    if hasattr(model.fs, 'ix_unit'):
        model.fs.ix_unit.costing = UnitModelCostingBlock(
            flowsheet_costing_block=model.fs.costing
        )
        
        cost_ion_exchange(
            model.fs.ix_unit.costing,
            model.fs.ix_unit,
            vessel_material=vessel_material,
            include_resin=include_resin,
            instrumentation_level=instrumentation_level
        )
    
    # Cost feed pump if present
    if hasattr(model.fs, 'feed_pump'):
        model.fs.feed_pump.costing = UnitModelCostingBlock(
            flowsheet_costing_block=model.fs.costing
        )
        
        cost_feed_pump(
            model.fs.feed_pump.costing,
            model.fs.feed_pump
        )
    
    # Calculate total costs
    model.fs.costing.cost_process()
    
    return model