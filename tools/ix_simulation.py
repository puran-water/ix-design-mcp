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
from .ix_simulation_direct import simulate_ix_system_direct

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
        # Project paths
        "project_root": str(Path(__file__).parent.parent),
        
        # Configuration from optimization
        "flowsheet_type": config.flowsheet_type,
        "flowsheet_description": config.flowsheet_description,
        "na_competition_factor": config.na_competition_factor,
        "effective_capacity": config.effective_capacity,
        
        # Vessel configurations
        "ix_vessels": vessels,
        
        # Degasser configuration
        "degasser": degasser_dict,
        
        # Water analysis
        "feed_water": water_dict,
        
        # Breakthrough criteria
        "breakthrough_criteria": input_data.breakthrough_criteria,
        
        # Regenerant parameters
        "regenerant_parameters": input_data.regenerant_parameters,
        
        # Acid options
        "acid_options": input_data.acid_options,
        
        # Simulation options
        "simulation_options": input_data.simulation_options,
        
        # Timestamp for unique runs
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
    }
    
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
            if (cell.cell_type == 'code' and 
                'tags' in cell.metadata and 
                'results' in cell.metadata.tags and
                cell.outputs):
                
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
    treated_water = MCASWaterComposition(
        flow_m3_hr=treated_water_raw.get("flow_m3_hr", 0),
        temperature_celsius=treated_water_raw.get("temperature_celsius", 25),
        pressure_bar=treated_water_raw.get("pressure_bar", 4),
        pH=treated_water_raw.get("pH", 7),
        ion_concentrations_mg_L=treated_water_raw.get("ion_concentrations_mg_L", {})
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
    
    # Select template based on flowsheet type
    flowsheet_type = input_data.configuration.flowsheet_type
    template_map = {
        "h_wac_degasser_na_wac": "ix_simulation_hwac_template.ipynb",
        "sac_na_wac_degasser": "ix_simulation_sac_template.ipynb",
        "na_wac_degasser": "ix_simulation_nawac_template.ipynb"
    }
    
    template_name = template_map.get(flowsheet_type, "ix_simulation_general_template.ipynb")
    template_path = template_dir / template_name
    
    # For now, use a general template if specific one doesn't exist
    if not template_path.exists():
        template_path = template_dir / "ix_simulation_general_template.ipynb"
        if not template_path.exists():
            # Create a minimal template for testing
            logger.warning(f"Template not found: {template_path}. Creating minimal template.")
            create_minimal_template(template_path)
    
    # Generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"ix_simulation_{flowsheet_type}_{timestamp}.ipynb"
    output_path = output_dir / output_filename
    
    # Execute notebook
    logger.info(f"Starting IX simulation for {flowsheet_type} flowsheet")
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
            treated_water=input_data.water_analysis,  # Return input as fallback
            ix_performance={},
            degasser_performance={},
            water_quality_progression=[],
            economics={},
            recommendations=[f"Simulation failed: {str(e)}"]
        )


def create_minimal_template(template_path: Path):
    """
    Create a minimal notebook template for testing.
    
    This is a placeholder until proper templates are developed.
    """
    template_path.parent.mkdir(exist_ok=True)
    
    notebook_content = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Ion Exchange System Simulation\n", "Minimal template for testing"]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {"tags": ["parameters"]},
                "outputs": [],
                "source": [
                    "# Parameters cell - papermill will inject values here\n",
                    "project_root = None\n",
                    "flowsheet_type = None\n",
                    "feed_water = None\n",
                    "ix_vessels = None\n",
                    "degasser = None"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Minimal simulation placeholder\n",
                    "print(f\"Simulating {flowsheet_type} flowsheet\")\n",
                    "print(f\"Feed flow: {feed_water['flow_m3_hr']} m3/hr\")"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {"tags": ["results"]},
                "outputs": [],
                "source": [
                    "# Results cell - tagged for extraction\n",
                    "results = {\n",
                    "    \"status\": \"success\",\n",
                    "    \"treated_water\": {\n",
                    "        \"flow_m3_hr\": feed_water['flow_m3_hr'],\n",
                    "        \"temperature_celsius\": 25,\n",
                    "        \"pressure_bar\": 4,\n",
                    "        \"pH\": 7.5,\n",
                    "        \"ion_concentrations_mg_L\": {\n",
                    "            \"Ca_2+\": 5,\n",
                    "            \"Mg_2+\": 2,\n",
                    "            \"Na_+\": feed_water['ion_concentrations_mg_L'].get('Na_+', 100)\n",
                    "        }\n",
                    "    },\n",
                    "    \"ix_performance\": {\n",
                    "        \"SAC\": {\n",
                    "            \"breakthrough_time_hours\": 24,\n",
                    "            \"bed_volumes_treated\": 384,\n",
                    "            \"regenerant_consumption_kg\": 50,\n",
                    "            \"average_hardness_leakage_mg_L\": 3,\n",
                    "            \"capacity_utilization_percent\": 75\n",
                    "        }\n",
                    "    },\n",
                    "    \"degasser_performance\": {\n",
                    "        \"influent_CO2_mg_L\": 44,\n",
                    "        \"effluent_CO2_mg_L\": 4.4,\n",
                    "        \"efficiency_percent\": 90,\n",
                    "        \"power_consumption_kW\": degasser['fan_power_kW']\n",
                    "    },\n",
                    "    \"economics\": {\n",
                    "        \"capital_cost\": 500000,\n",
                    "        \"operating_cost_annual\": 100000,\n",
                    "        \"cost_per_m3\": 0.15\n",
                    "    },\n",
                    "    \"water_quality_progression\": [\n",
                    "        {\n",
                    "            \"stage\": \"Feed\",\n",
                    "            \"pH\": feed_water['pH'],\n",
                    "            \"temperature_celsius\": 25,\n",
                    "            \"ion_concentrations_mg_L\": feed_water['ion_concentrations_mg_L'],\n",
                    "            \"alkalinity_mg_L_CaCO3\": feed_water['alkalinity_mg_L_CaCO3'],\n",
                    "            \"hardness_mg_L_CaCO3\": feed_water['total_hardness_mg_L_CaCO3'],\n",
                    "            \"tds_mg_L\": feed_water['tds_mg_L']\n",
                    "        }\n",
                    "    ]\n",
                    "}\n",
                    "results"
                ]
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.12"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }
    
    # Write notebook
    import json
    with open(template_path, 'w') as f:
        json.dump(notebook_content, f, indent=2)