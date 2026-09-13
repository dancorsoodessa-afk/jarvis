"""Tests for dialogue memory: session persistence, trimming, RAG injection."""

import json

import pytest

from agent.core import JarvisAgent
from agent.memory import MemoryStore, SessionMemory, keywords, relevant_notes
from agent.providers.openai_chat import OpenAIChatProvider
from agent.skills import NoteStore


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.system_prompt = "BASE"
        self.last_messages = []

    def generate(self, prompt, tools=None):
        self.last_messages.append(prompt)
        return f"echo: {prompt}"


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "mem.json")


def test_session_append_and_reload(store):
    session = SessionMemory(store)
    session.append("привет", "здравствуй")
    fresh = SessionMemory(store)  # simulate restart
    history = fresh.load_history()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "привет"


def test_session_trims(store):
    session = SessionMemory(store, max_exchanges=3)
    for i in range(10):
        session.append(f"q{i}", f"a{i}")
    history = session.load_history()
    assert len(history) <= 6  # 3 exchanges * 2
    assert history[-1]["content"] == "a9"


def test_session_clear(store):
    session = SessionMemory(store)
    session.append("q", "a")
    assert "очищена" in session.clear()
    assert session.load_history() == []
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["chat_history"] == []


def test_keywords_filters_noise():
    assert "скажи" not in keywords("скажи джарвис что новое")
    ks = keywords("расскажи про погоду в Москве")
    assert "погоду" in ks and "москве" in ks


def test_relevant_notes_rag(tmp_path):
    notes = NoteStore(tmp_path / "notes.json")
    notes.add("Пользователь живёт в Москве", tags="город")
    notes.add("Любит кофе", tags="")
    block = relevant_notes(notes, ["какая погода в Москве"])
    assert "Москве" in block
    assert "кофе" not in block  # нерелевантное не попадает
    assert relevant_notes(notes, ["привет"]) == ""
    assert relevant_notes(NoteStore(tmp_path / "empty.json"), ["город"]) == ""


def test_context_hook_injects_into_provider(store, tmp_path):
    notes = NoteStore(tmp_path / "notes.json")
    notes.add("Пользователя зовут Алексей", tags="имя")
    provider = FakeProvider()
    agent = JarvisAgent(provider, memory=store)

    def hook(text):
        block = relevant_notes(notes, [text])
        if block:
            provider.system_prompt = "BASE\n\n" + block

    agent.context_hook = hook
    agent.handle("меня зовут алексей?")
    assert "Алексей" in provider.system_prompt
    assert provider.system_prompt.startswith("BASE")


def test_history_restored_into_provider(store):
    SessionMemory(store).append("старый вопрос", "старый ответ")
    provider = OpenAIChatProvider(
        history=SessionMemory(store).load_history(), model="test-model")
    assert provider.history[0] == {"role": "user", "content": "старый вопрос"}
    messages = provider._messages("новый вопрос")
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user"]
