"""
WAC PHREEQC Template Module

Provides PHREEQC input templates for Weak Acid Cation (WAC) exchange resins.
Includes templates for both Na-form and H-form WAC resins.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.core_config import CONFIG
from tools.base_ix_simulation import BaseIXSimulation

# Import enhanced generator if available
try:
    from tools.enhanced_phreeqc_generator import EnhancedPHREEQCGenerator
    from tools.wac_enhanced_species import generate_wac_exchange_species
    ENHANCED_GENERATOR_AVAILABLE = True
except ImportError:
    ENHANCED_GENERATOR_AVAILABLE = False

logger = logging.getLogger(__name__)


def create_wac_na_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 10,
    max_bv: int = 300,
    database_path: Optional[str] = None,
    enable_enhancements: bool = True,
    capacity_factor: float = 1.0
) -> str:
    """
    Create PHREEQC input for WAC Na-form simulation.
    
    Uses EXCHANGE blocks with WAC-specific selectivity coefficients.
    
    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        
    Returns:
        PHREEQC input string
    """
    # Get database path
    if database_path is None:
        database_path = str(CONFIG.get_phreeqc_database())
    
    # Calculate key parameters
    bed_volume_L = vessel_config['bed_volume_L']
    bed_depth_m = vessel_config.get('bed_depth_m', 1.5)  # Get bed depth for TRANSPORT
    flow_rate_L_hr = water_composition.get('flow_m3_hr', 100) * 1000
    
    # Cell volume and porosity
    cell_volume_L = bed_volume_L / cells
    porosity = 0.4
    pore_volume_L = bed_volume_L * porosity
    water_per_cell_kg = pore_volume_L / cells  # Water mass in kg (assuming density = 1)
    
    # WAC Na-form capacity
    capacity_eq_L = CONFIG.WAC_NA_WORKING_CAPACITY  # eq/L bed volume
    total_capacity_eq = capacity_eq_L * bed_volume_L  # Total exchange capacity
    
    # Exchange sites normalized per kg water (CRITICAL for PHREEQC)
    exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
    
    # Time step for one shift (hours)
    time_per_shift = bed_volume_L / flow_rate_L_hr
    
    # Calculate shifts using SAC's proven method
    # Each BV requires bed_volume_L / water_per_cell_kg shifts
    shifts = int(max_bv * bed_volume_L / water_per_cell_kg)
    
    # Apply capacity degradation if enabled
    effective_capacity_eq_L = capacity_eq_L
    if enable_enhancements and capacity_factor < 1.0:
        # Create a temporary helper instance
        class TempIXHelper(BaseIXSimulation):
            def run_simulation(self, input_data):
                pass
        
        helper = TempIXHelper()
        effective_capacity_eq_L = helper.apply_capacity_degradation(
            capacity_eq_L, capacity_factor
        )
        logger.info(f"Applied capacity factor {capacity_factor}: {capacity_eq_L} -> {effective_capacity_eq_L} eq/L")
        
        # Recalculate exchange capacity with degraded value
        total_capacity_eq = effective_capacity_eq_L * bed_volume_L
        exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
    
    # Generate enhanced exchange species if enabled
    exchange_species_block = ""
    temperature_c = water_composition.get('temperature_celsius', 25)

    if enable_enhancements and ENHANCED_GENERATOR_AVAILABLE:
        # Use enhanced pH-dependent model
        exchange_species_block = generate_wac_exchange_species(
            resin_type='WAC_Na',
            temperature_c=temperature_c,
            enhanced_selectivity=True
        )
    elif enable_enhancements:
        # Use helper to generate enhanced exchange species
        if 'helper' not in locals():
            class TempIXHelper(BaseIXSimulation):
                def run_simulation(self, input_data):
                    pass
            helper = TempIXHelper()

        exchange_species_block = helper.generate_enhanced_exchange_species(
            'WAC_Na', water_composition, temperature_c,
            capacity_factor,
            enable_ionic_strength=CONFIG.ENABLE_IONIC_STRENGTH_CORRECTION,
            enable_temperature=CONFIG.ENABLE_TEMPERATURE_CORRECTION
        )
    else:
        # Use default WAC-Na exchange species
        exchange_species_block = f"""# WAC-specific exchange reactions with enhanced selectivity
