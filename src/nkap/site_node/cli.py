"""Commandes du nœud de site.

``nkap-site init | migrate | serve | sync | status | verify-audit``
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence

from nkap.core.clock import SystemClock
from nkap.core.migrations import SITE_MIGRATIONS, upgrade_database
from nkap.i18n import translate
from nkap.site_node.audit_log import verify_audit_log
from nkap.site_node.config import SiteSettings
from nkap.site_node.identity import DEFAULT_TIMEZONE, NodeIdentity, initialize_identity
from nkap.site_node.runtime import build_site_runtime
from nkap.site_node.sync_status import read_sync_status


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nkap-site", description="Nœud de site Nkap.")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Crée la base du site et enregistre son identité.")
    init.add_argument("--company-id", type=uuid.UUID, required=True)
    init.add_argument("--site-id", type=uuid.UUID, required=True)
    init.add_argument("--site-code", required=True, help="Ex. S01 (identique au central)")
    init.add_argument("--timezone", default=DEFAULT_TIMEZONE)

    commands.add_parser("migrate", help="Met à jour le schéma de la base du site.")
    serve = commands.add_parser("serve", help="Démarre le service du site (API + envoi).")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    commands.add_parser("sync", help="Lance une synchronisation immédiate.")
    commands.add_parser("status", help="Affiche l'état de la synchronisation.")
    commands.add_parser("verify-audit", help="Vérifie l'intégrité du journal d'audit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = SiteSettings()  # valeurs lues dans l'environnement ou le fichier .env

    if args.command in ("init", "migrate"):
        upgrade_database(SITE_MIGRATIONS, settings.database_url)
    if args.command == "migrate":
        print("Base du site à jour.")
        return 0

    runtime = build_site_runtime(settings, SystemClock())
    try:
        if args.command == "init":
            identity = NodeIdentity(args.company_id, args.site_id, args.site_code, args.timezone)
            with runtime.session_factory.begin() as session:
                initialize_identity(session, identity, runtime.clock.now())
            print(f"Site {identity.site_code} initialisé.")
            return 0

        if args.command == "serve":
            import uvicorn

            from nkap.site_node.api import create_site_app

            app = create_site_app(
                session_factory=runtime.session_factory,
                uow=runtime.uow,
                clock=runtime.clock,
                sender=runtime.sender,
                worker=runtime.worker,
                drift_tolerance=runtime.drift_tolerance,
            )
            uvicorn.run(app, host=args.host or settings.host, port=args.port or settings.port)
            return 0

        if args.command == "sync":
            if runtime.sender is None:
                print(translate("sync.disabled"))
                return 1
            result = runtime.sender.sync_once(force=True)
            print(f"Résultat : {result.status} — envoyés {result.sent}, acquittés {result.acked},")
            print(f"en attente {result.pending}.")
            if result.error_message:
                print(f"Erreur : {result.error_message} ({result.error_code})")
            return 0 if result.status in ("synced", "partial") else 1

        if args.command == "status":
            with runtime.session_factory() as session:
                view = read_sync_status(session, runtime.clock, runtime.drift_tolerance)
            print(f"État : {view.state}")
            print(f"En attente d'envoi : {view.pending_count} (refusés : {view.rejected_count})")
            print(f"Dernier contact avec le central : {view.last_success_at or 'jamais'}")
            if view.offline_since:
                print(f"Hors ligne depuis : {view.offline_since}")
            if view.last_error_message:
                print(f"Dernière erreur : {view.last_error_message} ({view.last_error_code})")
            if view.clock_alert:
                print(f"ALERTE : horloge décalée de {view.clock_offset_seconds} s avec le central.")
            return 0

        if args.command == "verify-audit":
            with runtime.session_factory() as session:
                check = verify_audit_log(session)
            if check.ok:
                print(f"Journal d'audit intègre ({check.checked} lignes vérifiées).")
                return 0
            print(f"JOURNAL D'AUDIT ALTÉRÉ à la ligne {check.first_broken_seq} : {check.reason}.")
            return 1
    finally:
        runtime.close()
    return 2  # pragma: no cover - argparse refuse les commandes inconnues


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
