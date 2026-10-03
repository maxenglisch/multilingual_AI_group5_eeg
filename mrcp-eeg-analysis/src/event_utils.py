import numpy as np
import pandas as pd

DEFAULT_CODES = {768:"trial_start",771:"preparation_start",7711:"movement_start",
                 7712:"movement_end",1000:"trial_end",32766:"session_boundary"}

def find_trigger_column(columns):
    hits = [c for c in columns if any(k in str(c).lower() for k in ("trigger","marker","event"))]
    if not hits:
        raise ValueError("No Trigger/Marker/Event column found")
    if len(hits) > 1:
        raise ValueError(f"Ambiguous trigger columns: {hits}")
    return hits[0]

def parse_triggers(values, sfreq, codes=None):
    codes = codes or DEFAULT_CODES
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").round().astype("Int64")
    valid = numeric.isin(codes)
    onset = (valid & numeric.ne(numeric.shift(1, fill_value=-1))).fillna(False)
    samples = np.flatnonzero(onset.to_numpy(dtype=bool))
    rows = [{"sample":int(i), "time_seconds":float(i/sfreq),
             "trigger_code":int(numeric.iloc[i]), "event_name":codes[int(numeric.iloc[i])]}
            for i in samples]
    events = np.array([[r["sample"],0,r["trigger_code"]] for r in rows], dtype=int).reshape(-1,3)
    return events, rows

def validate_event_sequence(rows):
    warnings=[]; active=[]; expected=[768,771,7711,7712,1000]
    for r in rows:
        code=r["trigger_code"]
        if code==32766: continue
        if code==768: active=[768]; continue
        if not active and code==771: active=[771]
        elif active:
            active.append(code)
            target=expected if active[0]==768 else expected[1:]
            if active != target[:len(active)]:
                warnings.append(f"Unexpected event order near sample {r['sample']}: {active}"); active=[]
            elif code==1000: active=[]
    counts=pd.Series([r["trigger_code"] for r in rows]).value_counts().to_dict() if rows else {}
    for code in (771,7711,7712):
        if counts.get(code,0) != 10: warnings.append(f"Trigger {code}: expected about 10, found {counts.get(code,0)}")
    return counts,warnings
