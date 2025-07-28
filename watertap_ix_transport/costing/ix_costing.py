"""
Ion Exchange System Costing Module

This module provides costing functions for ion exchange equipment including:
- IX vessels and internals
- Resin costs
- Pumps and piping
- Instrumentation
- Installation factors
"""

from pyomo.environ import (
    Var, Param, Constraint, Expression,
    units as pyunits, exp, log
)
from idaes.core.util.misc import StrEnum
from idaes.core.base.costing_base import (
    register_costing_parameter_block,
    make_capital_cost_var
)
import idaes.core.util.scaling as iscale


class VesselMaterial(StrEnum):
    """Vessel material options"""
    FRP = "FRP"  # Fiberglass reinforced plastic
    RubberLinedSteel = "RubberLinedSteel"
    StainlessSteel = "StainlessSteel"
    CarbonSteel = "CarbonSteel"


def build_ix_costing_param_block(blk):
    """
    Build ion exchange costing parameter block.
    
    Contains cost factors and parameters for IX equipment.
    """
    # Vessel cost parameters (2023 USD basis)
    blk.vessel_cost_per_m3 = Param(
        default=15000,  # $/m³ for FRP vessels
        units=pyunits.USD_2023 / pyunits.m**3,
        doc="Base cost per cubic meter of vessel volume"
    )
    
    # Material cost factors relative to FRP
    blk.material_factor = Param(
        VesselMaterial,
        default={
            VesselMaterial.FRP: 1.0,
            VesselMaterial.RubberLinedSteel: 1.5,
            VesselMaterial.StainlessSteel: 2.5,
            VesselMaterial.CarbonSteel: 1.2
        },
        doc="Cost multiplier for vessel materials"
    )
    
    # Resin costs ($/m³)
    blk.resin_cost_per_m3 = Param(
        default={
            "SAC": 2000,  # Strong acid cation
            "WAC_H": 3500,  # Weak acid cation H-form
            "WAC_Na": 3500,  # Weak acid cation Na-form
            "SBA": 4000,  # Strong base anion
            "WBA": 3000   # Weak base anion
        },
        doc="Resin cost per cubic meter"
    )
    
    # Internals and distribution system
    blk.internals_fraction = Param(
        default=0.20,
        doc="Fraction of vessel cost for internals"
    )
    
    # Pump costs
    blk.pump_base_cost = Param(
        default=5000,
        units=pyunits.USD_2023,
        doc="Base cost for pump at 1 m³/hr, 10 m head"
    )
    
    blk.pump_size_exponent = Param(
        default=0.65,
        doc="Size exponent for pump scaling"
    )
    
    # Installation factors
    blk.installation_factor = Param(
        default=2.5,
        doc="Installation factor (installed cost / equipment cost)"
    )
    
    # Piping and valves
    blk.piping_cost_per_m = Param(
        default=500,
        units=pyunits.USD_2023 / pyunits.m,
        doc="Piping cost per meter including valves"
    )
    
    # Instrumentation
    blk.basic_instrumentation = Param(
        default=15000,
        units=pyunits.USD_2023,
        doc="Basic instrumentation package per vessel"
    )
    
    blk.advanced_instrumentation = Param(
        default=50000,
        units=pyunits.USD_2023,
        doc="Advanced instrumentation with online monitoring"
    )


