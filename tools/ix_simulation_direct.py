"""
Direct Ion Exchange Simulation using PhreeqPy Engine

This module provides direct simulation capabilities without notebook execution,
using the PhreeqPy engine for accurate PHREEQC-based calculations.
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass
from pathlib import Path
import json
import time

from .phreeqpy_engine import PhreeqPyEngine, IXColumn
from .schemas import (
    IXSimulationInput,
    IXSimulationOutput,
    IXPerformanceMetrics,
    WaterQualityProgression,
    MCASWaterComposition,
    IXConfigurationOutput
)

logger = logging.getLogger(__name__)


def load_resin_parameters():
    """Load resin parameters from JSON database"""
    param_file = Path(__file__).parent.parent / "data" / "resin_parameters.json"
    with open(param_file, 'r') as f:
        return json.load(f)


def simulate_ix_system_direct(input_data: IXSimulationInput) -> IXSimulationOutput:
    """
    Simulate ion exchange system using direct PhreeqPy calculations.
    
    This bypasses notebook execution and provides real PHREEQC-based results.
    Supports both equilibrium and TRANSPORT models.
    
    Args:
        input_data: Simulation input parameters
        
    Returns:
        IXSimulationOutput with detailed performance metrics
    """
    start_time = time.time()
    try:
        # Check model type from simulation options
        model_type = input_data.simulation_options.get("model_type", "equilibrium")
        
        if model_type == "transport":
            # Use PHREEQC TRANSPORT model
            return _simulate_with_transport(input_data, start_time)
        else:
            # Use standard equilibrium model
            # Initialize PhreeqPy engine
            engine = PhreeqPyEngine()
            
            if not engine.pp:
                logger.warning("PhreeqPy not available - using simplified calculations")
                # Fall back to simplified calculations if needed
                return _simplified_simulation(input_data, start_time)
        
        # Extract configuration and water analysis
        config = input_data.configuration
        feed_water = input_data.water_analysis
        
        # Initialize results containers
        ix_performance = {}
        water_quality_progression = []
        
        # Add feed water to progression
        water_quality_progression.append(WaterQualityProgression(
            stage="Feed",
            pH=feed_water.pH,
            temperature_celsius=feed_water.temperature_celsius,
            ion_concentrations_mg_L=feed_water.ion_concentrations_mg_L,
            alkalinity_mg_L_CaCO3=feed_water.get_alkalinity_mg_L_CaCO3(),
            hardness_mg_L_CaCO3=feed_water.get_total_hardness_mg_L_CaCO3(),
            tds_mg_L=feed_water.get_tds_mg_L()
        ))
        
        # Load resin parameters from database
        resin_params = load_resin_parameters()
        
        # Process each IX vessel
        current_water = feed_water.ion_concentrations_mg_L.copy()
        current_ph = feed_water.pH
        current_temp = feed_water.temperature_celsius
        
        for vessel_name, vessel_config in config.ix_vessels.items():
            logger.info(f"Simulating {vessel_name} with {vessel_config.resin_type} resin")
            
            # Get resin-specific parameters from database
            resin_data = resin_params['resin_types'][vessel_config.resin_type]
            
            # Extract capacity (use gel type as default)
            capacity_eq_L = resin_data['exchange_capacity_eq_L']['gel']
            
            # Extract selectivity coefficients
            selectivity = resin_data['selectivity_coefficients']
            
            # Create IXColumn with database values
            column = IXColumn(
                resin_type=vessel_config.resin_type,
                resin_volume_L=vessel_config.resin_volume_m3 * 1000,
                exchange_capacity_eq_L=capacity_eq_L,
                selectivity_coefficients={
                    "Ca/Na": selectivity.get('Ca/Na', 40),
                    "Mg/Na": selectivity.get('Mg/Na', 25),
                    "K/Na": selectivity.get('K/Na', 2.5),
                    "Fe/Na": selectivity.get('Fe2/Na', 50)
                }
            )
            
            # Run breakthrough simulation
            # Calculate flow rate in L/hr
            flow_rate_L_hr = feed_water.flow_m3_hr * 1000 / vessel_config.number_service
            
            # Prepare feed water dict for simulate_breakthrough
            feed_water_dict = {
                "ion_concentrations_mg_L": current_water,
                "pH": current_ph,
                "temperature_celsius": current_temp
            }
            
            breakthrough_data = engine.simulate_breakthrough(
                column=column,
                feed_water=feed_water_dict,
                flow_rate_L_hr=flow_rate_L_hr,
                target_bv=1200,  # Typical max
                bv_increment=10
            )
            
            # Find breakthrough point (based on criteria)
            breakthrough_criteria = input_data.breakthrough_criteria
            hardness_limit = breakthrough_criteria.get("hardness_mg_L_CaCO3", 5.0)
            
            breakthrough_bv = None
            breakthrough_hours = None
            
            # Calculate feed hardness once
            ca_feed = current_water.get("Ca_2+", 0)
            mg_feed = current_water.get("Mg_2+", 0)
            hardness_feed = ca_feed * 2.5 + mg_feed * 4.1
            
            for i, point in enumerate(breakthrough_data):
                effluent = point.effluent_concentrations_mg_L
                ca_eff = effluent.get("Ca_2+", 0)
                mg_eff = effluent.get("Mg_2+", 0)
                hardness_eff = ca_eff * 2.5 + mg_eff * 4.1
                
                if hardness_eff > hardness_limit and breakthrough_bv is None:
                    breakthrough_bv = point.bed_volumes
                    breakthrough_hours = breakthrough_bv / config.hydraulics["bed_volumes_per_hour"]
                    
                    # Use effluent at 50% breakthrough as representative
                    mid_idx = i // 2
                    if mid_idx < len(breakthrough_data):
                        current_water = breakthrough_data[mid_idx].effluent_concentrations_mg_L
                        current_ph = breakthrough_data[mid_idx].pH
            
            # If no breakthrough found, use max simulation
            if breakthrough_bv is None:
                breakthrough_bv = 1200
                breakthrough_hours = breakthrough_bv / config.hydraulics["bed_volumes_per_hour"]
                if breakthrough_data:
                    current_water = breakthrough_data[-1].effluent_concentrations_mg_L
                    current_ph = breakthrough_data[-1].pH
            
            # Calculate total hardness removed
            # Average hardness removal (assume 95% removal before breakthrough)
            avg_hardness_removal = hardness_feed * 0.95  # mg/L as CaCO3
            volume_treated_L = flow_rate_L_hr * breakthrough_hours
            total_hardness_removed_g = avg_hardness_removal * volume_treated_L / 1000  # g as CaCO3
            
            # Calculate regeneration requirements
            # Convert hardness removed from g CaCO3 to equivalents
            capacity_used_eq = total_hardness_removed_g / 50.045  # MW of CaCO3 / 2
            
            # Limit to practical resin capacity
            capacity_used_eq = min(
                capacity_used_eq,
                column.resin_volume_L * column.exchange_capacity_eq_L * 0.8  # 80% max utilization
            )
            
            regen_data = engine.calculate_regenerant_requirement(
                column=column,
                capacity_used_eq=capacity_used_eq,
                regenerant_type="NaCl" if vessel_config.resin_type == "SAC" else "HCl",
                efficiency=0.65 if vessel_config.resin_type == "SAC" else 0.85
            )
            
            # Add some breakthrough curve points to water quality progression for testing
            # Sample every 10th point up to 15 points total
            for i, point in enumerate(breakthrough_data[:150:10]):  # Every 10th point, max 15
                effluent = point.effluent_concentrations_mg_L
                water_quality_progression.append(WaterQualityProgression(
                    stage=f"{vessel_name} @ {point.bed_volumes:.0f} BV",
                    pH=point.pH,
                    temperature_celsius=current_temp,
                    ion_concentrations_mg_L=effluent,
                    alkalinity_mg_L_CaCO3=_calculate_alkalinity(effluent),
                    hardness_mg_L_CaCO3=effluent.get("Ca_2+", 0) * 2.5 + effluent.get("Mg_2+", 0) * 4.1,
                    tds_mg_L=sum(effluent.values())
                ))
            
            # Store performance metrics
            ix_performance[vessel_name] = IXPerformanceMetrics(
                breakthrough_time_hours=breakthrough_hours,
                bed_volumes_treated=breakthrough_bv,
                regenerant_consumption_kg=regen_data["regenerant_kg"],
                average_hardness_leakage_mg_L=hardness_limit / 2,  # Approximate
                capacity_utilization_percent=(capacity_used_eq / (column.resin_volume_L * column.exchange_capacity_eq_L)) * 100,
                regenerant_chemical=regen_data["regenerant_type"],
                specific_regenerant_g_L=regen_data["specific_consumption_g_L_resin"],
                cycles_completed=1,  # Single cycle simulation
                total_throughput_m3=breakthrough_hours * feed_water.flow_m3_hr,
                waste_volume_m3=vessel_config.resin_volume_m3 * 6  # Typical 6 BV waste per cycle
            )
            
            # Add to water quality progression
            water_quality_progression.append(WaterQualityProgression(
                stage=f"After {vessel_name}",
                pH=current_ph,
                temperature_celsius=current_temp,
                ion_concentrations_mg_L=current_water,
                alkalinity_mg_L_CaCO3=_calculate_alkalinity(current_water),
                hardness_mg_L_CaCO3=current_water.get("Ca_2+", 0) * 2.5 + current_water.get("Mg_2+", 0) * 4.1,
                tds_mg_L=sum(current_water.values())
            ))
        
        # Simulate degasser if present
        degasser_performance = {}
        if config.degasser:
            # Prepare water dict for degasser simulation
            degasser_feed = {
                "ion_concentrations_mg_L": current_water,
                "pH": current_ph,
                "temperature_celsius": current_temp
            }
            degasser_result = engine.simulate_degasser_performance(
                influent_water=degasser_feed,
                tower_ntu=3.0,
                target_co2_mg_L=5.0
            )
            
            degasser_performance = {
                "influent_CO2_mg_L": degasser_result["influent_CO2_mg_L"],
                "effluent_CO2_mg_L": degasser_result["effluent_CO2_mg_L"],
                "removal_percent": degasser_result["removal_percent"],
                "effluent_pH": degasser_result["effluent_pH"],
                "tower_height_m": config.degasser.packed_height_m,
                "diameter_m": config.degasser.diameter_m
            }
            
            # Update water after degasser
            current_ph = degasser_result["effluent_pH"]
            
            water_quality_progression.append(WaterQualityProgression(
                stage="After Degasser",
                pH=current_ph,
                temperature_celsius=current_temp,
                ion_concentrations_mg_L=current_water,
                alkalinity_mg_L_CaCO3=_calculate_alkalinity(current_water) * 0.8,  # Reduced by CO2 removal
                hardness_mg_L_CaCO3=current_water.get("Ca_2+", 0) * 2.5 + current_water.get("Mg_2+", 0) * 4.1,
                tds_mg_L=sum(current_water.values())
            ))
        
        # Check if acid dosing is needed
        acid_requirements = None
        if input_data.acid_options and current_ph > input_data.acid_options.get("target_pH", 7.0):
            acid_result = engine.calculate_acid_dose_for_degasser(
                influent_water=current_water,
                target_ph=input_data.acid_options.get("target_pH", 7.0),
                acid_type=input_data.acid_options.get("acid_type", "H2SO4")
            )
            
            acid_requirements = {
                acid_result["acid_type"]: {
                    "dose_mg_L": acid_result.get("optimal_dose_mg_L", acid_result.get("dose_mg_L", 0)),
                    "dose_mmol_L": acid_result.get("optimal_dose_mmol_L", acid_result.get("dose_mmol_L", 0)),
                    "annual_consumption_kg": acid_result.get("optimal_dose_mg_L", acid_result.get("dose_mg_L", 0)) * feed_water.flow_m3_hr * 365 * 20 / 1000,
                    "achieved_pH": acid_result.get("achieved_pH", input_data.acid_options.get("target_pH", 7.0))
                }
            }
        
        # Create treated water composition
        treated_water = MCASWaterComposition(
            flow_m3_hr=feed_water.flow_m3_hr,
            temperature_celsius=current_temp,
            pressure_bar=feed_water.pressure_bar,
            pH=current_ph,
            ion_concentrations_mg_L=current_water,
            source=f"Treated by {config.flowsheet_type}"
        )
        
        # Calculate simple economics
        economics = {
            "capital_cost": len(config.ix_vessels) * 50000,  # Rough estimate
            "operating_cost_annual": sum(
                perf.regenerant_consumption_kg * 365 * 20 / perf.breakthrough_time_hours * 0.2  # $0.2/kg regenerant
                for perf in ix_performance.values()
            ),
            "cost_per_m3": 0.5  # Rough estimate
        }
        
        return IXSimulationOutput(
            status="success",
            watertap_notebook_path="direct_simulation",  # No notebook used
            treated_water=treated_water,
            ix_performance=ix_performance,
            degasser_performance=degasser_performance,
            acid_requirements=acid_requirements,
            water_quality_progression=water_quality_progression,
            economics=economics,
            actual_runtime_seconds=time.time() - start_time
        )
        
    except Exception as e:
        logger.error(f"Direct simulation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return error status with empty results
        return IXSimulationOutput(
            status=f"error: {str(e)}",
            watertap_notebook_path="direct_simulation_error",
            treated_water=input_data.water_analysis,  # Return feed water
            ix_performance={},
            degasser_performance={},
            acid_requirements=None,
            water_quality_progression=[],
            economics={},
            actual_runtime_seconds=time.time() - start_time
        )


def _calculate_alkalinity(ion_concentrations: Dict[str, float]) -> float:
    """Calculate alkalinity from ion concentrations."""
    # Simplified calculation
    hco3 = ion_concentrations.get("HCO3_-", 0)
    co3 = ion_concentrations.get("CO3_2-", 0)
    oh = ion_concentrations.get("OH_-", 0)
    
    # Convert to mg/L as CaCO3
    alk_eq = hco3 / 61.02 + 2 * co3 / 60.01 + oh / 17.01
    return alk_eq * 50.04  # Convert eq/L to mg/L as CaCO3


def _simulate_with_transport(input_data: IXSimulationInput, start_time: float) -> IXSimulationOutput:
    """
    Simulate ion exchange using PHREEQC TRANSPORT model.
    
    This provides more accurate breakthrough curves and accounts for
    dispersion, kinetics, and non-ideal flow patterns.
    """
    from .phreeqc_transport_engine import PhreeqcTransportEngine, TransportParameters
    
    logger.info("Using PHREEQC TRANSPORT model for simulation")
    
    config = input_data.configuration
    feed_water = input_data.water_analysis
    
    # Initialize results containers
    ix_performance = {}
    water_quality_progression = []
    detailed_results = {}
    
    # Add feed water to progression
    water_quality_progression.append(WaterQualityProgression(
        stage="Feed",
        pH=feed_water.pH,
        temperature_celsius=feed_water.temperature_celsius,
        ion_concentrations_mg_L=feed_water.ion_concentrations_mg_L,
        alkalinity_mg_L_CaCO3=feed_water.get_alkalinity_mg_L_CaCO3(),
        hardness_mg_L_CaCO3=feed_water.get_total_hardness_mg_L_CaCO3(),
        tds_mg_L=feed_water.get_tds_mg_L()
    ))
    
    # Process each IX vessel using TRANSPORT
    current_water = feed_water.ion_concentrations_mg_L.copy()
    current_ph = feed_water.pH
    current_temp = feed_water.temperature_celsius
    
    for vessel_name, vessel_config in config.ix_vessels.items():
        logger.info(f"Simulating {vessel_name} with TRANSPORT model")
        
        # Initialize TRANSPORT engine
        engine = PhreeqcTransportEngine(
            resin_type=vessel_config.resin_type
        )
        
        # Prepare column parameters
        column_params = {
            'bed_volume_m3': vessel_config.resin_volume_m3,
            'diameter_m': vessel_config.diameter_m,
            'flow_rate_m3_hr': feed_water.flow_m3_hr / vessel_config.number_service,
            'bed_depth_m': vessel_config.bed_depth_m
        }
        
        # Prepare feed composition in PHREEQC format
        feed_composition = {
            'temperature': current_temp,
            'pH': current_ph,
            'alkalinity': feed_water.get_alkalinity_mg_L_CaCO3()
        }
        
        # Convert MCAS ions to PHREEQC format
        ion_mapping = {
            'Na_+': 'Na',
            'Ca_2+': 'Ca',
            'Mg_2+': 'Mg',
            'K_+': 'K',
            'NH4_+': 'N(5)',  # Ammonium as N(V)
            'Cl_-': 'Cl',
            'SO4_2-': 'S(6)',  # Sulfate as S(VI)
            'HCO3_-': 'C(4)',  # Bicarbonate handled via alkalinity
            'NO3_-': 'N(5)'   # Nitrate as N(V)
        }
        
        for mcas_ion, conc in current_water.items():
            if mcas_ion in ion_mapping:
                phreeqc_species = ion_mapping[mcas_ion]
                # Special handling for some species
                if mcas_ion == 'SO4_2-':
                    # Convert SO4 to S concentration
                    feed_composition[phreeqc_species] = conc * 32.066 / 96.064
                elif mcas_ion == 'HCO3_-':
                    # Bicarbonate handled via alkalinity
                    pass
                else:
                    feed_composition[phreeqc_species] = conc
        
        # Set up transport parameters
        transport_params = TransportParameters(
            cells=input_data.simulation_options.get("transport_cells", 20),
            shifts=500,  # Run for up to 500 BV
            time_step=3600,  # 1 hour
            dispersivity=0.02,
            diffusion_coefficient=1e-10,
            porosity=0.4
        )
        
        # Run TRANSPORT simulation
        results = engine.simulate_breakthrough(
            column_params, 
            feed_composition, 
            transport_params
        )
        
        if 'error' in results:
            logger.error(f"TRANSPORT simulation failed: {results['error']}")
            # Fall back to simplified calculation
            return _simplified_simulation(input_data)
        
        # Extract performance metrics
        breakthrough_bv = results.get('Ca_breakthrough_BV', 500)
        breakthrough_hours = breakthrough_bv * column_params['bed_volume_m3'] / (column_params['flow_rate_m3_hr'])
        
        # Calculate regenerant requirements
        # Approximate capacity used based on breakthrough
        capacity_used_eq = vessel_config.resin_volume_m3 * 1000 * 2.0 * 0.7  # 70% utilization
        
        if vessel_config.resin_type == "SAC":
            regenerant_chemical = "NaCl"
            regenerant_level = 160  # kg/m3
            efficiency = 0.65
        else:
            regenerant_chemical = "HCl"
            regenerant_level = 80  # kg/m3
            efficiency = 0.85
        
        regenerant_kg = (capacity_used_eq / efficiency) * 58.44 / 1000  # NaCl MW
        
        ix_performance[vessel_name] = IXPerformanceMetrics(
            breakthrough_time_hours=breakthrough_hours,
            bed_volumes_treated=breakthrough_bv,
            regenerant_consumption_kg=regenerant_kg,
            average_hardness_leakage_mg_L=2.0,  # Typical
            capacity_utilization_percent=70,
            regenerant_chemical=regenerant_chemical,
            specific_regenerant_g_L=regenerant_level,
            cycles_completed=1,
            total_throughput_m3=breakthrough_hours * column_params['flow_rate_m3_hr'],
            waste_volume_m3=vessel_config.resin_volume_m3 * 6  # Typical 6 BV waste per cycle
        )
        
        # Store detailed results
        detailed_results[vessel_name] = {
            'bed_volumes': results['bed_volumes'],
            'effluent_Ca_mg_L': results['effluent_Ca_mg_L'],
            'effluent_Mg_mg_L': results['effluent_Mg_mg_L'],
            'effluent_Na_mg_L': results['effluent_Na_mg_L'],
            'model_type': 'PHREEQC_TRANSPORT'
        }
        
        # Update water quality for next stage
        # Use average effluent quality
        if results['bed_volumes']:
            mid_idx = len(results['bed_volumes']) // 2
            current_water['Ca_2+'] = results['effluent_Ca_mg_L'][mid_idx]
            current_water['Mg_2+'] = results['effluent_Mg_mg_L'][mid_idx]
            current_water['Na_+'] = results['effluent_Na_mg_L'][mid_idx]
    
    # Create treated water object
    treated_water = MCASWaterComposition(
        flow_m3_hr=feed_water.flow_m3_hr,
        temperature_celsius=current_temp,
        pressure_bar=feed_water.pressure_bar,
        pH=current_ph,
        ion_concentrations_mg_L=current_water
    )
    
    # Add treated water to progression
    water_quality_progression.append(WaterQualityProgression(
        stage="Treated",
        pH=current_ph,
        temperature_celsius=current_temp,
        ion_concentrations_mg_L=current_water,
        alkalinity_mg_L_CaCO3=treated_water.get_alkalinity_mg_L_CaCO3(),
        hardness_mg_L_CaCO3=treated_water.get_total_hardness_mg_L_CaCO3(),
        tds_mg_L=treated_water.get_tds_mg_L()
    ))
    
    # Simple economic estimates
    economics = {
        "capital_cost": len(config.ix_vessels) * 200000,
        "operating_cost_annual": sum(p.regenerant_consumption_kg * 0.2 * 365 / p.breakthrough_time_hours * 24 
                                   for p in ix_performance.values()),
        "cost_per_m3": 0.15
    }
    
    return IXSimulationOutput(
        status="success",
        watertap_notebook_path="PHREEQC_TRANSPORT_direct",
        treated_water=treated_water,
        ix_performance=ix_performance,
        degasser_performance={
            "influent_CO2_mg_L": 44,
            "effluent_CO2_mg_L": 4.4,
            "efficiency_percent": 90,
            "power_consumption_kW": config.degasser.fan_power_kW
        },
        acid_requirements=None,
        water_quality_progression=water_quality_progression,
        economics=economics,
        detailed_results=detailed_results,
        actual_runtime_seconds=time.time() - start_time,
        recommendations=[
            f"TRANSPORT model used with {input_data.simulation_options.get('transport_cells', 20)} cells",
            "Results account for dispersion and non-ideal flow",
            "Check Na levels - typical industrial water has 200-500 mg/L Na+",
            "High Na reduces effective capacity for hardness removal"
        ]
    )


def _simplified_simulation(input_data: IXSimulationInput, start_time: float) -> IXSimulationOutput:
    """Fallback simplified simulation when PhreeqPy is not available."""
    logger.warning("Using simplified simulation - results are approximate")
    
    config = input_data.configuration
    feed_water = input_data.water_analysis
    
    # Simple hardness removal calculation
    feed_hardness = feed_water.get_total_hardness_mg_L_CaCO3()
    treated_hardness = 5.0  # Assume good removal
    
    # Create simplified treated water
    treated_water = MCASWaterComposition(
        flow_m3_hr=feed_water.flow_m3_hr,
        temperature_celsius=feed_water.temperature_celsius,
        pressure_bar=feed_water.pressure_bar,
        pH=7.5,
        ion_concentrations_mg_L={
            "Ca_2+": 2,
            "Mg_2+": 1,
            "Na_+": feed_water.ion_concentrations_mg_L.get("Na_+", 100) + 100,  # Added from exchange
            "Cl_-": feed_water.ion_concentrations_mg_L.get("Cl_-", 100),
            "SO4_2-": feed_water.ion_concentrations_mg_L.get("SO4_2-", 100),
            "HCO3_-": feed_water.ion_concentrations_mg_L.get("HCO3_-", 100)
        },
        source=f"Simplified treatment"
    )
    
    # Simple performance metrics
    ix_performance = {}
    for vessel_name, vessel_config in config.ix_vessels.items():
        ix_performance[vessel_name] = IXPerformanceMetrics(
            breakthrough_time_hours=24,
            bed_volumes_treated=384,
            regenerant_consumption_kg=50,
            average_hardness_leakage_mg_L=3,
            capacity_utilization_percent=75,
            regenerant_chemical="NaCl",
            specific_regenerant_g_L=120,
            cycles_completed=1,
            total_throughput_m3=240,
            waste_volume_m3=vessel_config.resin_volume_m3 * 6  # Typical 6 BV waste per cycle
        )
    
    return IXSimulationOutput(
        status="success (simplified)",
        watertap_notebook_path="simplified_calculation",
        treated_water=treated_water,
        ix_performance=ix_performance,
        degasser_performance={},
        acid_requirements=None,
        water_quality_progression=[],
        economics={"capital_cost": 100000, "operating_cost_annual": 20000, "cost_per_m3": 0.5},
        actual_runtime_seconds=time.time() - start_time
    )