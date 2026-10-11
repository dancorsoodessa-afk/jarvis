from agent import habits


def test_preferences_persist_update_and_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(habits, "_STORE_PATH", tmp_path / "preferences.json")

    assert "Запомнил" in habits.remember_preference("Редактирование кода", "Готовый результат")
    assert "Готовый результат" in habits.list_preferences("код")
    habits.remember_preference("Редактирование кода", "Без ручных правок")
    output = habits.list_preferences()

    assert output.count("Редактирование кода") == 1
    assert "Без ручных правок" in output


def test_preference_can_be_forgotten(tmp_path, monkeypatch):
    monkeypatch.setattr(habits, "_STORE_PATH", tmp_path / "preferences.json")
    habits.remember_preference("Язык", "Русский")

    assert "Забыл" in habits.forget_preference("язык")
    assert "не найдено" in habits.list_preferences()


def test_empty_preference_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(habits, "_STORE_PATH", tmp_path / "preferences.json")
    try:
        habits.remember_preference(" ", " ")
    except ValueError:
        pass
    else:
        raise AssertionError("empty preference must be rejected")
