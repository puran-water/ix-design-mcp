"""
Ion Exchange Simulation Tool

Executes PhreeqPy simulations for ion exchange systems via papermill notebook execution.
Notebook execution is REQUIRED for process isolation to prevent WaterTAP/PhreeqPy conflicts.
"""

import os
import sys
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Import papermill for notebook execution
try:
    import papermill as pm
except ImportError:
    pm = None

from .schemas import (
    IXSimulationInput,
    IXSimulationOutput,
    IXPerformanceMetrics,
    WaterQualityProgression,
    MCASWaterComposition
)
# Note: Direct simulation removed - notebook execution is the primary method for process isolation

logger = logging.getLogger(__name__)


def prepare_simulation_parameters(
    input_data: IXSimulationInput
) -> Dict[str, Any]:
    """
    Prepare parameters for notebook execution.
    
    Converts input data to format expected by Jupyter notebook template.
    """
    config = input_data.configuration
    water = input_data.water_analysis
    
    # Extract vessel configurations
    vessels = {}
    for stage_name, vessel_config in config.ix_vessels.items():
        vessels[stage_name] = {
            "resin_type": vessel_config.resin_type,
            "number_service": vessel_config.number_service,
            "number_standby": vessel_config.number_standby,
            "diameter_m": vessel_config.diameter_m,
            "bed_depth_m": vessel_config.bed_depth_m,
            "resin_volume_m3": vessel_config.resin_volume_m3,
            "vessel_height_m": vessel_config.vessel_height_m
        }
    
    # Prepare water analysis in format expected by notebook
    water_dict = {
        "flow_m3_hr": water.flow_m3_hr,
        "temperature_celsius": water.temperature_celsius,
        "pressure_bar": water.pressure_bar,
        "pH": water.pH,
        "ion_concentrations_mg_L": water.ion_concentrations_mg_L,
        "total_hardness_mg_L_CaCO3": water.get_total_hardness_mg_L_CaCO3(),
        "alkalinity_mg_L_CaCO3": water.get_alkalinity_mg_L_CaCO3(),
        "tds_mg_L": water.get_tds_mg_L(),
        "ionic_strength_mol_L": water.get_ionic_strength_mol_L()
    }
    
    # Prepare degasser configuration
    degasser_dict = {
        "type": config.degasser.type,
        "packing": config.degasser.packing,
        "diameter_m": config.degasser.diameter_m,
        "packed_height_m": config.degasser.packed_height_m,
        "hydraulic_loading_m_hr": config.degasser.hydraulic_loading_m_hr,
        "air_flow_m3_hr": config.degasser.air_flow_m3_hr,
        "fan_discharge_pressure_mbar": config.degasser.fan_discharge_pressure_mbar,
        "fan_power_kW": config.degasser.fan_power_kW
    }
    
    # Compile all parameters
    parameters = {
        # Project paths - use absolute path for papermill injection
        "project_root": str(Path(__file__).parent.parent.absolute()),
        
        # Path for watertap_ix_transport import in notebook
        "watertap_ix_transport_path": str(Path(__file__).parent.parent.absolute()),
        
        # Configuration object for notebook
        "configuration": {
            "flowsheet_type": config.flowsheet_type,
            "flowsheet_description": config.flowsheet_description,
            "na_competition_factor": getattr(config, 'na_competition_factor', 1.0),
            "effective_capacity": getattr(config, 'effective_capacity', {}),
            "ix_vessels": vessels,
            "degasser": degasser_dict,
            "hydraulics": config.hydraulics,
            "economics": getattr(config, 'economics', {})
        },
        
        # Water analysis object for notebook
        "water_analysis": water_dict,
        
        # Breakthrough criteria
        "breakthrough_criteria": input_data.breakthrough_criteria,
        
        # Regenerant parameters
        "regenerant_parameters": input_data.regenerant_parameters,
        
        # Acid options
        "acid_options": input_data.acid_options,
        
        # Simulation options (support both standard and GrayBox models)
        "simulation_options": {**input_data.simulation_options},
        
        # Timestamp for unique runs
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
    }
    
    # Log parameter values for debugging
    logger.info("Papermill parameters prepared:")
    logger.info(f"  - project_root: {parameters['project_root']}")
    logger.info(f"  - flowsheet_type: {parameters['configuration']['flowsheet_type']}")
    logger.info(f"  - na_competition_factor: {parameters['configuration']['na_competition_factor']}")
    logger.info(f"  - vessels: {list(parameters['configuration']['ix_vessels'].keys())}")
    logger.info(f"  - water flow: {parameters['water_analysis']['flow_m3_hr']} m³/hr")
    logger.info(f"  - feed ions: {list(parameters['water_analysis']['ion_concentrations_mg_L'].keys())}")
    
    # Validate critical parameters
    if parameters['water_analysis']['flow_m3_hr'] <= 0:
        logger.warning("WARNING: Zero or negative flow rate detected!")
    
    total_ions = sum(parameters['water_analysis']['ion_concentrations_mg_L'].values())
    if total_ions > 50000:  # 50 g/L is extremely high
        logger.warning(f"WARNING: Very high total ion concentration: {total_ions} mg/L")
    
    return parameters


