#!/usr/bin/env python
"""
Example usage of IX Design MCP Server
Demonstrates both configuration and simulation tools
"""

import json
import asyncio
from typing import Dict, Any

# This is a mock example - in practice you would use an MCP client library
# For example: from mcp import Client

async def example_ix_design():
    """Example workflow for IX system design"""
    
    # Step 1: Define water analysis
    water_analysis = {
        "flow_m3_hr": 150,
        "temperature_celsius": 25,
        "pressure_bar": 1.0,
        "pH": 7.5,
        "ion_concentrations_mg_L": {
            "Na_+": 200,      # Sodium
            "Ca_2+": 100,     # Calcium 
            "Mg_2+": 40,      # Magnesium
            "K_+": 5,         # Potassium
            "HCO3_-": 250,    # Bicarbonate (alkalinity)
            "Cl_-": 350,      # Chloride
            "SO4_2-": 150,    # Sulfate
            "NO3_-": 10,      # Nitrate
            "SiO2": 20        # Silica
        }
    }
    
    # Step 2: Get all configuration options
    print("=" * 60)
    print("STEP 1: Generating IX Configuration Options")
    print("=" * 60)
    
    config_request = {
        "tool": "optimize_ix_configuration",
        "arguments": {
            "water_analysis": water_analysis,
            "design_criteria": {
                "min_runtime_hours": 12,
                "max_vessels_per_stage": 3
            }
        }
    }
    
    # In practice: config_result = await client.call_tool(**config_request)
    # Mock result structure:
    config_result = {
        "status": "success",
        "configurations": [
            {
                "flowsheet_type": "h_wac_degasser_na_wac",
                "flowsheet_description": "Weak acid cation (H-form) → Degasser → Weak acid cation (Na-form)",
                "economics": {
                    "capital_cost_usd": 3400000,
                    "annual_opex_usd": 850000,
                    "cost_per_m3": 1.58
                },
                "characteristics": {
                    "suitability": "Best for >90% temporary hardness",
                    "advantages": ["Lower chemical costs", "Acid recovery possible"],
                    "challenges": ["pH control critical", "CO2 handling required"]
                }
            },
            {
                "flowsheet_type": "sac_na_wac_degasser", 
                "flowsheet_description": "Strong acid cation → Weak acid cation → Degasser",
                "economics": {
                    "capital_cost_usd": 3200000,
                    "annual_opex_usd": 920000,
                    "cost_per_m3": 1.65
                },
                "characteristics": {
                    "suitability": "Best for mixed hardness types",
                    "advantages": ["Complete hardness removal", "Robust operation"],
                    "challenges": ["Higher salt consumption", "More waste brine"]
                }
            },
            {
                "flowsheet_type": "na_wac_degasser",
                "flowsheet_description": "Weak acid cation (Na-form) → Degasser",
                "economics": {
                    "capital_cost_usd": 2100000,
                    "annual_opex_usd": 680000,
                    "cost_per_m3": 1.15
                },
                "characteristics": {
                    "suitability": "Simple water, low hardness",
                    "advantages": ["Simple operation", "Lower capital cost"],
                    "challenges": ["Limited hardness removal", "Not for high TDS"]
                }
            }
        ],
        "water_chemistry_analysis": {
            "total_hardness_mg_L_CaCO3": 389,
            "temporary_hardness_mg_L_CaCO3": 205,
            "permanent_hardness_mg_L_CaCO3": 184,
            "temporary_hardness_fraction": 0.53,
            "na_concentration_mg_L": 200,
            "na_competition_factor": 0.82
        }
    }
    
    # Display results
    print("\nWater Chemistry Analysis:")
    print(f"  Total Hardness: {config_result['water_chemistry_analysis']['total_hardness_mg_L_CaCO3']} mg/L as CaCO3")
    print(f"  Temporary/Permanent: {config_result['water_chemistry_analysis']['temporary_hardness_fraction']:.0%} / {1-config_result['water_chemistry_analysis']['temporary_hardness_fraction']:.0%}")
    print(f"  Na+ Competition Factor: {config_result['water_chemistry_analysis']['na_competition_factor']:.2f}")
    
    print("\nConfiguration Options:")
    for i, config in enumerate(config_result['configurations'], 1):
        print(f"\n{i}. {config['flowsheet_description']}")
        print(f"   CAPEX: ${config['economics']['capital_cost_usd']:,.0f}")
        print(f"   OPEX: ${config['economics']['annual_opex_usd']:,.0f}/year")
        print(f"   LCOW: ${config['economics']['cost_per_m3']:.2f}/m³")
        print(f"   Best for: {config['characteristics']['suitability']}")
    
    # Step 3: Select configuration (example: lowest LCOW)
    selected_config = min(config_result['configurations'], 
                         key=lambda x: x['economics']['cost_per_m3'])
    
    print("\n" + "=" * 60)
    print("STEP 2: Simulating Selected Configuration")
    print("=" * 60)
    print(f"Selected: {selected_config['flowsheet_type']} (Lowest LCOW)")
    
    # Step 4: Run detailed simulation
    sim_request = {
        "tool": "simulate_ix_system",
        "arguments": {
            "configuration": selected_config,
            "water_analysis": water_analysis,
            "simulation_options": {
                "model_type": "direct",
                "max_bed_volumes": 1000,
                "time_steps": 24
            }
        }
    }
    
    # In practice: sim_result = await client.call_tool(**sim_request)
    # Mock result structure:
    sim_result = {
        "status": "success",
        "ix_performance": {
            "Na-WAC": {
                "breakthrough_time_hours": 24,
                "bed_volumes_treated": 385,
                "regenerant_consumption_kg": 245,
                "average_hardness_leakage_mg_L": 8.5,
                "waste_volume_m3": 45
            }
        },
        "treated_water": {
            "pH": 8.2,
            "ion_concentrations_mg_L": {
                "Na_+": 389,
                "Ca_2+": 6.8,
                "Mg_2+": 1.7,
                "HCO3_-": 205,
                "Cl_-": 350,
                "SO4_2-": 150
            }
        },
        "economics": {
            "cost_per_cycle": 185,
            "annual_chemical_cost": 340000,
            "waste_disposal_cost_annual": 125000
        }
    }
    
    # Display simulation results
    print("\nSimulation Results:")
    for vessel, performance in sim_result['ix_performance'].items():
        print(f"\n{vessel} Performance:")
        print(f"  Runtime: {performance['breakthrough_time_hours']} hours")
        print(f"  Throughput: {performance['bed_volumes_treated']} BV")
        print(f"  Regenerant: {performance['regenerant_consumption_kg']} kg")
        print(f"  Hardness Leakage: {performance['average_hardness_leakage_mg_L']} mg/L")
    
    print("\nTreated Water Quality:")
    print(f"  pH: {sim_result['treated_water']['pH']}")
    print(f"  Residual Hardness: {sim_result['treated_water']['ion_concentrations_mg_L']['Ca_2+'] + sim_result['treated_water']['ion_concentrations_mg_L']['Mg_2+']*0.65:.1f} mg/L as CaCO3")
    
    print("\nOperating Economics:")
    print(f"  Cost per regeneration: ${sim_result['economics']['cost_per_cycle']}")
    print(f"  Annual chemical cost: ${sim_result['economics']['annual_chemical_cost']:,.0f}")
    
    print("\n" + "=" * 60)
    print("IX System Design Complete!")
    print("=" * 60)


if __name__ == "__main__":
    # Run the example
    asyncio.run(example_ix_design())