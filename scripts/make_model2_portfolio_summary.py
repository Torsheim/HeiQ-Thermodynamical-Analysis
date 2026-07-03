from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _as_float_list(values: list[str] | None, default: list[float]) -> list[float]:
    if values is None:
        return default
    return [float(v) for v in values]


def _clean_float_for_name(x: float) -> str:
    return (f"{x:g}").replace(".", "p").replace("-", "m")


def _is_valid_solution(df: pd.DataFrame, value_col: str) -> pd.Series:
    regime = df.get("regime", pd.Series("", index=df.index)).astype(str)
    return df[value_col].notna() & (regime != "no_solution")


def summarize_robust(
    df: pd.DataFrame,
    group_cols: list[str],
    value_col: str,
    scenario_col: str = "scenario",
    regime_col: str = "regime",
) -> pd.DataFrame:
    """Robust summary across scenarios.

    For each group, this reports whether all scenarios were solved and the worst
    required value across scenarios. If any scenario has no solution, the robust
    value is NaN and no_solution_scenarios lists the blockers.
    """
    rows: list[dict[str, Any]] = []

    for keys, group in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row: dict[str, Any] = dict(zip(group_cols, keys))

        valid = _is_valid_solution(group, value_col)
        solved = group[valid].copy()
        unsolved = group[~valid].copy()

        row["n_scenarios_total"] = int(group[scenario_col].nunique())
        row["n_scenarios_solved"] = int(solved[scenario_col].nunique())
        row["n_scenarios_no_solution"] = int(unsolved[scenario_col].nunique())
        row["all_scenarios_solved"] = bool(unsolved.empty)

        if not unsolved.empty:
            row["no_solution_scenarios"] = ";".join(sorted(unsolved[scenario_col].astype(str).unique()))
        else:
            row["no_solution_scenarios"] = ""

        if solved.empty:
            row[f"max_solved_{value_col}"] = np.nan
            row[f"hardest_solved_scenario_by_{value_col}"] = ""
            row[f"robust_{value_col}"] = np.nan
            row["hardest_scenario"] = ""
            row["regime_at_hardest_scenario"] = "no_solution"
        else:
            idx = solved[value_col].idxmax()
            hardest = solved.loc[idx]
            max_solved = float(hardest[value_col])
            row[f"max_solved_{value_col}"] = max_solved
            row[f"hardest_solved_scenario_by_{value_col}"] = str(hardest[scenario_col])
            row["hardest_scenario"] = str(hardest[scenario_col]) if unsolved.empty else "no_solution_exists"
            row["regime_at_hardest_scenario"] = (
                str(hardest[regime_col]) if unsolved.empty and regime_col in hardest.index else "no_solution"
            )
            row[f"robust_{value_col}"] = max_solved if unsolved.empty else np.nan

        if regime_col in group.columns:
            regimes = group.loc[valid, regime_col].astype(str)
            row["dominant_solved_regime"] = regimes.mode().iloc[0] if not regimes.empty else "no_solution"
        else:
            row["dominant_solved_regime"] = ""

        rows.append(row)

    return pd.DataFrame(rows)


