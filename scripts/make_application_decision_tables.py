from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _as_float_list(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values]


def classify_regime(f: float) -> str:
    if not np.isfinite(f):
        return "no_solution"
    if f < 0.10:
        return "small_pre_dehumidification"
    if f < 0.50:
        return "partial_pre_dehumidification"
    if f < 0.90:
        return "large_partial_latent_removal"
    if f < 0.999:
        return "near_full_latent_removal"
    return "full_latent_removal"


def load_and_filter(args: argparse.Namespace) -> pd.DataFrame:
    df = pd.read_csv(args.input)

    for col in [
        "target_savings_pct",
        "e_p_Wh_per_kg_water",
        "flux_g_m2_h",
        "area_limit_m2",
        "max_dry_air_flow_kg_s",
        "best_f_at_max_flow",
    ]:
        if col not in df.columns:
            raise KeyError(f"Missing expected column: {col}")

    selected_targets = _as_float_list(args.targets)
    selected_eps = _as_float_list(args.eps)
    selected_fluxes = _as_float_list(args.fluxes) if args.fluxes else None
    selected_areas = _as_float_list(args.areas) if args.areas else None

    df = df[df["target_savings_pct"].isin(selected_targets)].copy()
    df = df[df["e_p_Wh_per_kg_water"].isin(selected_eps)].copy()
    if selected_fluxes is not None:
        df = df[df["flux_g_m2_h"].isin(selected_fluxes)].copy()
    if selected_areas is not None:
        df = df[df["area_limit_m2"].isin(selected_areas)].copy()

    # Mark points that hit the search ceiling. These are lower bounds, not true maxima.
    df["search_limited"] = (
        df["max_dry_air_flow_kg_s"].notna()
        & (df["max_dry_air_flow_kg_s"] >= float(args.search_max_flow) * float(args.search_ceiling_fraction))
    )
    df["regime"] = df["best_f_at_max_flow"].apply(classify_regime)
    return df


def write_pivot_tables(df: pd.DataFrame, out_dir: Path) -> None:
    pivot_dir = out_dir / "pivot_tables"
    pivot_dir.mkdir(parents=True, exist_ok=True)

    for (target, ep), group in df.groupby(["target_savings_pct", "e_p_Wh_per_kg_water"]):
        prefix = f"target_{target:g}_ep_{ep:g}".replace(".", "p")

        flow_pivot = group.pivot_table(
            index="area_limit_m2",
            columns="flux_g_m2_h",
            values="max_dry_air_flow_kg_s",
            aggfunc="max",
        ).sort_index().sort_index(axis=1)
        flow_pivot.to_csv(pivot_dir / f"max_flow_{prefix}.csv")

        f_pivot = group.pivot_table(
            index="area_limit_m2",
            columns="flux_g_m2_h",
            values="best_f_at_max_flow",
            aggfunc="max",
        ).sort_index().sort_index(axis=1)
        f_pivot.to_csv(pivot_dir / f"best_f_{prefix}.csv")

        limited_pivot = group.pivot_table(
            index="area_limit_m2",
            columns="flux_g_m2_h",
            values="search_limited",
            aggfunc="max",
        ).sort_index().sort_index(axis=1)
        limited_pivot.to_csv(pivot_dir / f"search_limited_{prefix}.csv")


def make_min_area_for_flows(df: pd.DataFrame, desired_flows: list[float]) -> pd.DataFrame:
    rows: list[dict[str, float | str | bool]] = []

    group_cols = ["target_savings_pct", "e_p_Wh_per_kg_water", "flux_g_m2_h"]
    for (target, ep, flux), group in df.groupby(group_cols):
        group = group.sort_values("area_limit_m2")
        for desired_flow in desired_flows:
            ok = group[
                group["max_dry_air_flow_kg_s"].notna()
                & (group["max_dry_air_flow_kg_s"] >= desired_flow)
            ]
            if ok.empty:
                rows.append(
                    {
                        "target_savings_pct": target,
                        "e_p_Wh_per_kg_water": ep,
                        "flux_g_m2_h": flux,
                        "desired_dry_air_flow_kg_s": desired_flow,
                        "min_area_m2": np.nan,
                        "best_f_at_min_area": np.nan,
                        "savings_at_min_area_pct": np.nan,
                        "regime": "no_solution",
                        "search_limited_at_min_area": False,
                    }
                )
            else:
                chosen = ok.iloc[0]
                rows.append(
                    {
                        "target_savings_pct": target,
                        "e_p_Wh_per_kg_water": ep,
                        "flux_g_m2_h": flux,
                        "desired_dry_air_flow_kg_s": desired_flow,
                        "min_area_m2": float(chosen["area_limit_m2"]),
                        "best_f_at_min_area": float(chosen["best_f_at_max_flow"]),
                        "savings_at_min_area_pct": float(chosen["best_savings_at_max_flow_pct"]),
                        "regime": str(chosen["regime"]),
                        "search_limited_at_min_area": bool(chosen["search_limited"]),
                    }
                )
    return pd.DataFrame(rows)


