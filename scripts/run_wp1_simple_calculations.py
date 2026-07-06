from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

P_ATM_PA = 101_325.0
R_V_KJ_PER_KG_K = 0.4615
R_DA = 287.055


def saturation_pressure_water_pa(T_C: float) -> float:
    """Buck saturation pressure over liquid water, Pa."""
    return 611.21 * math.exp((18.678 - T_C / 234.5) * (T_C / (257.14 + T_C)))


def humidity_ratio_from_T_RH(T_C: float, RH_frac: float, p_atm_pa: float = P_ATM_PA) -> float:
    p_ws = saturation_pressure_water_pa(T_C)
    p_w = RH_frac * p_ws
    return 0.621945 * p_w / (p_atm_pa - p_w)


def RH_from_T_w(T_C: float, w: float, p_atm_pa: float = P_ATM_PA) -> float:
    p_w = p_atm_pa * w / (0.621945 + w)
    return p_w / saturation_pressure_water_pa(T_C)


def moist_air_enthalpy_kJ_per_kg_da(T_C: float, w_kg_per_kg_da: float) -> float:
    # ASHRAE-style reference: dry air at 0 C and liquid water at 0 C.
    return 1.006 * T_C + w_kg_per_kg_da * (2501.0 + 1.86 * T_C)


def water_vapour_enthalpy_kJ_per_kg(T_C: float) -> float:
    return 2501.0 + 1.86 * T_C


def dewpoint_from_w_C(w_kg_per_kg_da: float) -> float:
    lo, hi = -40.0, 80.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if humidity_ratio_from_T_RH(mid, 1.0) < w_kg_per_kg_da:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def specific_volume_m3_per_kg_da(T_C: float, w_kg_per_kg_da: float) -> float:
    T_K = T_C + 273.15
    return R_DA * T_K * (1.0 + 1.607858 * w_kg_per_kg_da) / P_ATM_PA


def carnot_scaled_COP(COP_base: float, evap_base_C: float, evap_new_C: float, condenser_C: float) -> float:
    T_c_base = evap_base_C + 273.15
    T_c_new = evap_new_C + 273.15
    T_h = condenser_C + 273.15
    carnot_base = T_c_base / (T_h - T_c_base)
    carnot_new = T_c_new / (T_h - T_c_new)
    return COP_base * carnot_new / carnot_base


def make_state(T_C: float, RH_frac: float, label: str) -> dict[str, float | str]:
    w = humidity_ratio_from_T_RH(T_C, RH_frac)
    h = moist_air_enthalpy_kJ_per_kg_da(T_C, w)
    return {
        "state": label,
        "T_C": T_C,
        "RH_pct": 100.0 * RH_frac,
        "w_g_per_kg_da": 1000.0 * w,
        "h_kJ_per_kg_da": h,
        "dewpoint_C": dewpoint_from_w_C(w),
        "specific_volume_m3_per_kg_da": specific_volume_m3_per_kg_da(T_C, w),
    }


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in value)


