"""Simulation layer: one world, many interventions, policies and outcomes.

``World`` is an immutable dataset. ``Intervention``s change it (a generator
scenario today, a causal ``do()`` later), ``Policy``s make decisions on it,
``Outcome``s measure the result, and an ``Experiment`` runs every combination
and returns tidy rows. See ``docs/refactor/structure/interfaces.md`` §1.

Every module is imported by its full path; this package re-exports nothing.
"""