def make_min_flux_for_flows(df: pd.DataFrame, desired_flows: list[float]) -> pd.DataFrame:
    rows: list[dict[str, float | str | bool]] = []

    group_cols = ["target_savings_pct", "e_p_Wh_per_kg_water", "area_limit_m2"]
    for (target, ep, area), group in df.groupby(group_cols):
        group = group.sort_values("flux_g_m2_h")
        for desired_flow in desired_flows:
            ok = group[
                group["max_dry_air_flow_kg_s"].notna()
                & (group["max_dry_air_flow_kg_s"] >= desired_flow)
            ]
            if ok.empty:
                rows.append(
                    {
                        "target_savings_pct": target,
                        "e_p_Wh_per_kg_water": ep,
                        "area_limit_m2": area,
                        "desired_dry_air_flow_kg_s": desired_flow,
                        "min_flux_g_m2_h": np.nan,
                        "best_f_at_min_flux": np.nan,
                        "savings_at_min_flux_pct": np.nan,
                        "regime": "no_solution",
                        "search_limited_at_min_flux": False,
                    }
                )
            else:
                chosen = ok.iloc[0]
                rows.append(
                    {
                        "target_savings_pct": target,
                        "e_p_Wh_per_kg_water": ep,
                        "area_limit_m2": area,
                        "desired_dry_air_flow_kg_s": desired_flow,
                        "min_flux_g_m2_h": float(chosen["flux_g_m2_h"]),
                        "best_f_at_min_flux": float(chosen["best_f_at_max_flow"]),
                        "savings_at_min_flux_pct": float(chosen["best_savings_at_max_flow_pct"]),
                        "regime": str(chosen["regime"]),
                        "search_limited_at_min_flux": bool(chosen["search_limited"]),
                    }
                )
    return pd.DataFrame(rows)


def plot_min_area_tables(min_area: pd.DataFrame, out_dir: Path) -> None:
    plot_dir = out_dir / "min_area_plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    for (target, ep), group in min_area.groupby(["target_savings_pct", "e_p_Wh_per_kg_water"]):
        fig, ax = plt.subplots(figsize=(8, 5))
        for flux, g in group.groupby("flux_g_m2_h"):
            g = g.sort_values("desired_dry_air_flow_kg_s")
            ax.plot(g["desired_dry_air_flow_kg_s"], g["min_area_m2"], marker="o", label=f"J={flux:g} g/(m² h)")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Desired dry-air flow [kg_da/s]")
        ax.set_ylabel("Minimum active area from grid [m²]")
        ax.set_title(f"Minimum area for >= {target:g}% saving, e_p={ep:g} Wh/kg")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(plot_dir / f"min_area_target_{target:g}_ep_{ep:g}.png", dpi=200)
        plt.close(fig)


def plot_min_flux_tables(min_flux: pd.DataFrame, out_dir: Path) -> None:
    plot_dir = out_dir / "min_flux_plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    for (target, ep), group in min_flux.groupby(["target_savings_pct", "e_p_Wh_per_kg_water"]):
        fig, ax = plt.subplots(figsize=(8, 5))
        for area, g in group.groupby("area_limit_m2"):
            g = g.sort_values("desired_dry_air_flow_kg_s")
            ax.plot(g["desired_dry_air_flow_kg_s"], g["min_flux_g_m2_h"], marker="o", label=f"A={area:g} m²")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Desired dry-air flow [kg_da/s]")
        ax.set_ylabel("Minimum flux from grid [g/(m² h)]")
        ax.set_title(f"Minimum flux for >= {target:g}% saving, e_p={ep:g} Wh/kg")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(plot_dir / f"min_flux_target_{target:g}_ep_{ep:g}.png", dpi=200)
        plt.close(fig)


