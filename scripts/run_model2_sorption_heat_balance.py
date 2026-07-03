from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

P_ATM_PA = 101_325.0
C_PA = 1.006      # kJ/(kg dry air K)
C_PV = 1.86       # kJ/(kg water vapour K)
C_PL = 4.186      # kJ/(kg liquid water K)
H_V0 = 2501.0     # kJ/kg, psychrometric water-vapour enthalpy reference
EPS = 1e-12


def saturation_pressure_water_pa(T_C: float) -> float:
    """Buck saturation vapour pressure over liquid water, Pa."""
    return 611.21 * math.exp((18.678 - T_C / 234.5) * (T_C / (257.14 + T_C)))


def humidity_ratio_from_T_RH(T_C: float, RH_frac: float, p_atm_pa: float = P_ATM_PA) -> float:
    RH_frac = max(0.0, min(1.0, RH_frac))
    p_ws = saturation_pressure_water_pa(T_C)
    p_w = RH_frac * p_ws
    return 0.621945 * p_w / max(p_atm_pa - p_w, EPS)


def RH_from_T_w(T_C: float, w_kg_per_kg_da: float, p_atm_pa: float = P_ATM_PA) -> float:
    p_w = p_atm_pa * w_kg_per_kg_da / max(0.621945 + w_kg_per_kg_da, EPS)
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


def dewpoint_from_w(T_low_C: float, T_high_C: float, w_target: float, p_atm_pa: float = P_ATM_PA) -> float:
    """Return T such that saturated air has humidity ratio w_target."""
    lo, hi = T_low_C, T_high_C
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        w_mid = humidity_ratio_from_T_RH(mid, 1.0, p_atm_pa)
        if w_mid < w_target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def simple_cooling_cop(evap_air_exit_T_C: float, approach_K: float = 5.0, condenser_T_C: float = 40.0, carnot_eff: float = 0.45) -> float:
    """Simple COP model chosen to reproduce the earlier Model 1 order of magnitude."""
    T_evap_K = evap_air_exit_T_C - approach_K + 273.15
    T_cond_K = condenser_T_C + 273.15
    if T_cond_K <= T_evap_K + 1e-9:
        return 8.0
    cop = carnot_eff * T_evap_K / (T_cond_K - T_evap_K)
    return max(0.5, min(10.0, cop))


def reheat_power_W(q_reheat_W: float, mode: str, heat_pump_cop: float = 3.0) -> float:
    mode = mode.lower()
    if q_reheat_W <= 0:
        return 0.0
    if mode in {"free", "free_reheat", "waste_heat", "none"}:
        return 0.0
    if mode in {"electric", "electric_reheat"}:
        return q_reheat_W
    if mode in {"heat_pump", "heat_pump_reheat", "heat_pump_reheat_cop3"}:
        return q_reheat_W / max(heat_pump_cop, EPS)
    raise ValueError(f"Unknown reheat mode: {mode}")


def lambda_zawodzinski_vapour(a_w: float) -> float:
    """Zawodzinski/Springer vapour-equilibrated Nafion hydration polynomial."""
    a = max(0.0, min(1.0, a_w))
    return 0.043 + 17.81 * a - 39.85 * a**2 + 36.0 * a**3


# Approximate from Ludlam et al. 2024 Figure 4 for Nafion 117.
# The paper gives the trend and crossover; exact numerical points are read approximately.
_BOUND_FRACTION_RH = np.array([0.0, 0.10, 0.30, 0.50, 0.70, 0.88])
_BOUND_FRACTION_N117 = np.array([0.84, 0.66, 0.56, 0.50, 0.44, 0.36])


def bound_fraction_nafion117_from_RH(RH_frac: float) -> float:
    return float(np.interp(max(0.0, min(0.9, RH_frac)), _BOUND_FRACTION_RH, _BOUND_FRACTION_N117))


def q_sorp_surrogate_kJ_per_kg(T_C: float, RH_frac: float, excess_bound_kJ_per_kg: float = 300.0) -> float:
    """Simple enthalpy prior: liquid-like h_fg plus extra binding proportional to bound-water fraction."""
    return latent_heat_kJ_per_kg(T_C) + excess_bound_kJ_per_kg * bound_fraction_nafion117_from_RH(RH_frac)


