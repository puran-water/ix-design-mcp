"""
MCAS-PHREEQC Translator Module

This module provides translation utilities between WaterTAP's MCAS 
(Multi-Component Aqueous Solution) property package and PHREEQC format.
"""

import logging
from typing import Dict, List, Any, Optional
from pyomo.environ import units as pyunits
from pyomo.environ import value
import numpy as np

logger = logging.getLogger(__name__)

# Ion charge data for electroneutrality checking
ION_CHARGES = {
    'Na_+': 1, 'K_+': 1, 'Ca_2+': 2, 'Mg_2+': 2, 'Ba_2+': 2, 'Sr_2+': 2,
    'Fe_2+': 2, 'Fe_3+': 3, 'Mn_2+': 2, 'Al_3+': 3, 'H_+': 1, 'NH4_+': 1,
    'Cl_-': -1, 'SO4_2-': -2, 'HCO3_-': -1, 'CO3_2-': -2, 'NO3_-': -1,
    'PO4_3-': -3, 'F_-': -1, 'OH_-': -1
}

# Molecular weights for common ions (g/mol)
MOLECULAR_WEIGHTS = {
    'Na_+': 22.99, 'K_+': 39.10, 'Ca_2+': 40.08, 'Mg_2+': 24.31, 
    'Ba_2+': 137.33, 'Sr_2+': 87.62, 'Fe_2+': 55.85, 'Fe_3+': 55.85,
    'Mn_2+': 54.94, 'Al_3+': 26.98, 'H_+': 1.01, 'NH4_+': 18.04,
    'Cl_-': 35.45, 'SO4_2-': 96.06, 'HCO3_-': 61.02, 'CO3_2-': 60.01,
    'NO3_-': 62.00, 'PO4_3-': 94.97, 'F_-': 19.00, 'OH_-': 17.01
}


