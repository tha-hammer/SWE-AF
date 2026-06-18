import json, os
from pathlib import Path
from swe_af.execution.dag_executor import _save_checkpoint, _checkpoint_path
from swe_af.execution.schemas import DAGState


def _seed_checkpoint(artifacts_dir: str, n_issues: int, build_id: str = "") -> str:
    state = DAGState(artifacts_dir=artifacts_dir, build_id=build_id,
                     all_issues=[{"name": f"i{i}"} for i in range(n_issues)])
    path = _checkpoint_path(state)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps(state.model_dump(), default=str))
    return path


def test_save_checkpoint_refuses_to_shrink_same_build(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    path = _seed_checkpoint(artifacts, 9, build_id="b1")
    smaller = DAGState(artifacts_dir=artifacts, build_id="b1",
                       all_issues=[{"name": "fix-1"}])
    _save_checkpoint(smaller)
    on_disk = json.loads(Path(path).read_text())
    assert len(on_disk["all_issues"]) == 9   # not stomped within the same build


def test_save_checkpoint_fail_open_cross_build(tmp_path):
    """Reused artifacts_dir: a different build_id on disk → overwrite even if smaller."""
    artifacts = str(tmp_path / ".artifacts")
    path = _seed_checkpoint(artifacts, 7, build_id="old-build")
    fresh = DAGState(artifacts_dir=artifacts, build_id="new-build",
                     all_issues=[{"name": "i0"}])
    _save_checkpoint(fresh)
    on_disk = json.loads(Path(path).read_text())
    assert len(on_disk["all_issues"]) == 1        # fresh build wins
    assert on_disk["build_id"] == "new-build"


def test_save_checkpoint_allows_equal_or_larger(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    path = _seed_checkpoint(artifacts, 2)
    bigger = DAGState(artifacts_dir=artifacts,
                      all_issues=[{"name": f"i{i}"} for i in range(5)])
    _save_checkpoint(bigger)
    assert len(json.loads(Path(path).read_text())["all_issues"]) == 5


def test_save_checkpoint_writes_when_absent(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    state = DAGState(artifacts_dir=artifacts, all_issues=[{"name": "i0"}])
    _save_checkpoint(state)
    assert os.path.exists(_checkpoint_path(state))


def test_save_checkpoint_fail_open_on_corrupt_existing(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    path = _checkpoint_path(DAGState(artifacts_dir=artifacts))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text("{ not json")
    state = DAGState(artifacts_dir=artifacts, all_issues=[{"name": "i0"}])
    _save_checkpoint(state)   # must not raise
    assert json.loads(Path(path).read_text())["all_issues"] == [{"name": "i0"}]
