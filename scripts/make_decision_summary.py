from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _fmt(x: float) -> str:
    if pd.isna(x):
        return "NaN"
    return f"{x:.1f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a concise decision summary from Model 1 robustness and Model 2 area/flux outputs."
    )
    parser.add_argument(
        "--thresholds",
        default="outputs/model1_robustness/thresholds_compact.csv",
        help="Path to Model 1 robustness thresholds_compact.csv",
    )
    parser.add_argument(
        "--area-limits",
        default="outputs/model2_area_flux_screen/required_flux_for_area_limits.csv",
        help="Path to Model 2 required_flux_for_area_limits.csv",
    )
    parser.add_argument(
        "--area-results",
        default="outputs/model2_area_flux_screen/area_flux_results.csv",
        help="Path to Model 2 area_flux_results.csv",
    )
    parser.add_argument(
        "--out",
        default="outputs/decision_summary",
        help="Output directory",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    thresholds = pd.read_csv(args.thresholds)
    area_limits = pd.read_csv(args.area_limits)
    area_results = pd.read_csv(args.area_results)

    # Remove physically meaningless f=0 threshold artifacts.
    thresholds = thresholds[thresholds["f_at_max_e_p"] > 1e-9].copy()

    # Key thresholds for decision-making.
    key = thresholds[
        (thresholds["target_savings_pct"].isin([5.0, 10.0]))
        & (thresholds["heat_to_process_fraction"].isin([0.0, 0.5, 1.0]))
        & (thresholds["f_cap"].isin([1.0, 0.99, 0.95]))
    ].copy()

    key = key.sort_values(
        [
            "evap_model",
            "f_cap",
            "case",
            "heat_to_process_fraction",
            "target_savings_pct",
        ]
    )

    key.to_csv(out_dir / "key_energy_thresholds.csv", index=False)

    # Conservative envelope:
    # strict coil, no exact f=1 transition, robust 5% and 10%.
    conservative = key[
        (key["evap_model"] == "strict_dewpoint_until_full")
        & (key["f_cap"].isin([0.99, 0.95]))
        & (key["target_savings_pct"].isin([5.0, 10.0]))
    ].copy()

    conservative_summary = (
        conservative.groupby(["target_savings_pct", "heat_to_process_fraction"])
        ["max_e_p_any_f_Wh_per_kg"]
        .agg(["min", "median", "max"])
        .reset_index()
        .rename(
            columns={
                "min": "worst_case_allowed_Wh_per_kg",
                "median": "median_allowed_Wh_per_kg",
                "max": "best_case_allowed_Wh_per_kg",
            }
        )
    )

    conservative_summary.to_csv(out_dir / "conservative_energy_envelope.csv", index=False)

    # Optimistic envelope:
    # exact f=1 allowed.
    optimistic = key[
        (key["f_cap"] == 1.0)
        & (key["target_savings_pct"].isin([5.0, 10.0]))
    ].copy()

    optimistic_summary = (
        optimistic.groupby(["target_savings_pct", "heat_to_process_fraction"])
        ["max_e_p_any_f_Wh_per_kg"]
        .agg(["min", "median", "max"])
        .reset_index()
        .rename(
            columns={
                "min": "worst_case_allowed_Wh_per_kg",
                "median": "median_allowed_Wh_per_kg",
                "max": "best_case_allowed_Wh_per_kg",
            }
        )
    )

    optimistic_summary.to_csv(out_dir / "optimistic_energy_envelope.csv", index=False)

    # Area/flux requirements for full latent removal.
    area_full = area_limits[area_limits["f_latent_by_eo"].round(6) == 1.0].copy()
    area_full = area_full.sort_values("area_limit_m2")
    area_full.to_csv(out_dir / "required_flux_full_latent_by_area.csv", index=False)

    # Example area requirements at selected fluxes for full latent removal.
    if "flux_g_m2_h" in area_results.columns:
        example_fluxes = [100, 300, 1000, 3000, 10000, 30000]
        full_area = area_results[area_results["f_latent_by_eo"].round(6) == 1.0].copy()
        full_area = full_area[full_area["flux_g_m2_h"].isin(example_fluxes)]
        full_area = full_area.sort_values("flux_g_m2_h")
        full_area.to_csv(out_dir / "required_area_full_latent_by_flux.csv", index=False)
    else:
        full_area = pd.DataFrame()

    # Make markdown report.
    report = []
    report.append("# HeiQ decision summary")
    report.append("")
    report.append("This summary condenses Model 1.2 robustness and Model 2 area/flux screening.")
    report.append("")
    report.append("## Main interpretation")
    report.append("")
    report.append(
        "- Conservative thresholds use `strict_dewpoint_until_full` and exclude reliance on the exact `f=1` transition."
    )
    report.append(
        "- Optimistic thresholds allow exact full latent removal (`f=1`), where the coil can become purely sensible."
    )
    report.append(
        "- Area requirements assume the full scenario: 30 C / 80% RH to 22 C / 50% RH at 1 kg dry air/s."
    )
    report.append("")
    report.append("## Conservative EO/ACEO energy envelope")
    report.append("")
    report.append("Allowed EO/ACEO energy in Wh/kg water:")
    report.append("")
    report.append("```text")
    report.append(conservative_summary.to_string(index=False))
    report.append("```")
    report.append("")
    report.append("Suggested conservative product target:")
    report.append("")
    report.append("```text")
    report.append("5% saving:   e_p roughly <= 125--175 Wh/kg_water")
    report.append("10% saving:  e_p roughly <= 100--150 Wh/kg_water")
    report.append("```")
    report.append("")
    report.append("## Optimistic EO/ACEO energy envelope")
    report.append("")
    report.append("This includes exact full latent removal, f=1:")
    report.append("")
    report.append("```text")
    report.append(optimistic_summary.to_string(index=False))
    report.append("```")
    report.append("")
    report.append("## Flux and area requirements")
    report.append("")
    report.append("Required flux for full latent removal at selected area limits:")
    report.append("")
    report.append("```text")
    report.append(area_full.to_string(index=False))
    report.append("```")
    report.append("")
    if not full_area.empty:
        report.append("Required membrane area at selected fluxes for full latent removal:")
        report.append("")
        cols = [c for c in ["flux_g_m2_h", "required_area_m2", "water_removed_by_eo_kg_h"] if c in full_area.columns]
        report.append("```text")
        report.append(full_area[cols].to_string(index=False))
        report.append("```")
        report.append("")

    report.append("## Practical product implication")
    report.append("")
    report.append(
        "Energy target alone is insufficient. A plausible product region likely requires both:"
    )
    report.append("")
    report.append("```text")
    report.append("e_p <= 100--150 Wh/kg_water")
    report.append("J_w >= 5,000--10,000 g/(m2 h) for compact full-latent-removal HVAC")
    report.append("```")
    report.append("")
    report.append(
        "If J_w is near 1,000 g/(m2 h), the required membrane area is tens of square meters per kg_da/s."
    )

    (out_dir / "decision_summary.md").write_text("\n".join(report), encoding="utf-8")

    print("\nWrote decision summary to:", out_dir)
    print("\nConservative energy envelope:")
    print(conservative_summary.to_string(index=False))
    print("\nRequired flux for full latent removal:")
    print(area_full.to_string(index=False))


if __name__ == "__main__":
    main()
