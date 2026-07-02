from heiq_thermo.ac_eo import square_wave_average_flux, kelvin_rh_threshold


def test_symmetric_linear_eo_cancels_under_zero_charge_ac():
    res = square_wave_average_flux(i_plus_A_m2=100.0, duty_plus=0.5, coeffs=[1.2e-9], zero_net_charge=True)
    assert abs(res["J_avg"]) < 1e-20


def test_quadratic_nonlinearity_survives_symmetric_ac():
    res = square_wave_average_flux(i_plus_A_m2=100.0, duty_plus=0.5, coeffs=[0.0, 1e-12], zero_net_charge=True)
    assert res["J_avg"] > 0


def test_kelvin_threshold_between_zero_and_one():
    rh = kelvin_rh_threshold(radius_m=5e-9, T_C=30.0)
    assert 0.0 < rh < 1.0
