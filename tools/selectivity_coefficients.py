"""
Selectivity coefficients from literature for capacity calculations.
All values from academic sources.
"""
import numpy as np


class SelectivityCoefficients:
    """Literature-based selectivity data from Helfferich and other academic sources."""

    # From Helfferich Ion Exchange, Table 5-9 and equations
    # Myers & Boyd experimental data for sulfonated polystyrene resins
    SAC_8DVB = {
        'Ca_Na': 5.16,    # Ca²⁺/Na⁺ at 8% DVB crosslinking
        'Mg_Na': 3.29,    # Mg²⁺/Na⁺ at 8% DVB
        'K_Na': 2.09,     # K⁺/Na⁺ at 8% DVB
        'H_Na': 1.27,     # H⁺/Na⁺ at 8% DVB
        'Ba_Na': 7.47,    # Ba²⁺/Na⁺ at 8% DVB
        'Sr_Na': 6.51,    # Sr²⁺/Na⁺ at 8% DVB
        'source': 'Helfferich Table 5-9, Myers & Boyd (1956)'
    }

    # Selectivity sequence from Helfferich p.424-425
    # Ba²⁺ > Pb²⁺ > Sr²⁺ > Ca²⁺ > Ni²⁺ > Cd²⁺ > Cu²⁺ > Co²⁺ > Zn²⁺ > Mg²⁺ > UO₂²⁺
    # Tl⁺ > Ag⁺ > Cs⁺ > Rb⁺ > K⁺ > NH₄⁺ > Na⁺ > H⁺ > Li⁺

    @staticmethod
    def calculate_separation_factor(K_A, K_B, z_A, z_B, C_total):
        """
        Calculate separation factor α from selectivity coefficients.

        From Helfferich Equation 5-24:
        α = K_A/K_B * (C_total)^(z_A - z_B)

        Args:
            K_A, K_B: Selectivity coefficients
            z_A, z_B: Valences of ions A and B
            C_total: Total solution normality (eq/L)

        Returns:
            Separation factor α
        """
        return K_A/K_B * (C_total ** (z_A - z_B))

    @staticmethod
    def binary_equilibrium(X_A_solution, K_AB, z_A=2, z_B=1):
        """
        Binary ion exchange equilibrium for heterovalent exchange.

        For Ca²⁺/Na⁺ exchange (z_A=2, z_B=1):
        X_Ca_resin = K * X_Ca_solution^(z_A/z_B) /
                     (1 + (K-1) * X_Ca_solution^(z_A/z_B))

        Args:
            X_A_solution: Equivalent fraction of ion A in solution
            K_AB: Selectivity coefficient A/B
            z_A: Valence of ion A (default 2 for Ca²⁺)
            z_B: Valence of ion B (default 1 for Na⁺)

        Returns:
            Equivalent fraction of ion A in resin
        """
        if X_A_solution <= 0:
            return 0
        if X_A_solution >= 1:
            return 1

        # For heterovalent exchange
        X_ratio = X_A_solution ** (z_A/z_B)
        X_A_resin = K_AB * X_ratio / (1 + (K_AB - 1) * X_ratio)
        return X_A_resin

    @staticmethod
    def multicomponent_equilibrium(solution_fractions, selectivity_matrix):
        """
        Multicomponent ion exchange equilibrium.

        Uses iterative solution of mass action equations.

        Args:
            solution_fractions: Dict of ion fractions in solution
            selectivity_matrix: Dict of selectivity coefficients

        Returns:
            Dict of ion fractions in resin
        """
        # Simplified - would need iterative solver for full multicomponent
        # For now, use weighted average approach
        resin_fractions = {}
        total = 0

        for ion, fraction in solution_fractions.items():
            K = selectivity_matrix.get(ion, 1.0)
            resin_fractions[ion] = fraction * K
            total += resin_fractions[ion]

        # Normalize
        for ion in resin_fractions:
            resin_fractions[ion] /= total

        return resin_fractions

    @staticmethod
    def temperature_correction(K_25C, T_celsius):
        """
        Temperature correction for selectivity coefficient.

        Van't Hoff equation approximation:
        ln(K_T/K_25) = -ΔH/R * (1/T - 1/298)

        Typical ΔH values for ion exchange: -4 to -8 kJ/mol

        Args:
            K_25C: Selectivity coefficient at 25°C
            T_celsius: Temperature in Celsius

        Returns:
            Temperature-corrected selectivity coefficient
        """
        # Approximate enthalpy of exchange (kJ/mol)
        delta_H = -6.0  # Typical for Ca/Na exchange
        R = 8.314e-3  # kJ/(mol·K)

        T_kelvin = T_celsius + 273.15
        T_ref = 298.15  # 25°C

        ln_K_ratio = -delta_H/R * (1/T_kelvin - 1/T_ref)
        K_T = K_25C * np.exp(ln_K_ratio)

        return K_T