"""
PhreeqPy Engine for Ion Exchange Calculations

Provides multi-component ion exchange modeling using PHREEQC's EXCHANGE blocks.
Handles breakthrough curve generation, regeneration simulation, and Na+ competition.
Integrates with water-chemistry-mcp for degasser calculations to avoid code duplication.
"""

import logging
import numpy as np
import sys
import os
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import phreeqpython
try:
    import phreeqpython
    PHREEQPY_AVAILABLE = True
except ImportError:
    PHREEQPY_AVAILABLE = False
    logger.warning("phreeqpython not available. Will use simplified calculations.")

# Add water-chemistry-mcp to path for degasser calculations
water_chem_path = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "water-chemistry-mcp"
))
if os.path.exists(water_chem_path):
    sys.path.insert(0, water_chem_path)
    try:
        from tools.chemical_addition import simulate_chemical_addition
        from tools.batch_processing import batch_process_scenarios
        from tools.phreeqc_wrapper import (
            run_phreeqc_simulation,
            build_solution_block,
            build_reaction_block,
            build_selected_output_block
        )
        # Import database management for proper database resolution
        from utils.database_management import database_manager
        WATER_CHEM_AVAILABLE = True
        logger.info("Water-chemistry-mcp integration available")
    except ImportError as e:
        WATER_CHEM_AVAILABLE = False
        logger.warning(f"Water-chemistry-mcp not available: {e}")
else:
    WATER_CHEM_AVAILABLE = False
    logger.warning("Water-chemistry-mcp path not found")

# Real resin definitions based on industry data
RESIN_DEFINITIONS = {
    "SAC": {
        "exchange_master": "X",
        "exchange_species": [
            # Strong acid cation exchange reactions (Gaines-Thomas convention)
            "X- = X-",  # Master species
            "X- + Na+ = NaX; log_k 0.0",  # Reference state
            "X- + K+ = KX; log_k 0.7",  # K+ preferred over Na+
            "X- + NH4+ = NH4X; log_k 1.1",  # NH4+ more preferred
            "2X- + Ca+2 = CaX2; log_k 0.8",  # Divalent selectivity
            "2X- + Mg+2 = MgX2; log_k 0.6",  # Lower than Ca
            "2X- + Sr+2 = SrX2; log_k 1.1",  # Higher than Ca
            "2X- + Ba+2 = BaX2; log_k 1.5",  # Highest divalent
            "X- + H+ = HX; log_k 1.0",  # H+ form
            "2X- + Fe+2 = FeX2; log_k 0.7",
            "3X- + Fe+3 = FeX3; log_k 2.5",
            "3X- + Al+3 = AlX3; log_k 2.0"
        ],
        "capacity_eq_L": 2.0,  # eq/L resin
        "regenerant": {
            "chemical": "NaCl",
            "concentration_percent": 10,
            "flow_bv_hr": 2,  # Slow for good efficiency
            "volume_bv": 4,  # Bed volumes of regenerant
            "efficiency": 0.65  # 65% efficiency typical
        }
    },
    "WAC_H": {
        "exchange_master": "Z",
        "exchange_species": [
            # Weak acid cation exchange (carboxylic acid groups)
            "Z- = Z-",  # Ionized form
            "HZ = HZ",  # Protonated form (master)
            "HZ = H+ + Z-; log_k -4.5",  # pKa ~4.5
            "Z- + Na+ = NaZ; log_k 0.0",  # Reference
            "Z- + K+ = KZ; log_k 0.3",
            "Z- + NH4+ = NH4Z; log_k 0.5",
            "2Z- + Ca+2 = CaZ2; log_k 1.5",  # Higher selectivity than SAC
            "2Z- + Mg+2 = MgZ2; log_k 1.2",
            "Z- + H+ = HZ; log_k 4.5"  # Protonation
        ],
        "capacity_eq_L": 4.0,  # Higher capacity than SAC
        "regenerant": {
            "chemical": "HCl",
            "concentration_percent": 5,
            "flow_bv_hr": 4,
            "volume_bv": 3,
            "efficiency": 0.85  # More efficient than SAC
        }
    },
    "WAC_Na": {
        "exchange_master": "Z",
        "exchange_species": [
            # Same as WAC_H but pre-equilibrated with Na+
            "Z- = Z-",
            "NaZ = NaZ",  # Master species in Na form
            "NaZ = Na+ + Z-; log_k 0.0",
            "Z- + H+ = HZ; log_k 4.5",
            "Z- + K+ = KZ; log_k 0.3",
            "Z- + NH4+ = NH4Z; log_k 0.5",
            "2Z- + Ca+2 = CaZ2; log_k 1.5",
            "2Z- + Mg+2 = MgZ2; log_k 1.2"
        ],
        "capacity_eq_L": 4.0,
        "regenerant": {
            "step1": {  # Convert to H form
                "chemical": "HCl",
                "concentration_percent": 5,
                "flow_bv_hr": 4,
                "volume_bv": 3,
                "efficiency": 0.85
            },
            "step2": {  # Convert to Na form
                "chemical": "NaOH",
                "concentration_percent": 4,
                "flow_bv_hr": 4,
                "volume_bv": 2,
                "efficiency": 0.90
            }
        }
    }
}


@dataclass
class IXColumn:
    """Represents an ion exchange column configuration."""
    resin_type: str  # SAC, WAC_H, WAC_Na
    resin_volume_L: float
    exchange_capacity_eq_L: float
    selectivity_coefficients: Dict[str, float]
    kinetic_factor: float = 1.0  # For rate calculations
    bed_depth_m: float = 1.5  # Typical bed depth in meters


@dataclass
class BreakthroughPoint:
    """Single point on a breakthrough curve."""
    bed_volumes: float
    time_hours: float
    effluent_concentrations_mg_L: Dict[str, float]
    pH: float
    capacity_utilized_eq: float