def write_markdown_report(
    df: pd.DataFrame,
    min_area: pd.DataFrame,
    min_flux: pd.DataFrame,
    args: argparse.Namespace,
    out_path: Path,
) -> None:
    lines: list[str] = []
    lines.append("# Application decision tables")
    lines.append("")
    lines.append("This report condenses the application-scaling output into product-facing design tables.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Rows marked `search_limited=True` hit the dry-air-flow ceiling of the simulation. Treat them as lower bounds.")
    lines.append("- `regime` is classified from the best EO/ACEO latent fraction `f` chosen by the model.")
    lines.append("- `min_area_m2` and `min_flux_g_m2_h` are grid-based minima, not continuous optimizations.")
    lines.append("")

    # Compact selected rows: most product-relevant desired flows and targets.
    desired_subset = min_area[min_area["desired_dry_air_flow_kg_s"].isin(args.report_flows)].copy()
    desired_subset = desired_subset[
        desired_subset["target_savings_pct"].isin(args.report_targets)
        & desired_subset["e_p_Wh_per_kg_water"].isin(args.report_eps)
    ]
    if args.report_fluxes:
        desired_subset = desired_subset[desired_subset["flux_g_m2_h"].isin(args.report_fluxes)]

    lines.append("## Minimum area for selected desired air flows")
    lines.append("")
    lines.append("```text")
    lines.append(desired_subset.to_string(index=False))
    lines.append("```")
    lines.append("")

    flux_subset = min_flux[min_flux["desired_dry_air_flow_kg_s"].isin(args.report_flows)].copy()
    flux_subset = flux_subset[
        flux_subset["target_savings_pct"].isin(args.report_targets)
        & flux_subset["e_p_Wh_per_kg_water"].isin(args.report_eps)
    ]
    if args.report_areas:
        flux_subset = flux_subset[flux_subset["area_limit_m2"].isin(args.report_areas)]

    lines.append("## Minimum flux for selected desired air flows")
    lines.append("")
    lines.append("```text")
    lines.append(flux_subset.to_string(index=False))
    lines.append("```")
    lines.append("")

    # Summary of how much of table is limited by search ceiling.
    lines.append("## Search-ceiling diagnostics")
    lines.append("")
    limited_count = int(df["search_limited"].sum())
    total_count = int(len(df))
    lines.append(f"- Search-limited rows: {limited_count} / {total_count}")
    if limited_count > 0:
        lines.append("- Consider re-running the application scaling with a higher `--dry-air-stop`.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make compact product-decision tables from Model 2 application scaling output.")
    parser.add_argument("--input", default="outputs/model2_application_scaling_wide/max_airflow_by_area_flux.csv")
    parser.add_argument("--out", default="outputs/application_decision_tables")
    parser.add_argument("--search-max-flow", type=float, default=10.0)
    parser.add_argument("--search-ceiling-fraction", type=float, default=0.995)
    parser.add_argument("--targets", type=float, nargs="+", default=[2, 5, 10])
    parser.add_argument("--eps", type=float, nargs="+", default=[50, 100, 150, 200])
    parser.add_argument("--fluxes", type=float, nargs="+", default=[100, 200, 500, 1000, 3000, 5000, 10000])
    parser.add_argument("--areas", type=float, nargs="+", default=[1, 2, 5, 10, 20, 50, 100, 300])
    parser.add_argument("--desired-flows", type=float, nargs="+", default=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10])

    # Reporting subsets for readable markdown.
    parser.add_argument("--report-flows", type=float, nargs="+", default=[0.1, 0.5, 1, 2])
    parser.add_argument("--report-targets", type=float, nargs="+", default=[5, 10])
    parser.add_argument("--report-eps", type=float, nargs="+", default=[50, 100, 150, 200])
    parser.add_argument("--report-fluxes", type=float, nargs="+", default=[100, 500, 1000, 3000, 5000, 10000])
    parser.add_argument("--report-areas", type=float, nargs="+", default=[5, 10, 20, 50, 100])

    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_and_filter(args)
    df.to_csv(out_dir / "filtered_max_airflow_by_area_flux.csv", index=False)
    write_pivot_tables(df, out_dir)

    min_area = make_min_area_for_flows(df, _as_float_list(args.desired_flows))
    min_area.to_csv(out_dir / "min_area_for_desired_flows.csv", index=False)

    min_flux = make_min_flux_for_flows(df, _as_float_list(args.desired_flows))
    min_flux.to_csv(out_dir / "min_flux_for_desired_flows.csv", index=False)

    plot_min_area_tables(min_area, out_dir)
    plot_min_flux_tables(min_flux, out_dir)

    write_markdown_report(df, min_area, min_flux, args, out_dir / "application_decision_report.md")

    print("Wrote application decision tables to:", out_dir)
    print("\nKey files:")
    print("- application_decision_report.md")
    print("- min_area_for_desired_flows.csv")
    print("- min_flux_for_desired_flows.csv")
    print("- pivot_tables/")
    print("- min_area_plots/")
    print("- min_flux_plots/")


if __name__ == "__main__":
    main()
