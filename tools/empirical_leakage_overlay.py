"""
Empirical Leakage Overlay for Ion Exchange Simulation

This module implements the two-layer architecture for IX simulation:
    Layer 1: PHREEQC for thermodynamic equilibrium and breakthrough timing
    Layer 2: Empirical overlay for realistic leakage prediction

Based on industry practice (DuPont WAVE, Purolite PRSM, Veolia projections)
where leakage is primarily driven by:
    - Incomplete regeneration (eta_regen < 1.0)
    - TDS/ionic strength effects
    - Channeling and maldistribution
    - Mass transfer limitations (kinetic effects)

Key Insight from IX Industry:
    Thermodynamic equilibrium models predict near-zero leakage (correct for equilibrium),
    but real systems show 1-10 mg/L leakage due to non-equilibrium effects.
    Vendors use empirical curves calibrated from pilot data, not pure thermodynamics.

References:
    - Helfferich, F. (1962). Ion Exchange. McGraw-Hill.
    - DuPont WAVE software documentation
    - Purolite PRSM software documentation
    - WaterTAP IonExchange0D model (Langmuir/Freundlich isotherms)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CalibrationParameters:
    """
    Tunable parameters for empirical leakage overlay.

    These parameters are site/resin-specific and should be calibrated
    from operational data or vendor pilot testing.

    Attributes:
        capacity_factor: Effective capacity vs. fresh resin (0.7-1.0)
        regen_eff_eta: Regeneration efficiency (0.85-0.98 typical)
        leak_floor_a0: Minimum equilibrium leakage mg/L as CaCO3
        leak_tds_slope_a1: TDS effect on leakage (mg/L per 1000 mg/L TDS)
        leak_regen_coeff_a2: Regeneration inefficiency effect
        leak_regen_exponent_b: Exponent for regeneration term
        k_ldf_25c: Linear driving force mass transfer coefficient (1/hr) at 25C
        channeling_factor: Accounts for flow maldistribution (1.0-1.3)
        aging_rate_per_cycle: Capacity loss per service cycle (0.0005-0.002)
        pka_shift: pH shift for WAC effective pKa vs. literature value

    Designer Lever Attributes:
        regenerant_dose_g_per_l: NaCl dose (g/L resin) - primary regen_eff driver
        regen_flow_direction: "counter" or "co" - counter-current adds +5% efficiency
        slow_rinse_volume_bv: Displacement rinse in bed volumes
        fast_rinse_volume_bv: Fast rinse in bed volumes
        service_flow_bv_hr: Operating service flow rate (BV/hr)
        bed_depth_m: Actual resin bed depth (m)
        resin_crosslinking_dvb: DVB crosslinking percentage (affects selectivity)
        resin_form: "gel" or "macroporous" (affects kinetics)

    WAC H+ Specific:
        base_na_leakage_percent: Base Na+ leakage for fresh H-form (% of influent)
        base_k_leakage_percent: Base K+ leakage for fresh H-form (% of influent)
        leakage_exhaustion_factor: Multiplier for Na/K leakage at exhaustion

    WAC H+ Henderson-Hasselbalch Parameters:
        wac_h_pka: pKa of carboxylic acid sites (default 4.8)
        wac_h_theoretical_capacity_eq_l: Theoretical capacity in eq/L resin (default 4.7)
        wac_h_kinetic_trap_factor: Factor for kinetically trapped protonation (0.0-1.0)
            0.0 = pure equilibrium (no capacity at pH > pKa)
            1.0 = fully kinetically trapped (100% capacity retained)

            Guidance for setting kinetic_trap_factor:
            - 0.85-0.95: Fresh resin, well-regenerated (counter-current HCl/H2SO4)
            - 0.70-0.85: Typical operation, good regeneration
            - 0.50-0.70: Older resin, partial regeneration, some fouling
            - <0.50: Degraded resin, poor regeneration, significant fouling

            Calibration approach:
            - If measured leakage is higher than predicted: decrease factor
            - If measured leakage is lower than predicted: increase factor
            - Default 0.85 assumes fresh resin with counter-current acid regeneration

        wac_h_ph_floor: Minimum pH during acid production phase (4.0-4.5 typical)
    """
    # Capacity and regeneration
    capacity_factor: float = 0.95
    regen_eff_eta: float = 0.92

    # Leakage model: C_leak = max(C_eq, a0 + a1*TDS/1000 + a2*(1-eta)^b)
    leak_floor_a0: float = 0.5  # mg/L as CaCO3
    leak_tds_slope_a1: float = 0.8  # mg/L per 1000 mg/L TDS
    leak_regen_coeff_a2: float = 25.0  # mg/L
    leak_regen_exponent_b: float = 1.5

    # Kinetics
    k_ldf_25c: float = 50.0  # 1/hr, typical for gel-type SAC
    ea_activation_kj_mol: float = 20.0  # Activation energy for T-correction

    # Maldistribution
    channeling_factor: float = 1.0

    # Aging
    aging_rate_per_cycle: float = 0.001
    cycles_operated: int = 0

    # WAC-specific
    pka_shift: float = 0.0

    # === DESIGNER LEVERS: REGENERATION ===
    regenerant_dose_g_per_l: float = 100.0  # g NaCl per L resin (80-160 typical SAC)
    regen_flow_direction: str = "counter"   # "counter" or "co" (counter-current preferred)
    slow_rinse_volume_bv: float = 1.0       # Displacement rinse (BV)
    fast_rinse_volume_bv: float = 3.0       # Fast rinse (BV)

    # === DESIGNER LEVERS: SERVICE ===
    service_flow_bv_hr: float = 12.0        # Operating flow rate (BV/hr)
    bed_depth_m: float = 1.5                # Actual bed depth (m)

    # === DESIGNER LEVERS: RESIN SELECTION ===
    resin_crosslinking_dvb: float = 8.0     # % DVB crosslinking (2, 4, 8, 12, 16)
    resin_form: str = "gel"                 # "gel" or "macroporous"

    # === WAC H+ SPECIFIC: Na/K LEAKAGE ===
    base_na_leakage_percent: float = 2.0    # Base Na+ leakage (% of influent)
    base_k_leakage_percent: float = 1.5     # Base K+ leakage (% of influent)
    leakage_exhaustion_factor: float = 3.0  # Multiplier at full exhaustion

    # === WAC H+ SPECIFIC: HENDERSON-HASSELBALCH CAPACITY ===
    wac_h_pka: float = 4.8                          # pKa of carboxylic acid sites
    wac_h_theoretical_capacity_eq_l: float = 4.7   # Theoretical capacity (eq/L resin)
    wac_h_kinetic_trap_factor: float = 0.85        # Kinetically trapped protonation factor
    wac_h_ph_floor: float = 4.2                    # Minimum pH during acid phase


@dataclass
class EmpiricalOverlayResult:
    """
    Result from empirical leakage overlay calculation.

    Contains the adjusted leakage values and diagnostic information.
    """
    # Adjusted leakage (replaces PHREEQC zero leakage)
    hardness_leakage_mg_l_caco3: float
    ca_leakage_mg_l: float
    mg_leakage_mg_l: float

    # Component breakdown
    equilibrium_leakage_mg_l: float  # From PHREEQC (typically ~0)
    empirical_leakage_mg_l: float  # From this model
    tds_contribution_mg_l: float
    regen_contribution_mg_l: float
    kinetic_factor: float

    # Adjusted capacity and breakthrough
    effective_capacity_factor: float
    adjusted_breakthrough_bv: float

    # Diagnostics
    model_notes: List[str] = field(default_factory=list)


class EmpiricalLeakageOverlay:
    """
    Applies empirical corrections to PHREEQC thermodynamic results.

    The overlay modifies PHREEQC output to account for:
    1. Non-zero leakage from incomplete regeneration
    2. TDS effects on selectivity
    3. Kinetic limitations
    4. Channeling and maldistribution
    5. Resin aging

    Usage:
        overlay = EmpiricalLeakageOverlay(params)
        result = overlay.apply_overlay(
            phreeqc_result=phreeqc_data,
            feed_composition=water_analysis,
            vessel_config=vessel
        )
    """

    def __init__(self, params: Optional[CalibrationParameters] = None):
        """
        Initialize overlay with calibration parameters.

        Args:
            params: Calibration parameters. If None, uses defaults.
        """
        self.params = params or CalibrationParameters()
        self._load_selectivity_data()

    def _load_selectivity_data(self):
        """Load selectivity coefficients from JSON database."""
        try:
            db_path = Path(__file__).parent.parent / "databases" / "resin_selectivity.json"
            with open(db_path) as f:
                self.selectivity_db = json.load(f)
            logger.debug("Loaded selectivity database")
        except Exception as e:
            logger.warning(f"Could not load selectivity database: {e}")
            self.selectivity_db = {}

    def calculate_empirical_leakage(
        self,
        feed_hardness_mg_l_caco3: float,
        feed_tds_mg_l: float,
        temperature_c: float = 25.0,
        phreeqc_leakage_mg_l: float = 0.0,
        resin_type: str = "SAC"
    ) -> EmpiricalOverlayResult:
        """
        Calculate empirical leakage using industry-standard correlations.

        The leakage formula follows the pattern used by IX vendors:
            C_leak = max(C_eq, a0 + a1*TDS/1000 + a2*(1-eta)^b)

        Where:
            C_eq = PHREEQC equilibrium leakage (typically ~0)
            a0 = Minimum leakage floor (even with perfect regen)
            a1 = TDS sensitivity coefficient
            a2 = Regeneration inefficiency coefficient
            eta = Regeneration efficiency (0.85-0.98)
            b = Exponent (typically 1.5)

        Args:
            feed_hardness_mg_l_caco3: Feed hardness as CaCO3 (mg/L)
            feed_tds_mg_l: Feed TDS (mg/L)
            temperature_c: Temperature (C)
            phreeqc_leakage_mg_l: PHREEQC-calculated equilibrium leakage
            resin_type: Resin type ('SAC', 'WAC_Na', 'WAC_H')

        Returns:
            EmpiricalOverlayResult with calculated leakage and diagnostics
        """
        p = self.params
        notes = []

        # Base leakage floor (always present, even with perfect regeneration)
        leak_floor = p.leak_floor_a0
        notes.append(f"Base leakage floor: {leak_floor:.2f} mg/L")

        # TDS contribution (higher TDS = reduced selectivity)
        tds_contribution = p.leak_tds_slope_a1 * (feed_tds_mg_l / 1000.0)
        notes.append(f"TDS contribution ({feed_tds_mg_l:.0f} mg/L): {tds_contribution:.2f} mg/L")

        # Regeneration inefficiency contribution
        # (1 - eta)^b gives non-linear increase with poor regeneration
        regen_inefficiency = 1.0 - p.regen_eff_eta
        regen_contribution = p.leak_regen_coeff_a2 * (regen_inefficiency ** p.leak_regen_exponent_b)
        notes.append(f"Regen inefficiency ({p.regen_eff_eta*100:.0f}% eff): {regen_contribution:.2f} mg/L")

        # Total empirical leakage
        empirical_leakage = leak_floor + tds_contribution + regen_contribution

        # Apply channeling factor (increases leakage if flow maldistribution)
        if p.channeling_factor > 1.0:
            empirical_leakage *= p.channeling_factor
            notes.append(f"Channeling factor {p.channeling_factor:.2f}x applied")

        # Apply kinetic factor (temperature-dependent mass transfer)
        kinetic_factor = self._calculate_kinetic_factor(temperature_c)
        # Kinetic limitations increase leakage (factor > 1 if mass transfer limited)
        empirical_leakage *= kinetic_factor
        notes.append(f"Kinetic factor: {kinetic_factor:.3f}")

        # Final leakage is max of PHREEQC equilibrium and empirical model
        final_leakage = max(phreeqc_leakage_mg_l, empirical_leakage)
        notes.append(f"Final leakage: max({phreeqc_leakage_mg_l:.3f}, {empirical_leakage:.2f}) = {final_leakage:.2f} mg/L")

        # Cap leakage at feed hardness (can't leak more than feed)
        if final_leakage > feed_hardness_mg_l_caco3:
            final_leakage = feed_hardness_mg_l_caco3
            notes.append(f"Capped at feed hardness: {feed_hardness_mg_l_caco3:.2f} mg/L")

        # Distribute leakage between Ca and Mg (typical ratio for most waters)
        # Use 60% Ca, 40% Mg as default (can be adjusted based on feed ratio)
        ca_fraction = 0.6
        mg_fraction = 0.4

        # Convert CaCO3 to ion concentrations
        # Ca: divide by 2.5 (factor from CaCO3 to Ca)
        # Mg: divide by 4.1 (factor from CaCO3 to Mg)
        ca_leakage = final_leakage * ca_fraction / 2.5
        mg_leakage = final_leakage * mg_fraction / 4.1

        # Calculate effective capacity factor (with aging)
        effective_capacity = self._calculate_effective_capacity()
        notes.append(f"Effective capacity factor: {effective_capacity:.3f}")

        # Calculate adjusted breakthrough BV
        # Reduced capacity = earlier breakthrough
        adjusted_bv_factor = effective_capacity * p.regen_eff_eta
        notes.append(f"Adjusted BV factor: {adjusted_bv_factor:.3f}")

        return EmpiricalOverlayResult(
            hardness_leakage_mg_l_caco3=final_leakage,
            ca_leakage_mg_l=ca_leakage,
            mg_leakage_mg_l=mg_leakage,
            equilibrium_leakage_mg_l=phreeqc_leakage_mg_l,
            empirical_leakage_mg_l=empirical_leakage,
            tds_contribution_mg_l=tds_contribution,
            regen_contribution_mg_l=regen_contribution,
            kinetic_factor=kinetic_factor,
            effective_capacity_factor=effective_capacity,
            adjusted_breakthrough_bv=adjusted_bv_factor,  # Multiplier for PHREEQC BV
            model_notes=notes
        )

    def _calculate_kinetic_factor(self, temperature_c: float) -> float:
        """
        Calculate kinetic factor based on temperature.

        Uses Arrhenius-type temperature correction for mass transfer:
            k(T) = k(25) * exp(-Ea/R * (1/T - 1/298))

        Returns factor to apply to leakage (>1 means higher leakage).
        """
        p = self.params

        # Reference temperature
        T_ref = 298.15  # K (25C)
        T = temperature_c + 273.15  # K

        # Arrhenius correction
        R = 8.314  # J/(mol*K)
        Ea = p.ea_activation_kj_mol * 1000  # Convert to J/mol

        # Mass transfer coefficient at temperature
        k_ratio = np.exp(-Ea / R * (1/T - 1/T_ref))

        # Lower mass transfer = higher leakage
        # At 15C: k_ratio ~ 0.7, factor ~ 1.3
        # At 35C: k_ratio ~ 1.5, factor ~ 0.8
        kinetic_factor = 1.0 / (k_ratio ** 0.5)  # Square root damping

        # Clamp to reasonable range
        return max(0.5, min(kinetic_factor, 2.0))

    def _calculate_effective_capacity(self) -> float:
        """
        Calculate effective capacity including aging effects.

        Capacity decreases with cycles operated due to:
            - Organic fouling
            - Oxidation damage
            - Physical attrition
        """
        p = self.params

        # Start with base capacity factor
        capacity = p.capacity_factor

        # Apply aging degradation
        if p.cycles_operated > 0:
            aging_factor = (1.0 - p.aging_rate_per_cycle) ** p.cycles_operated
            capacity *= max(aging_factor, 0.5)  # Minimum 50% capacity

        return capacity

    def calculate_wac_h_effective_capacity(
        self,
        feed_ph: float,
        feed_alkalinity_mg_l_caco3: float
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate WAC H-form effective capacity using Henderson-Hasselbalch.

        WAC H-form has carboxylic acid sites (-COOH) with pKa ~4.8. At feed pH > pKa,
        equilibrium thermodynamics predict deprotonation, which would mean no capacity.

        However, real WAC columns work because:
        1. Sites start 100% protonated from acid regeneration
        2. Deprotonation is kinetically trapped - sites only convert through
           physical cation displacement, not equilibrium acid-base chemistry

        This method calculates effective capacity accounting for:
        - Henderson-Hasselbalch equilibrium (thermodynamic limit)
        - Kinetic trapping factor (operational reality)

        The model:
            effective_capacity = theoretical_capacity * kinetic_trap_factor

        Note: Alkalinity does NOT limit resin capacity - it affects SERVICE RUN LENGTH
        and pH profile during operation. The resin capacity is determined by the
        kinetic trap factor, which represents how much protonation is retained from
        acid regeneration despite the high pH equilibrium favoring deprotonation.

        Args:
            feed_ph: Feed water pH
            feed_alkalinity_mg_l_caco3: Feed alkalinity as CaCO3 (mg/L)

        Returns:
            Tuple of:
                - effective_capacity_eq_l: Effective capacity (eq/L resin)
                - diagnostics: Dict with calculation details

        Example:
            >>> overlay = EmpiricalLeakageOverlay()
            >>> cap, diag = overlay.calculate_wac_h_effective_capacity(7.8, 200)
            >>> print(f"Effective capacity: {cap:.2f} eq/L")
            >>> print(f"Equilibrium capacity: {diag['equilibrium_capacity_eq_l']:.4f} eq/L")
        """
        p = self.params
        diagnostics = {}

        # Henderson-Hasselbalch: fraction protonated at equilibrium
        # alpha = [A-] / [HA] = 10^(pH - pKa)
        # fraction_protonated = 1 / (1 + alpha) = 1 / (1 + 10^(pH - pKa))
        alpha = 10 ** (feed_ph - p.wac_h_pka)
        fraction_protonated_eq = 1.0 / (1.0 + alpha)

        # Equilibrium capacity (what PHREEQC predicts - nearly zero at high pH)
        equilibrium_capacity = p.wac_h_theoretical_capacity_eq_l * fraction_protonated_eq
        diagnostics['equilibrium_capacity_eq_l'] = equilibrium_capacity
        diagnostics['fraction_protonated_equilibrium'] = fraction_protonated_eq

        # Kinetically trapped capacity (operational reality)
        # Sites remain protonated from acid regeneration until physically displaced
        kinetic_capacity = p.wac_h_theoretical_capacity_eq_l * p.wac_h_kinetic_trap_factor
        diagnostics['kinetic_capacity_eq_l'] = kinetic_capacity
        diagnostics['kinetic_trap_factor'] = p.wac_h_kinetic_trap_factor

        # Alkalinity tracking (for pH profile, not capacity)
        # WAC H-form removes hardness by releasing H+, which consumes alkalinity:
        #   R-H + Ca²⁺ → R₂-Ca + 2H⁺
        #   2H⁺ + 2HCO₃⁻ → 2H₂O + 2CO₂
        #
        # The resin CAPACITY is determined by kinetic trapping, not alkalinity.
        # Alkalinity affects the pH profile during service (acid phase severity).
        alkalinity_eq_l = feed_alkalinity_mg_l_caco3 / 50000  # mg/L CaCO3 to eq/L
        diagnostics['alkalinity_eq_l'] = alkalinity_eq_l
        diagnostics['alkalinity_mg_l_caco3'] = feed_alkalinity_mg_l_caco3

        # Effective capacity is simply the kinetically trapped capacity
        # The kinetic trap factor accounts for incomplete regeneration, resin age, etc.
        effective_capacity = kinetic_capacity
        diagnostics['effective_capacity_eq_l'] = effective_capacity

        # Calculate capacity utilization factor (relative to theoretical)
        # Guard against division by zero if theoretical capacity is zero
        if p.wac_h_theoretical_capacity_eq_l > 0:
            capacity_factor = effective_capacity / p.wac_h_theoretical_capacity_eq_l
        else:
            capacity_factor = 0.0
        diagnostics['capacity_utilization_factor'] = capacity_factor

        # Limiting factor is kinetic trapping (equilibrium would give near-zero)
        diagnostics['limiting_factor'] = 'kinetic_trap'

        logger.debug(f"WAC H effective capacity: {effective_capacity:.3f} eq/L "
                    f"({capacity_factor*100:.1f}% of theoretical, "
                    f"eq. predicts {equilibrium_capacity:.4f} eq/L)")

        return effective_capacity, diagnostics

    def calculate_wac_h_leakage(
        self,
        feed_hardness_mg_l_caco3: float,
        feed_alkalinity_mg_l_caco3: float,
        feed_ph: float,
        feed_tds_mg_l: float,
        temperature_c: float = 25.0,
        phreeqc_leakage_mg_l: float = 0.0
    ) -> EmpiricalOverlayResult:
        """
        Calculate WAC H-form specific leakage using Henderson-Hasselbalch model.

        This is the main entry point for WAC H-form leakage prediction. It accounts for:
        1. Equilibrium vs kinetic capacity discrepancy
        2. Alkalinity limitation on effective capacity
        3. Standard empirical factors (TDS, regen efficiency, kinetics)

        The leakage model for WAC H-form is:
            C_leak = feed_hardness * (1 - effective_utilization) + empirical_floor

        Where effective_utilization accounts for Henderson-Hasselbalch effects.

        Args:
            feed_hardness_mg_l_caco3: Feed hardness as CaCO3 (mg/L)
            feed_alkalinity_mg_l_caco3: Feed alkalinity as CaCO3 (mg/L)
            feed_ph: Feed water pH
            feed_tds_mg_l: Feed TDS (mg/L)
            temperature_c: Temperature (C)
            phreeqc_leakage_mg_l: PHREEQC-calculated leakage (typically near feed for WAC H)

        Returns:
            EmpiricalOverlayResult with adjusted leakage values
        """
        p = self.params
        notes = []

        # Calculate effective capacity using Henderson-Hasselbalch
        effective_capacity, cap_diagnostics = self.calculate_wac_h_effective_capacity(
            feed_ph=feed_ph,
            feed_alkalinity_mg_l_caco3=feed_alkalinity_mg_l_caco3
        )
        notes.append(f"H-H equilibrium capacity: {cap_diagnostics['equilibrium_capacity_eq_l']:.4f} eq/L")
        notes.append(f"Kinetic capacity: {cap_diagnostics['kinetic_capacity_eq_l']:.2f} eq/L")
        notes.append(f"Effective capacity: {effective_capacity:.2f} eq/L ({cap_diagnostics['capacity_utilization_factor']*100:.0f}%)")
        notes.append(f"Limiting factor: {cap_diagnostics['limiting_factor']}")

        # Base leakage from capacity limitation
        # If capacity_utilization < 1, some hardness will leak through
        capacity_utilization = cap_diagnostics['capacity_utilization_factor']

        # Leakage increases as effective capacity decreases
        # The 0.5 scaling factor is a heuristic based on:
        # - Real IX columns don't leak 100% of feed even at 0% capacity
        # - Mass transfer and kinetics provide some removal even with degraded capacity
        # - Calibrate this factor against pilot data when available
        #
        # Formula: capacity_leakage = feed_hardness * (1 - utilization) * 0.5
        # At 100% capacity (utilization=1.0): capacity_leakage = 0
        # At 85% capacity (utilization=0.85): capacity_leakage = feed * 0.15 * 0.5 = 7.5%
        # At 0% capacity (utilization=0.0): capacity_leakage = feed * 1.0 * 0.5 = 50%
        CAPACITY_LEAKAGE_SCALE = 0.5  # Heuristic factor - calibrate from pilot data
        capacity_leakage = feed_hardness_mg_l_caco3 * (1.0 - capacity_utilization) * CAPACITY_LEAKAGE_SCALE
        notes.append(f"Capacity-based leakage: {capacity_leakage:.2f} mg/L (scale={CAPACITY_LEAKAGE_SCALE})")

        # Apply standard empirical factors
        base_result = self.calculate_empirical_leakage(
            feed_hardness_mg_l_caco3=feed_hardness_mg_l_caco3,
            feed_tds_mg_l=feed_tds_mg_l,
            temperature_c=temperature_c,
            phreeqc_leakage_mg_l=0.0,  # Ignore PHREEQC for WAC H
            resin_type="WAC_H"
        )

        # Combine capacity leakage with empirical baseline
        total_leakage = capacity_leakage + base_result.empirical_leakage_mg_l
        notes.append(f"Empirical baseline: {base_result.empirical_leakage_mg_l:.2f} mg/L")
        notes.append(f"Total leakage: {total_leakage:.2f} mg/L")

        # Cap at feed hardness
        if total_leakage > feed_hardness_mg_l_caco3:
            total_leakage = feed_hardness_mg_l_caco3
            notes.append(f"Capped at feed hardness")

        # Distribute between Ca and Mg
        ca_fraction = 0.6
        mg_fraction = 0.4
        ca_leakage = total_leakage * ca_fraction / 2.5
        mg_leakage = total_leakage * mg_fraction / 4.1

        # Adjusted breakthrough BV based on effective capacity
        adjusted_bv = capacity_utilization * p.regen_eff_eta
        notes.append(f"Adjusted BV factor: {adjusted_bv:.3f}")

        notes.extend(base_result.model_notes)

        # Convert equilibrium capacity (eq/L) to equivalent leakage (mg/L CaCO3)
        # This represents what leakage WOULD be if only equilibrium capacity were available
        # (i.e., with no kinetic trapping - essentially full feed hardness would leak)
        eq_capacity_eq_l = cap_diagnostics['equilibrium_capacity_eq_l']
        # At near-zero equilibrium capacity, leakage would be ~100% of feed hardness
        # Guard against division by zero if theoretical_capacity is mis-set
        if p.wac_h_theoretical_capacity_eq_l > 0:
            equilibrium_leakage = feed_hardness_mg_l_caco3 * (1.0 - eq_capacity_eq_l / p.wac_h_theoretical_capacity_eq_l)
        else:
            equilibrium_leakage = feed_hardness_mg_l_caco3  # Default to full feed hardness

        return EmpiricalOverlayResult(
            hardness_leakage_mg_l_caco3=total_leakage,
            ca_leakage_mg_l=ca_leakage,
            mg_leakage_mg_l=mg_leakage,
            equilibrium_leakage_mg_l=equilibrium_leakage,  # Now properly in mg/L CaCO3
            empirical_leakage_mg_l=total_leakage,
            tds_contribution_mg_l=base_result.tds_contribution_mg_l,
            regen_contribution_mg_l=base_result.regen_contribution_mg_l,
            kinetic_factor=base_result.kinetic_factor,
            effective_capacity_factor=capacity_utilization,
            adjusted_breakthrough_bv=adjusted_bv,
            model_notes=notes
        )

    def calculate_regen_efficiency_from_design(self, resin_type: str = "SAC") -> float:
        """
        Calculate regeneration efficiency from designer parameters.

        Industry correlations based on DuPont/Purolite data:
        - Salt dose is the primary driver of regen efficiency
        - Counter-current regeneration adds ~5% efficiency bonus
        - Insufficient rinse volume reduces effective efficiency

        Salt dose to efficiency correlation (SAC, co-current baseline):
            - 6 lb/ft³ (96 g/L)  → 85% efficiency
            - 10 lb/ft³ (160 g/L) → 90% efficiency
            - 15 lb/ft³ (240 g/L) → 94% efficiency

        The correlation is logarithmic, fitted to the above anchors:
            eta_base = 0.85 + 0.098 * ln(dose_g_l / 96)

        Args:
            resin_type: 'SAC', 'WAC_Na', or 'WAC_H' for resin-specific adjustments

        Returns:
            Calculated regeneration efficiency (0.80-0.98)
        """
        p = self.params
        notes = []

        # Base efficiency from salt dose (logarithmic correlation)
        # Calibrated to match documented anchors: 96 g/L → 85%, 160 g/L → 90%, 240 g/L → 94%
        dose = max(p.regenerant_dose_g_per_l, 60.0)  # Minimum 60 g/L
        eta_base = 0.85 + 0.098 * np.log(dose / 96.0)
        notes.append(f"Base efficiency from {dose:.0f} g/L: {eta_base*100:.1f}%")

        # Counter-current bonus (+5% efficiency)
        # Map common flow direction terms: "counter", "back", "upflow" → counter-current
        flow_dir = p.regen_flow_direction.lower()
        if flow_dir in ("counter", "back", "upflow", "counter-current", "countercurrent"):
            eta_base += 0.05
            notes.append("Counter-current bonus: +5%")

        # Rinse volume penalty (need at least 3 BV total)
        total_rinse = p.slow_rinse_volume_bv + p.fast_rinse_volume_bv
        if total_rinse < 3.0:
            rinse_penalty = 0.02 * (3.0 - total_rinse)  # 2% penalty per missing BV
            eta_base -= rinse_penalty
            notes.append(f"Rinse penalty ({total_rinse:.1f} BV < 3.0): -{rinse_penalty*100:.1f}%")

        # Resin type adjustments
        if resin_type == "WAC_Na":
            # WAC Na-form has two-step regeneration - harder to achieve high efficiency
            eta_base -= 0.04
            notes.append("WAC Na two-step regen penalty: -4%")
        elif resin_type == "WAC_H":
            # WAC H-form with HCl is more efficient
            eta_base += 0.03
            notes.append("WAC H acid regen bonus: +3%")

        # Clamp to reasonable range
        eta_final = max(0.80, min(eta_base, 0.98))

        logger.debug(f"Calculated regen efficiency: {eta_final:.3f} - " + "; ".join(notes))
        return eta_final

    def update_regen_efficiency_from_design(self, resin_type: str = "SAC") -> None:
        """
        Update self.params.regen_eff_eta based on designer lever parameters.

        Call this method before calculate_empirical_leakage() if designer
        parameters (regenerant_dose_g_per_l, regen_flow_direction) are set
        and you want to derive regen_eff_eta from them.
        """
        calculated_eta = self.calculate_regen_efficiency_from_design(resin_type)
        self.params.regen_eff_eta = calculated_eta
        logger.info(f"Updated regen_eff_eta to {calculated_eta:.3f} from design parameters")

    def apply_to_breakthrough_data(
        self,
        breakthrough_data: Dict[str, np.ndarray],
        feed_composition: Dict[str, float],
        resin_type: str = "SAC"
    ) -> Dict[str, np.ndarray]:
        """
        Apply empirical overlay to PHREEQC breakthrough data.

        Modifies the breakthrough curves to show realistic leakage
        instead of PHREEQC's near-zero equilibrium values.

        Args:
            breakthrough_data: PHREEQC output with BV, Ca, Mg, etc.
            feed_composition: Feed water composition
            resin_type: Resin type for calibration

        Returns:
            Modified breakthrough data with empirical leakage
        """
        if not breakthrough_data or 'BV' not in breakthrough_data:
            return breakthrough_data

        # Calculate feed properties
        feed_hardness = (
            feed_composition.get('ca_mg_l', 0) * 2.5 +
            feed_composition.get('mg_mg_l', 0) * 4.1
        )
        feed_tds = self._estimate_tds(feed_composition)
        temperature = feed_composition.get('temperature_c', 25.0)

        # Get empirical leakage prediction
        result = self.calculate_empirical_leakage(
            feed_hardness_mg_l_caco3=feed_hardness,
            feed_tds_mg_l=feed_tds,
            temperature_c=temperature,
            phreeqc_leakage_mg_l=0.0,  # PHREEQC typically returns ~0
            resin_type=resin_type
        )

        # Create modified breakthrough data
        modified_data = breakthrough_data.copy()

        # Apply floor leakage to hardness columns
        if 'Hardness_CaCO3' in modified_data:
            hardness = np.array(modified_data['Hardness_CaCO3'])
            # Add empirical leakage floor
            modified_data['Hardness_CaCO3'] = np.maximum(
                hardness,
                result.hardness_leakage_mg_l_caco3
            )
            logger.info(f"Applied empirical hardness floor: {result.hardness_leakage_mg_l_caco3:.2f} mg/L")

        if 'Ca_mg/L' in modified_data:
            ca = np.array(modified_data['Ca_mg/L'])
            modified_data['Ca_mg/L'] = np.maximum(ca, result.ca_leakage_mg_l)

        if 'Mg_mg/L' in modified_data:
            mg = np.array(modified_data['Mg_mg/L'])
            modified_data['Mg_mg/L'] = np.maximum(mg, result.mg_leakage_mg_l)

        # Adjust breakthrough BV if capacity is degraded
        if result.effective_capacity_factor < 1.0 and 'BV' in modified_data:
            modified_data['BV'] = modified_data['BV'] * result.adjusted_breakthrough_bv
            logger.info(f"Adjusted BV by factor {result.adjusted_breakthrough_bv:.3f}")

        return modified_data

    def _estimate_tds(self, composition: Dict[str, float]) -> float:
        """Estimate TDS from water composition."""
        # Sum major ions
        tds = (
            composition.get('ca_mg_l', 0) +
            composition.get('mg_mg_l', 0) +
            composition.get('na_mg_l', 0) +
            composition.get('k_mg_l', 0) +
            composition.get('cl_mg_l', 0) +
            composition.get('so4_mg_l', 0) +
            composition.get('hco3_mg_l', 0) +
            composition.get('no3_mg_l', 0)
        )
        return max(tds, 100.0)  # Minimum 100 mg/L


