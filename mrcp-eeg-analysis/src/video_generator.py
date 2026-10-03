from __future__ import annotations

import argparse
import gc
import json
import logging
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_config
from .data_loader import diagnose_eeg, discover_pairs, inspect_table
from .eeg_processing import make_raw, preprocess
from .emg_processing import process_emg
from .event_utils import find_trigger_column, parse_triggers
from .mrcp_analysis import make_epochs
from .video_utils import create_mrcp_animation, preferred_video, refresh_video_manifest, save_animation


VIDEO_EXTENSIONS = (".mp4", ".gif")
SUBJECT_RE = re.compile(r"^SUBJECT(?P<number>\d+)$", re.IGNORECASE)


def normalize_subject_id(subject_id: str) -> str:
    match = SUBJECT_RE.fullmatch(str(subject_id).strip())
    if not match:
        raise ValueError(f"Invalid subject ID {subject_id!r}; expected SUBJECT followed by digits")
    return f"SUBJECT{int(match['number']):02d}"


def _subject_sort_key(subject_id: str) -> int:
    return int(subject_id.removeprefix("SUBJECT"))


def discover_subjects(data_dir: str | Path) -> list[str]:
    pairs, _unmatched = discover_pairs(data_dir)
    return sorted({pair.subject for pair in pairs if pair.eeg_path}, key=_subject_sort_key)


def _subject_output_directory(output_dir: str | Path, subject_id: str) -> Path | None:
    root = Path(output_dir)
    direct = root / subject_id.lower()
    if direct.is_dir():
        return direct
    if root.is_dir():
        for candidate in root.iterdir():
            if candidate.is_dir() and candidate.name.upper() == subject_id:
                return candidate
    return None


def _processed_fif(output_dir: str | Path, subject_id: str) -> Path | None:
    subject_dir = _subject_output_directory(output_dir, subject_id)
    if subject_dir is None:
        return None
    for name in ("raw_mrcp_filtered.fif", "raw_car.fif"):
        path = subject_dir / "fif" / name
        if path.is_file() and path.stat().st_size > 0:
            return path.resolve()
    return None