def extract_results_from_notebook(notebook_path: Path) -> Dict[str, Any]:
    """
    Extract simulation results from executed notebook.
    
    Looks for cells tagged with 'results' and extracts output data.
    """
    try:
        import nbformat
        
        # Read the completed notebook
        with open(notebook_path, 'r', encoding='utf-8') as f:
            nb = nbformat.read(f, as_version=4)
        
        # Look for results cells
        results_data = None
        for cell in nb.cells:
            # Check if this is a code cell with outputs
            if cell.cell_type == 'code' and cell.outputs:
                # Look for cells tagged with 'results' OR containing 'results = result'
                is_results_cell = False
                
                # Check for tags
                if 'tags' in cell.metadata and 'results' in cell.metadata.tags:
                    is_results_cell = True
                
                # Check for source containing 'results = result'
                if not is_results_cell and 'source' in cell:
                    source_text = ''.join(cell['source']) if isinstance(cell['source'], list) else cell['source']
                    if 'results = result' in source_text and 'results' in source_text.split('\n')[-1]:
                        is_results_cell = True
                
                if is_results_cell:
                    # Extract results from output
                    for output in cell.outputs:
                        if output.get('output_type') == 'execute_result':
                            if 'data' in output and 'text/plain' in output['data']:
                                results_str = output['data']['text/plain']
                                # Parse the results
                                try:
                                    import ast
                                    results_data = ast.literal_eval(results_str)
                                    break
                                except:
                                    try:
                                        results_data = json.loads(results_str)
                                        break
                                    except:
                                        logger.warning("Could not parse results from notebook")
                    
                    if results_data:
                        break
        
        return results_data
        
    except Exception as e:
        logger.error(f"Error extracting results: {str(e)}")
        return None


def format_simulation_output(
    raw_results: Dict[str, Any],
    notebook_path: str,
    execution_time: float
) -> IXSimulationOutput:
    """
    Format raw simulation results into structured output schema.
    """
    # Extract treated water quality
    treated_water_raw = raw_results.get("treated_water", {})
    
    # Validate for suspicious default values
    ion_concentrations = treated_water_raw.get("ion_concentrations_mg_L", {})
    uniform_10000_count = sum(1 for conc in ion_concentrations.values() if abs(conc - 10000) < 0.1)
    
    if uniform_10000_count > 3:
        logger.info(f"INFO: Detected {uniform_10000_count} ions with concentration ~10000 mg/L")
        logger.info("This may indicate MCAS fallback to 0.5 mol/L default - check unit conversions")
        # Add info to recommendations (less prominent)
        if "recommendations" not in raw_results:
            raw_results["recommendations"] = []
        raw_results["recommendations"].append(
            "INFO: Some ions show ~10000 mg/L concentration. If unexpected, verify unit conversions in the notebook.")
    
    treated_water = MCASWaterComposition(
        flow_m3_hr=treated_water_raw.get("flow_m3_hr", 0),
        temperature_celsius=treated_water_raw.get("temperature_celsius", 25),
        pressure_bar=treated_water_raw.get("pressure_bar", 4),
        pH=treated_water_raw.get("pH", 7),
        ion_concentrations_mg_L=ion_concentrations
    )
    
    # Extract IX performance metrics
    ix_performance = {}
    for stage_name, metrics in raw_results.get("ix_performance", {}).items():
        ix_performance[stage_name] = IXPerformanceMetrics(
            breakthrough_time_hours=metrics.get("breakthrough_time_hours", 0),
            bed_volumes_treated=metrics.get("bed_volumes_treated", 0),
            regenerant_consumption_kg=metrics.get("regenerant_consumption_kg", 0),
            average_hardness_leakage_mg_L=metrics.get("average_hardness_leakage_mg_L", 0),
            capacity_utilization_percent=metrics.get("capacity_utilization_percent", 0)
        )
    
    # Extract degasser performance
    degasser_performance = raw_results.get("degasser_performance", {
        "influent_CO2_mg_L": 0,
        "effluent_CO2_mg_L": 0,
        "efficiency_percent": 0,
        "power_consumption_kW": 0
    })
    
    # Extract acid requirements
    acid_requirements = raw_results.get("acid_requirements")
    
    # Extract water quality progression
    water_quality_progression = []
    for stage_data in raw_results.get("water_quality_progression", []):
        water_quality_progression.append(WaterQualityProgression(
            stage=stage_data.get("stage", ""),
            pH=stage_data.get("pH", 7),
            temperature_celsius=stage_data.get("temperature_celsius", 25),
            ion_concentrations_mg_L=stage_data.get("ion_concentrations_mg_L", {}),
            alkalinity_mg_L_CaCO3=stage_data.get("alkalinity_mg_L_CaCO3", 0),
            hardness_mg_L_CaCO3=stage_data.get("hardness_mg_L_CaCO3", 0),
            tds_mg_L=stage_data.get("tds_mg_L", 0)
        ))
    
    # Extract economics
    economics = raw_results.get("economics", {
        "capital_cost": 0,
        "operating_cost_annual": 0,
        "cost_per_m3": 0
    })
    
    # Extract recommendations
    recommendations = raw_results.get("recommendations", [])
    
    # Create output object
    return IXSimulationOutput(
        status="success",
        watertap_notebook_path=notebook_path,
        model_type=raw_results.get("model_type", "phreeqc"),
        actual_runtime_seconds=execution_time,
        treated_water=treated_water,
        ix_performance=ix_performance,
        degasser_performance=degasser_performance,
        acid_requirements=acid_requirements,
        water_quality_progression=water_quality_progression,
        economics=economics,
        detailed_results=raw_results.get("detailed_results"),
        recommendations=recommendations if recommendations else None
    )


