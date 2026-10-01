package com.dancorsoodessa.jarvis_ui.crypto

data class CryptoConfig(
    val coinGlassBaseUrl: String = "https://open-api-v4.coinglass.com",
    val okxBaseUrl: String = "https://www.okx.com",
    val okxDemo: Boolean = true
)
