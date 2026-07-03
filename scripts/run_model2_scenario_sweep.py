from __future__ import annotations

import argparse
import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from heiq_thermo.psychrometrics import state_from_T_RH


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def write_yaml(data: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def scenario_items(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    scenarios = data.get("scenarios", data)
    if not isinstance(scenarios, dict):
        raise ValueError("Scenario file must contain a 'scenarios' mapping or be a mapping itself.")
    out: list[tuple[str, dict[str, Any]]] = []
    for name, spec in scenarios.items():
        if not isinstance(spec, dict):
            raise ValueError(f"Scenario {name!r} must be a mapping")
        for key in ["start", "target"]:
            if key not in spec or not isinstance(spec[key], dict):
                raise ValueError(f"Scenario {name!r} must include {key}: {{T_C, RH}}")
            if "T_C" not in spec[key] or "RH" not in spec[key]:
                raise ValueError(f"Scenario {name!r} {key!r} must include T_C and RH")
        out.append((str(name), spec))
    return out


def make_config_for_scenario(base_cfg: dict[str, Any], spec: dict[str, Any], dry_air_mass_flow: float | None) -> dict[str, Any]:
    cfg = copy.deepcopy(base_cfg)
    cfg["start"] = {
        "T_C": float(spec["start"]["T_C"]),
        "RH": float(spec["start"]["RH"]),
    }
    cfg["target"] = {
        "T_C": float(spec["target"]["T_C"]),
        "RH": float(spec["target"]["RH"]),
    }
    if dry_air_mass_flow is not None:
        cfg.setdefault("air", {})["dry_air_mass_flow_kg_s"] = float(dry_air_mass_flow)
    cfg.setdefault("metadata", {})["scenario_description"] = str(spec.get("description", ""))
    return cfg


def scenario_psychrometric_summary(name: str, spec: dict[str, Any], pressure_pa: float) -> dict[str, Any]:
    start = state_from_T_RH(float(spec["start"]["T_C"]), float(spec["start"]["RH"]), pressure_pa)
    target = state_from_T_RH(float(spec["target"]["T_C"]), float(spec["target"]["RH"]), pressure_pa)
    delta_w = start.w - target.w
    return {
        "scenario": name,
        "description": spec.get("description", ""),
        "start_T_C": start.T_C,
        "start_RH_pct": 100.0 * start.RH,
        "start_w_g_per_kg_da": start.w_g_per_kg_da,
        "start_h_kJ_per_kg_da": start.h_kJ_per_kg_da,
        "start_dew_point_C": start.dew_point_C,
        "target_T_C": target.T_C,
        "target_RH_pct": 100.0 * target.RH,
        "target_w_g_per_kg_da": target.w_g_per_kg_da,
        "target_h_kJ_per_kg_da": target.h_kJ_per_kg_da,
        "target_dew_point_C": target.dew_point_C,
        "delta_w_g_per_kg_da": 1000.0 * delta_w,
        "delta_h_kJ_per_kg_da": target.h_kJ_per_kg_da - start.h_kJ_per_kg_da,
        "water_load_kg_h_per_kg_da_s": delta_w * 3600.0,
        "valid_dehumidification_case": bool(delta_w > 0),
    }


def run_command(cmd: list[str], cwd: Path, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("COMMAND:\n")
        f.write(" ".join(cmd) + "\n\n")
        proc = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}. See log: {log_path}")


def plot_scenario_severity(summary: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_df = summary.sort_values("delta_w_g_per_kg_da", ascending=False)
    ax.bar(plot_df["scenario"], plot_df["delta_w_g_per_kg_da"])
    ax.set_ylabel("Water to remove [g/kg dry air]")
    ax.set_title("Scenario latent-load severity")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "scenario_delta_w.png", dpi=220)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(plot_df["scenario"], plot_df["water_load_kg_h_per_kg_da_s"])
    ax.set_ylabel("Water load per 1 kg_da/s [kg/h]")
    ax.set_title("Water load per unit dry-air flow")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "scenario_water_load_per_flow.png", dpi=220)
    plt.close(fig)


def plot_min_area_by_scenario(all_area: pd.DataFrame, out_dir: Path, desired_flow: float, target: float, ep: float, fluxes: list[float]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = all_area[
        np.isclose(all_area["desired_dry_air_flow_kg_s"], desired_flow)
        & np.isclose(all_area["target_savings_pct"], target)
        & np.isclose(all_area["e_p_Wh_per_kg_water"], ep)
        & all_area["flux_g_m2_h"].isin(fluxes)
    ].copy()
    if df.empty:
        return
    scenarios = list(df["scenario"].drop_duplicates())
    x = np.arange(len(scenarios))
    width = 0.8 / max(len(fluxes), 1)
    fig, ax = plt.subplots(figsize=(max(10, 1.3 * len(scenarios)), 6))
    for k, flux in enumerate(fluxes):
        vals = []
        for scen in scenarios:
            sub = df[(df["scenario"] == scen) & np.isclose(df["flux_g_m2_h"], flux)]
            vals.append(float(sub["min_area_m2"].iloc[0]) if not sub.empty else np.nan)
        ax.bar(x + (k - (len(fluxes) - 1) / 2) * width, vals, width, label=f"J={flux:g}")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=35, ha="right")
    ax.set_ylabel("Minimum active area [m²]")
    ax.set_title(f"Minimum area by scenario: flow={desired_flow:g} kg_da/s, target={target:g}%, e_p={ep:g} Wh/kg")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="Flux [g/(m² h)]")
    fig.tight_layout()
    fig.savefig(out_dir / f"min_area_by_scenario_flow_{desired_flow:g}_target_{target:g}_ep_{ep:g}.png", dpi=220)
    plt.close(fig)