def write_markdown_report(
    out_path: Path,
    scenario_summary: pd.DataFrame,
    robust_area: pd.DataFrame,
    robust_flux: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    report_targets = [float(x) for x in args.report_targets]
    report_eps = [float(x) for x in args.report_eps]
    report_flows = [float(x) for x in args.report_flows]
    report_fluxes = [float(x) for x in args.report_fluxes]
    report_areas = [float(x) for x in args.report_areas]

    area_sel = robust_area[
        robust_area["target_savings_pct"].isin(report_targets)
        & robust_area["e_p_Wh_per_kg_water"].isin(report_eps)
        & robust_area["desired_dry_air_flow_kg_s"].isin(report_flows)
        & robust_area["flux_g_m2_h"].isin(report_fluxes)
    ].copy()

    flux_sel = robust_flux[
        robust_flux["target_savings_pct"].isin(report_targets)
        & robust_flux["e_p_Wh_per_kg_water"].isin(report_eps)
        & robust_flux["desired_dry_air_flow_kg_s"].isin(report_flows)
        & robust_flux["area_limit_m2"].isin(report_areas)
    ].copy()

    area_cols = [
        "target_savings_pct",
        "e_p_Wh_per_kg_water",
        "flux_g_m2_h",
        "desired_dry_air_flow_kg_s",
        "robust_min_area_m2",
        "all_scenarios_solved",
        "hardest_solved_scenario_by_min_area_m2",
        "regime_at_hardest_scenario",
        "no_solution_scenarios",
    ]
    area_cols = [c for c in area_cols if c in area_sel.columns]

    flux_cols = [
        "target_savings_pct",
        "e_p_Wh_per_kg_water",
        "area_limit_m2",
        "desired_dry_air_flow_kg_s",
        "robust_min_flux_g_m2_h",
        "all_scenarios_solved",
        "hardest_solved_scenario_by_min_flux_g_m2_h",
        "regime_at_hardest_scenario",
        "no_solution_scenarios",
    ]
    flux_cols = [c for c in flux_cols if c in flux_sel.columns]

    lines: list[str] = []
    lines.append("# Model 2 portfolio summary")
    lines.append("")
    lines.append("This report condenses the scenario sweep into robust product-facing requirements.")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `robust_min_area_m2` is the minimum active membrane area that works for all scenarios in the sweep.")
    lines.append("- `robust_min_flux_g_m2_h` is the minimum flux that works for all scenarios in the sweep.")
    lines.append("- If `all_scenarios_solved=False`, at least one scenario had no solution on the simulated grid.")
    lines.append("- Grid values are discrete; rerun with a finer grid if a decision boundary is important.")
    lines.append("")

    lines.append("## Scenario severity")
    sev_cols = [
        "scenario",
        "start_T_C",
        "start_RH_pct",
        "target_T_C",
        "target_RH_pct",
        "delta_w_g_per_kg_da",
        "water_load_kg_h_per_kg_da_s",
    ]
    sev_cols = [c for c in sev_cols if c in scenario_summary.columns]
    lines.append("")
    lines.append("```text")
    lines.append(scenario_summary[sev_cols].to_string(index=False))
    lines.append("```")
    lines.append("")

    lines.append("## Robust minimum area, selected cases")
    lines.append("")
    lines.append("```text")
    lines.append(area_sel[area_cols].sort_values(area_cols[:4]).to_string(index=False))
    lines.append("```")
    lines.append("")

    lines.append("## Robust minimum flux, selected cases")
    lines.append("")
    lines.append("```text")
    lines.append(flux_sel[flux_cols].sort_values(flux_cols[:4]).to_string(index=False))
    lines.append("```")
    lines.append("")

    # Simple recommended target extraction for 1 kg/s if present.
    lines.append("## Quick product reading")
    lines.append("")
    one_flow_area = area_sel[area_sel.get("desired_dry_air_flow_kg_s", pd.Series(dtype=float)).eq(1.0)].copy()
    if not one_flow_area.empty:
        lines.append("For 1 kg_da/s, the selected robust area cases above show the approximate active-area requirement across all scenarios.")
    lines.append("")
    lines.append("Typical interpretation:")
    lines.append("")
    lines.append("```text")
    lines.append("low e_p (50--100 Wh/kg): partial pre-dehumidification can be useful")
    lines.append("higher e_p (150--200 Wh/kg): large/full latent removal usually becomes necessary")
    lines.append("compact modules need high J_w; low J_w can still work if active area is large")
    lines.append("```")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def plot_scenario_severity(scenario_summary: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if "scenario" not in scenario_summary.columns or "water_load_kg_h_per_kg_da_s" not in scenario_summary.columns:
        return
    df = scenario_summary.sort_values("water_load_kg_h_per_kg_da_s", ascending=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(df["scenario"], df["water_load_kg_h_per_kg_da_s"])
    ax.set_xlabel("Water removal load [kg/h per kg_da/s]")
    ax.set_title("Scenario latent-load severity")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "scenario_latent_load_severity.png", dpi=200)
    plt.close(fig)


def plot_robust_area(robust_area: pd.DataFrame, out_dir: Path, report_targets: list[float], report_eps: list[float]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for target in report_targets:
        for ep in report_eps:
            df = robust_area[
                (robust_area["target_savings_pct"] == target)
                & (robust_area["e_p_Wh_per_kg_water"] == ep)
                & (robust_area["all_scenarios_solved"] == True)
            ].copy()
            if df.empty:
                continue
            fig, ax = plt.subplots(figsize=(8, 5))
            for flux, g in df.groupby("flux_g_m2_h"):
                g = g.sort_values("desired_dry_air_flow_kg_s")
                ax.plot(
                    g["desired_dry_air_flow_kg_s"],
                    g["robust_min_area_m2"],
                    marker="o",
                    label=f"J={flux:g} g/(m² h)",
                )
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("Desired dry-air flow [kg_da/s]")
            ax.set_ylabel("Robust minimum active area [m²]")
            ax.set_title(f"Robust area across scenarios: >= {target:g}% saving, e_p={ep:g} Wh/kg")
            ax.grid(True, which="both", alpha=0.3)
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(out_dir / f"robust_area_target_{_clean_float_for_name(target)}_ep_{_clean_float_for_name(ep)}.png", dpi=200)
            plt.close(fig)


def plot_robust_flux(robust_flux: pd.DataFrame, out_dir: Path, report_targets: list[float], report_eps: list[float]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for target in report_targets:
        for ep in report_eps:
            df = robust_flux[
                (robust_flux["target_savings_pct"] == target)
                & (robust_flux["e_p_Wh_per_kg_water"] == ep)
                & (robust_flux["all_scenarios_solved"] == True)
            ].copy()
            if df.empty:
                continue
            fig, ax = plt.subplots(figsize=(8, 5))
            for area, g in df.groupby("area_limit_m2"):
                g = g.sort_values("desired_dry_air_flow_kg_s")
                ax.plot(
                    g["desired_dry_air_flow_kg_s"],
                    g["robust_min_flux_g_m2_h"],
                    marker="o",
                    label=f"A={area:g} m²",
                )
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("Desired dry-air flow [kg_da/s]")
            ax.set_ylabel("Robust minimum flux [g/(m² h)]")
            ax.set_title(f"Robust flux across scenarios: >= {target:g}% saving, e_p={ep:g} Wh/kg")
            ax.grid(True, which="both", alpha=0.3)
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(out_dir / f"robust_flux_target_{_clean_float_for_name(target)}_ep_{_clean_float_for_name(ep)}.png", dpi=200)
            plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Model 2 scenario sweep into robust product requirements.")
    parser.add_argument("--sweep-dir", default="outputs/model2_scenario_sweep")
    parser.add_argument("--out", default="outputs/model2_portfolio_summary")
    parser.add_argument("--report-flows", nargs="+", default=["0.1", "0.5", "1", "2"])
    parser.add_argument("--report-targets", nargs="+", default=["5", "10"])
    parser.add_argument("--report-eps", nargs="+", default=["50", "100", "150", "200"])
    parser.add_argument("--report-fluxes", nargs="+", default=["500", "1000", "3000", "5000", "10000"])
    parser.add_argument("--report-areas", nargs="+", default=["10", "20", "50", "100"])
    args = parser.parse_args()

    sweep_dir = Path(args.sweep_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario_summary_path = sweep_dir / "scenario_summary.csv"
    area_path = sweep_dir / "all_min_area_for_desired_flows.csv"
    flux_path = sweep_dir / "all_min_flux_for_desired_flows.csv"

    scenario_summary = pd.read_csv(scenario_summary_path)
    area = pd.read_csv(area_path)
    flux = pd.read_csv(flux_path)

    if "water_load_kg_h_per_kg_da_s" in scenario_summary.columns:
        scenario_summary = scenario_summary.sort_values("water_load_kg_h_per_kg_da_s", ascending=False)

    robust_area = summarize_robust(
        area,
        group_cols=["target_savings_pct", "e_p_Wh_per_kg_water", "flux_g_m2_h", "desired_dry_air_flow_kg_s"],
        value_col="min_area_m2",
    )
    robust_flux = summarize_robust(
        flux,
        group_cols=["target_savings_pct", "e_p_Wh_per_kg_water", "area_limit_m2", "desired_dry_air_flow_kg_s"],
        value_col="min_flux_g_m2_h",
    )

    robust_area.to_csv(out_dir / "robust_min_area_across_scenarios.csv", index=False)
    robust_flux.to_csv(out_dir / "robust_min_flux_across_scenarios.csv", index=False)
    scenario_summary.to_csv(out_dir / "scenario_severity_sorted.csv", index=False)

    plot_dir = out_dir / "plots"
    plot_scenario_severity(scenario_summary, plot_dir)
    plot_robust_area(
        robust_area,
        plot_dir / "robust_area",
        _as_float_list(args.report_targets, [5.0, 10.0]),
        _as_float_list(args.report_eps, [50.0, 100.0, 150.0, 200.0]),
    )
    plot_robust_flux(
        robust_flux,
        plot_dir / "robust_flux",
        _as_float_list(args.report_targets, [5.0, 10.0]),
        _as_float_list(args.report_eps, [50.0, 100.0, 150.0, 200.0]),
    )

    write_markdown_report(out_dir / "model2_portfolio_summary.md", scenario_summary, robust_area, robust_flux, args)

    print("Wrote portfolio summary to:", out_dir)
    print("\nScenario severity:")
    cols = [c for c in ["scenario", "delta_w_g_per_kg_da", "water_load_kg_h_per_kg_da_s"] if c in scenario_summary.columns]
    print(scenario_summary[cols].to_string(index=False))


if __name__ == "__main__":
    main()
