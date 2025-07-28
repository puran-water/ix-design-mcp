"""
Kinetic Model for Ion Exchange

This module implements kinetic limitations for ion exchange modeling by adjusting
transport parameters based on flow conditions, temperature, and resin properties.
No fudge factors - only physical kinetic effects based on mass transfer theory.
"""

import logging
import math
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KineticParameters:
    """Parameters affecting ion exchange kinetics"""
    flow_rate_m3_hr: float
    bed_volume_m3: float
    bed_diameter_m: float
    resin_bead_diameter_mm: float = 0.6  # Typical 0.3-1.2 mm
    temperature_celsius: float = 25.0
    water_viscosity_cp: float = 1.0  # Centipoise at 25°C
    ionic_strength_M: float = 0.01
    
    @property
    def bed_height_m(self) -> float:
        """Calculate bed height from volume and diameter"""
        area = math.pi * (self.bed_diameter_m / 2) ** 2
        return self.bed_volume_m3 / area
    
    @property
    def superficial_velocity_m_hr(self) -> float:
        """Linear flow velocity in m/hr"""
        area = math.pi * (self.bed_diameter_m / 2) ** 2
        return self.flow_rate_m3_hr / area
    
    @property
    def ebct_minutes(self) -> float:
        """Empty bed contact time in minutes"""
        return (self.bed_volume_m3 / self.flow_rate_m3_hr) * 60
    
    @property
    def reynolds_number(self) -> float:
        """Reynolds number for flow through packed bed"""
        # Re = (ρ * v * d_p) / μ
        # For water at 25°C: ρ ≈ 1000 kg/m³
        velocity_m_s = self.superficial_velocity_m_hr / 3600
        diameter_m = self.resin_bead_diameter_mm / 1000
        viscosity_Pa_s = self.water_viscosity_cp / 1000
        return (1000 * velocity_m_s * diameter_m) / viscosity_Pa_s