EXCHANGE_SPECIES
    # Identity reaction for master species (required)
    X- = X-
        log_k 0.0
    
    Na+ + X- = NaX
        log_k 0.0
    
    Ca+2 + 2X- = CaX2
        log_k {CONFIG.WAC_LOGK_CA_NA}
        -gamma 5.0 0.165
    
    Mg+2 + 2X- = MgX2
        log_k {CONFIG.WAC_LOGK_MG_NA}
        -gamma 5.5 0.2
    
    K+ + X- = KX
        log_k {CONFIG.WAC_LOGK_K_NA}
        -gamma 3.5 0.015"""
    
    # Build PHREEQC input
    phreeqc_input = f"""
DATABASE {database_path}

{exchange_species_block}

# Feed solution
SOLUTION 0 Feed water
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        {water_composition.get('pH', 7.5)}
    units     mg/L
    Ca        {water_composition.get('ca_mg_l', 0)}
    Mg        {water_composition.get('mg_mg_l', 0)}
    Na        {water_composition.get('na_mg_l', 0)}
    K         {water_composition.get('k_mg_l', 0)}
    Cl        {water_composition.get('cl_mg_l', 0)} charge
    Alkalinity {water_composition.get('hco3_mg_l', 0)} as HCO3
    S(6)      {water_composition.get('so4_mg_l', 0)} as SO4
    N(5)      {water_composition.get('no3_mg_l', 0)} as NO3
    water     1 kg

# Initial column solution (strong NaCl to ensure Na-form)
SOLUTION 1-{cells} Initial column water
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        7.0
    Na        1000
    Cl        1000 charge
    water     {water_per_cell_kg} kg

# WAC exchanger in Na form
EXCHANGE 1-{cells}
    X         {exchange_per_kg_water}
    -equilibrate solution 1-{cells}

# Transport simulation
TRANSPORT
    -cells    {cells}
    -shifts   {shifts}
    -time_step {time_per_shift * 3600}  # seconds
    -flow_direction forward
    -boundary_conditions flux flux
    -lengths  {cells}*{bed_depth_m/cells}  # m (geometric length per cell)
    -dispersivities {cells}*0.002  # m
    -porosities {cells}*{porosity}
    -punch_cells {cells}
    -punch_frequency 1

# Output for breakthrough curves
SELECTED_OUTPUT 1
    -file transport.sel
    -reset false
    -solution true
    -time true
    -step true
    -pH true
    -alkalinity true
    -totals Ca Mg Na K Cl C(4) S(6)
    -molalities H+ OH- CO2 HCO3- CO3-2
    -saturation_indices Calcite Aragonite Dolomite

USER_PUNCH 1
    -headings BV Cell Ca_mg/L Mg_mg/L Na_mg/L Hardness_mg/L pH Alk_CaCO3_mg/L CO2_mg/L
    -start
    10 REM BV calculation: volume passed / total bed volume
    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    30 IF (STEP_NO <= 0) THEN GOTO 200
    40 PUNCH BV, CELL_NO
    50 ca_mg = TOT("Ca") * 40.078 * 1000
    60 mg_mg = TOT("Mg") * 24.305 * 1000
    70 na_mg = TOT("Na") * 22.990 * 1000
    80 PUNCH ca_mg
    90 PUNCH mg_mg
    100 PUNCH na_mg
    110 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1
    120 PUNCH hardness_caco3
    130 PUNCH -LA("H+")
    140 PUNCH ALK * 50044  # Convert to mg/L as CaCO3
    150 PUNCH MOL("CO2") * 44010  # Actual CO2, not total carbonate
    200 REM end
    -end

