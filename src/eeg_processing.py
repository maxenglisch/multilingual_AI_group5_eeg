import numpy as np
import os, sys

def microvolts_to_volts(data):
    return np.asarray(data,dtype=float)*1e-6

def make_raw(df, diagnostic, sfreq):
    import mne
    source=[diagnostic["source_columns"][x] for x in diagnostic["channels"]]
    values=df[source].apply(lambda x: __import__('pandas').to_numeric(x,errors='coerce'))
    if values.isna().any().any(): raise ValueError("EEG contains missing/non-numeric values")
    info=mne.create_info(diagnostic["channels"],sfreq,"eeg")
    raw=mne.io.RawArray(microvolts_to_volts(values.to_numpy().T),info,verbose=False)
    standard=mne.channels.make_standard_montage("standard_1020")
    positions=standard.get_positions()["ch_pos"]
    absent=[x for x in raw.ch_names if x not in positions]
    # Explicit head-frame coordinates avoid a fragile fiducial least-squares
    # transform in the supported Windows/Python 3.14 environment.
    present={name:positions[name] for name in raw.ch_names if name in positions}
    montage=mne.channels.make_dig_montage(ch_pos=present,coord_frame="head")
    raw.set_montage(montage,on_missing="warn")
    return raw,absent

def zero_phase_bandpass(raw,lo,hi,order):
    """Zero-phase Butterworth band-pass in place; shared by the MRCP and band-power branches."""
    if os.name=="nt" and sys.version_info >= (3,14):
        from scipy.signal import butter, sosfilt
        sos=butter(order,[lo,hi],btype="bandpass",fs=float(raw.info["sfreq"]),output="sos")
        data=raw.get_data(); pad=min(data.shape[1]-1,max(64,order*24))
        padded=np.pad(data,((0,0),(pad,pad)),mode="reflect")
        forward=sosfilt(sos,padded,axis=1)
        filtered=sosfilt(sos,forward[:,::-1],axis=1)[:,::-1][:,pad:-pad]
        raw._data[:]=filtered
    else:
        raw.filter(lo,hi,method="iir",phase="zero",
            iir_params={"order":order,"ftype":"butter"},verbose=False)
    return raw

def preprocess(raw,cfg):
    raw_original=raw.copy()
    raw_car=raw.copy().set_eeg_reference("average",projection=False,verbose=False)
    lo,hi=map(float,cfg["mrcp"]["bandpass"])
    order=int(cfg["mrcp"]["butterworth_order"])
    raw_mrcp=zero_phase_bandpass(raw_car.copy(),lo,hi,order)
    raw_csd=None
    if cfg["mrcp"].get("use_csd"):
        import mne
        try: raw_csd=mne.preprocessing.compute_current_source_density(raw_mrcp.copy())
        except Exception: raw_csd=None
    return raw_original,raw_car,raw_mrcp,raw_csd

def preprocess_bandpower(raw,cfg):
    """CAR plus the band-power filter from cfg["states"]; the MRCP 0.1-1 Hz band would remove every band."""
    states=cfg["states"]
    raw_car=raw.copy().set_eeg_reference("average",projection=False,verbose=False)
    lo,hi=map(float,states["bandpass"])
    raw_bp=zero_phase_bandpass(raw_car,lo,hi,int(states.get("butterworth_order",4)))
    notch=states.get("notch_hz")
    if notch and float(notch)<raw.info["sfreq"]/2:
        from scipy.signal import iirnotch, tf2sos, sosfiltfilt
        sos=tf2sos(*iirnotch(float(notch),30,fs=float(raw.info["sfreq"])))
        raw_bp._data[:]=sosfiltfilt(sos,raw_bp.get_data(),axis=1)
    return raw_bp
