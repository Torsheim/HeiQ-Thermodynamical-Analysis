from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from heiq_thermo.model import load_yaml, run_first_model, save_summary_text
from heiq_thermo.plots import (
    plot_best_savings_vs_heat_fraction,
    plot_savings_map,
    plot_simple_psychrometric_chart,
)


def configure_common_grid(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    cfg = copy.deepcopy(cfg)
    cfg["eo"]["fraction_latent_by_eo_grid"] = {
        "start": float(args.f_start),
        "stop": float(args.f_stop),
        "n": int(args.n_f),
    }
    cfg["eo"]["e_p_Wh_per_kg_water_grid"] = {
        "start": float(args.ep_start),
        "stop": float(args.ep_stop),
        "n": int(args.n_ep),
    }
    cfg["eo"]["heat_to_process_fraction_grid"] = [float(x) for x in args.heat_fractions]
    cfg.setdefault("plots", {})["savings_map_heat_fractions"] = [float(x) for x in args.heat_fractions]
    return cfg


def reheat_cases() -> dict[str, dict[str, Any]]:
    """Purchased-energy assumptions for post-cooling reheat.

    reheat_COP = 1.0      -> direct electric reheat.
    reheat_COP = 3.0      -> useful heat supplied by heat pump / recovery with COP 3.
    reheat_COP = 1e12     -> effectively free reheat / mixing / waste heat.
    """
    return {
        "electric_reheat": {
            "reheat_COP": 1.0,
            "description": "Reheat is purchased as direct electric heat, COP=1.",
        },
        "heat_pump_reheat_COP3": {
            "reheat_COP": 3.0,
            "description": "Reheat is purchased but delivered with COP=3.",
        },
        "free_reheat": {
            "reheat_COP": 1.0e12,
            "description": "Reheat/mixing/waste heat is treated as free purchased energy.",
        },
    }


def run_one_case(case_name: str, cfg: dict[str, Any], out_dir: Path) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)

    df, summary = run_first_model(cfg)

    df.to_csv(out_dir / "sensitivity_results.csv", index=False)
    save_summary_text(summary, out_dir / "summary.txt")

    with open(out_dir / "resolved_config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    plot_simple_psychrometric_chart(
        summary["start"],
        summary["target"],
        out_dir / "psychrometric_routes.png",
        dry_air_mass_flow_kg_s=summary["dry_air_mass_flow_kg_s"],
        example_e_p_Wh_per_kg_water=float(cfg.get("plots", {}).get("example_e_p_Wh_per_kg_water", 300.0)),
        example_heat_to_process_fraction=float(cfg.get("plots", {}).get("example_heat_to_process_fraction", 0.25)),
    )

    for chi in cfg["eo"]["heat_to_process_fraction_grid"]:
        plot_savings_map(df, out_dir / f"savings_map_chi_{float(chi):.2f}.png", float(chi))

    plot_best_savings_vs_heat_fraction(df, out_dir / "best_savings_vs_heat_fraction.png")

    df = df.copy()
    df.insert(0, "case", case_name)
    return df


