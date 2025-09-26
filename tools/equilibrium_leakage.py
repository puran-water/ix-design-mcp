"""
Ion Exchange Equilibrium Leakage Calculator

Based on USEPA Water Treatment Models implementation of Gaines-Thomas
equilibrium for heterovalent ion exchange.

Original Source:
    USEPA/Water_Treatment_Models
    IonExchangeModel/ixpy/hsdmix.py
    Authors: Jonathan Burkhardt, Boris Datsov, Levi Haupert
    License: Public domain (US Government work)

Key Reference:
    Helfferich, F. (1962). Ion Exchange. McGraw-Hill.
    - Chapter 5: Ion Exchange Equilibria
    - Electroselectivity effect: polyvalent ions preferentially
      taken up from dilute solutions

Gaines-Thomas Equation (Heterovalent Exchange):
    K_GT = (y_Ca × X_Na²) / (y_Na² × X_Ca)

    Where:
        y_i = solution phase mole/equivalent fraction
        X_i = resin phase equivalent fraction
        K_GT = thermodynamic selectivity coefficient

This module extracts ONLY the equilibrium solver for fast (<1 sec)
configuration calculations. For full column dynamics with mass
transfer, see the original USEPA model.
"""

import numpy as np
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class EquilibriumLeakageCalculator:
    """
    Calculate equilibrium leakage concentrations from feed water composition
    using Gaines-Thomas mass action law.

    This replaces the incorrect dose-based leakage model with a
    composition-based equilibrium model.
    """

    def __init__(self):
        self.MW_CA = 40.078
        self.MW_MG = 24.305
        self.MW_NA = 22.990
        self.MW_CACO3 = 100.09

    def calculate_sac_equilibrium_leakage(
        self,
        ca_mg_l: float,
        mg_mg_l: float,
        na_mg_l: float,
        K_Ca_Na: float = 5.16,
        K_Mg_Na: float = 3.29,
        f_active: float = 0.10
    ) -> Dict[str, float]:
        """
        Calculate SAC equilibrium hardness leakage from feed composition.

        Uses Gaines-Thomas equilibrium with partial bed utilization
        (mass transfer zone parameterization).

        Args:
            ca_mg_l: Feed calcium concentration (mg/L)
            mg_mg_l: Feed magnesium concentration (mg/L)
            na_mg_l: Feed sodium concentration (mg/L)
            K_Ca_Na: Ca²⁺/Na⁺ selectivity coefficient (default 5.16 for 8% DVB)
            K_Mg_Na: Mg²⁺/Na⁺ selectivity coefficient (default 3.29 for 8% DVB)
            f_active: Fraction of bed in active mass transfer zone (0.08-0.15)

        Returns:
            Dict with equilibrium leakage concentrations and diagnostics
        """
        ca_eq_l = ca_mg_l * 2 / self.MW_CA / 1000
        mg_eq_l = mg_mg_l * 2 / self.MW_MG / 1000
        na_eq_l = na_mg_l / self.MW_NA / 1000

        total_eq_l = ca_eq_l + mg_eq_l + na_eq_l

        if total_eq_l < 1e-10:
            logger.warning("Total cation concentration near zero")
            return {
                'ca_leakage_mg_l': 0.0,
                'mg_leakage_mg_l': 0.0,
                'hardness_leakage_mg_l_caco3': 0.0,
                'na_uptake_mg_l': 0.0
            }

        y_ca = ca_eq_l / total_eq_l
        y_mg = mg_eq_l / total_eq_l
        y_na = na_eq_l / total_eq_l

        X_ca, X_mg, X_na_eq = self._solve_equilibrium_resin_composition(
            y_ca, y_mg, y_na, K_Ca_Na, K_Mg_Na, f_active
        )

        y_ca_eq, y_mg_eq, y_na_eq = self._solve_equilibrium_solution_composition(
            X_ca, X_mg, X_na_eq, K_Ca_Na, K_Mg_Na, total_eq_l
        )

        ca_leakage_mg_l = y_ca_eq * total_eq_l * self.MW_CA / 2 * 1000
        mg_leakage_mg_l = y_mg_eq * total_eq_l * self.MW_MG / 2 * 1000
        na_leakage_mg_l = y_na_eq * total_eq_l * self.MW_NA * 1000

        hardness_leakage_eq_l = y_ca_eq * total_eq_l + y_mg_eq * total_eq_l
        hardness_leakage_mg_l_caco3 = hardness_leakage_eq_l * self.MW_CACO3 / 2 * 1000

        na_uptake_mg_l = na_mg_l - na_leakage_mg_l

        logger.debug(f"SAC Equilibrium Leakage Calculation:")
        logger.debug(f"  Feed: Ca={ca_mg_l:.1f}, Mg={mg_mg_l:.1f}, Na={na_mg_l:.1f} mg/L")
        logger.debug(f"  Feed fractions: y_Ca={y_ca:.4f}, y_Mg={y_mg:.4f}, y_Na={y_na:.4f}")
        logger.debug(f"  Resin fractions: X_Ca={X_ca:.4f}, X_Mg={X_mg:.4f}, X_Na={X_na_eq:.4f}")
        logger.debug(f"  Leakage: Ca={ca_leakage_mg_l:.2f}, Mg={mg_leakage_mg_l:.2f} mg/L")
        logger.debug(f"  Total hardness leakage: {hardness_leakage_mg_l_caco3:.2f} mg/L as CaCO3")

        return {
            'ca_leakage_mg_l': ca_leakage_mg_l,
            'mg_leakage_mg_l': mg_leakage_mg_l,
            'hardness_leakage_mg_l_caco3': hardness_leakage_mg_l_caco3,
            'na_uptake_mg_l': na_uptake_mg_l,
            'resin_composition': {
                'X_Ca': X_ca,
                'X_Mg': X_mg,
                'X_Na': X_na_eq
            },
            'effluent_fractions': {
                'y_Ca': y_ca_eq,
                'y_Mg': y_mg_eq,
                'y_Na': y_na_eq
            },
            'f_active': f_active
        }

    def _solve_equilibrium_resin_composition(
        self,
        y_ca: float,
        y_mg: float,
        y_na: float,
        K_Ca_Na: float,
        K_Mg_Na: float,
        f_active: float
    ) -> Tuple[float, float, float]:
        """
        Calculate resin phase composition at equilibrium in the active zone.

        Uses Gaines-Thomas mass action law with mass transfer zone parameterization.

        For heterovalent exchange:
            K_Ca_Na = (y_Ca × X_Na²) / (y_Na² × X_Ca)

        At equilibrium: X_Ca + X_Mg + X_Na = 1

        The f_active parameter represents the fraction of bed that is actively
        exchanging. The resin in this zone is in equilibrium with the feed,
        while (1 - f_active) fraction remains in Na-form.

        Returns:
            X_ca, X_mg, X_na: Resin phase composition (all must sum to 1.0)
        """
        if y_na < 1e-6:
            y_na = 1e-6

        X_ca_guess = 0.1
        X_mg_guess = 0.05
        X_na_guess = 1.0 - X_ca_guess - X_mg_guess

        for iteration in range(50):
            X_ca = (y_ca / K_Ca_Na) * (X_na_guess**2 / y_na**2)
            X_mg = (y_mg / K_Mg_Na) * (X_na_guess**2 / y_na**2)

            X_total = X_ca + X_mg + X_na_guess
            X_ca_norm = X_ca / X_total
            X_mg_norm = X_mg / X_total
            X_na_norm = X_na_guess / X_total

            if (abs(X_ca_norm - X_ca_guess) < 1e-6 and
                abs(X_mg_norm - X_mg_guess) < 1e-6 and
                abs(X_na_norm - X_na_guess) < 1e-6):
                break

            X_ca_guess = X_ca_norm
            X_mg_guess = X_mg_norm
            X_na_guess = X_na_norm

        if abs(X_ca_guess + X_mg_guess + X_na_guess - 1.0) > 0.01:
            logger.warning(f"Resin composition did not converge: sum={X_ca_guess + X_mg_guess + X_na_guess}")

        X_ca_active = X_ca_guess
        X_mg_active = X_mg_guess
        X_na_active = X_na_guess

        X_ca_avg = f_active * X_ca_active
        X_mg_avg = f_active * X_mg_active
        X_na_avg = f_active * X_na_active + (1.0 - f_active)

        total = X_ca_avg + X_mg_avg + X_na_avg
        if abs(total - 1.0) > 0.01:
            X_ca_avg /= total
            X_mg_avg /= total
            X_na_avg /= total

        return X_ca_avg, X_mg_avg, X_na_avg

    def _solve_equilibrium_solution_composition(
        self,
        X_ca: float,
        X_mg: float,
        X_na: float,
        K_Ca_Na: float,
        K_Mg_Na: float,
        C_total: float
    ) -> Tuple[float, float, float]:
        """
        Calculate solution phase composition from resin phase.

        This is the inverse problem: given resin composition X,
        find solution composition y that satisfies:
        1. Gaines-Thomas equilibrium
        2. Mass balance: y_Ca + y_Mg + y_Na = 1

        Uses quadratic formula from USEPA calc_Ceq_dv():
            aa * y_Na² + bb * y_Na + cc = 0
        """
        if X_ca < 1e-10 and X_mg < 1e-10:
            return 0.0, 0.0, 1.0

        selectivity_term = X_ca * K_Ca_Na + X_mg * K_Mg_Na
        aa = selectivity_term / X_na**2
        bb = 1.0
        cc = -1.0

        # When divalent loading is extremely small the quadratic becomes
        # ill-conditioned. Fall back to y_Na ≈ 1 (all Na⁺ in solution).
        if aa < 1e-12:
            return 0.0, 0.0, 1.0

        discriminant = bb**2 - 4 * aa * cc
        if discriminant < 0:
            logger.warning(f"Negative discriminant in equilibrium solver: {discriminant}")
            discriminant = 0

        y_na = (-bb + np.sqrt(discriminant)) / (2 * aa)
        y_na = max(1e-6, min(y_na, 1.0))

        y_ca = K_Ca_Na * X_ca * (y_na**2 / X_na**2)
        y_mg = K_Mg_Na * X_mg * (y_na**2 / X_na**2)

        y_total = y_ca + y_mg + y_na
        if abs(y_total - 1.0) > 0.01:
            y_ca = y_ca / y_total
            y_mg = y_mg / y_total
            y_na = y_na / y_total

        return y_ca, y_mg, y_na

    def calibrate_f_active(
        self,
        phreeqc_leakage_mg_l_caco3: float,
        ca_mg_l: float,
        mg_mg_l: float,
        na_mg_l: float,
        K_Ca_Na: float = 5.16,
        K_Mg_Na: float = 3.29
    ) -> float:
        """
        Calibrate f_active parameter to match PHREEQC simulation results.

        This is the key tuning parameter that accounts for:
        - Mass transfer zone length
        - Incomplete equilibration
        - Flow rate effects

        Args:
            phreeqc_leakage_mg_l_caco3: PHREEQC-predicted leakage
            ca_mg_l, mg_mg_l, na_mg_l: Feed water composition
            K_Ca_Na, K_Mg_Na: Selectivity coefficients

        Returns:
            Calibrated f_active value (typically 0.08-0.15)
        """
        f_active_min = 0.05
        f_active_max = 0.20
        tolerance = 0.1
        min_limit = 1e-4
        max_limit = 0.8

        def leakage_for(f_active_value: float) -> float:
            result = self.calculate_sac_equilibrium_leakage(
                ca_mg_l, mg_mg_l, na_mg_l, K_Ca_Na, K_Mg_Na, f_active_value
            )
            return result['hardness_leakage_mg_l_caco3']

        leakage_min = leakage_for(f_active_min)
        leakage_max = leakage_for(f_active_max)

        # Expand search window downwards if target is lower than our current minimum.
        if phreeqc_leakage_mg_l_caco3 < leakage_min:
            for _ in range(20):
                if f_active_min <= min_limit:
                    break
                f_active_max = f_active_min
                f_active_min = max(f_active_min / 2, min_limit)
                leakage_min = leakage_for(f_active_min)
                if phreeqc_leakage_mg_l_caco3 >= leakage_min:
                    break

        # Expand search window upwards if target is higher than our current maximum.
        elif phreeqc_leakage_mg_l_caco3 > leakage_max:
            for _ in range(20):
                if f_active_max >= max_limit:
                    break
                f_active_min = f_active_max
                f_active_max = min(f_active_max * 1.5, max_limit)
                leakage_max = leakage_for(f_active_max)
                if phreeqc_leakage_mg_l_caco3 <= leakage_max:
                    break

        # If the target still lies outside the achievable range we return the closest bound.
        if phreeqc_leakage_mg_l_caco3 <= leakage_min:
            logger.warning(
                "f_active calibration target below achievable range; returning minimum bound"
            )
            return f_active_min
        if phreeqc_leakage_mg_l_caco3 >= leakage_max:
            logger.warning(
                "f_active calibration target above achievable range; returning maximum bound"
            )
            return f_active_max

        f_active = None
        for _ in range(40):
            candidate = 0.5 * (f_active_min + f_active_max)
            leakage_predicted = leakage_for(candidate)
            error = leakage_predicted - phreeqc_leakage_mg_l_caco3

            if abs(error) < tolerance:
                f_active = candidate
                logger.info(
                    "Calibrated f_active=%.4f (leakage: %.2f mg/L vs %.2f mg/L target)",
                    candidate,
                    leakage_predicted,
                    phreeqc_leakage_mg_l_caco3
                )
                break

            if error > 0:
                f_active_max = candidate
            else:
                f_active_min = candidate

        if f_active is None:
            logger.warning("f_active calibration did not converge within tolerance")
            f_active = 0.5 * (f_active_min + f_active_max)

        return f_active
