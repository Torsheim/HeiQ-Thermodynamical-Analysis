# Model notes

## Core question

The first model answers:

```text
For a given inlet state and target state, how efficient must the EO/ACEO dehumidifier be to reduce total purchased electric power?
```

## Start and target states

Default:

```text
A = 30 C, 80% RH
B = 22 C, 50% RH
```

The code computes humidity ratio, enthalpy and dew point for each state.

## Conventional route

The conventional route assumes cooling/dehumidification to the saturated state with the target humidity ratio, then reheat/mixing to target.

```text
A -> D_sat(w_B) -> B
```

## Hybrid route

The hybrid route assumes EO/ACEO removes a fraction `f` of the required water before the cooling coil:

```text
A -> C_f -> B
```

The EO/ACEO step is parameterized by:

```text
e_p = Wh/kg water removed
chi = fraction of EO power that heats process air
```

## ACEO surrogate

The low-order ACEO surrogate is:

```text
J(i) = a1*i + a2*i^2 + a3*i^3 + ...
```

This represents the qualitative idea that linear EO reverses with current and cancels under symmetric AC, while nonlinear asymmetric terms can produce non-zero average pumping.

The vapor extension is not assumed to be valid. It is multiplied by a `mobile_water_factor` representing adsorbed-film or capillary-condensed water availability.
