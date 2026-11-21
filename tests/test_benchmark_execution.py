"""Ensure benchmark execution rejects changed inputs and invalid programs."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
SPEC = importlib.util.spec_from_file_location('benchmark_execution', ROOT / 'benchmarks/evaluate_case.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_invalid_program_not_reported_as_success(tmp_path):
    program = tmp_path / 'protocol.culs'
    program.write_text('let x = missing_material; return x;')
    result = runner.execute_case(program, tmp_path / 'results')
    assert result['accepted'] is False
    assert result['software_pass'] is False
    assert not (tmp_path / 'results/run.json').exists()
