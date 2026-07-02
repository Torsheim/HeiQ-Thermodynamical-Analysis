"""Process-route and energy models for EO/ACEO-assisted dehumidification."""

from __future__ import annotations

from dataclasses import dataclass

from .psychrometrics import MoistAirState, saturated_state_at_w, state_from_T_RH, state_from_T_w, T_from_h_w
from .cop import carnot_cop_cooling, effective_evap_temp_linear_by_fraction


@dataclass(frozen=True)
class ProcessResult:
    """Energy and state results for one route."""

    name: str
    start: MoistAirState
    target: MoistAirState
    intermediate: MoistAirState | None
    coil_exit: MoistAirState | None
    water_removed_by_eo_kg_s: float
    water_removed_by_coil_kg_s: float
    P_eo_W: float
    Q_coil_W: float
    P_compressor_W: float
    Q_reheat_W: float
    P_reheat_W: float
    P_total_W: float
    COP: float
    T_evap_C: float
    notes: str = ""


def eo_dehumidification_step(
    state_in: MoistAirState,
    target_w: float,
    dry_air_mass_flow_kg_s: float,
    e_p_Wh_per_kg_water: float,
    heat_to_process_fraction: float = 0.0,
) -> tuple[MoistAirState, float, float]:
    """Apply an idealised EO dehumidification step to the process air.

    The step removes water down to ``target_w``. Without heat leakage to the
    process stream, the step is assumed isothermal. A fraction of the electrical
    input can be added back to the process stream as sensible heat.
    """

    if target_w > state_in.w + 1e-12:
        raise ValueError("target_w must be lower than or equal to inlet humidity ratio")
    if dry_air_mass_flow_kg_s <= 0:
        raise ValueError("dry_air_mass_flow_kg_s must be positive")
    if e_p_Wh_per_kg_water < 0:
        raise ValueError("e_p_Wh_per_kg_water must be non-negative")
    if not 0.0 <= heat_to_process_fraction <= 1.0:
        raise ValueError("heat_to_process_fraction must be between 0 and 1")

    water_removed_kg_s = dry_air_mass_flow_kg_s * max(0.0, state_in.w - target_w)
    P_eo_W = e_p_Wh_per_kg_water * 3600.0 * water_removed_kg_s

    # Ideal isothermal dehumidification down to target_w.
    base_out = state_from_T_w(state_in.T_C, target_w, state_in.p_total_pa)

    # Add fraction of electrical energy as heat to process air.
    heat_added_kJ_per_kg_da = heat_to_process_fraction * P_eo_W / dry_air_mass_flow_kg_s / 1000.0
    h_out = base_out.h_kJ_per_kg_da + heat_added_kJ_per_kg_da
    T_out = T_from_h_w(h_out, target_w)
    state_out = state_from_T_w(T_out, target_w, state_in.p_total_pa)
    return state_out, P_eo_W, water_removed_kg_s


def conventional_ac_route(
    start: MoistAirState,
    target: MoistAirState,
    dry_air_mass_flow_kg_s: float,
    condenser_T_C: float,
    eta_carnot: float,
    evap_approach_C: float,
    reheat_COP: float = 1.0,
) -> ProcessResult:
    """Simple conventional cooling/dehumidification route.

    Route:
        start -> saturated state with target humidity ratio -> reheat to target.
    """

    coil_exit = saturated_state_at_w(target.w, start.p_total_pa)
    Q_coil_W = dry_air_mass_flow_kg_s * max(0.0, start.h_kJ_per_kg_da - coil_exit.h_kJ_per_kg_da) * 1000.0
    Q_reheat_W = dry_air_mass_flow_kg_s * max(0.0, target.h_kJ_per_kg_da - coil_exit.h_kJ_per_kg_da) * 1000.0
    T_evap_C = coil_exit.T_C - evap_approach_C
    COP = carnot_cop_cooling(T_evap_C, condenser_T_C, eta_carnot)
    P_compressor_W = Q_coil_W / COP
    P_reheat_W = Q_reheat_W / max(reheat_COP, 1e-9)
    P_total_W = P_compressor_W + P_reheat_W

    return ProcessResult(
        name="conventional_ac",
        start=start,
        target=target,
        intermediate=None,
        coil_exit=coil_exit,
        water_removed_by_eo_kg_s=0.0,
        water_removed_by_coil_kg_s=dry_air_mass_flow_kg_s * max(0.0, start.w - target.w),
        P_eo_W=0.0,
        Q_coil_W=Q_coil_W,
        P_compressor_W=P_compressor_W,
        Q_reheat_W=Q_reheat_W,
        P_reheat_W=P_reheat_W,
        P_total_W=P_total_W,
        COP=COP,
        T_evap_C=T_evap_C,
        notes="Conventional route: cool/dehumidify to saturated target-w state, then reheat.",
    )


