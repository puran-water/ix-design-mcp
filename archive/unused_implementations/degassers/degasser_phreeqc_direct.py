"""
Direct PHREEQC-based Degasser Model

Uses phreeqpython directly for chemistry calculations, avoiding water-chemistry-mcp complexity.
This approach allows for future kinetic modeling of CO2 stripping.
"""

import logging
from typing import Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Check if phreeqpython is available
try:
    import phreeqpython
    PHREEQPY_AVAILABLE = True
except ImportError:
    PHREEQPY_AVAILABLE = False
    logger.warning("phreeqpython not available")


class PhreeqcDegasser:
    """
    Degasser model using direct PHREEQC calculations.
    
    Supports:
    - Acid addition (HCl, H2SO4)
    - CO2 stripping to atmospheric equilibrium
    - Future kinetic modeling capabilities
    """
    
    def __init__(self, database: str = "phreeqc.dat"):
        """Initialize with PHREEQC database."""
        if not PHREEQPY_AVAILABLE:
            raise ImportError("phreeqpython is required for PhreeqcDegasser")
        
        self.pp = phreeqpython.PhreeqPython(database=database)
        logger.info(f"PhreeqcDegasser initialized with database: {database}")
    
    def create_solution(self, water_composition: Dict[str, Any]) -> phreeqpython.Solution:
        """
        Create a PHREEQC solution from water composition.
        
        Args:
            water_composition: Dict with:
                - ion_concentrations_mg_L: Dict of ion concentrations
                - pH: Initial pH
                - temperature_celsius: Temperature
                - alkalinity_mg_L_CaCO3: Optional alkalinity
        
        Returns:
            phreeqpython Solution object
        """
        # Build solution dict for phreeqpython
        solution_dict = {
            'pH': water_composition.get('pH', 7.0),
            'temp': water_composition.get('temperature_celsius', 25.0),
            'units': 'mg/L'
        }
        
        # Add ions
        ion_mapping = {
            'Na_+': 'Na',
            'Ca_2+': 'Ca',
            'Mg_2+': 'Mg',
            'K_+': 'K',
            'Cl_-': 'Cl',
            'SO4_2-': 'S(6)',
            'HCO3_-': 'C(4)',
            'NO3_-': 'N(5)',
            'F_-': 'F'
        }
        
        for ion, element in ion_mapping.items():
            if ion in water_composition.get('ion_concentrations_mg_L', {}):
                conc = water_composition['ion_concentrations_mg_L'][ion]
                solution_dict[element] = conc
        
        # Handle alkalinity if specified
        if 'alkalinity_mg_L_CaCO3' in water_composition:
            solution_dict['Alkalinity'] = water_composition['alkalinity_mg_L_CaCO3']
        
        # Create solution
        return self.pp.add_solution(solution_dict)
    
    def add_acid(self, solution: phreeqpython.Solution, 
                 acid_type: str, dose_mmol_L: float) -> phreeqpython.Solution:
        """
        Add acid to solution using REACTION block.
        
        Args:
            solution: phreeqpython solution
            acid_type: 'HCl' or 'H2SO4'
            dose_mmol_L: Acid dose in mmol/L
            
        Returns:
            New solution after acid addition
        """
        # Create PHREEQC input string
        solution_num = solution.number
        
        phreeqc_input = f"""
SOLUTION {solution_num}
    temp {solution.temperature}
    pH {solution.pH}
    units mg/L
"""
        
        # Add all elements
        for element, conc in solution.total_element.items():
            if element != 'H' and element != 'O':
                # Convert mol/L to mg/L based on element
                if element == 'Ca':
                    mg_L = conc * 40.08 * 1000
                elif element == 'Mg':
                    mg_L = conc * 24.31 * 1000
                elif element == 'Na':
                    mg_L = conc * 22.99 * 1000
                elif element == 'K':
                    mg_L = conc * 39.10 * 1000
                elif element == 'Cl':
                    mg_L = conc * 35.45 * 1000
                elif element == 'S(6)':
                    mg_L = conc * 32.07 * 1000  # As S
                elif element == 'C(4)':
                    mg_L = conc * 12.01 * 1000  # As C
                else:
                    continue
                phreeqc_input += f"    {element} {mg_L:.6f}\n"
        
        # Add reaction block
        phreeqc_input += f"""
REACTION 1
    {acid_type} 1.0
    {dose_mmol_L} mmol
SAVE SOLUTION 2
END
"""
        
        # Run simulation
        self.pp.ip.run_string(phreeqc_input)
        
        # Return new solution
        return self.pp.get_solution(2)
    
    def equilibrate_with_co2(self, solution: phreeqpython.Solution,
                           pCO2_atm: float = 10**-3.5) -> phreeqpython.Solution:
        """
        Equilibrate solution with atmospheric CO2.
        
        Args:
            solution: phreeqpython solution
            pCO2_atm: CO2 partial pressure in atmospheres
            
        Returns:
            New solution after CO2 equilibration
        """
        # Create PHREEQC input
        solution_num = solution.number
        
        phreeqc_input = f"""
USE SOLUTION {solution_num}
EQUILIBRIUM_PHASES 1
    CO2(g) {np.log10(pCO2_atm)} 10
SAVE SOLUTION 3
END
"""
        
        # Run simulation
        self.pp.ip.run_string(phreeqc_input)
        
        # Return equilibrated solution
        return self.pp.get_solution(3)
    
    def calculate_degasser_performance(self,
                                     initial_water: Dict[str, Any],
                                     acid_type: str = 'HCl',
                                     acid_dose_mmol_L: float = 5.0,
                                     equilibrate_with_air: bool = True) -> Dict[str, Any]:
        """
        Calculate complete degasser performance.
        
        Args:
            initial_water: Initial water composition
            acid_type: Type of acid
            acid_dose_mmol_L: Acid dose
            equilibrate_with_air: Whether to strip CO2 to atmospheric equilibrium
            
        Returns:
            Complete performance metrics
        """
        # Create initial solution
        sol_initial = self.create_solution(initial_water)
        
        # Store initial values
        initial_pH = sol_initial.pH
        initial_alk = sol_initial.alkalinity  # meq/L
        initial_alk_mg_L = initial_alk * 50  # Convert to mg/L as CaCO3
        initial_dic = sol_initial.total('C(4)')  # mol/L
        initial_co2 = sol_initial.species.get('CO2', 0) * 44.01 * 1000  # mg/L
        initial_hco3 = sol_initial.species.get('HCO3-', 0) * 61.02 * 1000  # mg/L
        
        # Step 1: Add acid
        sol_acid = self.add_acid(sol_initial, acid_type, acid_dose_mmol_L)
        
        acid_pH = sol_acid.pH
        acid_alk = sol_acid.alkalinity * 50  # mg/L as CaCO3
        acid_co2 = sol_acid.species.get('CO2', 0) * 44.01 * 1000  # mg/L
        acid_hco3 = sol_acid.species.get('HCO3-', 0) * 61.02 * 1000  # mg/L
        
        # Step 2: CO2 stripping (if enabled)
        if equilibrate_with_air:
            sol_final = self.equilibrate_with_co2(sol_acid)
            
            final_pH = sol_final.pH
            final_alk = sol_final.alkalinity * 50  # mg/L as CaCO3
            final_co2 = sol_final.species.get('CO2', 0) * 44.01 * 1000  # mg/L
            final_hco3 = sol_final.species.get('HCO3-', 0) * 61.02 * 1000  # mg/L
            final_dic = sol_final.total('C(4)')  # mol/L
        else:
            final_pH = acid_pH
            final_alk = acid_alk
            final_co2 = acid_co2
            final_hco3 = acid_hco3
            final_dic = sol_acid.total('C(4)')
        
        # Calculate CO2 removed
        co2_removed_mol_L = initial_dic - final_dic
        co2_removed_mg_L = co2_removed_mol_L * 44.01 * 1000
        
        # Build results
        results = {
            'initial': {
                'pH': initial_pH,
                'alkalinity_mg_L_CaCO3': initial_alk_mg_L,
                'CO2_mg_L': initial_co2,
                'HCO3_mg_L': initial_hco3,
                'DIC_mol_L': initial_dic
            },
            'after_acid': {
                'pH': acid_pH,
                'alkalinity_mg_L_CaCO3': acid_alk,
                'CO2_mg_L': acid_co2,
                'HCO3_mg_L': acid_hco3,
                'CO2_increase_mg_L': acid_co2 - initial_co2
            },
            'final': {
                'pH': final_pH,
                'alkalinity_mg_L_CaCO3': final_alk,
                'CO2_mg_L': final_co2,
                'HCO3_mg_L': final_hco3,
                'DIC_mol_L': final_dic
            },
            'performance': {
                'alkalinity_reduction_percent': (initial_alk_mg_L - final_alk) / initial_alk_mg_L * 100 if initial_alk_mg_L > 0 else 0,
                'HCO3_reduction_percent': (initial_hco3 - final_hco3) / initial_hco3 * 100 if initial_hco3 > 0 else 0,
                'CO2_removed_mg_L': co2_removed_mg_L,
                'CO2_removed_mol_L': co2_removed_mol_L,
                'pH_change': final_pH - initial_pH
            },
            'operating_conditions': {
                'acid_type': acid_type,
                'acid_dose_mmol_L': acid_dose_mmol_L,
                'CO2_stripping': equilibrate_with_air
            }
        }
        
        # Add ionic strength info
        results['initial']['ionic_strength'] = sol_initial.I
        results['final']['ionic_strength'] = sol_final.I if equilibrate_with_air else sol_acid.I
        
        # Add saturation indices if available
        try:
            results['initial']['SI_calcite'] = sol_initial.si('Calcite')
            results['final']['SI_calcite'] = sol_final.si('Calcite') if equilibrate_with_air else sol_acid.si('Calcite')
        except:
            pass
        
        return results
    
    def optimize_acid_dose(self,
                         initial_water: Dict[str, Any],
                         target_alkalinity_reduction_percent: float,
                         acid_type: str = 'HCl',
                         max_dose_mmol_L: float = 20.0) -> Dict[str, Any]:
        """
        Find optimal acid dose to achieve target alkalinity reduction.
        
        Uses bisection method to find the dose.
        """
        # Get initial alkalinity
        sol_initial = self.create_solution(initial_water)
        initial_alk = sol_initial.alkalinity * 50  # mg/L as CaCO3
        target_alk = initial_alk * (1 - target_alkalinity_reduction_percent / 100)
        
        # Bisection search
        dose_low = 0.0
        dose_high = max_dose_mmol_L
        tolerance = 0.01  # mmol/L
        
        for i in range(20):  # Max iterations
            dose_mid = (dose_low + dose_high) / 2
            
            # Test this dose
            result = self.calculate_degasser_performance(
                initial_water, acid_type, dose_mid, equilibrate_with_air=True
            )
            
            achieved_alk = result['final']['alkalinity_mg_L_CaCO3']
            
            if abs(achieved_alk - target_alk) < 1.0:  # Within 1 mg/L
                return {
                    'optimal_dose_mmol_L': dose_mid,
                    'achieved_alkalinity_mg_L': achieved_alk,
                    'target_alkalinity_mg_L': target_alk,
                    'iterations': i + 1,
                    'performance': result
                }
            
            if achieved_alk > target_alk:
                # Need more acid
                dose_low = dose_mid
            else:
                # Too much acid
                dose_high = dose_mid
        
        # Return best effort
        return {
            'optimal_dose_mmol_L': dose_mid,
            'achieved_alkalinity_mg_L': achieved_alk,
            'target_alkalinity_mg_L': target_alk,
            'iterations': 20,
            'converged': False,
            'performance': result
        }


