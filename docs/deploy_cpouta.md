# Daily swing shadow on cPouta

This deployment runs the S1 Breakout 20D, S2 Breakout 55D, and S3 Trend 6M
rules once daily. Each has independent MNQ, MGC, and MBT trade state. It sends
plain text notifications through the configured Telegram bot; it does not place
orders. The optional `msd-live.service` runs the frozen TikTok A/B Nasdaq
signals through Capital.com and sends Telegram alerts; it does not place orders.

## Prepare the VM

Use an Ubuntu 24.04 VM (standard.small or standard.medium) and log in as the
`ubuntu` user. Clone the repository wherever you want, then enter its root:

```sh
git clone <repository-url> market-signal-desk
cd market-signal-desk
```

Copy the existing laptop `.env` into this repository using your secure file
transfer method. The setup script requires it and never creates or replaces it.
Copy the shadow state from the laptop before the first run so prior Telegram
event IDs and audit history continue on the VM:

```sh
mkdir -p data/shadow
scp -r <laptop-repo>/data/shadow/. ubuntu@<vm-address>:<repo-path>/data/shadow/
```

The directory contains `telegram_sent.csv`, `swing_v1.csv`, and any compatible
strategy audit companion. Keep this state when moving or rebuilding the VM.

## Install and start

From the repository root, run:

```sh
./scripts/setup_cpouta.sh
```

The script installs `uv` in the user's home if needed, syncs Python dependencies,
builds the Rust extension only if it is unavailable, and downloads the 400-day
minute-bar replay window plus 220 days of daily-indicator warm-up for Dukascopy
USATECHIDXUSD and XAUUSD plus Binance BTCUSDT. Downloads resume into the normal
`data/bars` monthly Parquet layout; Binance is fetched and saved one month at a
time. It then installs and enables the
`msd-swing.timer` systemd timer at 07:00 Europe/Helsinki and sends one Telegram
connection test. The timer uses `Persistent=true`, so systemd catches up a run
after downtime.

The setup script needs `sudo` for the systemd unit files. It uses the current
repository path and current non-root user in the service definition.

## Add the live TikTok A/B service

The repository's `live.toml` enables only USATECHIDXUSD with the frozen A and B
strategies. On the existing VM, install and start the separate service without
rerunning the swing bootstrap:

```sh
./scripts/install_live_service.sh
```

The Capital epic is cached in the ignored file `data/live/epics.json`; runtime
resolution never edits tracked `live.toml`. To verify Capital login, epic
resolution, and a short recent-bar request without sending a Telegram message:

```sh
uv run --env-file .env python -m msd.live.engine --check
```

## Check, stop, and update

View the next timer activation and service result:

```sh
systemctl list-timers msd-swing.timer
systemctl status msd-swing.service
journalctl -u msd-swing.service
tail -n 100 data/logs/swing_shadow.log
systemctl status msd-live.service
journalctl -u msd-live.service
tail -n 100 data/logs/live.log
```

Stop and disable the daily timer:

```sh
sudo systemctl disable --now msd-swing.timer
sudo systemctl disable --now msd-live.service
```

Update the code and reinstall/reload the timer configuration:

```sh
git pull
./scripts/setup_cpouta.sh
```

The setup is idempotent. It preserves `.env`, local bars, and shadow history.
