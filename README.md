# HeiQ Thermodynamical Analysis

First-pass thermodynamic and psychrometric analysis for electroosmotic / asymmetric-electroosmotic assisted air dehumidification.

This repository starts with a deliberately simple model:

1. Compute moist-air states from dry-bulb temperature and relative humidity.
2. Compare psychrometric routes from a hot/humid inlet state to a target supply-air state.
3. Treat the EO/ACEO stage as a black-box water-removal device with an assumed electrical energy use in Wh/kg water.
4. Sweep the fraction of latent load handled by EO/ACEO and the energy cost of EO/ACEO water removal.
5. Estimate total purchased electric power for conventional AC vs hybrid EO/ACEO + AC.

The model is intentionally not yet a product-design model. It is a screening tool for answering:

> How good must the EO/ACEO water pump be before it can save system energy?

## Why this model is set up this way

For a fixed start and end point in a psychrometric chart, moist-air enthalpy change is fixed:

```text
Delta h = h_target - h_start
```

The possible benefit of EO/ACEO is not that `Delta h` becomes smaller. The possible benefit is that the process path changes which components provide the energy removal, and the cooling coil may be able to work at a higher effective evaporating temperature.

## Installation

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows PowerShell alternative

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the first model

```bash
heiq-thermo run --config scenarios/first_model.yaml --out outputs/first_model
```

or equivalently:

```bash
python -m heiq_thermo.cli run --config scenarios/first_model.yaml --out outputs/first_model
```

The run creates:

```text
outputs/first_model/summary.txt
outputs/first_model/sensitivity_results.csv
outputs/first_model/psychrometric_routes.png
outputs/first_model/savings_map_chi_0.00.png
outputs/first_model/savings_map_chi_0.50.png
outputs/first_model/savings_map_chi_1.00.png
outputs/first_model/best_savings_vs_heat_fraction.png
```

## Run tests

```bash
pytest
```

## Run the ACEO surrogate demo

This does **not** claim to model vapor ACEO correctly. It only implements a low-order surrogate for asymmetric AC electroosmosis:

```text
J(i) = a1*i + a2*i^2 + a3*i^3 + ...
```

Odd terms cancel under symmetric zero-net-charge AC. Even terms can produce non-zero period-averaged pumping if the system is nonlinear and asymmetric.

```bash
heiq-thermo aceo-demo --out outputs/aceo_demo --a2 1e-12 --mobile-water-factor 0.1
```

This writes:

```text
outputs/aceo_demo/aceo_surrogate_sweep.csv
```

## Main scenario parameters

Edit `scenarios/first_model.yaml`.

Important inputs:

```yaml
start:
  T_C: 30.0
  RH: 0.80

target:
  T_C: 22.0
  RH: 0.50

eo:
  fraction_latent_by_eo_grid:
    start: 0.0
    stop: 1.0
    n: 51

  e_p_Wh_per_kg_water_grid:
    start: 25.0
    stop: 1000.0
    n: 80

  heat_to_process_fraction_grid: [0.0, 0.25, 0.50, 0.75, 1.0]
```

Interpretation:

- `fraction_latent_by_eo = 0`: conventional AC baseline.
- `fraction_latent_by_eo = 1`: EO/ACEO removes all required water before the coil.
- `e_p_Wh_per_kg_water`: electrical energy required by EO/ACEO per kg water removed.
- `heat_to_process_fraction`: fraction of EO/ACEO electric input that heats the process/supply air.

## Model limitations

This first model uses several deliberate simplifications:

- Simple HVAC psychrometric correlations.
- Modified-Carnot COP model.
- EO/ACEO is a black-box water pump parameterized by Wh/kg water.
- The hybrid coil evaporator temperature is approximated by a simple interpolation as EO/ACEO takes more latent load.
- Pressure drops and fan power are not included yet.
- Vapor-phase ACEO is not proven by this model; it is represented by a `mobile_water_factor` multiplier in the ACEO surrogate.

These simplifications are useful at this stage because they expose the required performance targets for the membrane/pump team.

## Suggested next steps

1. Replace the simple COP model with a calibrated chiller/heat-pump map.
2. Add fan power and pressure drop.
3. Add heat recovery or separate cathode/reject-air heat accounting.
4. Add measured EO/ACEO water flux vs waveform, RH and temperature.
5. Replace the `mobile_water_factor` with a sorption/capillary-condensation model or experimental fit.
6. Add uncertainty ranges and Monte Carlo sensitivity analysis.
