from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

FARADAY_C_PER_MOL = 96485.33212
MW_WATER_KG_PER_MOL = 0.01801528


def _to_float_list(values: list[str]) -> list[float]:
    return [float(v) for v in values]


def _clean(x: float) -> str:
    return (f"{x:g}").replace(".", "p").replace("-", "m")


def transport_targets(e_p_Wh_per_kg: float, flux_g_m2_h: float, voltage_V: float) -> dict[str, float]:
    """Translate black-box e_p and water flux into effective electrical transport targets.

    This is not a mechanistic ACEO model. It is a target translator:
    how much effective water transport per unit charge, current density, and
    power density are implied by a desired Wh/kg and flux.
    """
    if e_p_Wh_per_kg <= 0:
        raise ValueError("e_p_Wh_per_kg must be positive")
    if voltage_V <= 0:
        raise ValueError("voltage_V must be positive")

    charge_per_kg_C_per_kg = e_p_Wh_per_kg * 3600.0 / voltage_V
    kg_per_C = 1.0 / charge_per_kg_C_per_kg
    mol_water_per_C = kg_per_C / MW_WATER_KG_PER_MOL
    water_molecules_per_charge = mol_water_per_C * FARADAY_C_PER_MOL

    flux_kg_m2_s = flux_g_m2_h / 1000.0 / 3600.0
    current_density_A_m2 = flux_kg_m2_s / kg_per_C
    power_density_W_m2 = current_density_A_m2 * voltage_V

    return {
        "e_p_Wh_per_kg_water": e_p_Wh_per_kg,
        "flux_g_m2_h": flux_g_m2_h,
        "voltage_V": voltage_V,
        "charge_per_kg_C_per_kg": charge_per_kg_C_per_kg,
        "kg_water_per_C": kg_per_C,
        "effective_water_molecules_per_charge": water_molecules_per_charge,
        "current_density_A_m2": current_density_A_m2,
        "power_density_W_m2": power_density_W_m2,
    }


def make_target_grid(eps: list[float], fluxes: list[float], voltages: list[float]) -> pd.DataFrame:
    rows = []
    for ep in eps:
        for flux in fluxes:
            for v in voltages:
                rows.append(transport_targets(ep, flux, v))
    return pd.DataFrame(rows)


def attach_transport_to_product_flux(robust_flux: pd.DataFrame, voltages: list[float]) -> pd.DataFrame:
    rows = []
    required_col = "robust_min_flux_g_m2_h"
    if required_col not in robust_flux.columns:
        raise ValueError(f"Expected column {required_col} in robust flux table")

    for _, row in robust_flux.iterrows():
        if not bool(row.get("all_scenarios_solved", False)):
            continue
        flux = row.get(required_col)
        ep = row.get("e_p_Wh_per_kg_water")
        if pd.isna(flux) or pd.isna(ep):
            continue
        for v in voltages:
            target = transport_targets(float(ep), float(flux), float(v))
            combined = row.to_dict()
            combined.update(target)
            rows.append(combined)
    return pd.DataFrame(rows)


def plot_water_per_charge(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Use one flux because water-per-charge is independent of flux.
    d = df.sort_values(["voltage_V", "e_p_Wh_per_kg_water"]).drop_duplicates(
        ["voltage_V", "e_p_Wh_per_kg_water"]
    )
    fig, ax = plt.subplots(figsize=(8, 5))
    for v, g in d.groupby("voltage_V"):
        ax.plot(
            g["e_p_Wh_per_kg_water"],
            g["effective_water_molecules_per_charge"],
            marker="o",
            label=f"V={v:g} V",
        )
    ax.set_xlabel("EO/ACEO energy e_p [Wh/kg water]")
    ax.set_ylabel("Effective water molecules per unit charge [-]")
    ax.set_title("Effective coupling implied by e_p and voltage")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "effective_water_per_charge_vs_ep.png", dpi=200)
    plt.close(fig)