def cost_ion_exchange(blk, ix_unit, 
                     vessel_material=VesselMaterial.FRP,
                     include_resin=True,
                     instrumentation_level="basic"):
    """
    Cost an ion exchange unit.
    
    Args:
        blk: Costing block
        ix_unit: Ion exchange unit model to cost
        vessel_material: Vessel construction material
        include_resin: Whether to include initial resin charge
        instrumentation_level: "basic" or "advanced"
    """
    # Create cost variables
    make_capital_cost_var(blk)
    
    # Vessel costs
    blk.vessel_volume = Var(
        initialize=10,
        units=pyunits.m**3,
        doc="Total vessel volume"
    )
    
    @blk.Constraint()
    def vessel_volume_constraint(b):
        return b.vessel_volume == (
            ix_unit.bed_volume * ix_unit.number_beds * 
            (1 + ix_unit.freeboard_fraction)
        )
    
    # Base vessel cost
    blk.vessel_cost = Var(
        initialize=100000,
        units=pyunits.USD_2023,
        doc="Vessel cost"
    )
    
    @blk.Constraint()
    def vessel_cost_constraint(b):
        material_factor = b.parent_block().ion_exchange.material_factor[vessel_material]
        return b.vessel_cost == (
            b.parent_block().ion_exchange.vessel_cost_per_m3 *
            b.vessel_volume * material_factor *
            ix_unit.number_beds
        )
    
    # Internals cost
    blk.internals_cost = Var(
        initialize=20000,
        units=pyunits.USD_2023,
        doc="Internals and distribution system cost"
    )
    
    @blk.Constraint()
    def internals_cost_constraint(b):
        return b.internals_cost == (
            b.vessel_cost * b.parent_block().ion_exchange.internals_fraction
        )
    
    # Resin cost
    if include_resin:
        blk.resin_cost = Var(
            initialize=50000,
            units=pyunits.USD_2023,
            doc="Initial resin charge cost"
        )
        
        @blk.Constraint()
        def resin_cost_constraint(b):
            resin_type = ix_unit.config.resin_type.value
            resin_cost_per_m3 = b.parent_block().ion_exchange.resin_cost_per_m3[resin_type]
            return b.resin_cost == (
                resin_cost_per_m3 * ix_unit.bed_volume * ix_unit.number_beds
            )
    else:
        blk.resin_cost = Param(default=0, units=pyunits.USD_2023)
    
    # Instrumentation
    blk.instrumentation_cost = Var(
        initialize=15000,
        units=pyunits.USD_2023,
        doc="Instrumentation cost"
    )
    
    @blk.Constraint()
    def instrumentation_cost_constraint(b):
        if instrumentation_level == "advanced":
            cost_per_vessel = b.parent_block().ion_exchange.advanced_instrumentation
        else:
            cost_per_vessel = b.parent_block().ion_exchange.basic_instrumentation
        return b.instrumentation_cost == cost_per_vessel * ix_unit.number_beds
    
    # Total direct cost
    @blk.Constraint()
    def capital_cost_constraint(b):
        return b.capital_cost == (
            b.vessel_cost + b.internals_cost + 
            b.resin_cost + b.instrumentation_cost
        )
    
    # Add scaling
    iscale.set_scaling_factor(blk.vessel_volume, 0.1)
    iscale.set_scaling_factor(blk.vessel_cost, 1e-5)
    iscale.set_scaling_factor(blk.capital_cost, 1e-5)


def cost_feed_pump(blk, pump_unit):
    """
    Cost a feed pump for the IX system.
    
    Args:
        blk: Costing block
        pump_unit: Pump unit model
    """
    make_capital_cost_var(blk)
    
    # Get pump parameters
    blk.flow_rate = Var(
        initialize=10,
        units=pyunits.m**3 / pyunits.hr,
        doc="Pump flow rate"
    )
    
    blk.head = Var(
        initialize=30,
        units=pyunits.m,
        doc="Pump head"
    )
    
    @blk.Constraint()
    def flow_rate_constraint(b):
        # Convert from m³/s to m³/hr
        return b.flow_rate == pump_unit.control_volume.properties_out[0].flow_vol * 3600
    
    @blk.Constraint()
    def head_constraint(b):
        # Convert pressure rise to head (m)
        # ΔP (Pa) / (ρ * g) = head (m)
        rho = 1000  # kg/m³ for water
        g = 9.81  # m/s²
        return b.head == (
            pump_unit.deltaP[0] / (rho * g * pyunits.Pa)
        )
    
    # Size factor for pump cost
    blk.size_factor = Var(
        initialize=1,
        doc="Pump size factor"
    )
    
    @blk.Constraint()
    def size_factor_constraint(b):
        # Reference: 1 m³/hr at 10 m head
        return b.size_factor == (
            (b.flow_rate / (1 * pyunits.m**3/pyunits.hr)) *
            (b.head / (10 * pyunits.m))
        ) ** b.parent_block().ion_exchange.pump_size_exponent
    
    # Pump cost
    @blk.Constraint()
    def capital_cost_constraint(b):
        return b.capital_cost == (
            b.parent_block().ion_exchange.pump_base_cost * b.size_factor
        )
    
    # Add pump efficiency cost factor for large pumps
    @blk.Expression()
    def efficiency_factor(b):
        # Higher efficiency pumps cost more
        # Assume 70% base efficiency, add 2% cost per 1% efficiency gain
        base_eff = 0.70
        actual_eff = pump_unit.efficiency[0]
        return 1 + 0.02 * (actual_eff - base_eff) / 0.01