END
"""
    
    return phreeqc_input


def create_wac_h_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 10,
    max_bv: int = 300,
    database_path: Optional[str] = None,
    enable_enhancements: bool = True,
    capacity_factor: float = 1.0
) -> str:
    """
    Create PHREEQC input for WAC H-form simulation.
    
    Uses EXCHANGE blocks with proper H+ exchange reactions.
    Models alkalinity removal through H+ release from resin.
    
    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        
    Returns:
        PHREEQC input string
    """
    # Get database path
    if database_path is None:
        database_path = str(CONFIG.get_phreeqc_database())
    
    # Calculate key parameters
    bed_volume_L = vessel_config['bed_volume_L']
    bed_depth_m = vessel_config.get('bed_depth_m', 1.5)  # Get bed depth for TRANSPORT
    flow_rate_L_hr = water_composition.get('flow_m3_hr', 100) * 1000
    
    # Cell volume and porosity
    cell_volume_L = bed_volume_L / cells
    porosity = 0.4
    pore_volume_L = bed_volume_L * porosity
    water_per_cell_kg = pore_volume_L / cells  # Water mass in kg (assuming density = 1)
    
    # WAC H-form capacity
    total_capacity_eq_L = CONFIG.WAC_H_TOTAL_CAPACITY  # eq/L bed volume
    total_capacity_eq = total_capacity_eq_L * bed_volume_L  # Total capacity
    
    # For H-form WAC, limit capacity to what can be utilized by alkalinity
    # Calculate alkalinity in eq/L
    alkalinity_eq_L = water_composition.get('hco3_mg_l', 0) / CONFIG.HCO3_EQUIV_WEIGHT / 1000
    
    # The effective capacity is limited by alkalinity availability
    # WAC can only remove hardness up to the alkalinity equivalent
    # But we still need full capacity for proper operation
    
    # Exchange sites normalized per kg water (CRITICAL for PHREEQC)
    exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
    
    # Time step for one shift (hours)
    time_per_shift = bed_volume_L / flow_rate_L_hr
    
    # Calculate shifts using SAC's proven method
    # Each BV requires bed_volume_L / water_per_cell_kg shifts
    shifts = int(max_bv * bed_volume_L / water_per_cell_kg)
    
    # Apply capacity degradation if enabled
    effective_capacity_eq_L = total_capacity_eq_L
    if enable_enhancements and capacity_factor < 1.0:
        # Create a temporary helper instance
        class TempIXHelper(BaseIXSimulation):
            def run_simulation(self, input_data):
                pass
        
        helper = TempIXHelper()
        effective_capacity_eq_L = helper.apply_capacity_degradation(
            total_capacity_eq_L, capacity_factor
        )
        logger.info(f"Applied capacity factor {capacity_factor}: {total_capacity_eq_L} -> {effective_capacity_eq_L} eq/L")
        
        # Recalculate exchange capacity with degraded value
        total_capacity_eq = effective_capacity_eq_L * bed_volume_L
        exchange_per_kg_water = total_capacity_eq / cells / water_per_cell_kg
    
    # Generate enhanced exchange species if enabled
    exchange_species_block = ""
    temperature_c = water_composition.get('temperature_celsius', 25)

    if enable_enhancements and ENHANCED_GENERATOR_AVAILABLE:
        # Use enhanced pH-dependent model
        exchange_species_block = generate_wac_exchange_species(
            resin_type='WAC_H',
            temperature_c=temperature_c,
            enhanced_selectivity=True
        )
    elif enable_enhancements:
        # Use helper to generate enhanced exchange species
        if 'helper' not in locals():
            class TempIXHelper(BaseIXSimulation):
                def run_simulation(self, input_data):
                    pass
            helper = TempIXHelper()

        exchange_species_block = helper.generate_enhanced_exchange_species(
            'WAC_H', water_composition, temperature_c,
            capacity_factor,
            enable_ionic_strength=CONFIG.ENABLE_IONIC_STRENGTH_CORRECTION,
            enable_temperature=CONFIG.ENABLE_TEMPERATURE_CORRECTION
        )
    else:
        # Use default WAC-H exchange species
        exchange_species_block = f"""# WAC H-form exchange reactions with H+ release