def plot_power_density(df: pd.DataFrame, out_dir: Path, voltage: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    d = df[df["voltage_V"] == voltage].copy()
    if d.empty:
        return
    piv = d.pivot_table(
        index="flux_g_m2_h",
        columns="e_p_Wh_per_kg_water",
        values="power_density_W_m2",
        aggfunc="mean",
    ).sort_index()
    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(piv.values, aspect="auto", origin="lower")
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels([f"{c:g}" for c in piv.columns])
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels([f"{i:g}" for i in piv.index])
    ax.set_xlabel("e_p [Wh/kg water]")
    ax.set_ylabel("Flux [g/(m² h)]")
    ax.set_title(f"EO/ACEO power density [W/m²], V={voltage:g} V")
    fig.colorbar(im, ax=ax, label="Power density [W/m²]")
    fig.tight_layout()
    fig.savefig(out_dir / f"power_density_grid_V_{_clean(voltage)}.png", dpi=200)
    plt.close(fig)


def plot_current_density(df: pd.DataFrame, out_dir: Path, voltage: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    d = df[df["voltage_V"] == voltage].copy()
    if d.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    for ep, g in d.groupby("e_p_Wh_per_kg_water"):
        g = g.sort_values("flux_g_m2_h")
        ax.plot(g["flux_g_m2_h"], g["current_density_A_m2"], marker="o", label=f"e_p={ep:g} Wh/kg")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Flux [g/(m² h)]")
    ax.set_ylabel("Required current density [A/m²]")
    ax.set_title(f"Current density implied by flux and e_p, V={voltage:g} V")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / f"current_density_vs_flux_V_{_clean(voltage)}.png", dpi=200)
    plt.close(fig)


def write_report(out_path: Path, grid: pd.DataFrame, product: pd.DataFrame | None, voltages: list[float]) -> None:
    lines = []
    lines.append("# Model 3 transport target translator")
    lines.append("")
    lines.append("This is not a mechanistic ACEO model. It translates Model 2 targets into effective transport requirements.")
    lines.append("")
    lines.append("## Equations")
    lines.append("")
    lines.append("For an assumed operating voltage V and black-box energy e_p:")
    lines.append("")
    lines.append("```text")
    lines.append("charge_per_kg = e_p * 3600 / V")
    lines.append("kg_water_per_C = 1 / charge_per_kg")
    lines.append("effective_water_molecules_per_charge = kg_water_per_C * F / M_water")
    lines.append("current_density = water_flux / kg_water_per_C")
    lines.append("power_density = current_density * V")
    lines.append("```")
    lines.append("")
    lines.append("The coupling value should be interpreted as an effective target, not necessarily a Faradaic mechanism.")
    lines.append("")

    coupling = grid.drop_duplicates(["e_p_Wh_per_kg_water", "voltage_V"]).copy()
    coupling = coupling.sort_values(["voltage_V", "e_p_Wh_per_kg_water"])
    lines.append("## Effective water-per-charge target")
    lines.append("")
    lines.append("```text")
    lines.append(
        coupling[[
            "voltage_V",
            "e_p_Wh_per_kg_water",
            "charge_per_kg_C_per_kg",
            "effective_water_molecules_per_charge",
        ]].to_string(index=False)
    )
    lines.append("```")
    lines.append("")

    selected = grid[
        grid["voltage_V"].eq(1.0) if 1.0 in voltages else grid["voltage_V"].eq(voltages[0])
    ].copy()
    selected = selected[selected["flux_g_m2_h"].isin([100.0, 500.0, 1000.0, 3000.0, 5000.0, 10000.0])]
    lines.append("## Example current and power-density targets")
    lines.append("")
    lines.append("```text")
    lines.append(
        selected[[
            "voltage_V",
            "e_p_Wh_per_kg_water",
            "flux_g_m2_h",
            "effective_water_molecules_per_charge",
            "current_density_A_m2",
            "power_density_W_m2",
        ]].sort_values(["e_p_Wh_per_kg_water", "flux_g_m2_h"]).to_string(index=False)
    )
    lines.append("```")
    lines.append("")

    if product is not None and not product.empty:
        lines.append("## Product-linked robust targets")
        lines.append("")
        keep_cols = [
            "target_savings_pct",
            "e_p_Wh_per_kg_water",
            "area_limit_m2",
            "desired_dry_air_flow_kg_s",
            "robust_min_flux_g_m2_h",
            "regime_at_hardest_scenario",
            "voltage_V",
            "effective_water_molecules_per_charge",
            "current_density_A_m2",
            "power_density_W_m2",
        ]
        keep_cols = [c for c in keep_cols if c in product.columns]
        # Keep a concise subset.
        subset = product[
            product["voltage_V"].eq(1.0 if 1.0 in voltages else voltages[0])
            & product["desired_dry_air_flow_kg_s"].isin([0.5, 1.0, 2.0])
            & product["target_savings_pct"].isin([5.0, 10.0])
            & product["e_p_Wh_per_kg_water"].isin([50.0, 100.0, 150.0, 200.0])
            & product["area_limit_m2"].isin([10.0, 20.0, 50.0])
        ].copy()
        lines.append("```text")
        lines.append(subset[keep_cols].to_string(index=False))
        lines.append("```")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate e_p and flux targets into effective transport/current/power targets.")
    parser.add_argument("--out", default="outputs/model3_transport_targets")
    parser.add_argument("--robust-flux-csv", default="outputs/model2_portfolio_summary/robust_min_flux_across_scenarios.csv")
    parser.add_argument("--e-p-values", nargs="+", default=["50", "100", "150", "200"])
    parser.add_argument("--flux-values", nargs="+", default=["100", "200", "500", "1000", "3000", "5000", "10000"])
    parser.add_argument("--voltages", nargs="+", default=["0.5", "1.0", "2.0", "5.0"])
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    eps = _to_float_list(args.e_p_values)
    fluxes = _to_float_list(args.flux_values)
    voltages = _to_float_list(args.voltages)

    grid = make_target_grid(eps, fluxes, voltages)
    grid.to_csv(out_dir / "transport_target_grid.csv", index=False)

    product = None
    robust_path = Path(args.robust_flux_csv)
    if robust_path.exists():
        robust_flux = pd.read_csv(robust_path)
        product = attach_transport_to_product_flux(robust_flux, voltages)
        product.to_csv(out_dir / "product_linked_transport_targets.csv", index=False)

    plot_dir = out_dir / "plots"
    plot_water_per_charge(grid, plot_dir)
    for v in voltages:
        plot_power_density(grid, plot_dir, v)
        plot_current_density(grid, plot_dir, v)

    write_report(out_dir / "model3_transport_targets_report.md", grid, product, voltages)

    print("Wrote Model 3 target translator outputs to:", out_dir)
    print("\nEffective coupling preview:")
    preview = grid.drop_duplicates(["voltage_V", "e_p_Wh_per_kg_water"]).sort_values(["voltage_V", "e_p_Wh_per_kg_water"])
    print(preview[["voltage_V", "e_p_Wh_per_kg_water", "effective_water_molecules_per_charge"]].to_string(index=False))


if __name__ == "__main__":
    main()
