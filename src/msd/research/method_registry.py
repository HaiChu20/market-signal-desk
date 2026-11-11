"""Protocol-v2 tournament registry derived from ``docs/methods.md``.

The documentation has 30 table rows plus three named pilots.  Two detector
modules have two frozen variants each, so 33 modules expand to the protocol's
35 tournament units.  A unit is the independently modelled and ledger-counted
object; the underlying detector module remains shared.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import re


ALL_SYMBOLS = ("USATECHIDXUSD", "USA500IDXUSD", "XAUUSD", "BTCUSDT", "ETHUSDT")
MARKET_SYMBOLS = {
    "all": ALL_SYMBOLS,
    "BTC/ETH": ("BTCUSDT", "ETHUSDT"),
    "indices": ("USATECHIDXUSD", "USA500IDXUSD"),
    "NQ": ("USATECHIDXUSD",),
}
PILOTS = {1: "sr_touch", 14: "liquidity_sweep", 39: "rsi2_mean_reversion"}
VARIANTS = {
    "bollinger": ("band_reversion", "squeeze_breakout"),
    "post_macro_event_reaction": ("follow", "fade"),
}


@dataclass(frozen=True)
class MethodSpec:
    id: int
    name: str
    module: str
    symbols: tuple[str, ...]
    status: str = "in_scope"
    variant: str | None = None

    @property
    def key(self) -> str:
        return self.name if self.variant is None else f"{self.name}:{self.variant}"


def _table_rows(text: str) -> list[tuple[int, str, str, str]]:
    rows = []
    pattern = re.compile(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|\s*([^|]+)\|")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            rows.append((int(match.group(1)), match.group(2), match.group(3).strip(),
                         match.group(4).strip()))
    return rows


def load_registry(path: Path = Path("docs/methods.md")) -> tuple[MethodSpec, ...]:
    """Parse the frozen method index and validate every referenced module."""
    text = path.read_text()
    rows = _table_rows(text)
    if len(rows) != 30:
        raise ValueError(f"Expected 30 method rows in {path}, found {len(rows)}")
    rows.extend((number, name, "pilot", "indices" if number == 39 else "all")
                for number, name in PILOTS.items())
    specs = []
    for number, name, role, market in sorted(rows):
        if market not in MARKET_SYMBOLS:
            raise ValueError(f"Unknown market scope {market!r} for {name}")
        module_name = f"msd.methods.{name}"
        module = importlib.import_module(module_name)
        if getattr(module, "NAME", name) != name:
            raise ValueError(f"Module NAME mismatch for {module_name}")
        module_symbols = tuple(getattr(module, "SYMBOLS", MARKET_SYMBOLS[market]))
        symbols = tuple(symbol for symbol in MARKET_SYMBOLS[market] if symbol in module_symbols)
        status = "inputs_pending" if "inputs pending" in role else "in_scope"
        variants = VARIANTS.get(name, (None,))
        specs.extend(MethodSpec(number, name, module_name, symbols, status, variant)
                     for variant in variants)
    keys = [spec.key for spec in specs]
    if len(specs) != 35 or len(set(keys)) != 35:
        raise ValueError(f"Protocol reconciliation failed: {len(specs)} units, {len(set(keys))} keys")
    return tuple(specs)


def reconciliation(registry: tuple[MethodSpec, ...]) -> dict[str, int]:
    return {
        "documented_table_rows": 30,
        "pilot_modules": 3,
        "detector_modules": len({spec.module for spec in registry}),
        "multi_variant_expansion": len(registry) - len({spec.module for spec in registry}),
        "tournament_units": len(registry),
        "inputs_pending": sum(spec.status != "in_scope" for spec in registry),
    }
