"""Regression: free-text slash commands get their words joined."""

import pytest

from agent.core import JarvisAgent
from agent.tools.registry import ToolRegistry
from agent.skills import NoteStore


class FakeProvider:
    name = "fake"

    def generate(self, prompt, tools=None):
        return prompt


def test_free_text_slash_command(tmp_path):
    notes = NoteStore(tmp_path / "notes.json")
    tools = ToolRegistry()
    tools.register("remember", notes.add,
                   description="запомнить",
                   parameters={"text": "что запомнить",
                               "tags": "теги (необязательно)"})
    agent = JarvisAgent(FakeProvider(), tools=tools)
    result = agent.handle("/remember я живу в Москве")
    assert "Запомнил" in result.text
    assert "я живу в Москве" in notes.recall("Москве")


def test_single_param_tool_joined(tmp_path):
    seen = []

    def echo(text):
        seen.append(text)
        return text

    tools = ToolRegistry()
    tools.register("echo", echo, parameters={"text": "текст"})
    agent = JarvisAgent(FakeProvider(), tools=tools)
    agent.handle("/echo раз два три")
    assert seen == ["раз два три"]
