"""Plotting helpers for first-pass thermodynamic analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .psychrometrics import humidity_ratio, saturated_state_at_w, state_from_T_w
from .processes import eo_dehumidification_step


def plot_simple_psychrometric_chart(
    start,
    target,
    out_path: str | Path,
    dry_air_mass_flow_kg_s: float,
    example_e_p_Wh_per_kg_water: float = 300.0,
    example_heat_to_process_fraction: float = 0.25,
) -> None:
    """Plot a simplified psychrometric chart with route sketches."""

    fig, ax = plt.subplots(figsize=(10, 6))
    T_values = np.linspace(0, 45, 300)

    for RH in np.arange(0.1, 1.01, 0.1):
        w_values = np.array([humidity_ratio(T, RH, start.p_total_pa) * 1000 for T in T_values])
        ax.plot(T_values, w_values, linewidth=0.8)
        if RH in {0.2, 0.4, 0.6, 0.8, 1.0}:
            idx = -45
            ax.text(T_values[idx], w_values[idx], f"{int(100*RH)}%", fontsize=8)

    coil_exit = saturated_state_at_w(target.w, target.p_total_pa)
    ax.plot([start.T_C, coil_exit.T_C], [start.w_g_per_kg_da, coil_exit.w_g_per_kg_da], marker="o", label="Conventional: cool/dehumidify")
    ax.plot([coil_exit.T_C, target.T_C], [coil_exit.w_g_per_kg_da, target.w_g_per_kg_da], marker="o", linestyle="--", label="Conventional: reheat/mix")

    C_ideal = state_from_T_w(start.T_C, target.w, start.p_total_pa)
    ax.plot([start.T_C, C_ideal.T_C], [start.w_g_per_kg_da, C_ideal.w_g_per_kg_da], marker="s", label="Ideal EO: remove water")
    ax.plot([C_ideal.T_C, target.T_C], [C_ideal.w_g_per_kg_da, target.w_g_per_kg_da], marker="s", linestyle="--", label="After EO: sensible cooling")

    C_hot, _, _ = eo_dehumidification_step(
        start,
        target_w=target.w,
        dry_air_mass_flow_kg_s=dry_air_mass_flow_kg_s,
        e_p_Wh_per_kg_water=example_e_p_Wh_per_kg_water,
        heat_to_process_fraction=example_heat_to_process_fraction,
    )
    ax.plot([start.T_C, C_hot.T_C], [start.w_g_per_kg_da, C_hot.w_g_per_kg_da], marker="^", label="EO with process heat")
    ax.plot([C_hot.T_C, target.T_C], [C_hot.w_g_per_kg_da, target.w_g_per_kg_da], marker="^", linestyle="--", label="Cooling after heated EO")

    ax.scatter([start.T_C], [start.w_g_per_kg_da], s=80)
    ax.text(start.T_C + 0.3, start.w_g_per_kg_da + 0.3, "A start", fontsize=10)
    ax.scatter([target.T_C], [target.w_g_per_kg_da], s=80)
    ax.text(target.T_C + 0.3, target.w_g_per_kg_da + 0.3, "B target", fontsize=10)

    ax.set_xlabel("Dry-bulb temperature [°C]")
    ax.set_ylabel("Humidity ratio [g water / kg dry air]")
    ax.set_title("Simplified psychrometric routes")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 45)
    ax.set_ylim(0, max(30, start.w_g_per_kg_da * 1.15))
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_savings_map(df: pd.DataFrame, out_path: str | Path, heat_to_process_fraction: float) -> None:
    """Plot savings heatmap vs EO fraction and Wh/kg water for one heat fraction."""

    sub = df[np.isclose(df["heat_to_process_fraction"], heat_to_process_fraction)].copy()
    if sub.empty:
        raise ValueError(f"No rows for heat_to_process_fraction={heat_to_process_fraction}")
    pivot = sub.pivot(index="e_p_Wh_per_kg_water", columns="f_latent_by_eo", values="savings_pct").sort_index()
    f_vals = pivot.columns.values.astype(float)
    e_vals = pivot.index.values.astype(float)
    Z = pivot.values

    fig, ax = plt.subplots(figsize=(9, 6))
    mesh = ax.pcolormesh(f_vals, e_vals, Z, shading="auto")
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Energy saving vs conventional [%]")
    levels = [0, 2, 5, 10]
    try:
        cs = ax.contour(f_vals, e_vals, Z, levels=levels, linewidths=0.8)
        ax.clabel(cs, fmt="%g%%", fontsize=8)
    except Exception:
        pass
    ax.set_xlabel("Fraction of latent water removal done by EO/ACEO, f")
    ax.set_ylabel("EO/ACEO electrical energy [Wh/kg water]")
    ax.set_title(f"Hybrid-system savings, heat-to-process fraction = {heat_to_process_fraction:.2f}")
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_best_savings_vs_heat_fraction(df: pd.DataFrame, out_path: str | Path) -> None:
    """Plot the best attainable savings in the sweep for each heat fraction."""

    grouped = df.groupby("heat_to_process_fraction")["savings_pct"].max().reset_index()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(grouped["heat_to_process_fraction"], grouped["savings_pct"], marker="o")
    ax.axhline(0, linewidth=0.8)
    ax.set_xlabel("Fraction of EO electrical input heating process air")
    ax.set_ylabel("Best saving in sweep [%]")
    ax.set_title("Sensitivity to where EO/ACEO heat is released")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
