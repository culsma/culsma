"""Discover a whole-program execution plugin before starting language execution."""

from importlib.metadata import entry_points
from .models import ProgramExecutionRequest, ProgramExecutorPort, ProgramExecutionError


class ProgramExecutionInteractor:
    def load_executor(self, name: str) -> ProgramExecutorPort:
        candidates = list(entry_points(group="culsma.program_executors", name=name))
        if not candidates:
            raise ProgramExecutionError(
                f"PROGRAM_EXECUTOR_NOT_INSTALLED: '{name}'; install a program execution provider for this driver in the CLI environment"
            )
        if len(candidates) != 1:
            raise ProgramExecutionError(f"PROGRAM_EXECUTOR_NAME_CONFLICT: '{name}'")
        try:
            factory = candidates[0].load()()
            if not callable(getattr(factory, "build", None)):
                raise ProgramExecutionError(
                    f"PROGRAM_EXECUTOR_FACTORY_INVALID: '{name}'"
                )
            executor = factory.build()
            if not callable(getattr(executor, "execute", None)):
                raise ProgramExecutionError(f"PROGRAM_EXECUTOR_INVALID: '{name}'")
        except ProgramExecutionError:
            raise
        except Exception as error:
            raise ProgramExecutionError(
                f"PROGRAM_EXECUTOR_LOAD_FAILED: '{name}': {error}"
            ) from error
        return executor

    def execute(self, request: ProgramExecutionRequest) -> dict:
        executor = self.load_executor(request.driver_name)
        result = executor.execute(request)
        if not isinstance(result, dict) or not isinstance(result.get("output"), dict):
            raise ProgramExecutionError(
                "PROGRAM_EXECUTOR_RESULT_INVALID: expected a run bundle"
            )
        return result
