import re

CANONICAL = {
    x.lower(): x for x in (
        "AF3 AFz AF4 F3 F1 Fz F2 F4 FC3 FC1 FCz FC2 FC4 C3 C1 Cz C2 C4 "
        "CP3 CP1 CPz CP2 CP4 P3 P1 Pz P2 P4 PO3 POz PO4 O1 O2"
    ).split()
}
EXCLUDED = {"tp9", "tp10", "drl", "cms"}


class TriggerOnlyEEGError(ValueError):
    """Known data-quality condition: a CSV contains metadata but no EEG signal."""

    def __init__(self, columns):
        self.columns = [str(column) for column in columns]
        super().__init__("No EEG signal columns; trigger-only file")

def normalize_column(value):
    text = str(value).lstrip("\ufeff").strip()
    text = re.sub(r"^(eeg[._\-\s]*)", "", text, flags=re.I).strip()
    return CANONICAL.get(text.lower(), text)

def detect_eeg_channels(columns, expected=32, mapping=None):
    original = [str(c) for c in columns]
    mapping = {str(k).strip(): normalize_column(v) for k, v in (mapping or {}).items()}
    detected, source = [], {}
    for raw in original:
        clean = normalize_column(raw)
        channel = mapping.get(raw.strip()) or (clean if clean.lower() in CANONICAL else None)
        if channel and channel.lower() not in EXCLUDED:
            if channel in detected:
                raise ValueError(f"Duplicate EEG channel after normalization: {channel}")
            detected.append(channel); source[channel] = raw
    non_eeg = [x for x in original if x not in source.values()]
    possible = set(CANONICAL.values())
    missing = sorted(possible - set(detected))
    extra = sorted(set(detected) - possible)
    metadata_only = all(
        normalize_column(column).lower() in {"trigger", "triggers"}
        or re.fullmatch(r"[+-]?\d+(?:\.\d+)?", normalize_column(column))
        for column in original
    )
    if not detected and metadata_only:
        raise TriggerOnlyEEGError(original)
    if len(detected) != expected:
        raise ValueError(
            f"Expected {expected} explicitly identified EEG channels, found {len(detected)}. "
            f"Detected={detected}; non-EEG={non_eeg}; no positional fallback is allowed."
        )
    return {"channels": detected, "source_columns": source, "non_eeg": non_eeg,
            "missing_candidates": missing, "extra_candidates": extra,
            "original_order": original}
