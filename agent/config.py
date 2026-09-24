import os
from dataclasses import dataclass


SUPPORTED_PROVIDERS = ("openai-compatible", "local-vulkan")


def normalize_provider(value: str | None) -> str:
    provider = (value or "openai-compatible").strip().lower()
    provider = provider.replace("_", "-").replace(" ", "-")
    aliases = {
        "openai": "openai-compatible",
        "openai-compatible-api": "openai-compatible",
        "openai-compatible-client": "openai-compatible",
        "openai-compatible-provider": "openai-compatible",
        "dragon": "openai-compatible",
        "dragon-local": "openai-compatible",
        "dragon-ai": "openai-compatible",
        "local": "local-vulkan",
        "vulkan": "local-vulkan",
        "llama": "local-vulkan",
        "llama-cpp": "local-vulkan",
    }
    return aliases.get(provider, provider)


@dataclass
class Settings:
    """Runtime settings for free/local AI providers only."""

    provider: str = "openai-compatible"
    chat_url: str = "https://openrouter.ai/api/v1/chat/completions"
    chat_key: str = ""
    chat_model: str = "openrouter/free"
    # Current free OpenRouter variants; these can also be overridden for local models.
    deepseek_url: str = ""
    deepseek_key: str = ""
    deepseek_model: str = "deepseek/deepseek-chat:free"
    glm_url: str = ""
    glm_key: str = ""
    glm_model: str = "z-ai/glm-5.2:free"
    llama_cli: str = "llama-cli"
    model: str = "model.gguf"
    ctx: int = 2048
    threads: int = 6
    memory_path: str = "jarvis_memory.json"
    kg_path: str | None = None

    def __post_init__(self):
        self.provider = normalize_provider(self.provider)

    @property
    def use_local(self) -> bool:
        return self.provider == "local-vulkan"

    @classmethod
    def from_env(cls) -> "Settings":
        provider = normalize_provider(os.environ.get("JARVIS_PROVIDER"))
        if os.environ.get("JARVIS_LOCAL") == "1":
            provider = "local-vulkan"
        try:
            ctx = max(256, int(os.environ.get("JARVIS_CTX", "2048")))
        except ValueError:
            ctx = 2048
        try:
            threads = max(1, int(os.environ.get("JARVIS_THREADS", "6")))
        except ValueError:
            threads = 6
        return cls(
            provider=provider,
            chat_url=os.environ.get("JARVIS_CHAT_URL", "https://openrouter.ai/api/v1/chat/completions").strip() or "https://openrouter.ai/api/v1/chat/completions",
            chat_key=os.environ.get("JARVIS_CHAT_KEY", "") or os.environ.get("OPENROUTER_API_KEY", ""),
            chat_model=os.environ.get("JARVIS_CHAT_MODEL", "openrouter/free").strip() or "openrouter/free",
            deepseek_url=os.environ.get("JARVIS_DEEPSEEK_URL", "").strip(),
            deepseek_key=os.environ.get("JARVIS_DEEPSEEK_KEY", ""),
            deepseek_model=os.environ.get("JARVIS_DEEPSEEK_MODEL", "deepseek/deepseek-chat:free").strip(),
            glm_url=os.environ.get("JARVIS_GLM_URL", "").strip(),
            glm_key=os.environ.get("JARVIS_GLM_KEY", ""),
            glm_model=os.environ.get("JARVIS_GLM_MODEL", "z-ai/glm-5.2:free").strip(),
            llama_cli=os.environ.get("JARVIS_LLAMA_CLI", "llama-cli").strip(),
            model=os.environ.get("JARVIS_MODEL", "model.gguf").strip(),
            ctx=ctx,
            threads=threads,
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json"),
            kg_path=os.environ.get("JARVIS_KG"),
        )
