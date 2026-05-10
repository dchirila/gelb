from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from bench_common import (  # noqa: E402
    RunMetadata,
    commit_sha,
    display_path,
    load_json_or_empty,
    mlups_result,
    write_json_artifact,
)


def test_mlups_result_keeps_shared_result_envelope():
    metadata = RunMetadata(
        machine="test-host (TestOS / test-cpu)",
        commit_sha="abc1234",
        timestamp="2026-06-03T12:00:00+00:00",
    )

    result = mlups_result(
        [1.25, None],
        1.25,
        metadata,
        prefix={"case": "tgv_periodic"},
        suffix={"cpu_openmp": True},
    )

    assert list(result) == [
        "case",
        "mlups_samples",
        "median",
        "machine",
        "commit_sha",
        "timestamp",
        "cpu_openmp",
    ]
    assert result == {
        "case": "tgv_periodic",
        "mlups_samples": [1.25, None],
        "median": 1.25,
        "machine": "test-host (TestOS / test-cpu)",
        "commit_sha": "abc1234",
        "timestamp": "2026-06-03T12:00:00+00:00",
        "cpu_openmp": True,
    }


def test_json_artifact_round_trip_creates_parent_and_newline(tmp_path):
    out = tmp_path / "nested" / "artifact.json"
    doc = {"schema_version": 1, "results": {"case": {"median": 42.0}}}

    write_json_artifact(out, doc)

    assert out.read_text().endswith("\n")
    assert load_json_or_empty(out) == doc


def test_load_json_or_empty_tolerates_missing_or_invalid_file(tmp_path):
    missing = tmp_path / "missing.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json")

    assert load_json_or_empty(missing) == {}
    assert load_json_or_empty(invalid) == {}


def test_display_path_prefers_repo_relative_paths(tmp_path):
    repo_root = tmp_path / "repo"
    artifact = repo_root / "docs" / "artifact.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}")

    assert display_path(artifact, repo_root) == Path("docs/artifact.json")


def test_commit_sha_falls_back_outside_git_repo(tmp_path):
    assert commit_sha(tmp_path) == "unknown"
