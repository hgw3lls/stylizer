from app import model_select


def test_auto_select_models_prefers_env_override_for_image_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", "gpt-4.1")

    monkeypatch.setattr(
        model_select,
        "list_model_ids",
        lambda force_refresh=False: {"gpt-4.1", "gpt-image-1-mini", "gpt-image-1"},
    )

    selection = model_select.auto_select_models(force_refresh=True)

    assert selection.analysis_model == "gpt-4.1"
    assert selection.image_model == "gpt-image-1-mini"


def test_auto_select_models_falls_back_without_gpt_image_1_5(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_ANALYSIS_MODEL", raising=False)

    monkeypatch.setattr(
        model_select,
        "list_model_ids",
        lambda force_refresh=False: {"gpt-4o-mini", "gpt-image-1"},
    )

    selection = model_select.auto_select_models(force_refresh=True)

    assert selection.analysis_model == "gpt-4o-mini"
    assert selection.image_model == "gpt-image-1"


def test_auto_select_models_returns_none_when_no_image_models(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_ANALYSIS_MODEL", raising=False)

    monkeypatch.setattr(model_select, "list_model_ids", lambda force_refresh=False: {"gpt-4o-mini"})

    selection = model_select.auto_select_models(force_refresh=True)

    assert selection.analysis_model == "gpt-4o-mini"
    assert selection.image_model is None
