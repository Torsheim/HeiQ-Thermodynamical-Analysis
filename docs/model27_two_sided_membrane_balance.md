# Model 2.7: two-sided membrane water and heat balance

This model adds a receiver/exhaust side to the membrane dehumidification analysis.

Previous Model 2.6 separated process-side sorption heat from EO/ACEO electrical heat. It answered: how much sorption heat can return to the process air while still saving energy?

Model 2.7 adds the next physical question: where does the water go, and what heat is required to release it on the receiver side?

## Core idea

The process side removes water vapour from humid supply air and sorbs it into the membrane. This releases sorption heat.

The receiver side must accept the water. If water leaves the membrane as vapour, desorption heat is required. That heat may come from:

1. sorption heat conducted or transported through the membrane,
2. EO/ACEO electrical heat not released to the process air,
3. receiver air by evaporative cooling,
4. external heat or a heat pump.

The model is a bookkeeping model. It does not yet solve spatial heat conduction, membrane water chemical potential, or detailed ACEO physics.

## Main variables

- `f_latent_by_membrane`: fraction of process latent load removed by the membrane.
- `e_p_Wh_per_kg_water`: EO/ACEO electrical energy per kg water removed.
- `q_sorp_kJ_per_kg_water`: heat released when process-side water vapour becomes sorbed membrane water.
- `q_desorp_kJ_per_kg_water`: heat required to release membrane water as receiver-side vapour.
- `chi_sorp_to_process_air`: fraction of sorption heat returned to process air.
- `eta_sorp_heat_to_desorp`: fraction of non-process sorption heat that can be reused to drive receiver-side desorption.
- `chi_desorp_from_receiver_air`: fraction of remaining desorption heat taken from receiver air.
- `receiver_flow_ratio`: receiver dry-air flow divided by process dry-air flow.

## Outputs

- receiver outlet temperature and RH,
- process-side HVAC purchased power,
- EO/ACEO power,
- external desorption heat power,
- total savings vs conventional AC,
- feasible design points satisfying receiver RH and savings constraints.

## Important limitation

The model assumes the receiver stream can accept water as vapour. If receiver outlet RH exceeds the chosen limit, the design point is marked infeasible. Condensation on the receiver side is not yet modeled explicitly.
