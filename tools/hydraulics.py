"""
Hydraulic Calculations for Ion Exchange Systems

Provides pressure drop, distributor design, and bed expansion calculations
for ion exchange vessel sizing and operation.

Key Features:
- Ergun equation for packed bed pressure drop
- Distributor/collector headloss correlations
- Velocity-dependent bed expansion (Richardson-Zaki)
- Freeboard sizing based on backwash expansion
- AWWA B100 compliance validation

References:
- Ergun, S. (1952). "Fluid flow through packed columns"
- Richardson & Zaki (1954). "Sedimentation and fluidisation"
- AWWA B100-09: Ion Exchange Materials Standard
- Water Treatment Plant Design (AWWA/ASCE), 5th Ed.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import math
import logging

logger = logging.getLogger(__name__)


# Physical Constants
WATER_DENSITY_KG_M3 = 1000.0  # kg/m³ at 20°C
WATER_VISCOSITY_PA_S = 0.001  # Pa·s at 20°C
GRAVITY_M_S2 = 9.81  # m/s²


@dataclass
class ResinProperties:
    """Physical properties of ion exchange resin."""
    particle_diameter_m: float  # m (typical: 0.0006-0.0008 m for 16-50 mesh)
    particle_density_kg_m3: float  # kg/m³ (typical: 1200-1300 for gel resins)
    bed_porosity: float  # void fraction (typical: 0.35-0.45 for settled bed)
    sphericity: float = 0.95  # shape factor (0.95-1.0 for spherical particles)


@dataclass
class HydraulicResult:
    """Results from hydraulic calculations."""
    # Pressure drop
    pressure_drop_service_kpa: float  # kPa during service
    pressure_drop_backwash_kpa: float  # kPa during backwash

    # Bed expansion
    bed_expansion_percent: float  # % expansion during backwash
    expanded_bed_depth_m: float  # m
    required_freeboard_m: float  # m (includes safety factor)

    # Distributor design
    distributor_headloss_kpa: float  # kPa through distributor/collector
    nozzle_velocity_m_s: float  # m/s through distributor nozzles

    # Validation
    velocity_in_range: bool  # True if 5-40 m/h per AWWA B100
    expansion_acceptable: bool  # True if expansion < 100%
    warnings: list[str]  # Any design warnings


def calculate_ergun_pressure_drop(
    bed_depth_m: float,
    bed_diameter_m: float,
    flow_rate_m3_h: float,
    resin_props: ResinProperties,
    temperature_c: float = 20.0
) -> float:
    """
    Calculate pressure drop through packed bed using Ergun equation.

    The Ergun equation combines viscous and inertial pressure losses:

        ΔP/L = 150·μ·(1-ε)²·v / (ε³·Dp²·ψ²) + 1.75·ρ·(1-ε)·v² / (ε³·Dp·ψ)

    Where:
        ΔP/L = pressure gradient (Pa/m)
        μ = dynamic viscosity (Pa·s)
        ε = bed porosity (void fraction)
        v = superficial velocity (m/s)
        Dp = particle diameter (m)
        ψ = particle sphericity
        ρ = fluid density (kg/m³)

    Args:
        bed_depth_m: Bed depth in meters
        bed_diameter_m: Vessel diameter in meters
        flow_rate_m3_h: Volumetric flow rate in m³/h
        resin_props: Resin physical properties
        temperature_c: Water temperature in °C (affects viscosity)

    Returns:
        Pressure drop in kPa
    """
    # Convert flow rate to m³/s
    flow_rate_m3_s = flow_rate_m3_h / 3600.0

    # Calculate superficial velocity (m/s)
    bed_area_m2 = math.pi * (bed_diameter_m / 2.0) ** 2
    velocity_m_s = flow_rate_m3_s / bed_area_m2

    # Temperature correction for viscosity (approximate)
    # μ(T) ≈ μ(20°C) · exp(-0.025 · (T - 20))
    viscosity = WATER_VISCOSITY_PA_S * math.exp(-0.025 * (temperature_c - 20.0))

    # Ergun equation terms
    porosity = resin_props.bed_porosity
    dp = resin_props.particle_diameter_m
    sphericity = resin_props.sphericity

    # Term 1: Viscous (laminar) component
    term1 = (
        150.0 * viscosity * (1 - porosity) ** 2 * velocity_m_s
        / (porosity ** 3 * dp ** 2 * sphericity ** 2)
    )

    # Term 2: Inertial (turbulent) component
    term2 = (
        1.75 * WATER_DENSITY_KG_M3 * (1 - porosity) * velocity_m_s ** 2
        / (porosity ** 3 * dp * sphericity)
    )

    # Total pressure gradient (Pa/m)
    dp_per_m = term1 + term2

    # Total pressure drop (Pa)
    pressure_drop_pa = dp_per_m * bed_depth_m

    # Convert to kPa
    pressure_drop_kpa = pressure_drop_pa / 1000.0

    logger.debug(
        f"Ergun ΔP: {pressure_drop_kpa:.2f} kPa "
        f"(velocity={velocity_m_s * 3600:.1f} m/h, "
        f"viscous={term1 * bed_depth_m / 1000:.2f} kPa, "
        f"inertial={term2 * bed_depth_m / 1000:.2f} kPa)"
    )

    return pressure_drop_kpa


def calculate_bed_expansion(
    flow_rate_m3_h: float,
    bed_diameter_m: float,
    resin_props: ResinProperties,
    temperature_c: float = 20.0
) -> Tuple[float, float]:
    """
    Calculate bed expansion during backwash using Richardson-Zaki correlation.

    The Richardson-Zaki equation relates voidage to velocity in fluidized beds:

        v = v_terminal · ε^n

    Where:
        v = superficial velocity
        v_terminal = terminal settling velocity of single particle
        ε = bed voidage (porosity) at velocity v
        n = Richardson-Zaki index (typically 4.65 for Re < 0.2)

    For terminal velocity, we use Stokes' law (low Reynolds number):

        v_terminal = g · Dp² · (ρ_p - ρ_f) / (18 · μ)

    Args:
        flow_rate_m3_h: Backwash flow rate in m³/h
        bed_diameter_m: Vessel diameter in meters
        resin_props: Resin physical properties
        temperature_c: Water temperature in °C

    Returns:
        Tuple of (expansion_percent, expanded_voidage)
    """
    # Convert flow to superficial velocity
    flow_rate_m3_s = flow_rate_m3_h / 3600.0
    bed_area_m2 = math.pi * (bed_diameter_m / 2.0) ** 2
    velocity_m_s = flow_rate_m3_s / bed_area_m2

    # Temperature correction for viscosity
    viscosity = WATER_VISCOSITY_PA_S * math.exp(-0.025 * (temperature_c - 20.0))

    # Calculate terminal settling velocity (Stokes' law)
    dp = resin_props.particle_diameter_m
    density_diff = resin_props.particle_density_kg_m3 - WATER_DENSITY_KG_M3

    v_terminal = (
        GRAVITY_M_S2 * dp ** 2 * density_diff / (18.0 * viscosity)
    )

    # Richardson-Zaki index (n = 4.65 for laminar, ~2.4 for turbulent)
    # Use intermediate value for typical IX operation
    n = 4.0

    # Calculate expanded voidage using Richardson-Zaki
    # v = v_terminal · ε^n  →  ε = (v / v_terminal)^(1/n)
    expanded_voidage = (velocity_m_s / v_terminal) ** (1.0 / n)

    # Clamp to physical limits
    expanded_voidage = min(max(expanded_voidage, resin_props.bed_porosity), 0.95)

    # Calculate expansion percentage
    # Bed height ratio: H_expanded / H_settled = (1 - ε_settled) / (1 - ε_expanded)
    height_ratio = (1 - resin_props.bed_porosity) / (1 - expanded_voidage)
    expansion_percent = (height_ratio - 1.0) * 100.0

    logger.debug(
        f"Bed expansion: {expansion_percent:.1f}% "
        f"(v={velocity_m_s * 3600:.1f} m/h, "
        f"v_terminal={v_terminal * 3600:.1f} m/h, "
        f"ε: {resin_props.bed_porosity:.3f} → {expanded_voidage:.3f})"
    )

    return expansion_percent, expanded_voidage


def calculate_distributor_headloss(
    flow_rate_m3_h: float,
    bed_diameter_m: float,
    nozzle_count: int = 20,
    nozzle_diameter_mm: float = 10.0
) -> Tuple[float, float]:
    """
    Calculate headloss through bed distributor/collector system.

    Uses orifice flow equation with discharge coefficient:

        ΔP = (ρ · v²) / (2 · Cd²)

    Where:
        v = velocity through nozzles (m/s)
        Cd = discharge coefficient (typically 0.6-0.8 for nozzles)

    Args:
        flow_rate_m3_h: Flow rate in m³/h
        bed_diameter_m: Vessel diameter in meters
        nozzle_count: Number of distributor nozzles
        nozzle_diameter_mm: Nozzle diameter in mm

    Returns:
        Tuple of (headloss_kpa, nozzle_velocity_m_s)
    """
    # Convert to m³/s and m
    flow_rate_m3_s = flow_rate_m3_h / 3600.0
    nozzle_diameter_m = nozzle_diameter_mm / 1000.0

    # Calculate nozzle area and velocity
    nozzle_area_m2 = math.pi * (nozzle_diameter_m / 2.0) ** 2
    total_nozzle_area = nozzle_area_m2 * nozzle_count
    nozzle_velocity_m_s = flow_rate_m3_s / total_nozzle_area

    # Orifice equation with discharge coefficient
    discharge_coeff = 0.7  # Typical for IX distributors
    headloss_pa = (
        WATER_DENSITY_KG_M3 * nozzle_velocity_m_s ** 2
        / (2.0 * discharge_coeff ** 2)
    )
    headloss_kpa = headloss_pa / 1000.0

    # Check for excessive velocity (>3 m/s can cause resin attrition)
    if nozzle_velocity_m_s > 3.0:
        logger.warning(
            f"High nozzle velocity: {nozzle_velocity_m_s:.2f} m/s "
            f"(>3 m/s may cause resin damage). Consider more nozzles."
        )

    return headloss_kpa, nozzle_velocity_m_s


def calculate_system_hydraulics(
    bed_depth_m: float,
    bed_diameter_m: float,
    service_flow_m3_h: float,
    backwash_flow_m3_h: float,
    resin_props: ResinProperties,
    temperature_c: float = 20.0,
    freeboard_safety_factor: float = 1.5
) -> HydraulicResult:
    """
    Perform complete hydraulic analysis for IX vessel.

    Args:
        bed_depth_m: Settled bed depth in meters
        bed_diameter_m: Vessel internal diameter in meters
        service_flow_m3_h: Service flow rate in m³/h
        backwash_flow_m3_h: Backwash flow rate in m³/h
        resin_props: Resin physical properties
        temperature_c: Operating temperature in °C
        freeboard_safety_factor: Multiplier for freeboard (default 1.5 = 50% safety)

    Returns:
        HydraulicResult with all calculations and warnings
    """
    warnings = []

    # 1. Service pressure drop
    dp_service = calculate_ergun_pressure_drop(
        bed_depth_m, bed_diameter_m, service_flow_m3_h,
        resin_props, temperature_c
    )

    # 2. Backwash pressure drop
    dp_backwash = calculate_ergun_pressure_drop(
        bed_depth_m, bed_diameter_m, backwash_flow_m3_h,
        resin_props, temperature_c
    )

    # 3. Bed expansion during backwash
    expansion_pct, expanded_voidage = calculate_bed_expansion(
        backwash_flow_m3_h, bed_diameter_m, resin_props, temperature_c
    )
    expanded_depth = bed_depth_m * (1 + expansion_pct / 100.0)

    # 4. Freeboard requirement
    # AWWA B100: Freeboard should accommodate bed expansion + safety margin
    required_freeboard = (expanded_depth - bed_depth_m) * freeboard_safety_factor

    # 5. Distributor headloss (estimate with typical nozzle count)
    # Rule of thumb: 1 nozzle per 0.03-0.05 m² of bed area
    bed_area = math.pi * (bed_diameter_m / 2.0) ** 2
    nozzle_count = max(int(bed_area / 0.04), 10)  # Minimum 10 nozzles
    dist_headloss, nozzle_vel = calculate_distributor_headloss(
        service_flow_m3_h, bed_diameter_m, nozzle_count
    )

    # 6. Validate linear velocity per AWWA B100
    bed_area_m2 = math.pi * (bed_diameter_m / 2.0) ** 2
    linear_velocity_m_h = service_flow_m3_h / bed_area_m2

    velocity_in_range = 5.0 <= linear_velocity_m_h <= 40.0
    if not velocity_in_range:
        warnings.append(
            f"Linear velocity {linear_velocity_m_h:.1f} m/h outside "
            f"AWWA B100 range (5-40 m/h)"
        )

    # 7. Validate expansion
    expansion_acceptable = expansion_pct < 100.0
    if not expansion_acceptable:
        warnings.append(
            f"Bed expansion {expansion_pct:.1f}% exceeds 100% "
            f"(reduce backwash rate or use larger diameter)"
        )

    # 8. Check pressure drop
    if dp_service > 70.0:
        warnings.append(
            f"Service pressure drop {dp_service:.1f} kPa high "
            f"(typical < 70 kPa). Consider shallower bed or coarser resin."
        )

    return HydraulicResult(
        pressure_drop_service_kpa=dp_service,
        pressure_drop_backwash_kpa=dp_backwash,
        bed_expansion_percent=expansion_pct,
        expanded_bed_depth_m=expanded_depth,
        required_freeboard_m=required_freeboard,
        distributor_headloss_kpa=dist_headloss,
        nozzle_velocity_m_s=nozzle_vel,
        velocity_in_range=velocity_in_range,
        expansion_acceptable=expansion_acceptable,
        warnings=warnings
    )


# Standard resin properties for common IX resins
STANDARD_SAC_RESIN = ResinProperties(
    particle_diameter_m=0.00065,  # 650 μm (16-50 mesh)
    particle_density_kg_m3=1250.0,  # Gel-type SAC
    bed_porosity=0.40,  # Typical settled bed
    sphericity=0.95
)

STANDARD_WAC_RESIN = ResinProperties(
    particle_diameter_m=0.00070,  # 700 μm (slightly larger)
    particle_density_kg_m3=1200.0,  # Acrylic WAC
    bed_porosity=0.42,  # Higher porosity
    sphericity=0.93  # Slightly less spherical
)
