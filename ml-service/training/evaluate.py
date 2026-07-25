"""M4 validation-only evaluation utility.

At M4 this may evaluate ONLY val.csv. It refuses test.csv unconditionally --
there is no flag in this program that enables it. M5 will add an explicit,
separate evaluation mode for the frozen test set; nothing here anticipates
or half-implements that.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from sklearn.metrics import confusion_matrix
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import ManifestImageDataset, load_active_classes, load_class_index_by_name
from model import ARCHITECTURE_NAME, build_model, select_device
from train import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    IMAGE_SIZE,
    POTATO_HEALTHY_DISCLOSURE,
    build_transforms,
    compute_metrics,
    compute_per_class_metrics,
    run_epoch,
)


class EvaluationRefused(Exception):
    pass


def load_checkpoint_and_model(checkpoint_path: Path, device: torch.device):
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if ckpt.get("architecture") != ARCHITECTURE_NAME:
        raise EvaluationRefused(
            f"checkpoint architecture {ckpt.get('architecture')!r} != expected {ARCHITECTURE_NAME!r}"
        )
    class_names = ckpt["class_names"]
    if len(class_names) != 6:
        raise EvaluationRefused(f"checkpoint has {len(class_names)} classes, expected 6")

    model = build_model(num_classes=len(class_names), pretrained=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    model.eval()
    return model, ckpt


def verify_class_map(ckpt: dict, class_map_path: Path, model_scope_path: Path) -> None:
    class_index_by_name = load_class_index_by_name(class_map_path)
    active_classes = load_active_classes(model_scope_path)
    expected_class_to_index = {name: class_index_by_name[name] for name in active_classes}
    if ckpt.get("class_to_index") != expected_class_to_index:
        raise EvaluationRefused(
            f"checkpoint class_to_index {ckpt.get('class_to_index')} does not match "
            f"current approved policy {expected_class_to_index}"
        )


def evaluate(checkpoint_path: Path, manifest_path: Path, class_map_path: Path, model_scope_path: Path, device_arg: str, batch_size: int, num_workers: int, allow_test: bool = False):
    if manifest_path.name == "test.csv" and not allow_test:
        raise EvaluationRefused(
            "evaluate.py refuses test.csv during M4. No flag in this program "
            "enables test-set evaluation -- that is explicit, separate M5 scope."
        )

    device = select_device(device_arg)
    model, ckpt = load_checkpoint_and_model(checkpoint_path, device)
    verify_class_map(ckpt, class_map_path, model_scope_path)

    class_names = ckpt["class_names"]
    _, val_transform, transform_config = build_transforms()

    # Deterministic transform sanity check against the checkpoint's recorded config.
    recorded = ckpt.get("preprocessing_config", {})
    if recorded and (
        recorded.get("image_size") != IMAGE_SIZE
        or recorded.get("normalization", {}).get("mean") != IMAGENET_MEAN
        or recorded.get("normalization", {}).get("std") != IMAGENET_STD
    ):
        raise EvaluationRefused("checkpoint preprocessing_config does not match this evaluator's transforms")

    dataset = ManifestImageDataset(
        manifest_path, class_map_path, model_scope_path, transform=val_transform, allow_test=allow_test
    )
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    criterion = torch.nn.CrossEntropyLoss()
    metrics, y_true, y_pred = run_epoch(model, loader, criterion, device, class_names, optimizer=None)
    per_class = compute_per_class_metrics(y_true, y_pred, class_names)
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))

    return {
        "manifest": str(manifest_path),
        "checkpoint": str(checkpoint_path),
        "checkpoint_epoch": ckpt.get("epoch"),
        "device": str(device),
        "num_samples": len(dataset),
        "metrics": metrics,
        "per_class_metrics": per_class,
        "confusion_matrix": {"class_order": class_names, "matrix": cm.tolist()},
        "potato_healthy_disclosure": POTATO_HEALTHY_DISCLOSURE,
        "test_set_used": manifest_path.name == "test.csv",
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M4 validation-only evaluation (test.csv is refused)")
    p.add_argument("--checkpoint", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path, help="Must be val.csv during M4")
    p.add_argument("--class-map", required=True, type=Path)
    p.add_argument("--model-scope", required=True, type=Path)
    p.add_argument("--output-json", required=True, type=Path)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--num-workers", type=int, default=0)
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    result = evaluate(
        args.checkpoint, args.manifest, args.class_map, args.model_scope,
        args.device, args.batch_size, args.num_workers, allow_test=False,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True, default=str)
    print(json.dumps({"metrics": result["metrics"], "num_samples": result["num_samples"]}, indent=2))
    return result


if __name__ == "__main__":
    main()
