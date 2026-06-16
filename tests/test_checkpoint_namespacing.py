import os
from swe_af.execution.dag_executor import _checkpoint_path, _save_checkpoint
from swe_af.execution.schemas import DAGState


def test_checkpoint_path_default_label(tmp_path):
    s = DAGState(artifacts_dir=str(tmp_path))
    assert _checkpoint_path(s).endswith("execution/checkpoint.json")


def test_checkpoint_path_fix_label(tmp_path):
    s = DAGState(artifacts_dir=str(tmp_path))
    assert _checkpoint_path(s, label="fix-1").endswith("execution/checkpoint-fix-1.json")


def test_save_with_label_leaves_main_untouched(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    main = DAGState(artifacts_dir=artifacts,
                    all_issues=[{"name": f"i{i}"} for i in range(9)])
    _save_checkpoint(main)                       # writes checkpoint.json
    fix = DAGState(artifacts_dir=artifacts, all_issues=[{"name": "fix-1"}])
    _save_checkpoint(fix, label="fix-1")         # writes checkpoint-fix-1.json
    assert os.path.exists(_checkpoint_path(main))
    assert os.path.exists(_checkpoint_path(fix, label="fix-1"))
    import json
    main_disk = json.loads(open(_checkpoint_path(main)).read())
    assert len(main_disk["all_issues"]) == 9     # not stomped by fix
