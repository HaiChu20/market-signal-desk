"""Append-only protocol trial ledger guards."""
from __future__ import annotations

import csv
from pathlib import Path


# Match the existing append-only ledger exactly; never rewrite its header.
FIELDS = ('run_id','date','config_hash','method','parameters','data_range','period','metrics','note')
DEV_PERIODS = {'dev','development'}
TEST_PERIOD = 'test'


def read_trials(path: Path) -> list[dict[str,str]]:
    if not path.exists():return []
    with path.open(newline='') as handle:
        reader=csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f'Unexpected trial ledger schema in {path}')
        return list(reader)


def append_trial(path: Path, row: dict[str,str], *, max_configs=20) -> None:
    """Append exactly one unique DEV configuration without rewriting history."""
    missing=set(FIELDS)-set(row)
    if missing:raise ValueError(f'Missing ledger fields: {sorted(missing)}')
    if row['period'] not in DEV_PERIODS:
        raise ValueError('DEV tournament ledger accepts development rows only')
    existing=read_trials(path)
    same=[item for item in existing if item['method']==row['method'] and
          item['period'] in DEV_PERIODS]
    if any(item['config_hash']==row['config_hash'] for item in same):
        raise ValueError('Configuration is already present in the append-only ledger')
    if len({item['config_hash'] for item in same}) >= max_configs:
        raise ValueError(f"Development configuration limit reached for {row['method']}")
    path.parent.mkdir(parents=True,exist_ok=True)
    new=not path.exists()
    with path.open('a',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS)
        if new:writer.writeheader()
        writer.writerow({field:row[field] for field in FIELDS})


def validate_test_trial(path: Path, row: dict[str, str]) -> None:
    """Validate a preregistered one-shot Test row without modifying the ledger."""
    missing=set(FIELDS)-set(row)
    if missing:raise ValueError(f'Missing ledger fields: {sorted(missing)}')
    if row['period'] != TEST_PERIOD:
        raise ValueError('One-shot Test ledger requires period=test')
    existing=read_trials(path)
    if any(item['period']==TEST_PERIOD and item['method']==row['method'] and
           item['config_hash']==row['config_hash'] for item in existing):
        raise ValueError('One-shot Test configuration is already present')


def append_test_trial_once(path: Path, row: dict[str, str]) -> None:
    """Append one Test result and refuse a second row for its frozen config."""
    validate_test_trial(path,row)
    path.parent.mkdir(parents=True,exist_ok=True)
    new=not path.exists()
    with path.open('a',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS)
        if new:writer.writeheader()
        writer.writerow({field:row[field] for field in FIELDS})
