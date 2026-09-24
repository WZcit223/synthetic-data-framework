"""Synthetic Data Framework (SDF).

A three-layer industrial-AI framework prototype:

    Foundation Layer  -> canonical entities + multi-source data registry
    Synthesis Layer   -> synthetic / predictive data generation
    Application Layer  -> operation / application logic (AI warehouse demo)

This package is the *engineering framework*: it demonstrates the end-to-end flow
on a small numerical core (numpy, scipy, scikit-learn). The places where a real
algorithm or real dataset must eventually plug in are marked with
``# ALGORITHM-HOOK`` / ``# DATA-HOOK`` and catalogued in
``docs/ALGORITHM_AND_DATA_CHECKLIST.md``.
"""

__version__ = "1.6.0"