def hybrid_eo_route(
    start: MoistAirState,
    target: MoistAirState,
    dry_air_mass_flow_kg_s: float,
    fraction_latent_by_eo: float,
    e_p_Wh_per_kg_water: float,
    heat_to_process_fraction: float,
    condenser_T_C: float,
    eta_carnot: float,
    evap_approach_C: float,
    conventional_evap_T_C: float,
    reheat_COP: float = 1.0,
    evap_model: str = "linear_by_fraction",
) -> ProcessResult:
    """Hybrid EO/ACEO + cooling route."""

    f = max(0.0, min(1.0, fraction_latent_by_eo))
    total_delta_w = max(0.0, start.w - target.w)
    w_after_eo = start.w - f * total_delta_w

    intermediate, P_eo_W, water_eo_kg_s = eo_dehumidification_step(
        start,
        target_w=w_after_eo,
        dry_air_mass_flow_kg_s=dry_air_mass_flow_kg_s,
        e_p_Wh_per_kg_water=e_p_Wh_per_kg_water,
        heat_to_process_fraction=heat_to_process_fraction,
    )

    remaining_latent_kg_s = dry_air_mass_flow_kg_s * max(0.0, intermediate.w - target.w)

    if remaining_latent_kg_s <= 1e-12:
        coil_exit = target
        Q_coil_W = dry_air_mass_flow_kg_s * max(0.0, intermediate.h_kJ_per_kg_da - target.h_kJ_per_kg_da) * 1000.0
        Q_reheat_W = 0.0
        T_evap_C = target.T_C - evap_approach_C
    else:
        coil_exit = saturated_state_at_w(target.w, start.p_total_pa)
        Q_coil_W = dry_air_mass_flow_kg_s * max(0.0, intermediate.h_kJ_per_kg_da - coil_exit.h_kJ_per_kg_da) * 1000.0
        Q_reheat_W = dry_air_mass_flow_kg_s * max(0.0, target.h_kJ_per_kg_da - coil_exit.h_kJ_per_kg_da) * 1000.0
        T_evap_sensible_C = target.T_C - evap_approach_C
        if evap_model == "linear_by_fraction":
            T_evap_C = effective_evap_temp_linear_by_fraction(f, conventional_evap_T_C, T_evap_sensible_C)
        elif evap_model == "strict_dewpoint_until_full":
            T_evap_C = conventional_evap_T_C
        else:
            raise ValueError(f"Unknown evap_model: {evap_model}")

    COP = carnot_cop_cooling(T_evap_C, condenser_T_C, eta_carnot)
    P_compressor_W = Q_coil_W / COP
    P_reheat_W = Q_reheat_W / max(reheat_COP, 1e-9)
    P_total_W = P_eo_W + P_compressor_W + P_reheat_W

    return ProcessResult(
        name="hybrid_eo_ac",
        start=start,
        target=target,
        intermediate=intermediate,
        coil_exit=coil_exit,
        water_removed_by_eo_kg_s=water_eo_kg_s,
        water_removed_by_coil_kg_s=remaining_latent_kg_s,
        P_eo_W=P_eo_W,
        Q_coil_W=Q_coil_W,
        P_compressor_W=P_compressor_W,
        Q_reheat_W=Q_reheat_W,
        P_reheat_W=P_reheat_W,
        P_total_W=P_total_W,
        COP=COP,
        T_evap_C=T_evap_C,
        notes=f"Hybrid route with f={f:.3f}, evap_model={evap_model}.",
    )


def states_from_scenario(config: dict) -> tuple[MoistAirState, MoistAirState]:
    """Build start and target states from a YAML scenario dictionary."""

    p = float(config.get("pressure_pa", 101_325.0))
    start = state_from_T_RH(float(config["start"]["T_C"]), float(config["start"]["RH"]), p)
    target = state_from_T_RH(float(config["target"]["T_C"]), float(config["target"]["RH"]), p)
    return start, target
