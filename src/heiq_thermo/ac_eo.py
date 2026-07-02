"""Simple surrogate models for asymmetric AC electroosmotic pumping.

These models are intentionally low-order. They are meant to be used before a
full FEM / Nernst-Planck / Stokes model is available.
"""

from __future__ import annotations

import math
from typing import Sequence

R_GAS = 8.31446261815324
WATER_MOLAR_VOLUME_M3_MOL = 18.01528e-6
WATER_SURFACE_TENSION_N_M = 0.072
WATER_DENSITY_KG_M3 = 997.0


def polynomial_flux(current_density_A_m2: float, coeffs: Sequence[float]) -> float:
    """Liquid EO flux surrogate from current density.

    ``coeffs`` are [a1, a2, a3, ...] such that J = a1*i + a2*i^2 + ...
    """

    i = current_density_A_m2
    return sum(a_n * i**n for n, a_n in enumerate(coeffs, start=1))


def square_wave_average_flux(
    i_plus_A_m2: float,
    duty_plus: float,
    coeffs: Sequence[float],
    zero_net_charge: bool = True,
    i_minus_A_m2: float | None = None,
) -> dict[str, float]:
    """Time-average flux over a two-level square-wave current program."""

    if not 0.0 < duty_plus < 1.0:
        raise ValueError("duty_plus must be between 0 and 1")
    if i_plus_A_m2 < 0:
        raise ValueError("i_plus_A_m2 should be positive")

    if zero_net_charge:
        i_minus = i_plus_A_m2 * duty_plus / (1.0 - duty_plus)
    else:
        i_minus = i_plus_A_m2 if i_minus_A_m2 is None else i_minus_A_m2

    J_plus = polynomial_flux(i_plus_A_m2, coeffs)
    J_minus = polynomial_flux(-i_minus, coeffs)
    J_avg = duty_plus * J_plus + (1.0 - duty_plus) * J_minus
    i_avg = duty_plus * i_plus_A_m2 + (1.0 - duty_plus) * (-i_minus)
    i_rms = math.sqrt(duty_plus * i_plus_A_m2**2 + (1.0 - duty_plus) * i_minus**2)
    return {
        "J_plus": J_plus,
        "J_minus": J_minus,
        "J_avg": J_avg,
        "i_minus_A_m2": i_minus,
        "i_avg_A_m2": i_avg,
        "i_rms_A_m2": i_rms,
    }


def kelvin_rh_threshold(radius_m: float, T_C: float, contact_angle_deg: float = 0.0) -> float:
    """Kelvin threshold RH for capillary condensation in a cylindrical pore."""

    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    T_K = T_C + 273.15
    cos_theta = math.cos(math.radians(contact_angle_deg))
    exponent = -2.0 * WATER_SURFACE_TENSION_N_M * WATER_MOLAR_VOLUME_M3_MOL * cos_theta / (radius_m * R_GAS * T_K)
    return max(0.0, min(1.0, math.exp(exponent)))


def filled_pore_fraction_from_distribution(
    RH: float,
    T_C: float,
    radii_m: Sequence[float],
    weights: Sequence[float] | None = None,
    contact_angle_deg: float = 0.0,
) -> float:
    """Return fraction of a pore-size distribution predicted to be water-filled."""

    if not 0.0 <= RH <= 1.0:
        raise ValueError("RH should be a fraction between 0 and 1")
    if weights is None:
        weights = [1.0] * len(radii_m)
    if len(radii_m) != len(weights):
        raise ValueError("radii_m and weights must have same length")
    total = sum(weights)
    if total <= 0:
        raise ValueError("weights must sum to a positive value")

    filled = 0.0
    for r, w in zip(radii_m, weights):
        if RH >= kelvin_rh_threshold(r, T_C, contact_angle_deg):
            filled += w
    return filled / total


def vapor_phase_aceo_water_flux(
    liquid_flux_m_s: float,
    mobile_water_factor: float,
    water_density_kg_m3: float = WATER_DENSITY_KG_M3,
) -> float:
    """Convert liquid superficial velocity to water mass flux for vapor operation."""

    if mobile_water_factor < 0:
        raise ValueError("mobile_water_factor cannot be negative")
    return water_density_kg_m3 * mobile_water_factor * liquid_flux_m_s
