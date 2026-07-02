from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from heiq_thermo.model import load_yaml, run_first_model
from heiq_thermo.processes import states_from_scenario


R_DRY_AIR_J_KG_K = 287.055

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


@dataclass(frozen=True)
class ScenarioKey:
    case: str
    evap_model: str
    heat_to_process_fraction: float
    pressure_drop_pa: float
    area_limit_m2: float

    def slug(self) -> str:
        area = "inf" if not np.isfinite(self.area_limit_m2) else f"{self.area_limit_m2:g}m2"
        return (
            f"{self.case}__{self.evap_model}__chi_{self.heat_to_process_fraction:.2f}"
            f"__dp_{self.pressure_drop_pa:g}Pa__A_{area}"
        ).replace(".", "p")


def linear_grid(start: float, stop: float, n: int) -> list[float]:
    return [float(x) for x in np.linspace(float(start), float(stop), int(n))]


def log_grid(start: float, stop: float, n: int) -> list[float]:
    return [float(x) for x in np.geomspace(float(start), float(stop), int(n))]


def moist_air_specific_volume_m3_per_kg_da(T_C: float, w: float, p_total_pa: float) -> float:
    """Approximate moist-air specific volume [m3/kg dry air]."""
    T_K = T_C + 273.15
    return R_DRY_AIR_J_KG_K * T_K * (1.0 + 1.6078 * w) / p_total_pa


def module_fan_power_W(
    dry_air_flow_kg_s: float,
    start_T_C: float,
    start_w: float,
    p_total_pa: float,
    pressure_drop_pa: float,
    fan_efficiency: float,
    airflow_multiplier: float,
) -> float:
    """Extra fan power from the EO/ACEO module.

    airflow_multiplier = 1 means only process-side airflow passes the EO module.
    airflow_multiplier = 2 can represent process + purge/reject stream of equal flow.
    """
    if pressure_drop_pa <= 0:
        return 0.0
    if fan_efficiency <= 0:
        raise ValueError("fan_efficiency must be positive")
    v_spec = moist_air_specific_volume_m3_per_kg_da(start_T_C, start_w, p_total_pa)
    vdot = dry_air_flow_kg_s * v_spec * airflow_multiplier
    return pressure_drop_pa * vdot / fan_efficiency


def required_area_m2(water_removed_kg_s: pd.Series | np.ndarray, flux_g_m2_h: float) -> np.ndarray:
    if flux_g_m2_h <= 0:
        return np.full_like(np.asarray(water_removed_kg_s, dtype=float), np.inf)
    return np.asarray(water_removed_kg_s, dtype=float) * 3600.0 * 1000.0 / float(flux_g_m2_h)


def configure_for_case(
    base_cfg: dict[str, Any],
    key: ScenarioKey,
    f_values: list[float],
    e_p_values: list[float],
) -> dict[str, Any]:
    cfg = copy.deepcopy(base_cfg)
    cfg.setdefault("metadata", {})["combined_feasibility_case"] = key.slug()
    cfg.setdefault("coil", {})["reheat_COP"] = float(REHEAT_CASES[key.case]["reheat_COP"])
    cfg.setdefault("coil", {})["hybrid_evap_model"] = key.evap_model
    cfg.setdefault("eo", {})["fraction_latent_by_eo_grid"] = f_values
    cfg.setdefault("eo", {})["e_p_Wh_per_kg_water_grid"] = e_p_values
    cfg.setdefault("eo", {})["heat_to_process_fraction_grid"] = [float(key.heat_to_process_fraction)]
    return cfg


