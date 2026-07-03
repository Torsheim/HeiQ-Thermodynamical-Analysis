from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from itertools import product

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

P_ATM_PA = 101_325.0
R_DA = 287.055
C_PA = 1.006
C_PV = 1.86
H_V0 = 2501.0


def saturation_pressure_water_pa(T_C: float) -> float:
    return 611.21 * np.exp((18.678 - T_C / 234.5) * (T_C / (257.14 + T_C)))


def humidity_ratio_from_T_RH(T_C: float, RH_frac: float, p_atm_pa: float = P_ATM_PA) -> float:
    p_ws = saturation_pressure_water_pa(T_C)
    p_w = RH_frac * p_ws
    return 0.621945 * p_w / (p_atm_pa - p_w)


def RH_from_T_w(T_C: float, w: float, p_atm_pa: float = P_ATM_PA) -> float:
    p_w = p_atm_pa * w / (0.621945 + w)
    return p_w / saturation_pressure_water_pa(T_C)


def moist_air_enthalpy(T_C: float, w: float) -> float:
    return C_PA * T_C + w * (H_V0 + C_PV * T_C)


def T_from_h_w(h: float, w: float) -> float:
    return (h - H_V0 * w) / (C_PA + C_PV * w)


def water_vapour_enthalpy(T_C: float) -> float:
    return H_V0 + C_PV * T_C


def specific_volume_m3_per_kg_da(T_C: float, w: float, p_atm_pa: float = P_ATM_PA) -> float:
    T_K = T_C + 273.15
    return R_DA * T_K * (1.0 + 1.607858 * w) / p_atm_pa


def dewpoint_for_w(w: float) -> float:
    lo, hi = -40.0, 90.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        w_sat = humidity_ratio_from_T_RH(mid, 1.0)
        if w_sat < w:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class State:
    label: str
    T_C: float
    w: float
    RH: float
    h: float
    dewpoint_C: float

    @property
    def w_g_per_kg_da(self) -> float:
        return 1000.0 * self.w

    @property
    def RH_pct(self) -> float:
        return 100.0 * self.RH


def state_from_T_RH(label: str, T_C: float, RH_frac: float) -> State:
    w = humidity_ratio_from_T_RH(T_C, RH_frac)
    h = moist_air_enthalpy(T_C, w)
    return State(label=label, T_C=T_C, w=w, RH=RH_frac, h=h, dewpoint_C=dewpoint_for_w(w))


def state_from_T_w(label: str, T_C: float, w: float) -> State:
    h = moist_air_enthalpy(T_C, w)
    RH = RH_from_T_w(T_C, w)
    return State(label=label, T_C=T_C, w=w, RH=RH, h=h, dewpoint_C=dewpoint_for_w(w))


def state_from_h_w(label: str, h: float, w: float) -> State:
    T_C = T_from_h_w(h, w)
    RH = RH_from_T_w(T_C, w)
    return State(label=label, T_C=T_C, w=w, RH=RH, h=h, dewpoint_C=dewpoint_for_w(w))


@dataclass(frozen=True)
class ConventionalResult:
    inlet: State
    target: State
    coil_exit: State
    cooling_load_W: float
    reheat_load_W: float
    compressor_power_W: float
    reheat_purchased_W: float
    total_purchased_W: float
    needs_dehumidification: bool
    infeasible_humidification: bool


