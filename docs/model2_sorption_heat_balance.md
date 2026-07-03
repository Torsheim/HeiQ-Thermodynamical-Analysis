# Model 2.6: sorption heat balance

This model extends the previous EO/ACEO dehumidification screening by separating two heat sources:

1. **EO/ACEO electrical heat**, controlled by `chi_elec_to_process_air`.
2. **Sorption heat**, controlled by `chi_sorp_to_process_air`.

The new membrane step uses

```text
h_air_after_membrane = h_air_in
                       - Δw_membrane * h_vapour
                       + chi_sorp * Δw_membrane * q_sorp
                       + chi_elec * Δw_membrane * e_p * 3.6
```

where:

- `Δw_membrane` is kg water removed by the membrane per kg dry air,
- `h_vapour` is the water-vapour enthalpy at inlet temperature in kJ/kg water,
- `q_sorp` is the heat released when one kg of vapour becomes sorbed membrane water,
- `e_p` is the EO/ACEO electrical energy in Wh/kg water.

The key new parameter is not only `q_sorp`, but also `chi_sorp_to_process_air`.
If `chi_sorp_to_process_air` is close to 1, most sorption heat returns to the supply air.
If it is close to 0, the membrane module rejects sorption heat to another heat sink.

## Why this matters

For the design case, full water removal is about 13.35 g/kg dry air. If `q_sorp` is near the latent heat of vaporization, the sorption heat is around 32 kJ/kg dry air. This can be much larger than EO electrical input at `e_p = 50--100 Wh/kg water`.

Therefore earlier Model 2 results should be interpreted as favourable cases unless sorption heat is explicitly accounted for.

## Main output

Run:

```bash
python scripts/run_model2_sorption_heat_balance.py \
  --config scenarios/first_model.yaml \
  --out outputs/model2_sorption_heat_balance \
  --reheat-modes free_reheat heat_pump_reheat_COP3 electric_reheat \
  --f-values 0.25 0.5 0.75 1.0 \
  --e-p-values 50 100 150 200 300 \
  --q-sorp-values 2200 2431 2600 2800 3000 \
  --chi-elec-values 0 0.5 1 \
  --n-chi-sorp 51 \
  --sorption-heat-rejection-cops 0 \
  --target-savings 0 2 5 10 \
  --add-hydration-surrogate-q
```

Important files:

```text
outputs/model2_sorption_heat_balance/sorption_heat_balance_report.md
outputs/model2_sorption_heat_balance/sorption_heat_balance_sweep.csv
outputs/model2_sorption_heat_balance/max_chi_sorp_for_savings.csv
outputs/model2_sorption_heat_balance/decision_thresholds_compact.csv
outputs/model2_sorption_heat_balance/plots/
```

## Interpretation

`max_chi_sorp_for_savings.csv` answers:

> What is the largest fraction of sorption heat that may return to process air while still meeting the desired saving target?

A low allowed `chi_sorp` means the design must remove sorption heat away from process air.
A high allowed `chi_sorp` means the system is tolerant to sorption heat release into the process air.

## Literature priors

See:

```text
scenarios/nafion_literature_priors.yaml
```

These priors include water uptake, approximate water-state fractions, a transport sanity check, and a recommended sorption-heat sweep.
