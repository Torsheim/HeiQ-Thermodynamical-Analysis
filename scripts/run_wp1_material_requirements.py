from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FARADAY_C_PER_MOL = 96485.33212
M_WATER_KG_PER_MOL = 0.01801528


def read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def effective_h2o_per_charge(e_p_Wh_per_kg: float, voltage_V: float) -> float:
    """
    Effective water molecules per elementary charge.

    e_p = V * Q / m
    Q_per_kg = e_p * 3600 / V
    mol_charge_per_kg = Q_per_kg / F
    mol_water_per_kg = 1 / M_water
    """
    if e_p_Wh_per_kg <= 0 or voltage_V <= 0:
        return np.nan

    charge_C_per_kg = e_p_Wh_per_kg * 3600.0 / voltage_V
    mol_charge_per_kg = charge_C_per_kg / FARADAY_C_PER_MOL
    mol_water_per_kg = 1.0 / M_WATER_KG_PER_MOL

    return mol_water_per_kg / mol_charge_per_kg


def current_density_A_m2(
    flux_g_m2_h: float,
    e_p_Wh_per_kg: float,
    voltage_V: float,
) -> float:
    """
    j = water_mass_flux * charge_per_mass

    With:
      flux [g/m2/h]
      e_p [Wh/kg]
      voltage [V]

    Result:
      j [A/m2] = flux * e_p / (1000 * V)
    """
    if voltage_V <= 0:
        return np.nan
    return flux_g_m2_h * e_p_Wh_per_kg / (1000.0 * voltage_V)


def power_density_W_m2(
    flux_g_m2_h: float,
    e_p_Wh_per_kg: float,
) -> float:
    """
    Electrical power density.

    P/A = flux[g/m2/h] * e_p[Wh/kg] / 1000
    """
    return flux_g_m2_h * e_p_Wh_per_kg / 1000.0


def required_area_m2(
    water_removed_kg_h: float,
    flux_g_m2_h: float,
) -> float:
    if flux_g_m2_h <= 0:
        return np.nan
    return 1000.0 * water_removed_kg_h / flux_g_m2_h


def asr_max_ohm_m2(
    ohmic_budget_Wh_per_kg: float,
    flux_g_m2_h: float,
    current_density_A_m2_value: float,
) -> float:
    """
    Ohmic energy per kg water:

      e_ohm [Wh/kg] = (j^2 * ASR) * 1000 / flux_g_m2_h

    Therefore:

      ASR_max = e_ohm_budget * flux / (1000*j^2)
    """
    if current_density_A_m2_value <= 0:
        return np.nan
    return (
        ohmic_budget_Wh_per_kg
        * flux_g_m2_h
        / (1000.0 * current_density_A_m2_value**2)
    )


def sigma_min_S_m(
    thickness_um: float,
    asr_ohm_m2: float,
) -> float:
    """
    ASR = thickness / sigma
    sigma = thickness / ASR
    """
    if asr_ohm_m2 <= 0:
        return np.nan
    return (thickness_um * 1e-6) / asr_ohm_m2