def best_rows_for_flux(
    base_df: pd.DataFrame,
    flux_g_m2_h: float,
    key: ScenarioKey,
    fan_power_when_active_W: float,
    require_positive_eo: bool,
) -> pd.DataFrame:
    """For each e_p and flux, select f that gives best adjusted savings.

    Area-limit filtering is applied before selecting best f. If no f is feasible,
    a NaN row is returned for that e_p/flux.
    """
    df = base_df.copy()

    water = df["hybrid_water_removed_by_eo_kg_s"].to_numpy(dtype=float)
    area = required_area_m2(water, flux_g_m2_h)
    active = water > 1e-12
    fan = np.where(active, fan_power_when_active_W, 0.0)
    adjusted_total = df["hybrid_P_total_W"].to_numpy(dtype=float) + fan
    conv = df["conventional_P_total_W"].to_numpy(dtype=float)
    adjusted_savings = 100.0 * (conv - adjusted_total) / conv

    df["flux_g_m2_h"] = float(flux_g_m2_h)
    df["required_area_m2"] = area
    df["extra_fan_power_W"] = fan
    df["hybrid_P_total_with_fan_W"] = adjusted_total
    df["savings_with_fan_pct"] = adjusted_savings
    df["area_feasible"] = area <= float(key.area_limit_m2)
    df["active_eo"] = active

    if require_positive_eo:
        df = df[df["active_eo"]].copy()

    if np.isfinite(key.area_limit_m2):
        df = df[df["area_feasible"]].copy()

    rows: list[dict[str, Any]] = []
    for e_p in sorted(base_df["e_p_Wh_per_kg_water"].unique()):
        sub = df[df["e_p_Wh_per_kg_water"] == e_p]
        if sub.empty:
            rows.append(
                {
                    "e_p_Wh_per_kg_water": float(e_p),
                    "flux_g_m2_h": float(flux_g_m2_h),
                    "best_savings_with_fan_pct": np.nan,
                    "best_f_latent_by_eo": np.nan,
                    "required_area_m2": np.nan,
                    "water_removed_by_eo_kg_h": np.nan,
                    "P_eo_W": np.nan,
                    "P_eo_per_area_W_m2": np.nan,
                    "extra_fan_power_W": fan_power_when_active_W,
                    "hybrid_P_total_with_fan_W": np.nan,
                    "conventional_P_total_W": float(base_df["conventional_P_total_W"].iloc[0]),
                    "area_feasible": False,
                }
            )
            continue

        idx = sub["savings_with_fan_pct"].idxmax()
        best = sub.loc[idx]
        area_best = float(best["required_area_m2"])
        P_eo = float(best["hybrid_P_eo_W"])
        power_density = P_eo / area_best if area_best > 0 and np.isfinite(area_best) else np.nan
        rows.append(
            {
                "e_p_Wh_per_kg_water": float(e_p),
                "flux_g_m2_h": float(flux_g_m2_h),
                "best_savings_with_fan_pct": float(best["savings_with_fan_pct"]),
                "best_f_latent_by_eo": float(best["f_latent_by_eo"]),
                "required_area_m2": area_best,
                "water_removed_by_eo_kg_h": float(best["hybrid_water_removed_by_eo_kg_s"] * 3600.0),
                "P_eo_W": P_eo,
                "P_eo_per_area_W_m2": power_density,
                "extra_fan_power_W": float(best["extra_fan_power_W"]),
                "hybrid_P_total_with_fan_W": float(best["hybrid_P_total_with_fan_W"]),
                "conventional_P_total_W": float(best["conventional_P_total_W"]),
                "area_feasible": bool(best["area_feasible"]),
            }
        )
    return pd.DataFrame(rows)


