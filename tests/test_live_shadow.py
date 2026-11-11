"""Public-feed close semantics, shadow gate and offline replay."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

from msd.live.binance import BinanceSpotFeed, parse_kline
from msd.live.shadow import QualifiedModels, ShadowLoop, format_signal
from msd.live.online_features import EXTRA_ONLINE_METHODS, VALIDATED_ONLINE_METHODS
from msd.live.telegram import TelegramClient
from msd.processing.features import build_features
from msd.processing.levels import build_levels
from msd.processing.timeframes import build_all_timeframes

ARCHIVE = Path('/Users/bfhach/Projects/market-signal-desk/data/bars/binance_spot/BTCUSDT/2021-06.parquet')


def _kline(ts, px):
    return [int(ts.timestamp() * 1000), str(px), str(px + 1), str(px - 1), str(px),
            '3', 0, '300', 4, '2', '200', '0']


def test_feed_closed_only_reconnect_and_rest_gap_backfill():
    t0 = pd.Timestamp('2025-01-01', tz='UTC')
    bars = [_kline(t0 + pd.Timedelta(minutes=i), 100+i) for i in range(5)]
    calls = []
    class Response(io.BytesIO):
        pass
    def opener(url, timeout):
        start = int(parse_qs(urlsplit(url).query)['startTime'][0])
        calls.append(start)
        end = bars[1][0] if len(calls) == 1 else bars[3][0]
        return Response(json.dumps([row for row in bars if start <= row[0] <= end]).encode())
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def recv(self, timeout):
            item = self.messages.pop(0)
            return json.dumps({'k': {'t': item[0], 'o': item[1], 'h': item[2],
                                     'l': item[3], 'c': item[4], 'v': item[5],
                                     'q': item[7], 'n': item[8], 'V': item[9],
                                     'Q': item[10], 'x': not self.messages}})
        messages = [bars[4], bars[4]]
    class Stop:
        done = False
        def is_set(self): return self.done
    stop = Stop()
    seen = []
    def on_bar(bar):
        seen.append(bar['ts'])
        if len(seen) == 4: stop.done = True
    feed = BinanceSpotFeed('BTCUSDT', opener=opener, connector=lambda *a, **k: Socket(),
                           clock=lambda: (t0 + pd.Timedelta(minutes=6)).timestamp())
    feed.stream(on_bar, last=t0, stop=stop, retry_seconds=0)
    assert seen == [t0 + pd.Timedelta(minutes=i) for i in range(1, 5)]
    assert len(calls) >= 2


def test_backfill_rounds_subminute_warmup_start():
    t0 = pd.Timestamp('2025-01-01', tz='UTC')
    requested = []
    def opener(url, timeout):
        requested.append(int(parse_qs(urlsplit(url).query)['startTime'][0]))
        return io.BytesIO(json.dumps([_kline(t0 + pd.Timedelta(minutes=1), 101)]).encode())
    feed = BinanceSpotFeed('BTCUSDT', opener=opener)
    result = feed.backfill(t0 + pd.Timedelta(seconds=17), now=t0 + pd.Timedelta(minutes=3))
    assert [row['ts'] for row in result] == [t0 + pd.Timedelta(minutes=1)]
    assert requested == [int((t0 + pd.Timedelta(minutes=1)).timestamp() * 1000)]


def test_transport_reconnect_replays_missing_closed_minute():
    t0 = pd.Timestamp('2025-01-01', tz='UTC')
    bars = [_kline(t0 + pd.Timedelta(minutes=i), 100+i) for i in range(4)]
    rest_calls = []
    def opener(url, timeout):
        start = int(parse_qs(urlsplit(url).query)['startTime'][0])
        rest_calls.append(start)
        end = bars[len(rest_calls)][0]
        return io.BytesIO(json.dumps([row for row in bars if start <= row[0] <= end]).encode())
    connections = []
    class Socket:
        def __init__(self, number): self.number = number
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def recv(self, timeout):
            if self.number == 1: raise OSError('disconnected')
            row = bars[3]
            return json.dumps({'k': {'t': row[0], 'o': row[1], 'h': row[2], 'l': row[3],
                                     'c': row[4], 'v': row[5], 'q': row[7], 'n': row[8],
                                     'V': row[9], 'Q': row[10], 'x': True}})
    def connector(*_, **__):
        connections.append(1)
        return Socket(len(connections))
    class Stop:
        done = False
        def is_set(self): return self.done
    stop = Stop()
    seen = []
    def on_bar(row):
        seen.append(row['ts'])
        if len(seen) == 3: stop.done = True
    feed = BinanceSpotFeed('BTCUSDT', opener=opener, connector=connector,
                           clock=lambda: (t0 + pd.Timedelta(minutes=5)).timestamp())
    feed.stream(on_bar, last=t0, stop=stop, retry_seconds=0)
    assert len(connections) == 2
    assert seen == [t0 + pd.Timedelta(minutes=i) for i in (1, 2, 3)]


def test_telegram_format_and_mocked_http(monkeypatch):
    order = {'side': 1, 'entry_type': 'limit', 'entry_price': 100, 'stop': 95, 'tp': 110,
             'confidence': .7, 'expiry_ts': pd.Timestamp('2025-01-01 01:00', tz='UTC')}
    event = {'price': 101, 'method': 'sr_touch'}
    text = format_signal('BTCUSDT', event, order, model_version='abcd', expected_net_R=1.0)
    assert 'BUY LIMIT 100.00' in text and 'SL 95.00' in text and 'TP 110.00' in text
    assert 'Confidence 70.0% P(TP first)' in text and 'Expected net R +1.00' in text
    requests = []
    class Response(io.BytesIO): pass
    def opener(req, timeout):
        requests.append(req)
        return Response(b'{}')
    sender = TelegramClient(token='hidden-test-token', chat_id='42', opener=opener,
                            monotonic=lambda: 1, sleep=lambda _: None)
    sender.send_message(text)
    assert len(requests) == 1 and b'chat_id=42' in requests[0].data
    assert 'hidden-test-token' not in text
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    monkeypatch.delenv('TELEGRAM_CHAT_ID', raising=False)
    assert not TelegramClient().credentials_present


def test_ungraded_report_card_cannot_load_model(tmp_path):
    directory = tmp_path / 'BTCUSDT' / 'sr_touch'
    directory.mkdir(parents=True)
    (directory / 'report_card.json').write_text(json.dumps({'grade': 'ungraded: development',
                                                            'method': 'sr_touch', 'symbol': 'BTCUSDT'}))
    (directory / 'manifest.json').write_text('{}')
    assert QualifiedModels(tmp_path).get('BTCUSDT', 'sr_touch') is None


def test_only_matching_graded_card_with_net_return_calibration_can_qualify(tmp_path, monkeypatch):
    directory = tmp_path / 'BTCUSDT' / 'sr_touch'
    directory.mkdir(parents=True)
    config_hash = 'a' * 64
    (directory / 'report_card.json').write_text(json.dumps({'grade': '✅', 'method': 'sr_touch',
                                                            'symbol': 'BTCUSDT', 'config_hash': config_hash}))
    (directory / 'manifest.json').write_text(json.dumps({'live_policy': {'side': 1,
                    'candidate_kind': 'natural', 'entry_type': 'market'}}))
    import msd.live.shadow as shadow
    artifact = SimpleNamespace(config_hash=config_hash,
                               calibration={'calibrated': [0., 1.], 'expected_net_R': [-1., 2.]})
    monkeypatch.setattr(shadow, 'load_artifact', lambda _: artifact)
    assert QualifiedModels(tmp_path).get('BTCUSDT', 'sr_touch') == (artifact, {'side': 1,
                    'candidate_kind': 'natural', 'entry_type': 'market'})
    artifact.calibration.pop('expected_net_R')
    assert QualifiedModels(tmp_path).get('BTCUSDT', 'sr_touch') is None


@pytest.mark.slow
def test_archive_feed_and_shadow_replay_equals_offline(tmp_path):
    if not ARCHIVE.exists(): pytest.skip('read-only BTC archive unavailable')
    bars = pd.read_parquet(ARCHIVE)
    bars = bars[(bars.ts >= '2021-06-01') & (bars.ts < '2021-06-04')].reset_index(drop=True)
    # The same historical REST fields must reproduce the archived raw spot bars.
    subset = bars.iloc[:12]
    rest = [_kline(row.ts, row.bid_o) for row in subset.itertuples()]
    for item, row in zip(rest, subset.itertuples()):
        item[2:5] = [str(row.bid_h), str(row.bid_l), str(row.bid_c)]
        item[5], item[7:11] = str(row.volume), [str(row.quote_volume), int(row.trades),
                                                str(row.taker_buy_base), str(row.taker_buy_quote)]
    reconstructed = pd.DataFrame([parse_kline(item) for item in rest])
    pd.testing.assert_frame_equal(reconstructed[subset.columns], subset.reset_index(drop=True),
                                  check_dtype=False, check_exact=True)
    tfs = build_all_timeframes(bars, 'BTCUSDT')
    levels = build_levels(bars, 'BTCUSDT', tfs)
    features = build_features(bars, 'BTCUSDT', tfs, levels)
    expected = [event for method in VALIDATED_ONLINE_METHODS
                if not hasattr(method, 'SYMBOLS') or 'BTCUSDT' in method.SYMBOLS
                for event in method.detect(features, levels, bars)]
    assert expected
    target = min(int(bars.ts.searchsorted(event['ts'])) for event in expected
                 if event['ts'] >= pd.Timestamp('2021-06-02 01:00', tz='UTC'))
    start, end = max(1, target-30), min(len(bars), target+31)
    shown = []
    class NoSend:
        credentials_present = True
        def send_message(self, _): raise AssertionError('ungraded candidate reached Telegram')
    loop = ShadowLoop('BTCUSDT', tmp_path/'shadow.sqlite3', history=bars.iloc[:start],
                      telegram=NoSend(), output=shown.append)
    assert 'sr_touch' in loop.online.available_methods
    assert loop.online.unavailable_methods
    for row in bars.iloc[start:end].to_dict('records'):
        loop.process(row)
    observed = [json.loads(row[0]) for row in loop.connection.execute(
        "SELECT event_json FROM candidates ORDER BY ts, method, event_json")]
    expected = [{**event, 'sym': 'BTCUSDT'} for event in expected
                if bars.ts.iloc[start] <= event['ts'] <= bars.ts.iloc[end-1]]
    def key(event):
        return (pd.Timestamp(event['ts']), event['method'], str(event.get('cluster_id')), event['price'])
    assert sorted(map(key, observed)) == sorted(map(key, expected))
    assert observed and len(shown) == len(observed)
    assert all(message.startswith('PRELIMINARY') for message in shown)
    assert {row[0] for row in loop.connection.execute('SELECT status FROM candidates')} == {'PRELIMINARY'}
    loop.close()
    restarted = ShadowLoop('BTCUSDT', tmp_path/'shadow.sqlite3', history=bars.iloc[:end])
    assert restarted.process(bars.iloc[end-1].to_dict()) == []
    assert restarted.connection.execute('SELECT count(*) FROM candidates').fetchone()[0] == len(observed)
    restarted.close()


@pytest.mark.slow
def test_checkpointed_online_method_matches_offline_nonvacuously(tmp_path):
    if not ARCHIVE.exists(): pytest.skip('read-only BTC archive unavailable')
    bars = pd.read_parquet(ARCHIVE)
    bars = bars[(bars.ts >= '2021-06-01') & (bars.ts < '2021-06-04')].reset_index(drop=True)
    tfs = build_all_timeframes(bars, 'BTCUSDT')
    levels = build_levels(bars, 'BTCUSDT', tfs)
    features = build_features(bars, 'BTCUSDT', tfs, levels)
    expected = [event for method in EXTRA_ONLINE_METHODS
                for event in method.detect(features, levels, bars)]
    assert expected
    target = min(int(bars.ts.searchsorted(event['ts'])) for event in expected)
    start, end = target-2, target+2
    loop = ShadowLoop('BTCUSDT', tmp_path/'extra.sqlite3', history=bars.iloc[:start], output=lambda _: None)
    assert all(method.NAME in loop.online.available_methods for method in EXTRA_ONLINE_METHODS)
    for bar in bars.iloc[start:end].to_dict('records'):
        loop.process(bar)
    observed = [json.loads(row[0]) for row in loop.connection.execute('SELECT event_json FROM candidates')]
    matched = [event for event in expected if bars.ts.iloc[start] <= event['ts'] <= bars.ts.iloc[end-1]]
    assert matched
    assert [(pd.Timestamp(event['ts']), event['method'], event['side'], event['price']) for event in observed] == [
        (pd.Timestamp(event['ts']), event['method'], event['side'], event['price']) for event in matched]
    loop.close()
