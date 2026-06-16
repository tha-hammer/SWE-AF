from swe_af.prompts.fix_generator import fix_generator_task_prompt


def test_prompt_includes_history_section():
    prompt = fix_generator_task_prompt(
        failed_criteria=[{"criterion": "X"}],
        dag_state_summary={},
        prd={},
        previously_failed_criteria=[{"criterion": "X"}],
    )
    assert "Previously Failed" in prompt
    assert "X" in prompt


def test_prompt_omits_history_when_empty():
    prompt = fix_generator_task_prompt(
        failed_criteria=[{"criterion": "X"}], dag_state_summary={}, prd={})
    assert "Previously Failed" not in prompt
