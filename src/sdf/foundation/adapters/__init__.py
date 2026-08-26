"""Adapters that map external open datasets into canonical entities.

An adapter is the concrete implementation of the Foundation Layer's promise that
real and synthetic data are interchangeable: it reads a foreign schema and emits
the same dataclasses the synthetic generator does, tagged with
``origin="external-open-dataset"`` in the registry.
"""

from sdf.foundation.adapters.retail_csv import (
    load_online_retail_csv,
    register_online_retail,
)

__all__ = ["load_online_retail_csv", "register_online_retail"]
