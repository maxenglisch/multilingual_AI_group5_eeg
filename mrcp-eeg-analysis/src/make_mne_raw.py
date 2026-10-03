from pathlib import Path


def save_raw_fif(raw, output_path, overwrite=True):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.save(path, overwrite=overwrite, verbose=False)
    return path


def save_pipeline_fifs(raw_original, raw_car, raw_mrcp, output_dir):
    root = Path(output_dir)
    return [
        save_raw_fif(raw_original, root / "raw_original.fif"),
        save_raw_fif(raw_car, root / "raw_car.fif"),
        save_raw_fif(raw_mrcp, root / "raw_mrcp_filtered.fif"),
    ]
