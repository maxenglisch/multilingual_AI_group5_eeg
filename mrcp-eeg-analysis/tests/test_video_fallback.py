from pathlib import Path
from src.make_video import _write_video_frames

class Writer:
    def mimsave(self,path,frames,fps):
        path=Path(path)
        if path.suffix==".mp4": raise RuntimeError("no mp4")
        path.write_bytes(b"gif")

def test_mp4_failure_falls_back_to_gif(tmp_path):
    result=_write_video_frames([object()],tmp_path/"test.mp4",2,Writer())
    assert result.suffix==".gif" and result.exists()
