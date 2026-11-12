"""Preliminary DEV summary of replayed method-event outcomes."""
from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd

from .any_minute import SYMBOLS
from .dataset import DEV_END


def registry_names():
    import msd.methods as package
    result=[]
    for path in Path(package.__file__).parent.glob('*.py'):
        if path.name.startswith('_') or path.stem in {'common','filters'}:continue
        module=importlib.import_module(f'msd.methods.{path.stem}')
        if hasattr(module,'NAME'):result.append(module.NAME)
    return sorted(set(result))


def summarize(root, names=None, symbols=SYMBOLS):
    names=registry_names() if names is None else names
    groups={name:[] for name in names};files={name:[] for name in names}
    for sym in symbols:
        event_dir=Path(root)/'events'/sym
        for path in sorted(event_dir.glob('*.parquet')):
            if path.stem[:4]>'2022':continue
            cols=['method','sym','ts','side','known_at','exit_ts','R']
            frame=pd.read_parquet(path,columns=cols)
            frame=frame[(pd.to_datetime(frame.known_at,utc=True)<DEV_END)&
                        (pd.to_datetime(frame.exit_ts,utc=True)<DEV_END)]
            for name,part in frame.groupby('method'):
                if name in groups:
                    groups[name].append(part);files[name].append(str(path))
    missing=[name for name in names if not files[name]]
    if missing:raise FileNotFoundError(
        'Missing production DEV event/label output for registered methods: '+', '.join(missing))
    rows=[]
    for name in names:
        frame=pd.concat(groups[name],ignore_index=True)
        rows.append({'method':name,'events':len(frame[['sym','ts','side']].drop_duplicates()),
                     'candidate_rows':len(frame),
                     'net_avg_R':float(pd.to_numeric(frame.R,errors='coerce').mean()),
                     'files':len(files[name])})
    return rows


def main(root=Path('data')):
    out=Path('reports/research/tournament_dev.md');out.parent.mkdir(parents=True,exist_ok=True)
    try:
        rows=summarize(root)
    except FileNotFoundError as error:
        out.write_text('# PRELIMINARY DEV tournament\n\nProduction method event outputs are incomplete. '
            'The tournament table is withheld until every registered method has an output file.\n\n'
            f'{error}\n')
        raise
    lines=['# PRELIMINARY DEV tournament','',
           'Production `data/events/{symbol}/{month}.parquet` carries method event outcomes (labels). '
           'Only decisions and exits before 2023 are included. Inputs may be regenerated.','',
           '| Method | Events | Candidate rows | Net avg R | Source files |',
           '|---|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['method']} | {row['events']} | {row['candidate_rows']} | "
                     f"{row['net_avg_R']:.4f} | {row['files']} |")
    lines+=['','Any-minute grid is reported separately in '
            '`any_minute_grid_BTCUSDT_dev.md` pending the other two symbols.']
    out.write_text('\n'.join(lines)+'\n')
    return out


if __name__=='__main__':main()