def validate_subject(subject_id: str, data_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    canonical = normalize_subject_id(subject_id)
    pairs, _unmatched = discover_pairs(data_dir, canonical)
    eeg_pairs = [pair for pair in pairs if pair.eeg_path]
    processed = _processed_fif(output_dir, canonical)
    if not eeg_pairs:
        return {
            "subject_id": canonical,
            "valid": False,
            "reason": "No readable EEG source file was found",
            "input": None,
            "processed_fif": str(processed) if processed else None,
        }
    first = eeg_pairs[0]
    return {
        "subject_id": canonical,
        "valid": True,
        "reason": None,
        "input": str(processed or first.eeg_path),
        "processed_fif": str(processed) if processed else None,
        "eeg_file": str(first.eeg_path),
        "emg_file": str(first.emg_path) if first.emg_path else None,
        "recording_count": len(eeg_pairs),
        "pair": first,
    }


def _load_emg_trace(emg_path: str | Path | None, cfg: dict[str, Any], logger: logging.Logger) -> tuple[Any, Any] | None:
    import numpy as np
    import pandas as pd

    if emg_path is None:
        logger.warning("Matching EMG file is unavailable")
        return None
    path = Path(emg_path)
    if not path.is_file():
        logger.warning("Matching EMG file is unavailable: %s", path)
        return None
    frame, _metadata = inspect_table(path)
    trigger_column = find_trigger_column(frame.columns)
    signal_columns = [column for column in frame.columns if column != trigger_column]
    if len(signal_columns) != 1:
        logger.warning("Expected one EMG signal in %s; found %s", path, signal_columns)
        return None
    values = pd.to_numeric(frame[signal_columns[0]], errors="coerce")
    if values.isna().any():
        logger.warning("Non-numeric EMG samples in %s", path)
        return None

    sfreq = float(cfg["emg"]["sampling_rate"])
    trigger_names = {int(key): value for key, value in cfg["triggers"].items()}
    events, _rows = parse_triggers(frame[trigger_column], sfreq, trigger_names)
    _raw, _filtered, _rectified, envelope = process_emg(values.to_numpy(), sfreq, cfg)
    lock = cfg["mrcp"]["lock"]
    epoch_cfg = cfg["mrcp"][lock]
    event_code = int(epoch_cfg["event_code"])
    tmin, tmax = float(epoch_cfg["tmin"]), float(epoch_cfg["tmax"])
    left, right = int(round(tmin * sfreq)), int(round(tmax * sfreq))
    chunks = []
    for sample in events[events[:, 2] == event_code, 0]:
        start, stop = int(sample + left), int(sample + right)
        if start >= 0 and stop <= len(envelope) and stop > start:
            chunks.append(envelope[start:stop])
    if not chunks:
        logger.warning("No complete movement-locked EMG windows in %s", path)
        return None
    trace = np.asarray(chunks, dtype=float).mean(axis=0)
    times = np.arange(trace.size, dtype=float) / sfreq + tmin
    logger.info("Loaded movement-locked EMG: path=%s epochs=%d samples=%d", path, len(chunks), trace.size)
    return times, trace


def _load_subject_epochs(subject_id, validation, output_dir, cfg, logger):
    import mne

    eeg_path = Path(validation["eeg_file"])
    frame, diagnostics, events, _rows, _counts, warnings, _format = diagnose_eeg(eeg_path, cfg)
    processed_fif = _processed_fif(output_dir, subject_id)
    if processed_fif is not None:
        raw_mrcp = mne.io.read_raw_fif(processed_fif, preload=True, verbose="ERROR")
        input_description = str(processed_fif)
    else:
        raw, absent = make_raw(frame, diagnostics, float(cfg["eeg"]["sampling_rate"]))
        warnings.extend(f"No standard_1020 coordinate: {name}" for name in absent)
        _raw_original, _raw_car, raw_mrcp, _raw_csd = preprocess(raw, cfg)
        input_description = str(eeg_path)
    sfreq = float(raw_mrcp.info["sfreq"])
    expected_sfreq = float(cfg["eeg"]["sampling_rate"])
    if abs(sfreq - expected_sfreq) > 1e-9:
        raise ValueError(f"EEG sampling rate {sfreq} does not match configured {expected_sfreq} Hz")

    # Keep every surviving EEG channel for the spatial topomap.
    epochs, dropped = make_epochs(raw_mrcp, events, cfg, channels=list(raw_mrcp.ch_names))
    warnings.append(f"Out-of-bounds epochs dropped: {dropped}")
    try:
        emg_trace = _load_emg_trace(validation.get("emg_file"), cfg, logger)
    except Exception as exc:
        emg_trace = None
        warnings.append(f"EMG unavailable: {exc}")
        logger.exception("%s: optional EMG loading failed; continuing with EEG", subject_id)

    expected_channels = [str(name) for name in cfg["eeg"].get("channel_names", [])]
    mrcp_channels = [str(name) for name in cfg["mrcp"].get("channels", [])]
    if not mrcp_channels:
        raise ValueError("config/dataset.yaml does not define mrcp.channels")
    logger.info(
        "INPUT_DIAGNOSTIC %s",
        json.dumps(
            {
                "subject": subject_id,
                "source_eeg_file": str(eeg_path),
                "processed_fif": str(processed_fif) if processed_fif else None,
                "input_used": input_description,
                "number_of_epochs": len(epochs),
                "eeg_channel_count": len(epochs.ch_names),
                "channel_names": list(epochs.ch_names),
                "configured_mrcp_channels": mrcp_channels,
                "sampling_rate_hz": sfreq,
            },
            ensure_ascii=False,
        ),
    )
    return epochs, emg_trace, expected_channels, mrcp_channels, input_description, warnings


def _new_run_logger(output_dir: str | Path) -> tuple[logging.Logger, Path]:
    logs = Path(output_dir) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"video_generation_{datetime.now():%Y%m%d_%H%M%S_%f}.log"
    logger = logging.getLogger(f"mrcp.video.{path.stem}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger, path


def _close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def generate_subject_video(subject_id, data_dir, output_dir, config=None, *, video_format="auto", fps=10, dpi=100, force=False, logger=None, update_manifest=True):
    canonical = normalize_subject_id(subject_id)
    requested_format = video_format.lower()
    if requested_format not in {"auto", "gif", "mp4"}:
        raise ValueError("Video format must be auto, gif, or mp4")
    if fps <= 0 or dpi <= 0:
        raise ValueError("FPS and DPI must be positive")
    own_logger = logger is None
    if logger is None:
        logger, _log_path = _new_run_logger(output_dir)
    video_dir = Path(output_dir) / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    animation = fig = epochs = emg_trace = None
    try:
        existing = preferred_video(video_dir, canonical)
        if existing is not None and not force:
            result = {"subject_id": canonical, "status": "skipped", "input": None,
                      "path": str(existing.resolve()), "output": str(existing.resolve()),
                      "format": existing.suffix.lstrip("."), "frames": None, "fps": fps,
                      "duration_seconds": None, "elapsed_seconds": 0.0, "error": None}
            logger.info("SUBJECT_RESULT %s", json.dumps(result, ensure_ascii=False))
            if update_manifest:
                refresh_video_manifest(video_dir)
            return result

        validation = validate_subject(canonical, data_dir, output_dir)
        if not validation["valid"]:
            raise FileNotFoundError(f"{canonical}: {validation['reason']}")
        cfg = load_config(config)
        epochs, emg_trace, expected_channels, mrcp_channels, input_description, input_warnings = _load_subject_epochs(
            canonical, validation, output_dir, cfg, logger
        )
        animation, fig, frame_count, duration, animation_warnings = create_mrcp_animation(
            epochs, subject_id=canonical, fps=fps, mrcp_channels=mrcp_channels,
            expected_channels=expected_channels, emg_trace=emg_trace, logger=logger)
        output_path, actual_format, fallback_reason = save_animation(
            animation, video_dir, canonical, requested_format=requested_format, fps=fps, dpi=dpi, logger=logger)
        if force:
            for suffix in VIDEO_EXTENSIONS:
                alternate = video_dir / f"{canonical}{suffix}"
                if alternate != output_path:
                    alternate.unlink(missing_ok=True)
        if update_manifest:
            refresh_video_manifest(video_dir)
        result = {
            "subject_id": canonical, "status": "generated", "input": input_description,
            "path": str(output_path.resolve()), "output": str(output_path.resolve()), "format": actual_format,
            "frames": frame_count, "fps": fps, "duration_seconds": round(duration, 6),
            "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
            "size_bytes": output_path.stat().st_size, "fallback_reason": fallback_reason,
            "warnings": input_warnings + animation_warnings, "error": None,
        }
        logger.info("SUBJECT_RESULT %s", json.dumps(result, ensure_ascii=False))
        return result
    except Exception as exc:
        failure = {"subject_id": canonical, "status": "failed", "output": None, "format": requested_format,
                   "frames": 0, "fps": fps, "duration_seconds": None,
                   "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
                   "error": str(exc), "traceback": traceback.format_exc()}
        logger.exception("SUBJECT_RESULT %s", json.dumps(failure, ensure_ascii=False))
        raise
    finally:
        if fig is not None:
            try:
                import matplotlib.pyplot as plt
                plt.close(fig)
            except Exception:
                pass
        animation = fig = epochs = emg_trace = None
        gc.collect()
        if own_logger:
            _close_logger(logger)


def generate_all_videos(data_dir, output_dir, config=None, *, video_format="auto", fps=10, dpi=100, force=False):
    logger, log_path = _new_run_logger(output_dir)
    results = []
    try:
        subjects = discover_subjects(data_dir)
        for index, subject_id in enumerate(subjects, start=1):
            print(f"[{index}/{len(subjects)}] {subject_id}", flush=True)
            try:
                result = generate_subject_video(subject_id, data_dir, output_dir, config,
                    video_format=video_format, fps=fps, dpi=dpi, force=force, logger=logger,
                    update_manifest=False)
            except Exception as exc:
                result = {"subject_id": subject_id, "status": "failed", "output": None, "error": str(exc)}
            results.append(result)
            print(f"  {result['status']}: {result.get('output') or result.get('error')}", flush=True)
            gc.collect()
        manifest, _payload = refresh_video_manifest(Path(output_dir) / "videos")
        generated = sum(item["status"] == "generated" for item in results)
        skipped = sum(item["status"] == "skipped" for item in results)
        failed = [item["subject_id"] for item in results if item["status"] == "failed"]
        summary = {"total": len(results), "generated": generated, "skipped": skipped, "failed": len(failed),
                   "failed_subjects": failed, "results": results, "manifest": str(manifest.resolve()),
                   "log": str(log_path.resolve())}
        logger.info("BATCH_RESULT %s", json.dumps({key: value for key, value in summary.items() if key != "results"}))
        return summary
    finally:
        _close_logger(logger)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--subject", help="Generate one subject, for example SUBJECT01")
    selection.add_argument("--all", action="store_true", help="Generate every discovered subject sequentially")
    selection.add_argument("--list", action="store_true", help="List processable subjects without generating")
    parser.add_argument("--data-dir", required=True, help="Movement-related SUBJECTS directory")
    parser.add_argument("--output-dir", default="outputs", help="Project output root; videos are saved under outputs/videos")
    parser.add_argument("--config", help="Override config/dataset.yaml")
    parser.add_argument("--format", choices=("auto", "gif", "mp4"), dest="video_format", default="auto")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--dpi", type=int, default=100)
    parser.add_argument("--force", action="store_true", help="Atomically replace an existing subject video")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        subjects = discover_subjects(args.data_dir)
        for subject_id in subjects:
            validation = validate_subject(subject_id, args.data_dir, args.output_dir)
            print(f"{subject_id}\t{validation['input']}")
        print(f"Processable subjects: {len(subjects)}")
        return 0
    if args.all:
        summary = generate_all_videos(args.data_dir, args.output_dir, args.config,
            video_format=args.video_format, fps=args.fps, dpi=args.dpi, force=args.force)
        print(f"Videos: {summary['generated']} generated, {summary['skipped']} skipped, {summary['failed']} failed")
        print(f"Manifest: {summary['manifest']}")
        return 1 if summary["failed"] else 0
    try:
        result = generate_subject_video(args.subject, args.data_dir, args.output_dir, args.config,
            video_format=args.video_format, fps=args.fps, dpi=args.dpi, force=args.force)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    if result["status"] == "skipped":
        print(f"SKIP {result['subject_id']}: {result['output']}")
    else:
        print(f"Saved:\n{result['output']}")
        print(f"Frames: {result['frames']}  FPS: {result['fps']}  Size: {result['size_bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
