# Crypto random-direction benchmark consistency

BTCUSDT and ETHUSDT now share one benchmark bar path: `load_executable_1m`
applies the pipeline's annual Dukascopy-calibrated executable spread to Binance
spot mid-price bars. Both use 0.06% financing per UTC night and the crypto
calendar (seven days per week). This is the same cost convention used by the
label kernel.

## BTC DEV sample

The comparison used the 16 gated signals from the January–February 2021 CPU
sequence smoke. The previous path reconstructed a constant spread from the
median of `spread_R * planned_risk`; the new path called the production loader.

| Measure | Previous | Production loader | Change |
|---|---:|---:|---:|
| Spread | 91.8 USD | 91.8 USD | 0.0 USD |
| Mean opposite-direction net R | -1.9506348883 | -1.9506348883 | 0.0 R |
| Trades whose R changed | 0 / 16 | — | 0 |
| Maximum absolute R change | — | — | 0.0 R |

The sample is deliberately small and is a consistency check, not evidence for
or against a trading edge. The result is unchanged because the old median
reconstruction happened to equal the 2021 annual BTC spread. The production
loader removes that accidental dependency on candidate-table cost columns.