class MCASPhreeqcTranslator:
    """Translator between MCAS property blocks and PHREEQC format"""
    
    def __init__(self):
        """Initialize translator with species mapping"""
        # Map MCAS component names to PHREEQC species
        self.species_map = {
            # Cations
            'Ca_2+': 'Ca+2',
            'Mg_2+': 'Mg+2', 
            'Na_+': 'Na+',
            'K_+': 'K+',
            'H_+': 'H+',
            'NH4_+': 'N(5)',  # Ammonium as N(+5) in PHREEQC
            'Fe_2+': 'Fe+2',
            'Fe_3+': 'Fe+3',
            'Mn_2+': 'Mn+2',
            'Ba_2+': 'Ba+2',
            'Sr_2+': 'Sr+2',
            'Al_3+': 'Al+3',
            # Anions
            'Cl_-': 'Cl-',
            'SO4_2-': 'SO4-2',
            'HCO3_-': 'HCO3-',
            'CO3_2-': 'CO3-2',
            'NO3_-': 'NO3-',
            'PO4_3-': 'PO4-3',
            'F_-': 'F-',
            'OH_-': 'OH-',
            # Neutral species
            'SiO2': 'Si',
            'H2O': 'H2O'
        }
        
        # Reverse mapping
        self.phreeqc_to_mcas = {v: k for k, v in self.species_map.items()}
        
        # Special handling for alkalinity
        self.alkalinity_species = ['HCO3_-', 'CO3_2-', 'OH_-']
        
        # Common molecular weights
        self.molecular_weights = MOLECULAR_WEIGHTS.copy()
        
    def mcas_to_phreeqc_solution(self, mcas_state, solution_number: int = 1) -> str:
        """
        Convert MCAS state block to PHREEQC SOLUTION block
        
        Args:
            mcas_state: MCAS property state block
            solution_number: PHREEQC solution number
            
        Returns:
            PHREEQC SOLUTION input string
        """
        lines = [f"SOLUTION {solution_number}"]
        lines.append("    units mg/L")
        
        # Temperature
        temp_celsius = value(mcas_state.temperature) - 273.15
        lines.append(f"    temp {temp_celsius:.2f}")
        
        # pH - check if available
        if hasattr(mcas_state, 'pH'):
            pH_value = value(mcas_state.pH)
            lines.append(f"    pH {pH_value:.3f}")
        else:
            # Calculate from H+ concentration if available
            if hasattr(mcas_state, 'conc_mol_phase_comp'):
                if ('Liq', 'H_+') in mcas_state.conc_mol_phase_comp:
                    h_conc = value(mcas_state.conc_mol_phase_comp['Liq', 'H_+'])
                    if h_conc > 0:
                        pH_value = -np.log10(h_conc / 1000)  # mol/m3 to mol/L
                        lines.append(f"    pH {pH_value:.3f}")
                    else:
                        lines.append("    pH 7.0  # Default")
                else:
                    lines.append("    pH 7.0  # Default")
            else:
                lines.append("    pH 7.0  # Default")
        
        # pe (redox potential) - set default
        lines.append("    pe 4.0")
        
        # Get concentrations
        if hasattr(mcas_state, 'conc_mass_phase_comp'):
            # Mass concentration available
            for (phase, comp), conc_var in mcas_state.conc_mass_phase_comp.items():
                if phase == 'Liq' and comp in self.species_map:
                    conc_mg_L = value(pyunits.convert(conc_var, to_units=pyunits.mg/pyunits.L))
                    if conc_mg_L > 1e-6:  # Skip very small concentrations
                        phreeqc_species = self.species_map[comp]
                        # Handle special species
                        if phreeqc_species == 'N(5)':
                            lines.append(f"    N(5) {conc_mg_L:.6f} as NH4")
                        elif phreeqc_species == 'Si':
                            lines.append(f"    Si {conc_mg_L:.6f} as SiO2")
                        elif comp != 'H2O':  # Skip water
                            lines.append(f"    {phreeqc_species} {conc_mg_L:.6f}")
        
        elif hasattr(mcas_state, 'flow_mol_phase_comp'):
            # Need to calculate concentrations from flow rates
            total_vol_flow = value(mcas_state.flow_vol_phase['Liq'])  # m3/s
            
            for (phase, comp), flow_var in mcas_state.flow_mol_phase_comp.items():
                if phase == 'Liq' and comp in self.species_map:
                    mol_flow = value(flow_var)  # mol/s
                    if total_vol_flow > 0:
                        conc_mol_m3 = mol_flow / total_vol_flow  # mol/m3
                        # Get molecular weight
                        mw = value(mcas_state.params.mw_comp[comp])  # kg/mol
                        conc_mg_L = conc_mol_m3 * mw * 1000  # mg/L
                        
                        if conc_mg_L > 1e-6:
                            phreeqc_species = self.species_map[comp]
                            if phreeqc_species == 'N(5)':
                                lines.append(f"    N(5) {conc_mg_L:.6f} as NH4")
                            elif phreeqc_species == 'Si':
                                lines.append(f"    Si {conc_mg_L:.6f} as SiO2")
                            elif comp != 'H2O':
                                lines.append(f"    {phreeqc_species} {conc_mg_L:.6f}")
        
        # Handle alkalinity if present
        if hasattr(mcas_state, 'alkalinity'):
            alk_mg_L = value(pyunits.convert(mcas_state.alkalinity, to_units=pyunits.mg/pyunits.L))
            lines.append(f"    Alkalinity {alk_mg_L:.2f} as CaCO3")
        
        # Charge balance - typically on dominant ion
        lines.append("    -water 1 # 1 kg of water")
        
        return '\n'.join(lines)
    
    def phreeqc_to_mcas_results(self, phreeqc_results: Dict, mcas_block) -> None:
        """
        Update MCAS state block with PHREEQC simulation results
        
        Args:
            phreeqc_results: Dictionary of PHREEQC results
            mcas_block: MCAS property block to update
        """
        # Update pH if available
        if 'pH' in phreeqc_results:
            if hasattr(mcas_block, 'pH'):
                mcas_block.pH.set_value(phreeqc_results['pH'])
        
        # Update concentrations
        for phreeqc_species, conc_mg_L in phreeqc_results.items():
            if phreeqc_species in self.phreeqc_to_mcas:
                mcas_comp = self.phreeqc_to_mcas[phreeqc_species]
                
                if hasattr(mcas_block, 'conc_mass_phase_comp'):
                    if ('Liq', mcas_comp) in mcas_block.conc_mass_phase_comp:
                        # Convert mg/L to model units
                        conc_var = mcas_block.conc_mass_phase_comp['Liq', mcas_comp]
                        conc_value = pyunits.convert_value(
                            conc_mg_L,
                            from_units=pyunits.mg/pyunits.L,
                            to_units=conc_var.get_units()
                        )
                        conc_var.set_value(conc_value)
                
                # Also update molar flows if needed
                if hasattr(mcas_block, 'flow_mol_phase_comp'):
                    if ('Liq', mcas_comp) in mcas_block.flow_mol_phase_comp:
                        # Get total volumetric flow
                        vol_flow = value(mcas_block.flow_vol_phase['Liq'])  # m3/s
                        # Get molecular weight
                        mw = value(mcas_block.params.mw_comp[mcas_comp])  # kg/mol
                        # Calculate molar flow
                        mol_flow = (conc_mg_L / 1000) / mw * vol_flow  # mol/s
                        mcas_block.flow_mol_phase_comp['Liq', mcas_comp].set_value(mol_flow)
        
        # Update alkalinity if tracked
        if 'alkalinity_mg_L' in phreeqc_results:
            if hasattr(mcas_block, 'alkalinity'):
                alk_value = pyunits.convert_value(
                    phreeqc_results['alkalinity_mg_L'],
                    from_units=pyunits.mg/pyunits.L,
                    to_units=mcas_block.alkalinity.get_units()
                )
                mcas_block.alkalinity.set_value(alk_value)
    
    def get_phreeqc_units(self, mcas_units) -> str:
        """Convert MCAS units to PHREEQC units string"""
        # PHREEQC typically uses mg/L for solutions
        return "mg/L"
    
    def extract_feed_composition(self, mcas_state) -> Dict[str, Any]:
        """
        Extract feed water composition from MCAS state in a format
        compatible with existing PHREEQC engines.
        
        Handles both mass-based and molar-based flow specifications.
        
        Returns:
            dict with structure:
            {
                'temperature': float (°C),
                'pressure': float (bar),
                'pH': float,
                'concentrations': {ion: mg/L},
                'units': 'mg/L'
            }
        """
        # Temperature in Celsius
        temp_K = value(mcas_state.temperature)
        temp_C = temp_K - 273.15
        
        # Pressure in bar
        pressure_Pa = value(mcas_state.pressure)
        pressure_bar = pressure_Pa / 1e5
        
        # Get concentrations in mg/L
        concentrations = {}
        
        # Check if using mass or molar basis
        # First check if the property package has material_flow_basis attribute
        using_mass_basis = False
        if hasattr(mcas_state.params, 'config') and hasattr(mcas_state.params.config, 'material_flow_basis'):
            from watertap.property_models.multicomp_aq_sol_prop_pack import MaterialFlowBasis
            using_mass_basis = mcas_state.params.config.material_flow_basis == MaterialFlowBasis.mass
        
        if using_mass_basis and hasattr(mcas_state, 'flow_mass_phase_comp'):
            # Mass basis - preferred for IX models
            # Get volumetric flow rate from property package
            if hasattr(mcas_state, 'flow_vol_phase'):
                flow_vol_m3_s = value(mcas_state.flow_vol_phase['Liq'])  # m³/s
                logger.info(f"Using flow_vol_phase: {flow_vol_m3_s:.10e} m³/s (decimal: {flow_vol_m3_s})")
            else:
                # Fallback: calculate from mass flows assuming density ~1000 kg/m³
                water_flow_kg_s = value(mcas_state.flow_mass_phase_comp['Liq', 'H2O'])
                total_flow_kg_s = water_flow_kg_s
                
                for comp in mcas_state.params.solute_set:
                    # Get mass flow of component
                    mass_flow_kg_s = value(mcas_state.flow_mass_phase_comp['Liq', comp])
                    total_flow_kg_s += mass_flow_kg_s
                
                flow_vol_m3_s = total_flow_kg_s / 1000  # m³/s
                logger.info(f"Calculated flow_vol from mass: {flow_vol_m3_s:.6f} m³/s (total mass: {total_flow_kg_s:.6f} kg/s)")
            
            # Log water mass flow
            water_flow_kg_s = value(mcas_state.flow_mass_phase_comp['Liq', 'H2O'])
            logger.info(f"Water mass flow: {water_flow_kg_s:.6f} kg/s")
            
            for comp in mcas_state.params.solute_set:
                # Get mass flow of component
                mass_flow_kg_s = value(mcas_state.flow_mass_phase_comp['Liq', comp])
                logger.info(f"Mass flow of {comp}: {mass_flow_kg_s:.6f} kg/s")
                
                # Convert to mg/L
                # C (kg/m³) = mass_flow (kg/s) / flow_vol (m³/s)
                # C (mg/L) = C (kg/m³) × 1000 (since 1 kg/m³ = 1000 mg/L)
                conc_mg_L = mass_flow_kg_s / flow_vol_m3_s * 1000 if flow_vol_m3_s > 0 else 0
                
                # Ensure minimum concentration to avoid numerical issues
                conc_mg_L = max(conc_mg_L, 1e-3)  # 0.001 mg/L minimum
                
                # Map to PHREEQC species name
                phreeqc_name = self.species_map.get(comp, comp)
                concentrations[phreeqc_name] = conc_mg_L
        else:
            # Molar basis - legacy support
            # Get total volumetric flow rate
            flow_vol = value(mcas_state.flow_vol_phase['Liq'])  # m³/s
            
            for comp in mcas_state.params.solute_set:
                # Get molar flow of component
                mol_flow = value(mcas_state.flow_mol_phase_comp['Liq', comp])  # mol/s
                
                # Convert to concentration
                # C (mol/L) = mol_flow (mol/s) / flow_vol (m³/s) * 1000 (L/m³)
                conc_mol_L = mol_flow / flow_vol * 1000 if flow_vol > 0 else 0
                
                # Convert to mg/L using molecular weight
                mw = self._get_molecular_weight(comp)  # g/mol
                conc_mg_L = conc_mol_L * mw * 1000  # mg/L
                
                # Ensure minimum concentration
                conc_mg_L = max(conc_mg_L, 1e-3)  # 0.001 mg/L minimum
                
                # Map to PHREEQC species name
                phreeqc_name = self.species_map.get(comp, comp)
                concentrations[phreeqc_name] = conc_mg_L
        
        # Get pH
        pH = 7.0  # Default
        if hasattr(mcas_state, 'pH'):
            pH = value(mcas_state.pH)
        elif 'H+' in concentrations:
            # Calculate pH from H+ concentration in mg/L
            h_mg_L = concentrations['H+']
            if h_mg_L > 0:
                h_mol_L = h_mg_L / 1008  # Convert mg/L to mol/L (MW of H+ = 1.008 g/mol)
                pH = -np.log10(h_mol_L)
                # Sanity check - if pH is unrealistic, use neutral
                if pH < 0 or pH > 14:
                    logger.warning(f"Calculated pH {pH:.2f} out of range, using 7.0")
                    pH = 7.0
        elif hasattr(mcas_state, 'conc_mol_phase_comp'):
            if ('Liq', 'H_+') in mcas_state.conc_mol_phase_comp:
                h_conc = value(mcas_state.conc_mol_phase_comp['Liq', 'H_+'])  # mol/m³
                if h_conc > 0:
                    pH = -np.log10(h_conc / 1000)  # Convert to mol/L
        
        # Log concentrations for debugging
        logger.info("PHREEQC feed composition:")
        logger.info(f"  Temperature: {temp_C:.1f} °C")
        logger.info(f"  pH: {pH:.2f}")
        total_tds = sum(concentrations.values())
        logger.info(f"  Total TDS: {total_tds:.1f} mg/L")
        for species, conc in concentrations.items():
            logger.info(f"  {species}: {conc:.3f} mg/L")
        
        # Calculate alkalinity from carbonate species
        alkalinity = 0
        if 'HCO3-' in concentrations:
            # Simple approximation: alkalinity ≈ HCO3 concentration
            alkalinity = concentrations['HCO3-'] * 50.04 / 61.02  # as CaCO3
        
        # Build return dictionary in format expected by engines
        feed_comp = {
            'temperature': temp_C,
            'pressure': pressure_bar,
            'pH': pH,
            'alkalinity': alkalinity,
            'concentrations': concentrations,
            'units': 'mg/L'
        }
        
        # Also add simplified keys for backward compatibility
        comp_mapping = {
            'Ca+2': 'Ca',
            'Mg+2': 'Mg',
            'Na+': 'Na',
            'K+': 'K',
            'Cl-': 'Cl',
            'SO4-2': 'SO4',
            'HCO3-': 'HCO3',
            'Fe+2': 'Fe',
            'Mn+2': 'Mn',
            'Ba+2': 'Ba',
            'Sr+2': 'Sr',
            'Al+3': 'Al'
        }
        
        for phreeqc_name, simple_name in comp_mapping.items():
            if phreeqc_name in concentrations:
                feed_comp[simple_name] = concentrations[phreeqc_name]
            else:
                feed_comp[simple_name] = 0
        
        return feed_comp
    
    def _get_molecular_weight(self, comp: str) -> float:
        """Get molecular weight for a component"""
        if comp in MOLECULAR_WEIGHTS:
            return MOLECULAR_WEIGHTS[comp]
        else:
            logger.warning(f"Molecular weight not found for {comp}, using 100 g/mol")
            return 100.0
    
    def update_mcas_from_simple_dict(self, mcas_block, results: Dict[str, float]) -> None:
        """
        Update MCAS block from simplified results dictionary
        (used for compatibility with existing engines)
        """
        # Map simple names back to MCAS components
        reverse_mapping = {
            'Ca': 'Ca_2+',
            'Mg': 'Mg_2+',
            'Na': 'Na_+',
            'K': 'K_+',
            'Cl': 'Cl_-',
            'SO4': 'SO4_2-',
            'HCO3': 'HCO3_-',
            'Fe': 'Fe_2+',
            'Mn': 'Mn_2+',
            'Ba': 'Ba_2+',
            'Sr': 'Sr_2+',
            'Al': 'Al_3+'
        }
        
        # Create PHREEQC-style results dict
        phreeqc_results = {}
        for simple_name, value in results.items():
            if simple_name in reverse_mapping:
                mcas_comp = reverse_mapping[simple_name]
                if mcas_comp in self.species_map:
                    phreeqc_species = self.species_map[mcas_comp]
                    phreeqc_results[phreeqc_species] = value
            elif simple_name == 'pH':
                phreeqc_results['pH'] = value
            elif simple_name == 'alkalinity':
                phreeqc_results['alkalinity_mg_L'] = value
        
        # Use standard update method
        self.phreeqc_to_mcas_results(phreeqc_results, mcas_block)
    
    def mcas_to_phreeqc_dict(self, mcas_state) -> Dict[str, Any]:
        """
        Convert MCAS state to dictionary format for water-chemistry-mcp.
        
        Args:
            mcas_state: MCAS property state block
            
        Returns:
            Dictionary compatible with water-chemistry-mcp tools
        """
        # Temperature
        temp_celsius = value(mcas_state.temperature) - 273.15
        
        # pH
        pH_value = 7.0  # Default
        if hasattr(mcas_state, 'pH'):
            pH_value = value(mcas_state.pH)
        elif hasattr(mcas_state, 'flow_mol_phase_comp') and ('Liq', 'H_+') in mcas_state.flow_mol_phase_comp:
            # Calculate from H+ concentration
            h_conc = value(mcas_state.conc_mol_phase_comp['Liq', 'H_+'])  # mol/m3
            if h_conc > 0:
                h_conc_mol_L = h_conc / 1000  # mol/L
                pH_value = -np.log10(h_conc_mol_L)
        
        # Build analysis dict with element totals for water-chemistry-mcp
        analysis = {}
        
        # Map ions to elements
        ion_to_element = {
            'Na_+': 'Na', 'Ca_2+': 'Ca', 'Mg_2+': 'Mg', 'K_+': 'K',
            'Cl_-': 'Cl', 'SO4_2-': 'S(6)', 'HCO3_-': 'C(4)', 'NO3_-': 'N(5)',
            'F_-': 'F', 'SiO2': 'Si'
        }
        
        # Get concentrations
        if hasattr(mcas_state, 'conc_mass_phase_comp'):
            # Mass concentration basis
            for (phase, comp), conc_var in mcas_state.conc_mass_phase_comp.items():
                if phase == 'Liq' and comp in ion_to_element:
                    conc_kg_m3 = value(conc_var)
                    conc_mg_L = conc_kg_m3 * 1000  # kg/m3 to mg/L (1 kg/m³ = 1000 mg/L)
                    element = ion_to_element[comp]
                    analysis[element] = conc_mg_L
        elif hasattr(mcas_state, 'flow_mass_phase_comp'):
            # Mass flow basis - calculate concentrations
            total_flow = value(mcas_state.flow_mass_phase_comp['Liq', 'H2O'])
            if total_flow > 0:
                for (phase, comp), flow_var in mcas_state.flow_mass_phase_comp.items():
                    if phase == 'Liq' and comp != 'H2O' and comp in ion_to_element:
                        comp_flow = value(flow_var)  # kg/s
                        # Fix: total_flow is water flow in kg/s, need volumetric flow
                        # Assuming density ~1000 kg/m³
                        flow_vol_m3_s = total_flow / 1000  # m³/s
                        conc_kg_m3 = comp_flow / flow_vol_m3_s  # kg/m³
                        conc_mg_L = conc_kg_m3 * 1000  # kg/m³ to mg/L
                        element = ion_to_element[comp]
                        analysis[element] = conc_mg_L
        
        # Get alkalinity if available
        alkalinity = None
        if hasattr(mcas_state, 'alkalinity'):
            alkalinity = value(pyunits.convert(mcas_state.alkalinity, to_units=pyunits.mg/pyunits.L))
        
        return {
            "analysis": analysis,
            "pH": pH_value,
            "temperature_celsius": temp_celsius,
            "pressure_atm": value(mcas_state.pressure) / 101325,
            "units": "mg/L",
            "alkalinity": alkalinity
        }
    
    def phreeqc_to_mcas_state(self, phreeqc_results: Dict[str, Any], mcas_state) -> Dict[str, Any]:
        """
        Convert PHREEQC results to MCAS state values.
        
        Args:
            phreeqc_results: Results from water-chemistry-mcp
            mcas_state: MCAS property state block to update
            
        Returns:
            Dictionary of component mass flows (kg/s)
        """
        # Extract the solution data
        if "final_solution" in phreeqc_results:
            solution = phreeqc_results["final_solution"]
        else:
            solution = phreeqc_results
        
        # Get total water flow from inlet
        water_flow = value(mcas_state.flow_mass_phase_comp['Liq', 'H2O'])
        
        # Get volumetric flow rate
        if hasattr(mcas_state, 'flow_vol_phase'):
            flow_vol_m3_s = value(mcas_state.flow_vol_phase['Liq'])  # m³/s
        else:
            # Estimate from water flow assuming density ~1000 kg/m³
            flow_vol_m3_s = water_flow / 1000  # m³/s
        
        # Build mass flows dict
        mass_flows = {'H2O': water_flow}
        
        # Map elements back to ions
        element_to_ion = {
            'Na': 'Na_+', 'Ca': 'Ca_2+', 'Mg': 'Mg_2+', 'K': 'K_+',
            'Cl': 'Cl_-', 'S(6)': 'SO4_2-', 'C(4)': 'HCO3_-', 'N(5)': 'NO3_-',
            'F': 'F_-', 'Si': 'SiO2'
        }
        
        # Get concentrations from analysis
        if "analysis" in solution:
            for element, conc_mg_L in solution["analysis"].items():
                if element in element_to_ion:
                    ion = element_to_ion[element]
                    # Convert mg/L to kg/s using volumetric flow
                    # mass_flow (kg/s) = conc (mg/L) × flow (m³/s) × 1e-6 (kg/mg)
                    mass_flow = (conc_mg_L / 1e6) * flow_vol_m3_s  # kg/s
                    mass_flows[ion] = mass_flow
        
        # Handle species concentrations if provided
        if "species_concentrations" in solution:
            # Map PHREEQC species to MCAS components
            for species, conc_mg_L in solution["species_concentrations"].items():
                if species in self.phreeqc_to_mcas:
                    mcas_comp = self.phreeqc_to_mcas[species]
                    mass_flow = (conc_mg_L / 1e6) * flow_vol_m3_s
                    mass_flows[mcas_comp] = mass_flow
        
        return mass_flows
    
    def check_electroneutrality(self, concentrations: Dict[str, float], tolerance: float = 0.01) -> tuple:
        """
        Check electroneutrality of a solution.
        
        Args:
            concentrations: Dict of ion concentrations in mg/L
            tolerance: Acceptable charge imbalance fraction
            
        Returns:
            (is_neutral, charge_imbalance): bool and charge imbalance in meq/L
        """
        positive_charge = 0  # meq/L
        negative_charge = 0  # meq/L
        
        for ion, conc_mg_L in concentrations.items():
            # Find MCAS component name
            mcas_comp = self.phreeqc_to_mcas.get(ion)
            if not mcas_comp:
                # Try direct mapping
                mcas_comp = ion
            
            if mcas_comp in ION_CHARGES:
                charge = ION_CHARGES[mcas_comp]
                mw = MOLECULAR_WEIGHTS.get(mcas_comp, 100)
                
                # Convert mg/L to meq/L
                meq_L = conc_mg_L / mw * abs(charge)
                
                if charge > 0:
                    positive_charge += meq_L
                else:
                    negative_charge += meq_L
        
        # Calculate imbalance
        total_charge = positive_charge + negative_charge
        charge_imbalance = positive_charge - negative_charge
        
        # Check if balanced within tolerance
        if (positive_charge + negative_charge) > 0:
            relative_imbalance = abs(charge_imbalance) / (positive_charge + negative_charge)
            is_neutral = relative_imbalance < tolerance
        else:
            is_neutral = True  # No ions
        
        logger.info(f"Charge balance: +{positive_charge:.2f} / -{negative_charge:.2f} meq/L, "
                   f"imbalance: {charge_imbalance:.2f} meq/L")
        
        return is_neutral, charge_imbalance
    
    def adjust_for_electroneutrality(self, concentrations: Dict[str, float], 
                                   adjustment_ion: str = 'Cl-') -> Dict[str, float]:
        """
        Adjust ion concentrations to achieve electroneutrality.
        
        Args:
            concentrations: Dict of ion concentrations in mg/L (will be modified)
            adjustment_ion: Ion to adjust (typically Cl- or Na+)
            
        Returns:
            Adjusted concentrations dict
        """
        is_neutral, charge_imbalance = self.check_electroneutrality(concentrations)
        
        if is_neutral:
            return concentrations.copy()
        
        # Find MCAS name for adjustment ion
        mcas_adj_ion = None
        for mcas_comp, phreeqc_comp in self.species_map.items():
            if phreeqc_comp == adjustment_ion:
                mcas_adj_ion = mcas_comp
                break
        
        if not mcas_adj_ion or mcas_adj_ion not in ION_CHARGES:
            logger.warning(f"Cannot adjust with {adjustment_ion} - not found in charge data")
            return concentrations.copy()
        
        # Calculate required adjustment
        adj_charge = ION_CHARGES[mcas_adj_ion]
        adj_mw = MOLECULAR_WEIGHTS.get(mcas_adj_ion, 100)
        
        # meq/L needed = charge_imbalance / charge_of_adjustment_ion
        meq_needed = -charge_imbalance / adj_charge
        mg_L_needed = meq_needed * adj_mw / abs(adj_charge)
        
        # Make a copy and adjust
        adjusted = concentrations.copy()
        current_conc = adjusted.get(adjustment_ion, 0)
        new_conc = max(0, current_conc + mg_L_needed)
        adjusted[adjustment_ion] = new_conc
        
        logger.info(f"Adjusted {adjustment_ion} from {current_conc:.1f} to {new_conc:.1f} mg/L")
        
        return adjusted