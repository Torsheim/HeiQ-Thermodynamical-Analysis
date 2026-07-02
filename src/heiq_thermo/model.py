"""High-level simulation functions."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .processes import conventional_ac_route, hybrid_eo_route, states_from_scenario
from .psychrometrics import saturated_state_at_w


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def grid_from_config(obj: Any) -> list[float]:
    if isinstance(obj, list):
        return [float(x) for x in obj]
    if isinstance(obj, dict):
        return [float(x) for x in np.linspace(float(obj["start"]), float(obj["stop"]), int(obj["n"]))]
    raise TypeError(f"Unsupported grid config: {obj!r}")


def process_result_to_row(result, prefix: str = "") -> dict[str, float | str]:
    row = {
        prefix + "name": result.name,
        prefix + "P_total_W": result.P_total_W,
        prefix + "P_eo_W": result.P_eo_W,
        prefix + "P_compressor_W": result.P_compressor_W,
        prefix + "P_reheat_W": result.P_reheat_W,
        prefix + "Q_coil_W": result.Q_coil_W,
        prefix + "Q_reheat_W": result.Q_reheat_W,
        prefix + "COP": result.COP,
        prefix + "T_evap_C": result.T_evap_C,
        prefix + "water_removed_by_eo_kg_s": result.water_removed_by_eo_kg_s,
        prefix + "water_removed_by_coil_kg_s": result.water_removed_by_coil_kg_s,
    }
    if result.intermediate is not None:
        row.update({
            prefix + "intermediate_T_C": result.intermediate.T_C,
            prefix + "intermediate_RH": result.intermediate.RH,
            prefix + "intermediate_w_g_per_kg_da": result.intermediate.w_g_per_kg_da,
            prefix + "intermediate_h_kJ_per_kg_da": result.intermediate.h_kJ_per_kg_da,
        })
    return row


def run_first_model(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    start, target = states_from_scenario(config)
    dry_air_flow = float(config["air"]["dry_air_mass_flow_kg_s"])
    coil = config["coil"]
    condenser_T_C = float(coil["condenser_T_C"])
    eta_carnot = float(coil["eta_carnot"])
    evap_approach_C = float(coil["evap_approach_C"])
    reheat_COP = float(coil.get("reheat_COP", 1.0))
    evap_model = str(coil.get("hybrid_evap_model", "linear_by_fraction"))

    conv = conventional_ac_route(start, target, dry_air_flow, condenser_T_C, eta_carnot, evap_approach_C, reheat_COP)
    conventional_evap_T_C = conv.T_evap_C

    eo = config["eo"]
    f_grid = grid_from_config(eo["fraction_latent_by_eo_grid"])
    e_grid = grid_from_config(eo["e_p_Wh_per_kg_water_grid"])
    chi_grid = grid_from_config(eo["heat_to_process_fraction_grid"])

    rows = []
    for f, e_p, chi in itertools.product(f_grid, e_grid, chi_grid):
        hybrid = hybrid_eo_route(
            start=start,
            target=target,
            dry_air_mass_flow_kg_s=dry_air_flow,
            fraction_latent_by_eo=f,
            e_p_Wh_per_kg_water=e_p,
            heat_to_process_fraction=chi,
            condenser_T_C=condenser_T_C,
            eta_carnot=eta_carnot,
            evap_approach_C=evap_approach_C,
            conventional_evap_T_C=conventional_evap_T_C,
            reheat_COP=reheat_COP,
            evap_model=evap_model,
        )
        savings_pct = 100.0 * (conv.P_total_W - hybrid.P_total_W) / conv.P_total_W
        row = {
            "f_latent_by_eo": f,
            "e_p_Wh_per_kg_water": e_p,
            "heat_to_process_fraction": chi,
            "conventional_P_total_W": conv.P_total_W,
            "hybrid_P_total_W": hybrid.P_total_W,
            "savings_pct": savings_pct,
        }
        row.update(process_result_to_row(hybrid, prefix="hybrid_"))
        rows.append(row)

    summary = {
        "start": start,
        "target": target,
        "conventional": conv,
        "target_saturated_state": saturated_state_at_w(target.w, target.p_total_pa),
        "dry_air_mass_flow_kg_s": dry_air_flow,
        "delta_w_g_per_kg_da": start.w_g_per_kg_da - target.w_g_per_kg_da,
    }
    return pd.DataFrame(rows), summary


def save_summary_text(summary: dict[str, Any], path: str | Path) -> None:
    start = summary["start"]
    target = summary["target"]
    conv = summary["conventional"]
    sat = summary["target_saturated_state"]
    dry_air_flow = summary["dry_air_mass_flow_kg_s"]
    delta_w = summary["delta_w_g_per_kg_da"]
    lines = [
        "HeiQ first thermodynamic model summary",
        "=" * 45,
        "",
        f"Dry-air mass flow: {dry_air_flow:.4g} kg_da/s",
        "",
        "Start state:",
        f"  T = {start.T_C:.3f} C",
        f"  RH = {100*start.RH:.3f} %",
        f"  w = {start.w_g_per_kg_da:.3f} g/kg_da",
        f"  h = {start.h_kJ_per_kg_da:.3f} kJ/kg_da",
        f"  dew point = {start.dew_point_C:.3f} C",
        "",
        "Target state:",
        f"  T = {target.T_C:.3f} C",
        f"  RH = {100*target.RH:.3f} %",
        f"  w = {target.w_g_per_kg_da:.3f} g/kg_da",
        f"  h = {target.h_kJ_per_kg_da:.3f} kJ/kg_da",
        f"  dew point = {target.dew_point_C:.3f} C",
        "",
        f"Water to remove: {delta_w:.3f} g/kg_da",
        "",
        "Conventional route:",
        f"  coil exit saturated at target w: T = {sat.T_C:.3f} C, RH = {100*sat.RH:.1f} %, w = {sat.w_g_per_kg_da:.3f} g/kg_da",
        f"  cooling load = {conv.Q_coil_W:.3f} W",
        f"  reheat load = {conv.Q_reheat_W:.3f} W",
        f"  effective evaporator T = {conv.T_evap_C:.3f} C",
        f"  COP = {conv.COP:.3f}",
        f"  compressor power = {conv.P_compressor_W:.3f} W",
        f"  reheat power = {conv.P_reheat_W:.3f} W",
        f"  total purchased power = {conv.P_total_W:.3f} W",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