def plot_min_flux_by_scenario(all_flux: pd.DataFrame, out_dir: Path, desired_flow: float, target: float, ep: float, areas: list[float]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = all_flux[
        np.isclose(all_flux["desired_dry_air_flow_kg_s"], desired_flow)
        & np.isclose(all_flux["target_savings_pct"], target)
        & np.isclose(all_flux["e_p_Wh_per_kg_water"], ep)
        & all_flux["area_limit_m2"].isin(areas)
    ].copy()
    if df.empty:
        return
    scenarios = list(df["scenario"].drop_duplicates())
    x = np.arange(len(scenarios))
    width = 0.8 / max(len(areas), 1)
    fig, ax = plt.subplots(figsize=(max(10, 1.3 * len(scenarios)), 6))
    for k, area in enumerate(areas):
        vals = []
        for scen in scenarios:
            sub = df[(df["scenario"] == scen) & np.isclose(df["area_limit_m2"], area)]
            vals.append(float(sub["min_flux_g_m2_h"].iloc[0]) if not sub.empty else np.nan)
        ax.bar(x + (k - (len(areas) - 1) / 2) * width, vals, width, label=f"A={area:g}")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=35, ha="right")
    ax.set_ylabel("Minimum flux [g/(m² h)]")
    ax.set_title(f"Minimum flux by scenario: flow={desired_flow:g} kg_da/s, target={target:g}%, e_p={ep:g} Wh/kg")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="Area [m²]")
    fig.tight_layout()
    fig.savefig(out_dir / f"min_flux_by_scenario_flow_{desired_flow:g}_target_{target:g}_ep_{ep:g}.png", dpi=220)
    plt.close(fig)