def conventional_ac_route(
    inlet: State,
    target: State,
    dry_air_flow_kg_s: float,
    cooling_COP: float,
    reheat_mode: str,
    reheat_COP: float,
) -> ConventionalResult:
    needs_dehumidification = inlet.w > target.w + 1e-9
    infeasible_humidification = inlet.w < target.w - 1e-9

    if needs_dehumidification:
        coil_T = dewpoint_for_w(target.w)
        coil_exit = state_from_T_w("coil_exit", coil_T, target.w)
        cooling_load_W = max(0.0, (inlet.h - coil_exit.h) * dry_air_flow_kg_s * 1000.0)
        reheat_load_W = max(0.0, (target.h - coil_exit.h) * dry_air_flow_kg_s * 1000.0)
    else:
        # If the inlet is already dry enough, use a simple sensible/enthalpy cooler to target.
        # This branch should not dominate the intended use case.
        coil_exit = target
        cooling_load_W = max(0.0, (inlet.h - target.h) * dry_air_flow_kg_s * 1000.0)
        reheat_load_W = max(0.0, (target.h - inlet.h) * dry_air_flow_kg_s * 1000.0)

    compressor_power_W = cooling_load_W / cooling_COP if cooling_COP > 0 else np.inf

    if reheat_mode == "free_reheat":
        reheat_purchased_W = 0.0
    elif reheat_mode == "electric_reheat":
        reheat_purchased_W = reheat_load_W
    elif reheat_mode == "heat_pump_reheat":
        reheat_purchased_W = reheat_load_W / reheat_COP
    else:
        raise ValueError(f"Unknown reheat_mode={reheat_mode!r}")

    return ConventionalResult(
        inlet=inlet,
        target=target,
        coil_exit=coil_exit,
        cooling_load_W=cooling_load_W,
        reheat_load_W=reheat_load_W,
        compressor_power_W=compressor_power_W,
        reheat_purchased_W=reheat_purchased_W,
        total_purchased_W=compressor_power_W + reheat_purchased_W,
        needs_dehumidification=needs_dehumidification,
        infeasible_humidification=infeasible_humidification,
    )


def external_heat_case(q_external_W: float, mode: str, external_COP: float) -> tuple[float, bool, str]:
    if q_external_W <= 1e-9:
        return 0.0, True, "no_external_heat_needed"
    if mode == "free":
        return 0.0, True, "free_external_heat"
    if mode == "paid":
        if external_COP <= 0:
            raise ValueError("--external-desorp-heat-COP must be > 0 when --desorption-heat-mode paid")
        return q_external_W / external_COP, True, "paid_external_heat"
    if mode == "none":
        return 0.0, False, "external_heat_not_allowed"
    raise ValueError(f"Unknown desorption heat mode: {mode}")


