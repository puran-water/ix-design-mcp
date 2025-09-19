"""
Vessel sizing calculations for IX systems with handcalcs rendering.

These functions are decorated with @handcalc to render equations in
"hand calculation" format in Jupyter notebooks.
"""

from math import pi, sqrt
try:
    from handcalcs.decorator import handcalc
except ImportError:
    # Fallback if handcalcs not available
    def handcalc(**kwargs):
        def decorator(func):
            return func
        return decorator

try:
    import forallpeople as si
    si.environment('default')
except ImportError:
    # If forallpeople not available, create dummy si object
    class DummySI:
        def __getattr__(self, name):
            return 1
    si = DummySI()


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_bed_volume(Q_m3_hr: float, SV_hr: float) -> tuple:
    """Calculate required resin bed volume.

    Args:
        Q_m3_hr: Design flow rate in m³/hr
        SV_hr: Service velocity in bed volumes per hour

    Returns:
        V_bed_m3: Bed volume in m³
        V_bed_L: Bed volume in liters
    """
    V_bed_m3 = Q_m3_hr / SV_hr  # Bed volume required in m³
    V_bed_L = V_bed_m3 * 1000   # Volume in liters
    return V_bed_m3, V_bed_L


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_minimum_area(Q_m3_hr: float, LV_max_m_hr: float) -> float:
    """Calculate minimum cross-sectional area for linear velocity constraint.

    Args:
        Q_m3_hr: Design flow rate in m³/hr
        LV_max_m_hr: Maximum linear velocity in m/hr

    Returns:
        A_min_m2: Minimum cross-sectional area in m²
    """
    A_min_m2 = Q_m3_hr / LV_max_m_hr  # Minimum area for linear velocity
    return A_min_m2


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_vessel_diameter(A_min_m2: float) -> float:
    """Calculate minimum vessel diameter from area.

    Args:
        A_min_m2: Minimum cross-sectional area in m²

    Returns:
        D_min_m: Minimum diameter in meters
    """
    D_min_m = sqrt(4 * A_min_m2 / pi)  # Minimum diameter
    return D_min_m


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_actual_area(D_selected_m: float) -> float:
    """Calculate actual cross-sectional area for selected diameter.

    Args:
        D_selected_m: Selected vessel diameter in meters

    Returns:
        A_actual_m2: Actual cross-sectional area in m²
    """
    A_actual_m2 = pi * (D_selected_m / 2) ** 2  # Actual area
    return A_actual_m2


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_linear_velocity(Q_m3_hr: float, A_actual_m2: float) -> float:
    """Calculate actual linear velocity.

    Args:
        Q_m3_hr: Design flow rate in m³/hr
        A_actual_m2: Actual cross-sectional area in m²

    Returns:
        LV_actual_m_hr: Actual linear velocity in m/hr
    """
    LV_actual_m_hr = Q_m3_hr / A_actual_m2  # Actual linear velocity
    return LV_actual_m_hr


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_bed_depth(V_bed_m3: float, A_actual_m2: float) -> float:
    """Calculate bed depth from volume and area.

    Args:
        V_bed_m3: Bed volume in m³
        A_actual_m2: Cross-sectional area in m²

    Returns:
        h_bed_m: Bed depth in meters
    """
    h_bed_m = V_bed_m3 / A_actual_m2  # Bed depth
    return h_bed_m


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_service_velocity(Q_m3_hr: float, V_bed_actual_m3: float) -> float:
    """Calculate actual service velocity in bed volumes per hour.

    Args:
        Q_m3_hr: Design flow rate in m³/hr
        V_bed_actual_m3: Actual bed volume in m³

    Returns:
        SV_actual_hr: Actual service velocity in BV/hr
    """
    SV_actual_hr = Q_m3_hr / V_bed_actual_m3  # Service velocity
    return SV_actual_hr


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_freeboard(h_bed_m: float, expansion_factor: float) -> float:
    """Calculate freeboard height for backwash expansion.

    Args:
        h_bed_m: Bed depth in meters
        expansion_factor: Expansion factor (1.0 = 100% expansion)

    Returns:
        h_freeboard_m: Freeboard height in meters
    """
    h_freeboard_m = h_bed_m * expansion_factor  # Freeboard height
    return h_freeboard_m


@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_vessel_height(h_bed_m: float, h_freeboard_m: float, h_distributor_m: float) -> float:
    """Calculate total vessel height.

    Args:
        h_bed_m: Bed depth in meters
        h_freeboard_m: Freeboard height in meters
        h_distributor_m: Height for distributor/collector in meters

    Returns:
        h_vessel_m: Total vessel height in meters
    """
    h_vessel_m = h_bed_m + h_freeboard_m + h_distributor_m  # Total height
    return h_vessel_m


@handcalc(jupyter_display=True, override="short", precision=2, left="\\[\n", right="\n\\]")
def calculate_aspect_ratio(h_bed_m: float, D_selected_m: float) -> float:
    """Calculate vessel aspect ratio (L/D).

    Args:
        h_bed_m: Bed depth in meters
        D_selected_m: Vessel diameter in meters

    Returns:
        aspect_ratio: Length to diameter ratio
    """
    aspect_ratio = h_bed_m / D_selected_m  # L/D ratio
    return aspect_ratio


# Additional calculations for WAC systems

@handcalc(jupyter_display=True, override="long", precision=2, left="\\[\n", right="\n\\]")
def calculate_wac_bed_expansion(h_bed_m: float, resin_form: str) -> float:
    """Calculate WAC bed expansion during regeneration.

    Args:
        h_bed_m: Bed depth in meters
        resin_form: 'Na' or 'H' form

    Returns:
        h_expanded_m: Expanded bed height in meters
    """
    if resin_form == 'Na':
        expansion_percent = 50.0  # Na-form expansion
    else:
        expansion_percent = 100.0  # H-form expansion

    h_expanded_m = h_bed_m * (1 + expansion_percent / 100)
    return h_expanded_m