def simulate_ix_system(input_data: IXSimulationInput) -> IXSimulationOutput:
    """
    Execute WaterTAP/PhreeqPy simulation for ion exchange system performance.
    
    This function executes a parameterized Jupyter notebook to ensure process isolation,
    preventing conflicts between WaterTAP/PhreeqPy and the MCP server. The notebook:
    1. Creates WaterTAP flowsheet with custom IX unit models
    2. Uses PhreeqPy for multi-component ion exchange calculations
    3. Simulates breakthrough curves with Na+ competition
    4. Calculates regenerant requirements
    5. Performs economic analysis
    
    Args:
        input_data: IXSimulationInput containing:
            - configuration: Output from optimize_ix_configuration
            - water_analysis: Feed water in MCAS format (same requirements as optimize tool)
            - breakthrough_criteria: Performance targets (e.g., hardness < 5 mg/L)
            - regenerant_parameters: Chemical types and concentrations
            - simulation_options: Computational settings
    
    Water Composition Requirements:
        Same as optimize_ix_configuration - must use MCAS notation:
        - Cations: Na_+, Ca_2+, Mg_2+, K_+, H_+, NH4_+, Fe_2+, Fe_3+
        - Anions: Cl_-, SO4_2-, HCO3_-, CO3_2-, NO3_-, PO4_3-, F_-, OH_-
        - Neutrals: CO2, H2O, SiO2, B(OH)3
        
        Non-standard ions will be logged but won't affect calculations.
    
    Returns:
        IXSimulationOutput containing:
        - status: "success", "partial_success", or "error"
        - watertap_notebook_path: Path to executed notebook for audit trail
        - treated_water: Effluent quality in MCAS format (for RO feed)
        - ix_performance: Breakthrough times, capacity utilization, regenerant use
        - degasser_performance: CO2 removal efficiency
        - water_quality_progression: Stage-by-stage water quality
        - economics: CAPEX, OPEX, cost per m³
        - detailed_results: Breakthrough curves and other detailed data
        - recommendations: Operational guidance based on results
    
    Simulation Approach:
        - Executes in isolated subprocess via papermill to prevent conflicts
        - Uses PhreeqPy EXCHANGE blocks for multi-component modeling
        - Accounts for competitive ion exchange (Na+ vs hardness)
        - Models pH changes through exchange cycles
        - Includes kinetic factors for realistic breakthrough
        - Calculates regeneration requirements and waste volumes
    
    Note:
        Notebook execution is REQUIRED (not optional) to ensure process isolation.
        This prevents WaterTAP/PhreeqPy from conflicting with the MCP server.
    """
    start_time = time.time()
    
    # Ensure papermill is available
    if pm is None:
        raise ImportError("papermill is required for notebook execution. Please install with: pip install papermill")
    
    # Prepare parameters
    parameters = prepare_simulation_parameters(input_data)
    
    # Setup paths
    template_dir = Path(__file__).parent.parent / "notebooks"
    output_dir = Path(__file__).parent.parent / "results"
    output_dir.mkdir(exist_ok=True)
    
    # Use unified template for all flowsheet types
    flowsheet_type = input_data.configuration.flowsheet_type
    
    # Choose template based on simulation options
    use_graybox = input_data.simulation_options.get('use_graybox', False)
    
    if use_graybox:
        template_name = "ix_simulation_graybox_template.ipynb"
        logger.info("Using GrayBox model template for automatic mass balance enforcement")
    else:
        # Use CLI wrapper for consistent results with ix_cli.py
        template_name = "ix_simulation_cli_wrapper.ipynb"
        logger.info("Using CLI wrapper for consistent results with ix_cli.py")
    
    template_path = template_dir / template_name
    
    # Verify template exists
    if not template_path.exists():
        raise FileNotFoundError(
            f"Template not found at {template_path}. "
            f"Please ensure {template_name} exists in the notebooks directory."
        )
    
    # Generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"ix_simulation_{flowsheet_type}_{timestamp}.ipynb"
    output_path = output_dir / output_filename
    
    # Execute notebook
    model_type = "graybox" if use_graybox else "watertap_direct_phreeqc"
    logger.info(f"Starting IX simulation for {flowsheet_type} flowsheet using {model_type} model")
    logger.info(f"Output notebook: {output_path}")
    
    start_time = time.time()
    
    try:
        pm.execute_notebook(
            str(template_path),
            str(output_path),
            parameters=parameters,
            kernel_name="python3",
            start_timeout=60,
            execution_timeout=1800  # 30 minutes max
        )
        
        execution_time = time.time() - start_time
        logger.info(f"Notebook execution completed in {execution_time:.1f} seconds")
        
        # Extract results
        raw_results = extract_results_from_notebook(output_path)
        
        if raw_results:
            # Format and return results
            return format_simulation_output(
                raw_results,
                str(output_path),
                execution_time
            )
        else:
            # Return partial success with notebook path
            return IXSimulationOutput(
                status="partial_success",
                watertap_notebook_path=str(output_path),
                model_type="phreeqc",
                actual_runtime_seconds=execution_time,
                treated_water=input_data.water_analysis,  # Return input as fallback
                ix_performance={},
                degasser_performance={},
                water_quality_progression=[],
                economics={},
                recommendations=["Simulation completed but results extraction failed. Check notebook manually."]
            )
            
    except Exception as e:
        logger.error(f"Error in simulate_ix_system: {str(e)}")
        
        # Return error output
        return IXSimulationOutput(
            status="error",
            watertap_notebook_path=str(output_path) if output_path.exists() else "",
            model_type="phreeqc",
            actual_runtime_seconds=time.time() - start_time,
            treated_water=input_data.water_analysis,  # Return input as fallback
            ix_performance={},
            degasser_performance={},
            water_quality_progression=[],
            economics={},
            recommendations=[f"Simulation failed: {str(e)}"]
        )


def simulate_ix_system_graybox(input_data: IXSimulationInput) -> IXSimulationOutput:
    """
    Execute GrayBox simulation for ion exchange system.
    
    This is a convenience function that ensures the GrayBox model is used
    for automatic mass balance enforcement and robust optimization.
    
    The GrayBox model provides:
    - Automatic mass balance enforcement through Pyomo constraints
    - Proper Jacobian calculation for efficient optimization
    - No manual variable updates or constraint fixing required
    - Follows the proven Reaktoro-PSE integration pattern
    
    Args:
        input_data: Same as simulate_ix_system
        
    Returns:
        IXSimulationOutput with GrayBox model results
    """
    # Ensure GrayBox option is enabled
    if 'simulation_options' not in input_data.__dict__:
        input_data.simulation_options = {}
    
    input_data.simulation_options['use_graybox'] = True
    input_data.simulation_options['model_type'] = 'graybox'
    
    logger.info("Executing GrayBox simulation with automatic mass balance enforcement")
    
    # Call main simulation function with GrayBox enabled
    return simulate_ix_system(input_data)


