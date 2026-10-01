package com.dancorsoodessa.jarvis_ui.crypto

object CryptoTrading {
    const val DEMO = "demo"
    const val REAL = "real"
    fun requiresConfirmation(mode: String): Boolean = mode.equals(REAL, ignoreCase = true)
}