def make_pre_step_case(
    A: State,
    D: State,
    baseline: ConventionalResult,
    dry_air_flow_kg_s: float,
    cooling_COP: float,
    reheat_mode: str,
    reheat_COP: float,
    delta_h_pre_kJ_per_kg_da: float,
    e_p_Wh_per_kg_water: float,
    q_sorp_kJ_per_kg_water: float,
    chi_sorp_to_process_air: float,
    chi_elec_to_process_air: float,
    eta_internal_heat_to_desorp: float,
    desorption_heat_mode: str,
    external_desorp_heat_COP: float,
    process_dp_pa: float,
    receiver_dp_pa: float,
    fan_efficiency: float,
    receiver_T_C: float,
    receiver_RH: float,
    receiver_flow_ratio: float,
    max_receiver_RH: float,
    allow_overdehumidification: bool,
) -> dict[str, float | str | bool]:
    h_v = water_vapour_enthalpy(A.T_C)
    e_p_kJ_per_kg = 3.6 * e_p_Wh_per_kg_water

    denom = h_v - chi_sorp_to_process_air * q_sorp_kJ_per_kg_water - chi_elec_to_process_air * e_p_kJ_per_kg
    row: dict[str, float | str | bool] = {
        "delta_h_pre_kJ_per_kg_da": delta_h_pre_kJ_per_kg_da,
        "e_p_Wh_per_kg_water": e_p_Wh_per_kg_water,
        "q_sorp_kJ_per_kg_water": q_sorp_kJ_per_kg_water,
        "chi_sorp_to_process_air": chi_sorp_to_process_air,
        "chi_elec_to_process_air": chi_elec_to_process_air,
        "eta_internal_heat_to_desorp": eta_internal_heat_to_desorp,
        "denom_kJ_per_kg_water": denom,
        "valid_denom": denom > 0,
    }

    if denom <= 0:
        row.update({"feasible": False, "reason": "nonpositive_enthalpy_drop_denominator"})
        return row

    dw = delta_h_pre_kJ_per_kg_da / denom
    w_Ap = A.w - dw
    h_Ap = A.h - delta_h_pre_kJ_per_kg_da

    row["water_removed_g_per_kg_da"] = 1000.0 * dw
    row["A_prime_h_kJ_per_kg_da"] = h_Ap
    row["equivalent_f_of_total_latent_to_target"] = dw / (A.w - D.w) if A.w > D.w else np.nan

    if dw <= 0 or w_Ap <= 0:
        row.update({"feasible": False, "reason": "invalid_water_removal_or_negative_humidity"})
        return row

    over_dehumidifies = w_Ap < D.w - 1e-9
    if over_dehumidifies and not allow_overdehumidification:
        row.update({"feasible": False, "reason": "pre_step_removes_more_water_than_target_allows"})
        return row

    A_prime = state_from_h_w("A_prime", h_Ap, w_Ap)

    if not np.isfinite(A_prime.T_C) or A_prime.RH < 0:
        row.update({"feasible": False, "reason": "invalid_A_prime_state"})
        return row

    downstream = conventional_ac_route(
        inlet=A_prime,
        target=D,
        dry_air_flow_kg_s=dry_air_flow_kg_s,
        cooling_COP=cooling_COP,
        reheat_mode=reheat_mode,
        reheat_COP=reheat_COP,
    )

    water_kg_s = dry_air_flow_kg_s * dw
    P_EO_W = water_kg_s * e_p_Wh_per_kg_water * 3600.0
    Q_sorp_W = water_kg_s * q_sorp_kJ_per_kg_water * 1000.0
    Q_desorp_required_W = Q_sorp_W
    Q_internal_available_W = eta_internal_heat_to_desorp * (
        (1.0 - chi_sorp_to_process_air) * Q_sorp_W + (1.0 - chi_elec_to_process_air) * P_EO_W
    )
    Q_external_desorp_W = max(0.0, Q_desorp_required_W - Q_internal_available_W)
    external_purchased_W, external_ok, external_case = external_heat_case(
        Q_external_desorp_W, desorption_heat_mode, external_desorp_heat_COP
    )

    # Fan powers. Process-side volume flow is based on A. Receiver-side is optional and scales with receiver_flow_ratio.
    v_A = specific_volume_m3_per_kg_da(A.T_C, A.w)
    process_volume_flow_m3_s = dry_air_flow_kg_s * v_A
    process_fan_W = process_dp_pa * process_volume_flow_m3_s / fan_efficiency if fan_efficiency > 0 else np.inf

    receiver_in_w = humidity_ratio_from_T_RH(receiver_T_C, receiver_RH)
    receiver_dry_air_flow_kg_s = receiver_flow_ratio * dry_air_flow_kg_s
    if receiver_dry_air_flow_kg_s > 0:
        receiver_out_w = receiver_in_w + water_kg_s / receiver_dry_air_flow_kg_s
        receiver_out_RH = RH_from_T_w(receiver_T_C, receiver_out_w)
        receiver_out_T_C = receiver_T_C
        v_receiver = specific_volume_m3_per_kg_da(receiver_T_C, receiver_in_w)
        receiver_volume_flow_m3_s = receiver_dry_air_flow_kg_s * v_receiver
        receiver_fan_W = receiver_dp_pa * receiver_volume_flow_m3_s / fan_efficiency if fan_efficiency > 0 else np.inf
    else:
        receiver_out_w = np.nan
        receiver_out_RH = np.nan
        receiver_out_T_C = np.nan
        receiver_fan_W = 0.0

    receiver_feasible = bool(np.isfinite(receiver_out_RH) and receiver_out_RH <= max_receiver_RH)

    hybrid_total_W = downstream.total_purchased_W + P_EO_W + process_fan_W + receiver_fan_W + external_purchased_W
    avoided_downstream_W = baseline.total_purchased_W - downstream.total_purchased_W
    pre_step_net_gain_W = avoided_downstream_W - P_EO_W - process_fan_W - receiver_fan_W - external_purchased_W
    savings_pct = 100.0 * (baseline.total_purchased_W - hybrid_total_W) / baseline.total_purchased_W

    feasible = external_ok and receiver_feasible and (not downstream.infeasible_humidification or allow_overdehumidification)
    reason = "ok" if feasible else "receiver_or_external_heat_infeasible"

    row.update(
        {
            "feasible": feasible,
            "reason": reason,
            "external_heat_case": external_case,
            "A_T_C": A.T_C,
            "A_RH_pct": A.RH_pct,
            "A_w_g_per_kg_da": A.w_g_per_kg_da,
            "A_h_kJ_per_kg_da": A.h,
            "A_prime_T_C": A_prime.T_C,
            "A_prime_RH_pct": A_prime.RH_pct,
            "A_prime_w_g_per_kg_da": A_prime.w_g_per_kg_da,
            "D_T_C": D.T_C,
            "D_RH_pct": D.RH_pct,
            "D_w_g_per_kg_da": D.w_g_per_kg_da,
            "D_h_kJ_per_kg_da": D.h,
            "over_dehumidifies_target": over_dehumidifies,
            "baseline_total_purchased_W": baseline.total_purchased_W,
            "baseline_cooling_load_W": baseline.cooling_load_W,
            "baseline_reheat_load_W": baseline.reheat_load_W,
            "downstream_after_pre_total_purchased_W": downstream.total_purchased_W,
            "downstream_after_pre_cooling_load_W": downstream.cooling_load_W,
            "downstream_after_pre_reheat_load_W": downstream.reheat_load_W,
            "avoided_downstream_purchased_W": avoided_downstream_W,
            "EO_power_W": P_EO_W,
            "sorption_heat_total_W": Q_sorp_W,
            "sorption_heat_to_process_air_W": chi_sorp_to_process_air * Q_sorp_W,
            "electrical_heat_to_process_air_W": chi_elec_to_process_air * P_EO_W,
            "desorption_heat_required_W": Q_desorp_required_W,
            "internal_heat_available_for_desorp_W": Q_internal_available_W,
            "external_desorp_heat_W": Q_external_desorp_W,
            "external_desorp_purchased_W": external_purchased_W,
            "process_fan_power_W": process_fan_W,
            "receiver_fan_power_W": receiver_fan_W,
            "receiver_T_in_C": receiver_T_C,
            "receiver_RH_in_pct": 100.0 * receiver_RH,
            "receiver_flow_ratio": receiver_flow_ratio,
            "receiver_T_out_C_constT": receiver_out_T_C,
            "receiver_RH_out_pct_constT": 100.0 * receiver_out_RH if np.isfinite(receiver_out_RH) else np.nan,
            "receiver_feasible_constT": receiver_feasible,
            "hybrid_total_purchased_W": hybrid_total_W,
            "pre_step_net_gain_W": pre_step_net_gain_W,
            "savings_pct": savings_pct,
            "coil_exit_after_pre_T_C": downstream.coil_exit.T_C,
            "coil_exit_after_pre_w_g_per_kg_da": downstream.coil_exit.w_g_per_kg_da,
            "coil_exit_after_pre_h_kJ_per_kg_da": downstream.coil_exit.h,
        }
    )
    return row


