from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heiq_thermo.model import load_yaml, grid_from_config
from heiq_thermo.processes import states_from_scenario
from heiq_thermo.psychrometrics import CP_DRY_AIR_KJ_KG_K, CP_WATER_VAPOUR_KJ_KG_K

R_DRY_AIR_J_KG_K = 287.055


def moist_air_specific_volume_m3_per_kg_da(T_C: float, w: float, p_total_pa: float) -> float:
    """Approximate moist-air specific volume per kg dry air."""
    T_K = T_C + 273.15
    return R_DRY_AIR_J_KG_K * T_K * (1.0 + 1.6078 * w) / p_total_pa


def as_grid(obj: Any) -> list[float]:
    return grid_from_config(obj)


def default_grid(values: list[float]) -> list[float]:
    return [float(x) for x in values]


def required_area_m2(water_removed_kg_s: float, flux_g_m2_h: float) -> float:
    if flux_g_m2_h <= 0:
        return np.inf
    water_g_h = water_removed_kg_s * 3600.0 * 1000.0
    return water_g_h / flux_g_m2_h


def eo_power_W(water_removed_kg_s: float, e_p_Wh_per_kg: float) -> float:
    return e_p_Wh_per_kg * 3600.0 * water_removed_kg_s


def fan_power_W(dry_air_flow_kg_s: float, start_T_C: float, start_w: float, p_pa: float, dp_pa: float, fan_efficiency: float) -> float:
    if fan_efficiency <= 0:
        raise ValueError("fan_efficiency must be positive")
    vdot_m3_s = dry_air_flow_kg_s * moist_air_specific_volume_m3_per_kg_da(start_T_C, start_w, p_pa)
    return dp_pa * vdot_m3_s / fan_efficiency


def run_area_screen(config: dict[str, Any], args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, float]]:
    start, target = states_from_scenario(config)
    dry_air_flow = float(config["air"]["dry_air_mass_flow_kg_s"])
    total_water_kg_s = dry_air_flow * max(0.0, start.w - target.w)

    f_grid = as_grid({"start": args.f_start, "stop": args.f_stop, "n": args.n_f})
    ep_grid = default_grid(args.e_p_values)
    flux_grid = default_grid(args.flux_values)
    dp_grid = default_grid(args.pressure_drop_values)
    area_limit_grid = default_grid(args.area_limits)

    rows: list[dict[str, float]] = []
    for f in f_grid:
        water_eo_kg_s = total_water_kg_s * f
        for e_p in ep_grid:
            P_eo = eo_power_W(water_eo_kg_s, e_p)
            for flux in flux_grid:
                area = required_area_m2(water_eo_kg_s, flux)
                power_density = P_eo / area if area > 0 and np.isfinite(area) else np.nan
                for dp in dp_grid:
                    P_fan = fan_power_W(dry_air_flow, start.T_C, start.w, start.p_total_pa, dp, args.fan_efficiency)
                    rows.append(
                        {
                            "f_latent_by_eo": f,
                            "water_removed_by_eo_kg_s": water_eo_kg_s,
                            "water_removed_by_eo_kg_h": water_eo_kg_s * 3600.0,
                            "e_p_Wh_per_kg_water": e_p,
                            "flux_g_m2_h": flux,
                            "required_area_m2": area,
                            "P_eo_W": P_eo,
                            "P_eo_per_area_W_m2": power_density,
                            "pressure_drop_Pa": dp,
                            "P_fan_extra_W": P_fan,
                            "P_eo_plus_fan_W": P_eo + P_fan,
                        }
                    )

    # Required flux to meet area limits.
    area_rows: list[dict[str, float]] = []
    for f in f_grid:
        water_eo_kg_s = total_water_kg_s * f
        water_g_h = water_eo_kg_s * 3600.0 * 1000.0
        for A in area_limit_grid:
            req_flux = water_g_h / A if A > 0 else np.inf
            area_rows.append({"f_latent_by_eo": f, "area_limit_m2": A, "required_flux_g_m2_h": req_flux})

    df = pd.DataFrame(rows)
    area_req_df = pd.DataFrame(area_rows)
    df.attrs["area_requirements"] = area_req_df

    summary = {
        "dry_air_flow_kg_da_s": dry_air_flow,
        "start_T_C": start.T_C,
        "start_RH": start.RH,
        "target_T_C": target.T_C,
        "target_RH": target.RH,
        "start_w_g_per_kg_da": start.w_g_per_kg_da,
        "target_w_g_per_kg_da": target.w_g_per_kg_da,
        "total_water_to_remove_kg_s": total_water_kg_s,
        "total_water_to_remove_kg_h": total_water_kg_s * 3600.0,
        "specific_volume_m3_per_kg_da": moist_air_specific_volume_m3_per_kg_da(start.T_C, start.w, start.p_total_pa),
    }
    return df, summary


def plot_area_vs_flux(df: pd.DataFrame, out_dir: Path, f_values: list[float]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = df[(df["e_p_Wh_per_kg_water"] == df["e_p_Wh_per_kg_water"].min()) & (df["pressure_drop_Pa"] == df["pressure_drop_Pa"].min())]
    fig, ax = plt.subplots(figsize=(8, 5))
    for f in f_values:
        sub = base.iloc[(base["f_latent_by_eo"] - f).abs().argsort()].head(len(base["flux_g_m2_h"].unique()))
        chosen_f = sub["f_latent_by_eo"].iloc[0]
        sub = base[np.isclose(base["f_latent_by_eo"], chosen_f)].sort_values("flux_g_m2_h")
        ax.loglog(sub["flux_g_m2_h"], sub["required_area_m2"], marker="o", label=f"f≈{chosen_f:.2f}")
    ax.set_xlabel("Water flux [g/(m² h)]")
    ax.set_ylabel("Required active membrane area [m²]")
    ax.set_title("Required area vs assumed membrane water flux")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "required_area_vs_flux.png", dpi=200)
    plt.close(fig)


