# Model 2 portfolio summary and Model 3 target translator

This package adds two scripts.

## `scripts/make_model2_portfolio_summary.py`

Condenses `outputs/model2_scenario_sweep/` into robust product-facing requirements across all psychrometric scenarios.

It produces:

- `robust_min_area_across_scenarios.csv`
- `robust_min_flux_across_scenarios.csv`
- `scenario_severity_sorted.csv`
- `model2_portfolio_summary.md`
- plots of robust area/flux requirements

The robust values only count as robust if all scenarios in the sweep are solved.

## `scripts/run_model3_transport_targets.py`

Translates Model 2 targets into effective electrical transport requirements.

It does not claim a mechanistic ACEO model. It computes the effective coupling needed for a given black-box energy cost and water flux:

```text
charge_per_kg = e_p * 3600 / V
kg_water_per_C = 1 / charge_per_kg
effective_water_molecules_per_charge = kg_water_per_C * F / M_water
current_density = water_flux / kg_water_per_C
power_density = current_density * V
```

Use this to compare experimental ACEO/Nafion measurements against the product-level targets from Model 2.
