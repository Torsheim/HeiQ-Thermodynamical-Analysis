# WP1 material decision memo

This memo summarizes the membrane and system targets implied by the WP1 stage-gate analysis.

## 1. Main takeaway

EO pre-drying remains interesting only if three things are simultaneously true:

1. EO energy is roughly in the 50--100 Wh/kg-water range, maybe up to 150 Wh/kg in favorable COP/heat cases.
2. Membrane flux is high enough to keep area practical, roughly several thousand g/(m2 h) or higher.
3. Sorption heat is mostly handled passively or usefully; active heat rejection quickly eats the benefit.

## 2. Required membrane area

```text
                  case  flux_g_m2_h  required_area_m2
Pre-dried: 32C, 30% RH       1000.0             55.40
Pre-dried: 32C, 30% RH       3000.0             18.47
Pre-dried: 32C, 30% RH       5000.0             11.08
Pre-dried: 32C, 30% RH      10000.0              5.54
Pre-dried: 32C, 50% RH       1000.0             33.56
Pre-dried: 32C, 50% RH       3000.0             11.19
Pre-dried: 32C, 50% RH       5000.0              6.71
Pre-dried: 32C, 50% RH      10000.0              3.36
```

Interpretation: 32C,50%RH is plausible at 3000--10000 g/(m2 h). The 30%RH case is much harder and needs either higher flux or larger area.

## 3. Effective EO transport target

At 1 V, the implied effective water transport per charge is:

```text
 design_e_p_Wh_per_kg_water  effective_H2O_per_charge
                       25.0                     59.51
                       50.0                     29.75
                      100.0                     14.88
                      150.0                      9.92
                      200.0                      7.44
```

Interpretation: 100 Wh/kg corresponds to about 15 H2O per charge. Lower energy requires stronger coupling.

## 4. Focus material requirement table

Assumptions: q_sorp=2431 kJ/kg, active_heat_fraction=0.25, voltage=1 V, membrane thickness=50 um, ohmic budget=25% of e_p.

