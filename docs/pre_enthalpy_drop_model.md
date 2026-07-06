# Pre-enthalpy-drop membrane model

This model tests the corrected process hypothesis:

- Original route: A -> B -> C -> D.
- New route: A -> A' -> B' -> C' -> D.
- The membrane pre-step A -> A' is chosen by a target moist-air enthalpy drop, for example h_A - h_A' = 5 kJ/kg dry air, or h_A' = 40 kJ/kg dry air.

The required membrane water removal is solved from

```text
Delta w = Delta h_pre / (h_v - chi_sorp*q_sorp - chi_elec*3.6*e_p)
```

where:

- Delta w is kg water removed per kg dry air.
- h_v is water-vapour enthalpy at the inlet temperature.
- q_sorp is the assumed sorption heat in kJ/kg water.
- chi_sorp is the fraction of sorption heat returned to process air.
- e_p is EO/ACEO electrical energy in Wh/kg water.
- chi_elec is the fraction of electrical input heating process air.

The script then compares:

```text
original purchased power from A to D
```

against

```text
membrane pre-step power + ordinary AC purchased power from A' to D
```

It writes CSV tables, a markdown report, heatmaps, a required-water-removal plot, and a psychrometric route plot.
