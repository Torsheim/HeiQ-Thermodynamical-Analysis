from __future__ import annotations

from pathlib import Path
import pandas as pd


OUT = Path("outputs/wp1_stage_gate_summary")
DOCS = Path("docs")
DOCS.mkdir(exist_ok=True)

stage = pd.read_csv(OUT / "wp1_stage_gate_candidates.csv")
be = pd.read_csv(OUT / "wp1_stage_gate_break_even_ep.csv")

# Focus cases for text
passive = be[
    (be["q_sorp_kJ_per_kg_water"] == 2431.0)
    & (be["active_heat_fraction"] == 0.0)
    & (be["extra_fan_power_kW"] == 0.0)
    & (be["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
].copy()

full_active = be[
    (be["q_sorp_kJ_per_kg_water"] == 2431.0)
    & (be["active_heat_fraction"] == 1.0)
    & (be["extra_fan_power_kW"] == 0.0)
    & (be["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
].copy()

moderate = stage[
    (stage["q_sorp_kJ_per_kg_water"] == 2431.0)
    & (stage["active_heat_fraction"] == 0.25)
    & (stage["extra_fan_power_kW"] == 0.0)
    & (stage["e_p_Wh_per_kg_water"].isin([50.0, 100.0, 150.0, 200.0]))
    & (stage["COP_case"].isin(["fixed_COP_3", "fixed_COP_5"]))
].copy()

cols = [
    "case",
    "COP_case",
    "e_p_Wh_per_kg_water",
    "saved_purchased_power_vs_baseline_kW",
    "EO_power_kW",
    "thermal_penalty_kW",
    "net_saving_kW",
    "net_saving_pct_of_baseline",
    "passes_stage_gate",
    "passes_5pct_net_saving",
    "passes_10pct_net_saving",
]

memo = []
memo.append("# WP1 decision memo: EO pre-drying stage gate")
memo.append("")
memo.append("## Question")
memo.append("")
memo.append("Can EO-based pre-drying reduce purchased HVAC energy enough to justify moving to more detailed membrane and system design?")
memo.append("")
memo.append("## Stage-gate equation")
memo.append("")
memo.append("```text")
memo.append("P_net = P_saved - P_EO - P_thermal - P_fan")
memo.append("```")
memo.append("")
memo.append("A case passes the first stage gate if `P_net > 0`.")
memo.append("")
memo.append("## Key result 1: optimistic/passive heat handling")
memo.append("")
memo.append("If sorption heat is handled passively or usefully, the allowable EO energy is:")
memo.append("")
memo.append("```text")
memo.append(passive[[
    "case",
    "COP_case",
    "water_removed_by_predrying_kg_h",
    "saved_purchased_power_vs_baseline_kW",
    "penalized_break_even_e_p_Wh_per_kg_water",
]].to_string(index=False))
memo.append("```")
memo.append("")
memo.append("Interpretation: the simple break-even target is roughly 237 Wh/kg water at COP 3 and 142 Wh/kg water at COP 5.")
memo.append("")
memo.append("## Key result 2: conservative active heat rejection")
memo.append("")
memo.append("If all sorption heat must be rejected actively with COP 3, the allowable EO energy collapses:")
memo.append("")
memo.append("```text")
memo.append(full_active[[
    "case",
    "COP_case",
    "sorption_heat_kW",
    "thermal_penalty_kW",
    "penalized_break_even_e_p_Wh_per_kg_water",
]].to_string(index=False))
memo.append("```")
memo.append("")
memo.append("Interpretation: this case is too strict for a viable product unless external/passive heat rejection is available.")
memo.append("")
memo.append("## Key result 3: moderate heat-handling penalty")
memo.append("")
memo.append("For an intermediate assumption where 25% of sorption heat is actively handled:")
memo.append("")
memo.append("```text")
memo.append(moderate[cols].sort_values(["case", "COP_case", "e_p_Wh_per_kg_water"]).to_string(index=False))
memo.append("```")
memo.append("")
memo.append("## Preliminary WP1 conclusion")
memo.append("")
memo.append("- EO pre-drying is energetically interesting if EO energy is roughly below 100--150 Wh/kg water.")
memo.append("- The concept is very sensitive to heat handling.")
memo.append("- If most sorption heat can be rejected passively or used on the exit side, WP1 should continue.")
memo.append("- If most sorption heat requires active cooling, the energy case becomes weak.")
memo.append("")
memo.append("## Recommended next action")
memo.append("")
memo.append("Use this as the WP1 stage-gate summary, then proceed to quantify feasible membrane properties: flux, area, conductivity, EO transport number, and heat rejection architecture.")

path = DOCS / "wp1_decision_memo.md"
path.write_text("\n".join(memo), encoding="utf-8")
print(f"Wrote {path}")