def plot_required_flux_for_area(area_df: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for A, sub in area_df.groupby("area_limit_m2"):
        sub = sub.sort_values("f_latent_by_eo")
        ax.plot(sub["f_latent_by_eo"], sub["required_flux_g_m2_h"], marker="o", markersize=2.5, label=f"A={A:g} m²")
    ax.set_yscale("log")
    ax.set_xlabel("Fraction of latent water removal by EO/ACEO, f")
    ax.set_ylabel("Required flux [g/(m² h)]")
    ax.set_title("Membrane flux required to stay below area limit")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "required_flux_for_area_limits.png", dpi=200)
    plt.close(fig)


def plot_power_density(df: pd.DataFrame, out_dir: Path, f: float = 1.0) -> None:
    # Plot EO power density at selected f, no fan power, as function of flux and e_p.
    sub = df[(df["pressure_drop_Pa"] == df["pressure_drop_Pa"].min())].copy()
    chosen_f = sub.iloc[(sub["f_latent_by_eo"] - f).abs().argsort()].iloc[0]["f_latent_by_eo"]
    sub = sub[np.isclose(sub["f_latent_by_eo"], chosen_f)]
    pivot = sub.pivot_table(index="e_p_Wh_per_kg_water", columns="flux_g_m2_h", values="P_eo_per_area_W_m2", aggfunc="mean")
    X, Y = np.meshgrid(pivot.columns.values, pivot.index.values)
    Z = pivot.values
    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.contourf(X, Y, Z, levels=30)
    ax.set_xscale("log")
    ax.set_xlabel("Water flux [g/(m² h)]")
    ax.set_ylabel("EO/ACEO energy [Wh/kg water]")
    ax.set_title(f"EO electrical power density, f≈{chosen_f:.2f} [W/m²]")
    fig.colorbar(im, ax=ax, label="W/m²")
    fig.tight_layout()
    fig.savefig(out_dir / f"power_density_f_{chosen_f:.2f}.png", dpi=200)
    plt.close(fig)


def write_summary(summary: dict[str, float], df: pd.DataFrame, area_req_df: pd.DataFrame, out_path: Path) -> None:
    lines = [
        "# Model 2 area and flux screen",
        "",
        "This is not a full device model. It translates Model 1 water-removal requirements into membrane area, required flux, EO power, and optional extra fan power.",
        "",
        "## Scenario",
        "",
        f"- Dry-air flow: {summary['dry_air_flow_kg_da_s']:.4g} kg_da/s",
        f"- Start: {summary['start_T_C']:.2f} C, RH={100*summary['start_RH']:.1f} %, w={summary['start_w_g_per_kg_da']:.3f} g/kg_da",
        f"- Target: {summary['target_T_C']:.2f} C, RH={100*summary['target_RH']:.1f} %, w={summary['target_w_g_per_kg_da']:.3f} g/kg_da",
        f"- Total water to remove: {summary['total_water_to_remove_kg_s']:.6f} kg/s = {summary['total_water_to_remove_kg_h']:.3f} kg/h",
        "",
        "## Example area requirements for full latent removal, f=1",
        "",
        "```text",
    ]
    sub = df[(np.isclose(df["f_latent_by_eo"], 1.0)) & (df["e_p_Wh_per_kg_water"] == df["e_p_Wh_per_kg_water"].min()) & (df["pressure_drop_Pa"] == df["pressure_drop_Pa"].min())]
    cols = ["flux_g_m2_h", "required_area_m2", "water_removed_by_eo_kg_h"]
    lines.append(sub[cols].drop_duplicates().sort_values("flux_g_m2_h").to_string(index=False))
    lines.extend(["```", "", "## Required flux for selected area limits", "", "```text"])
    lines.append(area_req_df[np.isclose(area_req_df["f_latent_by_eo"], 1.0)].to_string(index=False))
    lines.extend(["```", ""])
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Model 2 starter: membrane area/flux/product screen.")
    parser.add_argument("--config", default="scenarios/first_model.yaml")
    parser.add_argument("--out", default="outputs/model2_area_flux_screen")
    parser.add_argument("--f-start", type=float, default=0.05)
    parser.add_argument("--f-stop", type=float, default=1.0)
    parser.add_argument("--n-f", type=int, default=20)
    parser.add_argument("--e-p-values", type=float, nargs="+", default=[50, 100, 150, 200, 250, 300, 400, 500])
    parser.add_argument("--flux-values", type=float, nargs="+", default=[50, 100, 300, 1000, 3000, 10000, 30000])
    parser.add_argument("--pressure-drop-values", type=float, nargs="+", default=[0, 25, 50, 100, 200])
    parser.add_argument("--fan-efficiency", type=float, default=0.60)
    parser.add_argument("--area-limits", type=float, nargs="+", default=[1, 2, 5, 10, 20, 50, 100])
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = load_yaml(args.config)
    df, summary = run_area_screen(config, args)
    area_req_df = df.attrs["area_requirements"]

    df.to_csv(out_dir / "area_flux_results.csv", index=False)
    area_req_df.to_csv(out_dir / "required_flux_for_area_limits.csv", index=False)

    plot_area_vs_flux(df, out_dir, f_values=[0.25, 0.5, 0.75, 1.0])
    plot_required_flux_for_area(area_req_df, out_dir)
    plot_power_density(df, out_dir, f=1.0)
    write_summary(summary, df, area_req_df, out_dir / "model2_area_flux_report.md")

    print("Wrote Model 2 area/flux outputs to:", out_dir)
    print(Path(out_dir / "model2_area_flux_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
