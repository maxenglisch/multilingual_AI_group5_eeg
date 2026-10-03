from src.group_analysis import execute_subjects

def test_one_failure_does_not_stop_others():
    def process(subject):
        if subject=="SUBJECT02": raise RuntimeError("bad")
        return subject
    result=execute_subjects(["SUBJECT01","SUBJECT02","SUBJECT03"],process)
    assert result["SUBJECT01"]["status"]=="success" and result["SUBJECT02"]["status"]=="failed" and result["SUBJECT03"]["status"]=="success"
