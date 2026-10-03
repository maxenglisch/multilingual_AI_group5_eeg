import os
from pathlib import Path
from tempfile import gettempdir

_runtime = Path(gettempdir()) / "eeg_emg_mrcp_runtime"
_runtime.mkdir(parents=True, exist_ok=True)
(_runtime / "numba").mkdir(parents=True, exist_ok=True)
(_runtime / "matplotlib").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MNE_DONTWRITE_HOME", "true")
os.environ.setdefault("_MNE_FAKE_HOME_DIR", str(_runtime))
os.environ.setdefault("MPLCONFIGDIR", str(_runtime / "matplotlib"))
os.environ.setdefault("NUMBA_CACHE_DIR", str(_runtime / "numba"))
