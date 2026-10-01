package com.dancorsoodessa.jarvis_ui.crypto

object CryptoRisk {
    fun guard(realTrading: Boolean): String =
        if (realTrading) "REAL_TRADING_REQUIRES_CONFIRMATION" else "DEMO"
}
