"""
Enhanced PHREEQC Input Generator with Selectivity Database Integration

This module generates optimized PHREEQC input using the comprehensive
selectivity database for accurate multicomponent ion exchange simulation.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging

# Ensure parent directory is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.core_config import CONFIG
# WAC uses dual-domain EXCHANGE model - see watertap_ix_transport/transport_core/wac_templates.py
# SURFACE model was deprecated (Codex 019abbed) due to numerical instability at industrial scale

logger = logging.getLogger(__name__)


class EnhancedPHREEQCGenerator:
    """Generate PHREEQC input with database-driven selectivity coefficients."""

    def __init__(self):
        """Initialize generator and load selectivity database."""
        self.db_path = Path(__file__).parent.parent / "databases" / "resin_selectivity.json"
        self.selectivity_db = self._load_database()

    def _load_database(self) -> Dict[str, Any]:
        """Load the selectivity database."""
        if not self.db_path.exists():
            logger.warning(f"Selectivity database not found at {self.db_path}")
            return {}

        with open(self.db_path, 'r') as f:
            return json.load(f)

    def get_resin_key(self, resin_type: str, dvb_percent: Optional[int] = None) -> str:
        """
        Map resin type to database key.

        Args:
            resin_type: Basic resin type (SAC, WAC_Na, WAC_H)
            dvb_percent: DVB crosslinking % for SAC resins

        Returns:
            Database key for resin type
        """
        if resin_type == "SAC":
            # Default to 8% DVB if not specified (standard commercial)
            dvb = dvb_percent or 8
            # Find closest DVB% in database
            available_dvb = [2, 4, 8, 12, 16]
            closest_dvb = min(available_dvb, key=lambda x: abs(x - dvb))
            return f"SAC_{closest_dvb}DVB"
        else:
            return resin_type  # WAC_Na or WAC_H

    def generate_exchange_species(
        self,
        resin_type: str,
        temperature_c: float = 25.0,
        dvb_percent: Optional[int] = None,
        ions_present: Optional[List[str]] = None,
        use_wac_enhanced: bool = True
    ) -> str:
        """
        Generate EXCHANGE_SPECIES block using selectivity database.

        Args:
            resin_type: Type of resin (SAC, WAC_Na, WAC_H)
            temperature_c: Operating temperature in Celsius
            dvb_percent: DVB crosslinking % for SAC resins
            ions_present: List of ions to include (auto-detect if None)
            use_wac_enhanced: Use enhanced WAC model with pH dependence

        Returns:
            Complete EXCHANGE_SPECIES block as string
        """
        # For WAC resins, use dual-domain EXCHANGE model from wac_templates
        if resin_type.startswith("WAC") and use_wac_enhanced:
            # WAC uses specialized templates - see wac_templates.py
            raise NotImplementedError(
                "WAC resins use dual-domain EXCHANGE templates. "
                "Use watertap_ix_transport.transport_core.wac_templates instead."
            )

        # Get resin data from database
        resin_key = self.get_resin_key(resin_type, dvb_percent)

        if "resin_types" not in self.selectivity_db:
            logger.warning("Selectivity database missing resin_types")
            return self._fallback_exchange_species(resin_type)

        if resin_key not in self.selectivity_db["resin_types"]:
            logger.warning(f"Resin {resin_key} not in database, using fallback")
            return self._fallback_exchange_species(resin_type)

        resin_data = self.selectivity_db["resin_types"][resin_key]
        species_data = resin_data.get("exchange_species", {})

        # Build EXCHANGE_MASTER_SPECIES and EXCHANGE_SPECIES blocks
        lines = []
        lines.append(f"# Exchange species for {resin_data.get('description', resin_key)}")
        lines.append(f"# Temperature: {temperature_c:.1f}°C")
        if dvb_percent and resin_type == "SAC":
            lines.append(f"# DVB crosslinking: {dvb_percent}%")

        # Add EXCHANGE_MASTER_SPECIES first (required for custom exchange definitions)
        lines.append("EXCHANGE_MASTER_SPECIES")
        lines.append("    X X-")
        lines.append("")
        lines.append("EXCHANGE_SPECIES")

        # Add identity reaction for master species
        lines.append("    # Master species identity")
        lines.append("    X- = X-")
        lines.append("        log_k 0.0")
        lines.append("")

        # Temperature correction factor (van't Hoff)
        # Approximate: d(log_k)/dT ≈ -0.01 to -0.02 per °C
        temp_correction = -0.015 * (temperature_c - 25.0)

        # Process each species from database
        for species_name, species_info in species_data.items():
            # Parse species formula to get reaction
            reaction = self._format_reaction(species_name, species_info, resin_type)
            if not reaction:
                continue

            # Skip if ion not in feed (if specified)
            if ions_present:
                ion_in_reaction = any(ion in reaction for ion in ions_present)
                if not ion_in_reaction:
                    continue

            # Get log_k value with temperature correction
            log_k = species_info.get("log_k", 0.0) + temp_correction

            # Add reaction
            lines.append(f"    # {species_name}")
            if species_info.get("notes"):
                lines.append(f"    # Note: {species_info['notes']}")
            lines.append(f"    {reaction}")
            lines.append(f"        log_k {log_k:.3f}")

            # Add activity coefficients if available
            if "gamma" in species_info:
                gamma = species_info["gamma"]
                lines.append(f"        -gamma {gamma[0]} {gamma[1]}")

            # Add temperature dependence
            if temperature_c != 25.0:
                # Analytical expression for temperature dependence
                # Format: A1 A2 A3 A4 A5 (van't Hoff parameters)
                lines.append("        -analytical_expression -2.0 0 0 0 0")

            lines.append("")

        return "\n".join(lines)

    def _format_reaction(
        self,
        species_name: str,
        species_info: Dict[str, Any],
        resin_type: str
    ) -> Optional[str]:
        """
        Format the exchange reaction from species name and info.

        Args:
            species_name: Name like "Ca_X2" or "Na_HX"
            species_info: Dictionary with reaction info
            resin_type: Type of resin

        Returns:
            Formatted reaction string or None
        """
        # Check for explicit reaction in database
        if "reaction" in species_info:
            return species_info["reaction"]

        # Parse standard species names
        if species_name == "H_X":
            if resin_type == "WAC_Na":
                return "H+ + X- = HX"
            else:
                return None  # Skip for other resins

        # Handle common cations
        ion_map = {
            "Na_X": "Na+ + X- = NaX",
            "K_X": "K+ + X- = KX",
            "Li_X": "Li+ + X- = LiX",
            "NH4_X": "NH4+ + X- = NH4X",
            "H_X": "H+ + X- = HX",
            "Cs_X": "Cs+ + X- = CsX",
            "Rb_X": "Rb+ + X- = RbX",
            "Ag_X": "Ag+ + X- = AgX",
            "Ca_X2": "Ca+2 + 2X- = CaX2",
            "Mg_X2": "Mg+2 + 2X- = MgX2",
            "Sr_X2": "Sr+2 + 2X- = SrX2",
            "Ba_X2": "Ba+2 + 2X- = BaX2",
            "Fe_X2": "Fe+2 + 2X- = FeX2",
            "Mn_X2": "Mn+2 + 2X- = MnX2",
            "Zn_X2": "Zn+2 + 2X- = ZnX2",
            "Cu_X2": "Cu+2 + 2X- = CuX2",
            "Ni_X2": "Ni+2 + 2X- = NiX2",
            "Co_X2": "Co+2 + 2X- = CoX2",
            "Pb_X2": "Pb+2 + 2X- = PbX2",
            "Cd_X2": "Cd+2 + 2X- = CdX2",
        }

        return ion_map.get(species_name)

    def _fallback_exchange_species(self, resin_type: str) -> str:
        """
        Generate fallback EXCHANGE_SPECIES if database unavailable.

        Uses CONFIG values as fallback.
        """
        lines = []
        lines.append("# Fallback exchange species (database unavailable)")
        lines.append("EXCHANGE_SPECIES")
        lines.append("    X- = X-")
        lines.append("        log_k 0.0")
        lines.append("")

        if resin_type == "SAC":
            lines.append("    Na+ + X- = NaX")
            lines.append("        log_k 0.0")
            lines.append("        -gamma 4.0 0.075")
            lines.append("")
            lines.append("    Ca+2 + 2X- = CaX2")
            lines.append(f"        log_k {CONFIG.SAC_LOGK_CA_NA:.3f}")
            lines.append("        -gamma 5.0 0.165")
            lines.append("")
            lines.append("    Mg+2 + 2X- = MgX2")
            lines.append(f"        log_k {CONFIG.SAC_LOGK_MG_NA:.3f}")
            lines.append("        -gamma 5.5 0.2")

        elif resin_type == "WAC_Na":
            lines.append("    H+ + X- = HX")
            lines.append(f"        log_k {CONFIG.WAC_PKA:.3f}")
            lines.append("")
            lines.append("    Na+ + X- = NaX")
            lines.append("        log_k 0.0")
            lines.append("")
            lines.append("    Ca+2 + 2X- = CaX2")
            lines.append(f"        log_k {CONFIG.WAC_LOGK_CA_NA:.3f}")
            lines.append("")
            lines.append("    Mg+2 + 2X- = MgX2")
            lines.append(f"        log_k {CONFIG.WAC_LOGK_MG_NA:.3f}")

        return "\n".join(lines)

    def generate_transport_block(
        self,
        column_length_m: float,
        flow_velocity_m_hr: float,
        dispersivity_m: Optional[float] = None,
        porosity: float = 0.4,
        timesteps: int = 100,
        total_time_hours: float = 24
    ) -> str:
        """
        Generate TRANSPORT block for column breakthrough simulation.

        Args:
            column_length_m: Bed depth in meters
            flow_velocity_m_hr: Linear velocity in m/hr
            dispersivity_m: Longitudinal dispersivity (auto-calculate if None)
            porosity: Bed porosity (typically 0.35-0.45)
            timesteps: Number of time steps
            total_time_hours: Total simulation time

        Returns:
            TRANSPORT block as string
        """
        # Auto-calculate dispersivity if not provided
        if dispersivity_m is None:
            # Use correlation: α = 0.001 * L for well-packed beds
            # Or Peclet number approach: Pe = v*L/D = 50-100 for IX
            peclet = 75  # Typical for ion exchange
            dispersivity_m = column_length_m / peclet
            logger.info(f"Auto-calculated dispersivity: {dispersivity_m:.6f} m (Pe={peclet})")

        # Calculate time step
        time_step_sec = (total_time_hours * 3600) / timesteps

        # Calculate number of cells (typically 10-20 for IX)
        n_cells = min(20, max(10, int(column_length_m * 100)))  # 1 cell per cm, max 20

        lines = []
        lines.append("# Transport parameters for column breakthrough")
        lines.append("TRANSPORT")
        lines.append(f"    -cells {n_cells}")
        lines.append(f"    -shifts {timesteps}")
        lines.append(f"    -time_step {time_step_sec:.1f} seconds")
        lines.append(f"    -flow_direction forward")
        lines.append(f"    -boundary_conditions flux flux")
        lines.append(f"    -lengths {n_cells}*{column_length_m/n_cells:.4f}")
        lines.append(f"    -dispersivities {n_cells}*{dispersivity_m:.6f}")
        lines.append(f"    -correct_disp true")
        lines.append(f"    -diffusion_coefficient 1e-9  # m2/s typical for ions")
        lines.append(f"    -thermal_diffusion 1  # Include temperature effects")
        lines.append("    -punch_cells 1-20")
        lines.append("    -punch_frequency 5")
        lines.append("    -print_cells 1-20")
        lines.append("    -print_frequency 10")

        return "\n".join(lines)


def validate_enhanced_generator():
    """Test the enhanced PHREEQC generator."""
    gen = EnhancedPHREEQCGenerator()

    print("\n" + "="*60)
    print("ENHANCED PHREEQC GENERATOR VALIDATION")
    print("="*60)

    # Test 1: Generate SAC exchange species with different DVB%
    print("\n--- SAC with 8% DVB (standard) ---")
    sac_8dvb = gen.generate_exchange_species("SAC", dvb_percent=8)
    print(sac_8dvb[:500])

    print("\n--- SAC with 16% DVB (high selectivity) ---")
    sac_16dvb = gen.generate_exchange_species("SAC", dvb_percent=16)
    # Check that Ca selectivity is higher in 16% DVB
    if "log_k 0.86" in sac_16dvb and "log_k 0.71" in sac_8dvb:
        print("PASS: Ca selectivity increases with DVB%")
    else:
        print("FAIL: Selectivity trend incorrect")

    # Test 2: Generate WAC exchange species with pH dependence
    print("\n--- WAC Na-form with enhanced pH model ---")
    wac_na = gen.generate_exchange_species("WAC_Na", use_wac_enhanced=True)
    if "H+ + X- = HX" in wac_na and "log_k 4.8" in wac_na:
        print("PASS: WAC pH-dependent capacity included")
    else:
        print("FAIL: WAC pH model missing")

    # Test 3: Generate TRANSPORT block
    print("\n--- TRANSPORT block for breakthrough ---")
    transport = gen.generate_transport_block(
        column_length_m=2.0,
        flow_velocity_m_hr=5.0
    )
    print(transport[:300])

    print("\n" + "="*60)
    print("VALIDATION COMPLETE")
    print("="*60)



if __name__ == "__main__":
    validate_enhanced_generator()