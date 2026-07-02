from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heiq_thermo.model import load_yaml, run_first_model


def reheat_cop_for_case(case: str) -> float:
    if case == "electric_reheat":
        return 1.0
    if case == "heat_pump_reheat_COP3":
        return 3.0
    if case == "free_reheat":
        return 1.0e12
    raise ValueError(f"Unknown reheat case: {case}")


def configure_model(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("coil", {})["reheat_COP"] = reheat_cop_for_case(args.reheat_case)
    cfg.setdefault("coil", {})["hybrid_evap_model"] = args.evap_model
    cfg.setdefault("eo", {})["fraction_latent_by_eo_grid"] = {
        "start": 0.0,
        "stop": 1.0,
        "n": int(args.n_f),
    }
    cfg["eo"]["e_p_Wh_per_kg_water_grid"] = [float(x) for x in args.e_p_values]
    cfg["eo"]["heat_to_process_fraction_grid"] = [float(args.heat_fraction)]
    return cfg


def fan_power_extra_W(dry_air_flow_kg_s: float, pressure_drop_pa: float, rho_air_kg_m3: float, fan_efficiency: float) -> float:
    if pressure_drop_pa <= 0:
        return 0.0
    volumetric_flow_m3_s = dry_air_flow_kg_s / rho_air_kg_m3
    return pressure_drop_pa * volumetric_flow_m3_s / max(fan_efficiency, 1e-9)


def best_savings_for_cell(
    model_rows: pd.DataFrame,
    e_p: float,
    f_max: float,
    dry_air_flow_kg_s: float,
    base_dry_air_flow_kg_s: float,
    pressure_drop_pa: float,
    rho_air_kg_m3: float,
    fan_efficiency: float,
    require_positive_eo: bool,
) -> tuple[float, float]:
    """Return best savings and chosen f for a given area/flow-limited f_max."""
    eps = 1e-9
    sub = model_rows[np.isclose(model_rows["e_p_Wh_per_kg_water"], e_p)].copy()
    if require_positive_eo:
        sub = sub[sub["f_latent_by_eo"] > eps]
    sub = sub[sub["f_latent_by_eo"] <= f_max + eps]
    if sub.empty:
        return float("nan"), float("nan")

    scale = dry_air_flow_kg_s / base_dry_air_flow_kg_s
    fan_W = fan_power_extra_W(dry_air_flow_kg_s, pressure_drop_pa, rho_air_kg_m3, fan_efficiency)

    conv_P = sub["conventional_P_total_W"] * scale
    hybrid_P = sub["hybrid_P_total_W"] * scale + fan_W
    savings = 100.0 * (conv_P - hybrid_P) / conv_P

    idx = savings.idxmax()
    return float(savings.loc[idx]), float(sub.loc[idx, "f_latent_by_eo"])


def make_max_airflow_table(
    model_rows: pd.DataFrame,
    summary: dict[str, Any],
    args: argparse.Namespace,
) -> pd.DataFrame:
    base_mda = float(summary["dry_air_mass_flow_kg_s"])
    delta_w_kg_per_kg = float(summary["delta_w_g_per_kg_da"]) / 1000.0

    dry_air_grid = np.geomspace(float(args.dry_air_start), float(args.dry_air_stop), int(args.n_air))

    rows: list[dict[str, Any]] = []
    for target_saving in args.target_savings:
        for e_p in args.e_p_values:
            for flux in args.flux_values:
                for area_limit in args.area_limits:
                    best_mda = np.nan
                    best_saving = np.nan
                    best_f = np.nan
                    best_water_kg_h = np.nan
                    for mda in dry_air_grid:
                        total_water_g_h = mda * delta_w_kg_per_kg * 3600.0 * 1000.0
                        if total_water_g_h <= 0:
                            continue
                        f_max = min(1.0, (float(area_limit) * float(flux)) / total_water_g_h)
                        if f_max <= 0:
                            continue
                        savings, chosen_f = best_savings_for_cell(
                            model_rows=model_rows,
                            e_p=float(e_p),
                            f_max=f_max,
                            dry_air_flow_kg_s=float(mda),
                            base_dry_air_flow_kg_s=base_mda,
                            pressure_drop_pa=float(args.pressure_drop_pa),
                            rho_air_kg_m3=float(args.rho_air_kg_m3),
                            fan_efficiency=float(args.fan_efficiency),
                            require_positive_eo=bool(args.require_positive_eo),
                        )
                        if np.isfinite(savings) and savings >= float(target_saving):
                            best_mda = float(mda)
                            best_saving = float(savings)
                            best_f = float(chosen_f)
                            best_water_kg_h = total_water_g_h / 1000.0
                    rows.append(
                        {
                            "target_savings_pct": float(target_saving),
                            "e_p_Wh_per_kg_water": float(e_p),
                            "flux_g_m2_h": float(flux),
                            "area_limit_m2": float(area_limit),
                            "max_dry_air_flow_kg_s": best_mda,
                            "water_load_at_max_flow_kg_h": best_water_kg_h,
                            "best_savings_at_max_flow_pct": best_saving,
                            "best_f_at_max_flow": best_f,
                        }
                    )
    return pd.DataFrame(rows)


def plot_max_airflow_curves(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for (target, e_p), sub in df.groupby(["target_savings_pct", "e_p_Wh_per_kg_water"]):
        fig, ax = plt.subplots(figsize=(8, 5))
        for flux, g in sub.groupby("flux_g_m2_h"):
            g = g.sort_values("area_limit_m2")
            ax.plot(g["area_limit_m2"], g["max_dry_air_flow_kg_s"], marker="o", label=f"J={flux:g} g/(m² h)")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Available active membrane area [m²]")
        ax.set_ylabel("Max dry-air flow meeting target [kg_da/s]")
        ax.set_title(f"Max air flow for >= {target:g}% saving, e_p={e_p:g} Wh/kg")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(out_dir / f"max_airflow_target_{target:g}_ep_{e_p:g}.png", dpi=200)
        plt.close(fig)


def plot_required_area_for_airflow(df: pd.DataFrame, out_dir: Path) -> None:
    """Invert max-flow table approximately: for each e_p, target, flux, show min area for selected air flows."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for (target, e_p), sub in df.groupby(["target_savings_pct", "e_p_Wh_per_kg_water"]):
        fig, ax = plt.subplots(figsize=(8, 5))
        for flux, g in sub.groupby("flux_g_m2_h"):
            g = g.sort_values("area_limit_m2")
            ax.plot(g["max_dry_air_flow_kg_s"], g["area_limit_m2"], marker="o", label=f"J={flux:g} g/(m² h)")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Max dry-air flow meeting target [kg_da/s]")
        ax.set_ylabel("Available active membrane area [m²]")
        ax.set_title(f"Area/flow scaling for >= {target:g}% saving, e_p={e_p:g} Wh/kg")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(out_dir / f"area_flow_scaling_target_{target:g}_ep_{e_p:g}.png", dpi=200)
        plt.close(fig)


def write_report(df: pd.DataFrame, summary: dict[str, Any], args: argparse.Namespace, out_path: Path) -> None:
    delta_w = float(summary["delta_w_g_per_kg_da"])
    base_mda = float(summary["dry_air_mass_flow_kg_s"])
    start = summary["start"]
    target = summary["target"]

    lines: list[str] = []
    lines.append("# Model 2 application scaling report")
    lines.append("")
    lines.append("This report maps active area and flux to the maximum dry-air flow that can be treated while still meeting a savings target.")
    lines.append("")
    lines.append("## Scenario")
    lines.append("")
    lines.append(f"- Base dry-air flow in scenario file: {base_mda:g} kg_da/s")
    lines.append(f"- Start: {start.T_C:.2f} C, RH={100*start.RH:.1f} %, w={start.w_g_per_kg_da:.3f} g/kg_da")
    lines.append(f"- Target: {target.T_C:.2f} C, RH={100*target.RH:.1f} %, w={target.w_g_per_kg_da:.3f} g/kg_da")
    lines.append(f"- Water to remove per kg dry air: {delta_w:.3f} g/kg_da")
    lines.append(f"- Reheat case: {args.reheat_case}")
    lines.append(f"- Evap model: {args.evap_model}")
    lines.append(f"- Heat-to-process fraction chi: {args.heat_fraction:g}")
    lines.append(f"- Extra pressure drop: {args.pressure_drop_pa:g} Pa")
    lines.append("")
    lines.append("## Max dry-air flow table")
    lines.append("")
    lines.append("Rows show the largest dry-air mass flow in the search grid that meets each target.")
    lines.append("")
    compact = df.copy()
    compact = compact.sort_values(["target_savings_pct", "e_p_Wh_per_kg_water", "flux_g_m2_h", "area_limit_m2"])
    lines.append("```text")
    lines.append(compact.to_string(index=False))
    lines.append("```")
    lines.append("")
    lines.append("## Practical interpretation")
    lines.append("")
    lines.append("At fixed psychrometric inlet/target conditions, the central scale parameter is approximately:")
    lines.append("")
    lines.append("```text")
    lines.append("water_load_per_area = dry_air_flow * delta_w / active_area")
    lines.append("```")
    lines.append("")
    lines.append("Thus a case with 1 kg_da/s and 100 m2 area is similar to 0.1 kg_da/s and 10 m2 area.")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Application scaling map: air-flow capacity vs area, flux and EO/ACEO energy.")
    parser.add_argument("--config", default="scenarios/first_model.yaml")
    parser.add_argument("--out", default="outputs/model2_application_scaling")
    parser.add_argument("--reheat-case", default="free_reheat", choices=["free_reheat", "heat_pump_reheat_COP3", "electric_reheat"])
    parser.add_argument("--evap-model", default="strict_dewpoint_until_full", choices=["strict_dewpoint_until_full", "linear_by_fraction"])
    parser.add_argument("--heat-fraction", type=float, default=0.5)
    parser.add_argument("--pressure-drop-pa", type=float, default=50.0)
    parser.add_argument("--rho-air-kg-m3", type=float, default=1.18)
    parser.add_argument("--fan-efficiency", type=float, default=0.55)
    parser.add_argument("--n-f", type=int, default=101)
    parser.add_argument("--dry-air-start", type=float, default=0.02)
    parser.add_argument("--dry-air-stop", type=float, default=2.0)
    parser.add_argument("--n-air", type=int, default=120)
    parser.add_argument("--area-limits", type=float, nargs="+", default=[1, 2, 5, 10, 20, 50, 100, 300])
    parser.add_argument("--flux-values", type=float, nargs="+", default=[100, 200, 500, 1000, 3000, 5000, 10000])
    parser.add_argument("--e-p-values", type=float, nargs="+", default=[50, 100, 150, 200])
    parser.add_argument("--target-savings", type=float, nargs="+", default=[2, 5, 10])
    parser.add_argument("--require-positive-eo", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = configure_model(load_yaml(args.config), args)
    model_rows, summary = run_first_model(cfg)
    model_rows.to_csv(out_dir / "base_energy_rows.csv", index=False)

    table = make_max_airflow_table(model_rows, summary, args)
    table.to_csv(out_dir / "max_airflow_by_area_flux.csv", index=False)

    plot_max_airflow_curves(table, out_dir / "max_airflow_plots")
    plot_required_area_for_airflow(table, out_dir / "area_flow_plots")
    write_report(table, summary, args, out_dir / "application_scaling_report.md")

    print("Wrote application scaling outputs to:", out_dir)
    print("\nShort preview:")
    print(table.head(30).to_string(index=False))


if __name__ == "__main__":
    main()
