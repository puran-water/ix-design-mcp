"""
IX flowsheet builder with integrated heuristic sizing.

This module combines heuristic sizing from the tools with the flowsheet builder
to automatically size IX vessels based on water quality and flow rate.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyomo.environ import ConcreteModel, value
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
import idaes.logger as idaeslog

from watertap_ix_transport.ix_flowsheet_builder import (
    build_ix_flowsheet as build_ix_flowsheet_base,
    initialize_ix_flowsheet
)
from tools.ix_configuration import size_ix_vessel, IXConfigurationTool
from tools.schemas import IXConfigurationInput, MCASWaterComposition

import logging
logger = logging.getLogger(__name__)


def build_ix_flowsheet_with_sizing(
    feed_composition: dict,
    flow_rate_m3h: float,
    temperature_c: float = 25.0,
    pressure_bar: float = 4.0,
    target_hardness_removal: float = 0.95,
    resin_type: str = 'SAC',
    regenerant: str = 'NaCl',
    operating_conditions: dict = None,
    include_feed_pump: bool = True,
    feed_pressure_bar: float = 1.0,
    use_heuristic_sizing: bool = True,
    max_vessel_diameter_m: float = 2.4,
):
    """
    Build IX flowsheet with automatic heuristic sizing.
    
    Args:
        feed_composition: Feed water composition (mg/L)
        flow_rate_m3h: Flow rate in m³/hr
        temperature_c: Temperature in °C
        pressure_bar: Operating pressure in bar
        target_hardness_removal: Target removal fraction (0-1)
        resin_type: Type of resin ('SAC', 'WAC_H', 'WAC_Na')
        regenerant: Regenerant chemical
        operating_conditions: Optional derating factors
        include_feed_pump: Whether to include feed pump
        feed_pressure_bar: Feed pressure if pump included
        use_heuristic_sizing: Whether to use heuristic sizing
        max_vessel_diameter_m: Maximum vessel diameter
        
    Returns:
        Pyomo ConcreteModel with IX flowsheet
    """
    
    if use_heuristic_sizing:
        logger.info("Using heuristic sizing for IX vessels")
        
        # Calculate hardness to remove
        ca_mg_L = feed_composition.get('Ca_2+', feed_composition.get('Ca', 0))
        mg_mg_L = feed_composition.get('Mg_2+', feed_composition.get('Mg', 0))
        
        # Convert to meq/L
        ca_meq_L = ca_mg_L / 20.04  # MW Ca = 40.08, valence = 2
        mg_meq_L = mg_mg_L / 12.15  # MW Mg = 24.31, valence = 2
        hardness_meq_L = ca_meq_L + mg_meq_L
        hardness_to_remove_meq_L = hardness_meq_L * target_hardness_removal
        
        # Calculate competition factor
        competition_factor = 1.0  # Default
        if operating_conditions and 'competition_factor' in operating_conditions:
            competition_factor = operating_conditions['competition_factor']
        else:
            # Simple competition calculation based on Na
            na_mg_L = feed_composition.get('Na_+', feed_composition.get('Na', 0))
            na_meq_L = na_mg_L / 22.99
            if hardness_meq_L > 0:
                # Higher Na/hardness ratio = more competition
                competition_factor = 1.0 + 0.1 * (na_meq_L / hardness_meq_L)
                competition_factor = min(competition_factor, 2.0)  # Cap at 2x
        
        # Size vessels
        vessel_config = size_ix_vessel(
            flow_m3_hr=flow_rate_m3h,
            resin_type=resin_type,
            hardness_to_remove_meq_L=hardness_to_remove_meq_L,
            competition_factor=competition_factor,
            max_diameter_m=max_vessel_diameter_m
        )
        
        logger.info(f"Heuristic sizing results:")
        logger.info(f"  Number of service vessels: {vessel_config.number_service}")
        logger.info(f"  Number of standby vessels: {vessel_config.number_standby}")
        logger.info(f"  Vessel diameter: {vessel_config.diameter_m} m")
        logger.info(f"  Bed depth: {vessel_config.bed_depth_m} m")
        logger.info(f"  Total resin volume: {vessel_config.resin_volume_m3} m³")
        logger.info(f"  Vessel height: {vessel_config.vessel_height_m} m")
        
        # Use sized parameters
        number_of_beds = vessel_config.number_service
        bed_diameter_m = vessel_config.diameter_m
        bed_depth_m = vessel_config.bed_depth_m
        
        # Calculate bed volume per vessel
        bed_volume_m3 = vessel_config.resin_volume_m3 / vessel_config.number_service
        
    else:
        # Use default values if not sizing
        number_of_beds = 2
        bed_diameter_m = 2.0
        bed_depth_m = 2.0
        bed_volume_m3 = 3.14159 * (bed_diameter_m/2)**2 * bed_depth_m
    
    # Build flowsheet with calculated dimensions
    model = build_ix_flowsheet_base(
        feed_composition=feed_composition,
        flow_rate_m3h=flow_rate_m3h,
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        target_hardness_removal=target_hardness_removal,
        resin_type=resin_type,
        regenerant=regenerant,
        number_of_beds=number_of_beds,
        bed_depth_m=bed_depth_m,
        bed_diameter_m=bed_diameter_m,
        operating_conditions=operating_conditions,
        include_feed_pump=include_feed_pump,
        feed_pressure_bar=feed_pressure_bar
    )
    
    # Store sizing results on model for reference
    if use_heuristic_sizing:
        model.fs.ix_sizing = vessel_config
        
        # Log service cycle estimation
        if hasattr(model.fs.ix_unit, 'service_time'):
            service_time_hr = value(model.fs.ix_unit.service_time)
            cycles_per_day = 24 / service_time_hr if service_time_hr > 0 else 0
            logger.info(f"Estimated service cycle: {service_time_hr:.1f} hours ({cycles_per_day:.1f} cycles/day)")
    
    return model


def configure_complete_ix_system(input_data: IXConfigurationInput) -> dict:
    """
    Configure complete IX system including sizing and flowsheet.
    
    Args:
        input_data: IXConfigurationInput with water quality and requirements
        
    Returns:
        Dictionary with configuration results and flowsheet model
    """
    # Use the IX configuration tool for complete system design
    config_tool = IXConfigurationTool()
    config_output = config_tool.configure_system(input_data)
    
    # Extract the primary IX stage configuration
    primary_stage = config_output.process_train[0]
    
    # Convert MCASWaterComposition to dict
    feed_comp_dict = {
        'Ca_2+': input_data.feed_water.Ca_mg_L,
        'Mg_2+': input_data.feed_water.Mg_mg_L,
        'Na_+': input_data.feed_water.Na_mg_L,
        'K_+': input_data.feed_water.K_mg_L,
        'Cl_-': input_data.feed_water.Cl_mg_L,
        'SO4_2-': input_data.feed_water.SO4_mg_L,
        'HCO3_-': input_data.feed_water.HCO3_mg_L,
    }
    
    # Add trace metals if present
    if input_data.feed_water.Fe_mg_L > 0:
        feed_comp_dict['Fe_2+'] = input_data.feed_water.Fe_mg_L
    if input_data.feed_water.Mn_mg_L > 0:
        feed_comp_dict['Mn_2+'] = input_data.feed_water.Mn_mg_L
    
    # Build flowsheet for primary stage
    model = build_ix_flowsheet_with_sizing(
        feed_composition=feed_comp_dict,
        flow_rate_m3h=input_data.flow_rate_m3_hr,
        temperature_c=input_data.feed_water.temperature_C,
        pressure_bar=4.0,  # Default operating pressure
        target_hardness_removal=primary_stage.target_removal_fraction,
        resin_type=primary_stage.resin_type,
        regenerant=primary_stage.regenerant,
        operating_conditions=input_data.operating_conditions,
        include_feed_pump=True,
        use_heuristic_sizing=False,  # Already sized by config tool
        max_vessel_diameter_m=input_data.max_vessel_diameter_m
    )
    
    # Use the sized dimensions from config tool
    model.fs.ix_unit.bed_diameter.fix(primary_stage.vessels.diameter_m)
    model.fs.ix_unit.bed_depth.fix(primary_stage.vessels.bed_depth_m)
    
    # Initialize the flowsheet
    initialize_ix_flowsheet(model)
    
    return {
        'configuration': config_output,
        'flowsheet_model': model,
        'primary_stage': primary_stage,
        'total_stages': len(config_output.process_train)
    }


if __name__ == "__main__":
    # Example usage
    feed_composition = {
        'Ca_2+': 150,  # mg/L
        'Mg_2+': 80,   # mg/L
        'Na_+': 100,   # mg/L
        'Cl_-': 400,   # mg/L
        'SO4_2-': 100, # mg/L
        'HCO3_-': 180, # mg/L
    }
    
    # Build with heuristic sizing
    print("Building IX flowsheet with heuristic sizing...")
    model = build_ix_flowsheet_with_sizing(
        feed_composition=feed_composition,
        flow_rate_m3h=100.0,
        temperature_c=25.0,
        target_hardness_removal=0.95,
        use_heuristic_sizing=True
    )
    
    print(f"\nInitial DOF: {degrees_of_freedom(model)}")
    
    # Initialize
    initialize_ix_flowsheet(model)
    
    print(f"DOF after initialization: {degrees_of_freedom(model)}")
    
    # Report results
    ix = model.fs.ix_unit
    print(f"\nIX sizing results:")
    print(f"  Bed diameter: {value(ix.bed_diameter):.2f} m")
    print(f"  Bed depth: {value(ix.bed_depth):.2f} m")
    print(f"  Bed volume: {value(ix.bed_volume):.2f} m³")
    print(f"  Service time: {value(ix.service_time):.1f} hours")
    
    if hasattr(model.fs, 'ix_sizing'):
        print(f"\nVessel configuration:")
        print(f"  Service vessels: {model.fs.ix_sizing.number_service}")
        print(f"  Standby vessels: {model.fs.ix_sizing.number_standby}")
        print(f"  Total vessels: {model.fs.ix_sizing.number_service + model.fs.ix_sizing.number_standby}")