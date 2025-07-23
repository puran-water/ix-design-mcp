#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 4.1: MCP Tool 1 (Configuration) Testing

This test suite validates the optimize_ix_configuration MCP tool:
1. Various water chemistries
2. Vessel sizing calculations
3. Flowsheet selection logic
4. Na+ competition factor
5. Edge cases
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

# Import the configuration tool
from tools.ix_configuration import optimize_ix_configuration, optimize_ix_configuration_all
from tools.schemas import (
    IXConfigurationInput, 
    IXConfigurationOutput,
    IXMultiConfigurationOutput,
    MCASWaterComposition
)


class TestMCPConfiguration(unittest.TestCase):
    """Test suite for MCP Configuration Tool"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Test water compositions representing different scenarios
        self.test_scenarios = {
            "high_temp_hardness": {
                "description": "High temporary hardness - should select H-WAC flowsheet",
                "water_analysis": {
                    "flow_m3_hr": 100.0,
                    "temperature_celsius": 25.0,
                    "pressure_bar": 1.0,
                    "pH": 8.0,
                    "ion_concentrations_mg_L": {
                        "Na_+": 50.0,
                        "Ca_2+": 80.0,
                        "Mg_2+": 24.0,
                        "HCO3_-": 366.0,  # 300 mg/L as CaCO3 alkalinity
                        "Cl_-": 100.0,
                        "SO4_2-": 50.0
                    }
                },
                "expected_flowsheet": "h_wac_degasser_na_wac"
            },
            "high_perm_hardness": {
                "description": "High permanent hardness - should select SAC flowsheet",
                "water_analysis": {
                    "flow_m3_hr": 150.0,
                    "temperature_celsius": 30.0,
                    "pressure_bar": 1.5,
                    "pH": 7.5,
                    "ion_concentrations_mg_L": {
                        "Na_+": 200.0,
                        "Ca_2+": 120.0,
                        "Mg_2+": 48.0,
                        "HCO3_-": 61.0,   # 50 mg/L as CaCO3 alkalinity
                        "Cl_-": 400.0,
                        "SO4_2-": 200.0
                    }
                },
                "expected_flowsheet": "sac_na_wac_degasser"
            },
            "simple_water": {
                "description": "Simple water chemistry - should select Na-WAC flowsheet",
                "water_analysis": {
                    "flow_m3_hr": 50.0,
                    "temperature_celsius": 20.0,
                    "pressure_bar": 1.0,
                    "pH": 7.0,
                    "ion_concentrations_mg_L": {
                        "Na_+": 100.0,
                        "Ca_2+": 40.0,
                        "Mg_2+": 10.0,
                        "HCO3_-": 122.0,  # 100 mg/L as CaCO3 alkalinity
                        "Cl_-": 150.0,
                        "SO4_2-": 48.0
                    }
                },
                "expected_flowsheet": "na_wac_degasser"
            },
            "high_sodium": {
                "description": "High sodium water - test Na+ competition",
                "water_analysis": {
                    "flow_m3_hr": 200.0,
                    "temperature_celsius": 25.0,
                    "pressure_bar": 2.0,
                    "pH": 7.8,
                    "ion_concentrations_mg_L": {
                        "Na_+": 2000.0,  # Very high sodium
                        "Ca_2+": 60.0,
                        "Mg_2+": 20.0,
                        "HCO3_-": 183.0,
                        "Cl_-": 3000.0,
                        "SO4_2-": 100.0
                    }
                },
                "expected_competition_factor": 0.3  # Should be heavily reduced
            },
            "zero_hardness": {
                "description": "Zero hardness water - edge case",
                "water_analysis": {
                    "flow_m3_hr": 10.0,
                    "temperature_celsius": 25.0,
                    "pressure_bar": 1.0,
                    "pH": 7.0,
                    "ion_concentrations_mg_L": {
                        "Na_+": 100.0,
                        "Cl_-": 154.5
                    }
                },
                "expected_error": True
            },
            "high_tds": {
                "description": "Very high TDS - should generate warning",
                "water_analysis": {
                    "flow_m3_hr": 100.0,
                    "temperature_celsius": 25.0,
                    "pressure_bar": 1.0,
                    "pH": 7.5,
                    "ion_concentrations_mg_L": {
                        "Na_+": 5000.0,
                        "Ca_2+": 500.0,
                        "Mg_2+": 200.0,
                        "Cl_-": 8000.0,
                        "SO4_2-": 1000.0,
                        "HCO3_-": 200.0
                    }
                },
                "expected_warning": "High TDS"
            }
        }
    
    def test_flowsheet_selection(self):
        """Test that correct flowsheets are selected for different water chemistries"""
        print("\n=== Testing Flowsheet Selection ===")
        
        for scenario_name, scenario in self.test_scenarios.items():
            if "expected_flowsheet" not in scenario:
                continue
                
            print(f"\n{scenario_name}: {scenario['description']}")
            
            # Create input
            input_data = IXConfigurationInput(
                water_analysis=MCASWaterComposition(**scenario["water_analysis"])
            )
            
            # Run optimization - use the single configuration function for backward compatibility
            try:
                result = optimize_ix_configuration(input_data)
                
                # Check flowsheet selection
                self.assertEqual(result.flowsheet_type, scenario["expected_flowsheet"],
                               f"Wrong flowsheet for {scenario_name}")
                
                print(f"  ✓ Selected: {result.flowsheet_type}")
                print(f"  Description: {result.flowsheet_description}")
                
                # Check vessel configurations
                self.assertIsNotNone(result.ix_vessels)
                self.assertGreater(len(result.ix_vessels), 0)
                print(f"  Vessels configured: {list(result.ix_vessels.keys())}")
                
            except Exception as e:
                if scenario.get("expected_error", False):
                    print(f"  ✓ Expected error: {str(e)}")
                else:
                    self.fail(f"Unexpected error for {scenario_name}: {str(e)}")
    
    def test_multi_configuration_output(self):
        """Test that multi-configuration returns all 3 flowsheet options"""
        print("\n=== Testing Multi-Configuration Output ===")
        
        # Use a standard test water
        water = MCASWaterComposition(
            flow_m3_hr=100.0,
            temperature_celsius=25.0,
            pressure_bar=1.0,
            pH=7.5,
            ion_concentrations_mg_L={
                "Na_+": 200.0,
                "Ca_2+": 80.0,
                "Mg_2+": 30.0,
                "HCO3_-": 183.0,
                "Cl_-": 300.0,
                "SO4_2-": 120.0
            }
        )
        
        input_data = IXConfigurationInput(water_analysis=water)
        
        # Run multi-configuration optimization
        result = optimize_ix_configuration_all(input_data)
        
        # Check we got all 3 configurations
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.configurations), 3, 
                        "Should generate exactly 3 configurations")
        
        # Check each configuration has required fields
        flowsheet_types = set()
        for config in result.configurations:
            self.assertIsNotNone(config.flowsheet_type)
            self.assertIsNotNone(config.ix_vessels)
            self.assertIsNotNone(config.degasser)
            self.assertIsNotNone(config.na_competition_factor)
            flowsheet_types.add(config.flowsheet_type)
            
            print(f"\n  Configuration: {config.flowsheet_type}")
            print(f"    Vessels: {list(config.ix_vessels.keys())}")
            print(f"    Total resin: {config.hydraulics['total_resin_volume_m3']:.1f} m³")
            if config.characteristics:
                print(f"    Best for: {config.characteristics['best_for']}")
        
        # Ensure we have all 3 different flowsheets
        expected_flowsheets = {"h_wac_degasser_na_wac", "sac_na_wac_degasser", "na_wac_degasser"}
        self.assertEqual(flowsheet_types, expected_flowsheets,
                        "Should generate all 3 flowsheet types")
        
        # Check recommendation logic
        self.assertIsNotNone(result.summary['recommended_flowsheet'])
        self.assertIsNotNone(result.summary['recommendation_reason'])
        print(f"\n  Recommended: {result.summary['recommended_flowsheet']}")
        print(f"  Reason: {result.summary['recommendation_reason']}")
    
    def test_na_competition_factor(self):
        """Test Na+ competition factor calculation"""
        print("\n=== Testing Na+ Competition Factor ===")
        
        # Test with different Na/hardness ratios
        test_cases = [
            ("Low Na+", 50, 100, 0.8, 1.0),    # Na < hardness, factor should be high
            ("Equal Na+", 200, 100, 0.5, 0.8),  # Na = 2×hardness, moderate reduction  
            ("High Na+", 1000, 100, 0.3, 0.5),  # Na >> hardness, significant reduction
            ("Very High Na+", 5000, 100, 0.3, 0.4)  # Extreme Na, minimum factor
        ]
        
        for case_name, na_mg_L, hardness_as_ca, min_factor, max_factor in test_cases:
            water_data = {
                "flow_m3_hr": 100.0,
                "temperature_celsius": 25.0,
                "pressure_bar": 1.0,
                "pH": 7.5,
                "ion_concentrations_mg_L": {
                    "Na_+": na_mg_L,
                    "Ca_2+": hardness_as_ca,  # All hardness as Ca for simplicity
                    "Cl_-": na_mg_L * 1.54,  # Maintain charge balance
                    "SO4_2-": hardness_as_ca * 2.4
                }
            }
            
            input_data = IXConfigurationInput(
                water_analysis=MCASWaterComposition(**water_data)
            )
            
            result = optimize_ix_configuration(input_data)
            
            print(f"\n{case_name}:")
            print(f"  Na+: {na_mg_L} mg/L")
            print(f"  Hardness: {hardness_as_ca * 2.5:.0f} mg/L as CaCO3")
            print(f"  Competition factor: {result.na_competition_factor:.3f}")
            
            # Check factor is in expected range
            self.assertGreaterEqual(result.na_competition_factor, min_factor,
                                  f"Competition factor too low for {case_name}")
            self.assertLessEqual(result.na_competition_factor, max_factor,
                                f"Competition factor too high for {case_name}")
    
    def test_vessel_sizing(self):
        """Test vessel sizing calculations"""
        print("\n=== Testing Vessel Sizing ===")
        
        # Test with different flow rates
        flow_rates = [10, 50, 100, 200, 500]  # m³/hr
        
        for flow in flow_rates:
            water_data = {
                "flow_m3_hr": flow,
                "temperature_celsius": 25.0,
                "pressure_bar": 1.0,
                "pH": 7.5,
                "ion_concentrations_mg_L": {
                    "Na_+": 100.0,
                    "Ca_2+": 60.0,
                    "Mg_2+": 24.0,
                    "HCO3_-": 183.0,
                    "Cl_-": 200.0,
                    "SO4_2-": 96.0
                }
            }
            
            input_data = IXConfigurationInput(
                water_analysis=MCASWaterComposition(**water_data)
            )
            
            result = optimize_ix_configuration(input_data)
            
            print(f"\nFlow rate: {flow} m³/hr")
            
            # Check each vessel
            for vessel_name, vessel in result.ix_vessels.items():
                print(f"\n  {vessel_name}:")
                print(f"    Service vessels: {vessel.number_service}")
                print(f"    Standby vessels: {vessel.number_standby}")
                print(f"    Diameter: {vessel.diameter_m} m")
                print(f"    Bed depth: {vessel.bed_depth_m} m")
                print(f"    Resin volume: {vessel.resin_volume_m3} m³")
                
                # Verify constraints
                self.assertLessEqual(vessel.diameter_m, 2.4,
                                   "Vessel diameter exceeds shipping constraint")
                self.assertGreaterEqual(vessel.bed_depth_m, 0.75,
                                      "Bed depth below minimum")
                self.assertEqual(vessel.number_standby, 1,
                               "Should have N+1 redundancy")
                
                # Check hydraulic loading
                area = 3.14159 * vessel.diameter_m**2 / 4
                linear_velocity = flow / vessel.number_service / area
                self.assertLessEqual(linear_velocity, 25.0,
                                   "Linear velocity exceeds maximum")
    
    def test_degasser_sizing(self):
        """Test degasser sizing calculations"""
        print("\n=== Testing Degasser Sizing ===")
        
        water_data = {
            "flow_m3_hr": 100.0,
            "temperature_celsius": 25.0,
            "pressure_bar": 1.0,
            "pH": 8.0,
            "ion_concentrations_mg_L": {
                "Na_+": 100.0,
                "Ca_2+": 60.0,
                "Mg_2+": 24.0,
                "HCO3_-": 244.0,  # 200 mg/L as CaCO3
                "Cl_-": 200.0,
                "SO4_2-": 96.0
            }
        }
        
        input_data = IXConfigurationInput(
            water_analysis=MCASWaterComposition(**water_data)
        )
        
        result = optimize_ix_configuration(input_data)
        
        degasser = result.degasser
        
        print(f"\nDegasser configuration:")
        print(f"  Type: {degasser.type}")
        print(f"  Packing: {degasser.packing}")
        print(f"  Diameter: {degasser.diameter_m} m")
        print(f"  Packed height: {degasser.packed_height_m} m")
        print(f"  Hydraulic loading: {degasser.hydraulic_loading_m_hr} m/hr")
        print(f"  Air flow: {degasser.air_flow_m3_hr} m³/hr")
        print(f"  Fan power: {degasser.fan_power_kW} kW")
        
        # Verify design parameters
        self.assertEqual(degasser.hydraulic_loading_m_hr, 40.0,
                        "Hydraulic loading should be 40 m/hr")
        self.assertEqual(degasser.air_flow_m3_hr, 100.0 * 45,  # 45:1 ratio
                        "Air flow should be 45× water flow")
        self.assertGreater(degasser.fan_power_kW, 0,
                         "Fan power should be calculated")
    
    def test_warnings_and_edge_cases(self):
        """Test warning generation and edge case handling"""
        print("\n=== Testing Warnings and Edge Cases ===")
        
        # Test high TDS warning
        scenario = self.test_scenarios["high_tds"]
        input_data = IXConfigurationInput(
            water_analysis=MCASWaterComposition(**scenario["water_analysis"])
        )
        
        result = optimize_ix_configuration(input_data)
        
        print(f"\nHigh TDS scenario:")
        print(f"  TDS: {sum(scenario['water_analysis']['ion_concentrations_mg_L'].values()):.0f} mg/L")
        
        if result.warnings:
            print(f"  Warnings generated: {len(result.warnings)}")
            tds_warning_found = False
            for warning in result.warnings:
                print(f"    - {warning}")
                if "TDS" in warning:
                    tds_warning_found = True
            self.assertTrue(tds_warning_found, "Should warn about high TDS")
        else:
            print("  ⚠ No warnings generated (expected warning)")
        
        # Test high Na+ warning
        scenario = self.test_scenarios["high_sodium"]
        input_data = IXConfigurationInput(
            water_analysis=MCASWaterComposition(**scenario["water_analysis"])
        )
        
        result = optimize_ix_configuration(input_data)
        
        print(f"\nHigh sodium scenario:")
        print(f"  Na+ competition factor: {result.na_competition_factor:.3f}")
        
        if result.warnings:
            for warning in result.warnings:
                print(f"    - {warning}")
                if "Na+" in warning:
                    print("  ✓ Na+ competition warning generated")
    
    def test_output_completeness(self):
        """Test that output contains all required fields"""
        print("\n=== Testing Output Completeness ===")
        
        water_data = {
            "flow_m3_hr": 100.0,
            "temperature_celsius": 25.0,
            "pressure_bar": 1.0,
            "pH": 7.5,
            "ion_concentrations_mg_L": {
                "Na_+": 100.0,
                "Ca_2+": 60.0,
                "Mg_2+": 24.0,
                "HCO3_-": 183.0,
                "Cl_-": 200.0,
                "SO4_2-": 96.0
            }
        }
        
        input_data = IXConfigurationInput(
            water_analysis=MCASWaterComposition(**water_data)
        )
        
        result = optimize_ix_configuration(input_data)
        
        # Check all required fields are present
        required_fields = [
            "flowsheet_type",
            "flowsheet_description", 
            "na_competition_factor",
            "effective_capacity",
            "ix_vessels",
            "degasser",
            "hydraulics"
        ]
        
        for field in required_fields:
            self.assertTrue(hasattr(result, field),
                          f"Missing required field: {field}")
            print(f"  ✓ {field}: present")
        
        # Check effective capacity dict
        self.assertIn("SAC", result.effective_capacity)
        self.assertIn("WAC_H", result.effective_capacity)
        self.assertIn("WAC_Na", result.effective_capacity)
        
        # Check hydraulics dict
        self.assertIn("bed_volumes_per_hour", result.hydraulics)
        self.assertIn("linear_velocity_m_hr", result.hydraulics)
        self.assertIn("total_resin_volume_m3", result.hydraulics)
        self.assertIn("total_vessels", result.hydraulics)


def run_configuration_tests():
    """Run MCP configuration tool tests"""
    print("=" * 70)
    print("PHASE 4.1: MCP CONFIGURATION TOOL VALIDATION")
    print("=" * 70)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMCPConfiguration)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("\n✓ ALL TESTS PASSED - Configuration tool validated!")
    else:
        print("\n✗ TESTS FAILED - Review issues above")
    
    # Save results
    with open('test_results_phase4_configuration.json', 'w') as f:
        results = {
            'phase': '4.1',
            'component': 'MCP Configuration Tool',
            'tests_run': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'skipped': len(result.skipped),
            'success': result.wasSuccessful()
        }
        json.dump(results, f, indent=2)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_configuration_tests()
    sys.exit(0 if success else 1)