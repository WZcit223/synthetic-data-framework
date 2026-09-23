"""Tests for the name catalog."""

from __future__ import annotations

import pytest

from .catalog import intervention, intervention_names, outcome, policy
from .intervention import Baseline, SpecIntervention
from .policy import NaivePolicy, ServiceLevelPolicy


def test_names_resolve_to_the_built_ins():
    assert intervention_names()[0] == "baseline" and "promo_spike" in intervention_names()
    assert intervention("baseline") == Baseline()
    assert isinstance(intervention("promo_spike"), SpecIntervention)
    assert policy("naive", lead_time_days=3) == NaivePolicy(lead_time_days=3)
    assert policy("service-level", service_level=0.99).name == "service-level-99"
    assert isinstance(policy("service-level"), ServiceLevelPolicy)
    assert outcome("simulated_cost").name == "simulated_cost"


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: intervention("nope"), "unknown intervention 'nope'"),
        (lambda: policy("nope"), "unknown policy kind 'nope'"),
        (lambda: outcome("nope"), "unknown outcome 'nope'"),
    ],
)
def test_unknown_names_list_the_choices(call, message):
    with pytest.raises(KeyError, match=message):
        call()
