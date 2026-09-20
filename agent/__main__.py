"""Entry points:
  python -m agent            interactive CLI
  python -m agent --ipc      JSON-lines over stdin/stdout (desktop UI)
  python -m agent --ipc-tcp [port] [host]  JSON-lines over TCP (Android/remote UI)
"""

import sys

from agent.runtime import build_agent
from agent.config import Settings
from agent.multi_agent import ThreeAgentProvider
from agent.providers.openai_chat import OpenAIChatProvider
from agent import ipc
from agent.tools import self_modify


JARVIS_SYSTEM_PROMPT = (
    "Ты — Джарвис, личный ИИ-агент пользователя. "
    "Всегда отвечай на русском языке, если пользователь явно не попросил другой язык. "
    "Ты не просто чат: если у тебя есть подходящий инструмент, самостоятельно выполняй задачу. "
    "Для изменения собственного проекта используй инструменты чтения/записи исходников и после изменения запускай тесты. "
    "Не утверждай, что действие выполнено, если инструмент его не выполнил. "
    "Перед действительно опасным действием требуй подтверждение. "
    "Работай последовательно: понять задачу → действовать инструментами → проверить результат → сообщить результат."
)

# Backward-compatible identity alias.
BUSYA_SYSTEM_PROMPT = JARVIS_SYSTEM_PROMPT


def _attach_self_improvement_tools(agent) -> None:
    agent.tools.register("read_source", self_modify.read_source,
                         description="Прочитать исходный/config файл проекта JARVIS. Путь только внутри проекта.",
                         parameters={"path": "путь относительно корня проекта"})
    agent.tools.register("write_source", self_modify.write_source,
                         description="Изменить исходный/config файл проекта JARVIS. Перед записью создаётся резервная копия.",
                         parameters={"path": "путь относительно корня проекта", "content": "полное новое содержимое файла"})
    agent.tools.register("run_tests", self_modify.run_tests,
                         description="Запустить полный набор Python-тестов проекта после изменения кода.")
    agent.tools.register("git_status", self_modify.git_status,
                         description="Показать текущую ветку и незакоммиченные изменения проекта.")
    agent.tools.register("rollback_last_change", self_modify.rollback_last_backup,
                         description="Откатить последнюю резервную копию, созданную инструментом write_source.")


def _attach_free_secondary_agents(agent, settings: Settings) -> None:
    if settings.provider != "openai-compatible":
        return
    deepseek = None
    glm = None
    if settings.deepseek_model:
        deepseek = OpenAIChatProvider(
            url=settings.deepseek_url or settings.chat_url,
            api_key=settings.deepseek_key or settings.chat_key,
            model=settings.deepseek_model,
        )
    if settings.glm_model:
        glm = OpenAIChatProvider(
            url=settings.glm_url or settings.chat_url,
            api_key=settings.glm_key or settings.chat_key,
            model=settings.glm_model,
        )
    if deepseek is not None or glm is not None:
        agent.provider = ThreeAgentProvider(agent.provider, deepseek, glm)


def _set_busya_identity(agent) -> None:
    provider = agent.provider
    target = provider.main if isinstance(provider, ThreeAgentProvider) else provider
    if hasattr(target, "system_prompt"):
        target.system_prompt = BUSYA_SYSTEM_PROMPT
    if hasattr(target, "name"):
        try:
            target.name = "Буся ИИ"
        except Exception:
            pass
    if isinstance(provider, ThreeAgentProvider):
        provider.name = "Джарвис · 3 агента"


def main():
    settings = Settings.from_env()
    agent = build_agent(settings)
    _attach_free_secondary_agents(agent, settings)
    _set_busya_identity(agent)
    _attach_self_improvement_tools(agent)
    args = sys.argv[1:]

    if "--ipc" in args:
        ipc.serve_stdio(agent)
        return

    if "--ipc-tcp" in args:
        i = args.index("--ipc-tcp")
        port = int(args[i + 1]) if i + 1 < len(args) else 8765
        host = args[i + 2] if i + 2 < len(args) else "127.0.0.1"
        ipc.serve_tcp(agent, host=host, port=port)
        return

    if "--voice" in args:
        from agent.voice_loop import VoiceLoop
        VoiceLoop(agent).run()
        return

    if "--memory-clear" in args:
        from agent.memory import SessionMemory
        from agent.memory.store import MemoryStore
        store = MemoryStore(settings.memory_path)
        print(SessionMemory(store).clear())
        return

    names = ", ".join(f"/{n}" for n in agent.tools.names())
    print(f"JARVIS готов (provider: {agent.provider.name}). "
          f"Инструменты: {names}. Выход: /exit, Ctrl+C.")
    while True:
        try:
            message = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if message.strip() in ("/exit", "/quit"):
            break
        result = agent.handle(message)
        print(result.text)


if __name__ == "__main__":
    main()