EXCHANGE_SPECIES
    # Identity reaction for master species (required)
    X- = X-
        log_k 0.0
    
    # H+ is reference species for H-form resin
    H+ + X- = HX
        log_k 0.0
    
    # Ca exchange releases 2H+ (models alkalinity consumption)
    Ca+2 + 2HX = CaX2 + 2H+
        log_k {CONFIG.WAC_LOGK_CA_H}  # ~2.0 for favorable exchange
        -gamma 5.0 0.165
    
    # Mg exchange releases 2H+
    Mg+2 + 2HX = MgX2 + 2H+
        log_k {CONFIG.WAC_LOGK_MG_H}  # ~1.8
        -gamma 5.5 0.2
    
    # Na exchange releases H+ (less favorable)
    Na+ + HX = NaX + H+
        log_k {CONFIG.WAC_LOGK_NA_H}  # ~0.5
        -gamma 4.0 0.075
    
    # K exchange releases H+
    K+ + HX = KX + H+
        log_k {CONFIG.WAC_LOGK_K_H}  # ~0.7
        -gamma 3.5 0.015"""
    
    # Build PHREEQC input
    phreeqc_input = f"""
DATABASE {database_path}

{exchange_species_block}

# Feed solution
SOLUTION 0 Feed water
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        {water_composition.get('pH', 7.5)}
    units     mg/L
    Ca        {water_composition.get('ca_mg_l', 0)}
    Mg        {water_composition.get('mg_mg_l', 0)}
    Na        {water_composition.get('na_mg_l', 0)}
    K         {water_composition.get('k_mg_l', 0)}
    Cl        {water_composition.get('cl_mg_l', 0)} charge
    Alkalinity {water_composition.get('hco3_mg_l', 0)} as HCO3
    S(6)      {water_composition.get('so4_mg_l', 0)} as SO4
    N(5)      {water_composition.get('no3_mg_l', 0)} as NO3
    water     1 kg

# Initial column solution (mildly acidic to maintain H-form without being extreme)
SOLUTION 1-{cells} Initial column water
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        5.5
    Cl        0.01 charge  # Small amount of Cl- to balance H+ at pH 5.5
    water     {water_per_cell_kg} kg

# WAC exchanger - initialize as H-form via equilibration
EXCHANGE 1-{cells}
    -equilibrate solution 1-{cells}
    X         {exchange_per_kg_water}

# Transport simulation
TRANSPORT
    -cells    {cells}
    -shifts   {shifts}
    -time_step {time_per_shift * 3600}  # seconds
    -flow_direction forward
    -boundary_conditions flux flux
    -lengths  {cells}*{bed_depth_m/cells}  # m (geometric length per cell)
    -dispersivities {cells}*0.002  # m
    -porosities {cells}*{porosity}
    -punch_cells {cells}
    -punch_frequency 1

# Output for breakthrough curves
SELECTED_OUTPUT 1
    -file transport.sel
    -reset false
    -solution true
    -time true
    -step true
    -pH true
    -alkalinity true
    -totals Ca Mg Na K Cl C(4) S(6)
    -molalities H+ OH- CO2 HCO3- CO3-2 CaX2 MgX2 NaX KX HX
    -saturation_indices Calcite Aragonite Dolomite

USER_PUNCH 1
    -headings BV Cell Ca_mg/L Mg_mg/L Na_mg/L Hardness_mg/L pH Alk_CaCO3_mg/L CO2_mg/L Active_Sites_% Removal_%
    -start
    10 REM BV calculation: volume passed / total bed volume
    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    30 IF (STEP_NO <= 0) THEN GOTO 300
    40 PUNCH BV, CELL_NO
    50 ca_mg = TOT("Ca") * 40.078 * 1000
    60 mg_mg = TOT("Mg") * 24.305 * 1000
    70 na_mg = TOT("Na") * 22.990 * 1000
    80 PUNCH ca_mg
    90 PUNCH mg_mg
    100 PUNCH na_mg
    110 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1
    120 PUNCH hardness_caco3
    130 PUNCH -LA("H+")
    140 alk_mg = ALK * 61000
    145 IF (alk_mg < 0) THEN alk_mg = 0
    150 PUNCH alk_mg
    160 co2_mg = MOL("CO2") * 44010  # MOL is mol/kgw, MW=44010 mg/mol
    170 PUNCH co2_mg
    # Calculate active sites percentage based on HX fraction
    # HX mol/kg water, need to compare to total exchange per kg water
    180 hx_mol = MOL("HX")
    185 total_x = {exchange_per_kg_water}
    190 active_percent = (hx_mol / total_x) * 100
    195 IF (active_percent > 100) THEN active_percent = 100
    200 PUNCH active_percent
    # Calculate alkalinity removal
    220 feed_alk = {water_composition.get('hco3_mg_l', 0)}
    230 IF (feed_alk > 0) THEN removal = (1 - alk_mg/feed_alk) * 100 ELSE removal = 0
    240 IF (removal < 0) THEN removal = 0
    250 PUNCH removal
    300 REM end
    -end

