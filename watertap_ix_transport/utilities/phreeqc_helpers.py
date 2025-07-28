"""
PHREEQC Helper Functions

Utility functions for PHREEQC calculations, including resolution-independent
bed volume (BV) calculations.
"""

import numpy as np
from typing import Dict


def calculate_bv_parameters(bed_depth_m: float, diameter_m: float, porosity: float, cells: int) -> Dict[str, float]:
    """
    Calculate parameters needed for resolution-independent BV calculation.
    
    This function computes the necessary parameters to ensure bed volume (BV)
    calculations remain consistent regardless of the number of cells used in
    the PHREEQC TRANSPORT simulation.
    
    Args:
        bed_depth_m: Bed depth in meters
        diameter_m: Column diameter in meters
        porosity: Bed porosity (fraction)
        cells: Number of cells for TRANSPORT discretization
        
    Returns:
        Dictionary containing:
            - total_pore_volume_L: Total pore volume in liters
            - water_per_cell_kg: Water mass per cell in kg
            - cells: Number of cells
            - cell_length_m: Length of each cell in meters
            - bed_volume_L: Total bed volume in liters
            - resin_volume_L: Total resin volume in liters
            
    Example:
        >>> params = calculate_bv_parameters(2.0, 0.1, 0.4, 20)
        >>> print(f"Total pore volume: {params['total_pore_volume_L']:.1f} L")
        Total pore volume: 6.3 L
    """
    # Calculate cross-sectional area
    cross_section = np.pi * (diameter_m/2)**2
    
    # Calculate volumes
    total_volume_m3 = bed_depth_m * cross_section
    bed_volume_L = total_volume_m3 * 1000
    total_pore_volume_L = bed_volume_L * porosity
    resin_volume_L = bed_volume_L * (1 - porosity)
    
    # Calculate per-cell values
    cell_length_m = bed_depth_m / cells
    water_per_cell_kg = total_pore_volume_L / cells  # Assuming water density = 1 kg/L
    
    return {
        'total_pore_volume_L': total_pore_volume_L,
        'water_per_cell_kg': water_per_cell_kg,
        'cells': cells,
        'cell_length_m': cell_length_m,
        'bed_volume_L': bed_volume_L,
        'resin_volume_L': resin_volume_L
    }


def generate_bv_punch_lines(total_pore_volume_L: float, line_start: int = 10) -> list:
    """
    Generate PHREEQC USER_PUNCH lines for resolution-independent BV calculation.
    
    Args:
        total_pore_volume_L: Total pore volume in liters
        line_start: Starting line number for USER_PUNCH commands
        
    Returns:
        List of strings containing USER_PUNCH commands
        
    Example:
        >>> lines = generate_bv_punch_lines(6.28, 30)
        >>> for line in lines:
        ...     print(line)
        30 total_pore_vol = 6.280  # L
        40 w = POR()  # Get water mass in this cell (kg)
        50 bed_vol = STEP_NO * w / total_pore_vol
        60 PUNCH bed_vol
    """
    lines = []
    n = line_start
    
    lines.append(f"    {n} total_pore_vol = {total_pore_volume_L:.3f}  # L")
    n += 10
    lines.append(f"    {n} w = POR()  # Get water mass in this cell (kg)")
    n += 10
    lines.append(f"    {n} bed_vol = STEP_NO * w / total_pore_vol")
    n += 10
    lines.append(f"    {n} PUNCH bed_vol")
    
    return lines


def validate_bv_calculation(bed_depth_m: float, diameter_m: float, porosity: float,
                          cells_list: list = [10, 20, 40]) -> Dict[str, bool]:
    """
    Validate that BV calculations are resolution-independent.
    
    This function checks that the total pore volume calculation yields consistent
    results when divided by different numbers of cells.
    
    Args:
        bed_depth_m: Bed depth in meters
        diameter_m: Column diameter in meters
        porosity: Bed porosity (fraction)
        cells_list: List of cell counts to test
        
    Returns:
        Dictionary with validation results
    """
    results = []
    
    for cells in cells_list:
        params = calculate_bv_parameters(bed_depth_m, diameter_m, porosity, cells)
        
        # Check that water_per_cell * cells = total_pore_volume
        calc_total = params['water_per_cell_kg'] * cells
        expected_total = params['total_pore_volume_L']
        
        results.append({
            'cells': cells,
            'calculated_total': calc_total,
            'expected_total': expected_total,
            'error': abs(calc_total - expected_total)
        })
    
    # Check if all calculations are consistent
    max_error = max(r['error'] for r in results)
    is_valid = max_error < 1e-10  # Numerical tolerance
    
    return {
        'is_valid': is_valid,
        'max_error': max_error,
        'results': results
    }


def convert_hardcoded_bv(step_no: int, hardcoded_water_kg: float, hardcoded_resin_L: float,
                        actual_water_kg: float, actual_resin_L: float) -> float:
    """
    Convert a hardcoded BV calculation to the correct value.
    
    This function helps identify and fix hardcoded BV calculations like
    "BV = STEP_NO * 0.314 / 7.85" by converting them to the correct value
    based on actual column parameters.
    
    Args:
        step_no: PHREEQC step number
        hardcoded_water_kg: Hardcoded water volume per shift (e.g., 0.314)
        hardcoded_resin_L: Hardcoded resin volume (e.g., 7.85)
        actual_water_kg: Actual water volume per shift
        actual_resin_L: Actual resin volume
        
    Returns:
        Corrected BV value
        
    Example:
        >>> # Original: BV = STEP_NO * 0.314 / 7.85
        >>> # For 2m bed with 0.628 kg water per shift and 15.7 L resin:
        >>> correct_bv = convert_hardcoded_bv(100, 0.314, 7.85, 0.628, 15.7)
        >>> print(f"Corrected BV: {correct_bv:.1f}")
        Corrected BV: 4.0
    """
    # The hardcoded calculation
    hardcoded_bv = step_no * hardcoded_water_kg / hardcoded_resin_L
    
    # The correction factor
    water_factor = actual_water_kg / hardcoded_water_kg
    resin_factor = hardcoded_resin_L / actual_resin_L
    
    # Corrected BV
    correct_bv = hardcoded_bv * water_factor * resin_factor
    
    return correct_bv