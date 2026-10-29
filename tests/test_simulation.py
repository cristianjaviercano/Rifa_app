import pytest
from scripts.simulate import run


@pytest.mark.parametrize("method", ["INTERNAL_CSPRNG", "EXTERNAL_LOTTERY"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_full_simulation(pg, method, seed):
    s = run(pg, buyers=30, seed=seed, method=method)
    assert s["aprobadas"] > 0 and s["sorteo"]["method"] == method
