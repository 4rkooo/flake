import pytest

from flake.harness import retro, versions

G = "taco-council"


def test_retro_refuses_while_a_canary_is_on_trial(db, monkeypatch):
    versions.create(G, versions.V1_POLICY, "seed", None, created_by="seed", status="active")
    canary_id = versions.create(G, versions.V1_POLICY, "retro", None, status="canary")
    # if the guard fails, the run would reach the (stubbed) episode read below
    monkeypatch.setattr(retro.memory, "resolved_episodes", lambda g: pytest.fail("retro ran"), raising=False)
    with pytest.raises(RuntimeError, match=canary_id):
        retro.run(G)
    assert len(versions.history(G)) == 2  # no new version
