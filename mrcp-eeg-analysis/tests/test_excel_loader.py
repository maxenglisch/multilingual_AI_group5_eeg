import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.data_loader import diagnose_eeg, discover_pairs, read_table


def _eeg_frame(rows=20):
    cfg=load_config(); data={"Triggers":[771]+[0]*(rows-1),"0":range(rows),"1":[0]*rows}
    for source in cfg["eeg"]["channel_columns"]: data[source]=np.arange(rows,dtype=float)
    for source in ("34","35","36","37"): data[source]=[0]*rows
    return pd.DataFrame(data)


def test_csv_and_xlsx_eeg_pair_with_csv_emg_and_trial_01(tmp_path):
    csv_eeg=tmp_path/"SUBJECT01_Trial_01_EEG.csv"
    csv_emg=tmp_path/"SUBJECT01_Trial_01_EMG.csv"
    xlsx_eeg=tmp_path/"SUBJECT11_Trial_01_EEG.xlsx"
    xlsx_emg=tmp_path/"SUBJECT11_Trial_01_EMG.csv"
    _eeg_frame().to_csv(csv_eeg,index=False); pd.DataFrame({"Triggers":[0],"0":[1]}).to_csv(csv_emg,index=False)
    _eeg_frame().to_excel(xlsx_eeg,index=False,sheet_name="EEG"); pd.DataFrame({"Triggers":[0],"0":[1]}).to_csv(xlsx_emg,index=False)
    before={path:path.read_bytes() for path in (csv_eeg,csv_emg,xlsx_eeg,xlsx_emg)}

    pairs,_=discover_pairs(tmp_path)
    assert [(pair.subject,pair.session) for pair in pairs]==[("SUBJECT01","01"),("SUBJECT11","01")]
    assert all(pair.eeg_path and pair.emg_path for pair in pairs)
    assert pairs[1].eeg_path.suffix==".xlsx" and pairs[1].emg_path.suffix==".csv"
    assert all(path.read_bytes()==content for path,content in before.items())


def test_xlsx_has_32_explicit_channels_and_safe_cleanup(tmp_path):
    path=tmp_path/"SUBJECT11_Trial_01_EEG.xlsx"
    frame=_eeg_frame(); frame["Unnamed: 99"]=np.nan
    frame.to_excel(path,index=False,sheet_name="EEG")
    before=path.read_bytes()
    df,diag,_events,_rows,_counts,_warnings,metadata=diagnose_eeg(path,load_config())
    assert len(diag["channels"])==32
    assert diag["source_columns"]["AF3"]=="2"
    assert "Unnamed: 99" not in df.columns
    assert metadata["sheet_name"]=="EEG" and metadata["delimiter"]=="excel"
    assert path.read_bytes()==before


def test_unsupported_table_extension_is_clear(tmp_path):
    path=tmp_path/"SUBJECT01_Trial_01_EEG.json"; path.write_text("{}",encoding="utf-8")
    with pytest.raises(ValueError,match="Unsupported table format.*Supported: .csv, .xlsx, .xls"):
        read_table(path)