def make_requirement_rows(
    breakeven_df: pd.DataFrame,
    flux_values: list[float],
    design_ep_values: list[float],
    voltage_values: list[float],
    thickness_um_values: list[float],
    ohmic_budget_fractions: list[float],
    q_sorp_values: list[float],
    active_heat_fractions: list[float],
    extra_fan_power_kW_values: list[float],
) -> pd.DataFrame:
    rows = []

    d = breakeven_df.copy()

    d = d[d["q_sorp_kJ_per_kg_water"].isin(q_sorp_values)]
    d = d[d["active_heat_fraction"].isin(active_heat_fractions)]
    d = d[d["extra_fan_power_kW"].isin(extra_fan_power_kW_values)]

    for _, row in d.iterrows():
        water_kg_h = float(row["water_removed_by_predrying_kg_h"])
        ep_max = float(row["penalized_break_even_e_p_Wh_per_kg_water"])
        q_sorp = float(row["q_sorp_kJ_per_kg_water"])
        sorption_heat_kW = float(row["sorption_heat_kW"])
        active_fraction = float(row["active_heat_fraction"])
        passive_fraction = max(0.0, 1.0 - active_fraction)

        for e_p in design_ep_values:
            ep_margin = ep_max - e_p
            passes_ep = ep_margin >= 0.0

            for flux in flux_values:
                area_m2 = required_area_m2(water_kg_h, flux)

                for voltage in voltage_values:
                    n_h2o_charge = effective_h2o_per_charge(e_p, voltage)
                    j = current_density_A_m2(flux, e_p, voltage)
                    pden = power_density_W_m2(flux, e_p)

                    for ohmic_fraction in ohmic_budget_fractions:
                        e_ohm_budget = e_p * ohmic_fraction
                        asr_max = asr_max_ohm_m2(e_ohm_budget, flux, j)

                        for thickness_um in thickness_um_values:
                            sigma_min = sigma_min_S_m(thickness_um, asr_max)

                            rows.append(
                                {
                                    "case": row["case"],
                                    "COP_case": row["COP_case"],
                                    "COP_used": row["COP_used"],
                                    "q_sorp_kJ_per_kg_water": q_sorp,
                                    "active_heat_fraction": active_fraction,
                                    "passive_heat_fraction": passive_fraction,
                                    "extra_fan_power_kW": row["extra_fan_power_kW"],
                                    "water_removed_by_predrying_kg_h": water_kg_h,
                                    "saved_purchased_power_vs_baseline_kW": row["saved_purchased_power_vs_baseline_kW"],
                                    "sorption_heat_kW": sorption_heat_kW,
                                    "thermal_penalty_kW": row["thermal_penalty_kW"],
                                    "ep_max_Wh_per_kg_water": ep_max,
                                    "design_e_p_Wh_per_kg_water": e_p,
                                    "ep_margin_Wh_per_kg_water": ep_margin,
                                    "passes_ep_stage_gate": passes_ep,
                                    "flux_g_m2_h": flux,
                                    "required_area_m2": area_m2,
                                    "voltage_V": voltage,
                                    "effective_H2O_per_charge": n_h2o_charge,
                                    "current_density_A_m2": j,
                                    "electrical_power_density_W_m2": pden,
                                    "ohmic_budget_fraction_of_ep": ohmic_fraction,
                                    "ohmic_budget_Wh_per_kg_water": e_ohm_budget,
                                    "ASR_max_ohm_m2": asr_max,
                                    "ASR_max_ohm_cm2": asr_max * 1e4,
                                    "thickness_um": thickness_um,
                                    "sigma_min_S_m": sigma_min,
                                    "sigma_min_mS_cm": sigma_min * 10.0,
                                }
                            )

    return pd.DataFrame(rows)


def make_heat_rejection_rows(
    breakeven_df: pd.DataFrame,
    deltaT_values_K: list[float],
    q_sorp_values: list[float],
    active_heat_fractions: list[float],
    extra_fan_power_kW_values: list[float],
) -> pd.DataFrame:
    rows = []

    d = breakeven_df.copy()
    d = d[d["q_sorp_kJ_per_kg_water"].isin(q_sorp_values)]
    d = d[d["active_heat_fraction"].isin(active_heat_fractions)]
    d = d[d["extra_fan_power_kW"].isin(extra_fan_power_kW_values)]

    base_cols = [
        "case",
        "COP_case",
        "q_sorp_kJ_per_kg_water",
        "active_heat_fraction",
        "extra_fan_power_kW",
    ]

    d = d.drop_duplicates(base_cols)

    for _, row in d.iterrows():
        total_heat_kW = float(row["sorption_heat_kW"])
        active_fraction = float(row["active_heat_fraction"])
        passive_fraction = max(0.0, 1.0 - active_fraction)

        active_heat_kW = active_fraction * total_heat_kW
        passive_heat_kW = passive_fraction * total_heat_kW

        for deltaT in deltaT_values_K:
            if deltaT <= 0:
                UA_W_K = np.nan
            else:
                UA_W_K = passive_heat_kW * 1000.0 / deltaT

            rows.append(
                {
                    "case": row["case"],
                    "COP_case": row["COP_case"],
                    "q_sorp_kJ_per_kg_water": row["q_sorp_kJ_per_kg_water"],
                    "water_removed_by_predrying_kg_h": row["water_removed_by_predrying_kg_h"],
                    "sorption_heat_total_kW": total_heat_kW,
                    "active_heat_fraction": active_fraction,
                    "active_heat_kW": active_heat_kW,
                    "passive_heat_fraction": passive_fraction,
                    "passive_heat_kW": passive_heat_kW,
                    "deltaT_for_passive_rejection_K": deltaT,
                    "UA_required_W_per_K": UA_W_K,
                }
            )

    return pd.DataFrame(rows)


