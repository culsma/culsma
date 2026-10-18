import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from culsma import cli
from culsma.driver.models import ProgramExecutionRequest, ProgramExecutionError
from culsma.driver import interactors


class TestProgramExecutor:
    def request(self):
        return ProgramExecutionRequest((Path("experiment.culs"),), "device")

    def test_missing_provider_is_explicit(self, monkeypatch):
        monkeypatch.setattr(interactors, "entry_points", lambda **kwargs: [])
        with pytest.raises(ProgramExecutionError, match="NOT_INSTALLED"):
            interactors.ProgramExecutionInteractor().execute(self.request())

    def test_conflicting_provider_is_rejected(self, monkeypatch):
        monkeypatch.setattr(interactors, "entry_points", lambda **kwargs: [None, None])
        with pytest.raises(ProgramExecutionError, match="NAME_CONFLICT"):
            interactors.ProgramExecutionInteractor().execute(self.request())

    @pytest.mark.parametrize(
        "factory", [lambda: object(), lambda: SimpleNamespace(build=lambda: object())]
    )
    def test_bad_plugin_contract_is_rejected(self, monkeypatch, factory):
        monkeypatch.setattr(
            interactors,
            "entry_points",
            lambda **kwargs: [SimpleNamespace(load=lambda: factory)],
        )
        with pytest.raises(ProgramExecutionError, match="INVALID"):
            interactors.ProgramExecutionInteractor().execute(self.request())

    def test_load_failure_is_reported(self, monkeypatch):
        def unavailable():
            raise ImportError("optional provider missing")

        monkeypatch.setattr(
            interactors,
            "entry_points",
            lambda **kwargs: [SimpleNamespace(load=unavailable)],
        )
        with pytest.raises(ProgramExecutionError, match="LOAD_FAILED"):
            interactors.ProgramExecutionInteractor().execute(self.request())

    def test_backend_receives_whole_request(self, monkeypatch):
        calls = []

        class Executor:
            def execute(self, request):
                calls.append(request)
                return {"output": {"ok": True}}

        class Factory:
            def build(self):
                return Executor()

        def entries(**kwargs):
            assert kwargs == {"group": "culsma.program_executors", "name": "device"}
            return [SimpleNamespace(load=lambda: Factory)]

        monkeypatch.setattr(interactors, "entry_points", entries)
        request = self.request()
        assert interactors.ProgramExecutionInteractor().execute(request)["output"]["ok"]
        assert calls == [request]

    def test_invalid_result_is_reported(self, monkeypatch):
        factory = lambda: SimpleNamespace(
            build=lambda: SimpleNamespace(execute=lambda request: None)
        )
        monkeypatch.setattr(
            interactors,
            "entry_points",
            lambda **kwargs: [SimpleNamespace(load=lambda: factory)],
        )
        with pytest.raises(ProgramExecutionError, match="RESULT_INVALID"):
            interactors.ProgramExecutionInteractor().execute(self.request())

    def test_core_cli_submits_whole_program(self, monkeypatch, capsys):
        requests = []

        def external(self, request):
            requests.append(request)
            return {
                "output": {"ok": True, "returns": {}, "report": {"alerts": []}},
                "validate": [],
            }

        def forbidden(*args, **kwargs):
            raise AssertionError(
                "Standalone execution ran before external program submission"
            )

        monkeypatch.setattr(interactors.ProgramExecutionInteractor, "execute", external)
        monkeypatch.setattr(cli, "execute_batch_pipeline", forbidden)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "culsma",
                "run",
                "experiment.culs",
                "--driver",
                "device",
                "--driver-config",
                "deck.json",
                "--library-root",
                "library",
                "--json",
            ],
        )
        cli.main()
        assert requests[0].input_paths == (Path("experiment.culs"),)
        assert requests[0].driver_name == "device" and requests[0].config_path == Path(
            "deck.json"
        )
        assert requests[0].library_roots == (Path("library"),)
        assert '"ok": true' in capsys.readouterr().out

    def test_no_driver_keeps_standalone(self, monkeypatch, capsys):
        calls = []

        def local(**kwargs):
            calls.append(kwargs)
            return {
                "output": {"ok": True, "returns": {}, "report": {"alerts": []}},
                "validate": [],
            }

        def forbidden(*args):
            raise AssertionError("Plugin used without explicit driver selection")

        monkeypatch.setattr(cli, "execute_batch_pipeline", local)
        monkeypatch.setattr(
            interactors.ProgramExecutionInteractor, "execute", forbidden
        )
        monkeypatch.setattr(sys, "argv", ["culsma", "experiment.culs", "--json"])
        cli.main()
        assert calls[0]["input_paths"] == [Path("experiment.culs")]

    def test_driver_config_requires_selection(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            ["culsma", "run", "experiment.culs", "--driver-config", "deck.json"],
        )
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 2

    def test_architecture_is_vendor_neutral(self):
        root = Path(cli.__file__).parent
        for rel in ("cli.py", "driver/models.py", "driver/interactors.py"):
            tree = ast.parse((root / rel).read_text())
            imports = [
                n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
            ]
            imports += [
                a.name
                for n in ast.walk(tree)
                if isinstance(n, ast.Import)
                for a in n.names
            ]
            assert not any(
                name.startswith(
                    ("culsma_os", "culsma_opentrons", "culsma_driver_hamilton")
                )
                for name in imports
            )
        for rel in ("driver/models.py", "driver/interactors.py"):
            tree = ast.parse((root / rel).read_text())
            assert not any(isinstance(n, ast.FunctionDef) for n in tree.body)
