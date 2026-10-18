# Nkap

Logiciel de gestion intégrée **multi-sites** (stocks, transferts entre dépôts, caisses,
premières écritures comptables) qui **continue de fonctionner sans Internet**.
Chaque site travaille sur sa propre base et se synchronise avec un serveur central
dès que la connexion revient.

Premier client : Boulangerie de la Paix (Dschang). Le produit est conçu pour être
revendu à d'autres structures : aucune donnée propre à un client n'est écrite dans le code.

> **État : étape 1 terminée** (squelette de bout en bout), en attente de validation.
> La synchronisation, le journal d'audit et le banc de tests fonctionnent sur une donnée
> factice (des « notes »). Aucune fonction métier (stocks, caisses...) n'existe encore.
> Rapport : [`docs/etapes/etape-1.md`](docs/etapes/etape-1.md) ·
> Décisions : [`docs/decisions/`](docs/decisions/).

## Architecture en une image

```
   Site A (ex. boulangerie)              Site B (ex. point de vente)
 ┌──────────────────────────┐          ┌──────────────────────────┐
 │ Postes Windows (PySide6) │          │ Postes Windows (PySide6) │
 │            │ réseau local│          │            │             │
 │  Nœud de site (PC + UPS) │          │  Nœud de site (PC + UPS) │
 │  service + base SQLite   │          │  service + base SQLite   │
 └────────────┬─────────────┘          └────────────┬─────────────┘
              │   HTTPS, quand Internet est disponible │
              └──────────────► Central ◄──────────────┘
                        (service + PostgreSQL, hébergé)
```

- Les postes ne contiennent aucune base : ils parlent au **nœud de site**.
- Le nœud de site est le **seul** à écrire dans la base du site, et le seul à parler au central.
- Les sites envoient des **événements numérotés** ; le central ne les applique qu'une fois,
  dans l'ordre, et renvoie un accusé de réception.

## Installation sur Windows (PowerShell)

Prérequis : [Python 3.12](https://www.python.org/downloads/) (cocher « Add python.exe to PATH »)
et [Git](https://git-scm.com/download/win).

```powershell
# 1. Récupérer le code
git clone https://github.com/vendly-app/Nkap.git
cd Nkap
git checkout ccr-0269e16a-nbri2p

# 2. Créer l'environnement Python du projet
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Si PowerShell refuse d'activer l'environnement (`Activate.ps1`), ce n'est pas nécessaire :
toutes les commandes ci-dessous appellent directement `.\.venv\Scripts\python.exe`.

## Lancer les tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Environ 300 tests, une minute environ (sans PostgreSQL configuré, les variantes PostgreSQL
sont sautées : c'est normal). Ils comprennent les tests d'acceptation
(`tests/acceptance/`) : saisie hors ligne (T08), double synchronisation (T09) et arrêt
brutal d'un processus en pleine écriture (T17).

Les tests utilisent SQLite. Pour les lancer aussi sur PostgreSQL (facultatif sur un poste
de développement, systématique dans l'intégration continue) :

```powershell
$env:NKAP_TEST_POSTGRES_URL = "postgresql+psycopg://postgres:motdepasse@localhost:5432/postgres"
.\.venv\Scripts\python.exe -m pytest
```

Contrôles de qualité (également exécutés automatiquement sur GitHub) :

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

## Essayer : un central et un site sur le même PC

Ouvrir **trois fenêtres PowerShell** dans le dossier `Nkap`.

**Fenêtre 1 — le central** (base SQLite d'essai ; en production ce sera PostgreSQL) :

```powershell
New-Item -ItemType Directory -Force C:\Nkap\essai | Out-Null
$env:NKAP_CENTRAL_DATABASE_URL = "sqlite:///C:/Nkap/essai/central.db"
.\.venv\Scripts\nkap-central.exe migrate
.\.venv\Scripts\nkap-central.exe register-site --site-id 11111111-1111-4111-8111-111111111111 --company-id 22222222-2222-4222-8222-222222222222 --site-code S01
# Copier le jeton affiché (nks_...), puis :
.\.venv\Scripts\nkap-central.exe serve
```

**Fenêtre 2 — le nœud de site S01** (remplacer `nks_...` par le jeton copié) :

```powershell
$env:NKAP_SITE_DATABASE_URL = "sqlite:///C:/Nkap/essai/site.db"
$env:NKAP_SITE_CENTRAL_URL = "http://127.0.0.1:8800"
$env:NKAP_SITE_SYNC_TOKEN = "nks_..."
.\.venv\Scripts\nkap-site.exe init --site-id 11111111-1111-4111-8111-111111111111 --company-id 22222222-2222-4222-8222-222222222222 --site-code S01
.\.venv\Scripts\nkap-site.exe serve
```

**Fenêtre 3 — saisir et observer** :

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8700/api/v1/demo-notes -ContentType "application/json; charset=utf-8" -Body '{"text":"Note de test"}'
Invoke-RestMethod http://127.0.0.1:8700/api/v1/demo-notes      # sync_status : pending puis synced
Invoke-RestMethod http://127.0.0.1:8700/api/v1/sync/status
```

On peut aussi tout essayer dans le navigateur : http://127.0.0.1:8700/docs (site) et
http://127.0.0.1:8800/docs (central).

Pour voir le mode hors ligne : fermer la fenêtre 1 (Ctrl+C), créer des notes (elles restent
`pending`, l'état passe à `offline`), relancer `nkap-central.exe serve` : le site renvoie tout
seul. L'attente entre deux essais grandit pendant une coupure (2 s, 4 s, 8 s... jusqu'à
5 minutes) ; `Invoke-RestMethod -Method Post http://127.0.0.1:8700/api/v1/sync/run` force
l'envoi immédiat.

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `src/nkap/` | Code du produit |
| `tests/` | Tests automatisés (pytest) |
| `docs/decisions/` | Décisions d'architecture : la mémoire du projet |
| `docs/cadrage/` | Cadrage et plan des étapes |
| `docs/etapes/` | Rapport de fin de chaque étape |
| `docs/reference/` | Cahier des charges v1.0 et son analyse critique |
| `BRIEF.md` | Référence du projet (prévaut sur le cahier des charges v1.0) |

## Règles du projet

- Aucune règle comptable ou fiscale inventée : tout est paramétrable et marqué
  `TODO(expert-comptable)` tant qu'un expert-comptable ne l'a pas validé.
- Aucun nombre à virgule flottante (`float`) pour les montants et les quantités.
- Aucun secret dans le code : voir `.env.example`.
- Code en anglais ; interface, messages et documentation en français.

Licence : propriétaire, voir [`LICENSE`](LICENSE).
