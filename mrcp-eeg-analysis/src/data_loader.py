from dataclasses import dataclass
from pathlib import Path
import csv, logging, re
import pandas as pd
from .channel_utils import detect_eeg_channels
from .event_utils import find_trigger_column, parse_triggers, validate_event_sequence

logger=logging.getLogger(__name__)
SUPPORTED_SUFFIXES={".csv",".xlsx",".xls"}
PATTERN=re.compile(r"(?P<subject>SUBJECT\d+)[_\-](?:(?:Session)|(?:Trial))[_\-]?(?P<session>\d+)[_\-](?P<kind>EEG|EMG)(?P<suffix>\.csv|\.xlsx|\.xls)$",re.I)

@dataclass
class RecordingPair:
    subject:str; session:str; eeg_path:Path|None=None; emg_path:Path|None=None

def discover_pairs(root, subject=None):
    pairs={}; unmatched=[]
    for path in Path(root).rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES: continue
        m=PATTERN.search(path.name)
        if not m:
            if not subject or subject.upper() in path.name.upper(): unmatched.append(path)
            continue
        s=m["subject"].upper(); session=m["session"].zfill(2)
        if subject and s != subject.upper(): continue
        key=(s,session); pairs.setdefault(key,RecordingPair(s,session)); attribute=m["kind"].lower()+"_path"
        existing=getattr(pairs[key],attribute)
        if existing and existing != path:
            raise ValueError(f"Duplicate {m['kind'].upper()} table for {s} Trial_{session}: {existing} | {path}")
        setattr(pairs[key],attribute,path)
    return sorted(pairs.values(),key=lambda x:(x.subject,x.session)),unmatched

def _clean_table(df):
    df=df.dropna(axis=0,how="all").dropna(axis=1,how="all")
    df.columns=[str(c).lstrip("\ufeff").strip() for c in df.columns]
    unnamed=[column for column in df.columns if column.lower().startswith("unnamed:")]
    return df.drop(columns=unnamed) if unnamed else df


def inspect_table(path, nrows=None):
    path=Path(path)
    if not path.exists() or path.stat().st_size==0: raise ValueError(f"Empty or missing table: {path}")
    suffix=path.suffix.lower()
    if suffix==".csv":
        line=path.open(encoding="utf-8-sig",errors="replace").readline()
        delimiter=csv.Sniffer().sniff(line,delimiters=",;\t|").delimiter
        df=pd.read_csv(path,sep=delimiter,encoding="utf-8-sig",nrows=nrows)
        metadata={"delimiter":delimiter,"raw_header":line.rstrip("\r\n"),"sheet_name":""}
    elif suffix in {".xlsx",".xls"}:
        engine="openpyxl" if suffix==".xlsx" else "xlrd"
        with pd.ExcelFile(path,engine=engine) as workbook:
            sheet=workbook.sheet_names[0]
            df=pd.read_excel(workbook,sheet_name=sheet,nrows=nrows)
        metadata={"delimiter":"excel","raw_header":"|".join(map(str,df.columns)),"sheet_name":sheet}
    else:
        raise ValueError(f"Unsupported table format {suffix!r}: {path}. Supported: .csv, .xlsx, .xls")
    return _clean_table(df),metadata


def read_table(path: Path, nrows=None) -> pd.DataFrame:
    return inspect_table(path,nrows)[0]


def inspect_csv(path, nrows=None):
    df,metadata=inspect_table(path,nrows)
    return df,metadata["delimiter"],metadata["raw_header"]

def diagnose_eeg(path, cfg, nrows=None):
    df,metadata=inspect_table(path,nrows)
    logger.info("EEG table: path=%s shape=%s sheet_name=%s columns=%s",
                Path(path).resolve(),df.shape,metadata["sheet_name"] or "CSV",list(df.columns))
    diag=detect_eeg_channels(df.columns,int(cfg["eeg"]["expected_channel_count"]),cfg["eeg"].get("column_mapping"))
    logger.info("EEG validation: path=%s detected_channels=%d excluded_metadata=%s uv_to_v=%s sampling_rate_hz=%s",
                Path(path).resolve(),len(diag["channels"]),diag["non_eeg"],
                str(cfg["eeg"].get("input_unit","uV")).lower() in {"uv","µv","μv"},cfg["eeg"]["sampling_rate"])
    trigger=find_trigger_column(df.columns)
    events,rows=parse_triggers(df[trigger],float(cfg["eeg"]["sampling_rate"]),
                               {int(k):v for k,v in cfg["triggers"].items()})
    counts,warnings=validate_event_sequence(rows)
    return df,diag,events,rows,counts,warnings,metadata
