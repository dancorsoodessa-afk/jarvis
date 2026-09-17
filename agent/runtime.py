"""Single assembly point for the JARVIS application core."""
from pathlib import Path
from .config import Settings
from .core import JarvisAgent
from .logging_setup import get as get_log
from .memory import MemoryStore, SessionMemory, relevant_notes
from .providers.local_vulkan import LocalVulkanProvider
from .providers.openai_chat import OpenAIChatProvider
from .tooling import build_tools
from .state import StateMachine


def build_agent(settings: Settings | None = None) -> JarvisAgent:
    settings = settings or Settings.from_env()
    get_log("runtime").info("Старт агента (provider=%s)", settings.provider)
    memory = MemoryStore(settings.memory_path)
    session = None
    if settings.provider == "local-vulkan":
        provider = LocalVulkanProvider(settings.llama_cli, settings.model, ctx=settings.ctx, threads=settings.threads)
    elif settings.provider == "openai-compatible":
        session = SessionMemory(memory)
        provider = OpenAIChatProvider(url=settings.chat_url.strip(), api_key=settings.chat_key,
                                      model=settings.chat_model, history=session.load_history())
    else:
        raise RuntimeError(f"Неизвестный провайдер: {settings.provider}. Доступны: openai-compatible, local-vulkan")

    tools, reminders, notes = build_tools(settings)
    agent = JarvisAgent(provider, tools=tools, memory=memory, reminders=reminders, state=StateMachine())
    if session is not None:
        def _sync_memory(user: str, assistant: str):
            session.append(user, assistant)
            data = memory.load(); data["chat_history"] = provider.history; memory.save(data)
        agent.on_exchange = _sync_memory
        agent.session = session
        base_prompt = provider.system_prompt
        def _rag_hook(text: str):
            block = relevant_notes(notes, session.last_user_text(2) + [text])
            provider.system_prompt = (base_prompt + "\n\n" + block) if block else base_prompt
        agent.context_hook = _rag_hook
    return agent