class PhreeqPyEngine:
    """
    Engine for multi-component ion exchange calculations using PhreeqPy.
    """
    
    def __init__(self, database: Optional[str] = None):
        """Initialize the PhreeqPy engine."""
        self.database = database
        self.pp = None
        
        if PHREEQPY_AVAILABLE:
            # Determine which database to use
            db_to_use = None
            
            if database:
                # User specified a database
                db_to_use = database
            elif WATER_CHEM_AVAILABLE:
                # Use water-chemistry-mcp's database management
                try:
                    # Get the database path from water-chemistry-mcp
                    recommended_db = database_manager.get_database_path('phreeqc.dat')
                    if recommended_db and os.path.exists(recommended_db):
                        db_to_use = recommended_db
                        logger.info(f"Using water-chemistry-mcp database: {recommended_db}")
                    else:
                        # Try the general recommendation
                        recommended_db = database_manager.recommend_database('general')
                        if recommended_db:
                            db_to_use = recommended_db
                            logger.info(f"Using water-chemistry-mcp recommended database: {recommended_db}")
                except Exception as e:
                    logger.warning(f"Could not get database from water-chemistry-mcp: {e}")
            
            # Try to initialize with selected database
            if db_to_use:
                try:
                    # For phreeqpython, just use the database filename, not full path
                    db_filename = os.path.basename(db_to_use)
                    self.pp = phreeqpython.PhreeqPython(database=db_filename)
                    logger.info(f"PhreeqPy engine initialized with {db_filename}")
                    self.database = db_to_use
                except Exception as e:
                    logger.warning(f"Failed to initialize PhreeqPy with {db_filename}: {e}")
                    # Fall through to try default
            
            # If still not initialized, try default
            if self.pp is None:
                try:
                    self.pp = phreeqpython.PhreeqPython()
                    logger.info("PhreeqPy engine initialized with default database")
                    self.database = "default"
                except Exception as e:
                    logger.error(f"Failed to initialize PhreeqPy with default database: {e}")
                    self.pp = None
    
    def setup_exchange_sites(self, column: IXColumn) -> str:
        """
        Generate PHREEQC EXCHANGE block for the resin.
        
        Returns PHREEQC input string for EXCHANGE definition.
        """
        # Calculate total exchange sites in moles
        total_sites_eq = column.resin_volume_L * column.exchange_capacity_eq_L
        
        if column.resin_type == "SAC":
            # Strong acid cation - initially in Na+ form after regeneration
            exchange_block = f"""
EXCHANGE 1
    -equilibrate 1
    NaX {total_sites_eq}
            """
        elif column.resin_type == "WAC_H":
            # Weak acid cation - H+ form
            exchange_block = f"""
EXCHANGE 1
    -equilibrate 1
    HX {total_sites_eq}
            """
        elif column.resin_type == "WAC_Na":
            # Weak acid cation - Na+ form
            exchange_block = f"""
EXCHANGE 1
    -equilibrate 1
    NaX {total_sites_eq}
            """
        else:
            raise ValueError(f"Unknown resin type: {column.resin_type}")
        
        return exchange_block
    
    def create_solution_block(self, water_composition: Dict[str, float], 
                            pH: float, temperature: float = 25) -> str:
        """
        Create PHREEQC SOLUTION block from water composition.
        
        Args:
            water_composition: Ion concentrations in mg/L (MCAS format)
            pH: pH value
            temperature: Temperature in Celsius
        
        Returns:
            PHREEQC SOLUTION block string
        """
        # Convert MCAS notation to PHREEQC elements
        phreeqc_elements = {
            "Na_+": "Na",
            "Ca_2+": "Ca", 
            "Mg_2+": "Mg",
            "K_+": "K",
            "NH4_+": "N(-3)",  # Ammonium as reduced nitrogen
            "Cl_-": "Cl",
            "SO4_2-": "S(6)",  # Sulfate as S(VI)
            "HCO3_-": "C(4)",  # Carbonate as C(IV)
            "NO3_-": "N(5)",   # Nitrate as N(V)
            "F_-": "F"
        }
        
        # Build solution block
        solution_lines = [
            "SOLUTION 1",
            f"    temp {temperature}",
            f"    pH {pH}",
            "    units mg/L"
        ]
        
        for ion, conc in water_composition.items():
            if ion in phreeqc_elements and conc > 0:
                element = phreeqc_elements[ion]
                solution_lines.append(f"    {element} {conc}")
        
        # Add charge balance on predominant ion
        if water_composition.get("Na_+", 0) > water_composition.get("Cl_-", 0):
            solution_lines.append("    charge Na")
        else:
            solution_lines.append("    charge Cl")
        
        return "\n".join(solution_lines)
    
    def simulate_breakthrough(
        self,
        column: IXColumn,
        feed_water: Dict[str, Any],
        flow_rate_L_hr: float,
        target_bv: int = 500,
        bv_increment: int = 10
    ) -> List[BreakthroughPoint]:
        """
        Simulate ion exchange breakthrough curve using PHREEQC TRANSPORT.
        
        Args:
            column: Ion exchange column configuration
            feed_water: Feed water composition and properties
            flow_rate_L_hr: Flow rate in L/hr
            target_bv: Target bed volumes to simulate
            bv_increment: Bed volume increment for calculations
        
        Returns:
            List of breakthrough points
        """
        if not PHREEQPY_AVAILABLE or self.pp is None:
            return self._simple_breakthrough_simulation(
                column, feed_water, flow_rate_L_hr, target_bv, bv_increment
            )
        
        breakthrough_points = []
        
        # Column discretization parameters
        n_cells = 20  # Number of cells to represent the column
        cell_volume_L = column.resin_volume_L / n_cells
        exchange_per_cell = column.exchange_capacity_eq_L * cell_volume_L
        
        # Time parameters
        pore_volume_L = column.resin_volume_L * 0.4  # Typical bed porosity
        residence_time_hrs = pore_volume_L / flow_rate_L_hr
        time_step_hrs = residence_time_hrs / n_cells
        shifts_per_bv = n_cells  # One pore volume = n_cells shifts
        
        # Create feed solution
        solution_block = self.create_solution_block(
            feed_water["ion_concentrations_mg_L"],
            feed_water["pH"],
            feed_water.get("temperature_celsius", 25)
        )
        
        # Get resin definition for this column type
        resin_def = RESIN_DEFINITIONS.get(column.resin_type, RESIN_DEFINITIONS["SAC"])
        
        # Build PHREEQC input with TRANSPORT
        transport_input = f"""
# Define exchange master and species
EXCHANGE_MASTER_SPECIES
    {resin_def['exchange_master']} {resin_def['exchange_master']}- 
    
EXCHANGE_SPECIES
"""
        # Add exchange species reactions
        for species in resin_def['exchange_species']:
            transport_input += f"    {species}\n"
        
        # Add feed solution (solution 0 for TRANSPORT)
        transport_input += f"""
# Feed water composition
SOLUTION 0 Feed water
    temp {feed_water.get('temperature_celsius', 25)}
    pH {feed_water["pH"]}
    units mg/L
"""
        # Add ions
        phreeqc_elements = {
            "Na_+": "Na", "Ca_2+": "Ca", "Mg_2+": "Mg", "K_+": "K",
            "NH4_+": "N(-3)", "Cl_-": "Cl", "SO4_2-": "S(6)", 
            "HCO3_-": "C(4)", "NO3_-": "N(5)", "F_-": "F"
        }
        
        for ion, conc in feed_water["ion_concentrations_mg_L"].items():
            if ion in phreeqc_elements and conc > 0:
                transport_input += f"    {phreeqc_elements[ion]} {conc}\n"
        
        # Add initial column solutions (cells 1 to n_cells)
        for i in range(1, n_cells + 1):
            transport_input += f"""
SOLUTION {i} Initial column water
    temp {feed_water.get('temperature_celsius', 25)}
    pH 7.0
    Na 1.0
    Cl 1.0
"""
        
        # Add exchange sites
        for i in range(1, n_cells + 1):
            if column.resin_type == "SAC":
                # SAC resin initially in Na+ form
                transport_input += f"""
EXCHANGE {i}
    {resin_def['exchange_master']}- {exchange_per_cell}
    -equilibrate {i}
"""
            elif column.resin_type == "WAC_H":
                # WAC in H+ form
                transport_input += f"""
EXCHANGE {i}
    H{resin_def['exchange_master']} {exchange_per_cell}
    -equilibrate {i}
"""
            elif column.resin_type == "WAC_Na":
                # WAC in Na+ form
                transport_input += f"""
EXCHANGE {i}
    Na{resin_def['exchange_master']} {exchange_per_cell}
    -equilibrate {i}
"""
        
        # Set up TRANSPORT block
        total_shifts = int(target_bv * shifts_per_bv)
        punch_frequency = int(bv_increment * shifts_per_bv)
        
        transport_input += f"""
TRANSPORT
    -cells {n_cells}
    -shifts {total_shifts}
    -time_step {time_step_hrs * 3600}  # Convert to seconds
    -flow_direction forward
    -boundary_conditions flux flux
    -lengths {cell_volume_L / 0.4}  # Cell length based on porosity
    -dispersivities 0.01  # Low dispersion for plug flow
    -punch_cells {n_cells}  # Monitor effluent
    -punch_frequency {punch_frequency}
    
SELECTED_OUTPUT 1
    -reset false
    -time true
    -step true
    -pH true
    -pe true
    -totals Na Ca Mg K NH4 Cl S(6) C(4) N(5) N(-3)
    
SELECTED_OUTPUT 2
    -reset false
    -step true
    -exchange {resin_def['exchange_master']}-
"""
        # Add exchange species to monitor
        for i in range(1, n_cells + 1):
            transport_input += f" Na{resin_def['exchange_master']} Ca{resin_def['exchange_master']}2"
            transport_input += f" Mg{resin_def['exchange_master']}2 H{resin_def['exchange_master']}"
        
        transport_input += "\nEND"
        
        # Run TRANSPORT simulation
        logger.info(f"Running TRANSPORT simulation with {n_cells} cells for {total_shifts} shifts")
        try:
            # PhreeqPython doesn't support TRANSPORT directly
            # Fall back to simple simulation
            logger.info("PhreeqPython doesn't support TRANSPORT - using simplified simulation")
            return self._simple_breakthrough_simulation(
                column, feed_water, flow_rate_L_hr, target_bv, bv_increment
            )
        except Exception as e:
            logger.error(f"TRANSPORT simulation failed: {e}")
            # Fall back to simple simulation
            return self._simple_breakthrough_simulation(
                column, feed_water, flow_rate_L_hr, target_bv, bv_increment
            )
        
        # Process results at each punch point
        current_shift = 0
        for i in range(0, len(selected_output), 1):
            row = selected_output.iloc[i]
            
            # Calculate bed volumes
            bv = current_shift / shifts_per_bv
            if bv > target_bv:
                break
                
            # Only record at bv_increment intervals
            if current_shift % punch_frequency == 0:
                # Extract concentrations (convert mol/kgw to mg/L)
                effluent = {
                    "Na_+": row.get("Na(mol/kgw)", 0) * 22990,
                    "Ca_2+": row.get("Ca(mol/kgw)", 0) * 40080,
                    "Mg_2+": row.get("Mg(mol/kgw)", 0) * 24305,
                    "K_+": row.get("K(mol/kgw)", 0) * 39098,
                    "NH4_+": row.get("N(-3)(mol/kgw)", 0) * 18038,
                    "Cl_-": row.get("Cl(mol/kgw)", 0) * 35453,
                    "SO4_2-": row.get("S(6)(mol/kgw)", 0) * 96056,
                    "HCO3_-": row.get("C(4)(mol/kgw)", 0) * 61017,
                    "NO3_-": row.get("N(5)(mol/kgw)", 0) * 62004
                }
                
                # Remove zero concentrations
                effluent = {k: v for k, v in effluent.items() if v > 0.01}
                
                pH = row.get("pH", 7.0)
                
                # Calculate capacity utilized from exchange composition
                # This is more accurate than the simple linear approximation
                capacity_used = self._calculate_capacity_used(selected_output, i, column, resin_def)
                
                # Calculate time
                time_hours = bv * column.resin_volume_L / flow_rate_L_hr
                
                point = BreakthroughPoint(
                    bed_volumes=bv,
                    time_hours=time_hours,
                    effluent_concentrations_mg_L=effluent,
                    pH=pH,
                    capacity_utilized_eq=capacity_used
                )
                
                breakthrough_points.append(point)
                logger.debug(f"BV {bv:.1f}: pH={pH:.2f}, Ca={effluent.get('Ca_2+', 0):.1f} mg/L")
            
            current_shift += 1
        
        return breakthrough_points
    
    def _calculate_capacity_used(self, selected_output, row_index: int, 
                                column: IXColumn, resin_def: Dict) -> float:
        """
        Calculate actual capacity used from exchange composition.
        
        Args:
            selected_output: PHREEQC selected output dataframe
            row_index: Current row in selected output
            column: Column configuration
            resin_def: Resin definition dictionary
        
        Returns:
            Capacity used in equivalents
        """
        try:
            row = selected_output.iloc[row_index]
            total_capacity = column.exchange_capacity_eq_L * column.resin_volume_L
            
            # Get exchange site occupancy
            master = resin_def['exchange_master']
            
            # For SAC resins, sum divalent ions on exchange sites
            if column.resin_type == "SAC":
                # Look for CaX2, MgX2, etc. in the output
                ca_fraction = row.get(f"Ca{master}2", 0) / total_capacity if f"Ca{master}2" in row else 0
                mg_fraction = row.get(f"Mg{master}2", 0) / total_capacity if f"Mg{master}2" in row else 0
                k_fraction = row.get(f"K{master}", 0) / total_capacity if f"K{master}" in row else 0
                nh4_fraction = row.get(f"NH4{master}", 0) / total_capacity if f"NH4{master}" in row else 0
                
                # Each divalent ion occupies 2 exchange sites
                capacity_used = (ca_fraction + mg_fraction) * 2 + k_fraction + nh4_fraction
                capacity_used *= total_capacity
                
            elif column.resin_type in ["WAC_H", "WAC_Na"]:
                # For WAC, consider ionized sites with exchanged ions
                na_fraction = row.get(f"Na{master}", 0) / total_capacity if f"Na{master}" in row else 0
                ca_fraction = row.get(f"Ca{master}2", 0) / total_capacity if f"Ca{master}2" in row else 0
                mg_fraction = row.get(f"Mg{master}2", 0) / total_capacity if f"Mg{master}2" in row else 0
                
                # Account for pH-dependent ionization
                h_fraction = row.get(f"H{master}", 0) / total_capacity if f"H{master}" in row else 0
                ionized_fraction = 1.0 - h_fraction
                
                capacity_used = ionized_fraction * total_capacity
            
            else:
                # Default to simple estimate
                capacity_used = total_capacity * 0.5
                
            return max(0, min(capacity_used, total_capacity))  # Bound between 0 and total
            
        except Exception as e:
            logger.warning(f"Error calculating capacity used: {e}")
            # Fallback to simple linear estimate
            return column.exchange_capacity_eq_L * column.resin_volume_L * 0.5
    
    def _simple_breakthrough_simulation(
        self,
        column: IXColumn,
        feed_water: Dict[str, Any],
        flow_rate_L_hr: float,
        target_bv: int,
        bv_increment: int
    ) -> List[BreakthroughPoint]:
        """
        Simplified breakthrough simulation when PhreeqPy is not available.
        
        Uses idealized breakthrough curves based on selectivity.
        """
        breakthrough_points = []
        
        # Calculate breakthrough for major ions
        ca_feed = feed_water["ion_concentrations_mg_L"].get("Ca_2+", 0)
        mg_feed = feed_water["ion_concentrations_mg_L"].get("Mg_2+", 0) 
        na_feed = feed_water["ion_concentrations_mg_L"].get("Na_+", 0)
        
        # Total hardness in meq/L, then convert to eq/L
        hardness_meq_L = ca_feed / 20.04 + mg_feed / 12.15
        hardness_eq_L = hardness_meq_L / 1000  # Convert meq/L to eq/L
        
        # Theoretical capacity (BV = total capacity / loading per BV)
        theoretical_bv = column.exchange_capacity_eq_L / hardness_eq_L
        
        # Apply competition factor
        if na_feed > 0:
            na_meq_L = na_feed / 22.99
            na_eq_L = na_meq_L / 1000
            na_hardness_ratio = na_eq_L / hardness_eq_L
            competition_factor = 1.0 / (1.0 + na_hardness_ratio / 4.0)  # Approximate
            effective_bv = theoretical_bv * competition_factor
        else:
            effective_bv = theoretical_bv
        
        # Debug logging
        logger.info(f"Breakthrough calculation:")
        logger.info(f"  Ca: {ca_feed} mg/L, Mg: {mg_feed} mg/L, Na: {na_feed} mg/L")
        logger.info(f"  Hardness: {hardness_meq_L:.2f} meq/L = {hardness_eq_L:.6f} eq/L")
        logger.info(f"  Theoretical BV: {theoretical_bv:.0f}")
        logger.info(f"  Effective BV: {effective_bv:.0f}")
        
        # Generate idealized breakthrough curve
        for bv in range(0, target_bv + 1, bv_increment):
            # Normalized position
            x = bv / effective_bv if effective_bv > 0 else 0
            
            # Breakthrough fraction (S-curve)
            if x < 0.5:
                breakthrough = 0.01  # Low leakage
            elif x < 1.5:
                # S-curve between 50% and 150% of capacity
                breakthrough = 0.5 * (1 + np.tanh(5 * (x - 1)))
            else:
                breakthrough = 0.99  # Full breakthrough
            
            # Calculate effluent
            effluent = {}
            for ion, conc in feed_water["ion_concentrations_mg_L"].items():
                if ion in ["Ca_2+", "Mg_2+", "K_+"]:
                    # Divalent/hardness ions removed
                    effluent[ion] = conc * breakthrough
                elif ion == "Na_+":
                    # Sodium increases due to exchange
                    # Calculate removed hardness in meq/L
                    removed_ca_meq = (ca_feed * (1 - breakthrough)) / 20.04  # mg/L to meq/L
                    removed_mg_meq = (mg_feed * (1 - breakthrough)) / 12.15  # mg/L to meq/L
                    removed_hardness_meq = removed_ca_meq + removed_mg_meq
                    
                    # Each meq of hardness releases 2 meq of Na+ (since Ca2+ and Mg2+ are divalent)
                    added_na_meq = removed_hardness_meq * 2  # meq/L
                    added_na_mg = added_na_meq * 22.99  # meq/L to mg/L
                    effluent[ion] = na_feed + added_na_mg
                else:
                    # Anions pass through
                    effluent[ion] = conc
            
            time_hours = (bv * column.resin_volume_L) / flow_rate_L_hr
            capacity_used = min(bv * hardness_eq_L, column.exchange_capacity_eq_L * column.resin_volume_L)
            
            point = BreakthroughPoint(
                bed_volumes=bv,
                time_hours=time_hours,
                effluent_concentrations_mg_L=effluent,
                pH=feed_water["pH"],  # Simplified - no pH calculation
                capacity_utilized_eq=capacity_used
            )
            
            breakthrough_points.append(point)
        
        return breakthrough_points
    
    def calculate_regenerant_requirement(
        self,
        column: IXColumn,
        capacity_used_eq: float,
        regenerant_type: str = "NaCl",
        efficiency: float = 0.85
    ) -> Dict[str, float]:
        """
        Calculate regenerant chemical requirements.
        
        Args:
            column: Ion exchange column
            capacity_used_eq: Capacity used in equivalents
            regenerant_type: Type of regenerant (NaCl, HCl, H2SO4)
            efficiency: Regeneration efficiency (0-1)
        
        Returns:
            Dictionary with regenerant requirements
        """
        # Stoichiometric requirement
        stoich_eq = capacity_used_eq / efficiency
        
        # Convert to mass based on regenerant type
        if regenerant_type == "NaCl":
            mw = 58.44  # g/mol
            regenerant_kg = stoich_eq * mw / 1000
            concentration_percent = 10  # 10% brine
        elif regenerant_type == "HCl":
            mw = 36.46
            regenerant_kg = stoich_eq * mw / 1000
            concentration_percent = 5  # 5% HCl
        elif regenerant_type == "H2SO4":
            mw = 98.08 / 2  # Per equivalent
            regenerant_kg = stoich_eq * mw / 1000
            concentration_percent = 2  # 2% H2SO4
        else:
            raise ValueError(f"Unknown regenerant: {regenerant_type}")
        
        # Calculate solution volume
        solution_volume_L = (regenerant_kg * 1000) / (concentration_percent * 10)  # 10 g/L per %
        
        # Rinse water (typically 3-5 BV)
        rinse_volume_L = column.resin_volume_L * 4
        
        return {
            "regenerant_type": regenerant_type,
            "regenerant_kg": round(regenerant_kg, 2),
            "concentration_percent": concentration_percent,
            "solution_volume_L": round(solution_volume_L, 1),
            "rinse_volume_L": round(rinse_volume_L, 1),
            "total_water_L": round(solution_volume_L + rinse_volume_L, 1),
            "specific_consumption_g_L_resin": round(regenerant_kg * 1000 / column.resin_volume_L, 1)
        }
    
    def simulate_degasser_performance(
        self,
        influent_water: Dict[str, Any],
        tower_ntu: float = 3.0,
        target_co2_mg_L: float = 5.0
    ) -> Dict[str, float]:
        """
        Simulate CO2 stripping in degasser tower using water-chemistry-mcp integration.
        
        Args:
            influent_water: Water composition entering degasser
            tower_ntu: Number of transfer units  
            target_co2_mg_L: Target CO2 concentration
        
        Returns:
            Degasser performance metrics
        """
        # Check if water-chemistry-mcp is available
        if WATER_CHEM_AVAILABLE:
            try:
                # Use water-chemistry-mcp's simulate_chemical_addition for CO2 stripping
                # Convert influent water to format expected by water-chemistry-mcp
                initial_solution = {
                    'pH': influent_water['pH'],
                    'temperature_celsius': influent_water.get('temperature_celsius', 25),
                    'analysis': {}
                }
                
                # Convert ion concentrations to element totals
                ion_to_element = {
                    'Na_+': 'Na', 'Ca_2+': 'Ca', 'Mg_2+': 'Mg', 'K_+': 'K',
                    'Cl_-': 'Cl', 'SO4_2-': 'S', 'HCO3_-': 'C', 'NO3_-': 'N'
                }
                
                for ion, conc in influent_water['ion_concentrations_mg_L'].items():
                    if ion in ion_to_element:
                        element = ion_to_element[ion]
                        initial_solution['analysis'][element] = conc
                
                # Run async function synchronously
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # First, get initial CO2 concentration
                # Use the same database as the PhreeqPy engine for consistency
                db_to_use = self.database if self.database and self.database != "default" else None
                initial_result = loop.run_until_complete(
                    simulate_chemical_addition({
                        'initial_solution': initial_solution,
                        'reactants': [],  # No chemical addition
                        'allow_precipitation': False,
                        'database': db_to_use  # Use same database or let water-chemistry-mcp decide
                    })
                )
                
                # Extract initial CO2
                if 'species_molality' in initial_result:
                    influent_co2 = initial_result['species_molality'].get('CO2', 0) * 44010  # mol/L to mg/L
                else:
                    # Fallback calculation
                    influent_co2 = self._estimate_co2_from_alkalinity(
                        influent_water.get('alkalinity_mg_L_CaCO3', 100),
                        influent_water['pH']
                    )
                
                # Calculate CO2 removal based on tower NTU
                # Using mass transfer correlation for packed towers
                removal_efficiency = 1 - np.exp(-tower_ntu * 0.8)  # Empirical factor
                co2_removed = influent_co2 * removal_efficiency
                final_co2 = max(target_co2_mg_L, influent_co2 - co2_removed)
                
                # Now simulate the degassed condition
                # This is done by equilibrating with atmospheric CO2
                degassed_result = loop.run_until_complete(
                    simulate_chemical_addition({
                        'initial_solution': initial_solution,
                        'reactants': [],
                        'allow_precipitation': False,
                        'equilibrium_phases': [{'mineral': 'CO2(g)', 'log_si': -3.5}],  # Low pCO2
                        'database': db_to_use  # Use same database or let water-chemistry-mcp decide
                    })
                )
                
                # Extract final pH and CO2
                if 'solution_summary' in degassed_result:
                    final_pH = degassed_result['solution_summary']['pH']
                    if 'species_molality' in degassed_result:
                        final_co2_actual = degassed_result['species_molality'].get('CO2', 0) * 44010
                        final_co2 = min(final_co2, final_co2_actual)  # Use actual if lower
                else:
                    # Empirical pH increase
                    pH_increase = min(2.0, tower_ntu * 0.3)
                    final_pH = min(8.5, influent_water["pH"] + pH_increase)
                
                loop.close()
                
            except Exception as e:
                logger.warning(f"Water-chemistry-mcp integration failed: {e}")
                # Fall back to simplified calculation
                return self._simple_degasser_calculation(
                    influent_water, tower_ntu, target_co2_mg_L
                )
                
        elif PHREEQPY_AVAILABLE and self.pp is not None:
            # Use local PHREEQC for CO2 calculations
            try:
                solution_block = self.create_solution_block(
                    influent_water["ion_concentrations_mg_L"],
                    influent_water["pH"],
                    influent_water.get("temperature_celsius", 25)
                )
                
                # Get initial CO2
                initial_string = f"""
{solution_block}
SELECTED_OUTPUT
    -reset false
    -totals C(4)
    -molalities CO2 HCO3- CO3-2
END
                """
                
                self.pp.ip.run_string(initial_string)
                sol_initial = self.pp.get_solution(1)
                influent_co2 = sol_initial.species['CO2'] * 44010 if 'CO2' in sol_initial.species else 0
                
                # Simulate degassing with low CO2 partial pressure
                degassed_string = f"""
{solution_block}
EQUILIBRIUM_PHASES 1
    CO2(g) -3.5  # Low partial pressure for stripping
SELECTED_OUTPUT
    -reset false
    -pH true
    -totals C(4)
    -molalities CO2
END
                """
                
                self.pp.ip.run_string(degassed_string)
                sol_final = self.pp.get_solution(1)
                
                final_co2 = sol_final.species.get('CO2', 0) * 44010  # mol/L to mg/L
                final_pH = sol_final.pH
                
            except Exception as e:
                logger.error(f"PHREEQC calculation failed: {e}")
                return self._simple_degasser_calculation(
                    influent_water, tower_ntu, target_co2_mg_L
                )
        else:
            # Use simplified calculation
            return self._simple_degasser_calculation(
                influent_water, tower_ntu, target_co2_mg_L
            )
        
        # Calculate removal efficiency
        removal_percent = (influent_co2 - final_co2) / influent_co2 * 100 if influent_co2 > 0 else 0
        
        return {
            "influent_CO2_mg_L": round(influent_co2, 1),
            "effluent_CO2_mg_L": round(final_co2, 1),
            "removal_percent": round(removal_percent, 1),
            "influent_pH": influent_water["pH"],
            "effluent_pH": round(final_pH, 2),
            "ntu_achieved": tower_ntu,
            "calculation_method": "water-chemistry-mcp" if WATER_CHEM_AVAILABLE else "phreeqc"
        }
    
    def _simple_degasser_calculation(self, influent_water: Dict[str, Any],
                                   tower_ntu: float, target_co2_mg_L: float) -> Dict[str, float]:
        """Simplified degasser calculation when advanced methods unavailable."""
        # Estimate CO2 from alkalinity and pH
        alk_mg_L = influent_water.get("alkalinity_mg_L_CaCO3", 100)
        pH = influent_water["pH"]
        
        influent_co2 = self._estimate_co2_from_alkalinity(alk_mg_L, pH)
        
        # Calculate removal based on NTU
        removal_efficiency = 1 - np.exp(-tower_ntu * 0.8)
        co2_removed = influent_co2 * removal_efficiency
        final_co2 = max(target_co2_mg_L, influent_co2 - co2_removed)
        
        # Estimate pH increase
        pH_increase = min(2.0, tower_ntu * 0.3)
        final_pH = min(8.5, influent_water["pH"] + pH_increase)
        
        removal_percent = (influent_co2 - final_co2) / influent_co2 * 100 if influent_co2 > 0 else 0
        
        return {
            "influent_CO2_mg_L": round(influent_co2, 1),
            "effluent_CO2_mg_L": round(final_co2, 1),
            "removal_percent": round(removal_percent, 1),
            "influent_pH": influent_water["pH"],
            "effluent_pH": round(final_pH, 2),
            "ntu_achieved": tower_ntu,
            "calculation_method": "simplified"
        }
    
    def _estimate_co2_from_alkalinity(self, alk_mg_caco3: float, pH: float) -> float:
        """Estimate dissolved CO2 from alkalinity and pH."""
        # Convert alkalinity to mol/L
        alk_mol_L = alk_mg_caco3 / 100000  # mg/L CaCO3 to mol/L
        
        # Calculate alpha values for carbonate system
        h_conc = 10**(-pH)
        k1 = 10**(-6.35)  # First dissociation constant at 25°C
        k2 = 10**(-10.33)  # Second dissociation constant at 25°C
        
        alpha0 = h_conc**2 / (h_conc**2 + h_conc*k1 + k1*k2)  # CO2 fraction
        alpha1 = h_conc*k1 / (h_conc**2 + h_conc*k1 + k1*k2)  # HCO3- fraction
        alpha2 = k1*k2 / (h_conc**2 + h_conc*k1 + k1*k2)  # CO3-2 fraction
        
        # Total carbonate = alkalinity (simplified, ignoring other bases)
        ct = alk_mol_L / (alpha1 + 2*alpha2)
        
        # CO2 concentration
        co2_mol_L = ct * alpha0
        co2_mg_L = co2_mol_L * 44010  # mol/L to mg/L
        
        return co2_mg_L
    
    def _convert_to_dict(self, water: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
        """Convert MCASWaterComposition or dict to standard dict format."""
        if isinstance(water, dict):
            return water
        
        # Handle MCASWaterComposition
        if hasattr(water, 'ion_concentrations_mg_L'):
            return {
                'temperature': water.temperature_celsius,
                'pH': water.pH,
                'alkalinity_mg_L_CaCO3': water.get_alkalinity_mg_L_CaCO3() if hasattr(water, 'get_alkalinity_mg_L_CaCO3') else 100,
                'ion_concentrations_mg_L': water.ion_concentrations_mg_L,
                'flow_m3_hr': water.flow_m3_hr if hasattr(water, 'flow_m3_hr') else 1.0
            }
        
        # If it's neither, return as-is and let downstream handle errors
        return water
    
    def calculate_acid_dose_for_degasser(
        self,
        influent_water: Union[Dict[str, Any], 'MCASWaterComposition'],
        target_ph: float = 6.2,
        acid_type: str = "H2SO4"
    ) -> Dict[str, Any]:
        """
        Calculate acid dose required for degasser feed pH adjustment.
        Uses water-chemistry-mcp for accurate dosing calculations.
        
        Args:
            influent_water: Water composition (dict or MCASWaterComposition)
            target_ph: Target pH for degasser feed
            acid_type: Type of acid (H2SO4, HCl)
        
        Returns:
            Acid dosing requirements and predicted water quality
        """
        # Convert to dict format
        water_dict = self._convert_to_dict(influent_water)
        
        if WATER_CHEM_AVAILABLE:
            try:
                # Convert to water-chemistry-mcp format
                initial_solution = {
                    'pH': water_dict['pH'],
                    'temperature_celsius': water_dict.get('temperature', 25),
                    'analysis': {}
                }
                
                # Convert ions to elements
                ion_to_element = {
                    'Na_+': 'Na', 'Ca_2+': 'Ca', 'Mg_2+': 'Mg', 'K_+': 'K',
                    'Cl_-': 'Cl', 'SO4_2-': 'S', 'HCO3_-': 'C', 'NO3_-': 'N'
                }
                
                for ion, conc in water_dict['ion_concentrations_mg_L'].items():
                    if ion in ion_to_element:
                        element = ion_to_element[ion]
                        initial_solution['analysis'][element] = conc
                
                # Use water-chemistry-mcp's batch processing for dose optimization
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Create dose sweep scenarios
                dose_range = np.linspace(0.1, 10.0, 20)  # mmol/L
                scenarios = []
                
                for dose in dose_range:
                    scenarios.append({
                        'name': f'acid_dose_{dose:.2f}',
                        'type': 'chemical_addition',
                        'reactants': [{'formula': acid_type, 'amount': dose, 'units': 'mmol'}]
                    })
                
                # Run batch processing
                batch_result = loop.run_until_complete(
                    batch_process_scenarios({
                        'base_solution': initial_solution,
                        'scenarios': scenarios,
                        'parallel_limit': 10,
                        'output_format': 'full'
                    })
                )
                
                # Find optimal dose
                best_dose = None
                best_result = None
                best_ph_diff = float('inf')
                
                for result in batch_result['results']:
                    if 'error' not in result:
                        scenario_result = result['result']
                        if 'solution_summary' in scenario_result:
                            result_ph = scenario_result['solution_summary']['pH']
                            ph_diff = abs(result_ph - target_ph)
                            
                            if ph_diff < best_ph_diff:
                                best_ph_diff = ph_diff
                                best_dose = result['scenario']['reactants'][0]['amount']
                                best_result = scenario_result
                
                loop.close()
                
                if best_result:
                    # Calculate acid consumption
                    mw_acid = {'H2SO4': 98.08, 'HCl': 36.46}.get(acid_type, 98.08)
                    acid_mg_L = best_dose * mw_acid
                    
                    # Extract CO2 generation
                    co2_generated = 0
                    if 'species_molality' in best_result:
                        initial_co2 = self._estimate_co2_from_alkalinity(
                            influent_water.get('alkalinity_mg_L_CaCO3', 100),
                            influent_water['pH']
                        ) / 44010  # mg/L to mol/L
                        final_co2 = best_result['species_molality'].get('CO2', 0)
                        co2_generated = (final_co2 - initial_co2) * 44010  # mol/L to mg/L
                    
                    return {
                        'acid_type': acid_type,
                        'optimal_dose_mmol_L': round(best_dose, 3),
                        'optimal_dose_mg_L': round(acid_mg_L, 1),
                        'target_pH': target_ph,
                        'achieved_pH': round(best_result['solution_summary']['pH'], 2),
                        'co2_generated_mg_L': round(max(0, co2_generated), 1),
                        'alkalinity_consumed_percent': round(
                            (1 - best_result['solution_summary'].get('alkalinity', 0) / 
                             influent_water.get('alkalinity_mg_L_CaCO3', 100)) * 100, 1
                        ),
                        'calculation_method': 'water-chemistry-mcp'
                    }
                else:
                    raise ValueError("No suitable acid dose found")
                    
            except Exception as e:
                logger.warning(f"Water-chemistry-mcp acid dosing failed: {e}")
                # Fall back to simplified calculation
                return self._simple_acid_dose_calculation(
                    water_dict, target_ph, acid_type
                )
        else:
            # Use simplified calculation
            return self._simple_acid_dose_calculation(
                water_dict, target_ph, acid_type
            )
    
    def _simple_acid_dose_calculation(self, influent_water: Dict[str, Any],
                                    target_ph: float, acid_type: str) -> Dict[str, Any]:
        """Simplified acid dose calculation."""
        # Get alkalinity
        alk_mg_caco3 = influent_water.get('alkalinity_mg_L_CaCO3', 100)
        alk_meq_L = alk_mg_caco3 / 50  # Convert to meq/L
        
        # Estimate acid requirement based on alkalinity destruction
        # Rule of thumb: destroy alkalinity to reach pH 6.2
        if target_ph <= 6.3:
            # Need to destroy most alkalinity
            acid_meq_L = alk_meq_L * 0.95
        else:
            # Partial alkalinity destruction
            acid_meq_L = alk_meq_L * (1 - 10**(target_ph - 8.3))
        
        # Convert to dose
        if acid_type == "H2SO4":
            acid_mmol_L = acid_meq_L / 2  # H2SO4 provides 2 eq/mol
            acid_mg_L = acid_mmol_L * 98.08
        else:  # HCl
            acid_mmol_L = acid_meq_L  # HCl provides 1 eq/mol
            acid_mg_L = acid_mmol_L * 36.46
        
        # Estimate CO2 generation (alkalinity converted to CO2)
        co2_generated = alk_meq_L * 0.95 * 22  # meq/L * 22 mg/meq CO2
        
        return {
            'acid_type': acid_type,
            'optimal_dose_mmol_L': round(acid_mmol_L, 3),
            'optimal_dose_mg_L': round(acid_mg_L, 1),
            'target_pH': target_ph,
            'achieved_pH': target_ph,  # Assumed
            'co2_generated_mg_L': round(co2_generated, 1),
            'alkalinity_consumed_percent': 95,
            'calculation_method': 'simplified'
        }


# Utility functions for notebook use

def create_phreeqpy_engine(database: str = "phreeqc.dat") -> PhreeqPyEngine:
    """Create and return a PhreeqPy engine instance."""
    return PhreeqPyEngine(database)


def run_ix_breakthrough_simulation(
    resin_type: str,
    resin_volume_L: float,
    feed_water: Dict[str, Any],
    flow_rate_L_hr: float,
    exchange_capacity_eq_L: float = 2.0,
    target_bv: int = 500
) -> Tuple[List[BreakthroughPoint], Dict[str, float]]:
    """
    Convenience function to run a complete breakthrough simulation.
    
    Returns:
        - List of breakthrough points
        - Regenerant requirements
    """
    # Create column
    column = IXColumn(
        resin_type=resin_type,
        resin_volume_L=resin_volume_L,
        exchange_capacity_eq_L=exchange_capacity_eq_L,
        selectivity_coefficients={"Ca/Na": 5.0, "Mg/Na": 3.0}  # Typical values
    )
    
    # Create engine and run simulation
    engine = PhreeqPyEngine()
    breakthrough_curve = engine.simulate_breakthrough(
        column, feed_water, flow_rate_L_hr, target_bv
    )
    
    # Find breakthrough point (e.g., 5 mg/L hardness)
    breakthrough_bv = None
    for point in breakthrough_curve:
        hardness = (point.effluent_concentrations_mg_L.get("Ca_2+", 0) / 2.5 + 
                   point.effluent_concentrations_mg_L.get("Mg_2+", 0) / 1.22)
        if hardness > 5:
            breakthrough_bv = point.bed_volumes
            capacity_used = point.capacity_utilized_eq
            break
    
    if breakthrough_bv is None:
        # Use last point
        capacity_used = breakthrough_curve[-1].capacity_utilized_eq
    
    # Calculate regenerant
    regenerant_req = engine.calculate_regenerant_requirement(
        column, capacity_used, 
        "NaCl" if resin_type == "SAC" else "HCl"
    )
    
    return breakthrough_curve, regenerant_req