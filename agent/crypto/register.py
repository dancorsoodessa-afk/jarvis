"""Register cryptocurrency skills in the JARVIS agent tool registry."""
from . import trader_skills as crypto

def register_crypto_tools(registry) -> None:
    """Expose the eleven crypto workflows to the assistant."""
    registry.register("crypto_copycat", crypto.trader_copycat, description="Отслеживать публичный BTC-адрес и его баланс; не определяет владельца.", parameters={"address":"публичный BTC-адрес"})
    registry.register("crypto_news", crypto.trader_news, description="Получить криптоновости CoinDesk RSS с фильтром по тикерам.", parameters={"symbols":"тикеры через запятую, необязательно"})
    registry.register("crypto_budget", crypto.trader_budget, description="Рассчитать резерв и максимальный размер позиции.", parameters={"budget":"общий бюджет","cash_buffer_pct":"резерв в процентах, по умолчанию 10","max_position_pct":"лимит позиции в процентах, по умолчанию 25"})
    registry.register("crypto_whale_watch", crypto.trader_whale_watch, description="Проверить публичный BTC-адрес (баланс и число транзакций).", parameters={"address":"публичный BTC-адрес"})
    registry.register("crypto_analyst", crypto.trader_analyst, description="Получить текущую цену, 24-часовое изменение, максимум, минимум и объём пары OKX.", parameters={"symbol":"пара OKX, например BTC-USDT"})
    registry.register("crypto_screener", crypto.trader_screener, description="Отобрать спотовые USDT-пары OKX по движению цены и объёму.", parameters={"limit":"число результатов от 1 до 100","min_volume":"минимальный объём в котируемой валюте"})
    registry.register("crypto_risk", crypto.trader_risk, description="Рассчитать размер позиции по балансу, цене входа, стопу и риску; плечо не используется.", parameters={"balance":"баланс","entry":"цена входа","stop":"цена Stop Loss","risk_pct":"риск в процентах, максимум 5"})
    registry.register("crypto_paper_order", crypto.trader_broker, description="Создать только виртуальную заявку Paper Trading; реальные ордера не поддерживаются.", parameters={"symbol":"пара","side":"BUY или SELL","quantity":"количество","price":"цена","store_dir":"папка хранения, необязательно"})
    registry.register("crypto_tax_fifo", crypto.trader_tax, description="Рассчитать себестоимость и реализованный PnL методом FIFO.", parameters={"lots_json":"JSON-массив лотов с quantity и buy_price","sell_quantity":"количество продажи","sell_price":"цена продажи"})
    registry.register("crypto_price_alert", crypto.trader_alerts, description="Проверить текущую цену на достижение заданных порогов.", parameters={"symbol":"пара","current_price":"текущая цена","above":"верхний порог, необязательно","below":"нижний порог, необязательно"})
    registry.register("crypto_rebalance", crypto.trader_rebalance, description="Рассчитать покупки/продажи для достижения целевых долей портфеля; не размещает ордера.", parameters={"holdings_json":"JSON позиций: asset, target_pct, current_value","total_value":"общая стоимость портфеля"})
