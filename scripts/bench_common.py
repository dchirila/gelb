"""Shared helpers for benchmark and validation artifact scripts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import datetime as dt
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class RunMetadata:
    machine: str
    commit_sha: str
    timestamp: str

    def as_result_fields(self) -> dict[str, str]:
        return {
            "machine": self.machine,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp,
        }


def machine_tag() -> str:
    """Hardware-class label for result files.

    The label is published with the figure data, so it never includes
    the host name.  Set ``GELB_BENCH_MACHINE`` to a curated label such
    as ``"Zen 4 AVX-512 reference"`` to match the shipped data files;
    otherwise only the OS and CPU architecture are recorded.
    """
    system = platform.system() or "unknown-system"
    arch = platform.machine() or "unknown-cpu"
    label = os.environ.get("GELB_BENCH_MACHINE", "").strip()
    if label:
        return f"{label} ({system} / {arch})"
    return f"{system} / {arch}"


def commit_sha(repo_root: Path = REPO_ROOT) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def collect_run_metadata(
        repo_root: Path = REPO_ROOT, *, machine: str | None = None
        ) -> RunMetadata:
    return RunMetadata(
        machine=machine if machine is not None else machine_tag(),
        commit_sha=commit_sha(repo_root),
        timestamp=utc_timestamp(),
    )


def load_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def write_json_artifact(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")


def display_path(path: Path, repo_root: Path = REPO_ROOT) -> Path:
    if not path.is_absolute():
        return path
    try:
        return path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return path


def mlups_result(
        samples: Sequence[float | None],
        median: float | None,
        metadata: RunMetadata,
        *,
        prefix: Mapping[str, Any] | None = None,
        suffix: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if prefix:
        result.update(prefix)
    result["mlups_samples"] = list(samples)
    result["median"] = median
    result.update(metadata.as_result_fields())
    if suffix:
        result.update(suffix)
    return result