class KineticModel:
    """
    Calculate kinetic limitations for ion exchange based on mass transfer theory.
    
    This model adjusts transport parameters to account for:
    - Film diffusion limitations at high flow rates
    - Particle diffusion limitations at low flow rates
    - Temperature effects on diffusion coefficients
    - Non-equilibrium conditions
    """
    
    def __init__(self):
        """Initialize kinetic model with literature correlations"""
        # Base diffusion coefficients at 25°C (m²/s)
        # Note: Ion diffusion in water ~ 1-2 × 10⁻⁹ m²/s
        # Ion diffusion in resin ~ 1-5 × 10⁻¹¹ m²/s
        self.D_film_base = 1.5e-9  # Film diffusion coefficient (Ca²⁺ in water)
        self.D_particle_base = 2e-11  # Particle diffusion coefficient (Ca²⁺ in resin)
        
        # Minimum EBCT for equilibrium (minutes)
        self.ebct_equilibrium = 3.0  # Below this, kinetic limitations apply
        
        # Temperature correction factor (per °C)
        self.temp_correction = 0.02  # 2% per degree
        
    def calculate_film_transfer_coefficient(self, params: KineticParameters) -> float:
        """
        Calculate film mass transfer coefficient using Wilson-Geankoplis correlation.
        
        For 0.0016 < Re < 55:
        Sh = 1.09 * (Re * Sc)^(1/3) * (ε)^(-1/3)
        
        Returns:
            Film transfer coefficient (1/s)
        """
        # Schmidt number: Sc = μ / (ρ * D)
        viscosity_Pa_s = params.water_viscosity_cp / 1000
        D_film = self.D_film_base * self.temperature_correction(params.temperature_celsius)
        Sc = viscosity_Pa_s / (1000 * D_film)
        
        # Sherwood number correlation
        Re = params.reynolds_number
        porosity = 0.4  # Typical for ion exchange beds
        
        if Re < 0.0016:
            # Very low flow - use minimum
            Sh = 2.0
        elif Re < 55:
            # Wilson-Geankoplis correlation
            # Correct the exponent on porosity term
            Sh = 1.09 * (Re * Sc) ** (1/3) / (porosity ** (1/3))
        else:
            # High flow - use Wakao-Funazkri
            Sh = 2.0 + 1.1 * Sc ** (1/3) * Re ** 0.6
            
        # Film transfer coefficient: k_f = Sh * D / d_p
        diameter_m = params.resin_bead_diameter_mm / 1000
        k_film = Sh * D_film / diameter_m
        
        # Apply porosity correction to actual mass transfer area
        # Actual area per volume is less than geometric due to porosity
        k_film = k_film * (1 - porosity) * 6 / diameter_m  # Convert to 1/s units
        
        return k_film
    
    def calculate_particle_diffusion_rate(self, params: KineticParameters) -> float:
        """
        Calculate particle diffusion rate constant.
        
        For spherical particles:
        k_p = 15 * D_p / (r_p^2)
        
        Returns:
            Particle diffusion rate constant (1/s)
        """
        D_particle = self.D_particle_base * self.temperature_correction(params.temperature_celsius)
        radius_m = params.resin_bead_diameter_mm / 2000  # Convert to radius in m
        
        # Correction for ionic strength (activity effects)
        # Higher ionic strength reduces diffusion in resin phase
        ionic_strength_factor = 1.0 / (1.0 + 10.0 * params.ionic_strength_M)  # Stronger effect in resin
        D_particle *= ionic_strength_factor
        
        k_particle = 15 * D_particle / (radius_m ** 2)
        
        return k_particle
    
    def temperature_correction(self, temp_celsius: float) -> float:
        """
        Calculate temperature correction factor for diffusion.
        
        Uses simplified Stokes-Einstein relation:
        D(T) / D(25°C) = T/298 * μ(25°C)/μ(T)
        
        Args:
            temp_celsius: Temperature in Celsius
            
        Returns:
            Correction factor (dimensionless)
        """
        T_kelvin = temp_celsius + 273.15
        T_ref = 298.15  # 25°C
        
        # Viscosity ratio (approximate)
        viscosity_ratio = math.exp(1.785 * (1/T_kelvin - 1/T_ref) * 1000)
        
        return (T_kelvin / T_ref) / viscosity_ratio
    
    def calculate_overall_rate(self, params: KineticParameters) -> Dict[str, float]:
        """
        Calculate overall mass transfer rate and controlling mechanism.
        
        The overall rate is limited by the slower of film or particle diffusion:
        1/k_overall = 1/k_film + 1/k_particle
        
        Returns:
            Dictionary with rate constants and controlling mechanism
        """
        k_film = self.calculate_film_transfer_coefficient(params)
        k_particle = self.calculate_particle_diffusion_rate(params)
        
        # Overall rate (resistances in series)
        k_overall = 1.0 / (1.0/k_film + 1.0/k_particle)
        
        # Determine controlling mechanism
        film_resistance = 1.0 / k_film
        particle_resistance = 1.0 / k_particle
        total_resistance = film_resistance + particle_resistance
        
        film_control_percent = (film_resistance / total_resistance) * 100
        
        if film_control_percent > 70:
            mechanism = "film_diffusion"
        elif film_control_percent < 30:
            mechanism = "particle_diffusion"
        else:
            mechanism = "mixed_control"
            
        return {
            'k_film': k_film,
            'k_particle': k_particle,
            'k_overall': k_overall,
            'mechanism': mechanism,
            'film_control_percent': film_control_percent,
            'time_constant_min': 1.0 / (k_overall * 60)  # Characteristic time
        }
    
    def calculate_kinetic_efficiency(self, params: KineticParameters) -> float:
        """
        Calculate kinetic efficiency factor (0-1) based on EBCT.
        
        This represents the fraction of theoretical capacity achieved
        under non-equilibrium conditions.
        
        Args:
            params: Kinetic parameters
            
        Returns:
            Efficiency factor (1.0 = equilibrium, <1.0 = kinetic limited)
        """
        # Get overall rate constant
        kinetics = self.calculate_overall_rate(params)
        time_constant_min = kinetics['time_constant_min']
        
        # Compare to actual contact time
        ebct_min = params.ebct_minutes
        
        # Efficiency based on first-order approach to equilibrium
        # η = 1 - exp(-t/τ) where τ is time constant
        if ebct_min > 5 * time_constant_min:
            # Essentially at equilibrium
            efficiency = 1.0
        else:
            # Kinetic limitation
            efficiency = 1.0 - math.exp(-ebct_min / time_constant_min)
            
        # Additional penalty for very high flow rates
        if params.superficial_velocity_m_hr > 40:
            # Above typical design range
            flow_penalty = 40 / params.superficial_velocity_m_hr
            efficiency *= flow_penalty
            
        return min(1.0, max(0.1, efficiency))  # Bound between 0.1 and 1.0
    
    def adjust_transport_parameters(self, 
                                  params: KineticParameters,
                                  base_dispersivity: float = 0.02,
                                  base_diffusion: float = 1e-10) -> Dict[str, float]:
        """
        Adjust PHREEQC TRANSPORT parameters for kinetic effects.
        
        Rather than using KINETICS blocks (complex), we adjust the
        transport parameters to approximate kinetic limitations.
        
        Args:
            params: Kinetic parameters
            base_dispersivity: Base dispersivity (m)
            base_diffusion: Base diffusion coefficient (m²/s)
            
        Returns:
            Adjusted transport parameters
        """
        kinetics = self.calculate_overall_rate(params)
        efficiency = self.calculate_kinetic_efficiency(params)
        
        # Increase dispersivity for kinetic limitations
        # More spreading when not at equilibrium
        kinetic_dispersion_factor = 2.0 - efficiency  # 1.0 to 2.0
        adjusted_dispersivity = base_dispersivity * kinetic_dispersion_factor
        
        # Reduce effective diffusion for slow kinetics
        adjusted_diffusion = base_diffusion * efficiency
        
        # Log details
        logger.info(f"Kinetic adjustments for EBCT={params.ebct_minutes:.1f} min:")
        logger.info(f"  Controlling mechanism: {kinetics['mechanism']}")
        logger.info(f"  Kinetic efficiency: {efficiency:.2f}")
        logger.info(f"  Dispersivity: {base_dispersivity:.3f} → {adjusted_dispersivity:.3f} m")
        logger.info(f"  Diffusion: {base_diffusion:.2e} → {adjusted_diffusion:.2e} m²/s")
        
        return {
            'dispersivity': adjusted_dispersivity,
            'diffusion_coefficient': adjusted_diffusion,
            'efficiency': efficiency,
            'mechanism': kinetics['mechanism']
        }
    
    def recommend_operating_conditions(self, params: KineticParameters) -> Dict[str, str]:
        """
        Recommend operating conditions to minimize kinetic limitations.
        
        Args:
            params: Current operating parameters
            
        Returns:
            Dictionary of recommendations
        """
        recommendations = {}
        kinetics = self.calculate_overall_rate(params)
        efficiency = self.calculate_kinetic_efficiency(params)
        
        if efficiency < 0.7:
            recommendations['efficiency'] = f"Low kinetic efficiency ({efficiency:.0%}). Consider reducing flow rate."
            
        if params.ebct_minutes < 2:
            target_flow = params.bed_volume_m3 * 60 / 3  # 3 min EBCT
            recommendations['ebct'] = f"EBCT too low ({params.ebct_minutes:.1f} min). Reduce flow to {target_flow:.1f} m³/hr"
            
        if kinetics['mechanism'] == 'film_diffusion' and params.superficial_velocity_m_hr > 25:
            recommendations['flow'] = "Film diffusion limited. Reduce flow rate or increase temperature"
            
        if kinetics['mechanism'] == 'particle_diffusion':
            recommendations['resin'] = "Consider using smaller bead size resin for faster kinetics"
            
        if params.temperature_celsius < 15:
            recommendations['temperature'] = "Low temperature reduces kinetics. Consider preheating if feasible"
            
        return recommendations


