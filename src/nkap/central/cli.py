"""Commandes du central : ``nkap-central migrate | register-site | revoke-site | serve``."""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence

from nkap.central.auth import register_site, revoke_site
from nkap.central.config import CentralSettings
from nkap.core.clock import SystemClock
from nkap.core.db import create_db_engine, make_session_factory
from nkap.core.migrations import CENTRAL_MIGRATIONS, upgrade_database
from nkap.core.orm import Actor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nkap-central", description="Serveur central Nkap.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Met à jour le schéma de la base centrale.")

    register = commands.add_parser(
        "register-site", help="Autorise un site et affiche son jeton secret (une seule fois)."
    )
    register.add_argument("--site-id", type=uuid.UUID, required=True)
    register.add_argument("--company-id", type=uuid.UUID, required=True)
    register.add_argument("--site-code", required=True, help="Ex. S01")

    revoke = commands.add_parser(
        "revoke-site", help="Retire à un site le droit de se synchroniser."
    )
    revoke.add_argument("--site-id", type=uuid.UUID, required=True)

    serve = commands.add_parser("serve", help="Démarre l'API du central.")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = CentralSettings()  # valeurs lues dans l'environnement ou le fichier .env

    if args.command == "migrate":
        upgrade_database(CENTRAL_MIGRATIONS, settings.database_url)
        print("Base centrale à jour.")
        return 0

    engine = create_db_engine(settings.database_url)
    factory = make_session_factory(engine)
    clock = SystemClock()
    actor = Actor(user_id=None, label="administrateur (ligne de commande)")
    try:
        if args.command == "register-site":
            with factory.begin() as session:
                token = register_site(
                    session,
                    site_id=args.site_id,
                    company_id=args.company_id,
                    site_code=args.site_code,
                    clock=clock,
                    actor=actor,
                )
            print(f"Site {args.site_code} autorisé.")
            print("Jeton secret du site (à copier dans la configuration du nœud de site,")
            print("il ne sera plus jamais affiché) :")
            print(token)
            return 0
        if args.command == "revoke-site":
            with factory.begin() as session:
                revoke_site(session, site_id=args.site_id, clock=clock, actor=actor)
            print("Site révoqué : ses prochains envois seront refusés.")
            return 0
        if args.command == "serve":
            import uvicorn

            from nkap.central.api import create_central_app

            app = create_central_app(factory, clock=clock)
            uvicorn.run(
                app,
                host=args.host or settings.host,
                port=args.port or settings.port,
                ssl_certfile=settings.ssl_certfile,
                ssl_keyfile=settings.ssl_keyfile,
            )
            return 0
    finally:
        engine.dispose()
    return 2  # pragma: no cover - argparse refuse les commandes inconnues


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
