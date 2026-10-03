import pytest
from src.data_loader import inspect_csv
from src.event_utils import find_trigger_column

def test_empty_file_error(tmp_path):
    p=tmp_path/"empty.csv"; p.touch()
    with pytest.raises(ValueError,match="Empty"): inspect_csv(p)

def test_missing_trigger_error():
    with pytest.raises(ValueError,match="No Trigger"): find_trigger_column(["time","signal"])