END
"""
    
    return phreeqc_input


def create_wac_h_surface_phreeqc_input(
    water_composition: Dict[str, float],
    vessel_config: Dict[str, float],
    cells: int = 10,
    max_bv: int = 300,
    database_path: Optional[str] = None
) -> str:
    """
    Create PHREEQC input for WAC H-form simulation using SURFACE blocks.
    
    Models pH-dependent exchange capacity using carboxylic acid surface sites.
    This naturally limits hardness removal to temporary hardness without post-processing.
    
    Args:
        water_composition: Feed water composition (mg/L)
        vessel_config: Vessel configuration with bed_volume_L
        cells: Number of cells for discretization
        max_bv: Maximum bed volumes to simulate
        database_path: Path to PHREEQC database
        
    Returns:
        PHREEQC input string
    """
    # Get database path
    if database_path is None:
        database_path = str(CONFIG.get_phreeqc_database())
    
    # Calculate key parameters
    bed_volume_L = vessel_config['bed_volume_L']
    bed_depth_m = vessel_config.get('bed_depth_m', 1.5)  # Get bed depth for TRANSPORT
    flow_rate_L_hr = water_composition.get('flow_m3_hr', 100) * 1000
    
    # Cell volume and porosity
    cell_volume_L = bed_volume_L / cells
    porosity = 0.4
    pore_volume_L = bed_volume_L * porosity
    water_per_cell_kg = pore_volume_L / cells  # Water mass in kg (assuming density = 1)
    
    # WAC H-form capacity - total COOH groups per L bed volume
    total_capacity_mol_L = CONFIG.WAC_H_TOTAL_CAPACITY  # mol COOH/L bed volume
    total_capacity_mol = total_capacity_mol_L * bed_volume_L  # Total moles of COOH
    
    # Surface sites per cell (distributed evenly)
    sites_per_cell = total_capacity_mol / cells
    
    # Time step for one shift (hours)
    time_per_shift = bed_volume_L / flow_rate_L_hr
    
    # Calculate shifts
    shifts = int(max_bv * bed_volume_L / water_per_cell_kg)
    
    # Build PHREEQC input
    phreeqc_input = f"""
DATABASE {database_path}

# Define carboxylic acid surface sites for WAC resin
# Using Wac_ prefix for weak acid cation sites (similar to Hfo_ for hydrous ferric oxide)
SURFACE_MASTER_SPECIES
    Wac_s Wac_sOH

SURFACE_SPECIES
    # Reference species (protonated carboxylic acid)
    Wac_sOH = Wac_sOH
        log_k 0
    
    # Deprotonation reaction (pKa = 4.5)
    Wac_sOH = Wac_sO- + H+
        log_k -4.5
    
    # Additional protonation at very low pH (if needed)
    Wac_sOH + H+ = Wac_sOH2+
        log_k 2.0
    
    # Divalent cation binding (2:1 stoichiometry)
    2Wac_sO- + Ca+2 = (Wac_sO)2Ca
        log_k 1.0  # Calibrated to achieve ~30% hardness removal
    
    2Wac_sO- + Mg+2 = (Wac_sO)2Mg
        log_k 0.8  # Calibrated to achieve ~30% hardness removal
    
    # Monovalent cation binding
    Wac_sO- + Na+ = Wac_sONa
        log_k 3.0  # Lower affinity than divalent cations
    
    Wac_sO- + K+ = Wac_sOK
        log_k 3.2  # Slightly higher than Na

