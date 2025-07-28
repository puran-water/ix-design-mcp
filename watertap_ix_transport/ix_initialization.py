"""
Elegant IX initialization utilities for WaterTAP models.

This module provides physics-based initialization functions for IX systems,
similar to the RO initialization approach.
"""

import logging
from typing import Dict, Any, Optional
from pyomo.environ import value, units as pyunits
from pyomo.util.calc_var_value import calculate_variable_from_constraint
from idaes.core.util.initialization import propagate_state
import idaes.logger as idaeslog

logger = logging.getLogger(__name__)


# Import the centralized utility
from .utilities.property_calculations import fix_mole_fractions as _fix_mole_fractions


def fix_mole_fractions(state_block, property_package=None):
    """
    Force calculation of mole fractions for MCAS state blocks.
    
    This is necessary when using MaterialFlowBasis.mass as MCAS doesn't 
    automatically calculate dependent variables like mole fractions.
    
    Args:
        state_block: MCAS state block (e.g., m.fs.feed.properties[0])
        property_package: MCAS property package with component_list (optional, 
                         will be determined from state_block if not provided)
    """
    # Use the centralized utility
    _fix_mole_fractions(state_block)
    
    # Additional IX-specific verification
    try:
        water_mol_frac = value(state_block.mole_frac_phase_comp['Liq', 'H2O'])
        if water_mol_frac < 0.95:
            logger.warning(
                f"Water mole fraction ({water_mol_frac:.4f}) is low. "
                "This may indicate incorrect mass flow specification."
            )
    except:
        logger.debug("Could not verify water mole fraction")


def calculate_ix_pressure_requirements(
    bed_depth_m: float,
    flow_velocity_m_hr: float = 10.0,  # Typical IX SV of 10 BV/hr
    bed_count: int = 2,
    safety_factor: float = 1.5
) -> float:
    """
    Calculate required pressure for IX operation.
    
    IX systems typically operate at lower pressures than RO.
    Main pressure requirements:
    - Overcome bed pressure drop (typically 0.5-1 bar per meter of bed)
    - Maintain minimum flow distribution pressure
    - Account for piping and valve losses
    
    Args:
        bed_depth_m: Depth of ion exchange bed in meters
        flow_velocity_m_hr: Superficial velocity in m/hr (or BV/hr)
        bed_count: Number of beds (affects piping complexity)
        safety_factor: Safety factor for pressure sizing
        
    Returns:
        Required feed pressure in Pa
    """
    # Base pressure drop through resin bed
    # Typical: 0.5-1.0 bar per meter of bed depth
    dp_per_meter = 0.75e5  # Pa/m (0.75 bar/m)
    bed_pressure_drop = bed_depth_m * dp_per_meter
    
    # Additional pressure for flow distribution
    # Higher velocities need more pressure for even distribution
    distribution_pressure = 0.5e5  # 0.5 bar minimum
    if flow_velocity_m_hr > 15:
        distribution_pressure = 1.0e5  # 1 bar for high SV
    
    # Piping and valve losses
    # More complex with multiple beds
    piping_losses = 0.3e5 * (1 + 0.2 * (bed_count - 1))  # 0.3 bar base + 0.06 bar per extra bed
    
    # Outlet pressure (typically atmospheric)
    outlet_pressure = 101325  # 1 atm
    
    # Total required pressure
    required_pressure = (
        outlet_pressure + 
        bed_pressure_drop + 
        distribution_pressure + 
        piping_losses
    ) * safety_factor
    
    logger.info(
        f"IX pressure calculation:\n"
        f"  Bed depth: {bed_depth_m:.1f} m\n"
        f"  Bed pressure drop: {bed_pressure_drop/1e5:.2f} bar\n"
        f"  Distribution pressure: {distribution_pressure/1e5:.2f} bar\n"
        f"  Piping losses: {piping_losses/1e5:.2f} bar\n"
        f"  Total required: {required_pressure/1e5:.2f} bar"
    )
    
    return required_pressure