def df_to_latex_tabular(df: pd.DataFrame, cols: list[str], headers: list[str], floatfmt: dict[str, str] | None = None) -> str:
    floatfmt = floatfmt or {}
    lines: list[str] = []
    lines.append(r"\begin{tabular}{" + "l" + "r" * (len(cols) - 1) + "}")
    lines.append(r"\toprule")
    lines.append(" & ".join(headers) + r" \\")
    lines.append(r"\midrule")
    for _, row in df[cols].iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, (float, np.floating)):
                fmt = floatfmt.get(c, ".2f")
                vals.append(format(float(v), fmt))
            else:
                vals.append(latex_escape(str(v)))
        lines.append(" & ".join(vals) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def plot_psychrometric(states_df: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    T_grid = np.linspace(10, 40, 300)
    for RH in [0.2, 0.3, 0.5, 0.8, 1.0]:
        w_curve = [1000.0 * humidity_ratio_from_T_RH(T, RH) for T in T_grid]
        ax.plot(T_grid, w_curve, linewidth=1.0)
        idx = -35 if RH < 1 else -60
        ax.text(T_grid[idx], w_curve[idx], f"{int(100*RH)}% RH", fontsize=8)

    for _, row in states_df.iterrows():
        ax.scatter(row["T_C"], row["w_g_per_kg_da"], s=60)
        ax.annotate(
            row["state"],
            (row["T_C"], row["w_g_per_kg_da"]),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=9,
        )

    # Draw main path arrows: 32C80 -> 32C50/30 -> target
    baseline = states_df[states_df["state"] == "Baseline inlet: 32C, 80% RH"].iloc[0]
    target = states_df[states_df["state"] == "Target: 22C, 50% RH"].iloc[0]
    for label in ["Pre-dried: 32C, 50% RH", "Pre-dried: 32C, 30% RH"]:
        pred = states_df[states_df["state"] == label].iloc[0]
        ax.plot([baseline["T_C"], pred["T_C"]], [baseline["w_g_per_kg_da"], pred["w_g_per_kg_da"]], linestyle="--")
        ax.plot([pred["T_C"], target["T_C"]], [pred["w_g_per_kg_da"], target["w_g_per_kg_da"]], linestyle="-")
    ax.plot([baseline["T_C"], target["T_C"]], [baseline["w_g_per_kg_da"], target["w_g_per_kg_da"]], linestyle=":", linewidth=1.5)

    ax.set_xlabel("Dry-bulb temperature [C]")
    ax.set_ylabel("Humidity ratio [g/kg dry air]")
    ax.set_title("Simple psychrometric points for WP1 pre-drying cases")
    ax.set_xlim(10, 40)
    ax.set_ylim(0, 32)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_cooling_power(load_df: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    subset = load_df[load_df["COP_case"] == "fixed_COP_3"].copy()
    labels = subset["case"].tolist()
    values = subset["downstream_cooling_purchased_kW"].tolist()
    ax.bar(range(len(values)), values)
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("Purchased cooling power [kW per kg_da/s]")
    ax.set_title("Downstream HVAC purchased power at COP=3")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_ep_budget(threshold_df: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    sub = threshold_df[threshold_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"])]
    x = np.arange(len(sub))
    ax.bar(x, sub["break_even_e_p_Wh_per_kg_water"])
    ax.set_xticks(x)
    ax.set_xticklabels(sub["case"] + "\n" + sub["COP_case"], rotation=0)
    ax.set_ylabel("Break-even EO energy [Wh/kg water]")
    ax.set_title("Maximum EO energy before pre-drying loses its cooling-power saving")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_heat_rejection(heat_df: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    sub = heat_df[heat_df["q_sorp_kJ_per_kg_water"] == 2431.0].copy()
    x = np.arange(len(sub))
    ax.bar(x, sub["sorption_heat_kW"])
    ax.set_xticks(x)
    ax.set_xticklabels(sub["case"], rotation=15, ha="right")
    ax.set_ylabel("Sorption heat [kW per kg_da/s]")
    ax.set_title("Heat that must be managed if q_sorp ≈ h_fg")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="WP1 simple calculations for Gree/EO pre-drying feasibility.")
    parser.add_argument("--out", default="outputs/wp1_simple_calculations")
    parser.add_argument("--dry-air-flow-kg-s", type=float, default=1.0)
    parser.add_argument("--inlet-T-C", type=float, default=32.0)
    parser.add_argument("--baseline-RH", type=float, default=0.80)
    parser.add_argument("--predry-RH-values", type=float, nargs="+", default=[0.50, 0.30])
    parser.add_argument("--target-T-C", type=float, default=22.0)
    parser.add_argument("--target-RH", type=float, default=0.50)
    parser.add_argument("--COP-values", type=float, nargs="+", default=[3.0, 5.0])
    parser.add_argument("--base-evap-C", type=float, default=7.0)
    parser.add_argument("--predry-evap-C-values", type=float, nargs="+", default=[12.0, 15.0])
    parser.add_argument("--condenser-C", type=float, default=40.0)
    parser.add_argument("--e-p-values", type=float, nargs="+", default=[25, 50, 100, 150, 200])
    parser.add_argument("--q-sorp-values", type=float, nargs="+", default=[2200.0, 2431.0, 2600.0])
    parser.add_argument("--flux-values", type=float, nargs="+", default=[500, 1000, 3000, 5000, 10000])
    args = parser.parse_args()

    out_dir = Path(args.out)
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # Psychrometric state table
    states = []
    baseline_label = f"Baseline inlet: {args.inlet_T_C:g}C, {100*args.baseline_RH:g}% RH"
    states.append(make_state(args.inlet_T_C, args.baseline_RH, baseline_label))
    for rh in args.predry_RH_values:
        states.append(make_state(args.inlet_T_C, rh, f"Pre-dried: {args.inlet_T_C:g}C, {100*rh:g}% RH"))
    target_label = f"Target: {args.target_T_C:g}C, {100*args.target_RH:g}% RH"
    states.append(make_state(args.target_T_C, args.target_RH, target_label))
    states_df = pd.DataFrame(states)
    states_df.to_csv(out_dir / "psychrometric_state_table.csv", index=False)

    baseline = states_df.iloc[0]
    target = states_df.iloc[-1]
    h_base = float(baseline["h_kJ_per_kg_da"])
    w_base = float(baseline["w_g_per_kg_da"]) / 1000.0
    h_target = float(target["h_kJ_per_kg_da"])
    w_target = float(target["w_g_per_kg_da"]) / 1000.0

    # Cooling power and savings
    load_rows = []
    threshold_rows = []
    eo_rows = []
    heat_rows = []
    area_rows = []

    case_states = states_df.iloc[:-1]
    baseline_load_kW = args.dry_air_flow_kg_s * (h_base - h_target)

    for _, state in case_states.iterrows():
        case = str(state["state"])
        h_case = float(state["h_kJ_per_kg_da"])
        w_case = float(state["w_g_per_kg_da"]) / 1000.0
        downstream_load_kW = args.dry_air_flow_kg_s * max(h_case - h_target, 0.0)
        remaining_water_kg_h = args.dry_air_flow_kg_s * max(w_case - w_target, 0.0) * 3600.0
        predry_water_kg_h = args.dry_air_flow_kg_s * max(w_base - w_case, 0.0) * 3600.0
        load_avoided_kW = baseline_load_kW - downstream_load_kW

        for COP in args.COP_values:
            P_downstream = downstream_load_kW / COP
            P_baseline = baseline_load_kW / COP
            saved_kW = P_baseline - P_downstream
            load_rows.append({
                "case": case,
                "COP_case": f"fixed_COP_{COP:g}",
                "COP_used": COP,
                "downstream_cooling_load_kW": downstream_load_kW,
                "downstream_cooling_purchased_kW": P_downstream,
                "saved_purchased_power_vs_baseline_kW": saved_kW,
                "saving_pct_if_predrying_free": 100.0 * saved_kW / P_baseline if P_baseline > 0 else 0.0,
                "remaining_water_to_target_kg_h": remaining_water_kg_h,
                "water_removed_by_predrying_kg_h": predry_water_kg_h,
            })

            if predry_water_kg_h > 0:
                mdot_w = predry_water_kg_h / 3600.0
                e_p_break_even = (saved_kW * 1000.0) / (mdot_w * 3600.0)
                threshold_rows.append({
                    "case": case,
                    "COP_case": f"fixed_COP_{COP:g}",
                    "COP_used": COP,
                    "water_removed_by_predrying_kg_h": predry_water_kg_h,
                    "saved_purchased_power_vs_baseline_kW": saved_kW,
                    "break_even_e_p_Wh_per_kg_water": e_p_break_even,
                })
                for ep in args.e_p_values:
                    P_eo_kW = ep * mdot_w * 3600.0 / 1000.0
                    net_saving_kW = saved_kW - P_eo_kW
                    eo_rows.append({
                        "case": case,
                        "COP_case": f"fixed_COP_{COP:g}",
                        "e_p_Wh_per_kg_water": ep,
                        "EO_power_kW": P_eo_kW,
                        "net_saving_after_EO_only_kW": net_saving_kW,
                        "net_saving_after_EO_only_pct_of_baseline": 100.0 * net_saving_kW / P_baseline,
                    })

        # COP-adjusted cases for pre-dried states only
        if predry_water_kg_h > 0:
            for COP_base in args.COP_values:
                P_baseline = baseline_load_kW / COP_base
                for evap_new in args.predry_evap_C_values:
                    COP_adj = carnot_scaled_COP(COP_base, args.base_evap_C, evap_new, args.condenser_C)
                    P_downstream_adj = downstream_load_kW / COP_adj
                    saved_kW_adj = P_baseline - P_downstream_adj
                    load_rows.append({
                        "case": case,
                        "COP_case": f"COP{COP_base:g}_scaled_evap_{evap_new:g}C",
                        "COP_used": COP_adj,
                        "downstream_cooling_load_kW": downstream_load_kW,
                        "downstream_cooling_purchased_kW": P_downstream_adj,
                        "saved_purchased_power_vs_baseline_kW": saved_kW_adj,
                        "saving_pct_if_predrying_free": 100.0 * saved_kW_adj / P_baseline if P_baseline > 0 else 0.0,
                        "remaining_water_to_target_kg_h": remaining_water_kg_h,
                        "water_removed_by_predrying_kg_h": predry_water_kg_h,
                    })
                    mdot_w = predry_water_kg_h / 3600.0
                    e_p_break_even = (saved_kW_adj * 1000.0) / (mdot_w * 3600.0)
                    threshold_rows.append({
                        "case": case,
                        "COP_case": f"COP{COP_base:g}_scaled_evap_{evap_new:g}C",
                        "COP_used": COP_adj,
                        "water_removed_by_predrying_kg_h": predry_water_kg_h,
                        "saved_purchased_power_vs_baseline_kW": saved_kW_adj,
                        "break_even_e_p_Wh_per_kg_water": e_p_break_even,
                    })

        if predry_water_kg_h > 0:
            mdot_w = predry_water_kg_h / 3600.0
            for q_sorp in args.q_sorp_values:
                Q_sorp_kW = mdot_w * q_sorp
                heat_rows.append({
                    "case": case,
                    "q_sorp_kJ_per_kg_water": q_sorp,
                    "water_removed_by_predrying_kg_h": predry_water_kg_h,
                    "sorption_heat_kW": Q_sorp_kW,
                    "active_heat_rejection_power_if_COP3_kW": Q_sorp_kW / 3.0,
                })
            for flux in args.flux_values:
                area_m2 = 1000.0 * predry_water_kg_h / flux
                area_rows.append({
                    "case": case,
                    "flux_g_m2_h": flux,
                    "water_removed_by_predrying_kg_h": predry_water_kg_h,
                    "required_membrane_area_m2": area_m2,
                })

    load_df = pd.DataFrame(load_rows)
    threshold_df = pd.DataFrame(threshold_rows)
    eo_df = pd.DataFrame(eo_rows)
    heat_df = pd.DataFrame(heat_rows)
    area_df = pd.DataFrame(area_rows)
    load_df.to_csv(out_dir / "cooling_power_and_savings.csv", index=False)
    threshold_df.to_csv(out_dir / "eo_break_even_thresholds.csv", index=False)
    eo_df.to_csv(out_dir / "eo_power_net_savings.csv", index=False)
    heat_df.to_csv(out_dir / "heat_rejection_requirements.csv", index=False)
    area_df.to_csv(out_dir / "flux_area_requirements.csv", index=False)

    # Gibbs/activity scale estimates
    gibbs_rows = []
    T_K = args.inlet_T_C + 273.15
    for rh in args.predry_RH_values:
        g_kJ_kg = R_V_KJ_PER_KG_K * T_K * math.log(args.baseline_RH / rh)
        gibbs_rows.append({
            "activity_ratio": f"{args.baseline_RH:g}/{rh:g}",
            "T_C": args.inlet_T_C,
            "g_min_kJ_per_kg_water": g_kJ_kg,
            "g_min_Wh_per_kg_water": g_kJ_kg / 3.6,
        })
    gibbs_df = pd.DataFrame(gibbs_rows)
    gibbs_df.to_csv(out_dir / "gibbs_activity_scale.csv", index=False)

    # Figures
    plot_psychrometric(states_df, fig_dir / "wp1_psychrometric_points.png")
    plot_cooling_power(load_df, fig_dir / "wp1_cooling_power_COP3.png")
    if not threshold_df.empty:
        plot_ep_budget(threshold_df[threshold_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"])], fig_dir / "wp1_ep_break_even.png")
    if not heat_df.empty:
        plot_heat_rejection(heat_df, fig_dir / "wp1_sorption_heat.png")

    # LaTeX tables for inclusion
    state_tex = df_to_latex_tabular(
        states_df,
        ["state", "T_C", "RH_pct", "w_g_per_kg_da", "h_kJ_per_kg_da", "dewpoint_C"],
        ["State", "$T$", "RH", "$w$", "$h$", "$T_{dew}$"],
        {"T_C": ".1f", "RH_pct": ".0f", "w_g_per_kg_da": ".2f", "h_kJ_per_kg_da": ".2f", "dewpoint_C": ".2f"},
    )

    simple_load = load_df[load_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"])].copy()
    load_tex = df_to_latex_tabular(
        simple_load,
        ["case", "COP_case", "downstream_cooling_load_kW", "downstream_cooling_purchased_kW", "saved_purchased_power_vs_baseline_kW", "saving_pct_if_predrying_free", "water_removed_by_predrying_kg_h"],
        ["Case", "COP", "$Q_{down}$", "$P_{down}$", "$P_{saved}$", "Saving", r"$\dot m_w$"],
        {"downstream_cooling_load_kW": ".2f", "downstream_cooling_purchased_kW": ".2f", "saved_purchased_power_vs_baseline_kW": ".2f", "saving_pct_if_predrying_free": ".1f", "water_removed_by_predrying_kg_h": ".2f"},
    )

    threshold_simple = threshold_df[threshold_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"])].copy()
    threshold_tex = df_to_latex_tabular(
        threshold_simple,
        ["case", "COP_case", "water_removed_by_predrying_kg_h", "saved_purchased_power_vs_baseline_kW", "break_even_e_p_Wh_per_kg_water"],
        ["Case", "COP", r"$\dot m_w$", "$P_{saved}$", "$e_{p,max}$"],
        {"water_removed_by_predrying_kg_h": ".2f", "saved_purchased_power_vs_baseline_kW": ".2f", "break_even_e_p_Wh_per_kg_water": ".0f"},
    )

    gibbs_tex = df_to_latex_tabular(
        gibbs_df,
        ["activity_ratio", "T_C", "g_min_kJ_per_kg_water", "g_min_Wh_per_kg_water"],
        ["Activity ratio", "$T$", "$g_{min}$", "$g_{min}$"],
        {"T_C": ".1f", "g_min_kJ_per_kg_water": ".1f", "g_min_Wh_per_kg_water": ".1f"},
    )

    heat_tex = df_to_latex_tabular(
        heat_df[heat_df["q_sorp_kJ_per_kg_water"] == 2431.0],
        ["case", "water_removed_by_predrying_kg_h", "q_sorp_kJ_per_kg_water", "sorption_heat_kW", "active_heat_rejection_power_if_COP3_kW"],
        ["Case", r"$\dot m_w$", "$q_{sorp}$", "$Q_{sorp}$", "$P_{reject,COP3}$"],
        {"water_removed_by_predrying_kg_h": ".2f", "q_sorp_kJ_per_kg_water": ".0f", "sorption_heat_kW": ".2f", "active_heat_rejection_power_if_COP3_kW": ".2f"},
    )

    area_tex = df_to_latex_tabular(
        area_df[area_df["flux_g_m2_h"].isin([1000.0, 3000.0, 10000.0])],
        ["case", "flux_g_m2_h", "required_membrane_area_m2"],
        ["Case", "$J_w$", "$A_m$"],
        {"flux_g_m2_h": ".0f", "required_membrane_area_m2": ".2f"},
    )

    (out_dir / "wp1_simple_tables.tex").write_text(
        "\n\n".join([
            "% Auto-generated by scripts/run_wp1_simple_calculations.py",
            "\\newcommand{\\DryAirFlow}{" + f"{args.dry_air_flow_kg_s:g}" + "}",
            "\\newcommand{\\BaselineLoad}{" + f"{baseline_load_kW:.2f}" + "}",
            "\\newcommand{\\StateTable}{%\n" + state_tex + "\n}",
            "\\newcommand{\\LoadTable}{%\n" + load_tex + "\n}",
            "\\newcommand{\\ThresholdTable}{%\n" + threshold_tex + "\n}",
            "\\newcommand{\\GibbsTable}{%\n" + gibbs_tex + "\n}",
            "\\newcommand{\\HeatTable}{%\n" + heat_tex + "\n}",
            "\\newcommand{\\AreaTable}{%\n" + area_tex + "\n}",
        ]),
        encoding="utf-8",
    )

    # Markdown report
    report = []
    report.append("# WP1 simple pre-drying calculations")
    report.append("")
    report.append(f"Dry-air flow: {args.dry_air_flow_kg_s:g} kg_da/s")
    report.append("")
    report.append("## Psychrometric states")
    report.append("")
    report.append(states_df.to_string(index=False))
    report.append("")
    report.append("## Cooling power and savings")
    report.append("")
    report.append(simple_load.to_string(index=False))
    report.append("")
    report.append("## Break-even EO energy")
    report.append("")
    report.append(threshold_simple.to_string(index=False))
    report.append("")
    report.append("## Gibbs/activity separation scale")
    report.append("")
    report.append(gibbs_df.to_string(index=False))
    report.append("")
    report.append("## Heat rejection requirements")
    report.append("")
    report.append(heat_df.to_string(index=False))
    report.append("")
    report.append("## Flux/area requirements")
    report.append("")
    report.append(area_df.to_string(index=False))
    (out_dir / "wp1_simple_report.md").write_text("\n".join(report), encoding="utf-8")

    print(f"Wrote results to: {out_dir}")
    print((out_dir / "wp1_simple_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
