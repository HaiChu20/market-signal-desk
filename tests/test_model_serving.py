import hashlib
import json
import pickle

import pandas as pd
import pytest

from msd.live.model_serving import load_artifact, order_from_event


class DummyModel:
    def predict_proba(self, rows):
        assert rows.dtype.name == 'float32'
        return [[0.2, 0.8]]


def artifact_dir(tmp_path):
    model = pickle.dumps(DummyModel())
    (tmp_path / 'model.pkl').write_bytes(model)
    (tmp_path / 'calibration.json').write_text(json.dumps({'raw': [0, 0.5, 1], 'calibrated': [0, 0.4, 1]}))
    manifest = {'artifact_version': 1, 'protocol_version': 2,
                'config_hash': 'a' * 64, 'training_range': {'start': '2021-01-01', 'end': '2021-12-31'},
                'features': [{'name': 'signal', 'dtype': 'float32'}],
                'model_sha256': hashlib.sha256(model).hexdigest()}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    return tmp_path


def test_model_loader_and_order(tmp_path):
    model = load_artifact(artifact_dir(tmp_path), expected_config_hash='a' * 64)
    ts = pd.Timestamp('2024-01-01', tz='UTC')
    event = {'ts': ts, 'known_at': ts + pd.Timedelta(minutes=1), 'side_candidates': [1, -1],
             'price': 100., 'natural_sl': None, 'natural_tp': None, 'method': 'sr_touch'}
    features = pd.Series({'signal': 1., '1m_atr14': 2.})
    order = order_from_event(model, features, event, pd.DataFrame(), side=1,
                             candidate_kind='atr:1:2', risk_budget=20.)
    assert order['stop'] == 98. and order['tp'] == 104.
    assert order['confidence'] == pytest.approx(0.76)
    assert order['size'] == 10.
    assert order['entry_type'] == 'market'
    limit_order = order_from_event(model, features, event, pd.DataFrame(), side=1,
                                   candidate_kind='atr:1:2', risk_budget=20.,
                                   entry_type='limit', limit_price=99.,
                                   expiry_ts=ts + pd.Timedelta(minutes=10))
    assert limit_order['entry_price'] == 99.
    assert limit_order['size'] == 20.
    assert limit_order['expiry_ts'] == ts + pd.Timedelta(minutes=10)
    assert order_from_event(model, features, event, pd.DataFrame(), side=1,
                            candidate_kind='atr:1:2', min_probability=0.9) is None


def test_loader_rejects_config_and_checksum(tmp_path):
    root = artifact_dir(tmp_path)
    with pytest.raises(ValueError, match='config hash'):
        load_artifact(root, expected_config_hash='b' * 64)
    (root / 'model.pkl').write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        load_artifact(root)


def test_missing_rust_warning_once_and_strict_mode(monkeypatch, caplog):
    from msd.processing import labels
    monkeypatch.setattr(labels, '_RUST_FALLBACK_WARNED', False)
    monkeypatch.delenv('MSD_REQUIRE_RUST', raising=False)
    labels.rust_fallback(ImportError('missing test kernel'))
    labels.rust_fallback(ImportError('missing test kernel'))
    assert caplog.text.count('Rust kernels unavailable') == 1
    monkeypatch.setenv('MSD_REQUIRE_RUST', '1')
    with pytest.raises(RuntimeError, match='MSD_REQUIRE_RUST=1'):
        labels.rust_fallback(ImportError('missing test kernel'))
