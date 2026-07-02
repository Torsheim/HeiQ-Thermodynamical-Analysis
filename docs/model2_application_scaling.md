# Model 2 application scaling

This script converts the energy/flux feasibility analysis into an application sizing map.

It answers questions such as:

- For a given EO/ACEO energy cost and membrane flux, how much dry-air flow can be treated?
- How does the answer change with active membrane area?
- Does a technology with e.g. 100--200 g/(m2 h) flux make sense for full HVAC loads, or only for smaller air streams / larger membrane packs?

The central scaling is

\[
J_\mathrm{req} = \frac{\dot m_{da}\,\Delta w}{A_m}
\]

with unit conversion to g/(m2 h). A case with 1 kg_da/s and 100 m2 active area has approximately the same latent-load-per-area as 0.1 kg_da/s and 10 m2.
