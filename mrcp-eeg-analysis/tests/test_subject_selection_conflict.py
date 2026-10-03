import pytest
from src.main import build_parser

@pytest.mark.parametrize("args",[["--subject","SUBJECT01","--all-subjects"],["--subject","SUBJECT01","--subjects","SUBJECT02"],["--subjects","SUBJECT01","--all-subjects"]])
def test_selection_modes_conflict(args):
    with pytest.raises(SystemExit): build_parser().parse_args(["--data-dir","data",*args])
