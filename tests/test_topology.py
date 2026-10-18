import numpy as np
import pytest

from genesis.core.topology import diffuse


def test_closed_impulse_exact_stencil():
    field = np.zeros((5, 5))
    field[2, 2] = 1
    expected = np.zeros((5, 5))
    expected[2, 2] = 0.6
    expected[1, 2] = expected[3, 2] = expected[2, 1] = expected[2, 3] = 0.1
    np.testing.assert_allclose(
        diffuse(field, np.ones_like(field, dtype=bool), 0.1, "closed"), expected, atol=1e-16
    )


def test_closed_boundary_and_periodic_wrap():
    field = np.zeros((3, 4))
    field[0, 0] = 1
    land = np.ones_like(field, dtype=bool)
    closed = diffuse(field, land, 0.1, "closed")
    periodic = diffuse(field, land, 0.1, "periodic")
    assert closed[0, 0] == pytest.approx(0.8)
    assert closed[-1, 0] == closed[0, -1] == 0
    assert periodic[0, 0] == pytest.approx(0.6)
    assert periodic[-1, 0] == periodic[0, -1] == 0.1


@pytest.mark.parametrize("boundary", ["closed", "periodic"])
@pytest.mark.parametrize("shape", [(1, 1), (1, 9), (9, 1), (2, 2), (11, 17)])
@pytest.mark.parametrize("rate", [0.0, 0.1, 0.25])
def test_transport_conservation_positivity_and_no_input_mutation(boundary, shape, rate):
    rng = np.random.default_rng(79)
    land = rng.random(shape) > 0.25
    field = rng.random(shape) * land
    before = field.copy()
    original_total = field.sum()
    for _ in range(100):
        field = diffuse(field, land, rate, boundary)
        assert np.min(field) >= 0
        assert not np.any(field[~land])
    assert field.sum() == pytest.approx(original_total, abs=1e-12, rel=1e-12)
    untouched = before.copy()
    diffuse(before, land, rate, boundary)
    np.testing.assert_array_equal(before, untouched)


@pytest.mark.parametrize("boundary", ["closed", "periodic"])
def test_land_barrier_is_impermeable(boundary):
    land = np.ones((5, 7), dtype=bool)
    land[:, [0, 3, 6]] = False
    field = np.zeros((5, 7))
    field[2, 1] = 10
    for _ in range(50):
        field = diffuse(field, land, 0.25, boundary)
    assert field[:, 4:6].sum() == 0
    assert field[:, 1:3].sum() == pytest.approx(10)


@pytest.mark.parametrize("amplitude", [0.1, 0.6113431084989805])
def test_positivity_at_stability_limit_with_decimal_impulse(amplitude):
    field = np.zeros((3, 3))
    field[1, 1] = amplitude
    result = diffuse(field, np.ones_like(field, dtype=bool), 0.25, "closed")
    assert result.min() >= 0


@pytest.mark.parametrize("rate", [-0.1, 0.2501, float("nan")])
def test_unstable_rate_rejected(rate):
    with pytest.raises(ValueError):
        diffuse(np.ones((2, 2)), np.ones((2, 2), dtype=bool), rate, "closed")
