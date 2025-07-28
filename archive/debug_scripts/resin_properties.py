#!/usr/bin/env python3
"""
Resin Properties Module

This module handles loading and managing ion exchange resin properties
from the resin database (YAML format). It provides a clean interface
for accessing resin characteristics including capacity, selectivity,
operating conditions, and regeneration parameters.
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)


class ResinDatabase:
    """Manages ion exchange resin properties from YAML database."""
    
    def __init__(self, database_path: Optional[str] = None):
        """
        Initialize resin database.
        
        Args:
            database_path: Path to resin database YAML file.
                          Defaults to 'resin_database.yaml' in same directory.
        """
        if database_path is None:
            database_path = Path(__file__).parent / "resin_database.yaml"
        
        self.database_path = Path(database_path)
        self.resins = {}
        self.defaults = {}
        self._load_database()
    
    def _load_database(self):
        """Load resin database from YAML file."""
        if not self.database_path.exists():
            logger.warning(f"Resin database not found at {self.database_path}")
            self._load_builtin_database()
            return
        
        try:
            with open(self.database_path, 'r') as f:
                data = yaml.safe_load(f)
            
            self.resins = data.get('resins', {})
            self.defaults = data.get('defaults', {})
            logger.info(f"Loaded {len(self.resins)} resin types from {self.database_path}")
            
        except Exception as e:
            logger.error(f"Error loading resin database: {e}")
            self._load_builtin_database()
    
    def _load_builtin_database(self):
        """Load built-in resin properties as fallback."""
        logger.info("Loading built-in resin properties")
        
        self.resins = {
            'SAC': {
                'name': 'Strong Acid Cation',
                'type': 'cation',
                'capacity': {'value': 2.0, 'units': 'eq/L'},
                'porosity': 0.4,
                'selectivity': {
                    'Ca_2+': 1.6,
                    'Mg_2+': 1.3,
                    'K_+': 0.3,
                    'NH4_+': 0.2,
                    'H_+': 0.0
                },
                'operating': {
                    'pH_range': [0, 14],
                    'temperature_max_C': 120,
                    'flow_rate_BV_hr': [5, 50]
                }
            },
            'WAC': {
                'name': 'Weak Acid Cation',
                'type': 'cation',
                'capacity': {'value': 4.5, 'units': 'eq/L'},
                'porosity': 0.45,
                'pKa': 4.75,
                'selectivity': {
                    'Ca_2+': 2.5,
                    'Mg_2+': 2.3,
                    'Na_+': 1.8,
                    'K_+': 1.9
                },
                'operating': {
                    'pH_range': [5, 14],
                    'temperature_max_C': 100,
                    'flow_rate_BV_hr': [5, 30]
                }
            },
            'SBA': {
                'name': 'Strong Base Anion',
                'type': 'anion',
                'capacity': {'value': 1.2, 'units': 'eq/L'},
                'porosity': 0.42,
                'selectivity': {
                    'SO4_2-': 4.0,
                    'NO3_-': 2.8,
                    'Cl_-': 1.0,
                    'HCO3_-': 0.3,
                    'OH_-': 5.0
                },
                'operating': {
                    'pH_range': [0, 14],
                    'temperature_max_C': 60,
                    'flow_rate_BV_hr': [5, 25]
                }
            },
            'WBA': {
                'name': 'Weak Base Anion',
                'type': 'anion',
                'capacity': {'value': 1.6, 'units': 'eq/L'},
                'porosity': 0.48,
                'pKb': 6.5,
                'selectivity': {
                    'SO4_2-': 3.5,
                    'Cl_-': 1.5,
                    'NO3_-': 2.0
                },
                'operating': {
                    'pH_range': [0, 7],
                    'temperature_max_C': 40,
                    'flow_rate_BV_hr': [5, 20]
                }
            }
        }
        
        self.defaults = {
            'bed_expansion_percent': 50,
            'rinse_BV': 2,
            'minimum_bed_depth_m': 0.6,
            'maximum_bed_depth_m': 3.0,
            'freeboard_percent': 100
        }
    
    def get_resin(self, resin_type: str) -> Dict[str, Any]:
        """
        Get properties for a specific resin type.
        
        Args:
            resin_type: Resin identifier (e.g., 'SAC', 'WAC', 'SBA', 'WBA')
            
        Returns:
            Dictionary of resin properties
            
        Raises:
            ValueError: If resin type not found
        """
        if resin_type not in self.resins:
            available = ', '.join(self.resins.keys())
            raise ValueError(f"Resin type '{resin_type}' not found. Available: {available}")
        
        return self.resins[resin_type].copy()
    
    def get_capacity(self, resin_type: str) -> float:
        """
        Get resin capacity in eq/L.
        
        Args:
            resin_type: Resin identifier
            
        Returns:
            Capacity in eq/L
        """
        resin = self.get_resin(resin_type)
        return resin['capacity']['value']
    
    def get_porosity(self, resin_type: str) -> float:
        """
        Get resin bed porosity.
        
        Args:
            resin_type: Resin identifier
            
        Returns:
            Porosity (fraction)
        """
        resin = self.get_resin(resin_type)
        return resin.get('porosity', 0.4)
    
    def get_selectivity(self, resin_type: str, ion: str) -> Optional[float]:
        """
        Get selectivity coefficient for an ion.
        
        Args:
            resin_type: Resin identifier
            ion: Ion species (e.g., 'Ca_2+', 'Mg_2+')
            
        Returns:
            Selectivity coefficient (log K) or None if not found
        """
        resin = self.get_resin(resin_type)
        selectivity = resin.get('selectivity', {})
        return selectivity.get(ion)
    
    def get_all_selectivities(self, resin_type: str) -> Dict[str, float]:
        """
        Get all selectivity coefficients for a resin.
        
        Args:
            resin_type: Resin identifier
            
        Returns:
            Dictionary of ion: selectivity pairs
        """
        resin = self.get_resin(resin_type)
        return resin.get('selectivity', {}).copy()
    
    def validate_operating_conditions(
        self, 
        resin_type: str, 
        pH: Optional[float] = None,
        temperature_C: Optional[float] = None,
        flow_rate_BV_hr: Optional[float] = None
    ) -> Dict[str, Union[bool, str]]:
        """
        Validate operating conditions for a resin.
        
        Args:
            resin_type: Resin identifier
            pH: Operating pH
            temperature_C: Operating temperature in Celsius
            flow_rate_BV_hr: Flow rate in BV/hr
            
        Returns:
            Dictionary with 'valid' (bool) and 'messages' (list of warnings)
        """
        resin = self.get_resin(resin_type)
        operating = resin.get('operating', {})
        
        valid = True
        messages = []
        
        # Check pH
        if pH is not None and 'pH_range' in operating:
            pH_min, pH_max = operating['pH_range']
            if pH < pH_min or pH > pH_max:
                valid = False
                messages.append(f"pH {pH} outside range [{pH_min}, {pH_max}]")
        
        # Check temperature
        if temperature_C is not None and 'temperature_max_C' in operating:
            temp_max = operating['temperature_max_C']
            if temperature_C > temp_max:
                valid = False
                messages.append(f"Temperature {temperature_C}°C exceeds max {temp_max}°C")
        
        # Check flow rate
        if flow_rate_BV_hr is not None and 'flow_rate_BV_hr' in operating:
            flow_min, flow_max = operating['flow_rate_BV_hr']
            if flow_rate_BV_hr < flow_min:
                messages.append(f"Flow rate {flow_rate_BV_hr} BV/hr below recommended {flow_min} BV/hr")
            elif flow_rate_BV_hr > flow_max:
                messages.append(f"Flow rate {flow_rate_BV_hr} BV/hr above recommended {flow_max} BV/hr")
        
        return {'valid': valid, 'messages': messages}
    
    def get_phreeqc_exchange_species(self, resin_type: str) -> str:
        """
        Generate PHREEQC EXCHANGE_SPECIES block for a resin.
        
        Args:
            resin_type: Resin identifier
            
        Returns:
            PHREEQC formatted exchange species definitions
        """
        resin = self.get_resin(resin_type)
        selectivity = resin.get('selectivity', {})
        
        if resin['type'] == 'cation':
            # Cation exchange reactions
            lines = ["EXCHANGE_SPECIES"]
            
            # Reference reaction (usually Na+ or H+)
            if 'Na_+' in selectivity or resin_type == 'SAC':
                lines.append("    Na+ + X- = NaX")
                lines.append("        log_k   0.0")
            elif 'H_+' in selectivity:
                lines.append("    H+ + X- = HX")
                lines.append("        log_k   0.0")
            
            # Other cations
            for ion, log_k in selectivity.items():
                if ion in ['Na_+', 'H_+'] and log_k == 0.0:
                    continue  # Skip reference
                
                charge = ion.split('_')[-1]
                if charge == '2+':
                    lines.append(f"    {ion.replace('_', '')} + 2X- = {ion.split('_')[0]}X2")
                    lines.append(f"        log_k   {log_k}")
                elif charge == '+':
                    lines.append(f"    {ion.replace('_', '')} + X- = {ion.split('_')[0]}X")
                    lines.append(f"        log_k   {log_k}")
        
        elif resin['type'] == 'anion':
            # Anion exchange reactions
            lines = ["EXCHANGE_SPECIES"]
            
            # Reference reaction (usually Cl-)
            lines.append("    Cl- + X+ = XCl")
            lines.append("        log_k   0.0")
            
            # Other anions
            for ion, log_k in selectivity.items():
                if ion == 'Cl_-' and log_k == 1.0:
                    continue  # Skip reference
                
                charge = ion.split('_')[-1]
                if charge == '2-':
                    lines.append(f"    {ion.replace('_', '')} + 2X+ = X2{ion.split('_')[0]}")
                    lines.append(f"        log_k   {log_k}")
                elif charge == '-':
                    lines.append(f"    {ion.replace('_', '')} + X+ = X{ion.split('_')[0]}")
                    lines.append(f"        log_k   {log_k}")
        
        return '\n'.join(lines)
    
    def list_resins(self) -> List[str]:
        """Get list of available resin types."""
        return list(self.resins.keys())
    
    def get_default(self, parameter: str) -> Any:
        """Get default parameter value."""
        return self.defaults.get(parameter)


# Convenience function for quick access
def load_resin_database(path: Optional[str] = None) -> ResinDatabase:
    """Load resin database from file."""
    return ResinDatabase(path)


# Module-level instance for easy import
_default_db = None


def get_resin_properties(resin_type: str) -> Dict[str, Any]:
    """
    Get resin properties using default database.
    
    Args:
        resin_type: Resin identifier
        
    Returns:
        Dictionary of resin properties
    """
    global _default_db
    if _default_db is None:
        _default_db = ResinDatabase()
    return _default_db.get_resin(resin_type)


if __name__ == "__main__":
    # Test the module
    db = ResinDatabase()
    
    print("Available resins:", db.list_resins())
    print("\nSAC properties:")
    sac = db.get_resin('SAC')
    print(f"  Capacity: {db.get_capacity('SAC')} eq/L")
    print(f"  Porosity: {db.get_porosity('SAC')}")
    print(f"  Ca selectivity: {db.get_selectivity('SAC', 'Ca_2+')}")
    
    print("\nSAC PHREEQC species:")
    print(db.get_phreeqc_exchange_species('SAC'))
    
    print("\nValidating conditions:")
    validation = db.validate_operating_conditions('SAC', pH=7.5, temperature_C=25, flow_rate_BV_hr=15)
    print(f"  Valid: {validation['valid']}")
    if validation['messages']:
        print(f"  Messages: {validation['messages']}")