```text
                  case    COP_case  ep_max_Wh_per_kg_water  design_e_p_Wh_per_kg_water  ep_margin_Wh_per_kg_water  passes_ep_stage_gate  flux_g_m2_h  required_area_m2  effective_H2O_per_charge  current_density_A_m2  electrical_power_density_W_m2  ASR_max_ohm_cm2  sigma_min_S_m  sigma_min_mS_cm
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                        50.0                    130.812                  True       1000.0            55.396                    29.754                  50.0                           50.0           50.000           0.01              0.1
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                        50.0                    130.812                  True       3000.0            18.465                    29.754                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                        50.0                    130.812                  True       5000.0            11.079                    29.754                 250.0                          250.0           10.000           0.05              0.5
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                        50.0                    130.812                  True      10000.0             5.540                    29.754                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       100.0                     80.812                  True       1000.0            55.396                    14.877                 100.0                          100.0           25.000           0.02              0.2
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       100.0                     80.812                  True       3000.0            18.465                    14.877                 300.0                          300.0            8.333           0.06              0.6
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       100.0                     80.812                  True       5000.0            11.079                    14.877                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       100.0                     80.812                  True      10000.0             5.540                    14.877                1000.0                         1000.0            2.500           0.20              2.0
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       150.0                     30.812                  True       1000.0            55.396                     9.918                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       150.0                     30.812                  True       3000.0            18.465                     9.918                 450.0                          450.0            5.556           0.09              0.9
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       150.0                     30.812                  True       5000.0            11.079                     9.918                 750.0                          750.0            3.333           0.15              1.5
Pre-dried: 32C, 30% RH fixed_COP_3                 180.812                       150.0                     30.812                  True      10000.0             5.540                     9.918                1500.0                         1500.0            1.667           0.30              3.0
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                        50.0                     35.978                  True       1000.0            55.396                    29.754                  50.0                           50.0           50.000           0.01              0.1
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                        50.0                     35.978                  True       3000.0            18.465                    29.754                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                        50.0                     35.978                  True       5000.0            11.079                    29.754                 250.0                          250.0           10.000           0.05              0.5
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                        50.0                     35.978                  True      10000.0             5.540                    29.754                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False       1000.0            55.396                    14.877                 100.0                          100.0           25.000           0.02              0.2
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False       3000.0            18.465                    14.877                 300.0                          300.0            8.333           0.06              0.6
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False       5000.0            11.079                    14.877                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False      10000.0             5.540                    14.877                1000.0                         1000.0            2.500           0.20              2.0
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False       1000.0            55.396                     9.918                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False       3000.0            18.465                     9.918                 450.0                          450.0            5.556           0.09              0.9
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False       5000.0            11.079                     9.918                 750.0                          750.0            3.333           0.15              1.5
Pre-dried: 32C, 30% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False      10000.0             5.540                     9.918                1500.0                         1500.0            1.667           0.30              3.0
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                        50.0                    130.812                  True       1000.0            33.557                    29.754                  50.0                           50.0           50.000           0.01              0.1
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                        50.0                    130.812                  True       3000.0            11.186                    29.754                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                        50.0                    130.812                  True       5000.0             6.711                    29.754                 250.0                          250.0           10.000           0.05              0.5
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                        50.0                    130.812                  True      10000.0             3.356                    29.754                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       100.0                     80.812                  True       1000.0            33.557                    14.877                 100.0                          100.0           25.000           0.02              0.2
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       100.0                     80.812                  True       3000.0            11.186                    14.877                 300.0                          300.0            8.333           0.06              0.6
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       100.0                     80.812                  True       5000.0             6.711                    14.877                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       100.0                     80.812                  True      10000.0             3.356                    14.877                1000.0                         1000.0            2.500           0.20              2.0
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       150.0                     30.812                  True       1000.0            33.557                     9.918                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       150.0                     30.812                  True       3000.0            11.186                     9.918                 450.0                          450.0            5.556           0.09              0.9
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       150.0                     30.812                  True       5000.0             6.711                     9.918                 750.0                          750.0            3.333           0.15              1.5
Pre-dried: 32C, 50% RH fixed_COP_3                 180.812                       150.0                     30.812                  True      10000.0             3.356                     9.918                1500.0                         1500.0            1.667           0.30              3.0
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                        50.0                     35.978                  True       1000.0            33.557                    29.754                  50.0                           50.0           50.000           0.01              0.1
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                        50.0                     35.978                  True       3000.0            11.186                    29.754                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                        50.0                     35.978                  True       5000.0             6.711                    29.754                 250.0                          250.0           10.000           0.05              0.5
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                        50.0                     35.978                  True      10000.0             3.356                    29.754                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False       1000.0            33.557                    14.877                 100.0                          100.0           25.000           0.02              0.2
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False       3000.0            11.186                    14.877                 300.0                          300.0            8.333           0.06              0.6
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False       5000.0             6.711                    14.877                 500.0                          500.0            5.000           0.10              1.0
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       100.0                    -14.022                 False      10000.0             3.356                    14.877                1000.0                         1000.0            2.500           0.20              2.0
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False       1000.0            33.557                     9.918                 150.0                          150.0           16.667           0.03              0.3
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False       3000.0            11.186                     9.918                 450.0                          450.0            5.556           0.09              0.9
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False       5000.0             6.711                     9.918                 750.0                          750.0            3.333           0.15              1.5
Pre-dried: 32C, 50% RH fixed_COP_5                  85.978                       150.0                    -64.022                 False      10000.0             3.356                     9.918                1500.0                         1500.0            1.667           0.30              3.0
```

## 5. Heat rejection requirement

```text
                  case  q_sorp_kJ_per_kg_water  sorption_heat_total_kW  active_heat_fraction  active_heat_kW  passive_heat_kW  deltaT_for_passive_rejection_K  UA_required_W_per_K
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.00            0.00            37.41                             5.0              7481.57
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.00            0.00            37.41                            10.0              3740.78
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.00            0.00            37.41                            20.0              1870.39
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.25            9.35            28.06                             5.0              5611.18
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.25            9.35            28.06                            10.0              2805.59
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.25            9.35            28.06                            20.0              1402.79
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.50           18.70            18.70                             5.0              3740.78
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.50           18.70            18.70                            10.0              1870.39
Pre-dried: 32C, 30% RH                  2431.0                   37.41                  0.50           18.70            18.70                            20.0               935.20
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.00            0.00            22.66                             5.0              4532.11
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.00            0.00            22.66                            10.0              2266.05
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.00            0.00            22.66                            20.0              1133.03
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.25            5.67            17.00                             5.0              3399.08
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.25            5.67            17.00                            10.0              1699.54
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.25            5.67            17.00                            20.0               849.77
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.50           11.33            11.33                             5.0              2266.05
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.50           11.33            11.33                            10.0              1133.03
Pre-dried: 32C, 50% RH                  2431.0                   22.66                  0.50           11.33            11.33                            20.0               566.51
```

