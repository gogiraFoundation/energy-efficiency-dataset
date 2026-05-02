"""Backward-compatible re-export of network/dashboard SQL helpers.

Prefer importing ``dashboard.queries_network`` directly — this module exists so legacy
imports do not drift from the canonical implementation.
"""

from __future__ import annotations

from dashboard.queries_network import *  # noqa: F403