def _get_by_path(data: dict[str, Any], path: Iterable[str]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _first_existing(data: dict[str, Any], paths: list[tuple[str, ...]], default: Any) -> Any:
    for path in paths:
        value = _get_by_path(data, path)
        if value is not None:
            return value
    return default


def _rh_to_fraction(value: float) -> float:
    value = float(value)
    if value > 1.5:
        return value / 100.0
    return value


def read_scenario_config(path: str | Path) -> dict[str, float]:
    """Read known first_model.yaml variants, with robust defaults."""
    path = Path(path)
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    m_da = float(
        _first_existing(
            data,
            [
                ("dry_air_mass_flow_kg_s",),
                ("dry_air_mass_flow_kg_da_s",),
                ("airflow", "dry_air_mass_flow_kg_s"),
                ("airflow", "dry_air_mass_flow_kg_da_s"),
                ("scenario", "dry_air_mass_flow_kg_s"),
            ],
            1.0,
        )
    )
    start_T = float(
        _first_existing(
            data,
            [
                ("start", "T_C"),
                ("start_state", "T_C"),
                ("inlet", "T_C"),
                ("process_air_in", "T_C"),
                ("start_T_C",),
            ],
            30.0,
        )
    )
    start_RH = _rh_to_fraction(
        _first_existing(
            data,
            [
                ("start", "RH"),
                ("start", "RH_frac"),
                ("start", "RH_pct"),
                ("start_state", "RH"),
                ("start_state", "RH_frac"),
                ("start_state", "RH_pct"),
                ("inlet", "RH"),
                ("process_air_in", "RH"),
                ("start_RH",),
            ],
            0.80,
        )
    )
    target_T = float(
        _first_existing(
            data,
            [
                ("target", "T_C"),
                ("target_state", "T_C"),
                ("outlet", "T_C"),
                ("process_air_out", "T_C"),
                ("target_T_C",),
            ],
            22.0,
        )
    )
    target_RH = _rh_to_fraction(
        _first_existing(
            data,
            [
                ("target", "RH"),
                ("target", "RH_frac"),
                ("target", "RH_pct"),
                ("target_state", "RH"),
                ("target_state", "RH_frac"),
                ("target_state", "RH_pct"),
                ("outlet", "RH"),
                ("process_air_out", "RH"),
                ("target_RH",),
            ],
            0.50,
        )
    )

    return {
        "dry_air_mass_flow_kg_s": m_da,
        "start_T_C": start_T,
        "start_RH_frac": start_RH,
        "target_T_C": target_T,
        "target_RH_frac": target_RH,
    }


def conventional_baseline(
    T0: float,
    RH0: float,
    Tt: float,
    RHt: float,
    m_da: float,
    reheat_mode: str,
    heat_pump_reheat_cop: float,
    coil_approach_K: float,
    condenser_T_C: float,
    carnot_eff: float,
) -> dict[str, float]:
    w0 = humidity_ratio_from_T_RH(T0, RH0)
    wt = humidity_ratio_from_T_RH(Tt, RHt)
    h0 = moist_air_enthalpy_kJ_per_kg_da(T0, w0)
    ht = moist_air_enthalpy_kJ_per_kg_da(Tt, wt)
    T_dew = dewpoint_from_w(-30.0, max(T0 + 10.0, Tt + 10.0), wt)
    h_coil_exit = moist_air_enthalpy_kJ_per_kg_da(T_dew, wt)

    cooling_load_W = max(0.0, m_da * (h0 - h_coil_exit) * 1000.0)
    reheat_load_W = max(0.0, m_da * (ht - h_coil_exit) * 1000.0)
    cop = simple_cooling_cop(T_dew, approach_K=coil_approach_K, condenser_T_C=condenser_T_C, carnot_eff=carnot_eff)
    compressor_W = cooling_load_W / cop
    reheat_purchased_W = reheat_power_W(reheat_load_W, reheat_mode, heat_pump_cop=heat_pump_reheat_cop)
    total_W = compressor_W + reheat_purchased_W
    return {
        "w0": w0,
        "wt": wt,
        "h0": h0,
        "ht": ht,
        "conventional_coil_exit_T_C": T_dew,
        "conventional_coil_exit_h_kJ_per_kg_da": h_coil_exit,
        "conventional_cooling_load_W": cooling_load_W,
        "conventional_reheat_load_W": reheat_load_W,
        "conventional_COP": cop,
        "conventional_compressor_W": compressor_W,
        "conventional_reheat_purchased_W": reheat_purchased_W,
        "conventional_total_purchased_W": total_W,
    }


def hybrid_case(
    base: dict[str, float],
    T0: float,
    RH0: float,
    Tt: float,
    RHt: float,
    m_da: float,
    f_latent_by_membrane: float,
    e_p_Wh_per_kg_water: float,
    q_sorp_kJ_per_kg_water: float,
    chi_sorp: float,
    chi_elec: float,
    reheat_mode: str,
    heat_pump_reheat_cop: float,
    sorption_heat_rejection_cop: float,
    coil_approach_K: float,
    condenser_T_C: float,
    carnot_eff: float,
) -> dict[str, float]:
    w0 = base["w0"]
    wt = base["wt"]
    h0 = base["h0"]
    ht = base["ht"]
    total_dw = max(w0 - wt, 0.0)
    f = max(0.0, min(1.0, f_latent_by_membrane))
    dw_mem = f * total_dw
    w_mem = w0 - dw_mem

    h_v = water_vapour_enthalpy_kJ_per_kg(T0)
    e_p_kJ_per_kg_water = 3.6 * e_p_Wh_per_kg_water

    h_after_mem = (
        h0
        - dw_mem * h_v
        + chi_sorp * dw_mem * q_sorp_kJ_per_kg_water
        + chi_elec * dw_mem * e_p_kJ_per_kg_water
    )
    T_after_mem = T_from_h_w(h_after_mem, w_mem)
    RH_after_mem = RH_from_T_w(T_after_mem, w_mem)

    membrane_sorption_heat_total_W = m_da * dw_mem * q_sorp_kJ_per_kg_water * 1000.0
    membrane_sorption_heat_to_process_W = chi_sorp * membrane_sorption_heat_total_W
    membrane_sorption_heat_rejected_W = (1.0 - chi_sorp) * membrane_sorption_heat_total_W
    membrane_electric_power_W = m_da * dw_mem * e_p_Wh_per_kg_water * 3600.0
    membrane_electric_heat_to_process_W = chi_elec * membrane_electric_power_W

    if sorption_heat_rejection_cop and sorption_heat_rejection_cop > 0:
        membrane_heat_rejection_power_W = membrane_sorption_heat_rejected_W / sorption_heat_rejection_cop
    else:
        membrane_heat_rejection_power_W = 0.0

    if w_mem > wt + 1e-9:
        # Coil still needs to dehumidify to target humidity ratio.
        T_coil_exit = base["conventional_coil_exit_T_C"]
        h_coil_exit = base["conventional_coil_exit_h_kJ_per_kg_da"]
        cooling_load_W = max(0.0, m_da * (h_after_mem - h_coil_exit) * 1000.0)
        reheat_load_W = max(0.0, m_da * (ht - h_coil_exit) * 1000.0)
        coil_mode = "latent_dehumidifying"
    else:
        # Membrane has reached target humidity ratio; coil is sensible-only unless membrane overcooled the air.
        T_coil_exit = Tt
        h_coil_exit = ht
        cooling_load_W = max(0.0, m_da * (h_after_mem - ht) * 1000.0)
        reheat_load_W = max(0.0, m_da * (ht - h_after_mem) * 1000.0)
        coil_mode = "sensible_only_or_heating"

    cop = simple_cooling_cop(T_coil_exit, approach_K=coil_approach_K, condenser_T_C=condenser_T_C, carnot_eff=carnot_eff)
    compressor_W = cooling_load_W / cop if cooling_load_W > 0 else 0.0
    reheat_purchased_W = reheat_power_W(reheat_load_W, reheat_mode, heat_pump_cop=heat_pump_reheat_cop)
    total_purchased_W = compressor_W + reheat_purchased_W + membrane_electric_power_W + membrane_heat_rejection_power_W
    conv_total = base["conventional_total_purchased_W"]
    savings_pct = 100.0 * (conv_total - total_purchased_W) / max(conv_total, EPS)

    return {
        "f_latent_by_membrane": f,
        "e_p_Wh_per_kg_water": e_p_Wh_per_kg_water,
        "q_sorp_kJ_per_kg_water": q_sorp_kJ_per_kg_water,
        "chi_sorp_to_process_air": chi_sorp,
        "chi_elec_to_process_air": chi_elec,
        "sorption_heat_rejection_cop": sorption_heat_rejection_cop,
        "water_removed_by_membrane_g_per_kg_da": 1000.0 * dw_mem,
        "water_remaining_for_coil_g_per_kg_da": 1000.0 * max(w_mem - wt, 0.0),
        "air_after_membrane_T_C": T_after_mem,
        "air_after_membrane_RH_pct": 100.0 * RH_after_mem,
        "air_after_membrane_w_g_per_kg_da": 1000.0 * w_mem,
        "air_after_membrane_h_kJ_per_kg_da": h_after_mem,
        "air_after_membrane_delta_h_kJ_per_kg_da": h_after_mem - h0,
        "membrane_sorption_heat_total_W": membrane_sorption_heat_total_W,
        "membrane_sorption_heat_to_process_W": membrane_sorption_heat_to_process_W,
        "membrane_sorption_heat_rejected_W": membrane_sorption_heat_rejected_W,
        "membrane_electric_power_W": membrane_electric_power_W,
        "membrane_electric_heat_to_process_W": membrane_electric_heat_to_process_W,
        "membrane_heat_rejection_power_W": membrane_heat_rejection_power_W,
        "coil_mode": coil_mode,
        "hybrid_coil_exit_T_C": T_coil_exit,
        "hybrid_cooling_load_W": cooling_load_W,
        "hybrid_reheat_load_W": reheat_load_W,
        "hybrid_COP": cop,
        "hybrid_compressor_W": compressor_W,
        "hybrid_reheat_purchased_W": reheat_purchased_W,
        "hybrid_total_purchased_W": total_purchased_W,
        "conventional_total_purchased_W": conv_total,
        "savings_pct": savings_pct,
    }


def classify_q_sorp(q_sorp: float, h_fg: float) -> str:
    excess = q_sorp - h_fg
    if excess > 300:
        return "strongly_bound_above_liquid"
    if excess > 75:
        return "bound_or_interfacial"
    if excess > -75:
        return "liquid_like"
    return "weaker_than_liquid_like"


def plot_heatmap(df: pd.DataFrame, out_dir: Path, q_sorp: float, f: float, target_levels: list[float]) -> None:
    sub = df[(df["q_sorp_kJ_per_kg_water"] == q_sorp) & (df["f_latent_by_membrane"] == f)].copy()
    if sub.empty:
        return
    # One heatmap per sorption heat rejection COP and chi_elec. Keep the first combinations compact.
    for (rej_cop, chi_elec), g in sub.groupby(["sorption_heat_rejection_cop", "chi_elec_to_process_air"]):
        pivot = g.pivot_table(index="chi_sorp_to_process_air", columns="e_p_Wh_per_kg_water", values="savings_pct", aggfunc="max")
        if pivot.empty:
            continue
        x = pivot.columns.to_numpy(dtype=float)
        y = pivot.index.to_numpy(dtype=float)
        z = pivot.to_numpy(dtype=float)
        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        im = ax.imshow(
            z,
            origin="lower",
            aspect="auto",
            extent=[x.min(), x.max(), y.min(), y.max()],
            interpolation="nearest",
        )
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("System saving vs conventional [%]")
        finite = np.isfinite(z)
        if finite.any() and len(x) > 1 and len(y) > 1:
            levels = [lev for lev in target_levels if np.nanmin(z) <= lev <= np.nanmax(z)]
            if levels:
                cs = ax.contour(x, y, z, levels=levels)
                ax.clabel(cs, inline=True, fmt="%g%%")
        ax.set_xlabel("EO/ACEO electrical energy, e_p [Wh/kg water]")
        ax.set_ylabel("Fraction of sorption heat to process air, chi_sorp [-]")
        rej_label = "free" if not rej_cop else f"COP{rej_cop:g}"
        ax.set_title(f"Savings with sorption heat, q={q_sorp:g} kJ/kg, f={f:g}, heat rejection={rej_label}")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fname = f"savings_map_q{q_sorp:g}_f{f:g}_rej{rej_label}_chie{chi_elec:g}.png".replace(".", "p")
        fig.savefig(out_dir / fname, dpi=200)
        plt.close(fig)


def make_threshold_table(df: pd.DataFrame, target_savings: list[float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = [
        "reheat_mode",
        "sorption_heat_rejection_cop",
        "q_sorp_kJ_per_kg_water",
        "f_latent_by_membrane",
        "e_p_Wh_per_kg_water",
        "chi_elec_to_process_air",
    ]
    for key, g in df.groupby(group_cols):
        for target in target_savings:
            ok = g[g["savings_pct"] >= target]
            row = dict(zip(group_cols, key))
            row["target_savings_pct"] = target
            if ok.empty:
                row.update(
                    {
                        "max_chi_sorp_to_process_air": np.nan,
                        "min_chi_sorp_to_process_air": np.nan,
                        "best_savings_pct": g["savings_pct"].max(),
                        "air_T_at_max_chi_C": np.nan,
                        "rejected_sorption_heat_W_at_max_chi": np.nan,
                    }
                )
            else:
                # High chi_sorp is easiest thermally but worst for process-air enthalpy; max allowed is key.
                idx = ok["chi_sorp_to_process_air"].idxmax()
                row.update(
                    {
                        "max_chi_sorp_to_process_air": ok.loc[idx, "chi_sorp_to_process_air"],
                        "min_chi_sorp_to_process_air": ok["chi_sorp_to_process_air"].min(),
                        "best_savings_pct": g["savings_pct"].max(),
                        "air_T_at_max_chi_C": ok.loc[idx, "air_after_membrane_T_C"],
                        "rejected_sorption_heat_W_at_max_chi": ok.loc[idx, "membrane_sorption_heat_rejected_W"],
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Model 2.6: system-level EO/ACEO dehumidification with explicit sorption heat balance."
    )
    parser.add_argument("--config", default="scenarios/first_model.yaml")
    parser.add_argument("--out", default="outputs/model2_sorption_heat_balance")
    parser.add_argument("--reheat-modes", nargs="+", default=["free_reheat", "heat_pump_reheat_COP3", "electric_reheat"])
    parser.add_argument("--heat-pump-reheat-cop", type=float, default=3.0)
    parser.add_argument("--coil-approach-K", type=float, default=5.0)
    parser.add_argument("--condenser-T-C", type=float, default=40.0)
    parser.add_argument("--carnot-eff", type=float, default=0.45)

    parser.add_argument("--f-values", nargs="+", type=float, default=[0.25, 0.5, 0.75, 1.0])
    parser.add_argument("--e-p-values", nargs="+", type=float, default=[50, 100, 150, 200, 300])
    parser.add_argument("--chi-elec-values", nargs="+", type=float, default=[0.0, 0.5, 1.0])
    parser.add_argument("--chi-sorp-values", nargs="+", type=float, default=None)
    parser.add_argument("--n-chi-sorp", type=int, default=51)
    parser.add_argument("--q-sorp-values", nargs="+", type=float, default=[2200, 2431, 2600, 2800, 3000])
    parser.add_argument("--add-hydration-surrogate-q", action="store_true")
    parser.add_argument("--bound-water-excess-kJ-kg", type=float, default=300.0)
    parser.add_argument(
        "--sorption-heat-rejection-cops",
        nargs="+",
        type=float,
        default=[0.0],
        help="0 means rejected sorption heat is free/passive. Positive value means active rejection power = Q_rejected/COP.",
    )
    parser.add_argument("--target-savings", nargs="+", type=float, default=[0, 2, 5, 10])
    parser.add_argument("--plot-f-values", nargs="+", type=float, default=[1.0])
    parser.add_argument("--plot-q-values", nargs="+", type=float, default=[2431, 2600, 3000])
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_dir = out_dir / "plots"
    plot_dir.mkdir(exist_ok=True)

    scenario = read_scenario_config(args.config)
    m_da = scenario["dry_air_mass_flow_kg_s"]
    T0 = scenario["start_T_C"]
    RH0 = scenario["start_RH_frac"]
    Tt = scenario["target_T_C"]
    RHt = scenario["target_RH_frac"]

    q_sorp_values = list(args.q_sorp_values)
    q_hydration = q_sorp_surrogate_kJ_per_kg(T0, RH0, args.bound_water_excess_kJ_kg)
    if args.add_hydration_surrogate_q:
        q_sorp_values.append(round(q_hydration, 3))
    # Preserve order while removing duplicates within 0.001.
    q_unique: list[float] = []
    for q in q_sorp_values:
        if not any(abs(q - existing) < 1e-6 for existing in q_unique):
            q_unique.append(q)
    q_sorp_values = q_unique

    if args.chi_sorp_values is None:
        chi_sorp_values = np.linspace(0.0, 1.0, args.n_chi_sorp).tolist()
    else:
        chi_sorp_values = args.chi_sorp_values

    rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    for reheat_mode in args.reheat_modes:
        base = conventional_baseline(
            T0,
            RH0,
            Tt,
            RHt,
            m_da,
            reheat_mode=reheat_mode,
            heat_pump_reheat_cop=args.heat_pump_reheat_cop,
            coil_approach_K=args.coil_approach_K,
            condenser_T_C=args.condenser_T_C,
            carnot_eff=args.carnot_eff,
        )
        baseline_rows.append({"reheat_mode": reheat_mode, **base})
        for f in args.f_values:
            for e_p in args.e_p_values:
                for q_sorp in q_sorp_values:
                    for chi_sorp in chi_sorp_values:
                        for chi_elec in args.chi_elec_values:
                            for rej_cop in args.sorption_heat_rejection_cops:
                                row = hybrid_case(
                                    base,
                                    T0,
                                    RH0,
                                    Tt,
                                    RHt,
                                    m_da,
                                    f_latent_by_membrane=f,
                                    e_p_Wh_per_kg_water=e_p,
                                    q_sorp_kJ_per_kg_water=q_sorp,
                                    chi_sorp=chi_sorp,
                                    chi_elec=chi_elec,
                                    reheat_mode=reheat_mode,
                                    heat_pump_reheat_cop=args.heat_pump_reheat_cop,
                                    sorption_heat_rejection_cop=rej_cop,
                                    coil_approach_K=args.coil_approach_K,
                                    condenser_T_C=args.condenser_T_C,
                                    carnot_eff=args.carnot_eff,
                                )
                                row.update(
                                    {
                                        "reheat_mode": reheat_mode,
                                        "dry_air_mass_flow_kg_s": m_da,
                                        "start_T_C": T0,
                                        "start_RH_pct": 100.0 * RH0,
                                        "target_T_C": Tt,
                                        "target_RH_pct": 100.0 * RHt,
                                        "start_lambda_zawodzinski": lambda_zawodzinski_vapour(RH0),
                                        "target_lambda_zawodzinski": lambda_zawodzinski_vapour(RHt),
                                        "start_bound_fraction_nafion117_approx": bound_fraction_nafion117_from_RH(RH0),
                                        "target_bound_fraction_nafion117_approx": bound_fraction_nafion117_from_RH(RHt),
                                        "q_sorp_class": classify_q_sorp(q_sorp, latent_heat_kJ_per_kg(T0)),
                                        "q_sorp_hydration_surrogate_kJ_per_kg": q_hydration,
                                    }
                                )
                                rows.append(row)

    sweep = pd.DataFrame(rows)
    baselines = pd.DataFrame(baseline_rows)
    thresholds = make_threshold_table(sweep, args.target_savings)

    sweep.to_csv(out_dir / "sorption_heat_balance_sweep.csv", index=False)
    baselines.to_csv(out_dir / "conventional_baselines.csv", index=False)
    thresholds.to_csv(out_dir / "max_chi_sorp_for_savings.csv", index=False)

    # Compact decision slices: full latent removal, free reheat, passive heat rejection, chi_elec=0.5
    compact = thresholds[
        (thresholds["f_latent_by_membrane"].isin([1.0, 0.5, 0.25]))
        & (thresholds["target_savings_pct"].isin([5.0, 10.0]))
        & (thresholds["chi_elec_to_process_air"].isin([0.5]))
    ].copy()
    compact.to_csv(out_dir / "decision_thresholds_compact.csv", index=False)

    # Plots.
    for q in args.plot_q_values:
        # choose nearest q in available values, useful if h_fg is 2431.2 not exactly 2431
        if not q_sorp_values:
            continue
        q_actual = min(q_sorp_values, key=lambda x: abs(x - q))
        for f in args.plot_f_values:
            plot_heatmap(sweep, plot_dir, q_actual, f, [2, 5, 10])

    # Heat breakdown plot for full removal at selected q/e_p.
    selected = sweep[
        (sweep["reheat_mode"] == args.reheat_modes[0])
        & (sweep["f_latent_by_membrane"] == 1.0)
        & (sweep["chi_elec_to_process_air"] == args.chi_elec_values[min(1, len(args.chi_elec_values)-1)])
        & (sweep["sorption_heat_rejection_cop"] == args.sorption_heat_rejection_cops[0])
    ].copy()
    if not selected.empty:
        # Pick nearest q to hfg and e_p=100 if available.
        q_pick = min(q_sorp_values, key=lambda x: abs(x - latent_heat_kJ_per_kg(T0)))
        e_pick = min(args.e_p_values, key=lambda x: abs(x - 100.0))
        g = selected[(selected["q_sorp_kJ_per_kg_water"] == q_pick) & (selected["e_p_Wh_per_kg_water"] == e_pick)].sort_values("chi_sorp_to_process_air")
        if not g.empty:
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.plot(g["chi_sorp_to_process_air"], g["savings_pct"], marker="o", label="system saving")
            ax.axhline(0, linestyle="--")
            ax.axhline(5, linestyle=":")
            ax.axhline(10, linestyle=":")
            ax.set_xlabel("Fraction of sorption heat to process air, chi_sorp [-]")
            ax.set_ylabel("Saving vs conventional [%]")
            ax.set_title(f"Sensitivity to sorption heat placement, q={q_pick:g} kJ/kg, e_p={e_pick:g} Wh/kg, f=1")
            ax.grid(True, alpha=0.3)
            ax.legend()
            fig.tight_layout()
            fig.savefig(plot_dir / "savings_vs_chi_sorp_full_removal.png", dpi=200)
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(8, 5))
            ax.plot(g["chi_sorp_to_process_air"], g["air_after_membrane_T_C"], marker="o")
            ax.axhline(T0, linestyle="--", label="start T")
            ax.axhline(Tt, linestyle=":", label="target T")
            ax.set_xlabel("Fraction of sorption heat to process air, chi_sorp [-]")
            ax.set_ylabel("Air temperature after membrane [C]")
            ax.set_title("Sorption heat to process air heats the dehumidified air")
            ax.grid(True, alpha=0.3)
            ax.legend()
            fig.tight_layout()
            fig.savefig(plot_dir / "air_T_after_membrane_vs_chi_sorp_full_removal.png", dpi=200)
            plt.close(fig)

    # Report.
    w0 = humidity_ratio_from_T_RH(T0, RH0)
    wt = humidity_ratio_from_T_RH(Tt, RHt)
    h0 = moist_air_enthalpy_kJ_per_kg_da(T0, w0)
    ht = moist_air_enthalpy_kJ_per_kg_da(Tt, wt)
    total_dw = max(w0 - wt, 0.0)
    h_v = water_vapour_enthalpy_kJ_per_kg(T0)
    h_l = liquid_water_enthalpy_kJ_per_kg(T0)
    hfg = latent_heat_kJ_per_kg(T0)
    q_full_hfg_W = m_da * total_dw * hfg * 1000.0
    eo_100_W = m_da * total_dw * 100.0 * 3600.0

    report: list[str] = []
    report.append("# Model 2.6 sorption heat balance")
    report.append("")
    report.append("This run adds a separate sorption-heat balance to the EO/ACEO dehumidification model.")
    report.append("")
    report.append("## Scenario")
    report.append("")
    report.append(f"- Dry-air flow: {m_da:.4g} kg_da/s")
    report.append(f"- Start: {T0:.2f} C, RH={100*RH0:.1f} %, w={1000*w0:.3f} g/kg_da, h={h0:.3f} kJ/kg_da")
    report.append(f"- Target: {Tt:.2f} C, RH={100*RHt:.1f} %, w={1000*wt:.3f} g/kg_da, h={ht:.3f} kJ/kg_da")
    report.append(f"- Water to remove: {1000*total_dw:.3f} g/kg_da = {m_da*total_dw*3600:.3f} kg/h")
    report.append("")
    report.append("## Water and membrane priors")
    report.append("")
    report.append(f"- Water vapour enthalpy at inlet T: {h_v:.1f} kJ/kg")
    report.append(f"- Liquid water enthalpy at inlet T: {h_l:.1f} kJ/kg")
    report.append(f"- h_fg at inlet T: {hfg:.1f} kJ/kg")
    report.append(f"- Zawodzinski lambda at inlet RH: {lambda_zawodzinski_vapour(RH0):.2f}")
    report.append(f"- Zawodzinski lambda at target RH: {lambda_zawodzinski_vapour(RHt):.2f}")
    report.append(f"- Approx. Nafion 117 bound-water fraction at inlet RH: {bound_fraction_nafion117_from_RH(RH0):.2f}")
    report.append(f"- Hydration-surrogate q_sorp: {q_hydration:.1f} kJ/kg")
    report.append("")
    report.append("## Heat scale check")
    report.append("")
    report.append(f"- Full-removal sorption heat if q_sorp=h_fg: {q_full_hfg_W:.1f} W for this dry-air flow")
    report.append(f"- Full-removal EO electrical power at e_p=100 Wh/kg_water: {eo_100_W:.1f} W")
    if eo_100_W > 0:
        report.append(f"- Sorption heat / EO power at e_p=100 Wh/kg: {q_full_hfg_W / eo_100_W:.2f}x")
    report.append("")
    report.append("## Conventional baselines")
    report.append("")
    report.append("```text")
    report.append(baselines[["reheat_mode", "conventional_total_purchased_W", "conventional_cooling_load_W", "conventional_reheat_load_W", "conventional_COP"]].to_string(index=False))
    report.append("```")
    report.append("")
    report.append("## Compact decision thresholds")
    report.append("")
    report.append("`max_chi_sorp_to_process_air` is the largest fraction of sorption heat that can return to the process air while still meeting the saving target on the grid.")
    report.append("")
    compact_view = compact[
        (compact["reheat_mode"] == args.reheat_modes[0])
        & (compact["sorption_heat_rejection_cop"] == args.sorption_heat_rejection_cops[0])
    ].copy()
    if not compact_view.empty:
        cols = [
            "q_sorp_kJ_per_kg_water",
            "f_latent_by_membrane",
            "e_p_Wh_per_kg_water",
            "target_savings_pct",
            "max_chi_sorp_to_process_air",
            "best_savings_pct",
        ]
        report.append("```text")
        report.append(compact_view[cols].sort_values(cols[:4]).to_string(index=False))
        report.append("```")
    else:
        report.append("No compact rows found for the selected default slices.")
    report.append("")
    report.append("## Key output files")
    report.append("")
    report.append("- `sorption_heat_balance_sweep.csv`")
    report.append("- `max_chi_sorp_for_savings.csv`")
    report.append("- `decision_thresholds_compact.csv`")
    report.append("- `conventional_baselines.csv`")
    report.append("- `plots/`")
    report.append("")
    report.append("## Interpretation")
    report.append("")
    report.append("If `max_chi_sorp_to_process_air` is low, the membrane concept requires efficient rejection of sorption heat away from the process air.")
    report.append("If it is high, the process can tolerate sorption heat returning to the supply air, usually because EO/ACEO takes a small latent fraction or because the downstream coil can remove the added sensible load efficiently.")

    (out_dir / "sorption_heat_balance_report.md").write_text("\n".join(report), encoding="utf-8")

    print(f"Wrote Model 2.6 sorption heat balance outputs to: {out_dir}")
    print()
    print((out_dir / "sorption_heat_balance_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
