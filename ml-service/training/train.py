"""M4 EfficientNet-B0 training program (configuration-driven CLI).

Trains only on --train-manifest, validates only on --val-manifest. There is
no --test-manifest argument anywhere in this program -- the test manifest
is never wired in, per the M4 rule that it stays frozen for M5.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from torch import nn
from torch.utils.data import DataLoader
from torchvision import transforms as T

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import ManifestImageDataset, load_active_classes, load_class_index_by_name
from model import ARCHITECTURE_NAME, build_model, pretrained_weights_id, select_device

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
IMAGE_SIZE = 224


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def set_seed(seed: int) -> dict:
    """Seed every RNG this pipeline touches. Returns a disclosure dict for
    environment.json describing what was/was not made deterministic."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    disclosure = {
        "seed": seed,
        "python_random_seeded": True,
        "numpy_seeded": True,
        "torch_manual_seed_set": True,
        "mps_manual_seed_set": False,
        "cuda_manual_seed_set": False,
        "deterministic_algorithms": "warn_only",
        "determinism_note": (
            "torch.use_deterministic_algorithms(True, warn_only=True) is enabled "
            "so unsupported/nondeterministic ops on MPS emit a warning instead of "
            "crashing the run, rather than being silently skipped. This pipeline "
            "does NOT claim bit-for-bit reproducibility across runs on MPS -- "
            "several MPS kernels (notably some in EfficientNet's depthwise/SE "
            "blocks) have no deterministic implementation in torch 2.7.1. Seeded "
            "initialization, data ordering, and augmentation ARE reproducible; "
            "exact floating-point reduction order in MPS matmul/conv kernels may "
            "still vary. CPU runs are expected to be closer to fully "
            "deterministic than MPS runs."
        ),
    }

    if torch.backends.mps.is_available():
        torch.mps.manual_seed(seed)
        disclosure["mps_manual_seed_set"] = True
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        disclosure["cuda_manual_seed_set"] = True

    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception as e:  # pragma: no cover - defensive, torch-version dependent
        disclosure["deterministic_algorithms"] = f"unavailable ({e})"

    return disclosure


def seed_worker(worker_id: int) -> None:
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

