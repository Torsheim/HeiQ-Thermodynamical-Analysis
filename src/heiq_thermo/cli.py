"""Command-line interface for HeiQ thermodynamic analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .ac_eo import square_wave_average_flux, vapor_phase_aceo_water_flux
from .model import load_yaml, run_first_model, save_summary_text
from .plots import plot_best_savings_vs_heat_fraction, plot_savings_map, plot_simple_psychrometric_chart


def cmd_run(args: argparse.Namespace) -> None:
    config = load_yaml(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df, summary = run_first_model(config)
    csv_path = out_dir / "sensitivity_results.csv"
    df.to_csv(csv_path, index=False)
    save_summary_text(summary, out_dir / "summary.txt")

    plot_simple_psychrometric_chart(
        summary["start"],
        summary["target"],
        out_dir / "psychrometric_routes.png",
        dry_air_mass_flow_kg_s=summary["dry_air_mass_flow_kg_s"],
        example_e_p_Wh_per_kg_water=float(config["plots"].get("example_e_p_Wh_per_kg_water", 300.0)),
        example_heat_to_process_fraction=float(config["plots"].get("example_heat_to_process_fraction", 0.25)),
    )

    for chi in config["plots"].get("savings_map_heat_fractions", [0.0, 0.5, 1.0]):
        plot_savings_map(df, out_dir / f"savings_map_chi_{float(chi):.2f}.png", float(chi))
    plot_best_savings_vs_heat_fraction(df, out_dir / "best_savings_vs_heat_fraction.png")

    best = df.loc[df["savings_pct"].idxmax()]
    print(f"Wrote results to: {out_dir}")
    print(f"CSV: {csv_path}")
    print("Best case in sweep:")
    print(best[["f_latent_by_eo", "e_p_Wh_per_kg_water", "heat_to_process_fraction", "savings_pct", "hybrid_P_total_W", "conventional_P_total_W"]].to_string())


def cmd_aceo_demo(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    coeffs = [args.a1, args.a2, args.a3]
    rows = []
    for i_plus in np.linspace(args.i_min, args.i_max, args.n_i):
        for duty in np.linspace(0.1, 0.9, args.n_duty):
            res = square_wave_average_flux(i_plus, duty, coeffs, zero_net_charge=True)
            water_flux = vapor_phase_aceo_water_flux(res["J_avg"], args.mobile_water_factor)
            rows.append({
                "i_plus_A_m2": i_plus,
                "duty_plus": duty,
                "i_minus_A_m2": res["i_minus_A_m2"],
                "i_rms_A_m2": res["i_rms_A_m2"],
                "J_liquid_surrogate_m_s": res["J_avg"],
                "mobile_water_factor": args.mobile_water_factor,
                "J_water_kg_m2_s": water_flux,
            })
    df = pd.DataFrame(rows)
    csv_path = out_dir / "aceo_surrogate_sweep.csv"
    df.to_csv(csv_path, index=False)
    print(f"Wrote ACEO surrogate sweep to: {csv_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HeiQ thermodynamic analysis tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run first psychrometric/system model")
    p_run.add_argument("--config", default="scenarios/first_model.yaml", help="YAML scenario file")
    p_run.add_argument("--out", default="outputs/first_model", help="Output directory")
    p_run.set_defaults(func=cmd_run)

    p_aceo = sub.add_parser("aceo-demo", help="Run a simple asymmetric EO surrogate sweep")
    p_aceo.add_argument("--out", default="outputs/aceo_demo")
    p_aceo.add_argument("--a1", type=float, default=0.0)
    p_aceo.add_argument("--a2", type=float, default=1e-12)
    p_aceo.add_argument("--a3", type=float, default=0.0)
    p_aceo.add_argument("--i-min", type=float, default=10.0)
    p_aceo.add_argument("--i-max", type=float, default=1000.0)
    p_aceo.add_argument("--n-i", type=int, default=50)
    p_aceo.add_argument("--n-duty", type=int, default=41)
    p_aceo.add_argument("--mobile-water-factor", type=float, default=0.1)
    p_aceo.set_defaults(func=cmd_aceo_demo)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
