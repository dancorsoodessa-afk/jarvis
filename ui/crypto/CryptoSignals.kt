package com.dancorsoodessa.jarvis_ui.crypto

object CryptoSignals {
    fun status(symbol: String): String = "Signals: " + CryptoMarket.normalizeSymbol(symbol)
}
