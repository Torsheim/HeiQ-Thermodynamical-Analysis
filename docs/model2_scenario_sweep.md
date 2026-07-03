# Model 2.3 scenario sweep

The previous Model 2 application-scaling analysis used one psychrometric case. This sweep repeats the same product-facing analysis across several inlet/target air conditions.

The goal is to answer:

> Are the EO/ACEO energy/flux/area targets robust across climates, or are they only attractive in one humid design point?

The script:

1. reads a scenario list from `scenarios/climate_scenarios.yaml`,
2. creates a temporary config for each scenario,
3. runs `run_model2_load_area_scaling.py`,
4. runs `make_application_decision_tables.py`,
5. aggregates minimum area and minimum flux tables across scenarios,
6. writes a compact Markdown report and a few plots.

Important outputs:

- `scenario_summary.csv`: psychrometric severity of each scenario.
- `all_min_area_for_desired_flows.csv`: merged design table across scenarios.
- `all_min_flux_for_desired_flows.csv`: merged flux table across scenarios.
- `scenario_sweep_report.md`: compact summary.

Interpretation:

- High `delta_w_g_per_kg_da` means high latent load.
- Required membrane flux and area scale almost linearly with latent load at fixed selected EO/ACEO fraction.
- If a scenario has low sensible cooling demand, the benefit of separating latent/sensible loads may be different from hot-humid conditions.
