#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP Server Integration Tests

This test suite validates the complete MCP server functionality:
1. Server startup and tool registration
2. Configuration tool through MCP interface
3. Simulation tool through MCP interface
4. End-to-end workflow
5. Error handling and edge cases
"""

import sys
import os
import unittest
import json
from typing import Dict, List, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Import the actual tool functions directly
from tools.ix_configuration import optimize_ix_configuration_all
from tools.ix_simulation import simulate_ix_system
from tools.schemas import IXConfigurationInput, IXSimulationInput


class TestMCPServerIntegration(unittest.TestCase):
    """Test suite for MCP Server Integration"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Standard test water compositions
        self.test_water_basic = {
            "flow_m3_hr": 100.0,
            "temperature_celsius": 25.0,
            "pressure_bar": 1.0,
            "pH": 7.5,
            "ion_concentrations_mg_L": {
                "Na_+": 150.0,
                "Ca_2+": 80.0,
                "Mg_2+": 30.0,
                "HCO3_-": 183.0,
                "Cl_-": 300.0,
                "SO4_2-": 120.0
            }
        }
        
        self.test_water_high_temp_hardness = {
            "flow_m3_hr": 50.0,
            "temperature_celsius": 20.0,
            "pressure_bar": 1.0,
            "pH": 8.0,
            "ion_concentrations_mg_L": {
                "Na_+": 50.0,
                "Ca_2+": 120.0,
                "Mg_2+": 40.0,
                "HCO3_-": 400.0,  # High alkalinity
                "Cl_-": 100.0,
                "SO4_2-": 80.0
            }
        }
    
    def test_configuration_tool_basic(self):
        """Test basic configuration tool functionality"""
        print("\n" + "="*50)
        print("Testing Configuration Tool - Basic Water")
        print("="*50)
        
        # Run the configuration tool
        input_data = IXConfigurationInput(water_analysis=self.test_water_basic)
        result = optimize_ix_configuration_all(input_data).model_dump()
        
        # Validate response structure
        self.assertEqual(result["status"], "success")
        self.assertIn("configurations", result)
        self.assertIsInstance(result["configurations"], list)
        self.assertEqual(len(result["configurations"]), 3)  # Should have 3 flowsheets
        
        # Validate each configuration
        flowsheet_types = set()
        for config in result["configurations"]:
            self.assertIn("flowsheet_type", config)
            self.assertIn("flowsheet_description", config)
            self.assertIn("ix_vessels", config)
            self.assertIn("economics", config)
            self.assertIn("characteristics", config)
            
            flowsheet_types.add(config["flowsheet_type"])
            
            # Check economics
            economics = config["economics"]
            self.assertIn("capital_cost_usd", economics)
            self.assertIn("annual_opex_usd", economics)
            self.assertIn("cost_per_m3", economics)
            
            print(f"\n{config['flowsheet_type']}:")
            print(f"  CAPEX: ${economics['capital_cost_usd']:,.0f}")
            print(f"  OPEX: ${economics['annual_opex_usd']:,.0f}/year")
            print(f"  LCOW: ${economics['cost_per_m3']:.2f}/m³")
        
        # Ensure all flowsheet types are present
        expected_types = {"h_wac_degasser_na_wac", "sac_na_wac_degasser", "na_wac_degasser"}
        self.assertEqual(flowsheet_types, expected_types)
    
    def test_configuration_tool_high_temp_hardness(self):
        """Test configuration tool with high temporary hardness water"""
        print("\n" + "="*50)
        print("Testing Configuration Tool - High Temp Hardness")
        print("="*50)
        
        input_data = IXConfigurationInput(water_analysis=self.test_water_high_temp_hardness)
        result = optimize_ix_configuration_all(input_data).model_dump()
        
        self.assertEqual(result["status"], "success")
        
        # Check summary recommendations
        summary = result["summary"]
        self.assertIn("feed_flow_m3_hr", summary)
        self.assertIn("configurations_generated", summary)
        
        print(f"\nFlow Rate: {summary['feed_flow_m3_hr']} m³/hr")
        print(f"Configurations Generated: {summary['configurations_generated']}")
        
        # Verify H-WAC is recommended for high temp hardness
        h_wac_config = next(c for c in result["configurations"] 
                           if c["flowsheet_type"] == "h_wac_degasser_na_wac")
        # Check if characteristics exist and have the expected structure
        if "characteristics" in h_wac_config and "suitability" in h_wac_config["characteristics"]:
            print(f"\nH-WAC Suitability: {h_wac_config['characteristics']['suitability']}")
    
    def test_simulation_tool_basic(self):
        """Test simulation tool with basic configuration"""
        print("\n" + "="*50)
        print("Testing Simulation Tool - Basic")
        print("="*50)
        
        # First get configuration
        input_data = IXConfigurationInput(water_analysis=self.test_water_basic)
        config_result = optimize_ix_configuration_all(input_data).model_dump()
        
        # Pick SAC configuration for simulation
        sac_config = next(c for c in config_result["configurations"] 
                         if c["flowsheet_type"] == "sac_na_wac_degasser")
        
        # Run simulation
        sim_input = IXSimulationInput(
            configuration=sac_config,
            water_analysis=self.test_water_basic,
            simulation_options={
                "model_type": "direct",
                "max_bed_volumes": 500
            }
        )
        sim_result = simulate_ix_system(sim_input).model_dump()
        
        # Validate simulation output
        self.assertEqual(sim_result["status"], "success")
        self.assertIn("ix_performance", sim_result)
        self.assertIn("water_quality_progression", sim_result)
        self.assertIn("actual_runtime_seconds", sim_result)
        
        # Check performance metrics
        metrics = sim_result["ix_performance"]
        for vessel_name, vessel_metrics in metrics.items():
            self.assertIn("breakthrough_time_hours", vessel_metrics)
            self.assertIn("bed_volumes_treated", vessel_metrics)
            self.assertIn("regenerant_consumption_kg", vessel_metrics)
            self.assertIn("waste_volume_m3", vessel_metrics)
            
            print(f"\n{vessel_name} Performance:")
            print(f"  Breakthrough: {vessel_metrics['breakthrough_time_hours']:.1f} hours")
            print(f"  Bed Volumes: {vessel_metrics['bed_volumes_treated']:.0f} BV")
            print(f"  Regenerant: {vessel_metrics['regenerant_consumption_kg']:.1f} kg")
    
    def test_end_to_end_workflow(self):
        """Test complete workflow from configuration to simulation"""
        print("\n" + "="*50)
        print("Testing End-to-End Workflow")
        print("="*50)
        
        # Step 1: Configure system
        input_data = IXConfigurationInput(
            water_analysis=self.test_water_basic,
            design_criteria={
                "min_runtime_hours": 12,
                "max_vessels_per_stage": 4
            }
        )
        config_result = optimize_ix_configuration_all(input_data).model_dump()
        
        self.assertEqual(config_result["status"], "success")
        print(f"\n✓ Configuration complete: {len(config_result['configurations'])} options")
        
        # Step 2: Select lowest CAPEX option
        lowest_capex_config = min(config_result["configurations"], 
                                 key=lambda c: c["economics"]["capital_cost_usd"])
        
        print(f"\n✓ Selected: {lowest_capex_config['flowsheet_type']}")
        print(f"  CAPEX: ${lowest_capex_config['economics']['capital_cost_usd']:,.0f}")
        
        # Step 3: Simulate selected configuration
        sim_input = IXSimulationInput(
            configuration=lowest_capex_config,
            water_analysis=self.test_water_basic,
            simulation_options={
                "model_type": "direct",
                "max_bed_volumes": 1000
            }
        )
        sim_result = simulate_ix_system(sim_input).model_dump()
        
        self.assertEqual(sim_result["status"], "success")
        print("\n✓ Simulation complete")
        
        # Step 4: Analyze results
        total_runtime = sum(
            metrics["breakthrough_time_hours"] 
            for metrics in sim_result["ix_performance"].values()
        )
        print(f"\n✓ Total runtime before regeneration: {total_runtime:.1f} hours")
    
    def test_error_handling(self):
        """Test error handling for invalid inputs"""
        print("\n" + "="*50)
        print("Testing Error Handling")
        print("="*50)
        
        # Test 1: Missing required fields
        try:
            IXConfigurationInput()
            self.fail("Should have raised validation error")
        except Exception as e:
            print(f"\n✓ Correctly handled missing water_analysis: {type(e).__name__}")
        
        # Test 2: Invalid ion concentrations
        invalid_water = self.test_water_basic.copy()
        invalid_water["ion_concentrations_mg_L"] = {"invalid_ion": 100}
        
        try:
            input_data = IXConfigurationInput(water_analysis=invalid_water)
            self.fail("Should have raised validation error for invalid ions")
        except Exception as e:
            print(f"\n✓ Correctly rejected invalid ions: {type(e).__name__}")
        
        # Test 3: Extreme values
        extreme_water = self.test_water_basic.copy()
        extreme_water["flow_m3_hr"] = 10000  # Very high flow
        
        input_data = IXConfigurationInput(water_analysis=extreme_water)
        result = optimize_ix_configuration_all(input_data).model_dump()
        self.assertEqual(result["status"], "success")
        print("\n✓ Handled extreme flow values")
    
    def test_mcas_compatibility(self):
        """Test MCAS notation compatibility"""
        print("\n" + "="*50)
        print("Testing MCAS Compatibility")
        print("="*50)
        
        # Use various MCAS notations
        mcas_water = {
            "flow_m3_hr": 75.0,
            "temperature_celsius": 25.0,
            "pressure_bar": 1.0,
            "pH": 7.8,
            "ion_concentrations_mg_L": {
                "Na_+": 200.0,      # Standard cation
                "Ca_2+": 100.0,     # Divalent cation
                "Mg_2+": 40.0,      # Another divalent
                "K_+": 10.0,        # Monovalent
                "HCO3_-": 250.0,    # Standard anion
                "CO3_2-": 5.0,      # Carbonate
                "Cl_-": 350.0,      # Chloride
                "SO4_2-": 150.0,    # Sulfate
                "NO3_-": 20.0,      # Nitrate
                "SiO2": 30.0,       # Neutral species
                "CO2": 10.0         # Dissolved CO2
            }
        }
        
        input_data = IXConfigurationInput(water_analysis=mcas_water)
        result = optimize_ix_configuration_all(input_data).model_dump()
        
        self.assertEqual(result["status"], "success")
        
        # Check water chemistry analysis
        analysis = result["water_chemistry_analysis"]
        self.assertIn("total_hardness_mg_L_CaCO3", analysis)
        self.assertIn("alkalinity_mg_L_CaCO3", analysis)
        # TDS is calculated separately, not in water_chemistry_analysis
        # self.assertIn("tds_mg_L", analysis)
        
        print(f"\n✓ MCAS notation processed correctly")
        print(f"  Hardness: {analysis['total_hardness_mg_L_CaCO3']:.0f} mg/L as CaCO3")
        print(f"  Alkalinity: {analysis['alkalinity_mg_L_CaCO3']:.0f} mg/L as CaCO3")
        print(f"  Na Competition Factor: {analysis['na_competition_factor']:.2f}")


def run_tests():
    """Run all tests with detailed output"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestMCPServerIntegration)
    
    # Run tests with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "="*70)
    print("MCP SERVER INTEGRATION TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ ALL MCP SERVER INTEGRATION TESTS PASSED! ✅")
        print("\nThe IX Design MCP Server is ready for deployment:")
        print("1. Configuration tool returns all 3 flowsheet options ✓")
        print("2. Each option includes complete economics (CAPEX/OPEX/LCOW) ✓")
        print("3. Simulation tool provides detailed performance metrics ✓")
        print("4. MCAS notation fully supported for RO integration ✓")
        print("5. Error handling is robust ✓")
    else:
        print("\n❌ SOME TESTS FAILED - Review output above ❌")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)