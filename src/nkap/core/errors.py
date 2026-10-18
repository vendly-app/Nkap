"""Erreurs du produit : chaque erreur porte un code stable et un message traduisible."""

from __future__ import annotations

from nkap.i18n import translate


class NkapError(Exception):
    """Erreur métier ou technique avec code (ex. ``sync.offline``) et paramètres."""

    default_code = "error.generic"

    def __init__(self, code: str | None = None, **params: object) -> None:
        self.code = code or self.default_code
        self.params = params
        super().__init__(translate(self.code, **params))

    def message(self, locale: str = "fr") -> str:
        """Message de l'erreur dans la langue demandée."""
        return translate(self.code, locale, **self.params)
