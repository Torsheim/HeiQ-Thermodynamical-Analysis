from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required. Install with: pip install pyyaml") from exc


P_ATM_PA = 101_325.0
C_PA = 1.006      # kJ/(kg dry air K)
C_PV = 1.86       # kJ/(kg water vapour K)
C_PL = 4.186      # kJ/(kg liquid water K)
H_V0 = 2501.0     # kJ/kg water, psychrometric vapour enthalpy reference
M_WATER_KG_PER_MOL = 0.01801528


def saturation_pressure_water_pa(T_C: float) -> float:
    """Buck-type saturation pressure over liquid water, Pa."""
    return 611.21 * math.exp((18.678 - T_C / 234.5) * (T_C / (257.14 + T_C)))


def humidity_ratio_from_T_RH(T_C: float, RH_frac: float, p_atm_pa: float = P_ATM_PA) -> float:
    RH_frac = min(max(RH_frac, 0.0), 1.0)
    p_ws = saturation_pressure_water_pa(T_C)
    p_w = RH_frac * p_ws
    return 0.621945 * p_w / max(p_atm_pa - p_w, 1e-9)


def RH_from_T_w(T_C: float, w_kg_per_kg_da: float, p_atm_pa: float = P_ATM_PA) -> float:
    if w_kg_per_kg_da <= 0:
        return 0.0
    p_w = p_atm_pa * w_kg_per_kg_da / (0.621945 + w_kg_per_kg_da)
    return p_w / saturation_pressure_water_pa(T_C)


def moist_air_enthalpy_kJ_per_kg_da(T_C: float, w_kg_per_kg_da: float) -> float:
    return C_PA * T_C + w_kg_per_kg_da * (H_V0 + C_PV * T_C)


def T_from_h_w(h_kJ_per_kg_da: float, w_kg_per_kg_da: float) -> float:
    return (h_kJ_per_kg_da - H_V0 * w_kg_per_kg_da) / (C_PA + C_PV * w_kg_per_kg_da)


def water_vapour_enthalpy_kJ_per_kg(T_C: float) -> float:
    return H_V0 + C_PV * T_C


def liquid_water_enthalpy_kJ_per_kg(T_C: float) -> float:
    return C_PL * T_C


def latent_heat_kJ_per_kg(T_C: float) -> float:
    return water_vapour_enthalpy_kJ_per_kg(T_C) - liquid_water_enthalpy_kJ_per_kg(T_C)


def dewpoint_from_w_C(w_kg_per_kg_da: float, p_atm_pa: float = P_ATM_PA) -> float:
    """Return saturation temperature with the same humidity ratio."""
    lo, hi = -40.0, 80.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        w_mid = humidity_ratio_from_T_RH(mid, 1.0, p_atm_pa)
        if w_mid < w_kg_per_kg_da:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def cooling_COP_from_evap_C(
    evaporator_T_C: float,
    condenser_T_C: float = 45.0,
    carnot_efficiency: float = 0.516,
) -> float:
    T_e = evaporator_T_C + 273.15
    T_c = condenser_T_C + 273.15
    if T_c <= T_e + 0.1:
        return 20.0
    return max(0.1, carnot_efficiency * T_e / (T_c - T_e))


def reheat_purchased_power_W(reheat_load_W: float, reheat_mode: str) -> float:
    mode = reheat_mode.lower()
    if reheat_load_W <= 0:
        return 0.0
    if mode in {"free", "free_reheat", "none", "waste_heat"}:
        return 0.0
    if mode in {"electric", "electric_reheat"}:
        return reheat_load_W
    if mode in {"heat_pump_reheat_cop3", "heat_pump_cop3", "hp_reheat_cop3"}:
        return reheat_load_W / 3.0
    if mode.startswith("heat_pump_reheat_cop"):
        try:
            cop = float(mode.replace("heat_pump_reheat_cop", ""))
            return reheat_load_W / cop
        except ValueError:
            pass
    raise ValueError(f"Unknown reheat mode: {reheat_mode}")


