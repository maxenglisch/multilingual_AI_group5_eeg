from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np

def _font(size=16):
    try:return ImageFont.truetype("arial.ttf",size)
    except Exception:return ImageFont.load_default()

def _chart(draw,box,x,series,title,ylabel="",vline=0,colors=None):
    x=np.asarray(x,float); values=np.concatenate([np.asarray(y,float)[np.isfinite(y)] for y in series if np.isfinite(y).any()])
    ymin,ymax=(float(values.min()),float(values.max())) if len(values) else (-1,1)
    if ymax==ymin:ymax=ymin+1
    l,t,r,b=box; draw.rectangle(box,outline="#9aa5b1"); draw.text((l+8,t+5),title,fill="#17202a",font=_font(15)); draw.text((l+4,b-20),ylabel,fill="#52606d",font=_font(11))
    def pt(xx,yy):return (l+45+(xx-x[0])/(x[-1]-x[0])*(r-l-55),b-30-(yy-ymin)/(ymax-ymin)*(b-t-60))
    palette=colors or ["#2563eb","#dc2626","#059669","#7c3aed","#d97706"]
    for index,y in enumerate(series):
        points=[pt(xx,yy) for xx,yy in zip(x,y) if np.isfinite(yy)]
        if len(points)>1:draw.line(points,fill=palette[index%len(palette)],width=2)
    if x[0]<=vline<=x[-1]:
        vx=pt(vline,ymin)[0]; draw.line((vx,t+25,vx,b-30),fill="black",width=2)

def _save_charts(path,charts,width=1400,height_per=360):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True); image=Image.new("RGB",(width,height_per*len(charts)),"white");draw=ImageDraw.Draw(image)
    for i,(x,series,title,ylabel) in enumerate(charts):_chart(draw,(20,i*height_per+10,width-20,(i+1)*height_per-10),x,series,title,ylabel)
    image.save(path)

def save_montage(raw,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True); image=Image.new("RGB",(900,900),"white");draw=ImageDraw.Draw(image);draw.ellipse((100,80,800,780),outline="black",width=4);draw.polygon([(420,80),(450,25),(480,80)],outline="black")
    coords=[raw.info["chs"][i]["loc"][:2] for i in range(len(raw.ch_names))]; scale=max(max(abs(float(v)) for p in coords for v in p),.01)
    for name,(x,y) in zip(raw.ch_names,coords):
        px=450+float(x)/scale*300;py=430-float(y)/scale*300;draw.ellipse((px-9,py-9,px+9,py+9),fill="#d97706",outline="black");draw.text((px+10,py-8),name,fill="black",font=_font(12))
    draw.text((250,820),"Standard 10-20 electrode montage",fill="black",font=_font(22));image.save(path)

def save_raw(raw,path,seconds=10):
    n=min(raw.n_times,int(seconds*raw.info["sfreq"]));t=np.arange(n)/raw.info["sfreq"];data=raw.get_data()[:9,:n]*1e6
    _save_charts(path,[(t,[y],f"Raw EEG - {name}","Amplitude (uV)") for name,y in zip(raw.ch_names[:9],data)],height_per=220)

def save_mrcp(epochs,nine_path,grand_path):
    times=epochs.times;data=epochs.get_data(copy=False)*1e6;mean=data.mean(0)
    _save_charts(nine_path,[(times,[y],f"MRCP - {name}","Amplitude (uV)") for name,y in zip(epochs.ch_names,mean)],height_per=220)
    _save_charts(grand_path,[(times,[mean.mean(0)],"MRCP grand average across core channels","Amplitude (uV)")])

def _event_epochs(signal,samples,sfreq,tmin=-2.0,tmax=3.0):
    left=int(round(tmin*sfreq));right=int(round(tmax*sfreq));chunks=[]
    for sample in samples:
        if sample+left>=0 and sample+right<len(signal):chunks.append(signal[sample+left:sample+right])
    return np.asarray(chunks),np.arange(right-left)/sfreq+tmin

def save_emg_and_alignment(emg_envelope,emg_events,emg_sfreq,eeg_epochs,emg_path,alignment_path):
    chunks,times=_event_epochs(emg_envelope,emg_events[emg_events[:,2]==7711,0],emg_sfreq,-2,2)
    if not len(chunks):raise ValueError("No in-bounds EMG movement-start epochs")
    mean=chunks.mean(0);_save_charts(emg_path,[(times,[mean],"EMG movement-locked response","Envelope (ADC units)")])
    eeg=eeg_epochs.get_data(copy=False).mean((0,1))*1e6
    _save_charts(alignment_path,[(eeg_epochs.times,[eeg],"EEG movement-locked","Amplitude (uV)"),(times,[mean],"EMG aligned by trigger time","Envelope (ADC units)")])
