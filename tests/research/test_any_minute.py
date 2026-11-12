import pandas as pd
from msd.research.any_minute import _gate_open_signals_streaming

def test_early_exit_releases_signal_before_deadline():
    rows=pd.DataFrame({'known_at':pd.to_datetime(['2022-01-01T00:00Z','2022-01-01T00:10Z']),
        'label_end_ts':pd.to_datetime(['2022-01-01T00:05Z','2022-01-01T00:20Z']),
        'deadline_ts':pd.to_datetime(['2022-01-06T00:00Z']*2),'event_key':['a','b']})
    assert len(_gate_open_signals_streaming(rows))==2

def test_candidate_inside_exit_bar_is_blocked():
    rows=pd.DataFrame({'known_at':pd.to_datetime(['2022-01-01T00:00Z','2022-01-01T00:05Z']),
        'label_end_ts':pd.to_datetime(['2022-01-01T00:05Z','2022-01-01T00:20Z']),
        'deadline_ts':pd.to_datetime(['2022-01-06T00:00Z']*2),'event_key':['a','b']})
    # exit_ts is the exit bar start; its close/known time is 00:06.
    assert len(_gate_open_signals_streaming(rows))==1


def test_streaming_gate_uses_event_key_tie_break_and_resets_index():
    known=pd.Timestamp('2022-01-01T00:00Z')
    rows=pd.DataFrame({'known_at':[known,known],
        'label_end_ts':[known+pd.Timedelta(minutes=5)]*2,
        'event_key':['b','a']},index=[8,9])
    chosen=_gate_open_signals_streaming(rows)
    assert chosen.event_key.tolist()==['a']
    assert chosen.index.tolist()==[0]
