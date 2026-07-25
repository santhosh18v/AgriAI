"""Tests for training/evaluate.py's test-manifest refusal."""

import pytest

from _shared import write_manifest
from evaluate import EvaluationRefused, evaluate


def test_evaluate_refuses_test_manifest(tiny_env, tmp_path):
    manifest_path = tiny_env["root"] / "test.csv"
    write_manifest(manifest_path, tiny_env["rows"])

    fake_checkpoint = tmp_path / "does_not_need_to_exist.pt"
    with pytest.raises(EvaluationRefused, match="refuses test.csv"):
        evaluate(
            fake_checkpoint, manifest_path, tiny_env["class_map_path"],
            tiny_env["model_scope_path"], "cpu", 4, 0,
        )


def test_evaluate_has_no_test_opt_in_flag_in_cli():
    """The CLI parser must not expose any way to pass allow_test=True."""
    from evaluate import build_arg_parser

    parser = build_arg_parser()
    option_strings = {a for action in parser._actions for a in action.option_strings}
    assert not any("test" in opt.lower() for opt in option_strings)
