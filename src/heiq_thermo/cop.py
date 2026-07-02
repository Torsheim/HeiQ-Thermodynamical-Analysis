"""Simple COP models for first-pass cooling calculations."""

from __future__ import annotations


def carnot_cop_cooling(T_evap_C: float, T_cond_C: float, eta_carnot: float = 0.45) -> float:
    """Modified Carnot COP for cooling."""

    T_e = T_evap_C + 273.15
    T_c = T_cond_C + 273.15
    if T_c <= T_e:
        raise ValueError("Condensing temperature must exceed evaporating temperature")
    return eta_carnot * T_e / (T_c - T_e)


def effective_evap_temp_linear_by_fraction(
    f_latent_by_eo: float,
    T_evap_conventional_C: float,
    T_evap_sensible_C: float,
) -> float:
    """Interpolate effective evaporator temperature as EO removes latent load."""

    f = max(0.0, min(1.0, f_latent_by_eo))
    return T_evap_conventional_C + f * (T_evap_sensible_C - T_evap_conventional_C)
