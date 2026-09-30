from pathlib import Path
from emotivpro_mne_import import read_emotivpro_csv, validate_schema, get_sampling_rate, numeric_frame, EmotivProFormatError

root = Path(__file__).resolve().parents[1]
valid = root / "emotivpro_v2_all_streams_dummy.csv"
meta, df = read_emotivpro_csv(valid)
print("valid columns", len(df.columns), "rows", len(df))
print("sampling", get_sampling_rate(meta))
print("warnings", validate_schema(df, expected_sensors=["AF3", "Fz"]))

for p in sorted((root / "error_cases").glob("*.csv")):
    try:
        meta, df = read_emotivpro_csv(p)
        _ = get_sampling_rate(meta)
        _ = validate_schema(df, expected_sensors=["AF3", "Fz"])
        # strict numeric check for motion only
        mot_cols = [c for c in df.columns if c.startswith("MOT.")]
        if mot_cols:
            numeric_frame(df, mot_cols, strict=True)
        print("ERROR_CASE parsed", p.name, "(should be reviewed manually if intentional warning-case)")
    except Exception as exc:
        print("ERROR_CASE failed as expected", p.name, type(exc).__name__, str(exc)[:160])
