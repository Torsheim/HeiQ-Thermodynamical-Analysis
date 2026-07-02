"""Psychrometric helper functions for moist air at near-atmospheric pressure.

Conventions
-----------
* Temperature is in degree Celsius unless the name ends in ``_K``.
* Relative humidity is a fraction, e.g. 0.8 for 80% RH.
* Humidity ratio ``w`` is kg water vapour / kg dry air.
* Moist-air enthalpy ``h`` is kJ / kg dry air.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

P_STD_PA = 101_325.0
MW_RATIO_WATER_DRY_AIR = 0.62198
CP_DRY_AIR_KJ_KG_K = 1.006
CP_WATER_VAPOUR_KJ_KG_K = 1.86
H_FG_0C_KJ_KG = 2501.0


@dataclass(frozen=True)
class MoistAirState:
    """A thermodynamic state of moist air per kg dry air."""

    T_C: float
    RH: float
    w: float
    h_kJ_per_kg_da: float
    p_v_pa: float
    dew_point_C: float
    p_total_pa: float = P_STD_PA

    @property
    def w_g_per_kg_da(self) -> float:
        return 1000.0 * self.w


def saturation_vapor_pressure_pa(T_C: float) -> float:
    """Return saturation vapour pressure of water over liquid water [Pa].

    Uses a Buck/Magnus-style correlation. It is accurate enough for first-pass
    HVAC calculations around ordinary air-conditioning temperatures.
    Validity target: roughly -20 to 60 C.
    """

    return 611.21 * math.exp((18.678 - T_C / 234.5) * (T_C / (257.14 + T_C)))


def vapor_pressure_from_T_RH(T_C: float, RH: float) -> float:
    """Water vapour partial pressure [Pa] from dry-bulb temperature and RH."""

    if not 0.0 <= RH <= 1.5:
        raise ValueError(f"RH should be a fraction around 0..1, got {RH!r}")
    return RH * saturation_vapor_pressure_pa(T_C)


def humidity_ratio_from_pv(p_v_pa: float, p_total_pa: float = P_STD_PA) -> float:
    """Humidity ratio kg water / kg dry air from vapour partial pressure."""

    if p_v_pa < 0:
        raise ValueError("Vapour pressure cannot be negative")
    if p_v_pa >= p_total_pa:
        raise ValueError("Vapour pressure must be below total pressure")
    return MW_RATIO_WATER_DRY_AIR * p_v_pa / (p_total_pa - p_v_pa)


def vapor_pressure_from_w(w: float, p_total_pa: float = P_STD_PA) -> float:
    """Water vapour partial pressure [Pa] from humidity ratio."""

    if w < 0:
        raise ValueError("Humidity ratio cannot be negative")
    return p_total_pa * w / (MW_RATIO_WATER_DRY_AIR + w)


def humidity_ratio(T_C: float, RH: float, p_total_pa: float = P_STD_PA) -> float:
    """Humidity ratio from dry-bulb temperature and RH fraction."""

    p_v = vapor_pressure_from_T_RH(T_C, RH)
    return humidity_ratio_from_pv(p_v, p_total_pa)


def relative_humidity_from_T_w(T_C: float, w: float, p_total_pa: float = P_STD_PA) -> float:
    """Relative humidity fraction from dry-bulb temperature and humidity ratio."""

    p_v = vapor_pressure_from_w(w, p_total_pa)
    return p_v / saturation_vapor_pressure_pa(T_C)


def moist_air_enthalpy_kJ_per_kg_da(T_C: float, w: float) -> float:
    """Moist-air enthalpy [kJ/kg dry air].

    Standard HVAC approximation:
        h = 1.006*T + w*(2501 + 1.86*T)
    with T in C and w in kg/kg dry air.
    """

    return CP_DRY_AIR_KJ_KG_K * T_C + w * (H_FG_0C_KJ_KG + CP_WATER_VAPOUR_KJ_KG_K * T_C)


def T_from_h_w(h_kJ_per_kg_da: float, w: float) -> float:
    """Invert the HVAC enthalpy formula to get dry-bulb T [C]."""

    denom = CP_DRY_AIR_KJ_KG_K + w * CP_WATER_VAPOUR_KJ_KG_K
    return (h_kJ_per_kg_da - H_FG_0C_KJ_KG * w) / denom


def dew_point_from_pv(p_v_pa: float, T_low_C: float = -80.0, T_high_C: float = 100.0) -> float:
    """Dew point [C] from water vapour partial pressure using bisection."""

    if p_v_pa <= 0:
        return float("-inf")
    lo, hi = T_low_C, T_high_C
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if saturation_vapor_pressure_pa(mid) < p_v_pa:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def dew_point_from_T_RH(T_C: float, RH: float) -> float:
    """Dew point [C] from dry-bulb temperature and RH fraction."""

    return dew_point_from_pv(vapor_pressure_from_T_RH(T_C, RH))


def state_from_T_RH(T_C: float, RH: float, p_total_pa: float = P_STD_PA) -> MoistAirState:
    """Construct a moist-air state from dry-bulb temperature and RH fraction."""

    p_v = vapor_pressure_from_T_RH(T_C, RH)
    w = humidity_ratio_from_pv(p_v, p_total_pa)
    h = moist_air_enthalpy_kJ_per_kg_da(T_C, w)
    T_dp = dew_point_from_pv(p_v)
    return MoistAirState(T_C=T_C, RH=RH, w=w, h_kJ_per_kg_da=h, p_v_pa=p_v, dew_point_C=T_dp, p_total_pa=p_total_pa)


def state_from_T_w(T_C: float, w: float, p_total_pa: float = P_STD_PA) -> MoistAirState:
    """Construct a moist-air state from dry-bulb temperature and humidity ratio."""

    p_v = vapor_pressure_from_w(w, p_total_pa)
    RH = p_v / saturation_vapor_pressure_pa(T_C)
    h = moist_air_enthalpy_kJ_per_kg_da(T_C, w)
    T_dp = dew_point_from_pv(p_v)
    return MoistAirState(T_C=T_C, RH=RH, w=w, h_kJ_per_kg_da=h, p_v_pa=p_v, dew_point_C=T_dp, p_total_pa=p_total_pa)


def saturated_state_at_w(w: float, p_total_pa: float = P_STD_PA) -> MoistAirState:
    """Return the saturated state whose humidity ratio is ``w``."""

    p_v = vapor_pressure_from_w(w, p_total_pa)
    T_sat = dew_point_from_pv(p_v)
    return state_from_T_w(T_sat, w, p_total_pa)