# Example usage function
def example_degasser_calculation():
    """Example calculation showing typical usage."""
    if not PHREEQPY_AVAILABLE:
        print("phreeqpython not available")
        return
    
    # Create degasser
    degasser = PhreeqcDegasser()
    
    # Define water composition
    water = {
        'ion_concentrations_mg_L': {
            'Na_+': 50,
            'Ca_2+': 40,
            'Mg_2+': 10,
            'Cl_-': 100,
            'HCO3_-': 244  # 200 mg/L as CaCO3 alkalinity
        },
        'pH': 7.5,
        'temperature_celsius': 25,
        'alkalinity_mg_L_CaCO3': 200
    }
    
    # Calculate performance
    results = degasser.calculate_degasser_performance(
        water,
        acid_type='HCl',
        acid_dose_mmol_L=5.0,
        equilibrate_with_air=True
    )
    
    # Print results
    print("Degasser Performance:")
    print(f"  Initial: pH {results['initial']['pH']:.2f}, Alk {results['initial']['alkalinity_mg_L_CaCO3']:.1f} mg/L")
    print(f"  After acid: pH {results['after_acid']['pH']:.2f}, Alk {results['after_acid']['alkalinity_mg_L_CaCO3']:.1f} mg/L")
    print(f"  Final: pH {results['final']['pH']:.2f}, Alk {results['final']['alkalinity_mg_L_CaCO3']:.1f} mg/L")
    print(f"  Alkalinity reduction: {results['performance']['alkalinity_reduction_percent']:.1f}%")
    print(f"  CO2 removed: {results['performance']['CO2_removed_mg_L']:.1f} mg/L")
    
    return results