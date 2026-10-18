"""Traduction des messages (français par défaut, anglais).

Le Cameroun est bilingue : tout message destiné à un utilisateur a un **code stable**
(ex. ``sync.offline``) et un texte dans chaque langue, rangé dans ``fr.json`` et
``en.json``. Les programmes s'échangent les codes ; l'interface affiche le texte dans
la langue de l'utilisateur.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Literal

Locale = Literal["fr", "en"]
SUPPORTED_LOCALES: tuple[Locale, ...] = ("fr", "en")
DEFAULT_LOCALE: Locale = "fr"


@cache
def catalog(locale: Locale) -> dict[str, str]:
    """Catalogue des messages d'une langue (code -> texte)."""
    raw = resources.files(__package__).joinpath(f"{locale}.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise ValueError(f"Catalogue de traduction invalide : {locale}.json")
    return data


class _KeepMissing(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def translate(code: str, locale: str = DEFAULT_LOCALE, /, **params: object) -> str:
    """Texte d'un message dans la langue demandée (repli : français, puis le code)."""
    chosen: Locale = "en" if locale == "en" else DEFAULT_LOCALE
    template = catalog(chosen).get(code) or catalog(DEFAULT_LOCALE).get(code) or code
    return template.format_map(_KeepMissing(params))
