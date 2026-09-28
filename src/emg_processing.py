import numpy as np
from scipy.signal import butter,sosfiltfilt,sosfilt,iirnotch,filtfilt
import os,sys

def _zero_phase_sos(sos,data):
    if os.name=="nt" and sys.version_info >= (3,14):
        pad=min(len(data)-1,max(64,len(sos)*24)); padded=np.pad(data,(pad,pad),mode="reflect")
        forward=sosfilt(sos,padded); return sosfilt(sos,forward[::-1])[::-1][pad:-pad]
    return sosfiltfilt(sos,data)

def process_emg(data,sfreq,cfg):
    raw=np.asarray(data,dtype=float); signal=raw.copy()
    if cfg["emg"].get("software_filter_enabled"):
        lo,hi=cfg["emg"]["bandpass"]
        signal=_zero_phase_sos(butter(4,[lo,hi],btype="bandpass",fs=sfreq,output="sos"),signal)
        b,a=iirnotch(float(cfg["emg"]["notch"]),30,fs=sfreq); signal=filtfilt(b,a,signal)
    rect=np.abs(signal)
    sos=butter(4,float(cfg["emg"]["envelope_lowpass"]),btype="lowpass",fs=sfreq,output="sos")
    return raw,signal,rect,_zero_phase_sos(sos,rect)
