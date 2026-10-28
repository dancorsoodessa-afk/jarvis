from agent.tools_catalog import TOOLS
from jarvis_desktop import _migrate_tool_preferences


def test_legacy_settings_enable_the_full_tool_catalog_once():
    legacy = {"disabled_tools": [name for name, *_ in TOOLS if name != "status"]}
    assert len(legacy["disabled_tools"]) == 69

    assert _migrate_tool_preferences(legacy) is True
    assert legacy["disabled_tools"] == []
    assert legacy["tool_settings_version"] == 1


def test_tool_preferences_are_preserved_after_migration():
    settings = {
        "tool_settings_version": 1,
        "disabled_tools": ["status", "not-a-real-tool", "status"],
    }

    assert _migrate_tool_preferences(settings) is True
    assert settings["disabled_tools"] == ["status"]
    assert settings["tool_settings_version"] == 1


def test_migrated_tool_preferences_do_not_reset_on_next_start():
    settings = {"tool_settings_version": 1, "disabled_tools": ["status"]}

    assert _migrate_tool_preferences(settings) is False
    assert settings["disabled_tools"] == ["status"]
