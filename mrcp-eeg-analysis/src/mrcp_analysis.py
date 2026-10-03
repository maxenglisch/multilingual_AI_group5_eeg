import numpy as np

def make_epochs(raw,events,cfg,channels=None):
    import mne
    lock=cfg["mrcp"]["lock"]; spec=cfg["mrcp"][lock]; code=int(spec["event_code"])
    picks=[c for c in (channels or cfg["mrcp"]["channels"]) if c in raw.ch_names]
    if not picks: raise ValueError("None of the configured MRCP channels exist")
    selected=events[events[:,2]==code]
    n=int(raw.n_times); sf=float(raw.info["sfreq"])
    valid=np.array([e for e in selected if e[0]+spec["tmin"]*sf>=0 and e[0]+spec["tmax"]*sf<n],dtype=int).reshape(-1,3)
    dropped=len(selected)-len(valid)
    if not len(valid): raise ValueError("No in-bounds MRCP epochs")
    epochs=mne.Epochs(raw,valid,{lock:code},spec["tmin"],spec["tmax"],baseline=tuple(spec["baseline"]),
                      picks=picks,preload=True,reject_by_annotation=True,verbose=False)
    return epochs,dropped