def run_combined_feasibility(config: dict[str, Any], args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, float]]:
    start, target = states_from_scenario(config)
    dry_air_flow = float(config["air"]["dry_air_mass_flow_kg_s"])
    water_total_kg_s = dry_air_flow * max(0.0, start.w - target.w)
    fan_power_cache: dict[float, float] = {}

    f_values = linear_grid(args.f_start, args.f_stop, args.n_f)
    e_p_values = linear_grid(args.ep_start, args.ep_stop, args.n_ep)
    flux_values = log_grid(args.flux_start, args.flux_stop, args.n_flux)

    results: list[pd.DataFrame] = []

    for case in args.reheat_cases:
        if case not in REHEAT_CASES:
            raise ValueError(f"Unknown reheat case: {case}. Valid: {list(REHEAT_CASES)}")
        for evap_model in args.evap_models:
            if evap_model not in EVAP_MODELS:
                raise ValueError(f"Unknown evap model: {evap_model}. Valid: {EVAP_MODELS}")
            for chi in args.heat_fractions:
                for dp in args.pressure_drop_values:
                    if dp not in fan_power_cache:
                        fan_power_cache[dp] = module_fan_power_W(
                            dry_air_flow_kg_s=dry_air_flow,
                            start_T_C=start.T_C,
                            start_w=start.w,
                            p_total_pa=start.p_total_pa,
                            pressure_drop_pa=float(dp),
                            fan_efficiency=float(args.fan_efficiency),
                            airflow_multiplier=float(args.airflow_multiplier),
                        )
                    fan_power = fan_power_cache[dp]

                    for area_limit in args.area_limits:
                        key = ScenarioKey(
                            case=case,
                            evap_model=evap_model,
                            heat_to_process_fraction=float(chi),
                            pressure_drop_pa=float(dp),
                            area_limit_m2=float(area_limit),
                        )
                        print(f"Running {key.slug()}")
                        cfg = configure_for_case(config, key, f_values, e_p_values)
                        base_df, _summary = run_first_model(cfg)
                        base_df = base_df.copy()
                        parts = []
                        for flux in flux_values:
                            parts.append(
                                best_rows_for_flux(
                                    base_df=base_df,
                                    flux_g_m2_h=float(flux),
                                    key=key,
                                    fan_power_when_active_W=fan_power,
                                    require_positive_eo=bool(args.require_positive_eo),
                                )
                            )
                        combined = pd.concat(parts, ignore_index=True)
                        combined.insert(0, "case", case)
                        combined.insert(1, "evap_model", evap_model)
                        combined.insert(2, "heat_to_process_fraction", float(chi))
                        combined.insert(3, "pressure_drop_pa", float(dp))
                        combined.insert(4, "area_limit_m2", float(area_limit))
                        results.append(combined)

    out = pd.concat(results, ignore_index=True)
    summary = {
        "dry_air_flow_kg_s": dry_air_flow,
        "start_T_C": start.T_C,
        "start_RH": start.RH,
        "start_w_g_per_kg_da": start.w_g_per_kg_da,
        "target_T_C": target.T_C,
        "target_RH": target.RH,
        "target_w_g_per_kg_da": target.w_g_per_kg_da,
        "water_total_kg_s": water_total_kg_s,
        "water_total_kg_h": water_total_kg_s * 3600.0,
    }
    return out, summary


