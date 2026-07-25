"""Tests for train.py's CLI argument parsing (deterministic configuration)."""

from pathlib import Path

from train import build_arg_parser

REQUIRED_ARGS = [
    "--train-manifest", "x",
    "--val-manifest", "y",
    "--class-map", "z",
    "--model-scope", "w",
    "--output-dir", "o",
]


def test_default_baseline_hyperparameters():
    args = build_arg_parser().parse_args(REQUIRED_ARGS)
    assert args.seed == 42
    assert args.epochs == 15
    assert args.batch_size == 16
    assert args.learning_rate == 3e-4
    assert args.weight_decay == 1e-4
    assert args.early_stopping_patience == 4
    assert args.num_workers == 0
    assert args.device == "auto"
    assert args.pretrained is True
    assert args.resume_checkpoint is None
    assert args.max_batches_per_epoch is None


def test_parsing_is_deterministic_across_repeated_calls():
    args1 = build_arg_parser().parse_args(REQUIRED_ARGS)
    args2 = build_arg_parser().parse_args(REQUIRED_ARGS)
    assert vars(args1) == vars(args2)


def test_paths_are_parsed_as_path_objects():
    args = build_arg_parser().parse_args(REQUIRED_ARGS)
    assert isinstance(args.train_manifest, Path)
    assert isinstance(args.output_dir, Path)


def test_no_pretrained_flag_disables_pretrained():
    args = build_arg_parser().parse_args(REQUIRED_ARGS + ["--no-pretrained"])
    assert args.pretrained is False


def test_no_test_manifest_argument_exists():
    """train.py must never expose a way to point at the frozen test manifest."""
    parser = build_arg_parser()
    option_strings = {a for action in parser._actions for a in action.option_strings}
    assert "--test-manifest" not in option_strings
