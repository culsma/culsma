"""Material quantity unit constants."""

from __future__ import annotations


VOLUME_TO_UL: dict[str, float] = {
    "uL": 1.0,
    "ul": 1.0,
    "mL": 1000.0,
    "ml": 1000.0,
    "L": 1_000_000.0,
}

MASS_TO_MG: dict[str, float] = {
    "ug": 0.001,
    "mg": 1.0,
    "g": 1000.0,
    "kg": 1_000_000.0,
}

COUNT_TO_CELLS: dict[str, float] = {
    "cells": 1.0,
}
