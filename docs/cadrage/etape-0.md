# Étape 0 — Cadrage

Statut : **validé par Roosevelt le 2026-10-18 (« Go »).** L'étape 1 est lancée.

## Réponses reçues

| Question | Réponse | Conséquence |
|---|---|---|
| 1. Protocole git | « Go » sur la proposition P1 | Claude pousse sur la branche `ccr-0269e16a-nbri2p` ; Roosevelt relit et fusionne par pull request |
| 2. Produit ou client | Demande d'un client : **Boulangerie de la Paix (Dschang)**, avec l'objectif de revendre le logiciel à d'autres structures | Décision 003 : rien de propre au client dans le code, une installation par client |
| 3. Durée hors ligne | Pas de réponse : valeur par défaut | 7 jours en exploitation, 30 jours testés |
| 4. Matériel des nœuds | Pas de réponse : valeur par défaut | Un PC Windows dédié par site, avec onduleur |
| 5. Serveur central | Pas de réponse : valeur par défaut | Central hébergé ; simulé en local à l'étape 1 ; à trancher avant l'étape 2 |

Nouveau point soulevé par la réponse 2 (décision 003) : la fabrication (recettes),
les produits périssables et les ventes au comptoir ne figurent pas dans le cahier des
charges v1.0. À cadrer avec le client avant l'étape 3.

Sources lues : `BRIEF.md`, `docs/reference/cahier-des-charges-v1.0.pdf` (5 pages, scan),
`docs/reference/analyse-critique-cdc-v1.0.md`.

---

## 1. Ce que j'ai compris (en 10 lignes)

1. Application Windows de gestion (stocks, transferts, caisses, écritures en brouillon) pour 3 à 5 sites, 6 à 20 utilisateurs.
2. Chaque site doit tourner **plusieurs jours sans Internet**.
3. Chaque site a un **nœud de site** (PC serveur + onduleur) : service FastAPI + SQLite en WAL, **seul écrivain** de la base. Les postes PySide6 sont des clients légers sur le réseau local.
4. Seul le nœud de site parle au **central** (FastAPI + PostgreSQL, hébergé).
5. **Propriété des données** : le site écrit ses mouvements, caisses et expéditions ; le destinataire écrit la réception ; le central écrit les référentiels et les clôtures. Pas de « dernier écrivain gagne ».
6. La synchronisation envoie des **événements métier immuables** (outbox dans la même transaction), numérotés par `site_seq` sans trou. Le central déduplique, détecte les trous, applique dans l'ordre, et acquitte. Rien n'est « consolidé » sans accusé.
7. L'ordre ne dépend jamais de l'horloge d'un PC ; l'horloge est injectable pour les tests.
8. Montants en entiers (FCFA sans décimale), quantités en `Decimal` ; jamais de `float`.
9. Journal d'audit en ajout seul, chaîné par hachage, conservé 10 ans.
10. Toute règle comptable ou fiscale est paramétrable et marquée `TODO(expert-comptable)`. Le MVP ne génère que des écritures **en brouillon**.

La synchronisation est construite **dès l'étape 1** (correction principale de l'analyse critique).

---

## 2. Points à signaler avant de coder

| # | Point | Proposition |
|---|---|---|
| P1 | Le brief dit que **Roosevelt pousse via VS Code**. Mais cette session Claude Code tourne dans le cloud, sur le dépôt `vendly-app/Nkap`, et pousse elle-même sur la branche `ccr-0269e16a-nbri2p`. | Je pousse sur cette branche ; Roosevelt relit et fusionne via une pull request. Je fournis quand même, à chaque étape, les commandes PowerShell pour récupérer, installer et lancer les tests sur Windows. |
| P2 | Les tests doivent passer sur SQLite **et** PostgreSQL. | Tests PostgreSQL lancés en local ici et en intégration continue (GitHub Actions avec un service PostgreSQL). Sur Windows, PostgreSQL ne sera nécessaire que pour tester le central. |
| P3 | Le site et le central n'ont pas le même schéma (outbox côté site, inbox et projections côté central). | Deux jeux de migrations Alembic séparés (`site` et `central`), chacun testé sur son moteur. Le code commun (types, événements) est partagé. À consigner en décision. |
| P4 | Python 3.12 est imposé. | Je cible 3.12 (`requires-python = ">=3.12,<3.13"`) et la CI teste 3.12. |
| P5 | Le nœud de site doit tourner en continu sur Windows. | Étape 1 : simple lancement en ligne de commande. Service Windows (NSSM ou pywin32) prévu à l'étape 8 (packaging). |