def make_shortlist(
    req_df: pd.DataFrame,
    max_area_m2: float,
    max_current_density_A_m2: float,
    max_power_density_W_m2: float,
    available_sigma_S_m: float,
    max_required_sigma_S_m: float | None,
) -> pd.DataFrame:
    d = req_df.copy()

    d = d[d["passes_ep_stage_gate"]]
    d = d[d["required_area_m2"] <= max_area_m2]
    d = d[d["current_density_A_m2"] <= max_current_density_A_m2]
    d = d[d["electrical_power_density_W_m2"] <= max_power_density_W_m2]

    if max_required_sigma_S_m is not None:
        d = d[d["sigma_min_S_m"] <= max_required_sigma_S_m]
    else:
        d = d[d["sigma_min_S_m"] <= available_sigma_S_m]

    sort_cols = [
        "case",
        "COP_case",
        "active_heat_fraction",
        "design_e_p_Wh_per_kg_water",
        "required_area_m2",
        "current_density_A_m2",
        "sigma_min_S_m",
    ]

    return d.sort_values(sort_cols).reset_index(drop=True)


def make_plots(
    req_df: pd.DataFrame,
    heat_df: pd.DataFrame,
    out_dir: Path,
    focus_q_sorp: float,
    focus_active_heat_fraction: float,
    focus_extra_fan_kW: float,
    focus_voltage: float,
    focus_ohmic_fraction: float,
    focus_thickness_um: float,
) -> None:
    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Area vs flux
    area = (
        req_df[
            (req_df["q_sorp_kJ_per_kg_water"] == focus_q_sorp)
            & (req_df["active_heat_fraction"] == focus_active_heat_fraction)
            & (req_df["extra_fan_power_kW"] == focus_extra_fan_kW)
            & (req_df["voltage_V"] == focus_voltage)
            & (req_df["ohmic_budget_fraction_of_ep"] == focus_ohmic_fraction)
            & (req_df["thickness_um"] == focus_thickness_um)
        ][["case", "flux_g_m2_h", "required_area_m2"]]
        .drop_duplicates()
    )

    if not area.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        for case, g in area.groupby("case"):
            g = g.sort_values("flux_g_m2_h")
            ax.plot(g["flux_g_m2_h"], g["required_area_m2"], marker="o", label=case)

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Membrane water flux [g/(m² h)]")
        ax.set_ylabel("Required active membrane area [m²]")
        ax.set_title("Required membrane area vs flux")
        ax.grid(True, alpha=0.3, which="both")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(plot_dir / "required_area_vs_flux.png", dpi=200)
        plt.close(fig)

    # Current density vs flux
    cur = req_df[
        (req_df["q_sorp_kJ_per_kg_water"] == focus_q_sorp)
        & (req_df["active_heat_fraction"] == focus_active_heat_fraction)
        & (req_df["extra_fan_power_kW"] == focus_extra_fan_kW)
        & (req_df["voltage_V"] == focus_voltage)
        & (req_df["ohmic_budget_fraction_of_ep"] == focus_ohmic_fraction)
        & (req_df["thickness_um"] == focus_thickness_um)
    ][[
        "design_e_p_Wh_per_kg_water",
        "flux_g_m2_h",
        "current_density_A_m2",
        "electrical_power_density_W_m2",
    ]].drop_duplicates()

    if not cur.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        for ep, g in cur.groupby("design_e_p_Wh_per_kg_water"):
            g = g.sort_values("flux_g_m2_h")
            ax.plot(g["flux_g_m2_h"], g["current_density_A_m2"], marker="o", label=f"e_p={ep:g} Wh/kg")

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Membrane water flux [g/(m² h)]")
        ax.set_ylabel("Current density [A/m²]")
        ax.set_title(f"Current density vs flux at V={focus_voltage:g} V")
        ax.grid(True, alpha=0.3, which="both")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(plot_dir / "current_density_vs_flux.png", dpi=200)
        plt.close(fig)

    # Effective water per charge vs e_p
    eff = req_df[
        (req_df["voltage_V"] == focus_voltage)
    ][[
        "design_e_p_Wh_per_kg_water",
        "effective_H2O_per_charge",
    ]].drop_duplicates().sort_values("design_e_p_Wh_per_kg_water")

    if not eff.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(
            eff["design_e_p_Wh_per_kg_water"],
            eff["effective_H2O_per_charge"],
            marker="o",
        )
        ax.set_xlabel("EO energy, e_p [Wh/kg water]")
        ax.set_ylabel("Effective H₂O per elementary charge")
        ax.set_title(f"Effective water/charge target at V={focus_voltage:g} V")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(plot_dir / "effective_water_per_charge_vs_ep.png", dpi=200)
        plt.close(fig)

    # Passive UA requirements
    heat_focus = heat_df[
        (heat_df["q_sorp_kJ_per_kg_water"] == focus_q_sorp)
        & (heat_df["active_heat_fraction"].isin([0.0, 0.25, 0.5]))
    ]

    if not heat_focus.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        for (case, active_fraction), g in heat_focus.groupby(["case", "active_heat_fraction"]):
            g = g.sort_values("deltaT_for_passive_rejection_K")
            ax.plot(
                g["deltaT_for_passive_rejection_K"],
                g["UA_required_W_per_K"],
                marker="o",
                label=f"{case}, active={active_fraction:g}",
            )

        ax.set_xlabel("Available passive heat-rejection ΔT [K]")
        ax.set_ylabel("Required UA [W/K]")
        ax.set_title("Passive heat rejection requirement")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(plot_dir / "passive_heat_rejection_UA.png", dpi=200)
        plt.close(fig)