def threshold_by_f(
    df: pd.DataFrame,
    savings_targets: tuple[float, ...] = (0.0, 2.0, 5.0, 10.0),
    min_f_for_threshold: float = 1e-9,
) -> pd.DataFrame:
    """For every f and heat fraction, find max Wh/kg that still meets target saving.

    f = 0 is excluded from threshold interpretation because EO/ACEO energy is then
    irrelevant: no latent load is being taken by EO/ACEO.
    """
    rows: list[dict[str, Any]] = []

    for case, case_df in df.groupby("case"):
        for target_saving in savings_targets:
            for (chi, f), group in case_df.groupby(["heat_to_process_fraction", "f_latent_by_eo"]):
                best = group.loc[group["savings_pct"].idxmax()]

                if float(f) <= min_f_for_threshold:
                    ok = group.iloc[0:0]
                else:
                    ok = group[group["savings_pct"] >= target_saving]

                row: dict[str, Any] = {
                    "case": case,
                    "target_savings_pct": float(target_saving),
                    "heat_to_process_fraction": float(chi),
                    "f_latent_by_eo": float(f),
                    "best_savings_pct_at_this_f": float(best["savings_pct"]),
                    "best_e_p_at_this_f_Wh_per_kg": float(best["e_p_Wh_per_kg_water"]),
                }

                if ok.empty:
                    row.update(
                        {
                            "max_e_p_meeting_target_Wh_per_kg": np.nan,
                            "savings_at_max_e_p_pct": np.nan,
                        }
                    )
                else:
                    max_ep = ok["e_p_Wh_per_kg_water"].max()
                    candidates = ok[ok["e_p_Wh_per_kg_water"] == max_ep]
                    chosen = candidates.loc[candidates["savings_pct"].idxmax()]
                    row.update(
                        {
                            "max_e_p_meeting_target_Wh_per_kg": float(max_ep),
                            "savings_at_max_e_p_pct": float(chosen["savings_pct"]),
                        }
                    )

                rows.append(row)

    return pd.DataFrame(rows)


def compact_thresholds(thresholds: pd.DataFrame) -> pd.DataFrame:
    """For each case/heat/target, find largest Wh/kg allowed at any EO fraction."""
    rows: list[dict[str, Any]] = []
    group_cols = ["case", "target_savings_pct", "heat_to_process_fraction"]

    for keys, group in thresholds.groupby(group_cols):
        case, target_saving, chi = keys
        ok = group.dropna(subset=["max_e_p_meeting_target_Wh_per_kg"])

        if ok.empty:
            rows.append(
                {
                    "case": case,
                    "target_savings_pct": float(target_saving),
                    "heat_to_process_fraction": float(chi),
                    "max_e_p_any_f_Wh_per_kg": np.nan,
                    "f_at_max_e_p": np.nan,
                    "savings_at_threshold_pct": np.nan,
                }
            )
            continue

        max_ep = ok["max_e_p_meeting_target_Wh_per_kg"].max()
        candidates = ok[ok["max_e_p_meeting_target_Wh_per_kg"] == max_ep]
        chosen = candidates.loc[candidates["savings_at_max_e_p_pct"].idxmax()]

        rows.append(
            {
                "case": case,
                "target_savings_pct": float(target_saving),
                "heat_to_process_fraction": float(chi),
                "max_e_p_any_f_Wh_per_kg": float(max_ep),
                "f_at_max_e_p": float(chosen["f_latent_by_eo"]),
                "savings_at_threshold_pct": float(chosen["savings_at_max_e_p_pct"]),
            }
        )

    return pd.DataFrame(rows).sort_values(group_cols)


def plot_threshold_curves(thresholds: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    for (case, chi), group in thresholds.groupby(["case", "heat_to_process_fraction"]):
        fig, ax = plt.subplots(figsize=(8, 5))

        for target_saving, target_group in group.groupby("target_savings_pct"):
            ax.plot(
                target_group["f_latent_by_eo"],
                target_group["max_e_p_meeting_target_Wh_per_kg"],
                marker="o",
                markersize=2.5,
                linewidth=1.2,
                label=f">= {target_saving:g}% saving",
            )

        ax.set_xlabel("Fraction of latent water removal done by EO/ACEO, f")
        ax.set_ylabel("Max EO/ACEO energy that still meets target [Wh/kg water]")
        ax.set_title(f"Break-even thresholds: {case}, heat-to-process = {chi:.2f}")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / f"threshold_curves_{case}_chi_{chi:.2f}.png", dpi=200)
        plt.close(fig)


