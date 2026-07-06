from __future__ import annotations

from pathlib import Path
import pandas as pd


REQ_PATH = Path("outputs/wp1_material_requirements/wp1_material_requirements_all.csv")
HEAT_PATH = Path("outputs/wp1_material_requirements/wp1_heat_rejection_UA_requirements.csv")
OUT_DIR = Path("outputs/wp1_material_requirements")
DOCS_DIR = Path("docs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path)


def compact_float(df: pd.DataFrame, cols: list[str], ndigits: int = 3) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = out[c].round(ndigits)
    return out


def main() -> None:
    req = read_required(REQ_PATH)
    heat = read_required(HEAT_PATH)

    # Focus: simple, interpretable fixed-COP cases.
    focus = req[
        (req["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
        & (req["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (req["active_heat_fraction"] == 0.25)
        & (req["extra_fan_power_kW"] == 0.0)
        & (req["voltage_V"] == 1.0)
        & (req["ohmic_budget_fraction_of_ep"] == 0.25)
        & (req["thickness_um"] == 50.0)
        & (req["design_e_p_Wh_per_kg_water"].isin([50.0, 100.0, 150.0]))
        & (req["flux_g_m2_h"].isin([1000.0, 3000.0, 5000.0, 10000.0]))
    ].copy()

    focus = focus.drop_duplicates(
        [
            "case",
            "COP_case",
            "design_e_p_Wh_per_kg_water",
            "flux_g_m2_h",
            "voltage_V",
            "thickness_um",
            "ohmic_budget_fraction_of_ep",
        ]
    )

    focus_cols = [
        "case",
        "COP_case",
        "ep_max_Wh_per_kg_water",
        "design_e_p_Wh_per_kg_water",
        "ep_margin_Wh_per_kg_water",
        "passes_ep_stage_gate",
        "flux_g_m2_h",
        "required_area_m2",
        "effective_H2O_per_charge",
        "current_density_A_m2",
        "electrical_power_density_W_m2",
        "ASR_max_ohm_cm2",
        "sigma_min_S_m",
        "sigma_min_mS_cm",
    ]

    focus_out = compact_float(
        focus[focus_cols].sort_values(
            ["case", "COP_case", "design_e_p_Wh_per_kg_water", "flux_g_m2_h"]
        ),
        [
            "ep_max_Wh_per_kg_water",
            "ep_margin_Wh_per_kg_water",
            "required_area_m2",
            "effective_H2O_per_charge",
            "current_density_A_m2",
            "electrical_power_density_W_m2",
            "ASR_max_ohm_cm2",
            "sigma_min_S_m",
            "sigma_min_mS_cm",
        ],
        3,
    )

    focus_out.to_csv(OUT_DIR / "compact_material_focus_table.csv", index=False)

    # Area-only table: independent of e_p and voltage.
    area = req[
        (req["COP_case"] == "fixed_COP_3")
        & (req["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (req["active_heat_fraction"] == 0.25)
        & (req["extra_fan_power_kW"] == 0.0)
        & (req["flux_g_m2_h"].isin([1000.0, 3000.0, 5000.0, 10000.0]))
    ][["case", "flux_g_m2_h", "required_area_m2"]].drop_duplicates()

    area = compact_float(area.sort_values(["case", "flux_g_m2_h"]), ["required_area_m2"], 2)
    area.to_csv(OUT_DIR / "compact_area_by_flux.csv", index=False)

    # Electrical target table.
    electrical = req[
        (req["voltage_V"] == 1.0)
        & (req["design_e_p_Wh_per_kg_water"].isin([25.0, 50.0, 100.0, 150.0, 200.0]))
    ][[
        "design_e_p_Wh_per_kg_water",
        "effective_H2O_per_charge",
    ]].drop_duplicates().sort_values("design_e_p_Wh_per_kg_water")

    electrical = compact_float(electrical, ["effective_H2O_per_charge"], 2)
    electrical.to_csv(OUT_DIR / "compact_effective_water_per_charge.csv", index=False)

    # Heat rejection table: remove duplicates caused by extra fan cases.
    heat_focus = heat[
        (heat["COP_case"] == "fixed_COP_3")
        & (heat["q_sorp_kJ_per_kg_water"] == 2431.0)
        & (heat["active_heat_fraction"].isin([0.0, 0.25, 0.5]))
        & (heat["deltaT_for_passive_rejection_K"].isin([5.0, 10.0, 20.0]))
    ][[
        "case",
        "q_sorp_kJ_per_kg_water",
        "sorption_heat_total_kW",
        "active_heat_fraction",
        "active_heat_kW",
        "passive_heat_kW",
        "deltaT_for_passive_rejection_K",
        "UA_required_W_per_K",
    ]].drop_duplicates()

    heat_focus = compact_float(
        heat_focus.sort_values(["case", "active_heat_fraction", "deltaT_for_passive_rejection_K"]),
        [
            "sorption_heat_total_kW",
            "active_heat_kW",
            "passive_heat_kW",
            "UA_required_W_per_K",
        ],
        2,
    )
    heat_focus.to_csv(OUT_DIR / "compact_heat_rejection_table.csv", index=False)

    # Conservative product candidates.
    # These are not final design points, only reasonable WP1 regions.
    candidates = focus[
        (focus["passes_ep_stage_gate"])
        & (focus["required_area_m2"] <= 20.0)
        & (focus["current_density_A_m2"] <= 500.0)
        & (focus["electrical_power_density_W_m2"] <= 500.0)
        & (focus["design_e_p_Wh_per_kg_water"].isin([50.0, 100.0, 150.0]))
    ].copy()

    candidate_cols = [
        "case",
        "COP_case",
        "design_e_p_Wh_per_kg_water",
        "ep_margin_Wh_per_kg_water",
        "flux_g_m2_h",
        "required_area_m2",
        "effective_H2O_per_charge",
        "current_density_A_m2",
        "electrical_power_density_W_m2",
        "sigma_min_S_m",
        "sigma_min_mS_cm",
    ]

    candidates = compact_float(
        candidates[candidate_cols].sort_values(
            ["case", "COP_case", "design_e_p_Wh_per_kg_water", "required_area_m2"]
        ),
        [
            "ep_margin_Wh_per_kg_water",
            "required_area_m2",
            "effective_H2O_per_charge",
            "current_density_A_m2",
            "electrical_power_density_W_m2",
            "sigma_min_S_m",
            "sigma_min_mS_cm",
        ],
        3,
    )

    candidates.to_csv(OUT_DIR / "compact_product_candidate_table.csv", index=False)

    memo = []
    memo.append("# WP1 material decision memo")
    memo.append("")
    memo.append("This memo summarizes the membrane and system targets implied by the WP1 stage-gate analysis.")
    memo.append("")
    memo.append("## 1. Main takeaway")
    memo.append("")
    memo.append("EO pre-drying remains interesting only if three things are simultaneously true:")
    memo.append("")
    memo.append("1. EO energy is roughly in the 50--100 Wh/kg-water range, maybe up to 150 Wh/kg in favorable COP/heat cases.")
    memo.append("2. Membrane flux is high enough to keep area practical, roughly several thousand g/(m2 h) or higher.")
    memo.append("3. Sorption heat is mostly handled passively or usefully; active heat rejection quickly eats the benefit.")
    memo.append("")
    memo.append("## 2. Required membrane area")
    memo.append("")
    memo.append("```text")
    memo.append(area.to_string(index=False))
    memo.append("```")
    memo.append("")
    memo.append("Interpretation: 32C,50%RH is plausible at 3000--10000 g/(m2 h). The 30%RH case is much harder and needs either higher flux or larger area.")
    memo.append("")
    memo.append("## 3. Effective EO transport target")
    memo.append("")
    memo.append("At 1 V, the implied effective water transport per charge is:")
    memo.append("")
    memo.append("```text")
    memo.append(electrical.to_string(index=False))
    memo.append("```")
    memo.append("")
    memo.append("Interpretation: 100 Wh/kg corresponds to about 15 H2O per charge. Lower energy requires stronger coupling.")
    memo.append("")
    memo.append("## 4. Focus material requirement table")
    memo.append("")
    memo.append("Assumptions: q_sorp=2431 kJ/kg, active_heat_fraction=0.25, voltage=1 V, membrane thickness=50 um, ohmic budget=25% of e_p.")
    memo.append("")
    memo.append("```text")
    memo.append(focus_out.head(120).to_string(index=False))
    memo.append("```")
    memo.append("")
    memo.append("## 5. Heat rejection requirement")
    memo.append("")
    memo.append("```text")
    memo.append(heat_focus.to_string(index=False))
    memo.append("```")
    memo.append("")
    memo.append("Interpretation: required UA is large. This is probably one of the main system risks.")
    memo.append("")
    memo.append("## 6. Conservative candidate window")
    memo.append("")
    memo.append("Filter used: area <= 20 m2, current density <= 500 A/m2, power density <= 500 W/m2, and e_p stage gate passed.")
    memo.append("")
    if candidates.empty:
        memo.append("No candidates passed the conservative filters.")
    else:
        memo.append("```text")
        memo.append(candidates.to_string(index=False))
        memo.append("```")
    memo.append("")
    memo.append("## 7. Recommended WP1 conclusion")
    memo.append("")
    memo.append("The most credible near-term target window is:")
    memo.append("")
    memo.append("- pre-dry to 50% RH first, not necessarily all the way to 30% RH;")
    memo.append("- e_p = 50--100 Wh/kg-water;")
    memo.append("- flux = 3000--10000 g/(m2 h);")
    memo.append("- active membrane area roughly 3--12 m2 per kg_da/s for the 50%RH case;")
    memo.append("- heat rejection design must be treated as a first-order system problem.")
    memo.append("")
    memo.append("The 30%RH case gives larger HVAC savings, but the water removal, heat rejection, and area requirements are much tougher.")

    out_md = DOCS_DIR / "wp1_material_decision_memo.md"
    out_md.write_text("\n".join(memo), encoding="utf-8")

    print(f"Wrote: {out_md}")
    print(f"Wrote: {OUT_DIR / 'compact_material_focus_table.csv'}")
    print(f"Wrote: {OUT_DIR / 'compact_area_by_flux.csv'}")
    print(f"Wrote: {OUT_DIR / 'compact_effective_water_per_charge.csv'}")
    print(f"Wrote: {OUT_DIR / 'compact_heat_rejection_table.csv'}")
    print(f"Wrote: {OUT_DIR / 'compact_product_candidate_table.csv'}")
    print()
    print(out_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
