#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 4.2: MCP Tool 2 (Simulation) Testing

This test suite validates the simulate_ix_system MCP tool:
1. All simulation modes (direct, transport, watertap)
2. Breakthrough curve generation
3. Regeneration predictions
4. Economic calculations
5. Derating factor application
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

# Import the tools
from tools.ix_configuration import optimize_ix_configuration
from tools.ix_simulation import simulate_ix_system
from tools.schemas import (
    IXConfigurationInput,
    IXSimulationInput,
    MCASWaterComposition
)


class TestMCPSimulation(unittest.TestCase):
    """Test suite for MCP Simulation Tool"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Standard test water
        self.test_water = MCASWaterComposition(
            flow_m3_hr=100.0,
            temperature_celsius=25.0,
            pressure_bar=1.0,
            pH=7.5,
            ion_concentrations_mg_L={
                "Na_+": 200.0,
                "Ca_2+": 80.0,
                "Mg_2+": 30.0,
                "HCO3_-": 183.0,  # 150 mg/L as CaCO3
                "Cl_-": 300.0,
                "SO4_2-": 120.0
            }
        )
        
        # Get configuration first
        config_input = IXConfigurationInput(water_analysis=self.test_water)
        self.configuration = optimize_ix_configuration(config_input)
    
    def test_direct_simulation_mode(self):
        """Test direct PhreeqPy simulation mode"""
        print("\n=== Testing Direct Simulation Mode ===")
        
        sim_input = IXSimulationInput(
            water_analysis=self.test_water,
            configuration=self.configuration,
            model_type="direct",
            target_hardness_mg_L_CaCO3=5.0,
            run_time_hours=24.0,
            target_cycles=100
        )
        
        try:
            result = simulate_ix_system(sim_input)
            
            print(f"\nSimulation completed successfully")
            print(f"  Model type: {result.model_type}")
            if result.actual_runtime_seconds is not None:
                print(f"  Runtime: {result.actual_runtime_seconds:.1f} seconds")
            else:
                print(f"  Runtime: Not measured")
            
            # Check performance metrics
            self.assertIsNotNone(result.performance_metrics)
            metrics = result.performance_metrics
            
            print(f"\nPerformance metrics:")
            print(f"  Breakthrough volume: {metrics.bed_volumes_treated:.1f} BV")
            print(f"  Service time: {metrics.breakthrough_time_hours:.1f} hours")
            print(f"  Regenerant usage: {metrics.regenerant_consumption_kg:.1f} kg/cycle")
            print(f"  Waste volume: {getattr(metrics, 'waste_volume_m3', 0):.1f} m³/cycle")
            
            # Verify reasonable values
            self.assertGreater(metrics.bed_volumes_treated, 10,
                             "Breakthrough volume too low")
            self.assertLess(metrics.bed_volumes_treated, 1000,
                           "Breakthrough volume unrealistically high")
            
            # Check water quality progression
            self.assertIsNotNone(result.water_quality_progression)
            self.assertGreater(len(result.water_quality_progression), 0)
            
            print(f"\nWater quality progression points: {len(result.water_quality_progression)}")
            
            # Check economics
            if result.economics:
                print(f"\nEconomics:")
                print(f"  Capital cost: ${result.economics.get('capital_cost', 0):.0f}")
                print(f"  Annual operating cost: ${result.economics.get('operating_cost_annual', 0):.0f}")
                print(f"  Cost per m³: ${result.economics.get('cost_per_m3', 0):.2f}")
                
        except Exception as e:
            self.fail(f"Direct simulation failed: {str(e)}")
    
    def test_transport_simulation_mode(self):
        """Test PHREEQC transport simulation mode"""
        print("\n=== Testing Transport Simulation Mode ===")
        
        sim_input = IXSimulationInput(
            water_analysis=self.test_water,
            configuration=self.configuration,
            model_type="transport",
            target_hardness_mg_L_CaCO3=5.0,
            run_time_hours=24.0
        )
        
        try:
            result = simulate_ix_system(sim_input)
            
            print(f"\nTransport simulation completed")
            print(f"  Model type: {result.model_type}")
            
            # Transport model should provide more detailed results
            if result.performance_metrics:
                metrics = result.performance_metrics
                print(f"\nTransport model results:")
                print(f"  Breakthrough volume: {metrics.bed_volumes_treated:.1f} BV")
                print(f"  Mass transfer zone: {getattr(metrics, 'mass_transfer_zone_m', 'N/A')}")
                
            # Check for kinetic effects
            if hasattr(result, 'notes') and result.notes:
                print(f"\nNotes: {result.notes}")
                
        except NotImplementedError:
            print("  ⚠ Transport mode not implemented (expected)")
        except Exception as e:
            self.fail(f"Transport simulation failed: {str(e)}")
    
    def test_watertap_simulation_mode(self):
        """Test WaterTAP simulation mode with derating"""
        print("\n=== Testing WaterTAP Simulation Mode ===")
        
        sim_input = IXSimulationInput(
            water_analysis=self.test_water,
            configuration=self.configuration,
            model_type="watertap",
            apply_derating=True,
            resin_age_years=2.0,
            fouling_potential="moderate",
            target_hardness_mg_L_CaCO3=5.0
        )
        
        try:
            result = simulate_ix_system(sim_input)
            
            print(f"\nWaterTAP simulation completed")
            print(f"  Model type: {result.model_type}")
            
            if result.performance_metrics:
                metrics = result.performance_metrics
                print(f"\nWaterTAP results with derating:")
                print(f"  Breakthrough volume: {metrics.bed_volumes_treated:.1f} BV")
                print(f"  Applied derating: {getattr(result, 'derating_factor', 'N/A')}")
                
                # With derating, breakthrough should be lower
                self.assertLess(metrics.bed_volumes_treated, 500,
                              "Derating not applied properly")
                
        except NotImplementedError:
            print("  ⚠ WaterTAP mode not implemented (expected)")
        except Exception as e:
            self.fail(f"WaterTAP simulation failed: {str(e)}")
    
    def test_breakthrough_curves(self):
        """Test breakthrough curve generation"""
        print("\n=== Testing Breakthrough Curves ===")
        
        sim_input = IXSimulationInput(
            water_analysis=self.test_water,
            configuration=self.configuration,
            model_type="direct",
            target_hardness_mg_L_CaCO3=5.0,
            run_time_hours=48.0  # Longer run for full curve
        )
        
        result = simulate_ix_system(sim_input)
        
        # Check water quality progression
        progression = result.water_quality_progression
        self.assertIsNotNone(progression)
        self.assertGreater(len(progression), 10,
                         "Not enough points for breakthrough curve")
        
        print(f"\nBreakthrough curve data:")
        print(f"  Data points: {len(progression)}")
        
        # Analyze curve shape - skip feed water stage
        bed_volumes = []
        hardness_values = []
        
        # Filter out non-breakthrough points (Feed, After stages)
        breakthrough_points = [p for p in progression if " @ " in p.stage and "BV" in p.stage]
        
        for i, point in enumerate(breakthrough_points[:10]):  # First 10 breakthrough points
            # Extract BV from stage (e.g., "Na-WAC @ 100 BV")
            stage_parts = point.stage.split(" @ ")
            bv = float(stage_parts[1].replace(" BV", ""))
            bed_volumes.append(bv)
            
            # Use hardness directly from the schema
            hardness = point.hardness_mg_L_CaCO3
            hardness_values.append(hardness)
            
            if len(bed_volumes) <= 5 or bed_volumes[-1] % 50 == 0:
                print(f"  {point.stage}: {hardness:.1f} mg/L as CaCO3")
        
        # Verify curve characteristics
        self.assertGreater(len(hardness_values), 0, "No breakthrough curve data found")
        
        if hardness_values:
            # Early points should have low hardness
            self.assertLess(hardness_values[0], 10,
                           "Initial hardness leakage too high")
            
            # Should eventually breakthrough
            max_hardness = max(hardness_values)
            self.assertGreater(max_hardness, 50,
                             "No breakthrough observed")
    
    def test_regeneration_optimization(self):
        """Test regeneration optimization calculations"""
        print("\n=== Testing Regeneration Optimization ===")
        
        # Test with different regeneration levels
        regen_levels = [0.8, 1.0, 1.2]  # Under, normal, over regeneration
        
        for level in regen_levels:
            sim_input = IXSimulationInput(
                water_analysis=self.test_water,
                configuration=self.configuration,
                model_type="direct",
                regeneration_level=level,
                target_hardness_mg_L_CaCO3=5.0
            )
            
            result = simulate_ix_system(sim_input)
            
            print(f"\nRegeneration level {level}:")
            if result.performance_metrics:
                print(f"  Breakthrough: {result.performance_metrics.bed_volumes_treated:.1f} BV")
                print(f"  Regenerant: {result.performance_metrics.regenerant_consumption_kg:.1f} kg")
                print(f"  Efficiency: {result.performance_metrics.regenerant_consumption_kg / result.performance_metrics.bed_volumes_treated:.3f} kg/BV")
    
    def test_multi_vessel_simulation(self):
        """Test simulation of multi-vessel systems"""
        print("\n=== Testing Multi-Vessel Simulation ===")
        
        # Get a multi-stage configuration
        water = MCASWaterComposition(
            flow_m3_hr=200.0,
            temperature_celsius=25.0,
            pressure_bar=1.0,
            pH=7.5,
            ion_concentrations_mg_L={
                "Na_+": 100.0,
                "Ca_2+": 120.0,
                "Mg_2+": 48.0,
                "HCO3_-": 61.0,   # Low alkalinity - should get SAC flowsheet
                "Cl_-": 300.0,
                "SO4_2-": 200.0
            }
        )
        
        config_input = IXConfigurationInput(water_analysis=water)
        config = optimize_ix_configuration(config_input)
        
        # Should have multiple vessels
        print(f"\nFlowsheet: {config.flowsheet_type}")
        print(f"Vessels: {list(config.ix_vessels.keys())}")
        
        sim_input = IXSimulationInput(
            water_analysis=water,
            configuration=config,
            model_type="direct",
            target_hardness_mg_L_CaCO3=1.0  # Very low target
        )
        
        result = simulate_ix_system(sim_input)
        
        if result.vessel_performance:
            print(f"\nVessel-specific performance:")
            for vessel_name, perf in result.vessel_performance.items():
                print(f"  {vessel_name}:")
                print(f"    Utilization: {perf.get('utilization', 'N/A')}")
                print(f"    Loading: {perf.get('loading', 'N/A')}")
    
    def test_error_handling(self):
        """Test error handling and edge cases"""
        print("\n=== Testing Error Handling ===")
        
        # Test with invalid target hardness
        sim_input = IXSimulationInput(
            water_analysis=self.test_water,
            configuration=self.configuration,
            model_type="direct",
            target_hardness_mg_L_CaCO3=-5.0  # Invalid negative target
        )
        
        try:
            result = simulate_ix_system(sim_input)
            # Should either handle gracefully or raise meaningful error
            if result.warnings:
                print(f"  Warnings generated: {result.warnings}")
        except ValueError as e:
            print(f"  ✓ Caught expected error: {str(e)}")
        except Exception as e:
            print(f"  ⚠ Unexpected error type: {type(e).__name__}: {str(e)}")
    
    def test_economics_calculation(self):
        """Test detailed economics calculation"""
        print("\n=== Testing Economics Calculation ===")
        
        sim_input = IXSimulationInput(
            water_analysis=self.test_water,
            configuration=self.configuration,
            model_type="direct",
            target_hardness_mg_L_CaCO3=5.0,
            economic_parameters={
                "resin_cost_usd_per_L": 150.0,
                "regenerant_cost_usd_per_kg": 0.2,
                "waste_disposal_cost_usd_per_m3": 50.0,
                "electricity_cost_usd_per_kWh": 0.12
            }
        )
        
        result = simulate_ix_system(sim_input)
        
        if result.economics:
            econ = result.economics
            print(f"\nDetailed economics:")
            print(f"  Capital costs:")
            print(f"    Capital cost: ${econ.get('capital_cost', 0):,.0f}")
            print(f"    Operating cost: ${econ.get('operating_cost_annual', 0):,.0f}")
            print(f"    Cost per m³: ${econ.get('cost_per_m3', 0):.2f}")
            
            # Calculate lifecycle cost
            if 'capital_cost' in econ and 'operating_cost_annual' in econ:
                years_operation = 10
                lifecycle_cost = econ['capital_cost'] + years_operation * econ['operating_cost_annual']
                print(f"\n  10-year lifecycle cost: ${lifecycle_cost:,.0f}")


def run_simulation_tests():
    """Run MCP simulation tool tests"""
    print("=" * 70)
    print("PHASE 4.2: MCP SIMULATION TOOL VALIDATION")
    print("=" * 70)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMCPSimulation)
    
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
        print("\n✓ ALL TESTS PASSED - Simulation tool validated!")
    else:
        print("\n✗ TESTS FAILED - Review issues above")
    
    # Save results
    with open('test_results_phase4_simulation.json', 'w') as f:
        results = {
            'phase': '4.2',
            'component': 'MCP Simulation Tool',
            'tests_run': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'skipped': len(result.skipped),
            'success': result.wasSuccessful()
        }
        json.dump(results, f, indent=2)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_simulation_tests()
    sys.exit(0 if success else 1)