def calculate_ix_system_cost(flowsheet, include_installation=True):
    """
    Calculate total cost for an IX system flowsheet.
    
    Args:
        flowsheet: Flowsheet with costed IX units
        include_installation: Whether to include installation factor
        
    Returns:
        dict with cost breakdown
    """
    costs = {
        'vessels': 0,
        'resin': 0,
        'pumps': 0,
        'instrumentation': 0,
        'piping': 0,
        'total_equipment': 0,
        'installation': 0,
        'total_installed': 0
    }
    
    # Sum up equipment costs
    for unit_name, unit in flowsheet.component_objects():
        if hasattr(unit, 'costing'):
            if 'ix' in unit_name.lower():
                costs['vessels'] += unit.costing.vessel_cost.value
                costs['resin'] += unit.costing.resin_cost.value
                costs['instrumentation'] += unit.costing.instrumentation_cost.value
            elif 'pump' in unit_name.lower():
                costs['pumps'] += unit.costing.capital_cost.value
    
    # Estimate piping (20% of vessel cost typically)
    costs['piping'] = 0.2 * costs['vessels']
    
    # Total equipment cost
    costs['total_equipment'] = (
        costs['vessels'] + costs['resin'] + costs['pumps'] + 
        costs['instrumentation'] + costs['piping']
    )
    
    # Installation
    if include_installation:
        installation_factor = flowsheet.costing.ion_exchange.installation_factor.value
        costs['installation'] = costs['total_equipment'] * (installation_factor - 1)
        costs['total_installed'] = costs['total_equipment'] * installation_factor
    else:
        costs['total_installed'] = costs['total_equipment']
    
    return costs


def add_ix_operating_costs(flowsheet, costs_dict):
    """
    Add operating costs to the cost dictionary.
    
    Args:
        flowsheet: Flowsheet with IX units
        costs_dict: Dictionary to add operating costs to
        
    Returns:
        Updated costs dictionary
    """
    # Annual operating costs
    costs_dict['operating'] = {
        'regenerant_chemicals': 0,
        'waste_disposal': 0,
        'labor': 0,
        'maintenance': 0,
        'power': 0,
        'resin_replacement': 0,
        'total_annual': 0
    }
    
    # Chemical costs (example rates)
    chemical_costs = {
        'NaCl': 0.10,  # $/kg
        'HCl': 0.20,   # $/kg
        'H2SO4': 0.15, # $/kg
        'NaOH': 0.30   # $/kg
    }
    
    # Calculate regenerant usage
    for unit_name, unit in flowsheet.component_objects():
        if hasattr(unit, 'regenerant_dose'):
            # Annual regenerations
            cycles_per_year = 365 * 24 / unit.service_time.value
            
            # Regenerant usage
            regen_kg_per_cycle = (
                unit.regenerant_dose.value * 
                unit.bed_volume.value * 
                unit.number_beds.value
            )
            
            regen_chemical = unit.config.regenerant.value
            if regen_chemical in chemical_costs:
                annual_cost = (
                    cycles_per_year * regen_kg_per_cycle * 
                    chemical_costs[regen_chemical]
                )
                costs_dict['operating']['regenerant_chemicals'] += annual_cost
    
    # Other operating costs (typical factors)
    costs_dict['operating']['labor'] = 100000  # 1 operator
    costs_dict['operating']['maintenance'] = 0.03 * costs_dict['total_installed']  # 3% of TIC
    costs_dict['operating']['power'] = 50000  # Pumping power
    costs_dict['operating']['waste_disposal'] = 0.2 * costs_dict['operating']['regenerant_chemicals']
    costs_dict['operating']['resin_replacement'] = costs_dict['resin'] / 5  # 5-year life
    
    # Total
    costs_dict['operating']['total_annual'] = sum(
        v for k, v in costs_dict['operating'].items() 
        if k != 'total_annual'
    )
    
    return costs_dict