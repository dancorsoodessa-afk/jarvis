"""Safe defaults for the Crypto Analyst module."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CryptoConfig:
    """Runtime configuration. Live exchange order execution is intentionally absent."""

    exchange: str = "okx"
    market_types: tuple[str, ...] = ("spot", "swap")
    paper_trading: bool = True
    allow_live_orders: bool = False
    max_symbols: int = 500
    orderbook_depth: int = 20
    max_data_age_ms: int = 1_500
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    symbols: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.exchange.lower() != "okx":
            raise ValueError("JARVIS Crypto Analyst supports OKX only.")
        if not self.paper_trading or self.allow_live_orders:
            raise ValueError("Crypto Analyst is paper-only; live orders are forbidden.")
        if self.max_symbols < 1:
            raise ValueError("max_symbols must be positive.")
        if self.orderbook_depth < 1:
            raise ValueError("orderbook_depth must be positive.")
        if self.max_data_age_ms < 1:
            raise ValueError("max_data_age_ms must be positive.")
