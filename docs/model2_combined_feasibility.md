# Model 2 combined feasibility

This script combines two requirements that must both hold for a product-relevant EO/ACEO dehumidification module:

1. **Energy:** EO/ACEO water removal must have low enough electrical energy use, measured as `e_p_Wh_per_kg_water`.
2. **Flux/area:** the membrane must move enough water per area, measured as `flux_g_m2_h`, so required active area is plausible.

The script produces a 2D feasibility map with:

- x-axis: EO/ACEO energy, Wh/kg water
- y-axis: available membrane flux, g/(m2 h)
- colour: best system saving after optimizing over latent fraction `f`
- constraints: maximum active area and optional extra fan power due to pressure drop

## Why this is the next step

Model 1 showed that EO/ACEO can be attractive if energy use is low enough. Model 2 area screening showed that low energy is not enough: membrane area can become enormous if flux is low.

This script combines those two filters into one decision surface.

## Typical command

```bash
python scripts/run_model2_combined_feasibility.py \
  --config scenarios/first_model.yaml \
  --out outputs/model2_combined_feasibility \
  --ep-start 25 \
  --ep-stop 800 \
  --n-ep 90 \
  --flux-start 100 \
  --flux-stop 50000 \
  --n-flux 90 \
  --reheat-cases free_reheat heat_pump_reheat_COP3 electric_reheat \
  --evap-models strict_dewpoint_until_full linear_by_fraction \
  --heat-fractions 0.5 \
  --pressure-drop-values 0 50 100 \
  --area-limits 5 10 20 50 \
  --primary-case free_reheat \
  --primary-evap-model strict_dewpoint_until_full \
  --primary-heat-fraction 0.5 \
  --primary-pressure-drop-pa 50 \
  --primary-area-limit-m2 10 \
  --require-positive-eo
```

## Key outputs

- `combined_feasibility_results.csv`: full grid results.
- `max_e_p_by_available_flux.csv`: for a given available flux cap, how high can Wh/kg be?
- `min_flux_by_e_p.csv`: for a given Wh/kg, how high must membrane flux be?
- `primary_maps/combined_savings_map.png`: energy/flux feasibility map for the primary scenario.
- `primary_maps/best_f_map.png`: which latent fraction the optimizer selects.
- `primary_maps/required_area_map.png`: required active membrane area.
- `combined_feasibility_report.md`: short summary.

## Interpretation

A good product region likely needs both:

```text
e_p <= 100--200 Wh/kg water
J_w >= several thousand to >10,000 g/(m2 h)
```

The exact thresholds depend strongly on reheat assumptions, coil assumptions, allowable active area, and pressure drop.
