from heiq_thermo.psychrometrics import (
    dew_point_from_T_RH,
    humidity_ratio,
    moist_air_enthalpy_kJ_per_kg_da,
    relative_humidity_from_T_w,
    state_from_T_RH,
)


def test_start_state_30C_80RH_is_reasonable():
    s = state_from_T_RH(30.0, 0.80)
    assert 0.021 < s.w < 0.0225
    assert 84.0 < s.h_kJ_per_kg_da < 87.0
    assert 26.0 < s.dew_point_C < 27.0


def test_target_state_22C_50RH_is_reasonable():
    s = state_from_T_RH(22.0, 0.50)
    assert 0.0080 < s.w < 0.0086
    assert 42.0 < s.h_kJ_per_kg_da < 44.5
    assert 10.0 < s.dew_point_C < 12.5


def test_relative_humidity_roundtrip():
    T = 25.0
    RH = 0.55
    w = humidity_ratio(T, RH)
    RH2 = relative_humidity_from_T_w(T, w)
    assert abs(RH2 - RH) < 1e-10


def test_enthalpy_increases_with_humidity_at_fixed_temperature():
    T = 30.0
    w1 = humidity_ratio(T, 0.3)
    w2 = humidity_ratio(T, 0.8)
    assert moist_air_enthalpy_kJ_per_kg_da(T, w2) > moist_air_enthalpy_kJ_per_kg_da(T, w1)


def test_dewpoint_below_drybulb_for_unsaturated_air():
    assert dew_point_from_T_RH(30.0, 0.80) < 30.0