---

## 3. Questions bloquantes (5 maximum)

1. **Protocole git (P1)** : es-tu d'accord pour que je pousse sur la branche et que tu fusionnes par pull request ? Ou veux-tu garder le flux « je te donne les commandes, tu pousses » ?
2. **Produit Baobab Labs ou projet pour un client précis ?** Cela fixe la licence du dépôt (propriétaire ou autre), le nom affiché et la responsabilité réglementaire.
3. **Coupures** : durée maximale hors ligne à tenir (ex. 7 jours en exploitation, 30 jours en test) et qualité du lien quand il existe (3G/4G, ADSL, fibre). Cela dimensionne les lots de synchronisation et le banc de tests.
4. **Matériel des nœuds de site** : un PC Windows dédié par site (version de Windows ?), avec onduleur ? Ou un PC de bureau partagé ?
5. **Serveur central** : hébergement prévu (VPS, cloud, fournisseur, pays) ? Pour l'étape 1, je peux tout simuler en local ; la réponse devient bloquante à l'étape 2.

Questions **non bloquantes pour l'étape 1**, à régler avant les étapes indiquées :
statut juridique et expert-comptable (avant l'étape 3), matrice rôles × sites × opérations (étape 2),
politique de caisse (étape 5), reprise de données initiale (étape 3), inventaire permanent ou intermittent (étape 6).

---

## 4. Plan détaillé de l'étape 1 — Squelette de bout en bout

**Objectif :** un événement factice créé sur un site, envoyé au central, dédupliqué, acquitté, avec le journal d'audit chaîné et un banc de simulation multi-sites. Aucune fonction métier encore.

**Critère de passage :** T08, T09 et T17 verts sur l'événement factice ; migrations validées sur SQLite et PostgreSQL ; décisions consignées.

### 4.1 Structure du dépôt

```
Nkap/
├── BRIEF.md, CLAUDE.md, README.md, .env.example, pyproject.toml
├── docs/decisions/            # ADR 001 à 008 (ci-dessous)
├── src/nkap/
│   ├── core/                  # horloge injectable, UUID, types Money/Quantity, erreurs
│   ├── events/                # enveloppe d'événement + schémas Pydantic versionnés
│   ├── audit/                 # journal chaîné (calcul et vérification du hachage)
│   ├── site_node/             # API FastAPI du site, base SQLite, outbox, envoi
│   │   └── migrations/        # Alembic « site »
│   └── central/               # API FastAPI centrale, PostgreSQL, inbox, accusés
│       └── migrations/        # Alembic « central »
└── tests/
    ├── unit/
    ├── sim/                   # banc de simulation (sites, réseau, horloges, pannes)
    └── acceptance/            # T08, T09, T17…
```

Le client PySide6 arrive à l'étape 2.

### 4.2 Décisions à consigner (`docs/decisions/`)

Numérotation définitive (dans l'ordre où les décisions sont consignées) :

| N° | Décision |
|---|---|
| 001 | Topologie : nœud de site écrivain unique, postes clients légers, central hébergé |
| 002 | Propriété des données (tableau du brief § 3.3) |
| 003 | Produit revendable : rien de propre au client dans le code, une installation par client |
| 004 | Identifiants : UUID générés localement (UUIDv7, triés dans le temps, meilleurs pour les index) ; numéros lisibles `TRF-S02-2026-000001` |
| 005 | Types : montants en entiers, quantités en `Decimal` via `TypeDecorator`, aucun `float` |
| 006 | Deux jeux de migrations Alembic (site / central) |
| 007 | Journal d'audit chaîné par SHA-256 et protégé par déclencheurs |
| 008 | Protocole de synchronisation : enveloppe d'événement, `site_seq`, lots atomiques, accusés, détection de trous |

### 4.3 Incréments (un commit chacun, tests compris)

1. **Socle du projet** : `pyproject.toml` (FastAPI, SQLAlchemy 2, Alembic, Pydantic, httpx, pytest, ruff, mypy), README avec commandes PowerShell, `.env.example`, CI GitHub Actions (ruff, mypy, pytest sur SQLite et PostgreSQL).
2. **`core`** : horloge injectable (`SystemClock`, `FakeClock`), générateur d'UUIDv7, `Money` (entier + devise) et `Quantity` (`Decimal`). Tests : aucun `float` accepté, arrondis, comportement identique sur les deux moteurs.
3. **Enveloppe d'événement** : `event_id`, `site_id`, `site_seq`, `entity_type`, `entity_id`, `version`, `payload_version`, `local_ts`, `business_date`, `payload`. Un événement factice `DemoNoteCreated`. Tests de validation stricte.
4. **Base du site + outbox** : tables `site_sequences`, `sync_outbox`, `demo_notes` ; migration Alembic « site » ; SQLite en WAL. Créer une note écrit la note, prend le `site_seq` suivant et écrit l'outbox **dans la même transaction**. Tests : atomicité, `site_seq` sans trou, même sous écritures concurrentes.
5. **Journal d'audit chaîné** : table `audit_log` avec `prev_hash`/`hash`, déclencheurs SQLite et PostgreSQL qui refusent `UPDATE` et `DELETE`, fonction de vérification de la chaîne. Tests : modification directe refusée ; altération détectée (prépare T23).
6. **Central + inbox** : tables `sync_inbox` (unique sur `event_id` et sur `(site_id, site_seq)`), `site_sync_state` (dernier `site_seq` contigu par site), `demo_notes` ; migration Alembic « central » ; endpoint `POST /sync/events` qui applique un lot en une transaction et répond avec l'accusé et, en cas de trou, le numéro à renvoyer.
7. **Envoi depuis le site** : boucle d'envoi par lots, reprise avec temporisation progressive, statut outbox `pending → sent → acked` ou `error`. « Consolidé » uniquement après accusé. Endpoint de statut du site (en attente, dernier succès, hors ligne depuis…).
8. **Banc de simulation** : plusieurs sites en mémoire contre un central réel (via le transport ASGI de httpx), interrupteur réseau par site, horloge propre à chaque site, injection de panne (arrêt de processus en pleine transaction).
9. **Tests d'acceptation** :
   - **T08** : réseau coupé, création de notes → conservées localement et marquées en attente.
   - **T09** : réseau rétabli, synchronisation lancée deux fois (et lot rejoué) → une seule note au central, aucun double effet.
   - **T17** : processus du site tué pendant une transaction et pendant un envoi → `PRAGMA integrity_check` OK, rien à moitié appliqué, l'envoi reprend seul.
   - En plus : trou de `site_seq` détecté et comblé ; deux sites hors ligne en parallèle sans collision d'identifiant (prépare T07) ; horloge du site décalée de ±2 jours sans effet sur l'ordre (prépare T19).

**Livrables en fin d'étape :** code, tests, migrations, ADR 001-008, README, résumé en 5 lignes, commandes PowerShell exactes.

**Durée indicative :** 1 à 2 semaines de travail effectif, découpées en 9 commits.

**Hors étape 1 :** authentification, rôles, référentiels descendants, client PySide6, stocks.
