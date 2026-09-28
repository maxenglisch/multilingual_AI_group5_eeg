"""Unified Movement-Related EEG/EMG MRCP command-line pipeline."""
import argparse
import logging
from pathlib import Path

import pandas as pd

from .config import load_config
from .channel_utils import TriggerOnlyEEGError
from .data_loader import diagnose_eeg, discover_pairs, inspect_csv
from .eeg_processing import make_raw, preprocess
from .emg_processing import process_emg
from .event_utils import find_trigger_column, parse_triggers
from .feature_extraction import extract_mrcp_epoch_features
from .make_mne_raw import save_pipeline_fifs
from .make_video import make_eeg_activity_video
from .mrcp_analysis import make_epochs
from .qc import save_emg_and_alignment, save_montage, save_mrcp, save_raw
from .report import write_report


def parse_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}: return True
    if text in {"false", "0", "no", "n"}: return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got {value!r}")


def subject_output_dir(output_dir, subject=None):
    root = Path(output_dir)
    return root / subject.lower() if subject else root


def setup_log(out):
    path = out / "logs" / "pipeline.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")],
        force=True,
    )


def run_single(args):
    cfg = load_config(args.config)
    out = subject_output_dir(args.output_dir, args.subject)
    for name in ("tables", "figures", "reports", "logs", "videos", "fif"):
        (out / name).mkdir(parents=True, exist_ok=True)
    setup_log(out)

    pairs, unmatched = discover_pairs(args.data_dir, args.subject)
    inventory, missing, channels, event_rows, warnings = [], [], [], [], []
    first = None
    trigger_names = {int(k): v for k, v in cfg["triggers"].items()}
    for pair in pairs:
        recording_key = f"{pair.subject}_Trial_{pair.session}"
        if not pair.eeg_path or not pair.emg_path:
            missing.append(vars(pair))
        row = {"subject": pair.subject, "session": pair.session,
               "eeg_path": str(pair.eeg_path or ""), "emg_path": str(pair.emg_path or "")}
        if pair.eeg_path:
            try:
                df, diag, events, rows, counts, warn, fmt = diagnose_eeg(pair.eeg_path, cfg)
                row.update(eeg_samples=len(df), eeg_duration=len(df) / cfg["eeg"]["sampling_rate"],
                           detected_channels=len(diag["channels"]), trigger_counts=str(counts))
                channels.append({
                    "subject": pair.subject, "session": pair.session, "file": str(pair.eeg_path),
                    "recording_key": recording_key, "status": "success",
                    "eeg_channel_count": len(diag["channels"]), "warning": "",
                    "delimiter": fmt["delimiter"], "raw_header": fmt["raw_header"],
                    "sheet_name": fmt.get("sheet_name", ""),
                    "uv_to_v_conversion": True,
                    "sampling_rate_hz": cfg["eeg"]["sampling_rate"],
                    "all_columns": "|".join(diag["original_order"]),
                    "dtypes": "|".join(f"{c}:{df[c].dtype}" for c in df),
                    "first_three_rows": df.head(3).to_json(orient="records"),
                    "detected_channels": "|".join(diag["channels"]),
                    "missing_candidates": "|".join(diag["missing_candidates"]),
                    "extra_candidates": "|".join(diag["extra_candidates"]),
                    "non_eeg_columns": "|".join(diag["non_eeg"]),
                })
                event_rows.extend({"subject": pair.subject, "session": pair.session, **item} for item in rows)
                warnings.extend(f"{pair.eeg_path}: {item}" for item in warn)
                if first is None:
                    first = (pair, df, diag, events)
            except TriggerOnlyEEGError as exc:
                message = "No EEG signal columns; trigger-only file"
                row.update(status="skipped_trigger_only", eeg_channel_count=0,
                           detected_channels=0, warning=message)
                channels.append({
                    "subject": pair.subject, "session": pair.session,
                    "recording_key": recording_key, "file": str(pair.eeg_path),
                    "all_columns": "|".join(exc.columns), "detected_channels": "",
                    "eeg_channel_count": 0, "status": "skipped_trigger_only",
                    "warning": message,
                })
                warnings.append(f"{pair.eeg_path}: {message}")
                logging.warning(
                    "Skipping trigger-only EEG: subject=%s recording_key=%s file=%s detected_columns=%s",
                    pair.subject, recording_key, pair.eeg_path, exc.columns)
            except Exception as exc:
                warnings.append(f"{pair.eeg_path}: {exc}")
                logging.exception(
                    "EEG diagnosis failed: subject=%s recording_key=%s file=%s",
                    pair.subject, recording_key, pair.eeg_path)
        if pair.emg_path:
            try:
                emg, _sep, _header = inspect_csv(pair.emg_path)
                row.update(emg_samples=len(emg), emg_duration=len(emg) / cfg["emg"]["sampling_rate"])
            except Exception as exc:
                warnings.append(f"{pair.emg_path}: {exc}")
        inventory.append(row)

    pd.DataFrame(inventory).to_csv(out / "tables" / "dataset_inventory.csv", index=False)
    pd.DataFrame(missing).to_csv(out / "tables" / "missing_pairs.csv", index=False)
    pd.DataFrame(channels).to_csv(out / "tables" / "channel_diagnostics.csv", index=False)
    events_df = pd.DataFrame(event_rows)
    events_df.to_csv(out / "tables" / "events.csv", index=False)
    summary_columns = ["subject", "session", "trigger_code", "event_name", "count"]
    if len(events_df):
        trigger_summary = (events_df.groupby(summary_columns[:-1]).size().rename("count").reset_index())
    else:
        trigger_summary = pd.DataFrame(columns=summary_columns)
    trigger_summary.to_csv(out / "tables" / "trigger_summary.csv", index=False)
    if unmatched:
        warnings.append("Unmatched CSV filenames: " + " | ".join(str(p) for p in unmatched))

    figures = []
    if not args.dry_run and first:
        pair, df, diag, events = first
        raw, absent = make_raw(df, diag, float(cfg["eeg"]["sampling_rate"]))
        warnings.extend(f"No standard_1020 coordinate: {name}" for name in absent)
        raw_original, raw_car, raw_mrcp, _raw_csd = preprocess(raw, cfg)
        save_montage(raw_original, out / "figures" / "electrode_montage.png")
        save_raw(raw_original, out / "figures" / "raw_eeg.png")
        epochs, dropped = make_epochs(raw_mrcp, events, cfg)
        subject_features = extract_mrcp_epoch_features(epochs, pair.subject, f"{pair.subject}_Trial_{pair.session}", cfg)
        subject_features.to_csv(out / "tables" / "mrcp_epoch_features.csv", index=False)
        warnings.append(f"Out-of-bounds epochs dropped: {dropped}")
        save_mrcp(epochs, out / "figures" / "mrcp_9_channels.png", out / "figures" / "mrcp_grand_average.png")
        figures = [
            ("Raw EEG waveform example", "../figures/raw_eeg.png"),
            ("Electrode montage", "../figures/electrode_montage.png"),
            ("MRCP nine-channel averages", "../figures/mrcp_9_channels.png"),
            ("MRCP grand average", "../figures/mrcp_grand_average.png"),
        ]
        if pair.emg_path:
            emg_df, _sep, _header = inspect_csv(pair.emg_path)
            trigger = find_trigger_column(emg_df.columns)
            emg_events, _ = parse_triggers(emg_df[trigger], float(cfg["emg"]["sampling_rate"]), trigger_names)
            signal_cols = [c for c in emg_df.columns if c != trigger]
            if len(signal_cols) != 1:
                warnings.append(f"{pair.emg_path}: expected one EMG signal column, found {signal_cols}")
            else:
                values = pd.to_numeric(emg_df[signal_cols[0]], errors="coerce")
                if values.isna().any():
                    warnings.append(f"{pair.emg_path}: non-numeric EMG samples")
                else:
                    _raw, _filtered, _rect, envelope = process_emg(
                        values.to_numpy(), float(cfg["emg"]["sampling_rate"]), cfg)
                    save_emg_and_alignment(
                        envelope, emg_events, float(cfg["emg"]["sampling_rate"]), epochs,
                        out / "figures" / "emg_movement_locked.png",
                        out / "figures" / "eeg_emg_alignment.png")
                    figures.extend([
                        ("EMG movement-locked response", "../figures/emg_movement_locked.png"),
                        ("EEG-EMG alignment", "../figures/eeg_emg_alignment.png"),
                    ])
        if args.save_fif:
            saved = save_pipeline_fifs(raw_original, raw_car, raw_mrcp, out / "fif")
            logging.info("Saved FIF files: %s", [str(p) for p in saved])
        if args.make_video:
            from .make_video import make_mrcp_eeg_emg_animation
            video = make_mrcp_eeg_emg_animation(
                epochs, out / "videos" / "mrcp_eeg_emg_animation.mp4", cfg,
                emg_envelope=locals().get("envelope"), emg_events=locals().get("emg_events"),
                emg_sfreq=float(cfg["sampling_rates"]["emg"]), fps=int(args.video_fps))
            logging.info("Saved video: %s", video)
    elif not args.dry_run and not first:
        warnings.append("No valid EEG recording was available for full processing")

    overview = f"{len(set(p.subject for p in pairs))} subjects; {len(pairs)} recording keys; {len(missing)} missing pairs"
    write_report(
        out / "reports" / "mrcp_report.html", overview,
        channels[0]["detected_channels"] if channels else "No valid EEG file",
        events_df.trigger_code.value_counts().to_dict() if len(events_df) else {}, warnings, figures)
    (out / "logs" / "warnings.txt").write_text("\n".join(warnings), encoding="utf-8")
    logging.info("Processed %d recording keys; warnings=%d; output=%s", len(pairs), len(warnings), out)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument("--output-dir", default="outputs")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--subject")
    selection.add_argument("--subjects", nargs="+")
    selection.add_argument("--all-subjects", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--make-video", nargs="?", const=True, type=parse_bool, default=False)
    parser.add_argument("--make-motorik-barcharts", action="store_true")
    parser.add_argument("--save-fif", type=parse_bool, default=False)
    parser.add_argument("--video-duration", type=float, default=10.0)
    parser.add_argument("--video-fps", type=int, default=10)
    parser.add_argument("--config", default=None)
    return parser


def run(args):
    if getattr(args, "make_motorik_barcharts", False):
        from .motorik_barchart import generate_motorik_barcharts
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=True)
        logging.info("Generating Motorik bar charts...")
        result = generate_motorik_barcharts(output_dir=Path(args.output_dir))
        logging.info("Motorik bar charts completed.")
        print("Motorik Bar Chart outputs:")
        for name, path in result.items():
            print(f"  {name}: {path}")
        return 0
    if not args.data_dir:
        raise ValueError("--data-dir is required unless --make-motorik-barcharts is used")
    if getattr(args, "all_subjects", False) or getattr(args, "subjects", None):
        from .group_analysis import run_group
        return run_group(args, load_config(args.config), run_single)
    return run_single(args)


def main():
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
