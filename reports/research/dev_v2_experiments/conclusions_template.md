# Plain-language conclusions template

Use this section at the top of the completed DEV report. Replace every `{{placeholder}}` from the final JSON; do not select which facts to mention based on whether they look favorable.

## What was tested

This was a development-only diagnostic using decisions and realized exits strictly before 2023-01-01. Test (2023–2024) was not read, and Final (2025+) remains locked. The one-day and three-day event outcomes were rebuilt under the corrected timestamp contract; old wide-v1 artifacts remain unchanged and are not mixed with the corrected results.

## Corrected one-day baseline

Under the corrected one-day deadline, `{{baseline_positive_count}}` of 34 rule units had positive OOF average net R and `{{baseline_t2_count}}` had both positive OOF net R and t > 2. The strongest unit was `{{baseline_best_unit}}` at `{{baseline_best_net_R}}` net R per trade, t `{{baseline_best_t}}`, and PF `{{baseline_best_pf}}`. Its selected trades ended by time exit `{{baseline_best_time_exit_pct}}` of the time.

This corrected baseline supersedes the wide-v1 Family-1 numbers for research decisions. It does not erase or rewrite the append-only wide-v1 record.

## E1 — three-day hold

Extending the maximum hold from one to three trading days `{{e1_overall_direction}}`: `{{e1_improved_count}}` units improved average OOF net R, while `{{e1_worsened_count}}` worsened. `{{e1_t2_count}}` units finished with positive OOF net R and t > 2. The largest improvement was `{{e1_best_delta_unit}}` at `{{e1_best_delta_R}}` R per trade; the largest deterioration was `{{e1_worst_delta_unit}}` at `{{e1_worst_delta_R}}` R.

For the two prior leads, Donchian changed from `{{donchian_hold1_R}}` to `{{donchian_hold3_R}}` R and funding fade changed from `{{funding_hold1_R}}` to `{{funding_hold3_R}}` R. Their time-exit shares changed by `{{donchian_time_delta}}` and `{{funding_time_delta}}`, respectively. Extra CFD financing nights and crossed crypto funding are included, so the comparison reflects the full cost of waiting longer.

Plain conclusion: `{{e1_conclusion_one_sentence}}`

## E2 — nested rule portfolio

Rule, horizon, geometry, and volatility-scaling choices were made using train folds only. On held-out folds, equal-risk sizing produced `{{equal_trades_per_day}}` trades/day, `{{equal_net_R_day}}` net R/day, Sharpe `{{equal_sharpe}}`, PF `{{equal_pf}}`, and maximum account drawdown `{{equal_mdd_pct}}`. Inverse-volatility sizing produced Sharpe `{{invvol_sharpe}}`, PF `{{invvol_pf}}`, and maximum account drawdown `{{invvol_mdd_pct}}`.

The drawdown is a fraction of account equity at a 0.5% base risk unit—not an R-unit statistic. State plainly whether the resulting concurrency is economically usable: `{{portfolio_usability_sentence}}`

Market contribution was NQ `{{nq_contribution_R}}` R, SPX `{{spx_contribution_R}}` R, XAU `{{xau_contribution_R}}` R, BTC `{{btc_contribution_R}}` R, and ETH `{{eth_contribution_R}}` R. ETH is zero if the frozen event replay contains no ETH rule events; this is not silently omitted data.

## E3 — intraday momentum

The fixed Gao–Han–Li–Zhou timing rule produced gross/net average results of `{{e3_all_gross_R}}` / `{{e3_all_net_R}}` R per trade for all nonzero signals, with hit rate `{{e3_all_hit}}` and t `{{e3_all_t}}`. Requiring absolute signal strength above the train-fold median produced gross/net `{{e3_filtered_gross_R}}` / `{{e3_filtered_net_R}}` R, hit `{{e3_filtered_hit}}`, and t `{{e3_filtered_t}}`.

The sign, 10:00 signal timestamp, 15:30 executable entry, 16:00 executable exit, and March/November New York DST conversions were hand-checked. E3 does not use wide event labels and was unaffected by the deadline-unit bug.

Plain conclusion: `{{e3_conclusion_one_sentence}}`

## Research decision

- Retain for further DEV research: `{{retained_hypotheses_or_none}}`.
- Falsified or not supported by these experiments: `{{unsupported_hypotheses}}`.
- Do not tune against the already-seen Test period. No result here unlocks Test or Final.

These are OOF DEV diagnostics, not a new protocol grade. Multiple rules were compared, so isolated t-statistics must not be presented as confirmatory evidence without the existing multiplicity controls.
