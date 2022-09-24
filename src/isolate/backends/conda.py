from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, List

from isolate._base import BaseEnvironment
from isolate.common import BASE_CACHE_DIR, cache_static, rmdir_on_fail
from isolate.connections import PythonIPC
from isolate.context import GLOBAL_CONTEXT, ContextType

_BASE_CONDA_DIR = BASE_CACHE_DIR / "conda"
_BASE_CONDA_DIR.mkdir(parents=True, exist_ok=True)

# Specify the path where the conda binary might reside in (or
# mamba, if it is the preferred one).
_CONDA_COMMAND = os.environ.get("CONDA_EXE", "conda")
_ISOLATE_CONDA_HOME = os.getenv("ISOLATE_CONDA_HOME")


@dataclass
class CondaEnvironment(BaseEnvironment[Path]):
    BACKEND_NAME: ClassVar[str] = "conda"

    packages: List[str]

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> CondaEnvironment:
        user_provided_packages = config.get("packages", [])
        return cls(user_provided_packages)

    @property
    def key(self) -> str:
        return hashlib.sha256(" ".join(self.packages).encode()).hexdigest()

    def create(self, *, exist_ok: bool = False) -> Path:
        path = self.context.get_cache_dir(self) / self.key
        if path.exists():
            if exist_ok:
                return path
            else:
                raise FileExistsError(f"Virtual environment already exists at '{path}'")

        with rmdir_on_fail(path):
            self.log("Creating the environment at '{}'", path, kind="info")
            conda_executable = _get_conda_executable()
            if self.packages:
                self.log(
                    "Installing packages: {}",
                    ", ".join(self.packages),
                    kind="info",
                )

            subprocess.check_call(
                [
                    conda_executable,
                    "create",
                    "--yes",
                    # The environment will be created under $BASE_CACHE_DIR/conda
                    # so that in the future we can reuse it.
                    "--prefix",
                    path,
                    *self.packages,
                ]
            )

        return path

    def destroy(self, conn_info: Path) -> None:
        shutil.rmtree(conn_info)

    def open_connection(self, conn_info: Path) -> PythonIPC:
        return PythonIPC(self, conn_info)


@cache_static
def _get_conda_executable() -> Path:
    for path in [_ISOLATE_CONDA_HOME, None]:
        conda_path = shutil.which(_CONDA_COMMAND, path=path)
        if conda_path is not None:
            return Path(conda_path)
    else:
        # TODO: we should probably show some instructions on how you
        # can install conda here.
        raise FileNotFoundError(
            "Could not find conda executable. If conda executable is not available by default, please point isolate "
            " to the path where conda binary is available 'ISOLATE_CONDA_HOME'."
        )