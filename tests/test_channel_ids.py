"""A channel is found by its id, never by its position in `CHANNELS`
(docs/specs/2026-10-01-renewal-rate-path-file.md §4, §8 commit 2).

Income is stream 7 and no channel, so once a channel takes an id past it the
ids skip 7 and a position is no longer an id. `decomposition.channel()` and
`run_monte_carlo`'s two freeze guards must therefore read the ids off the
table. These pins run against a table whose ids skip 7, so a lookup or a
guard that still reads positions, or a literal id range, fails here before a
real channel 8 exists.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

import hde.decomposition as dc
import hde.monte_carlo as mc
from hde.config import load_config_dict

FIXTURE = Path(__file__).parent / "fixtures" / "min_interaction.yaml"
# A probe channel two past the highest id on the real table, so the gap below
# it is no channel whatever the real table holds.
PROBE = max(entry.id for entry in dc.CHANNELS) + 2
GAP = PROBE - 1
SKIPPING = dc.CHANNELS + (dc.Channel(id=PROBE, key="probe", label="a probe channel",
                                     sizing_keys=()),)


@pytest.fixture
def skipping_table(monkeypatch):
    monkeypatch.setattr(dc, "CHANNELS", SKIPPING)
    monkeypatch.setattr(mc, "_CHANNELS", SKIPPING)


def _spec(paths: int = 20):
    raw = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    raw.setdefault("simulation", {})["num_sims"] = paths
    return load_config_dict(raw)


def test_every_channel_resolves_by_its_own_id():
    for entry in dc.CHANNELS:
        assert dc.channel(entry.id) is entry
    with pytest.raises(KeyError):
        dc.channel(dc.INCOME_STREAM_ID)
    with pytest.raises(KeyError):
        dc.channel(-1)


def test_an_id_past_a_gap_resolves_and_the_gap_raises(skipping_table):
    assert dc.channel(PROBE).key == "probe"
    with pytest.raises(KeyError):
        dc.channel(GAP)
    with pytest.raises(KeyError):
        dc.channel(PROBE + 1)


def test_the_freeze_guard_reads_its_ids_off_the_table(skipping_table):
    spec = _spec()
    streams = mc.addressed_streams(spec.simulation.random_seed)
    mc.run_monte_carlo(spec, streams, freeze=(PROBE,))
    with pytest.raises(ValueError, match="which is no channel"):
        mc.run_monte_carlo(spec, streams, freeze=(GAP,))
    with pytest.raises(ValueError, match="which is no channel"):
        mc.run_monte_carlo(spec, streams, freeze=(PROBE + 1,))
    with pytest.raises(ValueError, match="which is no channel"):
        mc.run_monte_carlo(spec, streams, freeze=(dc.INCOME_STREAM_ID,))


def test_the_legacy_binding_takes_a_freeze_of_every_id_on_the_table(skipping_table):
    spec = _spec()
    every = sorted({entry.id for entry in SKIPPING})
    mc.run_monte_carlo(spec, freeze=every)
    with pytest.raises(ValueError, match="partial freeze"):
        mc.run_monte_carlo(spec, freeze=[i for i in every if i != PROBE])