def _nested_get(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _first_found(data: dict[str, Any], paths: list[tuple[str, ...]], default: Any) -> Any:
    for path in paths:
        val = _nested_get(data, path)
        if val is not None:
            return val
    return default


def _rh_to_frac(x: float) -> float:
    return x / 100.0 if x > 1.0 else x


def load_scenario_config(path: str | Path) -> dict[str, float]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    dry_air = float(
        _first_found(
            raw,
            [
                ("dry_air_mass_flow_kg_s",),
                ("dry_air_flow_kg_s",),
                ("mass_flow", "dry_air_kg_s"),
                ("airflow", "dry_air_mass_flow_kg_s"),
            ],
            1.0,
        )
    )

    start_T = float(
        _first_found(
            raw,
            [
                ("start_state", "T_C"),
                ("start", "T_C"),
                ("initial_state", "T_C"),
                ("process_inlet", "T_C"),
                ("T_start_C",),
                ("start_T_C",),
            ],
            30.0,
        )
    )
    start_RH = float(
        _first_found(
            raw,
            [
                ("start_state", "RH"),
                ("start_state", "RH_frac"),
                ("start_state", "relative_humidity"),
                ("start", "RH"),
                ("initial_state", "RH"),
                ("process_inlet", "RH"),
                ("RH_start",),
                ("start_RH",),
            ],
            0.80,
        )
    )

    target_T = float(
        _first_found(
            raw,
            [
                ("target_state", "T_C"),
                ("target", "T_C"),
                ("supply_target", "T_C"),
                ("T_target_C",),
                ("target_T_C",),
            ],
            22.0,
        )
    )
    target_RH = float(
        _first_found(
            raw,
            [
                ("target_state", "RH"),
                ("target_state", "RH_frac"),
                ("target_state", "relative_humidity"),
                ("target", "RH"),
                ("supply_target", "RH"),
                ("RH_target",),
                ("target_RH",),
            ],
            0.50,
        )
    )

    return {
        "dry_air_mass_flow_kg_s": dry_air,
        "start_T_C": start_T,
        "start_RH_frac": _rh_to_frac(start_RH),
        "target_T_C": target_T,
        "target_RH_frac": _rh_to_frac(target_RH),
    }


def conventional_baseline(
    T0_C: float,
    RH0_frac: float,
    Tt_C: float,
    RHt_frac: float,
    mdot_da_kg_s: float,
    reheat_mode: str,
    evap_approach_K: float,
    condenser_T_C: float,
    carnot_efficiency: float,
) -> dict[str, float]:
    w0 = humidity_ratio_from_T_RH(T0_C, RH0_frac)
    wt = humidity_ratio_from_T_RH(Tt_C, RHt_frac)
    h0 = moist_air_enthalpy_kJ_per_kg_da(T0_C, w0)
    ht = moist_air_enthalpy_kJ_per_kg_da(Tt_C, wt)

    if w0 > wt:
        coil_T_C = dewpoint_from_w_C(wt)
        h_coil = moist_air_enthalpy_kJ_per_kg_da(coil_T_C, wt)
        cooling_load_W = max(0.0, (h0 - h_coil) * mdot_da_kg_s * 1000.0)
        reheat_load_W = max(0.0, (ht - h_coil) * mdot_da_kg_s * 1000.0)
        evap_T_C = coil_T_C - evap_approach_K
    else:
        cooling_load_W = max(0.0, (h0 - ht) * mdot_da_kg_s * 1000.0)
        reheat_load_W = 0.0
        evap_T_C = Tt_C - evap_approach_K
        coil_T_C = Tt_C

    cop = cooling_COP_from_evap_C(evap_T_C, condenser_T_C, carnot_efficiency)
    compressor_W = cooling_load_W / cop
    reheat_purchased_W = reheat_purchased_power_W(reheat_load_W, reheat_mode)
    total_W = compressor_W + reheat_purchased_W

    return {
        "w_start": w0,
        "w_target": wt,
        "h_start": h0,
        "h_target": ht,
        "coil_exit_T_C": coil_T_C,
        "effective_evaporator_T_C": evap_T_C,
        "cooling_load_W": cooling_load_W,
        "reheat_load_W": reheat_load_W,
        "cop": cop,
        "compressor_W": compressor_W,
        "reheat_purchased_W": reheat_purchased_W,
        "total_purchased_W": total_W,
    }


def conditioning_power_from_state_to_target(
    Tin_C: float,
    win: float,
    Tt_C: float,
    wt: float,
    mdot_da_kg_s: float,
    reheat_mode: str,
    evap_approach_K: float,
    condenser_T_C: float,
    carnot_efficiency: float,
) -> dict[str, float]:
    hin = moist_air_enthalpy_kJ_per_kg_da(Tin_C, win)
    ht_exact_target = moist_air_enthalpy_kJ_per_kg_da(Tt_C, wt)

    over_dry = win < wt - 1e-9

    if win > wt + 1e-9:
        coil_T_C = dewpoint_from_w_C(wt)
        h_coil = moist_air_enthalpy_kJ_per_kg_da(coil_T_C, wt)
        cooling_load_W = max(0.0, (hin - h_coil) * mdot_da_kg_s * 1000.0)
        reheat_load_W = max(0.0, (ht_exact_target - h_coil) * mdot_da_kg_s * 1000.0)
        evap_T_C = coil_T_C - evap_approach_K
        final_T_C = Tt_C
        final_w = wt
    else:
        # No latent coil work. If the membrane has exactly reached target w, cool sensibly to target.
        # If it over-dries, keep the lower w and report over_dry=True.
        final_w = min(win, wt)
        h_final = moist_air_enthalpy_kJ_per_kg_da(Tt_C, final_w)
        cooling_load_W = max(0.0, (hin - h_final) * mdot_da_kg_s * 1000.0)
        reheat_load_W = max(0.0, (h_final - hin) * mdot_da_kg_s * 1000.0)
        evap_T_C = Tt_C - evap_approach_K
        coil_T_C = Tt_C
        final_T_C = Tt_C

    cop = cooling_COP_from_evap_C(evap_T_C, condenser_T_C, carnot_efficiency)
    compressor_W = cooling_load_W / cop
    reheat_purchased_W = reheat_purchased_power_W(reheat_load_W, reheat_mode)

    return {
        "coil_exit_T_C": coil_T_C,
        "effective_evaporator_T_C": evap_T_C,
        "cooling_load_W": cooling_load_W,
        "reheat_load_W": reheat_load_W,
        "cop": cop,
        "compressor_W": compressor_W,
        "reheat_purchased_W": reheat_purchased_W,
        "total_conditioning_purchased_W": compressor_W + reheat_purchased_W,
        "final_T_C": final_T_C,
        "final_w": final_w,
        "over_dry": over_dry,
    }


def simulate_two_sided_point(
    *,
    T0_C: float,
    RH0_frac: float,
    Tt_C: float,
    RHt_frac: float,
    mdot_da_process_kg_s: float,
    reheat_mode: str,
    receiver_T_C: float,
    receiver_RH_frac: float,
    receiver_flow_ratio: float,
    f_latent: float,
    e_p_Wh_per_kg: float,
    q_sorp_kJ_per_kg: float,
    q_desorp_kJ_per_kg: float,
    chi_sorp_process: float,
    chi_elec_process: float,
    eta_sorp_heat_to_desorp: float,
    eta_elec_heat_to_desorp: float,
    chi_desorp_from_receiver_air: float,
    external_desorp_heat_COP: float,
    evap_approach_K: float,
    condenser_T_C: float,
    carnot_efficiency: float,
    max_receiver_RH_frac: float,
    max_receiver_T_C: float,
    conventional_total_W: float,
) -> dict[str, float | bool | str]:
    w0 = humidity_ratio_from_T_RH(T0_C, RH0_frac)
    wt = humidity_ratio_from_T_RH(Tt_C, RHt_frac)
    h0 = moist_air_enthalpy_kJ_per_kg_da(T0_C, w0)

    total_dw = max(w0 - wt, 0.0)
    dw_proc = min(max(f_latent, 0.0), 1.0) * total_dw
    w_proc_after = w0 - dw_proc

    h_v_proc = water_vapour_enthalpy_kJ_per_kg(T0_C)
    e_p_kJ_per_kg = 3.6 * e_p_Wh_per_kg
    h_proc_after = h0 - dw_proc * h_v_proc + chi_sorp_process * dw_proc * q_sorp_kJ_per_kg + chi_elec_process * dw_proc * e_p_kJ_per_kg
    T_proc_after = T_from_h_w(h_proc_after, w_proc_after)
    RH_proc_after = RH_from_T_w(T_proc_after, w_proc_after)

    mwater_kg_s = mdot_da_process_kg_s * dw_proc
    P_eo_W = mwater_kg_s * e_p_Wh_per_kg * 3600.0
    Q_sorp_total_W = mwater_kg_s * q_sorp_kJ_per_kg * 1000.0
    Q_sorp_to_process_W = chi_sorp_process * Q_sorp_total_W
    Q_sorp_not_process_W = (1.0 - chi_sorp_process) * Q_sorp_total_W
    Q_elec_to_process_W = chi_elec_process * P_eo_W
    Q_elec_not_process_W = (1.0 - chi_elec_process) * P_eo_W

    conditioning = conditioning_power_from_state_to_target(
        T_proc_after,
        w_proc_after,
        Tt_C,
        wt,
        mdot_da_process_kg_s,
        reheat_mode,
        evap_approach_K,
        condenser_T_C,
        carnot_efficiency,
    )

    receiver_flow_ratio = max(receiver_flow_ratio, 1e-12)
    mdot_da_receiver_kg_s = mdot_da_process_kg_s * receiver_flow_ratio
    w_rec_in = humidity_ratio_from_T_RH(receiver_T_C, receiver_RH_frac)
    h_rec_in = moist_air_enthalpy_kJ_per_kg_da(receiver_T_C, w_rec_in)
    h_v_rec = water_vapour_enthalpy_kJ_per_kg(receiver_T_C)

    dw_rec_add = mwater_kg_s / mdot_da_receiver_kg_s if mdot_da_receiver_kg_s > 0 else 0.0
    w_rec_out = w_rec_in + dw_rec_add

    Q_desorp_required_W = mwater_kg_s * q_desorp_kJ_per_kg * 1000.0
    Q_internal_available_W = eta_sorp_heat_to_desorp * Q_sorp_not_process_W + eta_elec_heat_to_desorp * Q_elec_not_process_W
    Q_desorp_by_internal_W = min(Q_desorp_required_W, max(0.0, Q_internal_available_W))
    Q_desorp_remaining_W = max(0.0, Q_desorp_required_W - Q_desorp_by_internal_W)
    Q_desorp_from_receiver_air_W = chi_desorp_from_receiver_air * Q_desorp_remaining_W
    Q_desorp_external_heat_W = (1.0 - chi_desorp_from_receiver_air) * Q_desorp_remaining_W

    if external_desorp_heat_COP > 0:
        P_external_desorp_W = Q_desorp_external_heat_W / external_desorp_heat_COP
    else:
        P_external_desorp_W = 0.0

    # Receiver air gets added water vapour enthalpy, but may supply part of the desorption heat by evaporative cooling.
    h_rec_out = h_rec_in + dw_rec_add * h_v_rec - Q_desorp_from_receiver_air_W / max(mdot_da_receiver_kg_s * 1000.0, 1e-12)
    T_rec_out = T_from_h_w(h_rec_out, w_rec_out)
    RH_rec_out = RH_from_T_w(T_rec_out, w_rec_out)

    total_purchased_W = conditioning["total_conditioning_purchased_W"] + P_eo_W + P_external_desorp_W
    savings_pct = 100.0 * (conventional_total_W - total_purchased_W) / conventional_total_W if conventional_total_W > 0 else math.nan

    receiver_feasible = (RH_rec_out <= max_receiver_RH_frac) and (T_rec_out <= max_receiver_T_C)
    receiver_supersaturated = RH_rec_out > 1.0

    if f_latent >= 0.999:
        regime = "full_latent_removal"
    elif f_latent >= 0.9:
        regime = "near_full_latent_removal"
    elif f_latent >= 0.5:
        regime = "large_partial_latent_removal"
    elif f_latent >= 0.1:
        regime = "partial_pre_dehumidification"
    else:
        regime = "small_pre_dehumidification"

    return {
        "reheat_mode": reheat_mode,
        "receiver_T_in_C": receiver_T_C,
        "receiver_RH_in_pct": 100.0 * receiver_RH_frac,
        "receiver_flow_ratio": receiver_flow_ratio,
        "receiver_dry_air_flow_kg_s": mdot_da_receiver_kg_s,
        "f_latent_by_membrane": f_latent,
        "regime": regime,
        "e_p_Wh_per_kg_water": e_p_Wh_per_kg,
        "q_sorp_kJ_per_kg_water": q_sorp_kJ_per_kg,
        "q_desorp_kJ_per_kg_water": q_desorp_kJ_per_kg,
        "chi_sorp_to_process_air": chi_sorp_process,
        "chi_elec_to_process_air": chi_elec_process,
        "eta_sorp_heat_to_desorp": eta_sorp_heat_to_desorp,
        "eta_elec_heat_to_desorp": eta_elec_heat_to_desorp,
        "chi_desorp_from_receiver_air": chi_desorp_from_receiver_air,
        "external_desorp_heat_COP": external_desorp_heat_COP,
        "process_T_after_membrane_C": T_proc_after,
        "process_RH_after_membrane_pct": 100.0 * RH_proc_after,
        "process_w_after_membrane_g_per_kg_da": 1000.0 * w_proc_after,
        "water_removed_kg_s": mwater_kg_s,
        "water_removed_kg_h": mwater_kg_s * 3600.0,
        "EO_power_W": P_eo_W,
        "sorption_heat_total_W": Q_sorp_total_W,
        "sorption_heat_to_process_W": Q_sorp_to_process_W,
        "sorption_heat_not_process_W": Q_sorp_not_process_W,
        "electric_heat_to_process_W": Q_elec_to_process_W,
        "electric_heat_not_process_W": Q_elec_not_process_W,
        "desorption_heat_required_W": Q_desorp_required_W,
        "desorption_heat_by_internal_W": Q_desorp_by_internal_W,
        "desorption_heat_remaining_W": Q_desorp_remaining_W,
        "desorption_heat_from_receiver_air_W": Q_desorp_from_receiver_air_W,
        "desorption_external_heat_W": Q_desorp_external_heat_W,
        "desorption_external_purchased_W": P_external_desorp_W,
        "receiver_w_in_g_per_kg_da": 1000.0 * w_rec_in,
        "receiver_w_out_g_per_kg_da": 1000.0 * w_rec_out,
        "receiver_T_out_C": T_rec_out,
        "receiver_RH_out_pct": 100.0 * RH_rec_out,
        "receiver_feasible": bool(receiver_feasible),
        "receiver_supersaturated": bool(receiver_supersaturated),
        "coil_cooling_load_W": conditioning["cooling_load_W"],
        "coil_reheat_load_W": conditioning["reheat_load_W"],
        "coil_compressor_W": conditioning["compressor_W"],
        "coil_reheat_purchased_W": conditioning["reheat_purchased_W"],
        "coil_COP": conditioning["cop"],
        "hybrid_total_purchased_W": total_purchased_W,
        "conventional_total_purchased_W": conventional_total_W,
        "savings_pct": savings_pct,
        "over_dry_process": bool(conditioning["over_dry"]),
    }


def build_thresholds(df: pd.DataFrame, targets: list[float], max_receiver_RH_pct: float, max_receiver_T_C: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = [
        "reheat_mode",
        "q_sorp_kJ_per_kg_water",
        "q_desorp_kJ_per_kg_water",
        "f_latent_by_membrane",
        "e_p_Wh_per_kg_water",
        "receiver_T_in_C",
        "receiver_RH_in_pct",
        "eta_sorp_heat_to_desorp",
        "chi_desorp_from_receiver_air",
        "external_desorp_heat_COP",
        "chi_elec_to_process_air",
    ]

    for keys, g in df.groupby(group_cols, dropna=False):
        base = dict(zip(group_cols, keys))
        for target in targets:
            valid = g[(g["savings_pct"] >= target) & (g["receiver_feasible"])]
            if valid.empty:
                rows.append({**base, "target_savings_pct": target, "min_receiver_flow_ratio": math.nan, "max_chi_sorp_to_process_air": math.nan, "best_savings_pct": g["savings_pct"].max()})
                continue
            # The smallest receiver flow ratio among valid cases is a product-relevant criterion.
            min_ratio = valid["receiver_flow_ratio"].min()
            at_min_ratio = valid[valid["receiver_flow_ratio"] == min_ratio]
            # Among those, maximize allowed process-side sorption heat fraction.
            max_chi = at_min_ratio["chi_sorp_to_process_air"].max()
            best = valid.sort_values("savings_pct", ascending=False).iloc[0]
            rows.append(
                {
                    **base,
                    "target_savings_pct": target,
                    "min_receiver_flow_ratio": min_ratio,
                    "max_chi_sorp_to_process_air_at_min_ratio": max_chi,
                    "best_savings_pct": float(best["savings_pct"]),
                    "receiver_RH_out_pct_at_best": float(best["receiver_RH_out_pct"]),
                    "receiver_T_out_C_at_best": float(best["receiver_T_out_C"]),
                    "receiver_flow_ratio_at_best": float(best["receiver_flow_ratio"]),
                }
            )
    return pd.DataFrame(rows)


def plot_selected(df: pd.DataFrame, out_dir: Path, args: argparse.Namespace) -> None:
    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Pick a representative q close to h_fg if available, otherwise the first.
    q_unique = sorted(df["q_sorp_kJ_per_kg_water"].unique())
    q_plot = min(q_unique, key=lambda x: abs(x - 2431.0))
    f_plot = 1.0 if 1.0 in set(df["f_latent_by_membrane"].unique()) else sorted(df["f_latent_by_membrane"].unique())[-1]
    rec_T_plot = args.primary_receiver_T_C
    rec_RH_plot = 100.0 * args.primary_receiver_RH
    ratio_plot = args.primary_receiver_flow_ratio

    # Savings vs chi_sorp for selected receiver settings.
    sub = df[
        (np.isclose(df["q_sorp_kJ_per_kg_water"], q_plot))
        & (np.isclose(df["f_latent_by_membrane"], f_plot))
        & (np.isclose(df["receiver_T_in_C"], rec_T_plot))
        & (np.isclose(df["receiver_RH_in_pct"], rec_RH_plot))
        & (np.isclose(df["receiver_flow_ratio"], ratio_plot))
        & (np.isclose(df["eta_sorp_heat_to_desorp"], args.primary_eta_sorp_heat_to_desorp))
        & (np.isclose(df["chi_desorp_from_receiver_air"], args.primary_chi_desorp_from_receiver_air))
        & (np.isclose(df["external_desorp_heat_COP"], args.primary_external_desorp_heat_COP))
    ].copy()

    if not sub.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        for ep, g in sub.groupby("e_p_Wh_per_kg_water"):
            g = g.sort_values("chi_sorp_to_process_air")
            ax.plot(g["chi_sorp_to_process_air"], g["savings_pct"], marker="o", label=f"e_p={ep:g}")
        for target in args.target_savings:
            ax.axhline(target, linestyle="--", alpha=0.4)
            ax.text(1.01, target, f"{target:g}%", va="center")
        ax.set_xlabel("Fraction of sorption heat returning to process air, chi_sorp [-]")
        ax.set_ylabel("System saving vs conventional [%]")
        ax.set_title(
            f"Savings vs chi_sorp; q={q_plot:.0f}, f={f_plot:g}, receiver ratio={ratio_plot:g}"
        )
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(plot_dir / "savings_vs_chi_sorp_selected.png", dpi=200)
        plt.close(fig)

    # Receiver RH vs receiver flow ratio for selected q/f/e_p/chi.
    ep_plot = args.primary_e_p_Wh_per_kg
    chi_plot = args.primary_chi_sorp_to_process_air
    sub = df[
        (np.isclose(df["q_sorp_kJ_per_kg_water"], q_plot))
        & (np.isclose(df["f_latent_by_membrane"], f_plot))
        & (np.isclose(df["e_p_Wh_per_kg_water"], ep_plot))
        & (np.isclose(df["chi_sorp_to_process_air"], chi_plot))
        & (np.isclose(df["eta_sorp_heat_to_desorp"], args.primary_eta_sorp_heat_to_desorp))
        & (np.isclose(df["chi_desorp_from_receiver_air"], args.primary_chi_desorp_from_receiver_air))
        & (np.isclose(df["external_desorp_heat_COP"], args.primary_external_desorp_heat_COP))
    ].copy()
    if not sub.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        for (Trec, RHrec), g in sub.groupby(["receiver_T_in_C", "receiver_RH_in_pct"]):
            g = g.sort_values("receiver_flow_ratio")
            ax.plot(g["receiver_flow_ratio"], g["receiver_RH_out_pct"], marker="o", label=f"{Trec:g}C, {RHrec:g}% RH")
        ax.axhline(args.max_receiver_RH * 100.0, linestyle="--", label="receiver RH limit")
        ax.set_xscale("log")
        ax.set_xlabel("Receiver dry-air flow / process dry-air flow [-]")
        ax.set_ylabel("Receiver outlet RH [%]")
        ax.set_title(f"Receiver humidity; q={q_plot:.0f}, f={f_plot:g}, e_p={ep_plot:g}, chi_sorp={chi_plot:g}")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(plot_dir / "receiver_RH_vs_flow_ratio_selected.png", dpi=200)
        plt.close(fig)

    # Heat budget bar plot for selected row closest to primary settings.
    if not df.empty:
        candidates = df.copy()
        for col, val in [
            ("q_sorp_kJ_per_kg_water", q_plot),
            ("f_latent_by_membrane", f_plot),
            ("e_p_Wh_per_kg_water", ep_plot),
            ("chi_sorp_to_process_air", chi_plot),
            ("receiver_T_in_C", rec_T_plot),
            ("receiver_RH_in_pct", rec_RH_plot),
            ("receiver_flow_ratio", ratio_plot),
        ]:
            candidates["_dist"] = candidates.get("_dist", 0.0) + (candidates[col] - val).abs() / (abs(val) + 1e-9)
        row = candidates.sort_values("_dist").iloc[0]
        labels = [
            "EO power",
            "sorption heat",
            "to process",
            "to desorption",
            "external desorp heat",
            "coil compressor",
        ]
        values = [
            row["EO_power_W"],
            row["sorption_heat_total_W"],
            row["sorption_heat_to_process_W"],
            row["desorption_heat_by_internal_W"],
            row["desorption_external_heat_W"],
            row["coil_compressor_W"],
        ]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(labels, values)
        ax.set_ylabel("Power or heat rate [W]")
        ax.set_title("Selected two-sided heat budget")
        ax.tick_params(axis="x", rotation=30)
        ax.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(plot_dir / "selected_heat_budget.png", dpi=200)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Model 2.7: two-sided membrane water and heat balance for EO/ACEO dehumidification."
    )
    parser.add_argument("--config", default="scenarios/first_model.yaml")
    parser.add_argument("--out", default="outputs/model27_two_sided_membrane_balance")

    parser.add_argument("--reheat-modes", nargs="+", default=["free_reheat"])
    parser.add_argument("--receiver-T-C-values", type=float, nargs="+", default=[30.0, 35.0, 40.0])
    parser.add_argument("--receiver-RH-values", type=float, nargs="+", default=[0.2, 0.4, 0.6])
    parser.add_argument("--receiver-flow-ratios", type=float, nargs="+", default=[0.25, 0.5, 1.0, 2.0, 5.0])

    parser.add_argument("--f-values", type=float, nargs="+", default=[0.25, 0.5, 1.0])
    parser.add_argument("--e-p-values", type=float, nargs="+", default=[50.0, 100.0, 150.0, 200.0])
    parser.add_argument("--q-sorp-values", type=float, nargs="+", default=[2200.0, 2431.0, 2600.0, 2800.0])
    parser.add_argument("--q-desorp-values", type=float, nargs="+", default=None, help="If omitted, q_desorp is set equal to q_sorp for each point.")
    parser.add_argument("--chi-sorp-values", type=float, nargs="+", default=[0.0, 0.25, 0.5, 0.75, 1.0])
    parser.add_argument("--chi-elec-values", type=float, nargs="+", default=[0.5])
    parser.add_argument("--eta-sorp-heat-to-desorp-values", type=float, nargs="+", default=[0.0, 0.5, 1.0])
    parser.add_argument("--eta-elec-heat-to-desorp-values", type=float, nargs="+", default=[0.0])
    parser.add_argument("--chi-desorp-from-receiver-air-values", type=float, nargs="+", default=[0.0, 0.5, 1.0])
    parser.add_argument("--external-desorp-heat-COP-values", type=float, nargs="+", default=[0.0, 3.0])

    parser.add_argument("--target-savings", type=float, nargs="+", default=[0.0, 2.0, 5.0, 10.0])
    parser.add_argument("--max-receiver-RH", type=float, default=0.95)
    parser.add_argument("--max-receiver-T-C", type=float, default=65.0)

    parser.add_argument("--evap-approach-K", type=float, default=5.0)
    parser.add_argument("--condenser-T-C", type=float, default=45.0)
    parser.add_argument("--carnot-efficiency", type=float, default=0.516)

    # Primary settings only affect selected plots.
    parser.add_argument("--primary-receiver-T-C", type=float, default=35.0)
    parser.add_argument("--primary-receiver-RH", type=float, default=0.4)
    parser.add_argument("--primary-receiver-flow-ratio", type=float, default=1.0)
    parser.add_argument("--primary-e-p-Wh-per-kg", type=float, default=100.0)
    parser.add_argument("--primary-chi-sorp-to-process-air", type=float, default=0.5)
    parser.add_argument("--primary-eta-sorp-heat-to-desorp", type=float, default=1.0)
    parser.add_argument("--primary-chi-desorp-from-receiver-air", type=float, default=0.0)
    parser.add_argument("--primary-external-desorp-heat-COP", type=float, default=0.0)

    args = parser.parse_args()

    cfg = load_scenario_config(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    T0_C = cfg["start_T_C"]
    RH0_frac = cfg["start_RH_frac"]
    Tt_C = cfg["target_T_C"]
    RHt_frac = cfg["target_RH_frac"]
    mdot_da = cfg["dry_air_mass_flow_kg_s"]

    w0 = humidity_ratio_from_T_RH(T0_C, RH0_frac)
    wt = humidity_ratio_from_T_RH(Tt_C, RHt_frac)
    h0 = moist_air_enthalpy_kJ_per_kg_da(T0_C, w0)
    ht = moist_air_enthalpy_kJ_per_kg_da(Tt_C, wt)
    total_dw = max(w0 - wt, 0.0)
    water_remove_full_kg_h = mdot_da * total_dw * 3600.0
    h_fg = latent_heat_kJ_per_kg(T0_C)

    baselines: list[dict[str, Any]] = []
    baseline_by_mode: dict[str, dict[str, float]] = {}
    for mode in args.reheat_modes:
        conv = conventional_baseline(
            T0_C,
            RH0_frac,
            Tt_C,
            RHt_frac,
            mdot_da,
            mode,
            args.evap_approach_K,
            args.condenser_T_C,
            args.carnot_efficiency,
        )
        baseline_by_mode[mode] = conv
        baselines.append({"reheat_mode": mode, **conv})
    baseline_df = pd.DataFrame(baselines)
    baseline_df.to_csv(out_dir / "conventional_baselines.csv", index=False)

    rows: list[dict[str, Any]] = []
    for reheat_mode in args.reheat_modes:
        conv_total = baseline_by_mode[reheat_mode]["total_purchased_W"]
        for receiver_T_C in args.receiver_T_C_values:
            for receiver_RH in args.receiver_RH_values:
                receiver_RH_frac = receiver_RH / 100.0 if receiver_RH > 1 else receiver_RH
                for receiver_ratio in args.receiver_flow_ratios:
                    for f in args.f_values:
                        for e_p in args.e_p_values:
                            for q_sorp in args.q_sorp_values:
                                q_desorp_values = args.q_desorp_values if args.q_desorp_values is not None else [q_sorp]
                                for q_desorp in q_desorp_values:
                                    for chi_sorp in args.chi_sorp_values:
                                        for chi_elec in args.chi_elec_values:
                                            for eta_sorp in args.eta_sorp_heat_to_desorp_values:
                                                for eta_elec in args.eta_elec_heat_to_desorp_values:
                                                    for chi_des_air in args.chi_desorp_from_receiver_air_values:
                                                        for ext_cop in args.external_desorp_heat_COP_values:
                                                            rows.append(
                                                                simulate_two_sided_point(
                                                                    T0_C=T0_C,
                                                                    RH0_frac=RH0_frac,
                                                                    Tt_C=Tt_C,
                                                                    RHt_frac=RHt_frac,
                                                                    mdot_da_process_kg_s=mdot_da,
                                                                    reheat_mode=reheat_mode,
                                                                    receiver_T_C=receiver_T_C,
                                                                    receiver_RH_frac=receiver_RH_frac,
                                                                    receiver_flow_ratio=receiver_ratio,
                                                                    f_latent=f,
                                                                    e_p_Wh_per_kg=e_p,
                                                                    q_sorp_kJ_per_kg=q_sorp,
                                                                    q_desorp_kJ_per_kg=q_desorp,
                                                                    chi_sorp_process=chi_sorp,
                                                                    chi_elec_process=chi_elec,
                                                                    eta_sorp_heat_to_desorp=eta_sorp,
                                                                    eta_elec_heat_to_desorp=eta_elec,
                                                                    chi_desorp_from_receiver_air=chi_des_air,
                                                                    external_desorp_heat_COP=ext_cop,
                                                                    evap_approach_K=args.evap_approach_K,
                                                                    condenser_T_C=args.condenser_T_C,
                                                                    carnot_efficiency=args.carnot_efficiency,
                                                                    max_receiver_RH_frac=args.max_receiver_RH,
                                                                    max_receiver_T_C=args.max_receiver_T_C,
                                                                    conventional_total_W=conv_total,
                                                                )
                                                            )

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "two_sided_membrane_sweep.csv", index=False)

    thresholds = build_thresholds(df, args.target_savings, args.max_receiver_RH * 100.0, args.max_receiver_T_C)
    thresholds.to_csv(out_dir / "two_sided_receiver_thresholds.csv", index=False)

    feasible = df[(df["receiver_feasible"]) & (df["savings_pct"] >= min([t for t in args.target_savings if t > 0] or [0]))].copy()
    feasible = feasible.sort_values(["savings_pct", "receiver_RH_out_pct"], ascending=[False, True])
    feasible.head(5000).to_csv(out_dir / "feasible_design_points_top.csv", index=False)

    # Compact table for primary-like settings.
    compact = thresholds[
        (np.isclose(thresholds["receiver_T_in_C"], args.primary_receiver_T_C))
        & (np.isclose(thresholds["receiver_RH_in_pct"], 100.0 * args.primary_receiver_RH))
        & (np.isclose(thresholds["eta_sorp_heat_to_desorp"], args.primary_eta_sorp_heat_to_desorp))
        & (np.isclose(thresholds["chi_desorp_from_receiver_air"], args.primary_chi_desorp_from_receiver_air))
        & (np.isclose(thresholds["external_desorp_heat_COP"], args.primary_external_desorp_heat_COP))
        & (thresholds["target_savings_pct"].isin(args.target_savings))
    ].copy()
    compact.to_csv(out_dir / "two_sided_compact_thresholds_primary.csv", index=False)

    plot_selected(df, out_dir, args)

    report: list[str] = []
    report.append("# Model 2.7 two-sided membrane balance")
    report.append("")
    report.append("This run adds a receiver/exhaust side to the membrane model.")
    report.append("")
    report.append("## Scenario")
    report.append("")
    report.append(f"- Process inlet: {T0_C:.2f} C, RH={100*RH0_frac:.1f} %, w={1000*w0:.3f} g/kg_da, h={h0:.3f} kJ/kg_da")
    report.append(f"- Process target: {Tt_C:.2f} C, RH={100*RHt_frac:.1f} %, w={1000*wt:.3f} g/kg_da, h={ht:.3f} kJ/kg_da")
    report.append(f"- Water to remove for f=1: {1000*total_dw:.3f} g/kg_da = {water_remove_full_kg_h:.3f} kg/h at this process flow")
    report.append(f"- h_fg at process inlet: {h_fg:.1f} kJ/kg water")
    report.append("")
    report.append("## What is new relative to Model 2.6")
    report.append("")
    report.append("Model 2.6 asked how much sorption heat may return to the process air. Model 2.7 also asks where the water and heat go on the receiver side.")
    report.append("")
    report.append("The receiver-side bookkeeping uses:")
    report.append("")
    report.append("```text")
    report.append("Q_desorp_required = m_water * q_desorp")
    report.append("Q_internal_available = eta_sorp * Q_sorp_not_process + eta_elec * Q_elec_not_process")
    report.append("receiver air gains the added water vapour enthalpy, but can also supply desorption heat by evaporative cooling")
    report.append("```")
    report.append("")
    report.append("## Conventional baselines")
    report.append("")
    report.append("```text")
    report.append(baseline_df[["reheat_mode", "total_purchased_W", "cooling_load_W", "reheat_load_W", "cop"]].to_string(index=False))
    report.append("```")
    report.append("")
    report.append("## Compact primary thresholds")
    report.append("")
    if compact.empty:
        report.append("No rows matched the primary plotting settings. See `two_sided_receiver_thresholds.csv`.")
    else:
        show_cols = [
            "reheat_mode",
            "q_sorp_kJ_per_kg_water",
            "f_latent_by_membrane",
            "e_p_Wh_per_kg_water",
            "target_savings_pct",
            "min_receiver_flow_ratio",
            "max_chi_sorp_to_process_air_at_min_ratio",
            "best_savings_pct",
            "receiver_RH_out_pct_at_best",
        ]
        report.append("```text")
        report.append(compact[show_cols].head(120).to_string(index=False))
        report.append("```")
    report.append("")
    report.append("## Key output files")
    report.append("")
    report.append("- `two_sided_membrane_sweep.csv`")
    report.append("- `two_sided_receiver_thresholds.csv`")
    report.append("- `two_sided_compact_thresholds_primary.csv`")
    report.append("- `feasible_design_points_top.csv`")
    report.append("- `conventional_baselines.csv`")
    report.append("- `plots/`")
    report.append("")
    report.append("## Interpretation guide")
    report.append("")
    report.append("- Low required receiver flow ratio means the water can be rejected to a modest exhaust/receiver stream.")
    report.append("- High receiver outlet RH or supersaturation means the receiver side cannot carry the removed water as vapour under that condition.")
    report.append("- `eta_sorp_heat_to_desorp = 1` is an optimistic internal heat-reuse limit: sorption heat not returned to process air can help drive desorption on the receiver side.")
    report.append("- `chi_desorp_from_receiver_air = 1` is an evaporative-cooling limit: receiver air supplies desorption heat.")
    report.append("- `external_desorp_heat_COP > 0` charges purchased power for external desorption heat.")

    (out_dir / "two_sided_membrane_report.md").write_text("\n".join(report), encoding="utf-8")

    print(f"Wrote two-sided membrane outputs to: {out_dir}")
    print()
    print((out_dir / "two_sided_membrane_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
