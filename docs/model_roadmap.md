# HeiQ thermodynamic-analysis model roadmap

## Model 1: thermodynamic/system screening

Model 1 treats EO/ACEO dehumidification as a black-box water-removal step with a specified energy cost in Wh/kg water. It answers:

> How efficient must EO/ACEO water removal be for a hybrid system to beat a conventional AC baseline?

## Model 1.1: reheat-threshold analysis

This adds reheat assumptions and break-even threshold calculations.

## Model 1.2: robustness analysis

This adds:

- f-capped threshold tables, so the exact f=1 full-latent-removal jump is separated from partial-removal cases.
- fixed-EO-energy plots, so heat-to-process sensitivity is not hidden by always choosing the lowest EO energy.
- evaporator-model comparison:
  - `linear_by_fraction`: optimistic interpolation.
  - `strict_dewpoint_until_full`: conservative assumption that the coil remains at the conventional dewpoint evaporator temperature until EO/ACEO removes all latent load.

## Model 2: area and flux product screen

Model 2 translates water-removal requirements into physical product requirements:

- required active membrane area,
- required membrane flux,
- EO electrical power density,
- optional extra fan power from added pressure drop.

This is still not a full membrane device model, but it adds a product-feasibility filter:

> Even if Wh/kg is good, is the required active area remotely plausible?

## Model 3: physical EO/ACEO membrane model

Future step:

- liquid EO/ACEO surrogate,
- vapor/mobile-water factor,
- sorption and hydration dynamics,
- pulse strategies,
- back-diffusion.
