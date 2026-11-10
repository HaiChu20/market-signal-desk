"""No-signal strategy used only to check the replay container boots."""
NAME = "smoke"
SYMBOLS = ("BTCUSDT",)
RESOLUTION = "MINUTE"


def orders(bars):
    return []