def estimate_kinetic_efficiency_simple(ebct_minutes: float, 
                                      flow_velocity_m_hr: float,
                                      resin_type: str = "SAC") -> float:
    """
    Simple kinetic efficiency estimate when detailed parameters aren't available.
    
    Args:
        ebct_minutes: Empty bed contact time
        flow_velocity_m_hr: Superficial velocity
        resin_type: Type of resin
        
    Returns:
        Efficiency factor (0-1)
    """
    # Base efficiency from EBCT
    if ebct_minutes >= 5:
        base_efficiency = 1.0
    elif ebct_minutes >= 3:
        base_efficiency = 0.9
    elif ebct_minutes >= 2:
        base_efficiency = 0.7
    elif ebct_minutes >= 1:
        base_efficiency = 0.5
    else:
        base_efficiency = 0.3
        
    # Flow rate penalty
    if flow_velocity_m_hr > 40:
        flow_factor = 0.7
    elif flow_velocity_m_hr > 25:
        flow_factor = 0.85
    else:
        flow_factor = 1.0
        
    # Resin type adjustment
    if resin_type.startswith("WAC"):
        # WAC has better kinetics (larger pores)
        resin_factor = 1.1
    else:
        resin_factor = 1.0
        
    return min(1.0, base_efficiency * flow_factor * resin_factor)