def initialize_ix_pump(
    pump,
    target_pressure: Optional[float] = None,
    efficiency: float = 0.8
) -> None:
    """
    Initialize IX feed pump with appropriate pressure.
    
    Args:
        pump: WaterTAP Pump unit
        target_pressure: Target outlet pressure in Pa (if None, will calculate)
        efficiency: Pump efficiency
    """
    # If no target pressure specified, calculate based on typical IX requirements
    if target_pressure is None:
        # Assume typical IX operating conditions
        target_pressure = 4e5  # 4 bar - typical for IX systems
        logger.info(f"Using default IX operating pressure: {target_pressure/1e5:.1f} bar")
    
    # Fix pressure and efficiency
    pump.outlet.pressure[0].fix(target_pressure)
    pump.efficiency_pump.fix(efficiency)
    
    # Get inlet conditions for state args
    inlet_state = pump.control_volume.properties_in[0]
    
    # Build state args based on property package type
    if hasattr(inlet_state.params, 'solute_set'):
        # MCAS package
        state_args = {
            'flow_mass_phase_comp': {
                ('Liq', comp): value(pump.inlet.flow_mass_phase_comp[0, 'Liq', comp])
                for comp in ['H2O'] + list(inlet_state.params.solute_set)
            },
            'temperature': value(pump.inlet.temperature[0]),
            'pressure': target_pressure  # Use target to avoid bound issues
        }
    else:
        # Standard package
        state_args = {
            'flow_mass_phase_comp': {
                ('Liq', 'H2O'): value(pump.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O']),
                ('Liq', 'TDS'): value(pump.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'])
            },
            'temperature': value(pump.inlet.temperature[0]),
            'pressure': target_pressure
        }
    
    # Initialize with relaxed tolerances
    pump.initialize(
        state_args=state_args,
        outlvl=idaeslog.NOTSET,
        optarg={
            'tol': 1e-4,
            'constr_viol_tol': 1e-4,
            'max_iter': 50,
            'print_level': 0
        }
    )
    
    logger.info(f"IX pump initialized at {target_pressure/1e5:.1f} bar")


def initialize_ix_system(
    model,
    verbose: bool = True
) -> None:
    """
    Initialize complete IX system with elegant approach.
    
    This handles:
    - Feed initialization
    - Pump initialization with appropriate pressure
    - IX unit initialization with PHREEQC calculations
    - Product stream initialization
    
    Args:
        model: Pyomo ConcreteModel with IX flowsheet
        verbose: Print detailed progress
    """
    if verbose:
        logger.info("Initializing IX system...")
    
    # Initialize feed
    model.fs.feed.initialize(outlvl=idaeslog.NOTSET)
    
    # Fix mole fractions for feed (important for mass-based property packages)
    if hasattr(model.fs, 'properties'):
        fix_mole_fractions(model.fs.feed.properties[0], model.fs.properties)
    
    # Find IX units dynamically
    from .ix_flowsheet_builder import IonExchangeTransport0D
    ix_units = []
    for attr_name in dir(model.fs):
        attr = getattr(model.fs, attr_name)
        if hasattr(attr, '__class__') and attr.__class__.__name__ == '_ScalarIonExchangeTransport0D':
            ix_units.append((attr_name, attr))
    
    if not ix_units:
        # Fallback to specific attribute if exists
        if hasattr(model.fs, 'ix_unit'):
            ix_units = [('ix_unit', model.fs.ix_unit)]
        else:
            logger.warning("No IX units found in flowsheet")
            return
    
    # Get IX unit parameters for pressure calculation (use first unit)
    ix_unit_name, ix_unit = ix_units[0]
    bed_depth = value(ix_unit.bed_depth)
    bed_diameter = value(ix_unit.bed_diameter) 
    bed_count = ix_unit.config.number_of_beds
    
    # Calculate bed area and velocity
    bed_area = 3.14159 * (bed_diameter/2)**2
    total_flow = value(model.fs.feed.outlet.flow_vol_phase[0, 'Liq'])
    flow_per_bed = total_flow / bed_count * 3600  # m³/hr per bed
    velocity = flow_per_bed / bed_area  # m/hr
    
    if hasattr(model.fs, 'feed_pump'):
        # Calculate required pressure
        required_pressure = calculate_ix_pressure_requirements(
            bed_depth_m=bed_depth,
            flow_velocity_m_hr=velocity,
            bed_count=bed_count
        )
        
        # Cap at reasonable maximum for IX
        max_ix_pressure = 10e5  # 10 bar max for IX
        if required_pressure > max_ix_pressure:
            logger.warning(
                f"Calculated pressure ({required_pressure/1e5:.1f} bar) exceeds "
                f"typical IX maximum ({max_ix_pressure/1e5:.1f} bar). Capping."
            )
            required_pressure = max_ix_pressure
        
        # Propagate to pump
        propagate_state(model.fs.feed_to_pump)
        
        # Initialize pump
        initialize_ix_pump(model.fs.feed_pump, required_pressure)
        
        # Propagate to IX
        propagate_state(model.fs.pump_to_ix)
    else:
        # Direct propagation
        propagate_state(model.fs.feed_to_ix)
    
    # Initialize all IX units
    for unit_name, unit in ix_units:
        if verbose:
            logger.info(f"\nInitializing IX unit: {unit_name}")
        
        # Fix mole fractions for IX inlet after propagation
        if hasattr(model.fs, 'properties'):
            ix_inlet_state = unit.control_volume.properties_in[0]
            fix_mole_fractions(ix_inlet_state, model.fs.properties)
        
        # Initialize IX unit
        # The IX unit has its own sophisticated initialization that:
        # 1. Runs PHREEQC to calculate breakthrough volumes
        # 2. Sets ion removal rates based on operating capacity
        # 3. Handles charge balance constraints
        unit.initialize(outlvl=idaeslog.NOTSET)
    
    # Propagate to products
    propagate_state(model.fs.ix_to_product)
    model.fs.treated_water.initialize(outlvl=idaeslog.NOTSET)
    
    # Initialize regeneration stream if present
    if hasattr(model.fs, 'regen_waste'):
        propagate_state(model.fs.ix_to_regen)
        model.fs.regen_waste.initialize(outlvl=idaeslog.NOTSET)
    
    if verbose:
        # Report performance metrics
        logger.info("\nIX System Initialized Successfully!")
        logger.info(f"Feed flow: {total_flow*3600:.1f} m³/hr")
        logger.info(f"Service velocity: {velocity:.1f} BV/hr")
        
        if hasattr(model.fs, 'feed_pump'):
            pump_power = value(model.fs.feed_pump.work_mechanical[0]) / 1000  # kW
            logger.info(f"Pump power: {pump_power:.1f} kW")
        
        # Report performance for all IX units
        for unit_name, unit in ix_units:
            logger.info(f"\n{unit_name} performance:")
            # Report breakthrough volumes if available
            if hasattr(unit, 'target_ion_set') and hasattr(unit, 'breakthrough_volume'):
                for ion in unit.target_ion_set:
                    if ion in unit.breakthrough_volume:
                        bv = value(unit.breakthrough_volume[ion])
                        logger.info(f"  {ion} breakthrough: {bv:.0f} BV")
            
            if hasattr(unit, 'service_time'):
                service_time = value(unit.service_time)
                logger.info(f"  Service time: {service_time:.1f} hours")


def estimate_ix_performance(
    feed_composition: Dict[str, float],
    flow_rate_m3h: float,
    bed_volume_m3: float,
    resin_capacity_eq_L: float = 2.0,
    target_ion: str = 'Ca2+'
) -> Dict[str, float]:
    """
    Quick estimation of IX performance for initialization guesses.
    
    Args:
        feed_composition: Ion concentrations in mg/L
        flow_rate_m3h: Flow rate in m³/hr
        bed_volume_m3: Volume of resin bed
        resin_capacity_eq_L: Resin capacity in eq/L
        target_ion: Primary ion for breakthrough calculation
        
    Returns:
        Dict with estimated performance metrics
    """
    # Convert concentration to equivalents
    ion_charges = {
        'Ca2+': 2, 'Mg2+': 2, 'Na+': 1, 'K+': 1,
        'Fe2+': 2, 'Fe3+': 3, 'Mn2+': 2, 'Al3+': 3
    }
    
    mw_data = {
        'Ca2+': 40.08, 'Mg2+': 24.31, 'Na+': 22.99, 'K+': 39.10,
        'Fe2+': 55.85, 'Fe3+': 55.85, 'Mn2+': 54.94, 'Al3+': 26.98
    }
    
    # Calculate total ionic load in eq/L
    total_cation_eq_L = 0
    for ion, conc_mg_L in feed_composition.items():
        if ion in ion_charges and ion in mw_data:
            eq_L = (conc_mg_L / 1000) / mw_data[ion] * ion_charges[ion]
            total_cation_eq_L += eq_L
    
    # Total capacity of bed
    bed_volume_L = bed_volume_m3 * 1000
    total_capacity_eq = bed_volume_L * resin_capacity_eq_L
    
    # Theoretical breakthrough (100% utilization)
    theoretical_bv = total_capacity_eq / (total_cation_eq_L * bed_volume_L)
    
    # Practical breakthrough (50-70% utilization typical)
    utilization = 0.6
    practical_bv = theoretical_bv * utilization
    
    # Service time
    flow_rate_bv_hr = flow_rate_m3h / bed_volume_m3
    service_time_hr = practical_bv / flow_rate_bv_hr
    
    return {
        'total_ionic_load_eq_L': total_cation_eq_L,
        'theoretical_bv': theoretical_bv,
        'practical_bv': practical_bv,
        'service_time_hr': service_time_hr,
        'utilization': utilization
    }