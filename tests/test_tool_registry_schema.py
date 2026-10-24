from agent.tools.registry import ToolRegistry


def test_tool_schema_keeps_defaulted_arguments_optional():
    registry = ToolRegistry()

    def example(required: str, optional: str = "", count: int = 1):
        return required, optional, count

    registry.register(
        "example",
        example,
        description="Example tool",
        parameters={
            "required": "Required value",
            "optional": "Optional value",
            "count": "Optional count",
        },
    )

    schema = registry.spec("example")["function"]["parameters"]
    assert schema["required"] == ["required"]
    assert set(schema["properties"]) == {"required", "optional", "count"}


def test_tool_schema_has_no_required_arguments_when_all_have_defaults():
    registry = ToolRegistry()

    def example(query: str = "", limit: int = 5):
        return query, limit

    registry.register(
        "example",
        example,
        description="Example tool",
        parameters={"query": "Optional query", "limit": "Optional limit"},
    )

    assert registry.spec("example")["function"]["parameters"]["required"] == []
