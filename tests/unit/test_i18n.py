from nkap.i18n import SUPPORTED_LOCALES, catalog, translate


def test_every_message_exists_in_every_language() -> None:
    keys = {locale: set(catalog(locale)) for locale in SUPPORTED_LOCALES}
    assert keys["fr"] == keys["en"]


def test_translate_formats_parameters_in_the_requested_language() -> None:
    fr = translate("event.unknown_type", event_type="X", payload_version=2)
    en = translate("event.unknown_type", "en", event_type="X", payload_version=2)
    assert "inconnu" in fr
    assert "Unknown" in en
    assert "X" in fr
    assert "X" in en


def test_translate_falls_back_to_french_then_to_the_code() -> None:
    assert translate("error.generic", "de") == translate("error.generic", "fr")
    assert translate("code.inexistant") == "code.inexistant"


def test_missing_parameters_are_left_visible() -> None:
    assert "{event_type}" in translate("event.unknown_type", payload_version=1)