def write_report(out_path: Path, scenario_summary: pd.DataFrame, all_area: pd.DataFrame, all_flux: pd.DataFrame, args: argparse.Namespace) -> None:
    lines: list[str] = []
    lines.append("# Model 2 scenario sweep report")
    lines.append("")
    lines.append("This report repeats the Model 2 application-scaling decision tables across multiple psychrometric scenarios.")
    lines.append("")
    lines.append("## Scenario severity")
    lines.append("")
    cols = [
        "scenario",
        "start_T_C",
        "start_RH_pct",
        "target_T_C",
        "target_RH_pct",
        "delta_w_g_per_kg_da",
        "water_load_kg_h_per_kg_da_s",
    ]
    lines.append("```text")
    lines.append(scenario_summary[cols].to_string(index=False))
    lines.append("```")
    lines.append("")
    lines.append("## Selected minimum-area table")
    lines.append("")
    selected_area = all_area[
        all_area["target_savings_pct"].isin(args.report_targets)
        & all_area["e_p_Wh_per_kg_water"].isin(args.report_eps)
        & all_area["flux_g_m2_h"].isin(args.report_fluxes)
        & all_area["desired_dry_air_flow_kg_s"].isin(args.report_flows)
    ].copy()
    area_cols = [
        "scenario",
        "target_savings_pct",
        "e_p_Wh_per_kg_water",
        "flux_g_m2_h",
        "desired_dry_air_flow_kg_s",
        "min_area_m2",
        "best_f_at_min_area",
        "regime",
    ]
    lines.append("```text")
    lines.append(selected_area[area_cols].to_string(index=False))
    lines.append("```")
    lines.append("")
    lines.append("## Selected minimum-flux table")
    lines.append("")
    selected_flux = all_flux[
        all_flux["target_savings_pct"].isin(args.report_targets)
        & all_flux["e_p_Wh_per_kg_water"].isin(args.report_eps)
        & all_flux["area_limit_m2"].isin(args.report_areas)
        & all_flux["desired_dry_air_flow_kg_s"].isin(args.report_flows)
    ].copy()
    flux_cols = [
        "scenario",
        "target_savings_pct",
        "e_p_Wh_per_kg_water",
        "area_limit_m2",
        "desired_dry_air_flow_kg_s",
        "min_flux_g_m2_h",
        "best_f_at_min_flux",
        "regime",
    ]
    lines.append("```text")
    lines.append(selected_flux[flux_cols].to_string(index=False))
    lines.append("```")
    lines.append("")
    lines.append("## Practical interpretation")
    lines.append("")
    lines.append("At fixed target savings, required area and required flux scale strongly with latent-load severity (`delta_w`).")
    lines.append("Use this scenario sweep to decide whether the first product should target hot-humid full HVAC loads, smaller modular flows, or shoulder-season humidity control.")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Model 2 application-scaling across multiple psychrometric scenarios.")
    parser.add_argument("--base-config", default="scenarios/first_model.yaml")
    parser.add_argument("--scenarios", default="scenarios/climate_scenarios.yaml")
    parser.add_argument("--out", default="outputs/model2_scenario_sweep")

    parser.add_argument("--reheat-case", default="free_reheat")
    parser.add_argument("--evap-model", default="strict_dewpoint_until_full")
    parser.add_argument("--heat-fraction", type=float, default=0.5)
    parser.add_argument("--pressure-drop-pa", type=float, default=50.0)
    parser.add_argument("--dry-air-start", type=float, default=0.01)
    parser.add_argument("--dry-air-stop", type=float, default=10.0)
    parser.add_argument("--n-air", type=int, default=180)
    parser.add_argument("--base-dry-air-flow-kg-s", type=float, default=1.0)

    parser.add_argument("--area-limits", type=float, nargs="+", default=[1, 2, 5, 10, 20, 50, 100, 300])
    parser.add_argument("--flux-values", type=float, nargs="+", default=[100, 200, 500, 1000, 3000, 5000, 10000])
    parser.add_argument("--e-p-values", type=float, nargs="+", default=[50, 100, 150, 200])
    parser.add_argument("--target-savings", type=float, nargs="+", default=[2, 5, 10])
    parser.add_argument("--desired-flows", type=float, nargs="+", default=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10])

    parser.add_argument("--report-flows", type=float, nargs="+", default=[0.1, 0.5, 1.0])
    parser.add_argument("--report-targets", type=float, nargs="+", default=[5, 10])
    parser.add_argument("--report-eps", type=float, nargs="+", default=[50, 100, 150, 200])
    parser.add_argument("--report-fluxes", type=float, nargs="+", default=[500, 1000, 3000])
    parser.add_argument("--report-areas", type=float, nargs="+", default=[10, 20, 50])

    parser.add_argument("--skip-existing", action="store_true", help="Skip scenario subruns if their decision-table outputs already exist.")
    parser.add_argument("--require-positive-eo", action="store_true", default=True)
    parser.add_argument("--no-require-positive-eo", dest="require_positive_eo", action="store_false")

    args = parser.parse_args()

    repo_root = Path.cwd()
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    base_cfg = load_yaml(args.base_config)
    scenario_data = load_yaml(args.scenarios)
    scenarios = scenario_items(scenario_data)

    pressure_pa = float(base_cfg.get("pressure_pa", 101325.0))
    summaries = []
    area_frames: list[pd.DataFrame] = []
    flux_frames: list[pd.DataFrame] = []

    for name, spec in scenarios:
        print(f"\n=== Scenario: {name} ===")
        summaries.append(scenario_psychrometric_summary(name, spec, pressure_pa))
        summary = summaries[-1]
        if not summary["valid_dehumidification_case"]:
            print(f"Skipping {name}: target has higher/equal humidity ratio than start.")
            continue

        scen_dir = out_root / "scenario_runs" / name
        config_path = out_root / "configs" / f"{name}.yaml"
        cfg = make_config_for_scenario(base_cfg, spec, args.base_dry_air_flow_kg_s)
        write_yaml(cfg, config_path)

        scaling_out = scen_dir / "application_scaling"
        decision_out = scen_dir / "decision_tables"
        decision_area_csv = decision_out / "min_area_for_desired_flows.csv"
        decision_flux_csv = decision_out / "min_flux_for_desired_flows.csv"

        if not (args.skip_existing and decision_area_csv.exists() and decision_flux_csv.exists()):
            scaling_cmd = [
                sys.executable,
                "scripts/run_model2_load_area_scaling.py",
                "--config", str(config_path),
                "--out", str(scaling_out),
                "--reheat-case", args.reheat_case,
                "--evap-model", args.evap_model,
                "--heat-fraction", str(args.heat_fraction),
                "--pressure-drop-pa", str(args.pressure_drop_pa),
                "--dry-air-start", str(args.dry_air_start),
                "--dry-air-stop", str(args.dry_air_stop),
                "--n-air", str(args.n_air),
                "--area-limits", *[str(x) for x in args.area_limits],
                "--flux-values", *[str(x) for x in args.flux_values],
                "--e-p-values", *[str(x) for x in args.e_p_values],
                "--target-savings", *[str(x) for x in args.target_savings],
            ]
            if args.require_positive_eo:
                scaling_cmd.append("--require-positive-eo")
            run_command(scaling_cmd, repo_root, scen_dir / "logs" / "run_model2_load_area_scaling.log")

            decision_cmd = [
                sys.executable,
                "scripts/make_application_decision_tables.py",
                "--input", str(scaling_out / "max_airflow_by_area_flux.csv"),
                "--out", str(decision_out),
                "--search-max-flow", str(args.dry_air_stop),
                "--desired-flows", *[str(x) for x in args.desired_flows],
                "--report-flows", *[str(x) for x in args.report_flows],
                "--report-targets", *[str(x) for x in args.report_targets],
                "--report-eps", *[str(x) for x in args.report_eps],
                "--report-fluxes", *[str(x) for x in args.report_fluxes],
                "--report-areas", *[str(x) for x in args.report_areas],
            ]
            run_command(decision_cmd, repo_root, scen_dir / "logs" / "make_application_decision_tables.log")

        area = pd.read_csv(decision_area_csv)
        flux = pd.read_csv(decision_flux_csv)
        for df in [area, flux]:
            df.insert(0, "scenario", name)
            df.insert(1, "description", spec.get("description", ""))
            df.insert(2, "start_T_C", float(spec["start"]["T_C"]))
            df.insert(3, "start_RH", float(spec["start"]["RH"]))
            df.insert(4, "target_T_C", float(spec["target"]["T_C"]))
            df.insert(5, "target_RH", float(spec["target"]["RH"]))
            df.insert(6, "delta_w_g_per_kg_da", summary["delta_w_g_per_kg_da"])
        area_frames.append(area)
        flux_frames.append(flux)

    scenario_summary = pd.DataFrame(summaries).sort_values("delta_w_g_per_kg_da", ascending=False)
    scenario_summary.to_csv(out_root / "scenario_summary.csv", index=False)
    plot_scenario_severity(scenario_summary, out_root / "plots")

    if not area_frames or not flux_frames:
        raise RuntimeError("No scenario runs produced decision tables.")

    all_area = pd.concat(area_frames, ignore_index=True)
    all_flux = pd.concat(flux_frames, ignore_index=True)
    all_area.to_csv(out_root / "all_min_area_for_desired_flows.csv", index=False)
    all_flux.to_csv(out_root / "all_min_flux_for_desired_flows.csv", index=False)

    # A few compact cross-scenario plots for discussion.
    for target in args.report_targets:
        for ep in [x for x in args.report_eps if x in [50, 100, 150]]:
            plot_min_area_by_scenario(
                all_area,
                out_root / "plots" / "min_area_by_scenario",
                desired_flow=1.0,
                target=float(target),
                ep=float(ep),
                fluxes=[x for x in args.report_fluxes],
            )
            plot_min_flux_by_scenario(
                all_flux,
                out_root / "plots" / "min_flux_by_scenario",
                desired_flow=1.0,
                target=float(target),
                ep=float(ep),
                areas=[x for x in args.report_areas],
            )

    write_report(out_root / "scenario_sweep_report.md", scenario_summary, all_area, all_flux, args)

    print("\nWrote scenario sweep outputs to:", out_root)
    print("\nScenario summary:")
    print(scenario_summary[["scenario", "delta_w_g_per_kg_da", "water_load_kg_h_per_kg_da_s"]].to_string(index=False))
    print("\nReport:", out_root / "scenario_sweep_report.md")


if __name__ == "__main__":
    main()
