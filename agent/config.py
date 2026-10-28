import os
from dataclasses import dataclass

SUPPORTED_PROVIDERS = ("gemini",)
DEFAULT_CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_MODEL = "gemini-2.5-flash"


def _timeout_env(name: str, default: int = 30) -> int:
    try:
        return max(5, min(180, int(os.environ.get(name, str(default)) or str(default))))
    except (TypeError, ValueError):
        return default


def normalize_chat_url(_value: str | None) -> str:
    return DEFAULT_CHAT_URL


def normalize_provider(_value: str | None) -> str:
    return "gemini"


@dataclass
class Settings:
    provider: str = "gemini"
    chat_url: str = DEFAULT_CHAT_URL
    chat_key: str = ""
    chat_model: str = DEFAULT_MODEL
    fast_model: str = DEFAULT_MODEL
    reasoning_model: str = DEFAULT_MODEL
    coding_model: str = DEFAULT_MODEL
    additional_model: str = DEFAULT_MODEL
    gemini_timeout: int = 30
    groq_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout: int = 30
    memory_path: str = "jarvis_memory.json"
    kg_path: str | None = None

    def __post_init__(self) -> None:
        self.provider = normalize_provider(self.provider)
        self.chat_url = DEFAULT_CHAT_URL

    @classmethod
    def from_env(cls) -> "Settings":
        default_model = os.environ.get("JARVIS_CHAT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("JARVIS_CHAT_KEY", "").strip()
        return cls(
            provider="gemini", chat_url=DEFAULT_CHAT_URL, chat_key=key,
            chat_model=default_model,
            fast_model=os.environ.get("JARVIS_FAST_MODEL", default_model).strip() or default_model,
            reasoning_model=os.environ.get("JARVIS_REASONING_MODEL", default_model).strip() or default_model,
            coding_model=os.environ.get("JARVIS_CODING_MODEL", default_model).strip() or default_model,
            additional_model=os.environ.get("JARVIS_ADDITIONAL_MODEL", default_model).strip() or default_model,
            gemini_timeout=_timeout_env("JARVIS_GEMINI_TIMEOUT", 30),
            groq_key=os.environ.get("GROQ_API_KEY", "").strip(),
            groq_model=os.environ.get("JARVIS_GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b",
            groq_timeout=_timeout_env("JARVIS_GROQ_TIMEOUT", 30),
            memory_path=os.environ.get("JARVIS_MEMORY", "jarvis_memory.json").strip() or "jarvis_memory.json",
            kg_path=os.environ.get("JARVIS_KG"),
        )
