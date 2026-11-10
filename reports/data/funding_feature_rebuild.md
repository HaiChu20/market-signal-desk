# BTC funding feature rebuild

- Funding prints loaded: 7,488 (2020-01-01 00:00:00+00:00 to 2026-10-31 16:00:00+00:00)
- Feature files rebuilt: 12 BTCUSDT 2024 monthly files
- Feature rows: 527,040; rows with as-of `funding_z20`: 502,560 (95.36%)
- Join rule: latest funding print with `funding_time <= known_at`; rolling z-score uses trailing 20 prints, including the latest available print.
