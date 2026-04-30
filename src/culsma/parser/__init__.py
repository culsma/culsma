from __future__ import annotations


def parse(source: str):
    # Keep parser package importable even when optional parser dependencies
    # are missing in minimal test environments.
    from culsma.parser.parser import parse as _parse

    return _parse(source)