def plot_psychrometric_paths(A: State, A_prime: State, D: State, baseline: ConventionalResult, downstream: ConventionalResult, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.5))

    T_grid = np.linspace(max(-5, min(A.T_C, A_prime.T_C, D.T_C) - 8), max(A.T_C, A_prime.T_C, D.T_C) + 10, 200)
    for RH in [0.2, 0.4, 0.6, 0.8, 1.0]:
        ws = [1000.0 * humidity_ratio_from_T_RH(T, RH) for T in T_grid]
        ax.plot(T_grid, ws, linewidth=0.8, alpha=0.45)
        ax.text(T_grid[-1], ws[-1], f"{int(RH*100)}%", fontsize=8, va="center")

    # Conventional A -> coil -> D
    ax.plot(
        [A.T_C, baseline.coil_exit.T_C, D.T_C],
        [A.w_g_per_kg_da, baseline.coil_exit.w_g_per_kg_da, D.w_g_per_kg_da],
        marker="o",
        label="Original route: A -> B/C -> D",
    )

    # Membrane pre-step A -> A' -> coil' -> D
    ax.plot(
        [A.T_C, A_prime.T_C, downstream.coil_exit.T_C, D.T_C],
        [A.w_g_per_kg_da, A_prime.w_g_per_kg_da, downstream.coil_exit.w_g_per_kg_da, D.w_g_per_kg_da],
        marker="s",
        label="With membrane pre-step: A -> A' -> B'/C' -> D",
    )

    for label, state in [("A", A), ("A'", A_prime), ("D", D)]:
        ax.annotate(label, (state.T_C, state.w_g_per_kg_da), textcoords="offset points", xytext=(6, 6), fontsize=11)

    ax.annotate("coil", (baseline.coil_exit.T_C, baseline.coil_exit.w_g_per_kg_da), textcoords="offset points", xytext=(6, -14), fontsize=9)
    ax.annotate("coil'", (downstream.coil_exit.T_C, downstream.coil_exit.w_g_per_kg_da), textcoords="offset points", xytext=(6, -14), fontsize=9)

    ax.set_xlabel("Dry-bulb temperature [C]")
    ax.set_ylabel("Humidity ratio [g/kg dry air]")
    ax.set_title("Original route vs membrane enthalpy pre-step")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def make_heatmaps(df: pd.DataFrame, out_dir: Path) -> None:
    plots = out_dir / "plots"
    plots.mkdir(parents=True, exist_ok=True)

    def _imshow_extent(xvals, yvals):
        """Return a non-singular imshow extent, also for one-row/one-column pivots."""
        x = np.asarray(xvals, dtype=float)
        y = np.asarray(yvals, dtype=float)

        if len(x) == 1:
            xpad = max(abs(x[0]) * 0.05, 1.0)
            xmin, xmax = x[0] - xpad, x[0] + xpad
        else:
            xs = np.sort(x)
            dx0 = xs[1] - xs[0]
            dx1 = xs[-1] - xs[-2]
            xmin, xmax = xs[0] - 0.5 * dx0, xs[-1] + 0.5 * dx1

        if len(y) == 1:
            ypad = max(abs(y[0]) * 0.05, 0.02)
            ymin, ymax = y[0] - ypad, y[0] + ypad
        else:
            ys = np.sort(y)
            dy0 = ys[1] - ys[0]
            dy1 = ys[-1] - ys[-2]
            ymin, ymax = ys[0] - 0.5 * dy0, ys[-1] + 0.5 * dy1

        return [xmin, xmax, ymin, ymax]

    for delta_h, q_sorp in sorted(
        set(zip(df["delta_h_pre_kJ_per_kg_da"], df["q_sorp_kJ_per_kg_water"]))
    ):
        sub = df[
            (df["delta_h_pre_kJ_per_kg_da"] == delta_h)
            & (df["q_sorp_kJ_per_kg_water"] == q_sorp)
            & (df["feasible"] == True)
        ]

        if sub.empty:
            continue

        piv = sub.pivot_table(
            index="chi_sorp_to_process_air",
            columns="e_p_Wh_per_kg_water",
            values="savings_pct",
            aggfunc="max",
        ).sort_index()

        if piv.empty:
            continue

        fig, ax = plt.subplots(figsize=(8, 5))

        extent = _imshow_extent(piv.columns.values, piv.index.values)

        im = ax.imshow(
            piv.values,
            origin="lower",
            aspect="auto",
            extent=extent,
        )
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("Best saving vs original route [%]")

        # Contours require at least a 2x2 grid.
        if piv.shape[0] >= 2 and piv.shape[1] >= 2:
            z = np.asarray(piv.values, dtype=float)
            finite = z[np.isfinite(z)]
            if finite.size > 0:
                zmin, zmax = float(np.nanmin(finite)), float(np.nanmax(finite))
                levels = [lev for lev in [0, 2, 5, 10] if zmin <= lev <= zmax]
                if levels:
                    ax.contour(
                        piv.columns.values,
                        piv.index.values,
                        piv.values,
                        levels=levels,
                        colors="k",
                        linewidths=0.8,
                    )
        else:
            ax.text(
                0.02,
                0.98,
                "Contours skipped: feasible grid has only one row/column",
                transform=ax.transAxes,
                va="top",
                ha="left",
                fontsize=8,
                bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
            )

        ax.set_xlabel("EO/ACEO energy e_p [Wh/kg water]")
        ax.set_ylabel("Fraction of sorption heat to process air, chi_sorp")
        ax.set_title(
            f"Pre-step saving map, Δh={delta_h:g} kJ/kg_da, q_sorp={q_sorp:g} kJ/kg"
        )
        fig.tight_layout()
        fig.savefig(plots / f"saving_map_dh_{delta_h:g}_qsorp_{q_sorp:g}.png", dpi=200)
        plt.close(fig)

    # Required water removal plot for each q_sorp and delta_h, using lowest e_p if possible.
    for delta_h in sorted(df["delta_h_pre_kJ_per_kg_da"].unique()):
        fig, ax = plt.subplots(figsize=(8, 5))
        plotted_any = False

        for q_sorp in sorted(df["q_sorp_kJ_per_kg_water"].unique()):
            sub = df[
                (df["delta_h_pre_kJ_per_kg_da"] == delta_h)
                & (df["q_sorp_kJ_per_kg_water"] == q_sorp)
            ]

            if sub.empty:
                continue

            ep_min = sub["e_p_Wh_per_kg_water"].min()
            curve = (
                sub[sub["e_p_Wh_per_kg_water"] == ep_min]
                .groupby("chi_sorp_to_process_air")["water_removed_g_per_kg_da"]
                .median()
            )

            if curve.empty:
                continue

            ax.plot(curve.index, curve.values, marker="o", label=f"q_sorp={q_sorp:g}, e_p={ep_min:g}")
            plotted_any = True

        ax.set_xlabel("Fraction of sorption heat to process air, chi_sorp")
        ax.set_ylabel("Required water removal [g/kg dry air]")
        ax.set_title(f"Water removal needed for Δh_pre={delta_h:g} kJ/kg_da")
        ax.grid(True, alpha=0.3)

        if plotted_any:
            ax.legend()

        fig.tight_layout()
        fig.savefig(plots / f"required_water_vs_chi_dh_{delta_h:g}.png", dpi=200)
        plt.close(fig)

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Direct model for a membrane pre-step that targets a chosen moist-air enthalpy drop before the ordinary AC route continues.")
    p.add_argument("--out", default="outputs/pre_enthalpy_drop")

    p.add_argument("--A-T-C", type=float, default=30.0)
    p.add_argument("--A-RH", type=float, default=0.80, help="Fraction, not percent. Ignored if --A-w-g-kg-da is set.")
    p.add_argument("--A-w-g-kg-da", type=float, default=None)

    p.add_argument("--D-T-C", type=float, default=22.0)
    p.add_argument("--D-RH", type=float, default=0.50, help="Fraction, not percent. Ignored if --D-w-g-kg-da is set.")
    p.add_argument("--D-w-g-kg-da", type=float, default=None)

    p.add_argument("--dry-air-flow-kg-s", type=float, default=1.0)
    p.add_argument("--cooling-COP", type=float, default=3.708)
    p.add_argument("--reheat-mode", choices=["free_reheat", "electric_reheat", "heat_pump_reheat"], default="free_reheat")
    p.add_argument("--reheat-COP", type=float, default=3.0)

    p.add_argument("--delta-h-pre-values", type=float, nargs="+", default=[5.0])
    p.add_argument("--pre-target-h-values", type=float, nargs="+", default=None, help="Optional target h_Aprime values. If set, these are converted to delta h = h_A - h_target.")

    p.add_argument("--e-p-values", type=float, nargs="+", default=[25, 50, 75, 100, 150, 200])
    p.add_argument("--q-sorp-values", type=float, nargs="+", default=[2200, 2431, 2600, 2800])
    p.add_argument("--chi-sorp-values", type=float, nargs="+", default=[0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0])
    p.add_argument("--chi-elec-values", type=float, nargs="+", default=[0.5])
    p.add_argument("--eta-internal-heat-to-desorp-values", type=float, nargs="+", default=[0, 0.5, 1.0])

    p.add_argument("--desorption-heat-mode", choices=["free", "paid", "none"], default="paid")
    p.add_argument("--external-desorp-heat-COP", type=float, default=3.0)

    p.add_argument("--process-dp-pa", type=float, default=0.0)
    p.add_argument("--receiver-dp-pa", type=float, default=0.0)
    p.add_argument("--fan-efficiency", type=float, default=0.5)

    p.add_argument("--receiver-T-C-values", type=float, nargs="+", default=[35.0, 40.0])
    p.add_argument("--receiver-RH-values", type=float, nargs="+", default=[0.20])
    p.add_argument("--receiver-flow-ratios", type=float, nargs="+", default=[0.5, 1.0, 2.0])
    p.add_argument("--max-receiver-RH", type=float, default=0.90)
    p.add_argument("--allow-overdehumidification", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.A_w_g_kg_da is None:
        A = state_from_T_RH("A", args.A_T_C, args.A_RH)
    else:
        A = state_from_T_w("A", args.A_T_C, args.A_w_g_kg_da / 1000.0)

    if args.D_w_g_kg_da is None:
        D = state_from_T_RH("D", args.D_T_C, args.D_RH)
    else:
        D = state_from_T_w("D", args.D_T_C, args.D_w_g_kg_da / 1000.0)

    if args.pre_target_h_values is not None:
        delta_h_values = [A.h - h_target for h_target in args.pre_target_h_values]
        delta_h_values = [x for x in delta_h_values if x > 0]
    else:
        delta_h_values = args.delta_h_pre_values

    baseline = conventional_ac_route(
        inlet=A,
        target=D,
        dry_air_flow_kg_s=args.dry_air_flow_kg_s,
        cooling_COP=args.cooling_COP,
        reheat_mode=args.reheat_mode,
        reheat_COP=args.reheat_COP,
    )

    rows = []
    for combo in product(
        delta_h_values,
        args.e_p_values,
        args.q_sorp_values,
        args.chi_sorp_values,
        args.chi_elec_values,
        args.eta_internal_heat_to_desorp_values,
        args.receiver_T_C_values,
        args.receiver_RH_values,
        args.receiver_flow_ratios,
    ):
        (
            delta_h,
            e_p,
            q_sorp,
            chi_sorp,
            chi_elec,
            eta_internal,
            rec_T,
            rec_RH,
            rec_flow,
        ) = combo
        rows.append(
            make_pre_step_case(
                A=A,
                D=D,
                baseline=baseline,
                dry_air_flow_kg_s=args.dry_air_flow_kg_s,
                cooling_COP=args.cooling_COP,
                reheat_mode=args.reheat_mode,
                reheat_COP=args.reheat_COP,
                delta_h_pre_kJ_per_kg_da=delta_h,
                e_p_Wh_per_kg_water=e_p,
                q_sorp_kJ_per_kg_water=q_sorp,
                chi_sorp_to_process_air=chi_sorp,
                chi_elec_to_process_air=chi_elec,
                eta_internal_heat_to_desorp=eta_internal,
                desorption_heat_mode=args.desorption_heat_mode,
                external_desorp_heat_COP=args.external_desorp_heat_COP,
                process_dp_pa=args.process_dp_pa,
                receiver_dp_pa=args.receiver_dp_pa,
                fan_efficiency=args.fan_efficiency,
                receiver_T_C=rec_T,
                receiver_RH=rec_RH,
                receiver_flow_ratio=rec_flow,
                max_receiver_RH=args.max_receiver_RH,
                allow_overdehumidification=args.allow_overdehumidification,
            )
        )

    df = pd.DataFrame(rows)
    csv_path = out_dir / "pre_enthalpy_drop_sweep.csv"
    df.to_csv(csv_path, index=False)

    feasible = df[df["feasible"] == True].copy() if "feasible" in df else pd.DataFrame()
    if not feasible.empty:
        sort_cols = ["savings_pct", "pre_step_net_gain_W", "receiver_flow_ratio", "water_removed_g_per_kg_da"]
        best = feasible.sort_values(sort_cols, ascending=[False, False, True, True]).head(200)
        best.to_csv(out_dir / "best_pre_enthalpy_drop_cases.csv", index=False)

        # Pick a representative best row for plotting.
        top = best.iloc[0]
        A_prime = state_from_h_w("A_prime", float(top["A_prime_h_kJ_per_kg_da"]), float(top["A_prime_w_g_per_kg_da"]) / 1000.0)
        downstream = conventional_ac_route(
            inlet=A_prime,
            target=D,
            dry_air_flow_kg_s=args.dry_air_flow_kg_s,
            cooling_COP=args.cooling_COP,
            reheat_mode=args.reheat_mode,
            reheat_COP=args.reheat_COP,
        )
        (out_dir / "plots").mkdir(exist_ok=True)
        plot_psychrometric_paths(A, A_prime, D, baseline, downstream, out_dir / "plots" / "best_process_path.png")

    make_heatmaps(df, out_dir)

    report = []
    report.append("# Pre-enthalpy-drop membrane model")
    report.append("")
    report.append("This model directly answers the pre-step question: can a membrane move the air from A to A' by a prescribed enthalpy drop before the ordinary AC route continues?")
    report.append("")
    report.append("## States")
    report.append("")
    report.append(f"- A: T={A.T_C:.3f} C, RH={A.RH_pct:.2f} %, w={A.w_g_per_kg_da:.3f} g/kg_da, h={A.h:.3f} kJ/kg_da")
    report.append(f"- D: T={D.T_C:.3f} C, RH={D.RH_pct:.2f} %, w={D.w_g_per_kg_da:.3f} g/kg_da, h={D.h:.3f} kJ/kg_da")
    report.append("")
    report.append("## Original route baseline")
    report.append("")
    report.append(f"- Reheat mode: `{args.reheat_mode}`")
    report.append(f"- Cooling COP: {args.cooling_COP:.3f}")
    report.append(f"- Baseline cooling load: {baseline.cooling_load_W:.3f} W")
    report.append(f"- Baseline reheat load: {baseline.reheat_load_W:.3f} W")
    report.append(f"- Baseline purchased power: {baseline.total_purchased_W:.3f} W")
    report.append(f"- Baseline coil exit: T={baseline.coil_exit.T_C:.3f} C, w={baseline.coil_exit.w_g_per_kg_da:.3f} g/kg_da, h={baseline.coil_exit.h:.3f} kJ/kg_da")
    report.append("")
    report.append("## Key equation")
    report.append("")
    report.append("```text")
    report.append("Delta w = Delta h_pre / (h_v - chi_sorp*q_sorp - chi_elec*3.6*e_p)")
    report.append("```")
    report.append("")
    report.append("where Delta w is kg water removed per kg dry air.")
    report.append("")
    report.append("## Files")
    report.append("")
    report.append(f"- `{csv_path}`")
    report.append("- `best_pre_enthalpy_drop_cases.csv`")
    report.append("- `plots/best_process_path.png`")
    report.append("- `plots/saving_map_*.png`")
    report.append("- `plots/required_water_vs_chi_*.png`")
    report.append("")

    if feasible.empty:
        report.append("## Result")
        report.append("")
        report.append("No feasible cases were found under the selected constraints.")
    else:
        report.append("## Best cases")
        report.append("")
        cols = [
            "savings_pct",
            "pre_step_net_gain_W",
            "delta_h_pre_kJ_per_kg_da",
            "water_removed_g_per_kg_da",
            "equivalent_f_of_total_latent_to_target",
            "A_prime_T_C",
            "A_prime_RH_pct",
            "A_prime_h_kJ_per_kg_da",
            "e_p_Wh_per_kg_water",
            "q_sorp_kJ_per_kg_water",
            "chi_sorp_to_process_air",
            "eta_internal_heat_to_desorp",
            "external_heat_case",
            "receiver_flow_ratio",
            "receiver_RH_out_pct_constT",
            "avoided_downstream_purchased_W",
            "EO_power_W",
            "external_desorp_purchased_W",
            "process_fan_power_W",
            "receiver_fan_power_W",
            "hybrid_total_purchased_W",
        ]
        cols = [c for c in cols if c in feasible.columns]
        report.append("```text")
        report.append(feasible.sort_values("savings_pct", ascending=False)[cols].head(60).to_string(index=False))
        report.append("```")

    report_path = out_dir / "pre_enthalpy_drop_report.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote results to: {out_dir}")
    print(report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