# Feed solution
SOLUTION 0 Feed water
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        {water_composition.get('pH', 7.5)}
    units     mg/L
    Ca        {water_composition.get('ca_mg_l', 0)}
    Mg        {water_composition.get('mg_mg_l', 0)}
    Na        {water_composition.get('na_mg_l', 0)}
    K         {water_composition.get('k_mg_l', 0)}
    Cl        {water_composition.get('cl_mg_l', 0)} charge
    Alkalinity {water_composition.get('hco3_mg_l', 0)} as HCO3
    S(6)      {water_composition.get('so4_mg_l', 0)} as SO4
    N(5)      {water_composition.get('no3_mg_l', 0)} as NO3
    water     1 kg

# Initial column solution (acidic to protonate sites)
SOLUTION 1-{cells} Initial column water
    temp      {water_composition.get('temperature_celsius', 25)}
    pH        3.0
    Cl        1 charge
    water     {water_per_cell_kg} kg

# Surface sites distributed across cells"""
    
    # Add SURFACE blocks for each cell
    for i in range(1, cells + 1):
        phreeqc_input += f"""

SURFACE {i}
    -sites_units absolute
    -no_edl
    Wac_s {sites_per_cell} 1 1
    -equilibrate solution {i}"""
    
    phreeqc_input += f"""

# Transport simulation
TRANSPORT
    -cells    {cells}
    -shifts   {shifts}
    -time_step {time_per_shift * 3600}  # seconds
    -flow_direction forward
    -boundary_conditions flux flux
    -lengths  {cells}*{bed_depth_m/cells}  # m (geometric length per cell)
    -dispersivities {cells}*0.002  # m
    -porosities {cells}*{porosity}
    -punch_cells {cells}
    -punch_frequency 1

# Output for breakthrough curves
SELECTED_OUTPUT 1
    -file transport.sel
    -reset false
    -solution true
    -time true
    -step true
    -pH true
    -alkalinity true
    -totals Ca Mg Na K Cl C(4) S(6)
    -molalities H+ OH- CO2 HCO3- CO3-2 Wac_sOH Wac_sO- (Wac_sO)2Ca (Wac_sO)2Mg Wac_sONa Wac_sOK
    -saturation_indices Calcite Aragonite Dolomite

USER_PUNCH 1
    -headings BV Cell Ca_mg/L Mg_mg/L Na_mg/L Hardness_mg/L pH Alk_CaCO3_mg/L CO2_mg/L Active_Sites_% Ca_Removal_%
    -start
    10 REM BV calculation: volume passed / total bed volume
    20 BV = STEP_NO * {water_per_cell_kg} / {bed_volume_L}
    30 IF (STEP_NO <= 0) THEN GOTO 300
    40 PUNCH BV, CELL_NO
    50 ca_mg = TOT("Ca") * 40.078 * 1000
    60 mg_mg = TOT("Mg") * 24.305 * 1000
    70 na_mg = TOT("Na") * 22.990 * 1000
    80 PUNCH ca_mg
    90 PUNCH mg_mg
    100 PUNCH na_mg
    110 hardness_caco3 = ca_mg * 2.5 + mg_mg * 4.1
    120 PUNCH hardness_caco3
    130 PUNCH -LA("H+")
    140 alk_mg = ALK * 61000
    145 IF (alk_mg < 0) THEN alk_mg = 0
    150 PUNCH alk_mg
    160 co2_mg = MOL("CO2") * 44010  # MOL is mol/kgw, MW=44010 mg/mol
    170 PUNCH co2_mg
    # Calculate active sites percentage based on Wac_sO- fraction
    180 wac_so_mol = MOL("Wac_sO-")
    185 wac_soh_mol = MOL("Wac_sOH")
    190 total_sites = wac_so_mol + wac_soh_mol + 2*MOL("(Wac_sO)2Ca") + 2*MOL("(Wac_sO)2Mg") + MOL("Wac_sONa") + MOL("Wac_sOK")
    195 IF (total_sites > 0) THEN active_percent = (wac_so_mol / total_sites) * 100 ELSE active_percent = 0
    200 PUNCH active_percent
    # Calculate Ca removal
    220 feed_ca = {water_composition.get('ca_mg_l', 0)}
    230 IF (feed_ca > 0) THEN ca_removal = (1 - ca_mg/feed_ca) * 100 ELSE ca_removal = 0
    240 IF (ca_removal < 0) THEN ca_removal = 0
    250 PUNCH ca_removal
    300 REM end
    -end

END
"""
    
    return phreeqc_input




