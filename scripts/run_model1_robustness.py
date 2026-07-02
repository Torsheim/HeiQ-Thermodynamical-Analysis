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
from heiq_thermo.plots import plot_savings_map


REHEAT_CASES: dict[str, dict[str, Any]] = {
    "electric_reheat": {
        "reheat_COP": 1.0,
        "description": "Conventional reheat is direct purchased electric heat, COP=1.",
    },
    "heat_pump_reheat_COP3": {
        "reheat_COP": 3.0,
        "description": "Conventional reheat is purchased but delivered with COP=3.",
    },
    "free_reheat": {
        "reheat_COP": 1.0e12,
        "description": "Conventional reheat/mixing/waste heat is free in purchased-energy accounting.",
    },
}

EVAP_MODELS = ["linear_by_fraction", "strict_dewpoint_until_full"]


def grid_to_values(obj: Any) -> list[float]:
    if isinstance(obj, list):
        return [float(x) for x in obj]
    if isinstance(obj, dict):
        return [float(x) for x in np.linspace(float(obj["start"]), float(obj["stop"]), int(obj["n"]))]
    raise TypeError(f"Unsupported grid config: {obj!r}")


def configure_grid(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    cfg = copy.deepcopy(cfg)
    cfg["eo"]["fraction_latent_by_eo_grid"] = {"start": args.f_start, "stop": args.f_stop, "n": args.n_f}
    cfg["eo"]["e_p_Wh_per_kg_water_grid"] = {"start": args.ep_start, "stop": args.ep_stop, "n": args.n_ep}
    cfg["eo"]["heat_to_process_fraction_grid"] = [float(x) for x in args.heat_fractions]
    return cfg


def run_case(cfg: dict[str, Any], out_dir: Path, case: str, evap_model: str) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    df, summary = run_first_model(cfg)
    df = df.copy()
    df.insert(0, "case", case)
    df.insert(1, "evap_model", evap_model)

    df.to_csv(out_dir / "sensitivity_results.csv", index=False)
    save_summary_text(summary, out_dir / "summary.txt")
    with open(out_dir / "resolved_config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    # Save selected savings maps for quick visual inspection.
    for chi in cfg["eo"]["heat_to_process_fraction_grid"]:
        try:
            plot_savings_map(df, out_dir / f"savings_map_chi_{float(chi):.2f}.png", float(chi))
        except Exception as exc:  # plotting should not kill the numerical run
            print(f"Warning: could not plot savings map for {case}/{evap_model}/chi={chi}: {exc}")

    return df


def thresholds_by_f(
    df: pd.DataFrame,
    targets: list[float],
    f_caps: list[float],
) -> pd.DataFrame:
    """Find max e_p that still satisfies a savings target for each f.

    ``f_cap`` is used to explicitly separate the exact f=1 transition from
    partial-removal cases. If f_cap=0.99, all f values above 0.99 are ignored.
    """
    rows: list[dict[str, Any]] = []

    for f_cap in f_caps:
        df_cap = df[df["f_latent_by_eo"] <= f_cap + 1e-12].copy()
        for (case, evap_model, chi, f), group in df_cap.groupby(
            ["case", "evap_model", "heat_to_process_fraction", "f_latent_by_eo"]
        ):
            for target in targets:
                ok = group[group["savings_pct"] >= target]
                if ok.empty:
                    max_ep = np.nan
                    savings_at_max_ep = np.nan
                    best_savings = float(group["savings_pct"].max())
                else:
                    max_ep = float(ok["e_p_Wh_per_kg_water"].max())
                    chosen = ok[ok["e_p_Wh_per_kg_water"] == max_ep].iloc[0]
                    savings_at_max_ep = float(chosen["savings_pct"])
                    best_savings = float(group["savings_pct"].max())

                rows.append(
                    {
                        "f_cap": float(f_cap),
                        "case": case,
                        "evap_model": evap_model,
                        "heat_to_process_fraction": float(chi),
                        "f_latent_by_eo": float(f),
                        "target_savings_pct": float(target),
                        "max_e_p_meeting_target_Wh_per_kg": max_ep,
                        "savings_at_max_e_p_pct": savings_at_max_ep,
                        "best_savings_at_this_f_pct": best_savings,
                    }
                )
    return pd.DataFrame(rows)


def compact_thresholds(thresholds: pd.DataFrame) -> pd.DataFrame:
    """For each scenario, find the best f and max e_p for each target."""
    rows: list[dict[str, Any]] = []
    cols = ["f_cap", "case", "evap_model", "heat_to_process_fraction", "target_savings_pct"]
    for keys, group in thresholds.groupby(cols):
        f_cap, case, evap_model, chi, target = keys
        ok = group.dropna(subset=["max_e_p_meeting_target_Wh_per_kg"])
        if ok.empty:
            rows.append(
                {
                    "f_cap": f_cap,
                    "case": case,
                    "evap_model": evap_model,
                    "heat_to_process_fraction": chi,
                    "target_savings_pct": target,
                    "max_e_p_any_f_Wh_per_kg": np.nan,
                    "f_at_max_e_p": np.nan,
                    "savings_at_threshold_pct": np.nan,
                }
            )
            continue

        max_ep = ok["max_e_p_meeting_target_Wh_per_kg"].max()
        candidates = ok[ok["max_e_p_meeting_target_Wh_per_kg"] == max_ep]
        # Prefer larger margin if same e_p.
        chosen = candidates.loc[candidates["savings_at_max_e_p_pct"].idxmax()]
        rows.append(
            {
                "f_cap": float(f_cap),
                "case": case,
                "evap_model": evap_model,
                "heat_to_process_fraction": float(chi),
                "target_savings_pct": float(target),
                "max_e_p_any_f_Wh_per_kg": float(max_ep),
                "f_at_max_e_p": float(chosen["f_latent_by_eo"]),
                "savings_at_threshold_pct": float(chosen["savings_at_max_e_p_pct"]),
            }
        )
    return pd.DataFrame(rows).sort_values(cols)


def plot_threshold_comparison(compact: pd.DataFrame, out_path: Path, target: float = 5.0) -> None:
    """Bar plot of threshold e_p for a selected savings target."""
    sub = compact[compact["target_savings_pct"] == target].copy()
    sub["label"] = (
        sub["case"]
        + "\n"
        + sub["evap_model"]
        + "\nchi="
        + sub["heat_to_process_fraction"].map(lambda x: f"{x:.2f}")
        + "\nf<="
        + sub["f_cap"].map(lambda x: f"{x:.2f}")
    )

    # Only plot a manageable subset: heat fractions 0, 0.5, 1.0.
    sub = sub[sub["heat_to_process_fraction"].isin([0.0, 0.5, 1.0])]
    sub = sub.sort_values(["f_cap", "evap_model", "case", "heat_to_process_fraction"])

    fig, ax = plt.subplots(figsize=(max(12, len(sub) * 0.34), 6))
    ax.bar(np.arange(len(sub)), sub["max_e_p_any_f_Wh_per_kg"])
    ax.set_xticks(np.arange(len(sub)))
    ax.set_xticklabels(sub["label"], rotation=75, ha="right", fontsize=7)
    ax.set_ylabel("Max EO/ACEO energy still meeting target [Wh/kg water]")
    ax.set_title(f"EO/ACEO thresholds for >= {target:g}% savings")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_fixed_ep_heat_sensitivity(
    df: pd.DataFrame,
    out_dir: Path,
    fixed_eps: list[float],
    savings_target_lines: list[float] = [0.0, 2.0, 5.0, 10.0],
) -> None:
    """At fixed e_p, optimize over f and plot best savings vs heat fraction."""
    out_dir.mkdir(parents=True, exist_ok=True)
    e_values = sorted(df["e_p_Wh_per_kg_water"].unique())

    summary_rows = []

    for requested_ep in fixed_eps:
        nearest_ep = min(e_values, key=lambda x: abs(x - requested_ep))
        sub_ep = df[np.isclose(df["e_p_Wh_per_kg_water"], nearest_ep)].copy()

        for evap_model, sub_evap in sub_ep.groupby("evap_model"):
            fig, ax = plt.subplots(figsize=(8, 5))

            for case, sub_case in sub_evap.groupby("case"):
                rows = []
                for chi, group in sub_case.groupby("heat_to_process_fraction"):
                    chosen = group.loc[group["savings_pct"].idxmax()]
                    rows.append(
                        {
                            "case": case,
                            "evap_model": evap_model,
                            "requested_ep": requested_ep,
                            "used_ep": nearest_ep,
                            "heat_to_process_fraction": float(chi),
                            "best_savings_pct": float(chosen["savings_pct"]),
                            "f_at_best_savings": float(chosen["f_latent_by_eo"]),
                        }
                    )
                curve = pd.DataFrame(rows).sort_values("heat_to_process_fraction")
                summary_rows.extend(rows)
                ax.plot(
                    curve["heat_to_process_fraction"],
                    curve["best_savings_pct"],
                    marker="o",
                    label=case,
                )

            for line in savings_target_lines:
                ax.axhline(line, color="k", linewidth=0.7, alpha=0.25)
            ax.set_xlabel("Fraction of EO/ACEO electrical input heating process air, chi")
            ax.set_ylabel("Best savings at fixed e_p [%], optimized over f")
            ax.set_title(f"Fixed e_p ≈ {nearest_ep:.1f} Wh/kg, evap_model={evap_model}")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(out_dir / f"fixed_ep_{nearest_ep:.0f}_{evap_model}.png", dpi=200)
            plt.close(fig)

    pd.DataFrame(summary_rows).to_csv(out_dir / "fixed_ep_summary.csv", index=False)


def write_markdown_report(compact: pd.DataFrame, out_path: Path) -> None:
    lines = [
        "# Model 1 robustness report",
        "",
        "This report compares reheat assumptions, evaporator-temperature assumptions, and explicit f-caps.",
        "",
        "Important interpretation:",
        "",
        "- `f_cap = 1.00` allows the exact full-latent-removal transition.",
        "- `f_cap = 0.99` and `f_cap = 0.95` show more conservative partial-removal thresholds.",
        "- `linear_by_fraction` is the optimistic evaporator-temperature interpolation.",
        "- `strict_dewpoint_until_full` is more conservative: the coil stays at the conventional dewpoint evaporator temperature until EO/ACEO removes all latent load.",
        "",
        "## Compact thresholds",
        "",
        "```text",
        compact.to_string(index=False),
        "```",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Model 1.2 robustness analysis.")
    parser.add_argument("--config", default="scenarios/first_model.yaml")
    parser.add_argument("--out", default="outputs/model1_robustness")
    parser.add_argument("--f-start", type=float, default=0.0)
    parser.add_argument("--f-stop", type=float, default=1.0)
    parser.add_argument("--n-f", type=int, default=101)
    parser.add_argument("--ep-start", type=float, default=25.0)
    parser.add_argument("--ep-stop", type=float, default=2000.0)
    parser.add_argument("--n-ep", type=int, default=160)
    parser.add_argument("--heat-fractions", type=float, nargs="+", default=[0.0, 0.25, 0.5, 0.75, 1.0])
    parser.add_argument("--savings-targets", type=float, nargs="+", default=[0.0, 2.0, 5.0, 10.0])
    parser.add_argument("--f-caps", type=float, nargs="+", default=[1.0, 0.99, 0.95])
    parser.add_argument("--fixed-eps", type=float, nargs="+", default=[50, 100, 150, 200, 250, 300, 400, 500])
    parser.add_argument("--evap-models", nargs="+", default=EVAP_MODELS)
    args = parser.parse_args()

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    base_cfg = configure_grid(load_yaml(args.config), args)
    all_frames = []

    for evap_model in args.evap_models:
        for case, info in REHEAT_CASES.items():
            cfg = copy.deepcopy(base_cfg)
            cfg.setdefault("coil", {})["reheat_COP"] = float(info["reheat_COP"])
            cfg["coil"]["hybrid_evap_model"] = evap_model
            cfg.setdefault("metadata", {})["case_description"] = info["description"]
            cfg["metadata"]["evap_model_description"] = evap_model

            case_dir = out_root / evap_model / case
            print(f"Running {case}, evap_model={evap_model}")
            all_frames.append(run_case(cfg, case_dir, case, evap_model))

    all_df = pd.concat(all_frames, ignore_index=True)
    all_df.to_csv(out_root / "all_cases_sensitivity_results.csv", index=False)

    thresholds = thresholds_by_f(all_df, targets=[float(x) for x in args.savings_targets], f_caps=[float(x) for x in args.f_caps])
    thresholds.to_csv(out_root / "thresholds_by_f.csv", index=False)

    compact = compact_thresholds(thresholds)
    compact.to_csv(out_root / "thresholds_compact.csv", index=False)

    plot_threshold_comparison(compact, out_root / "thresholds_5pct_comparison.png", target=5.0)
    plot_threshold_comparison(compact, out_root / "thresholds_10pct_comparison.png", target=10.0)
    plot_fixed_ep_heat_sensitivity(all_df, out_root / "fixed_ep_plots", fixed_eps=[float(x) for x in args.fixed_eps])
    write_markdown_report(compact, out_root / "model1_robustness_report.md")

    print("\nWrote robustness outputs to:", out_root)
    print("\nCompact thresholds:")
    print(compact.to_string(index=False))


if __name__ == "__main__":
    main()