class CalibrationLoader:
    """
    Loads and saves calibration parameters for different sites/resins.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize loader with config directory.

        Args:
            config_dir: Directory for calibration files.
                       Defaults to databases/calibrations/
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "databases" / "calibrations"
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self, site_id: str, resin_type: str) -> CalibrationParameters:
        """
        Load calibration parameters for a site/resin combination.

        Args:
            site_id: Site identifier (e.g., 'plant_a', 'default')
            resin_type: Resin type ('SAC', 'WAC_Na', 'WAC_H')

        Returns:
            CalibrationParameters (defaults if not found)
        """
        # Try site-specific file first
        filename = f"{site_id}_{resin_type.lower()}.json"
        filepath = self.config_dir / filename

        if filepath.exists():
            try:
                with open(filepath) as f:
                    data = json.load(f)
                # Filter out metadata keys (start with _)
                param_data = {k: v for k, v in data.items() if not k.startswith('_')}
                params = CalibrationParameters(**param_data)
                logger.info(f"Loaded calibration from {filepath}")
                return params
            except Exception as e:
                logger.warning(f"Error loading {filepath}: {e}")

        # Try resin-type defaults
        default_file = self.config_dir / f"default_{resin_type.lower()}.json"
        if default_file.exists():
            try:
                with open(default_file) as f:
                    data = json.load(f)
                # Filter out metadata keys (start with _)
                param_data = {k: v for k, v in data.items() if not k.startswith('_')}
                params = CalibrationParameters(**param_data)
                logger.info(f"Loaded default calibration for {resin_type}")
                return params
            except Exception as e:
                logger.warning(f"Error loading defaults: {e}")

        # Return built-in defaults
        logger.info(f"Using built-in defaults for {resin_type}")
        return self._get_builtin_defaults(resin_type)

    def save(self, params: CalibrationParameters, site_id: str, resin_type: str):
        """
        Save calibration parameters.

        Args:
            params: Parameters to save
            site_id: Site identifier
            resin_type: Resin type
        """
        filename = f"{site_id}_{resin_type.lower()}.json"
        filepath = self.config_dir / filename

        data = {
            # Core parameters
            'capacity_factor': params.capacity_factor,
            'regen_eff_eta': params.regen_eff_eta,
            'leak_floor_a0': params.leak_floor_a0,
            'leak_tds_slope_a1': params.leak_tds_slope_a1,
            'leak_regen_coeff_a2': params.leak_regen_coeff_a2,
            'leak_regen_exponent_b': params.leak_regen_exponent_b,
            'k_ldf_25c': params.k_ldf_25c,
            'ea_activation_kj_mol': params.ea_activation_kj_mol,
            'channeling_factor': params.channeling_factor,
            'aging_rate_per_cycle': params.aging_rate_per_cycle,
            'cycles_operated': params.cycles_operated,
            'pka_shift': params.pka_shift,
            # Designer lever parameters - Regeneration
            'regenerant_dose_g_per_l': params.regenerant_dose_g_per_l,
            'regen_flow_direction': params.regen_flow_direction,
            'slow_rinse_volume_bv': params.slow_rinse_volume_bv,
            'fast_rinse_volume_bv': params.fast_rinse_volume_bv,
            # Designer lever parameters - Service
            'service_flow_bv_hr': params.service_flow_bv_hr,
            'bed_depth_m': params.bed_depth_m,
            # Designer lever parameters - Resin selection
            'resin_crosslinking_dvb': params.resin_crosslinking_dvb,
            'resin_form': params.resin_form,
            # WAC H+ specific - Na/K leakage
            'base_na_leakage_percent': params.base_na_leakage_percent,
            'base_k_leakage_percent': params.base_k_leakage_percent,
            'leakage_exhaustion_factor': params.leakage_exhaustion_factor,
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved calibration to {filepath}")

    def _get_builtin_defaults(self, resin_type: str) -> CalibrationParameters:
        """Get built-in defaults for each resin type."""
        defaults = {
            'SAC': CalibrationParameters(
                capacity_factor=0.95,
                regen_eff_eta=0.92,
                leak_floor_a0=0.5,
                leak_tds_slope_a1=0.8,
                leak_regen_coeff_a2=25.0,
                leak_regen_exponent_b=1.5,
                k_ldf_25c=50.0,
                # Designer lever defaults for SAC
                regenerant_dose_g_per_l=100.0,  # ~6.25 lb/ft³
                regen_flow_direction="counter",
                slow_rinse_volume_bv=1.0,
                fast_rinse_volume_bv=3.0,
                service_flow_bv_hr=12.0,
                bed_depth_m=1.5,
                resin_crosslinking_dvb=8.0,
                resin_form="gel",
            ),
            'WAC_Na': CalibrationParameters(
                capacity_factor=0.90,
                regen_eff_eta=0.88,  # WAC harder to regenerate
                leak_floor_a0=0.3,   # Lower floor (better selectivity)
                leak_tds_slope_a1=0.6,
                leak_regen_coeff_a2=30.0,  # More sensitive to regen
                leak_regen_exponent_b=1.5,
                k_ldf_25c=40.0,  # Slower kinetics than SAC
                # Designer lever defaults for WAC Na
                regenerant_dose_g_per_l=80.0,  # Two-step: HCl + NaOH
                regen_flow_direction="counter",
                slow_rinse_volume_bv=1.0,
                fast_rinse_volume_bv=3.0,
                service_flow_bv_hr=10.0,  # Slower than SAC
                bed_depth_m=1.5,
                resin_crosslinking_dvb=4.0,  # Lower crosslinking typical for WAC
                resin_form="gel",
            ),
            'WAC_H': CalibrationParameters(
                capacity_factor=0.92,
                regen_eff_eta=0.95,  # Acid regen more efficient
                leak_floor_a0=0.2,   # Very low floor
                leak_tds_slope_a1=0.5,
                leak_regen_coeff_a2=20.0,
                leak_regen_exponent_b=1.3,
                k_ldf_25c=35.0,
                pka_shift=0.0,
                # Designer lever defaults for WAC H
                regenerant_dose_g_per_l=60.0,  # HCl regeneration (lower needed)
                regen_flow_direction="counter",
                slow_rinse_volume_bv=1.0,
                fast_rinse_volume_bv=3.0,
                service_flow_bv_hr=10.0,
                bed_depth_m=1.5,
                resin_crosslinking_dvb=4.0,
                resin_form="gel",
                # WAC H+ specific Na/K leakage
                base_na_leakage_percent=2.0,
                base_k_leakage_percent=1.5,
                leakage_exhaustion_factor=3.0,
                # WAC H+ Henderson-Hasselbalch parameters
                wac_h_pka=4.8,
                wac_h_theoretical_capacity_eq_l=4.7,
                wac_h_kinetic_trap_factor=0.85,  # 85% of theoretical capacity retained
                wac_h_ph_floor=4.2,
            ),
        }
        return defaults.get(resin_type, CalibrationParameters())


def create_default_calibrations():
    """Create default calibration files for all resin types."""
    loader = CalibrationLoader()

    for resin_type in ['SAC', 'WAC_Na', 'WAC_H']:
        params = loader._get_builtin_defaults(resin_type)
        loader.save(params, 'default', resin_type)

    logger.info("Created default calibration files")


# Convenience function for quick leakage calculation
def calculate_leakage(
    feed_hardness_mg_l_caco3: float,
    feed_tds_mg_l: float,
    resin_type: str = "SAC",
    regen_efficiency: float = 0.92,
    temperature_c: float = 25.0
) -> float:
    """
    Quick calculation of expected leakage.

    This is the main entry point for getting a realistic leakage estimate
    without running full PHREEQC simulation.

    Args:
        feed_hardness_mg_l_caco3: Feed hardness as CaCO3 (mg/L)
        feed_tds_mg_l: Feed TDS (mg/L)
        resin_type: 'SAC', 'WAC_Na', or 'WAC_H'
        regen_efficiency: Regeneration efficiency (0.85-0.98)
        temperature_c: Temperature (C)

    Returns:
        Expected hardness leakage in mg/L as CaCO3

    Example:
        >>> leakage = calculate_leakage(300, 1500, 'SAC', 0.90)
        >>> print(f"Expected leakage: {leakage:.1f} mg/L as CaCO3")
        Expected leakage: 3.2 mg/L as CaCO3
    """
    loader = CalibrationLoader()
    params = loader.load('default', resin_type)
    params = CalibrationParameters(
        **{**params.__dict__, 'regen_eff_eta': regen_efficiency}
    )

    overlay = EmpiricalLeakageOverlay(params)
    result = overlay.calculate_empirical_leakage(
        feed_hardness_mg_l_caco3=feed_hardness_mg_l_caco3,
        feed_tds_mg_l=feed_tds_mg_l,
        temperature_c=temperature_c,
        phreeqc_leakage_mg_l=0.0,
        resin_type=resin_type
    )

    return result.hardness_leakage_mg_l_caco3


def calculate_wac_h_leakage(
    feed_hardness_mg_l_caco3: float,
    feed_alkalinity_mg_l_caco3: float,
    feed_ph: float,
    feed_tds_mg_l: float,
    regen_efficiency: float = 0.95,
    temperature_c: float = 25.0,
    kinetic_trap_factor: float = 0.85
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate WAC H-form leakage with Henderson-Hasselbalch capacity model.

    This is the recommended entry point for WAC H-form leakage prediction.
    It accounts for the fundamental thermodynamic vs kinetic capacity paradox:

    - At pH 7.8 with pKa 4.8: Henderson-Hasselbalch predicts 99.9% deprotonation
    - This means equilibrium models (PHREEQC) show no capacity
    - Real columns work via kinetically trapped protonation from acid regeneration

    The kinetic_trap_factor represents how much of the theoretical capacity
    is actually available due to kinetic trapping:
        - 0.0 = pure equilibrium (no capacity at pH > pKa)
        - 1.0 = fully trapped (100% capacity)
        - 0.85 = typical for fresh resin with good regeneration

    Args:
        feed_hardness_mg_l_caco3: Feed hardness as CaCO3 (mg/L)
        feed_alkalinity_mg_l_caco3: Feed alkalinity as CaCO3 (mg/L)
        feed_ph: Feed water pH
        feed_tds_mg_l: Feed TDS (mg/L)
        regen_efficiency: Regeneration efficiency (0.90-0.98 for WAC H)
        temperature_c: Temperature (C)
        kinetic_trap_factor: Kinetically trapped capacity factor (0.0-1.0)

    Returns:
        Tuple of:
            - leakage_mg_l_caco3: Expected hardness leakage (mg/L as CaCO3)
            - diagnostics: Dict with calculation details

    Example:
        >>> leakage, diag = calculate_wac_h_leakage(
        ...     feed_hardness_mg_l_caco3=300,
        ...     feed_alkalinity_mg_l_caco3=200,
        ...     feed_ph=7.8,
        ...     feed_tds_mg_l=1500
        ... )
        >>> print(f"Expected leakage: {leakage:.1f} mg/L as CaCO3")
        >>> print(f"Equilibrium capacity: {diag['equilibrium_capacity_eq_l']:.4f} eq/L (H-H predicts)")
        >>> print(f"Kinetic capacity: {diag['kinetic_capacity_eq_l']:.2f} eq/L (operational)")
    """
    loader = CalibrationLoader()
    params = loader.load('default', 'WAC_H')

    # Override with provided parameters
    params.regen_eff_eta = regen_efficiency
    params.wac_h_kinetic_trap_factor = kinetic_trap_factor

    overlay = EmpiricalLeakageOverlay(params)
    result = overlay.calculate_wac_h_leakage(
        feed_hardness_mg_l_caco3=feed_hardness_mg_l_caco3,
        feed_alkalinity_mg_l_caco3=feed_alkalinity_mg_l_caco3,
        feed_ph=feed_ph,
        feed_tds_mg_l=feed_tds_mg_l,
        temperature_c=temperature_c
    )

    # Build diagnostics dict
    diagnostics = {
        'hardness_leakage_mg_l_caco3': result.hardness_leakage_mg_l_caco3,
        'ca_leakage_mg_l': result.ca_leakage_mg_l,
        'mg_leakage_mg_l': result.mg_leakage_mg_l,
        'effective_capacity_factor': result.effective_capacity_factor,
        'adjusted_breakthrough_bv': result.adjusted_breakthrough_bv,
        'tds_contribution_mg_l': result.tds_contribution_mg_l,
        'regen_contribution_mg_l': result.regen_contribution_mg_l,
        'kinetic_factor': result.kinetic_factor,
        'model_notes': result.model_notes,
    }

    # Calculate H-H specific diagnostics
    effective_capacity, cap_diag = overlay.calculate_wac_h_effective_capacity(
        feed_ph=feed_ph,
        feed_alkalinity_mg_l_caco3=feed_alkalinity_mg_l_caco3
    )
    diagnostics.update(cap_diag)

    return result.hardness_leakage_mg_l_caco3, diagnostics