Interpretation: required UA is large. This is probably one of the main system risks.

## 6. Conservative candidate window

Filter used: area <= 20 m2, current density <= 500 A/m2, power density <= 500 W/m2, and e_p stage gate passed.

```text
                  case    COP_case  design_e_p_Wh_per_kg_water  ep_margin_Wh_per_kg_water  flux_g_m2_h  required_area_m2  effective_H2O_per_charge  current_density_A_m2  electrical_power_density_W_m2  sigma_min_S_m  sigma_min_mS_cm
Pre-dried: 32C, 30% RH fixed_COP_3                        50.0                    130.812      10000.0             5.540                    29.754                 500.0                          500.0           0.10              1.0
Pre-dried: 32C, 30% RH fixed_COP_3                        50.0                    130.812       5000.0            11.079                    29.754                 250.0                          250.0           0.05              0.5
Pre-dried: 32C, 30% RH fixed_COP_3                        50.0                    130.812       3000.0            18.465                    29.754                 150.0                          150.0           0.03              0.3
Pre-dried: 32C, 30% RH fixed_COP_3                       100.0                     80.812       5000.0            11.079                    14.877                 500.0                          500.0           0.10              1.0
Pre-dried: 32C, 30% RH fixed_COP_3                       100.0                     80.812       3000.0            18.465                    14.877                 300.0                          300.0           0.06              0.6
Pre-dried: 32C, 30% RH fixed_COP_3                       150.0                     30.812       3000.0            18.465                     9.918                 450.0                          450.0           0.09              0.9
Pre-dried: 32C, 30% RH fixed_COP_5                        50.0                     35.978      10000.0             5.540                    29.754                 500.0                          500.0           0.10              1.0
Pre-dried: 32C, 30% RH fixed_COP_5                        50.0                     35.978       5000.0            11.079                    29.754                 250.0                          250.0           0.05              0.5
Pre-dried: 32C, 30% RH fixed_COP_5                        50.0                     35.978       3000.0            18.465                    29.754                 150.0                          150.0           0.03              0.3
Pre-dried: 32C, 50% RH fixed_COP_3                        50.0                    130.812      10000.0             3.356                    29.754                 500.0                          500.0           0.10              1.0
Pre-dried: 32C, 50% RH fixed_COP_3                        50.0                    130.812       5000.0             6.711                    29.754                 250.0                          250.0           0.05              0.5
Pre-dried: 32C, 50% RH fixed_COP_3                        50.0                    130.812       3000.0            11.186                    29.754                 150.0                          150.0           0.03              0.3
Pre-dried: 32C, 50% RH fixed_COP_3                       100.0                     80.812       5000.0             6.711                    14.877                 500.0                          500.0           0.10              1.0
Pre-dried: 32C, 50% RH fixed_COP_3                       100.0                     80.812       3000.0            11.186                    14.877                 300.0                          300.0           0.06              0.6
Pre-dried: 32C, 50% RH fixed_COP_3                       150.0                     30.812       3000.0            11.186                     9.918                 450.0                          450.0           0.09              0.9
Pre-dried: 32C, 50% RH fixed_COP_5                        50.0                     35.978      10000.0             3.356                    29.754                 500.0                          500.0           0.10              1.0
Pre-dried: 32C, 50% RH fixed_COP_5                        50.0                     35.978       5000.0             6.711                    29.754                 250.0                          250.0           0.05              0.5
Pre-dried: 32C, 50% RH fixed_COP_5                        50.0                     35.978       3000.0            11.186                    29.754                 150.0                          150.0           0.03              0.3
```

## 7. Recommended WP1 conclusion

The most credible near-term target window is:

- pre-dry to 50% RH first, not necessarily all the way to 30% RH;
- e_p = 50--100 Wh/kg-water;
- flux = 3000--10000 g/(m2 h);
- active membrane area roughly 3--12 m2 per kg_da/s for the 50%RH case;
- heat rejection design must be treated as a first-order system problem.

The 30%RH case gives larger HVAC savings, but the water removal, heat rejection, and area requirements are much tougher.