def build_transforms() -> tuple[T.Compose, T.Compose, dict]:
    """Conservative, disease-symptom-preserving augmentation for train;
    fully deterministic resize+normalize for validation. Returns
    (train_transform, val_transform, config_dict_for_metadata)."""
    train_transform = T.Compose(
        [
            T.RandomResizedCrop(IMAGE_SIZE, scale=(0.85, 1.0), ratio=(0.9, 1.1)),
            T.RandomHorizontalFlip(p=0.5),
            T.RandomRotation(degrees=15),
            T.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.1, hue=0.02),
            T.ToTensor(),
            T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    val_transform = T.Compose(
        [
            T.Resize(256),
            T.CenterCrop(IMAGE_SIZE),
            T.ToTensor(),
            T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    config = {
        "image_size": IMAGE_SIZE,
        "normalization": {"mean": IMAGENET_MEAN, "std": IMAGENET_STD},
        "train": {
            "random_resized_crop": {"size": IMAGE_SIZE, "scale": [0.85, 1.0], "ratio": [0.9, 1.1]},
            "random_horizontal_flip_p": 0.5,
            "random_vertical_flip": False,
            "random_vertical_flip_reason": (
                "Not used -- a plant leaf photographed upright has no natural "
                "vertical-flip symmetry the way it does horizontal, and vertical "
                "flip risks making disease-lesion orientation cues (e.g. gravity-"
                "influenced lesion spread patterns) look atypical."
            ),
            "random_rotation_degrees": 15,
            "color_jitter": {"brightness": 0.15, "contrast": 0.15, "saturation": 0.1, "hue": 0.02},
        },
        "val": {"resize": 256, "center_crop": IMAGE_SIZE},
        "rationale": (
            "Conservative augmentation intentionally avoids aggressive crops, "
            "large rotations, or strong color/contrast shifts that could alter "
            "or obscure disease-lesion appearance (color, shape, coverage) on "
            "the leaf, which are the actual classification signal."
        ),
    }
    return train_transform, val_transform, config


# ---------------------------------------------------------------------------
# Class weighting
# ---------------------------------------------------------------------------

def compute_class_weights(class_counts: dict[str, int], active_classes: list[str]) -> dict:
    total = sum(class_counts.values())
    num_classes = len(active_classes)
    unweighted = {name: 1.0 for name in active_classes}
    inverse_freq = {
        name: total / (num_classes * class_counts[name]) for name in active_classes
    }
    return {
        "class_counts": class_counts,
        "total_train_images": total,
        "unweighted": unweighted,
        "inverse_frequency_balanced": inverse_freq,
        "selected_strategy": "inverse_frequency_balanced",
        "selection_rationale": (
            "Potato Healthy (104 train images) is 6-13x smaller than the other "
            "5 classes (700-1331 images). Weighted cross-entropy with "
            "inverse-frequency-balanced weights (total / (num_classes * count)) "
            "is used as the single baseline strategy -- no oversampling is "
            "combined with it, to keep the first baseline's imbalance handling "
            "simple and its effect isolated/attributable."
        ),
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true, y_pred, class_names: list[str]) -> dict:
    accuracy = accuracy_score(y_true, y_pred)
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    _, _, weighted_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )
    return {
        "accuracy": float(accuracy),
        "macro_precision": float(macro_p),
        "macro_recall": float(macro_r),
        "macro_f1": float(macro_f1),
        "weighted_f1": float(weighted_f1),
    }


def compute_per_class_metrics(y_true, y_pred, class_names: list[str]) -> dict:
    labels = list(range(len(class_names)))
    p, r, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    return {
        class_names[i]: {
            "precision": float(p[i]),
            "recall": float(r[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i in labels
    }


POTATO_HEALTHY_DISCLOSURE = (
    "Potato Healthy per-class metrics have high uncertainty: the approved "
    "validation set contains only 24 Potato Healthy images drawn from just 6 "
    "independent physical-leaf groups. Image-level support (24) overstates "
    "the number of independent examples (6). Macro-F1 is sensitive to this "
    "small class, and no claim of production-level generalization is made "
    "for Potato Healthy from these numbers."
)


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------

def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ML_SERVICE_ROOT.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def build_checkpoint(
    model,
    optimizer,
    scheduler,
    epoch: int,
    best_val_macro_f1: float,
    val_loss: float,
    class_names: list[str],
    class_to_index: dict[str, int],
    transform_config: dict,
    run_config: dict,
    manifest_hashes: dict,
    seed: int,
) -> dict:
    return {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict() if scheduler is not None else None,
        "epoch": epoch,
        "best_val_macro_f1": best_val_macro_f1,
        "val_loss": val_loss,
        "class_names": class_names,
        "class_to_index": class_to_index,
        "architecture": ARCHITECTURE_NAME,
        "preprocessing_config": transform_config,
        "training_config": run_config,
        "manifest_hashes": manifest_hashes,
        "seed": seed,
        "agriai_repo_commit": _git_commit(),
        "torch_version": torch.__version__,
    }


def validate_resume_checkpoint(ckpt: dict, class_names, class_to_index, manifest_hashes, run_config) -> list[str]:
    """Returns a list of incompatibility problems (empty == compatible)."""
    problems = []
    if ckpt.get("architecture") != ARCHITECTURE_NAME:
        problems.append(
            f"architecture mismatch: checkpoint={ckpt.get('architecture')!r} vs current={ARCHITECTURE_NAME!r}"
        )
    if ckpt.get("class_names") != class_names:
        problems.append("class_names mismatch")
    if ckpt.get("class_to_index") != class_to_index:
        problems.append("class_to_index mismatch")
    if len(ckpt.get("class_names", [])) != 6:
        problems.append("checkpoint class count is not 6")
    if ckpt.get("manifest_hashes") != manifest_hashes:
        problems.append(
            f"manifest_hashes mismatch: checkpoint={ckpt.get('manifest_hashes')} vs "
            f"current={manifest_hashes}"
        )
    ckpt_preproc = ckpt.get("preprocessing_config")
    if ckpt_preproc != run_config.get("transforms"):
        problems.append("preprocessing_config mismatch")
    if ckpt.get("training_config", {}).get("seed") != run_config.get("seed"):
        problems.append(
            f"seed mismatch (disclosed, not silently ignored): "
            f"checkpoint={ckpt.get('training_config', {}).get('seed')} vs current={run_config.get('seed')}"
        )
    return problems


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Train / eval epoch loops
# ---------------------------------------------------------------------------

def run_epoch(model, loader, criterion, device, class_names, optimizer=None, max_batches=None):
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    n_samples = 0
    all_true, all_pred = [], []

    context = torch.enable_grad() if is_train else torch.no_grad()
    with context:
        for batch_idx, (images, labels) in enumerate(loader):
            if max_batches is not None and batch_idx >= max_batches:
                break
            images = images.to(device)
            labels = labels.to(device)

            if is_train:
                optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            if is_train:
                loss.backward()
                optimizer.step()

            batch_size = labels.size(0)
            total_loss += loss.item() * batch_size
            n_samples += batch_size
            preds = outputs.argmax(dim=1)
            all_true.extend(labels.detach().cpu().tolist())
            all_pred.extend(preds.detach().cpu().tolist())

    avg_loss = total_loss / n_samples if n_samples else float("nan")
    metrics = compute_metrics(all_true, all_pred, class_names) if n_samples else {}
    metrics["loss"] = avg_loss
    return metrics, all_true, all_pred


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M4 EfficientNet-B0 training baseline")
    p.add_argument("--train-manifest", required=True, type=Path)
    p.add_argument("--val-manifest", required=True, type=Path)
    p.add_argument("--class-map", required=True, type=Path)
    p.add_argument("--model-scope", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--learning-rate", type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--num-workers", type=int, default=0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--early-stopping-patience", type=int, default=4)
    p.add_argument("--pretrained", action="store_true", default=True)
    p.add_argument("--no-pretrained", dest="pretrained", action="store_false")
    p.add_argument("--resume-checkpoint", type=Path, default=None)
    p.add_argument(
        "--max-batches-per-epoch",
        type=int,
        default=None,
        help="Optional cap for smoke tests / time-boxed runs; omit for the real baseline.",
    )
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / "training.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )
    log = logging.getLogger("train")

    seed_disclosure = set_seed(args.seed)
    log.info("Seed disclosure: %s", json.dumps(seed_disclosure))

    active_classes = load_active_classes(args.model_scope)
    class_index_by_name = load_class_index_by_name(args.class_map)
    class_to_index = {name: class_index_by_name[name] for name in active_classes}
    class_names = [name for name, _ in sorted(class_to_index.items(), key=lambda kv: kv[1])]
    log.info("Active classes (%d): %s", len(class_names), class_names)

    device = select_device(args.device)
    log.info("Selected device: %s", device)

    train_transform, val_transform, transform_config = build_transforms()

    train_manifest_hash = _sha256_file(args.train_manifest)
    val_manifest_hash = _sha256_file(args.val_manifest)
    manifest_hashes = {
        "train_manifest": str(args.train_manifest),
        "train_manifest_sha256": train_manifest_hash,
        "val_manifest": str(args.val_manifest),
        "val_manifest_sha256": val_manifest_hash,
    }
    log.info("Manifest hashes: %s", manifest_hashes)

    g = torch.Generator()
    g.manual_seed(args.seed)

    train_dataset = ManifestImageDataset(
        args.train_manifest, args.class_map, args.model_scope, transform=train_transform
    )
    val_dataset = ManifestImageDataset(
        args.val_manifest, args.class_map, args.model_scope, transform=val_transform
    )
    log.info("Train dataset: %d images. Val dataset: %d images.", len(train_dataset), len(val_dataset))

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        worker_init_fn=seed_worker,
        generator=g,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    class_weights_info = compute_class_weights(train_dataset.class_counts(), active_classes)
    log.info("Class weights: %s", json.dumps(class_weights_info))
    weight_tensor = torch.tensor(
        [class_weights_info["inverse_frequency_balanced"][name] for name in class_names],
        dtype=torch.float32,
        device=device,
    )

    model = build_model(num_classes=len(class_names), pretrained=args.pretrained).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)
    criterion = nn.CrossEntropyLoss(weight=weight_tensor)

    run_config = {
        "architecture": ARCHITECTURE_NAME,
        "pretrained": args.pretrained,
        "pretrained_weights_id": pretrained_weights_id() if args.pretrained else None,
        "num_classes": len(class_names),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "num_workers": args.num_workers,
        "seed": args.seed,
        "device": str(device),
        "early_stopping_patience": args.early_stopping_patience,
        "optimizer": "AdamW",
        "scheduler": "ReduceLROnPlateau(mode=max, factor=0.5, patience=2, monitors=val_macro_f1)",
        "loss": "CrossEntropyLoss(weighted=inverse_frequency_balanced)",
        "class_weights": class_weights_info,
        "transforms": transform_config,
        "max_batches_per_epoch": args.max_batches_per_epoch,
        "model_selection_rule": (
            "primary: highest validation macro-F1; tie-breaker 1: lower "
            "validation loss; tie-breaker 2: earlier epoch"
        ),
    }

    start_epoch = 1
    best_val_macro_f1 = -1.0
    best_val_loss = float("inf")
    best_epoch = None
    epochs_since_improvement = 0
    history = []

    if args.resume_checkpoint is not None:
        if not args.resume_checkpoint.exists():
            raise FileNotFoundError(f"--resume-checkpoint not found: {args.resume_checkpoint}")
        ckpt = torch.load(args.resume_checkpoint, map_location=device, weights_only=False)
        problems = validate_resume_checkpoint(ckpt, class_names, class_to_index, manifest_hashes, run_config)
        if problems:
            raise RuntimeError(
                "Refusing to resume from an incompatible checkpoint. Problems found:\n"
                + "\n".join(f"  - {p}" for p in problems)
            )
        model.load_state_dict(ckpt["model_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        if ckpt.get("scheduler_state_dict") is not None:
            scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        start_epoch = ckpt["epoch"] + 1
        best_val_macro_f1 = ckpt["best_val_macro_f1"]
        best_val_loss = ckpt["val_loss"]
        best_epoch = ckpt["epoch"]
        log.info("Resumed from %s at epoch %d", args.resume_checkpoint, start_epoch)

    start_time = time.time()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time))

    stopped_early = False
    interrupted = False
    last_completed_epoch = start_epoch - 1

    try:
        for epoch in range(start_epoch, args.epochs + 1):
            epoch_start = time.time()

            train_metrics, _, _ = run_epoch(
                model, train_loader, criterion, device, class_names,
                optimizer=optimizer, max_batches=args.max_batches_per_epoch,
            )
            val_metrics, val_true, val_pred = run_epoch(
                model, val_loader, criterion, device, class_names,
                optimizer=None, max_batches=args.max_batches_per_epoch,
            )
            scheduler.step(val_metrics["macro_f1"])

            epoch_duration = time.time() - epoch_start
            log.info(
                "Epoch %d/%d | train loss=%.4f acc=%.4f macro_f1=%.4f | "
                "val loss=%.4f acc=%.4f macro_f1=%.4f | %.1fs",
                epoch, args.epochs,
                train_metrics["loss"], train_metrics["accuracy"], train_metrics["macro_f1"],
                val_metrics["loss"], val_metrics["accuracy"], val_metrics["macro_f1"],
                epoch_duration,
            )

            history.append(
                {
                    "epoch": epoch,
                    "train": train_metrics,
                    "val": val_metrics,
                    "epoch_duration_seconds": epoch_duration,
                    "learning_rate": optimizer.param_groups[0]["lr"],
                }
            )
            last_completed_epoch = epoch

            is_new_best = (
                val_metrics["macro_f1"] > best_val_macro_f1
                or (
                    val_metrics["macro_f1"] == best_val_macro_f1
                    and val_metrics["loss"] < best_val_loss
                )
            )
            if is_new_best:
                best_val_macro_f1 = val_metrics["macro_f1"]
                best_val_loss = val_metrics["loss"]
                best_epoch = epoch
                epochs_since_improvement = 0

                per_class_best = compute_per_class_metrics(val_true, val_pred, class_names)
                cm_best = confusion_matrix(val_true, val_pred, labels=list(range(len(class_names))))

                ckpt = build_checkpoint(
                    model, optimizer, scheduler, epoch, best_val_macro_f1, best_val_loss,
                    class_names, class_to_index, transform_config, run_config, manifest_hashes, args.seed,
                )
                torch.save(ckpt, args.output_dir / "best_model.pt")

                _write_json(args.output_dir / "validation_metrics_best.json", {**val_metrics, "epoch": epoch})
                _write_json(
                    args.output_dir / "per_class_metrics_best.json",
                    {"epoch": epoch, "per_class": per_class_best, "potato_healthy_disclosure": POTATO_HEALTHY_DISCLOSURE},
                )
                _write_json(
                    args.output_dir / "confusion_matrix_best.json",
                    {"epoch": epoch, "class_order": class_names, "matrix": cm_best.tolist()},
                )
                log.info("New best model at epoch %d (val macro_f1=%.4f)", epoch, best_val_macro_f1)
            else:
                epochs_since_improvement += 1

            last_ckpt = build_checkpoint(
                model, optimizer, scheduler, epoch, best_val_macro_f1, best_val_loss,
                class_names, class_to_index, transform_config, run_config, manifest_hashes, args.seed,
            )
            torch.save(last_ckpt, args.output_dir / "last_model.pt")

            if epochs_since_improvement >= args.early_stopping_patience:
                log.info(
                    "Early stopping triggered after %d epochs without improvement (patience=%d)",
                    epochs_since_improvement, args.early_stopping_patience,
                )
                stopped_early = True
                break
    except KeyboardInterrupt:
        log.warning("Training interrupted by user at epoch %d", last_completed_epoch)
        interrupted = True

    end_time = time.time()
    end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time))
    total_duration = end_time - start_time

    _write_json(args.output_dir / "training_history.json", {"epochs": history})
    _write_json(args.output_dir / "run_config.json", run_config)
    _write_json(args.output_dir / "manifest_hashes.json", manifest_hashes)

    environment = {
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "machine_architecture": platform.machine(),
        "torch_version": torch.__version__,
        "torchvision_version": __import__("torchvision").__version__,
        "pillow_version": __import__("PIL").__version__,
        "scikit_learn_version": __import__("sklearn").__version__,
        "device": str(device),
        "seed_disclosure": seed_disclosure,
        "manifest_hashes": manifest_hashes,
        "run_config": run_config,
        "start_time_utc": start_iso,
        "end_time_utc": end_iso,
        "total_training_duration_seconds": total_duration,
        "agriai_repo_commit": _git_commit(),
    }
    _write_json(args.output_dir / "environment.json", environment)

    if interrupted:
        status = "m4_incomplete_interrupted"
    elif last_completed_epoch < args.epochs and not stopped_early:
        status = "m4_incomplete_interrupted"
    else:
        status = "m4_baseline_complete"

    training_summary = {
        "status": status,
        "completed_epochs": last_completed_epoch,
        "requested_epochs": args.epochs,
        "stopped_early": stopped_early,
        "interrupted": interrupted,
        "best_epoch": best_epoch,
        "best_val_macro_f1": best_val_macro_f1 if best_epoch else None,
        "best_val_loss": best_val_loss if best_epoch else None,
        "total_training_duration_seconds": total_duration,
        "test_set_used": False,
        "potato_healthy_disclosure": POTATO_HEALTHY_DISCLOSURE,
    }
    _write_json(args.output_dir / "training_summary.json", training_summary)

    log.info("Training summary: %s", json.dumps(training_summary))
    return training_summary


def _write_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    main()
