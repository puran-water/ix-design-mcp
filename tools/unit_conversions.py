"""
Unit Conversion Module for IX Design MCP Server

Centralizes all unit conversions to ensure consistency and prevent errors.
Provides functions for converting between different concentration units,
flow rates, and other engineering units used in ion exchange calculations.
"""

from enum import Enum
from typing import Dict, Optional, Union
import math
from .core_config import CONFIG


class ConcentrationUnit(Enum):
    """Supported concentration units"""
    MG_L = "mg/L"
    MEQ_L = "meq/L"
    MOL_L = "mol/L"
    PPM = "ppm"  # Equivalent to mg/L for dilute solutions


class FlowUnit(Enum):
    """Supported flow rate units"""
    M3_HR = "m³/hr"
    L_HR = "L/hr"
    L_MIN = "L/min"
    GPM = "gpm"  # Gallons per minute
    GPH = "gph"  # Gallons per hour


class VolumeUnit(Enum):
    """Supported volume units"""
    M3 = "m³"
    L = "L"
    GAL = "gal"  # US gallons


def mg_to_meq(mg_l: float, ion: str) -> float:
    """
    Convert mg/L to meq/L for a specific ion.
    
    Args:
        mg_l: Concentration in mg/L
        ion: Ion name (e.g., 'Ca', 'Mg', 'Na')
        
    Returns:
        Concentration in meq/L
        
    Raises:
        ValueError: If ion is not recognized
    """
    equiv_weight = CONFIG.get_equiv_weight(ion)
    return mg_l / equiv_weight


def meq_to_mg(meq_l: float, ion: str) -> float:
    """
    Convert meq/L to mg/L for a specific ion.
    
    Args:
        meq_l: Concentration in meq/L
        ion: Ion name (e.g., 'Ca', 'Mg', 'Na')
        
    Returns:
        Concentration in mg/L
        
    Raises:
        ValueError: If ion is not recognized
    """
    equiv_weight = CONFIG.get_equiv_weight(ion)
    return meq_l * equiv_weight


def calculate_hardness_as_caco3(ca_mg_l: float, mg_mg_l: float) -> float:
    """
    Calculate total hardness as CaCO3 equivalent.
    
    Args:
        ca_mg_l: Calcium concentration in mg/L
        mg_mg_l: Magnesium concentration in mg/L
        
    Returns:
        Total hardness in mg/L as CaCO3
    """
    # Conversion factors to CaCO3 equivalent
    # Ca: 40.08 g/mol Ca -> 100.09 g/mol CaCO3 = 2.497
    # Mg: 24.305 g/mol Mg -> 100.09 g/mol CaCO3 = 4.118
    ca_factor = 2.497
    mg_factor = 4.118
    
    return ca_mg_l * ca_factor + mg_mg_l * mg_factor


def calculate_alkalinity_as_caco3(hco3_mg_l: float, co3_mg_l: float = 0.0, oh_mg_l: float = 0.0) -> float:
    """
    Calculate total alkalinity as CaCO3 equivalent.
    
    Args:
        hco3_mg_l: Bicarbonate concentration in mg/L
        co3_mg_l: Carbonate concentration in mg/L (default 0)
        oh_mg_l: Hydroxide concentration in mg/L (default 0)
        
    Returns:
        Total alkalinity in mg/L as CaCO3
    """
    # Conversion factors to CaCO3 equivalent
    # HCO3: 61.02 g/mol -> 50.04 g/mol CaCO3 equivalent = 0.820
    # CO3: 60.01 g/mol -> 50.04 g/mol CaCO3 equivalent = 0.834
    # OH: 17.01 g/mol -> 50.04 g/mol CaCO3 equivalent = 2.943
    hco3_factor = 0.820
    co3_factor = 0.834
    oh_factor = 2.943
    
    return hco3_mg_l * hco3_factor + co3_mg_l * co3_factor + oh_mg_l * oh_factor


def convert_flow_rate(value: float, from_unit: FlowUnit, to_unit: FlowUnit) -> float:
    """
    Convert flow rate between different units.
    
    Args:
        value: Flow rate value
        from_unit: Source unit
        to_unit: Target unit
        
    Returns:
        Converted flow rate
    """
    # Convert to L/hr as intermediate unit
    if from_unit == FlowUnit.M3_HR:
        l_hr = value * 1000
    elif from_unit == FlowUnit.L_HR:
        l_hr = value
    elif from_unit == FlowUnit.L_MIN:
        l_hr = value * 60
    elif from_unit == FlowUnit.GPM:
        l_hr = value * 3.78541 * 60  # 1 gal = 3.78541 L
    elif from_unit == FlowUnit.GPH:
        l_hr = value * 3.78541
    else:
        raise ValueError(f"Unknown flow unit: {from_unit}")
    
    # Convert from L/hr to target unit
    if to_unit == FlowUnit.M3_HR:
        return l_hr / 1000
    elif to_unit == FlowUnit.L_HR:
        return l_hr
    elif to_unit == FlowUnit.L_MIN:
        return l_hr / 60
    elif to_unit == FlowUnit.GPM:
        return l_hr / 3.78541 / 60
    elif to_unit == FlowUnit.GPH:
        return l_hr / 3.78541
    else:
        raise ValueError(f"Unknown flow unit: {to_unit}")