# Example usage
if __name__ == "__main__":
    # Test with typical industrial conditions
    params = KineticParameters(
        flow_rate_m3_hr=10.0,
        bed_volume_m3=2.0,
        bed_diameter_m=1.5,
        resin_bead_diameter_mm=0.6,
        temperature_celsius=20,
        ionic_strength_M=0.02
    )
    
    model = KineticModel()
    
    print(f"Operating Conditions:")
    print(f"  Flow rate: {params.flow_rate_m3_hr} m³/hr")
    print(f"  EBCT: {params.ebct_minutes:.1f} minutes")
    print(f"  Velocity: {params.superficial_velocity_m_hr:.1f} m/hr")
    print(f"  Reynolds number: {params.reynolds_number:.2f}")
    
    # Calculate kinetics
    kinetics = model.calculate_overall_rate(params)
    efficiency = model.calculate_kinetic_efficiency(params)
    
    print(f"\nKinetic Analysis:")
    print(f"  Film transfer coefficient: {kinetics['k_film']:.2e} 1/s")
    print(f"  Particle diffusion rate: {kinetics['k_particle']:.2e} 1/s")
    print(f"  Overall rate constant: {kinetics['k_overall']:.2e} 1/s")
    print(f"  Controlling mechanism: {kinetics['mechanism']}")
    print(f"  Film control: {kinetics['film_control_percent']:.0f}%")
    print(f"  Time constant: {kinetics['time_constant_min']:.1f} min")
    print(f"  Kinetic efficiency: {efficiency:.0%}")
    
    # Get adjusted parameters
    adjusted = model.adjust_transport_parameters(params)
    print(f"\nTransport Parameter Adjustments:")
    print(f"  Dispersivity: {adjusted['dispersivity']:.3f} m")
    print(f"  Diffusion coefficient: {adjusted['diffusion_coefficient']:.2e} m²/s")
    
    # Get recommendations
    recommendations = model.recommend_operating_conditions(params)
    if recommendations:
        print(f"\nRecommendations:")
        for issue, recommendation in recommendations.items():
            print(f"  {issue}: {recommendation}")