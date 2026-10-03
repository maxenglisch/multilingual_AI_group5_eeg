from src.event_utils import parse_triggers

def test_duplicate_float_string_triggers_collapse():
    events,rows=parse_triggers([None,"0","771.0",771,771,0,"7711",7711,float("nan"),0],128)
    assert events[:,2].tolist()==[771,7711]

def test_event_in_first_sample_is_retained():
    events,_=parse_triggers([771,771,0,7711],128)
    assert events[:,2].tolist()==[771,7711]