def write_report(
    out_dir: Path,
    req_df: pd.DataFrame,
    heat_df: pd.DataFrame,
    shortlist_df: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    focus = req_df[
        (req_df["q_sorp_kJ_per_kg_water"] == args.focus_q_sorp)
        & (req_df["active_heat_fraction"] == args.focus_active_heat_fraction)
        & (req_df["extra_fan_power_kW"] == args.focus_extra_fan_kW)
        & (req_df["voltage_V"] == args.focus_voltage)
        & (req_df["ohmic_budget_fraction_of_ep"] == args.focus_ohmic_fraction)
        & (req_df["thickness_um"] == args.focus_thickness_um)
        & (req_df["design_e_p_Wh_per_kg_water"].isin(args.report_ep_values))
        & (req_df["flux_g_m2_h"].isin(args.report_flux_values))
    ].copy()

    focus_cols = [
        "case",
        "COP_case",
        "ep_max_Wh_per_kg_water",
        "design_e_p_Wh_per_kg_water",
        "ep_margin_Wh_per_kg_water",
        "passes_ep_stage_gate",
        "flux_g_m2_h",
        "required_area_m2",
        "voltage_V",
        "effective_H2O_per_charge",
        "current_density_A_m2",
        "electrical_power_density_W_m2",
        "ohmic_budget_Wh_per_kg_water",
        "ASR_max_ohm_cm2",
        "thickness_um",
        "sigma_min_S_m",
        "sigma_min_mS_cm",
    ]

    heat_focus = heat_df[
        (heat_df["q_sorp_kJ_per_kg_water"] == args.focus_q_sorp)
        & (heat_df["active_heat_fraction"].isin([0.0, 0.25, 0.5, 1.0]))
        & (heat_df["deltaT_for_passive_rejection_K"].isin(args.report_deltaT_values))
    ].copy()

    heat_cols = [
        "case",
        "COP_case",
        "q_sorp_kJ_per_kg_water",
        "sorption_heat_total_kW",
        "active_heat_fraction",
        "active_heat_kW",
        "passive_heat_kW",
        "deltaT_for_passive_rejection_K",
        "UA_required_W_per_K",
    ]

    short_cols = [
        "case",
        "COP_case",
        "active_heat_fraction",
        "extra_fan_power_kW",
        "ep_max_Wh_per_kg_water",
        "design_e_p_Wh_per_kg_water",
        "flux_g_m2_h",
        "required_area_m2",
        "voltage_V",
        "effective_H2O_per_charge",
        "current_density_A_m2",
        "electrical_power_density_W_m2",
        "thickness_um",
        "sigma_min_S_m",
        "sigma_min_mS_cm",
        "ep_margin_Wh_per_kg_water",
    ]

    report = []
    report.append("# WP1 material and system requirements")
    report.append("")
    report.append("This report translates the WP1 energy stage gate into membrane and system targets.")
    report.append("")
    report.append("## Key equations")
    report.append("")
    report.append("```text")
    report.append("required_area = water_removed / membrane_flux")
    report.append("effective_H2O_per_charge = F*V / (M_water*e_p*3600)")
    report.append("current_density = flux*e_p/(1000*V)")
    report.append("power_density = flux*e_p/1000")
    report.append("e_ohm = j^2*ASR*1000/flux")
    report.append("ASR_max = e_ohm_budget*flux/(1000*j^2)")
    report.append("sigma_min = thickness/ASR_max")
    report.append("UA_required = passive_heat/DeltaT")
    report.append("```")
    report.append("")
    report.append("## Focus settings")
    report.append("")
    report.append(f"- q_sorp: {args.focus_q_sorp:g} kJ/kg water")
    report.append(f"- active heat fraction: {args.focus_active_heat_fraction:g}")
    report.append(f"- extra fan power: {args.focus_extra_fan_kW:g} kW")
    report.append(f"- voltage: {args.focus_voltage:g} V")
    report.append(f"- ohmic budget fraction of e_p: {args.focus_ohmic_fraction:g}")
    report.append(f"- thickness: {args.focus_thickness_um:g} µm")
    report.append("")
    report.append("## Focus requirement table")
    report.append("")
    if focus.empty:
        report.append("No focus rows found.")
    else:
        report.append("```text")
        report.append(
            focus[focus_cols]
            .sort_values(["case", "COP_case", "design_e_p_Wh_per_kg_water", "flux_g_m2_h"])
            .head(120)
            .to_string(index=False)
        )
        report.append("```")
    report.append("")
    report.append("## Heat rejection requirements")
    report.append("")
    if heat_focus.empty:
        report.append("No heat rejection rows found.")
    else:
        report.append("```text")
        report.append(
            heat_focus[heat_cols]
            .sort_values(["case", "COP_case", "active_heat_fraction", "deltaT_for_passive_rejection_K"])
            .to_string(index=False)
        )
        report.append("```")
    report.append("")
    report.append("## Shortlisted rows under engineering filters")
    report.append("")
    if shortlist_df.empty:
        report.append("No rows passed the selected engineering filters.")
    else:
        report.append("```text")
        report.append(
            shortlist_df[short_cols]
            .sort_values(["case", "COP_case", "active_heat_fraction", "design_e_p_Wh_per_kg_water", "required_area_m2"])
            .head(120)
            .to_string(index=False)
        )
        report.append("```")
    report.append("")
    report.append("## Interpretation")
    report.append("")
    report.append("- `required_area_m2` converts the WP1 water-removal target into an active membrane area.")
    report.append("- `effective_H2O_per_charge` is the effective electro-osmotic transport target implied by the chosen `e_p` and voltage.")
    report.append("- `current_density_A_m2` and `electrical_power_density_W_m2` are useful for electrode and stack sizing.")
    report.append("- `sigma_min_S_m` is a first ohmic-loss guardrail for the membrane. It is not a full MEA model.")
    report.append("- `UA_required_W_per_K` estimates how difficult passive heat rejection is.")

    (out_dir / "wp1_material_requirements_report.md").write_text(
        "\n".join(report),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translate WP1 stage-gate results into membrane/material/system requirements."
    )

    parser.add_argument("--stage-gate-dir", default="outputs/wp1_stage_gate_summary")
    parser.add_argument("--out", default="outputs/wp1_material_requirements")

    parser.add_argument("--design-ep-values", type=float, nargs="+", default=[25, 50, 75, 100, 150, 200])
    parser.add_argument("--flux-values", type=float, nargs="+", default=[500, 1000, 3000, 5000, 10000, 30000])
    parser.add_argument("--voltage-values", type=float, nargs="+", default=[0.5, 1.0, 2.0])
    parser.add_argument("--thickness-um-values", type=float, nargs="+", default=[25, 50, 100, 200])
    parser.add_argument("--ohmic-budget-fractions", type=float, nargs="+", default=[0.1, 0.25, 0.5])

    parser.add_argument("--q-sorp-values", type=float, nargs="+", default=[2200, 2431, 2600])
    parser.add_argument("--active-heat-fractions", type=float, nargs="+", default=[0, 0.25, 0.5, 1])
    parser.add_argument("--extra-fan-power-kW-values", type=float, nargs="+", default=[0, 0.25, 0.5, 1])
    parser.add_argument("--heat-rejection-deltaT-K", type=float, nargs="+", default=[2, 5, 10, 20])

    parser.add_argument("--max-area-m2", type=float, default=20.0)
    parser.add_argument("--max-current-density-A-m2", type=float, default=500.0)
    parser.add_argument("--max-power-density-W-m2", type=float, default=1000.0)
    parser.add_argument("--available-sigma-S-m", type=float, default=1.0)
    parser.add_argument("--max-required-sigma-S-m", type=float, default=None)

    parser.add_argument("--focus-q-sorp", type=float, default=2431.0)
    parser.add_argument("--focus-active-heat-fraction", type=float, default=0.25)
    parser.add_argument("--focus-extra-fan-kW", type=float, default=0.0)
    parser.add_argument("--focus-voltage", type=float, default=1.0)
    parser.add_argument("--focus-ohmic-fraction", type=float, default=0.25)
    parser.add_argument("--focus-thickness-um", type=float, default=50.0)

    parser.add_argument("--report-ep-values", type=float, nargs="+", default=[50, 100, 150])
    parser.add_argument("--report-flux-values", type=float, nargs="+", default=[1000, 3000, 5000, 10000])
    parser.add_argument("--report-deltaT-values", type=float, nargs="+", default=[5, 10, 20])

    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    stage_gate_dir = Path(args.stage_gate_dir)
    breakeven = read_required(stage_gate_dir / "wp1_stage_gate_break_even_ep.csv")

    req_df = make_requirement_rows(
        breakeven_df=breakeven,
        flux_values=args.flux_values,
        design_ep_values=args.design_ep_values,
        voltage_values=args.voltage_values,
        thickness_um_values=args.thickness_um_values,
        ohmic_budget_fractions=args.ohmic_budget_fractions,
        q_sorp_values=args.q_sorp_values,
        active_heat_fractions=args.active_heat_fractions,
        extra_fan_power_kW_values=args.extra_fan_power_kW_values,
    )

    heat_df = make_heat_rejection_rows(
        breakeven_df=breakeven,
        deltaT_values_K=args.heat_rejection_deltaT_K,
        q_sorp_values=args.q_sorp_values,
        active_heat_fractions=args.active_heat_fractions,
        extra_fan_power_kW_values=args.extra_fan_power_kW_values,
    )

    shortlist_df = make_shortlist(
        req_df=req_df,
        max_area_m2=args.max_area_m2,
        max_current_density_A_m2=args.max_current_density_A_m2,
        max_power_density_W_m2=args.max_power_density_W_m2,
        available_sigma_S_m=args.available_sigma_S_m,
        max_required_sigma_S_m=args.max_required_sigma_S_m,
    )

    req_df.to_csv(out_dir / "wp1_material_requirements_all.csv", index=False)
    heat_df.to_csv(out_dir / "wp1_heat_rejection_UA_requirements.csv", index=False)
    shortlist_df.to_csv(out_dir / "wp1_material_shortlist.csv", index=False)

    make_plots(
        req_df=req_df,
        heat_df=heat_df,
        out_dir=out_dir,
        focus_q_sorp=args.focus_q_sorp,
        focus_active_heat_fraction=args.focus_active_heat_fraction,
        focus_extra_fan_kW=args.focus_extra_fan_kW,
        focus_voltage=args.focus_voltage,
        focus_ohmic_fraction=args.focus_ohmic_fraction,
        focus_thickness_um=args.focus_thickness_um,
    )

    write_report(
        out_dir=out_dir,
        req_df=req_df,
        heat_df=heat_df,
        shortlist_df=shortlist_df,
        args=args,
    )

    print(f"Wrote WP1 material requirements to: {out_dir}")
    print()
    print((out_dir / "wp1_material_requirements_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