def convert_volume(value: float, from_unit: VolumeUnit, to_unit: VolumeUnit) -> float:
    """
    Convert volume between different units.
    
    Args:
        value: Volume value
        from_unit: Source unit
        to_unit: Target unit
        
    Returns:
        Converted volume
    """
    # Convert to L as intermediate unit
    if from_unit == VolumeUnit.M3:
        l_value = value * 1000
    elif from_unit == VolumeUnit.L:
        l_value = value
    elif from_unit == VolumeUnit.GAL:
        l_value = value * 3.78541
    else:
        raise ValueError(f"Unknown volume unit: {from_unit}")
    
    # Convert from L to target unit
    if to_unit == VolumeUnit.M3:
        return l_value / 1000
    elif to_unit == VolumeUnit.L:
        return l_value
    elif to_unit == VolumeUnit.GAL:
        return l_value / 3.78541
    else:
        raise ValueError(f"Unknown volume unit: {to_unit}")


def calculate_charge_balance(cations_meq_l: float, anions_meq_l: float) -> float:
    """
    Calculate charge balance error percentage.
    
    Args:
        cations_meq_l: Total cation charge in meq/L
        anions_meq_l: Total anion charge in meq/L
        
    Returns:
        Charge balance error as percentage
    """
    if cations_meq_l + anions_meq_l == 0:
        return 0.0
    
    return abs(cations_meq_l - anions_meq_l) / (cations_meq_l + anions_meq_l) * 100


def calculate_ionic_strength(ion_concentrations: Dict[str, float], ion_charges: Dict[str, int]) -> float:
    """
    Calculate ionic strength from ion concentrations.
    
    Args:
        ion_concentrations: Dictionary of ion concentrations in meq/L
        ion_charges: Dictionary of ion charges (e.g., {'Ca': 2, 'Na': 1})
        
    Returns:
        Ionic strength in mol/L
    """
    ionic_strength = 0.0
    
    for ion, conc_meq_l in ion_concentrations.items():
        if ion in ion_charges:
            charge = ion_charges[ion]
            # Convert meq/L to mol/L: meq/L / charge = mmol/L / 1000 = mol/L
            conc_mol_l = conc_meq_l / abs(charge) / 1000
            ionic_strength += 0.5 * conc_mol_l * charge**2
    
    return ionic_strength


def bed_volumes_to_volume(bed_volumes: float, bed_volume_L: float) -> float:
    """
    Convert bed volumes to actual volume.
    
    Args:
        bed_volumes: Number of bed volumes
        bed_volume_L: Bed volume in liters
        
    Returns:
        Actual volume in liters
    """
    return bed_volumes * bed_volume_L


def volume_to_bed_volumes(volume_L: float, bed_volume_L: float) -> float:
    """
    Convert actual volume to bed volumes.
    
    Args:
        volume_L: Volume in liters
        bed_volume_L: Bed volume in liters
        
    Returns:
        Number of bed volumes
    """
    return volume_L / bed_volume_L


def calculate_service_time(bed_volumes: float, bed_volume_L: float, flow_rate_L_hr: float) -> float:
    """
    Calculate service time from bed volumes and flow rate.
    
    Args:
        bed_volumes: Number of bed volumes until breakthrough
        bed_volume_L: Bed volume in liters
        flow_rate_L_hr: Flow rate in L/hr
        
    Returns:
        Service time in hours
    """
    total_volume_L = bed_volumes_to_volume(bed_volumes, bed_volume_L)
    return total_volume_L / flow_rate_L_hr


def calculate_linear_velocity(flow_m3_hr: float, diameter_m: float) -> float:
    """
    Calculate linear velocity from flow rate and vessel diameter.
    
    Args:
        flow_m3_hr: Flow rate in m³/hr
        diameter_m: Vessel diameter in meters
        
    Returns:
        Linear velocity in m/hr
    """
    area_m2 = math.pi * (diameter_m / 2) ** 2
    return flow_m3_hr / area_m2


def calculate_ebct(bed_volume_m3: float, flow_m3_hr: float) -> float:
    """
    Calculate Empty Bed Contact Time (EBCT).
    
    Args:
        bed_volume_m3: Bed volume in m³
        flow_m3_hr: Flow rate in m³/hr
        
    Returns:
        EBCT in minutes
    """
    ebct_hr = bed_volume_m3 / flow_m3_hr
    return ebct_hr * 60  # Convert to minutes


# Validation function
def validate_conversions():
    """
    Validate unit conversion functions.
    Called on module import to ensure correctness.
    """
    # Test concentration conversions
    assert abs(mg_to_meq(100, 'Ca') - 100/20.04) < 1e-6, "Ca mg to meq conversion error"
    assert abs(meq_to_mg(5, 'Ca') - 5*20.04) < 1e-6, "Ca meq to mg conversion error"
    
    # Test hardness calculation
    assert abs(calculate_hardness_as_caco3(40, 12) - (40*2.497 + 12*4.118)) < 1e-6, "Hardness calculation error"
    
    # Test flow conversions
    assert abs(convert_flow_rate(1, FlowUnit.M3_HR, FlowUnit.L_HR) - 1000) < 1e-6, "Flow conversion error"
    
    # Test volume conversions
    assert abs(convert_volume(1, VolumeUnit.M3, VolumeUnit.L) - 1000) < 1e-6, "Volume conversion error"


# Run validation on import
validate_conversions()