def summarize_available_flux(results: pd.DataFrame, targets: list[float], ep_milestones: list[float], flux_milestones: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Produce decision tables from combined feasibility results.

    Table A: for each available flux cap, what is the highest e_p that works?
    Table B: for each e_p milestone, what is the minimum flux that works?
    """
    scenario_cols = ["case", "evap_model", "heat_to_process_fraction", "pressure_drop_pa", "area_limit_m2"]

    rows_a: list[dict[str, Any]] = []
    rows_b: list[dict[str, Any]] = []

    for scenario_key, group in results.groupby(scenario_cols):
        scenario = dict(zip(scenario_cols, scenario_key))
        for target in targets:
            ok_target = group[group["best_savings_with_fan_pct"] >= float(target)]

            for flux_cap in flux_milestones:
                ok = ok_target[ok_target["flux_g_m2_h"] <= float(flux_cap)]
                row = dict(scenario)
                row.update({"target_savings_pct": float(target), "available_flux_cap_g_m2_h": float(flux_cap)})
                if ok.empty:
                    row.update({"max_e_p_Wh_per_kg": np.nan, "best_f": np.nan, "flux_used_g_m2_h": np.nan, "area_m2": np.nan, "savings_pct": np.nan})
                else:
                    max_ep = ok["e_p_Wh_per_kg_water"].max()
                    sub = ok[ok["e_p_Wh_per_kg_water"] == max_ep]
                    best = sub.loc[sub["best_savings_with_fan_pct"].idxmax()]
                    row.update(
                        {
                            "max_e_p_Wh_per_kg": float(max_ep),
                            "best_f": float(best["best_f_latent_by_eo"]),
                            "flux_used_g_m2_h": float(best["flux_g_m2_h"]),
                            "area_m2": float(best["required_area_m2"]),
                            "savings_pct": float(best["best_savings_with_fan_pct"]),
                        }
                    )
                rows_a.append(row)

            for ep in ep_milestones:
                # Use the closest grid point to the requested milestone.
                idx_near = (group["e_p_Wh_per_kg_water"] - float(ep)).abs().idxmin()
                ep_actual = float(group.loc[idx_near, "e_p_Wh_per_kg_water"])
                ep_group = ok_target[np.isclose(ok_target["e_p_Wh_per_kg_water"], ep_actual)]
                row = dict(scenario)
                row.update({"target_savings_pct": float(target), "requested_e_p_Wh_per_kg": float(ep), "actual_e_p_Wh_per_kg": ep_actual})
                if ep_group.empty:
                    row.update({"min_flux_g_m2_h": np.nan, "best_f": np.nan, "area_m2": np.nan, "savings_pct": np.nan})
                else:
                    min_flux = ep_group["flux_g_m2_h"].min()
                    sub = ep_group[ep_group["flux_g_m2_h"] == min_flux]
                    best = sub.loc[sub["best_savings_with_fan_pct"].idxmax()]
                    row.update(
                        {
                            "min_flux_g_m2_h": float(min_flux),
                            "best_f": float(best["best_f_latent_by_eo"]),
                            "area_m2": float(best["required_area_m2"]),
                            "savings_pct": float(best["best_savings_with_fan_pct"]),
                        }
                    )
                rows_b.append(row)

    return pd.DataFrame(rows_a), pd.DataFrame(rows_b)


def _pivot_for_plot(df: pd.DataFrame, value: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    piv = df.pivot_table(index="flux_g_m2_h", columns="e_p_Wh_per_kg_water", values=value, aggfunc="max")
    x = piv.columns.to_numpy(dtype=float)
    y = piv.index.to_numpy(dtype=float)
    z = piv.to_numpy(dtype=float)
    return x, y, z


def plot_primary_maps(results: pd.DataFrame, args: argparse.Namespace, out_dir: Path) -> None:
    primary = results[
        (results["case"] == args.primary_case)
        & (results["evap_model"] == args.primary_evap_model)
        & np.isclose(results["heat_to_process_fraction"], args.primary_heat_fraction)
        & np.isclose(results["pressure_drop_pa"], args.primary_pressure_drop_pa)
        & np.isclose(results["area_limit_m2"], args.primary_area_limit_m2)
    ].copy()

    if primary.empty:
        print("Warning: no rows found for primary plotting scenario. Skipping primary maps.")
        return

    plot_dir = out_dir / "primary_maps"
    plot_dir.mkdir(parents=True, exist_ok=True)

    title_base = (
        f"{args.primary_case}, {args.primary_evap_model}, chi={args.primary_heat_fraction}, "
        f"dp={args.primary_pressure_drop_pa:g} Pa, Amax={args.primary_area_limit_m2:g} m2"
    )

    for value, label, fname in [
        ("best_savings_with_fan_pct", "Best system savings [%]", "combined_savings_map.png"),
        ("best_f_latent_by_eo", "Best fraction of latent load by EO/ACEO [-]", "best_f_map.png"),
        ("required_area_m2", "Required active membrane area [m2]", "required_area_map.png"),
        ("P_eo_per_area_W_m2", "EO/ACEO electrical power density [W/m2]", "power_density_map.png"),
    ]:
        x, y, z = _pivot_for_plot(primary, value)
        fig, ax = plt.subplots(figsize=(9, 6))
        mesh = ax.pcolormesh(x, y, z, shading="auto")
        cbar = fig.colorbar(mesh, ax=ax)
        cbar.set_label(label)
        ax.set_yscale("log")
        ax.set_xlabel("EO/ACEO energy, e_p [Wh/kg water]")
        ax.set_ylabel("Available membrane flux [g/(m2 h)]")
        ax.set_title(f"{label}\n{title_base}")
        ax.grid(True, which="both", alpha=0.25)
        if value == "best_savings_with_fan_pct":
            try:
                levels = [0, 2, 5, 10]
                cs = ax.contour(x, y, z, levels=levels, linewidths=1.0)
                ax.clabel(cs, fmt="%g%%", fontsize=8)
            except Exception:
                pass
        fig.tight_layout()
        fig.savefig(plot_dir / fname, dpi=220)
        plt.close(fig)


def write_report(summary: dict[str, float], table_a: pd.DataFrame, table_b: pd.DataFrame, args: argparse.Namespace, out_dir: Path) -> None:
    lines: list[str] = []
    lines.append("# Model 2 combined feasibility report")
    lines.append("")
    lines.append("This combines the Model 1 energy screen with Model 2 area/flux requirements and optional extra fan power.")
    lines.append("")
    lines.append("## Scenario")
    lines.append("")
    lines.append(f"- Dry-air flow: {summary['dry_air_flow_kg_s']:.4g} kg_da/s")
    lines.append(f"- Start: {summary['start_T_C']:.2f} C, RH={100*summary['start_RH']:.1f} %, w={summary['start_w_g_per_kg_da']:.3f} g/kg_da")
    lines.append(f"- Target: {summary['target_T_C']:.2f} C, RH={100*summary['target_RH']:.1f} %, w={summary['target_w_g_per_kg_da']:.3f} g/kg_da")
    lines.append(f"- Total water to remove: {summary['water_total_kg_s']:.6f} kg/s = {summary['water_total_kg_h']:.3f} kg/h")
    lines.append("")
    lines.append("## Primary plotting scenario")
    lines.append("")
    lines.append("```text")
    lines.append(f"case                 = {args.primary_case}")
    lines.append(f"evap_model           = {args.primary_evap_model}")
    lines.append(f"heat fraction chi    = {args.primary_heat_fraction}")
    lines.append(f"pressure drop        = {args.primary_pressure_drop_pa} Pa")
    lines.append(f"area limit           = {args.primary_area_limit_m2} m2")
    lines.append("```")
    lines.append("")
    lines.append("## Max allowed EO/ACEO energy for selected available flux caps")
    lines.append("")
    lines.append("The table below answers: if membrane technology can deliver at most a given flux, how high can e_p be while still meeting the savings target and area limit?")
    lines.append("")
    # Keep primary scenario in report for readability.
    primary_a = table_a[
        (table_a["case"] == args.primary_case)
        & (table_a["evap_model"] == args.primary_evap_model)
        & np.isclose(table_a["heat_to_process_fraction"], args.primary_heat_fraction)
        & np.isclose(table_a["pressure_drop_pa"], args.primary_pressure_drop_pa)
        & np.isclose(table_a["area_limit_m2"], args.primary_area_limit_m2)
    ].copy()
    lines.append("```text")
    lines.append(primary_a.to_string(index=False))
    lines.append("```")
    lines.append("")
    lines.append("## Minimum required flux for selected EO/ACEO energy values")
    lines.append("")
    lines.append("The table below answers: if e_p is known, what membrane flux is required to meet the savings target and area limit?")
    lines.append("")
    primary_b = table_b[
        (table_b["case"] == args.primary_case)
        & (table_b["evap_model"] == args.primary_evap_model)
        & np.isclose(table_b["heat_to_process_fraction"], args.primary_heat_fraction)
        & np.isclose(table_b["pressure_drop_pa"], args.primary_pressure_drop_pa)
        & np.isclose(table_b["area_limit_m2"], args.primary_area_limit_m2)
    ].copy()
    lines.append("```text")
    lines.append(primary_b.to_string(index=False))
    lines.append("```")
    lines.append("")
    lines.append("## Practical reading")
    lines.append("")
    lines.append("A product-relevant region must satisfy both an energy target and a flux/area target. Typical useful reading from this model:")
    lines.append("")
    lines.append("```text")
    lines.append("energy: e_p should be around or below 100--200 Wh/kg_water for robust HVAC benefit")
    lines.append("flux:   J_w must often be several thousand to >10,000 g/(m2 h) for compact full-latent-removal modules")
    lines.append("area:   low e_p is not enough if active membrane area becomes tens to hundreds of m2")
    lines.append("```")
    lines.append("")
    (out_dir / "combined_feasibility_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Combined energy + flux + area feasibility map for EO/ACEO dehumidification.")
    parser.add_argument("--config", default="scenarios/first_model.yaml")
    parser.add_argument("--out", default="outputs/model2_combined_feasibility")

    parser.add_argument("--f-start", type=float, default=0.0)
    parser.add_argument("--f-stop", type=float, default=1.0)
    parser.add_argument("--n-f", type=int, default=101)

    parser.add_argument("--ep-start", type=float, default=25.0)
    parser.add_argument("--ep-stop", type=float, default=800.0)
    parser.add_argument("--n-ep", type=int, default=90)

    parser.add_argument("--flux-start", type=float, default=100.0)
    parser.add_argument("--flux-stop", type=float, default=50000.0)
    parser.add_argument("--n-flux", type=int, default=90)

    parser.add_argument("--reheat-cases", nargs="+", default=["free_reheat", "heat_pump_reheat_COP3", "electric_reheat"])
    parser.add_argument("--evap-models", nargs="+", default=["strict_dewpoint_until_full", "linear_by_fraction"])
    parser.add_argument("--heat-fractions", type=float, nargs="+", default=[0.5])
    parser.add_argument("--pressure-drop-values", type=float, nargs="+", default=[0.0, 50.0, 100.0])
    parser.add_argument("--area-limits", type=float, nargs="+", default=[5.0, 10.0, 20.0, 50.0])

    parser.add_argument("--fan-efficiency", type=float, default=0.6)
    parser.add_argument("--airflow-multiplier", type=float, default=1.0)
    parser.add_argument("--require-positive-eo", action="store_true", help="Exclude f=0 from best-f selection.")

    parser.add_argument("--savings-targets", type=float, nargs="+", default=[2.0, 5.0, 10.0])
    parser.add_argument("--ep-milestones", type=float, nargs="+", default=[50, 100, 150, 200, 250, 300, 400, 500])
    parser.add_argument("--flux-milestones", type=float, nargs="+", default=[1000, 3000, 5000, 10000, 30000, 50000])

    parser.add_argument("--primary-case", default="free_reheat")
    parser.add_argument("--primary-evap-model", default="strict_dewpoint_until_full")
    parser.add_argument("--primary-heat-fraction", type=float, default=0.5)
    parser.add_argument("--primary-pressure-drop-pa", type=float, default=50.0)
    parser.add_argument("--primary-area-limit-m2", type=float, default=10.0)

    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = load_yaml(args.config)
    results, summary = run_combined_feasibility(config, args)
    results.to_csv(out_dir / "combined_feasibility_results.csv", index=False)

    with open(out_dir / "run_arguments.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(vars(args), f, sort_keys=False)

    table_a, table_b = summarize_available_flux(
        results=results,
        targets=[float(x) for x in args.savings_targets],
        ep_milestones=[float(x) for x in args.ep_milestones],
        flux_milestones=[float(x) for x in args.flux_milestones],
    )
    table_a.to_csv(out_dir / "max_e_p_by_available_flux.csv", index=False)
    table_b.to_csv(out_dir / "min_flux_by_e_p.csv", index=False)

    plot_primary_maps(results, args, out_dir)
    write_report(summary, table_a, table_b, args, out_dir)

    print("\nWrote combined feasibility outputs to:", out_dir)
    print("\nPrimary scenario report:")
    print((out_dir / "combined_feasibility_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
