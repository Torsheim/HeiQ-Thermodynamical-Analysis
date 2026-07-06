from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def read_csv_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def parse_predry_rh_from_case(case: str) -> float | None:
    """
    Extract RH fraction from labels like:
      'Pre-dried: 32C, 50% RH'
    """
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)%\s*RH", case)
    if not m:
        return None
    return float(m.group(1)) / 100.0


def baseline_purchased_by_cop_case(load_df: pd.DataFrame) -> dict[str, float]:
    """
    For each COP_case, infer baseline purchased power from rows that contain
    saved_purchased_power_vs_baseline and saving_pct_if_predrying_free.
    """
    out: dict[str, float] = {}

    for cop_case, g in load_df.groupby("COP_case"):
        # Direct baseline row is easiest.
        baseline_rows = g[g["water_removed_by_predrying_kg_h"].abs() < 1e-12]
        if not baseline_rows.empty:
            out[cop_case] = float(baseline_rows.iloc[0]["downstream_cooling_purchased_kW"])
            continue

        # Otherwise infer from saved and percent.
        gg = g[g["saving_pct_if_predrying_free"].abs() > 1e-9].copy()
        if gg.empty:
            continue
        inferred = (
            gg["saved_purchased_power_vs_baseline_kW"]
            / (gg["saving_pct_if_predrying_free"] / 100.0)
        )
        out[cop_case] = float(np.nanmedian(inferred))

    return out


def make_stage_gate_rows(
    threshold_df: pd.DataFrame,
    load_df: pd.DataFrame,
    heat_df: pd.DataFrame,
    candidate_ep: list[float],
    heat_active_fractions: list[float],
    extra_fan_kW_values: list[float],
    heat_rejection_COP: float,
    q_sorp_values: list[float] | None,
) -> pd.DataFrame:
    baseline_map = baseline_purchased_by_cop_case(load_df)

    heat_lookup = {}
    for _, row in heat_df.iterrows():
        key = (
            str(row["case"]),
            float(row["q_sorp_kJ_per_kg_water"]),
        )
        heat_lookup[key] = float(row["sorption_heat_kW"])

    rows = []

    for _, row in threshold_df.iterrows():
        case = str(row["case"])
        cop_case = str(row["COP_case"])
        water_kg_h = float(row["water_removed_by_predrying_kg_h"])
        saved_kW = float(row["saved_purchased_power_vs_baseline_kW"])
        ep_max_simple = float(row["break_even_e_p_Wh_per_kg_water"])
        baseline_kW = baseline_map.get(cop_case, np.nan)

        if water_kg_h <= 0:
            continue

        available_qs = sorted(
            float(q)
            for (c, q), _v in heat_lookup.items()
            if c == case
        )
        if q_sorp_values is not None:
            available_qs = [q for q in available_qs if q in set(q_sorp_values)]

        for q_sorp in available_qs:
            sorption_heat_kW = heat_lookup[(case, q_sorp)]

            for active_fraction in heat_active_fractions:
                thermal_penalty_kW = active_fraction * sorption_heat_kW / heat_rejection_COP

                for extra_fan_kW in extra_fan_kW_values:
                    ep_max_after_penalties = (
                        max(saved_kW - thermal_penalty_kW - extra_fan_kW, 0.0)
                        * 1000.0
                        / water_kg_h
                    )

                    for ep in candidate_ep:
                        eo_kW = ep * water_kg_h / 1000.0
                        net_kW = saved_kW - eo_kW - thermal_penalty_kW - extra_fan_kW
                        net_pct = 100.0 * net_kW / baseline_kW if baseline_kW > 0 else np.nan

                        rows.append(
                            {
                                "case": case,
                                "predry_RH_frac": parse_predry_rh_from_case(case),
                                "COP_case": cop_case,
                                "COP_used": float(row["COP_used"]),
                                "baseline_purchased_kW": baseline_kW,
                                "water_removed_by_predrying_kg_h": water_kg_h,
                                "saved_purchased_power_vs_baseline_kW": saved_kW,
                                "q_sorp_kJ_per_kg_water": q_sorp,
                                "sorption_heat_kW": sorption_heat_kW,
                                "active_heat_fraction": active_fraction,
                                "heat_rejection_COP": heat_rejection_COP,
                                "thermal_penalty_kW": thermal_penalty_kW,
                                "extra_fan_power_kW": extra_fan_kW,
                                "e_p_Wh_per_kg_water": ep,
                                "EO_power_kW": eo_kW,
                                "net_saving_kW": net_kW,
                                "net_saving_pct_of_baseline": net_pct,
                                "simple_break_even_e_p_Wh_per_kg_water": ep_max_simple,
                                "penalized_break_even_e_p_Wh_per_kg_water": ep_max_after_penalties,
                                "passes_stage_gate": net_kW > 0.0,
                                "passes_5pct_net_saving": net_pct >= 5.0 if np.isfinite(net_pct) else False,
                                "passes_10pct_net_saving": net_pct >= 10.0 if np.isfinite(net_pct) else False,
                            }
                        )

    return pd.DataFrame(rows)