def plot_compact_summary(compact: pd.DataFrame, out_path: Path) -> None:
    plot_df = compact.copy()
    plot_df["label"] = (
        plot_df["case"]
        + ", chi="
        + plot_df["heat_to_process_fraction"].map(lambda x: f"{x:.2f}")
    )

    targets = sorted(plot_df["target_savings_pct"].unique())
    labels = list(plot_df["label"].unique())

    x = np.arange(len(labels))
    width = 0.8 / max(len(targets), 1)

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 0.7), 6))

    for k, target in enumerate(targets):
        vals = []
        for label in labels:
            sub = plot_df[
                (plot_df["label"] == label)
                & (plot_df["target_savings_pct"] == target)
            ]
            vals.append(
                float(sub["max_e_p_any_f_Wh_per_kg"].iloc[0])
                if not sub.empty
                else np.nan
            )

        ax.bar(
            x + (k - (len(targets) - 1) / 2) * width,
            vals,
            width,
            label=f">= {target:g}%",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Max allowed EO/ACEO energy [Wh/kg water]")
    ax.set_title("EO/ACEO energy thresholds for savings targets")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="Saving target")
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def write_markdown_report(compact: pd.DataFrame, out_path: Path) -> None:
    lines = [
        "# Reheat and EO/ACEO threshold analysis",
        "",
        "Interpretation:",
        "",
        "- `max_e_p_any_f_Wh_per_kg` is the highest EO/ACEO electrical energy per kg water removed that still meets the savings target somewhere in the latent-fraction sweep.",
        "- If a value is equal to the top of the simulated `e_p` grid, the real threshold may be higher; extend the grid.",
        "- If a value is NaN, no simulated point met that target.",
        "",
        "```text",
        compact.to_string(index=False),
        "```",
        "",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run reheat assumptions and EO/ACEO threshold analysis."
    )

    parser.add_argument("--config", default="scenarios/first_model.yaml")
    parser.add_argument("--out", default="outputs/reheat_threshold_analysis")

    parser.add_argument("--f-start", type=float, default=0.0)
    parser.add_argument("--f-stop", type=float, default=1.0)
    parser.add_argument("--n-f", type=int, default=101)

    parser.add_argument("--ep-start", type=float, default=25.0)
    parser.add_argument("--ep-stop", type=float, default=2000.0)
    parser.add_argument("--n-ep", type=int, default=120)

    parser.add_argument(
        "--heat-fractions",
        type=float,
        nargs="+",
        default=[0.0, 0.25, 0.5, 0.75, 1.0],
    )

    parser.add_argument(
        "--savings-targets",
        type=float,
        nargs="+",
        default=[0.0, 2.0, 5.0, 10.0],
    )

    args = parser.parse_args()

    base_cfg = configure_common_grid(load_yaml(args.config), args)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    all_frames = []

    for case_name, case_info in reheat_cases().items():
        cfg = copy.deepcopy(base_cfg)
        cfg.setdefault("coil", {})["reheat_COP"] = float(case_info["reheat_COP"])
        cfg.setdefault("metadata", {})["case_description"] = case_info["description"]

        print(f"Running case: {case_name} ({case_info['description']})")
        df_case = run_one_case(case_name, cfg, out_root / case_name)
        all_frames.append(df_case)

    all_df = pd.concat(all_frames, ignore_index=True)
    all_df.to_csv(out_root / "all_cases_sensitivity_results.csv", index=False)

    thresholds = threshold_by_f(
        all_df,
        savings_targets=tuple(float(x) for x in args.savings_targets),
    )
    thresholds.to_csv(out_root / "thresholds_by_f.csv", index=False)

    compact = compact_thresholds(thresholds)
    compact.to_csv(out_root / "thresholds_compact.csv", index=False)

    plot_threshold_curves(thresholds, out_root / "threshold_plots")
    plot_compact_summary(compact, out_root / "thresholds_compact.png")
    write_markdown_report(compact, out_root / "threshold_report.md")

    print("\nWrote analysis to:", out_root)
    print("\nCompact threshold table:")
    print(compact.to_string(index=False))


if __name__ == "__main__":
    main()
