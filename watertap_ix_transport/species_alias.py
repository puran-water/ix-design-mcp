"""
Species name mapping between PHREEQC and Pyomo/IDAES.

This module provides a single source of truth for species name mapping between:
- PHREEQC notation (e.g., Ca+2, Mg+2, Cl-)
- Pyomo/IDAES notation (e.g., Ca_2+, Mg_2+, Cl_-)

This mapping is critical for correct data exchange between PHREEQC simulations
and the Pyomo IX model.
"""

# Mapping from PHREEQC species names to Pyomo/IDAES names
PHREEQC_TO_PYOMO = {
    # Cations
    "Ca+2": "Ca_2+",
    "Mg+2": "Mg_2+",
    "Na+": "Na_+",
    "K+": "K_+",
    "H+": "H_+",
    "Fe+2": "Fe_2+",
    "Fe+3": "Fe_3+",
    "Mn+2": "Mn_2+",
    "Al+3": "Al_3+",
    "NH4+": "NH4_+",
    
    # Anions
    "Cl-": "Cl_-",
    "SO4-2": "SO4_2-",
    "HCO3-": "HCO3_-",
    "CO3-2": "CO3_2-",
    "NO3-": "NO3_-",
    "PO4-3": "PO4_3-",
    "OH-": "OH_-",
    "F-": "F_-",
    "Br-": "Br_-",
    
    # Neutral species
    "H2O": "H2O",
}

# Reverse mapping from Pyomo/IDAES to PHREEQC
PYOMO_TO_PHREEQC = {v: k for k, v in PHREEQC_TO_PYOMO.items()}


def phreeqc_to_pyomo(species_name: str) -> str:
    """
    Convert PHREEQC species name to Pyomo/IDAES format.
    
    Args:
        species_name: Species name in PHREEQC format (e.g., "Ca+2")
        
    Returns:
        Species name in Pyomo format (e.g., "Ca_2+")
        
    Raises:
        KeyError: If species name is not in the mapping
    """
    if species_name not in PHREEQC_TO_PYOMO:
        raise KeyError(
            f"Unknown PHREEQC species '{species_name}'. "
            f"Known species: {list(PHREEQC_TO_PYOMO.keys())}"
        )
    return PHREEQC_TO_PYOMO[species_name]


def pyomo_to_phreeqc(species_name: str) -> str:
    """
    Convert Pyomo/IDAES species name to PHREEQC format.
    
    Args:
        species_name: Species name in Pyomo format (e.g., "Ca_2+")
        
    Returns:
        Species name in PHREEQC format (e.g., "Ca+2")
        
    Raises:
        KeyError: If species name is not in the mapping
    """
    if species_name not in PYOMO_TO_PHREEQC:
        raise KeyError(
            f"Unknown Pyomo species '{species_name}'. "
            f"Known species: {list(PYOMO_TO_PHREEQC.keys())}"
        )
    return PYOMO_TO_PHREEQC[species_name]


def get_all_pyomo_species():
    """Get list of all known Pyomo species names."""
    return list(PYOMO_TO_PHREEQC.keys())


def get_all_phreeqc_species():
    """Get list of all known PHREEQC species names."""
    return list(PHREEQC_TO_PYOMO.keys())


def _validate_mappings():
    """
    Validate that all mappings are unique and bijective.
    Raises ValueError if duplicate values are found.
    This ensures data integrity and prevents silent bugs.
    """
    # Check forward mapping uniqueness
    forward_values = list(PHREEQC_TO_PYOMO.values())
    if len(forward_values) != len(set(forward_values)):
        # Find duplicates for better error message
        seen = set()
        duplicates = set()
        for value in forward_values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        raise ValueError(
            f"Duplicate values found in PHREEQC_TO_PYOMO mapping: {duplicates}. "
            "Each PHREEQC species must map to a unique Pyomo species."
        )
    
    # Check reverse mapping uniqueness
    reverse_values = list(PYOMO_TO_PHREEQC.values())
    if len(reverse_values) != len(set(reverse_values)):
        # Find duplicates for better error message
        seen = set()
        duplicates = set()
        for value in reverse_values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        raise ValueError(
            f"Duplicate values found in PYOMO_TO_PHREEQC mapping: {duplicates}. "
            "Each Pyomo species must map to a unique PHREEQC species."
        )
    
    # Verify bijective mapping (reverse of reverse should be identity)
    for phreeqc_name, pyomo_name in PHREEQC_TO_PYOMO.items():
        if PYOMO_TO_PHREEQC.get(pyomo_name) != phreeqc_name:
            raise ValueError(
                f"Mapping inconsistency: {phreeqc_name} -> {pyomo_name} but "
                f"{pyomo_name} -> {PYOMO_TO_PHREEQC.get(pyomo_name)}"
            )
    
    # Log successful validation
    import logging
    logger = logging.getLogger(__name__)
    logger.debug(
        f"Species alias validation passed: {len(PHREEQC_TO_PYOMO)} unique "
        f"bijective mappings between PHREEQC and Pyomo notation"
    )


# Run validation on module import to catch errors early
_validate_mappings()