def make_summary_tables(stage_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compact tables:
    1. Best candidate rows by case/COP/q/thermal/fan.
    2. Break-even e_p by case/COP/q/thermal/fan.
    """
    group_cols = [
        "case",
        "COP_case",
        "q_sorp_kJ_per_kg_water",
        "active_heat_fraction",
        "extra_fan_power_kW",
    ]

    best = (
        stage_df.sort_values(
            group_cols + ["net_saving_pct_of_baseline", "e_p_Wh_per_kg_water"],
            ascending=[True, True, True, True, True, False, True],
        )
        .drop_duplicates(group_cols)
        .reset_index(drop=True)
    )

    breakeven = (
        stage_df[group_cols + [
            "COP_used",
            "water_removed_by_predrying_kg_h",
            "saved_purchased_power_vs_baseline_kW",
            "sorption_heat_kW",
            "thermal_penalty_kW",
            "penalized_break_even_e_p_Wh_per_kg_water",
        ]]
        .drop_duplicates(group_cols)
        .sort_values(group_cols)
        .reset_index(drop=True)
    )

    return best, breakeven


def make_plots(stage_df: pd.DataFrame, out_dir: Path) -> None:
    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Plot break-even e_p for fixed COP 3 and 5, passive heat rejection.
    sub = stage_df[
        (stage_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
        & (stage_df["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (stage_df["active_heat_fraction"] == 0.0)
        & (stage_df["extra_fan_power_kW"] == 0.0)
    ].copy()

    if not sub.empty:
        table = (
            sub[[
                "case",
                "COP_case",
                "penalized_break_even_e_p_Wh_per_kg_water",
            ]]
            .drop_duplicates()
            .sort_values(["case", "COP_case"])
        )

        fig, ax = plt.subplots(figsize=(9, 5))
        labels = [
            f"{r.case}\n{r.COP_case}"
            for r in table.itertuples(index=False)
        ]
        ax.bar(range(len(table)), table["penalized_break_even_e_p_Wh_per_kg_water"])
        ax.set_xticks(range(len(table)))
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.set_ylabel("Break-even EO energy [Wh/kg water]")
        ax.set_title("WP1 stage-gate: break-even EO energy, passive heat handling")
        ax.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(plot_dir / "break_even_ep_passive_heat.png", dpi=200)
        plt.close(fig)

    # Plot net saving vs e_p for the most important fixed COP cases.
    sub = stage_df[
        (stage_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
        & (stage_df["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (stage_df["active_heat_fraction"] == 0.0)
        & (stage_df["extra_fan_power_kW"] == 0.0)
    ].copy()

    if not sub.empty:
        fig, ax = plt.subplots(figsize=(9, 5))
        for (case, cop_case), g in sub.groupby(["case", "COP_case"]):
            g = g.sort_values("e_p_Wh_per_kg_water")
            ax.plot(
                g["e_p_Wh_per_kg_water"],
                g["net_saving_pct_of_baseline"],
                marker="o",
                label=f"{case}, {cop_case}",
            )
        ax.axhline(0.0, linestyle="--")
        ax.axhline(5.0, linestyle=":")
        ax.set_xlabel("EO energy, e_p [Wh/kg water]")
        ax.set_ylabel("Net saving [% of baseline purchased power]")
        ax.set_title("Net saving after EO power, passive heat handling")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(plot_dir / "net_saving_vs_ep_passive_heat.png", dpi=200)
        plt.close(fig)

    # Sensitivity to active heat fraction at e_p=100 Wh/kg.
    sub = stage_df[
        (stage_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
        & (stage_df["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (stage_df["e_p_Wh_per_kg_water"] == 100.0)
        & (stage_df["extra_fan_power_kW"] == 0.0)
    ].copy()

    if not sub.empty:
        fig, ax = plt.subplots(figsize=(9, 5))
        for (case, cop_case), g in sub.groupby(["case", "COP_case"]):
            g = g.sort_values("active_heat_fraction")
            ax.plot(
                g["active_heat_fraction"],
                g["net_saving_pct_of_baseline"],
                marker="o",
                label=f"{case}, {cop_case}",
            )
        ax.axhline(0.0, linestyle="--")
        ax.set_xlabel("Fraction of sorption heat requiring active rejection")
        ax.set_ylabel("Net saving [% of baseline purchased power]")
        ax.set_title("Sensitivity to active heat handling, e_p=100 Wh/kg")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(plot_dir / "net_saving_vs_active_heat_fraction_ep100.png", dpi=200)
        plt.close(fig)


def write_report(
    out_dir: Path,
    stage_df: pd.DataFrame,
    best_df: pd.DataFrame,
    breakeven_df: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    passive = breakeven_df[
        (breakeven_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
        & (breakeven_df["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (breakeven_df["active_heat_fraction"] == 0.0)
        & (breakeven_df["extra_fan_power_kW"] == 0.0)
    ].copy()

    conservative = breakeven_df[
        (breakeven_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
        & (breakeven_df["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (breakeven_df["active_heat_fraction"] == 1.0)
        & (breakeven_df["extra_fan_power_kW"] == 0.0)
    ].copy()

    candidate_focus = stage_df[
        (stage_df["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
        & (stage_df["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (stage_df["active_heat_fraction"].isin([0.0, 0.25, 1.0]))
        & (stage_df["extra_fan_power_kW"] == 0.0)
        & (stage_df["e_p_Wh_per_kg_water"].isin([25.0, 50.0, 100.0, 150.0, 200.0]))
    ].copy()

    cols_focus = [
        "case",
        "COP_case",
        "active_heat_fraction",
        "e_p_Wh_per_kg_water",
        "saved_purchased_power_vs_baseline_kW",
        "EO_power_kW",
        "thermal_penalty_kW",
        "net_saving_kW",
        "net_saving_pct_of_baseline",
        "passes_stage_gate",
        "passes_5pct_net_saving",
        "passes_10pct_net_saving",
    ]

    report = []
    report.append("# WP1 stage-gate summary")
    report.append("")
    report.append("This is an algebraic stage-gate summary based on the simple WP1 pre-drying calculations.")
    report.append("")
    report.append("## Core stage-gate equation")
    report.append("")
    report.append("```text")
    report.append("P_net = P_saved - P_EO - P_thermal - P_fan")
    report.append("```")
    report.append("")
    report.append("A case passes the basic stage gate when `P_net > 0`.")
    report.append("")
    report.append("## Inputs")
    report.append("")
    report.append(f"- Input directory: `{args.input_dir}`")
    report.append(f"- Heat rejection COP for active heat penalty: {args.heat_rejection_COP:g}")
    report.append(f"- Candidate EO energies: {args.candidate_ep}")
    report.append(f"- Active heat fractions: {args.active_heat_fractions}")
    report.append(f"- Extra fan powers: {args.extra_fan_power_kW}")
    report.append("")
    report.append("## Passive heat-handling break-even e_p")
    report.append("")
    if passive.empty:
        report.append("No passive heat-handling rows found.")
    else:
        report.append("```text")
        report.append(
            passive[[
                "case",
                "COP_case",
                "water_removed_by_predrying_kg_h",
                "saved_purchased_power_vs_baseline_kW",
                "penalized_break_even_e_p_Wh_per_kg_water",
            ]].to_string(index=False)
        )
        report.append("```")
    report.append("")
    report.append("## Conservative active heat-rejection break-even e_p")
    report.append("")
    if conservative.empty:
        report.append("No conservative rows found.")
    else:
        report.append("```text")
        report.append(
            conservative[[
                "case",
                "COP_case",
                "sorption_heat_kW",
                "thermal_penalty_kW",
                "penalized_break_even_e_p_Wh_per_kg_water",
            ]].to_string(index=False)
        )
        report.append("```")
    report.append("")
    report.append("## Candidate focus table")
    report.append("")
    if candidate_focus.empty:
        report.append("No candidate focus rows found.")
    else:
        report.append("```text")
        report.append(
            candidate_focus[cols_focus]
            .sort_values(["case", "COP_case", "active_heat_fraction", "e_p_Wh_per_kg_water"])
            .to_string(index=False)
        )
        report.append("```")
    report.append("")
    report.append("## Interpretation")
    report.append("")
    report.append("- The passive heat-handling table is an optimistic but useful upper bound.")
    report.append("- The active heat-rejection table is intentionally conservative: it assumes a selected fraction of sorption heat must be rejected with an active device.")
    report.append("- A robust WP1 result is one where the allowable `e_p` remains above plausible membrane targets even after fan and thermal penalties.")

    (out_dir / "wp1_stage_gate_report.md").write_text("\n".join(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create WP1 stage-gate decision tables from simple pre-drying outputs.")
    parser.add_argument("--input-dir", default="outputs/wp1_simple_calculations")
    parser.add_argument("--out", default="outputs/wp1_stage_gate_summary")
    parser.add_argument("--candidate-ep", type=float, nargs="+", default=[25, 50, 75, 100, 150, 200, 300])
    parser.add_argument("--q-sorp-values", type=float, nargs="+", default=[2200.0, 2431.0, 2600.0])
    parser.add_argument("--active-heat-fractions", type=float, nargs="+", default=[0.0, 0.25, 0.5, 1.0])
    parser.add_argument("--heat-rejection-COP", type=float, default=3.0)
    parser.add_argument("--extra-fan-power-kW", type=float, nargs="+", default=[0.0, 0.25, 0.5, 1.0])
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    load_df = read_csv_required(input_dir / "cooling_power_and_savings.csv")
    threshold_df = read_csv_required(input_dir / "eo_break_even_thresholds.csv")
    heat_df = read_csv_required(input_dir / "heat_rejection_requirements.csv")

    stage_df = make_stage_gate_rows(
        threshold_df=threshold_df,
        load_df=load_df,
        heat_df=heat_df,
        candidate_ep=args.candidate_ep,
        heat_active_fractions=args.active_heat_fractions,
        extra_fan_kW_values=args.extra_fan_power_kW,
        heat_rejection_COP=args.heat_rejection_COP,
        q_sorp_values=args.q_sorp_values,
    )

    best_df, breakeven_df = make_summary_tables(stage_df)

    stage_df.to_csv(out_dir / "wp1_stage_gate_candidates.csv", index=False)
    best_df.to_csv(out_dir / "wp1_stage_gate_best_by_group.csv", index=False)
    breakeven_df.to_csv(out_dir / "wp1_stage_gate_break_even_ep.csv", index=False)

    make_plots(stage_df, out_dir)
    write_report(out_dir, stage_df, best_df, breakeven_df, args)

    print(f"Wrote WP1 stage-gate summary to: {out_dir}")
    print()
    print((out_dir / "wp1_stage_gate_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
