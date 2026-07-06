# WP1 decision memo: EO pre-drying stage gate

## Question

Can EO-based pre-drying reduce purchased HVAC energy enough to justify moving to more detailed membrane and system design?

## Stage-gate equation

```text
P_net = P_saved - P_EO - P_thermal - P_fan
```

A case passes the first stage gate if `P_net > 0`.

## Key result 1: optimistic/passive heat handling

If sorption heat is handled passively or usefully, the allowable EO energy is:

```text
                  case    COP_case  water_removed_by_predrying_kg_h  saved_purchased_power_vs_baseline_kW  penalized_break_even_e_p_Wh_per_kg_water
Pre-dried: 32C, 30% RH fixed_COP_3                        55.396222                             13.133623                                237.085185
Pre-dried: 32C, 30% RH fixed_COP_5                        55.396222                              7.880174                                142.251111
Pre-dried: 32C, 50% RH fixed_COP_3                        33.557362                              7.955953                                237.085185
Pre-dried: 32C, 50% RH fixed_COP_5                        33.557362                              4.773572                                142.251111
```

Interpretation: the simple break-even target is roughly 237 Wh/kg water at COP 3 and 142 Wh/kg water at COP 5.

## Key result 2: conservative active heat rejection

If all sorption heat must be rejected actively with COP 3, the allowable EO energy collapses:

```text
                  case    COP_case  sorption_heat_kW  thermal_penalty_kW  penalized_break_even_e_p_Wh_per_kg_water
Pre-dried: 32C, 30% RH fixed_COP_3         37.407838           12.469279                                 11.992593
Pre-dried: 32C, 30% RH fixed_COP_5         37.407838           12.469279                                  0.000000
Pre-dried: 32C, 50% RH fixed_COP_3         22.660541            7.553514                                 11.992593
Pre-dried: 32C, 50% RH fixed_COP_5         22.660541            7.553514                                  0.000000
```

Interpretation: this case is too strict for a viable product unless external/passive heat rejection is available.

## Key result 3: moderate heat-handling penalty

For an intermediate assumption where 25% of sorption heat is actively handled:

```text
                  case    COP_case  e_p_Wh_per_kg_water  saved_purchased_power_vs_baseline_kW  EO_power_kW  thermal_penalty_kW  net_saving_kW  net_saving_pct_of_baseline  passes_stage_gate  passes_5pct_net_saving  passes_10pct_net_saving
Pre-dried: 32C, 30% RH fixed_COP_3                 50.0                             13.133623     2.769811            3.117320       7.246493                   42.366880               True                    True                     True
Pre-dried: 32C, 30% RH fixed_COP_3                100.0                             13.133623     5.539622            3.117320       4.476682                   26.173080               True                    True                     True
Pre-dried: 32C, 30% RH fixed_COP_3                150.0                             13.133623     8.309433            3.117320       1.706870                    9.979279               True                    True                    False
Pre-dried: 32C, 30% RH fixed_COP_3                200.0                             13.133623    11.079244            3.117320      -1.062941                   -6.214521              False                   False                    False
Pre-dried: 32C, 30% RH fixed_COP_5                 50.0                              7.880174     2.769811            3.117320       1.993043                   19.420665               True                    True                     True
Pre-dried: 32C, 30% RH fixed_COP_5                100.0                              7.880174     5.539622            3.117320      -0.776768                   -7.569002              False                   False                    False
Pre-dried: 32C, 30% RH fixed_COP_5                150.0                              7.880174     8.309433            3.117320      -3.546579                  -34.558669              False                   False                    False
Pre-dried: 32C, 30% RH fixed_COP_5                200.0                              7.880174    11.079244            3.117320      -6.316390                  -61.548336              False                   False                    False
Pre-dried: 32C, 50% RH fixed_COP_3                 50.0                              7.955953     1.677868            1.888378       4.389707                   25.664579               True                    True                     True
Pre-dried: 32C, 50% RH fixed_COP_3                100.0                              7.955953     3.355736            1.888378       2.711839                   15.854863               True                    True                     True
Pre-dried: 32C, 50% RH fixed_COP_3                150.0                              7.955953     5.033604            1.888378       1.033971                    6.045147               True                    True                    False
Pre-dried: 32C, 50% RH fixed_COP_3                200.0                              7.955953     6.711472            1.888378      -0.643897                   -3.764569              False                   False                    False
Pre-dried: 32C, 50% RH fixed_COP_5                 50.0                              4.773572     1.677868            1.888378       1.207326                   11.764454               True                    True                     True
Pre-dried: 32C, 50% RH fixed_COP_5                100.0                              4.773572     3.355736            1.888378      -0.470543                   -4.585073              False                   False                    False
Pre-dried: 32C, 50% RH fixed_COP_5                150.0                              4.773572     5.033604            1.888378      -2.148411                  -20.934600              False                   False                    False
Pre-dried: 32C, 50% RH fixed_COP_5                200.0                              4.773572     6.711472            1.888378      -3.826279                  -37.284127              False                   False                    False
```

## Preliminary WP1 conclusion

- EO pre-drying is energetically interesting if EO energy is roughly below 100--150 Wh/kg water.
- The concept is very sensitive to heat handling.
- If most sorption heat can be rejected passively or used on the exit side, WP1 should continue.
- If most sorption heat requires active cooling, the energy case becomes weak.

## Recommended next action

Use this as the WP1 stage-gate summary, then proceed to quantify feasible membrane properties: flux, area, conductivity, EO transport number, and heat rejection architecture.