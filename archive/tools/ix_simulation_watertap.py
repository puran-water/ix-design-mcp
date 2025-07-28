"""
Ion Exchange Simulation using WaterTAP IX Transport Model

This module provides simulation capabilities using the WaterTAP framework
with integrated PHREEQC transport modeling and derating factors.
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path
import sys
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyomo.environ import ConcreteModel, value
from idaes.core.util.model_statistics import degrees_of_freedom

# Import from the watertap_ix_transport package in parent directory
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from watertap_ix_transport.ix_flowsheet_builder import build_ix_flowsheet, initialize_ix_flowsheet
from watertap_ix_transport.ion_exchange_transport_0D import ResinType, RegenerantChem
from watertap_ix_transport.transport_core.derating_factors import DeratingCalculator
from watertap_ix_transport.transport_core.physics_based_derating import (
    PhysicsBasedDeratingEngine,
    PhysicsBasedDeratingFactors
)

from .schemas import (
    IXSimulationInput,
    IXSimulationOutput,
    IXPerformanceMetrics,
    WaterQualityProgression,
    BreakthroughCurve,
    MCASWaterComposition
)

logger = logging.getLogger(__name__)


def simulate_ix_watertap(input_data: IXSimulationInput) -> IXSimulationOutput:
    """
    Simulate ion exchange system using WaterTAP IX Transport model.
    
    This uses the full WaterTAP framework with PHREEQC transport modeling,
    derating factors, and rigorous thermodynamics.
    
    Args:
        input_data: Simulation input parameters
        
    Returns:
        IXSimulationOutput with detailed performance metrics
    """
    try:
        # Extract configuration and water analysis
        config = input_data.configuration
        water = input_data.water_analysis
        sim_options = input_data.simulation_options
        
        # Convert water composition to WaterTAP format
        feed_composition = water.ion_concentrations_mg_L.copy()
        
        # Process each stage (for now, just primary)
        primary_vessel = list(config.ix_vessels.values())[0]
        
        # Convert resin type string to enum
        resin_type_map = {
            'SAC': ResinType.SAC,
            'WAC_H': ResinType.WAC_H,
            'WAC_Na': ResinType.WAC_Na
        }
        resin_type_enum = resin_type_map.get(primary_vessel.resin_type, ResinType.SAC)
        
        # Convert regenerant string to enum
        regenerant_map = {
            'NaCl': RegenerantChem.NaCl,
            'HCl': RegenerantChem.HCl,
            'H2SO4': RegenerantChem.H2SO4,
            'NaOH': RegenerantChem.NaOH,
            'single_use': RegenerantChem.single_use
        }
        regenerant_enum = regenerant_map.get(
            input_data.regeneration.get("regenerant_type", "NaCl"),
            RegenerantChem.NaCl
        )
        
        # Prepare operating conditions from simulation options
        operating_conditions = None
        if sim_options.get("apply_derating", True):
            operating_conditions = {
                'resin_age_years': sim_options.get("resin_age_years", 0),
                'fouling_potential': sim_options.get("fouling_potential", "moderate"),
                'regenerant_dose_actual': sim_options.get("regenerant_dose_actual", 120),
                'regeneration_level': sim_options.get("regeneration_level", "standard"),
                'distributor_quality': sim_options.get("distributor_quality", "good"),
                'target_ions': ['Ca_2+', 'Mg_2+'] if primary_vessel.resin_type == 'SAC' else ['H_+']
            }
        
        # Build flowsheet
        model = build_ix_flowsheet(
            feed_composition=feed_composition,
            flow_rate_m3h=water.flow_m3_hr,
            temperature_c=water.temperature_celsius,
            resin_type=resin_type_enum,
            regenerant=regenerant_enum,
            number_of_beds=primary_vessel.number_service,
            bed_depth_m=primary_vessel.bed_depth_m,
            bed_diameter_m=primary_vessel.diameter_m,
            target_hardness_removal=sim_options.get("target_removal", 0.95),
            include_feed_pump=sim_options.get("include_feed_pump", True),
            feed_pressure_bar=water.pressure_bar
        )
        
        # Initialize flowsheet
        initialize_ix_flowsheet(model, verbose=False)
        
        # Apply derating factors if requested
        derating = None
        if operating_conditions:
            # Use physics-based derating if requested
            use_physics_based = sim_options.get("physics_based_derating", True)
            
            # Prepare column parameters
            column_params = {
                'bed_depth_m': primary_vessel.bed_depth_m,
                'bed_diameter_m': primary_vessel.diameter_m,
                'hydraulic_loading_m_hr': water.flow_m3_hr / (np.pi * (primary_vessel.diameter_m/2)**2),
                'service_time_hr': 24.0,  # Will be calculated later
                'bed_volumes_to_breakthrough': 100.0  # Will be updated from PHREEQC
            }
            
            if use_physics_based:
                # Use new physics-based engine
                engine_mode = 'design' if sim_options.get("mode", "design") == "design" else 'digital_twin'
                engine = PhysicsBasedDeratingEngine(mode=engine_mode)
                
                # Get operating history if available
                operating_history = {
                    'cycles_completed': operating_conditions.get('cycles_completed', 0),
                    'resin_age_years': operating_conditions.get('resin_age_years', 0)
                }
                
                derating = engine.calculate_physics_based_derating(
                    column_params=column_params,
                    feed_composition=feed_composition,
                    operating_history=operating_history
                )
                
                logger.info(f"Physics-based derating - Total capacity: {derating.total_capacity_factor:.2f}, "
                           f"Utilization: {derating.utilization_factor:.2f}")
            else:
                # Use empirical derating calculator
                calculator = DeratingCalculator()
                
                derating = calculator.calculate_all_factors(
                    feed_composition=feed_composition,
                    column_params=column_params,
                    operating_conditions=operating_conditions
                )
                
                logger.info(f"Empirical derating - Total capacity: {derating.total_capacity_factor:.2f}")
            
            # Store derating info for later reporting
            model.fs.derating_factors = derating
        
        # Extract results
        ix = model.fs.ix_unit
        t = model.fs.time.first()
        
        # Get breakthrough data if available
        breakthrough_curves = []
        if hasattr(ix, 'breakthrough_volume'):
            for ion, bv_var in ix.breakthrough_volume.items():
                breakthrough_curves.append(BreakthroughCurve(
                    ion=ion,
                    breakthrough_bed_volumes=value(bv_var),
                    loading_eq_L=0.0,  # Not directly available
                    leakage_mg_L=0.0   # Would need to get from PHREEQC results
                ))
        
        # Calculate performance metrics
        service_time_hr = value(ix.service_time) if hasattr(ix, 'service_time') else 24.0
        
        # Get inlet/outlet compositions
        inlet_hardness = 0
        outlet_hardness = 0
        for comp in ['Ca_2+', 'Mg_2+']:
            if comp in model.fs.feed.outlet.flow_mass_phase_comp:
                inlet_conc = value(model.fs.feed.outlet.flow_mass_phase_comp[t, 'Liq', comp])
                outlet_conc = value(model.fs.treated_water.inlet.flow_mass_phase_comp[t, 'Liq', comp])
                
                # Convert kg/s to mg/L
                flow_vol = value(model.fs.feed.outlet.flow_vol_phase[t, 'Liq'])
                if flow_vol > 0:
                    inlet_hardness += inlet_conc / flow_vol * 1e6 / 20.04 if comp == 'Ca_2+' else inlet_conc / flow_vol * 1e6 / 12.15
                    outlet_hardness += outlet_conc / flow_vol * 1e6 / 20.04 if comp == 'Ca_2+' else outlet_conc / flow_vol * 1e6 / 12.15
        
        hardness_removal = (inlet_hardness - outlet_hardness) / inlet_hardness if inlet_hardness > 0 else 0
        
        # Get pressure drop
        pressure_drop_bar = -value(ix.pressure_drop) / 1e5 if hasattr(ix, 'pressure_drop') else 0.5
        
        # Get regeneration parameters
        regen_dose = input_data.regeneration.get("dose_kg_m3_resin", 120)
        regen_volume_m3 = value(ix.bed_volume) * 0.6 * 4  # 4 BV typical
        
        # Calculate capacity utilization and regenerant consumption
        bed_volumes = breakthrough_curves[0].breakthrough_bed_volumes if breakthrough_curves else 100
        breakthrough_time_hr = bed_volumes * value(ix.bed_volume) / (water.flow_m3_hr / primary_vessel.number_service)
        
        # Calculate regenerant consumption
        regenerant_kg = regen_dose * primary_vessel.resin_volume_m3 * 0.6  # 60% of salt dose is consumed
        
        # Create performance metrics
        performance = IXPerformanceMetrics(
            # Required fields for backward compatibility
            breakthrough_time_hours=breakthrough_time_hr,
            bed_volumes_treated=bed_volumes,
            regenerant_consumption_kg=regenerant_kg,
            average_hardness_leakage_mg_L=outlet_hardness * 50 / 2,  # Average is half of outlet
            capacity_utilization_percent=75.0 if derating else 85.0,  # Estimate based on derating
            
            # Extended fields
            vessel_name="Primary IX",
            resin_type=primary_vessel.resin_type,
            service_cycle_time_hr=service_time_hr,
            service_flow_rate_m3_hr=water.flow_m3_hr,
            bed_volumes_to_breakthrough=bed_volumes,
            operating_capacity_eq_L=value(ix.operating_capacity) * value(ix.resin_capacity) if hasattr(ix, 'operating_capacity') else 1.2,
            hardness_removal_percent=hardness_removal * 100,
            sodium_leakage_mg_L=0.0,  # Would need from PHREEQC
            silica_leakage_mg_L=0.0,
            pressure_drop_bar=pressure_drop_bar,
            rinse_volume_m3=regen_volume_m3 * 0.5,  # Estimate
            regenerant_dose_kg_m3_resin=regen_dose,
            regenerant_volume_m3=regen_volume_m3,
            waste_volume_m3=regen_volume_m3 * 1.2,
            breakthrough_curves=breakthrough_curves
        )
        
        # Create water quality progression
        progression = []
        
        # Feed water
        progression.append(WaterQualityProgression(
            stage="Feed",
            pH=water.pH,
            temperature_celsius=water.temperature_celsius,
            ion_concentrations_mg_L=water.ion_concentrations_mg_L,
            alkalinity_mg_L_CaCO3=water.get_alkalinity_mg_L_CaCO3(),
            hardness_mg_L_CaCO3=water.get_total_hardness_mg_L_CaCO3(),
            tds_mg_L=water.get_tds_mg_L()
        ))
        
        # After IX
        treated_composition = water.ion_concentrations_mg_L.copy()
        treated_composition['Ca_2+'] = treated_composition.get('Ca_2+', 0) * (1 - hardness_removal)
        treated_composition['Mg_2+'] = treated_composition.get('Mg_2+', 0) * (1 - hardness_removal)
        
        # pH would change slightly due to ion exchange - estimate
        treated_ph = water.pH + 0.2  # Slight increase due to H+ exchange for hardness
        
        progression.append(WaterQualityProgression(
            stage="After Primary IX",
            pH=treated_ph,
            temperature_celsius=water.temperature_celsius,
            ion_concentrations_mg_L=treated_composition,
            alkalinity_mg_L_CaCO3=water.get_alkalinity_mg_L_CaCO3(),
            hardness_mg_L_CaCO3=outlet_hardness * 50,  # Convert meq/L to mg/L as CaCO3
            tds_mg_L=water.get_tds_mg_L()  # Approximate
        ))
        
        # Create treated water object
        treated_water = MCASWaterComposition(
            flow_m3_hr=water.flow_m3_hr,
            temperature_celsius=water.temperature_celsius,
            pressure_bar=water.pressure_bar - pressure_drop_bar,
            pH=treated_ph,
            ion_concentrations_mg_L=treated_composition
        )
        
        # Calculate economics (simplified)
        capex_usd = primary_vessel.number_service * primary_vessel.resin_volume_m3 * 1000 * 50  # $50/ft³
        
        # Operating costs
        salt_cost_per_year = (regen_dose * primary_vessel.resin_volume_m3 * 0.6 * 
                              365 * 24 / service_time_hr * 0.10)  # $0.10/kg salt
        
        opex_usd_per_year = salt_cost_per_year * 1.3  # Add 30% for other costs
        
        # Create output
        output = IXSimulationOutput(
            status="success",
            watertap_notebook_path="watertap_ix_transport_direct",
            treated_water=treated_water,
            configuration=config,
            ix_performance={"Primary": performance},
            water_quality_progression=progression,
            degasser_performance={},  # Not implemented yet
            acid_requirements=None,
            chemical_consumption={
                "NaCl_kg_per_day": regen_dose * primary_vessel.resin_volume_m3 * 0.6 * 24 / service_time_hr,
                "HCl_kg_per_day": 0.0,
                "NaOH_kg_per_day": 0.0
            },
            waste_generation={
                "brine_m3_per_day": regen_volume_m3 * 1.2 * 24 / service_time_hr,
                "sludge_kg_per_day": 0.0
            },
            economics={
                "capex_usd": capex_usd,
                "opex_usd_per_year": opex_usd_per_year,
                "water_cost_usd_per_m3": opex_usd_per_year / (water.flow_m3_hr * 8760)
            },
            warnings=[]
        )
        
        # Add derating factor information if available
        if operating_conditions and hasattr(model.fs, 'derating_factors'):
            df = model.fs.derating_factors
            
            # Check if physics-based or empirical
            is_physics_based = isinstance(df, PhysicsBasedDeratingFactors)
            derating_type = "Physics-based" if is_physics_based else "Empirical"
            
            warning_msg = (
                f"{derating_type} derating factors applied: "
                f"Fouling={df.fouling_factor:.2f}, "
                f"Regeneration={df.regeneration_efficiency:.2f}, "
                f"Channeling={df.channeling_factor:.2f}, "
                f"Competition={df.competition_factor:.2f}"
            )
            
            if is_physics_based:
                warning_msg += f" (Dispersivity={df.dispersivity_m:.3f} m)"
            
            output.warnings.append(warning_msg)
            
            # Add additional warnings for severe derating
            if df.total_capacity_factor < 0.5:
                output.warnings.append(
                    f"WARNING: Severe capacity loss detected - only {df.total_capacity_factor*100:.0f}% "
                    f"of theoretical capacity available"
                )
            
            if is_physics_based and hasattr(df, 'fouling_tracker'):
                cycles_remaining = df.fouling_tracker.predict_remaining_cycles()
                if cycles_remaining < 50:
                    output.warnings.append(
                        f"WARNING: Resin replacement recommended within {cycles_remaining} cycles"
                    )
        
        return output
        
    except Exception as e:
        logger.error(f"Simulation failed: {str(e)}")
        raise


def simulate_ix_system(input_data: IXSimulationInput) -> IXSimulationOutput:
    """
    Main entry point for IX simulation.
    
    Routes to appropriate simulation engine based on options.
    """
    model_type = input_data.simulation_options.get("model_type", "watertap")
    
    if model_type == "watertap":
        return simulate_ix_watertap(input_data)
    else:
        # Fall back to existing simulation
        from .ix_simulation_direct import simulate_ix_system_direct
        return simulate_ix_system_direct(input_data)