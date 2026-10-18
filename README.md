# Nkap

Logiciel de gestion intégrée **multi-sites** (stocks, transferts entre dépôts, caisses,
premières écritures comptables) qui **continue de fonctionner sans Internet**.
Chaque site travaille sur sa propre base et se synchronise avec un serveur central
dès que la connexion revient.

Premier client : Boulangerie de la Paix (Dschang). Le produit est conçu pour être
revendu à d'autres structures : aucune donnée propre à un client n'est écrite dans le code.

> **État : étape 1 en cours** (squelette de bout en bout : synchronisation, audit,
> banc de tests). Aucune fonction métier n'est encore disponible.
> Plan et décisions : [`docs/cadrage/etape-0.md`](docs/cadrage/etape-0.md),
> [`docs/decisions/`](docs/decisions/).

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

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `src/nkap/` | Code du produit |
| `tests/` | Tests automatisés (pytest) |
| `docs/decisions/` | Décisions d'architecture : la mémoire du projet |
| `docs/cadrage/` | Cadrage et plan des étapes |
| `docs/reference/` | Cahier des charges v1.0 et son analyse critique |
| `BRIEF.md` | Référence du projet (prévaut sur le cahier des charges v1.0) |

## Règles du projet

- Aucune règle comptable ou fiscale inventée : tout est paramétrable et marqué
  `TODO(expert-comptable)` tant qu'un expert-comptable ne l'a pas validé.
- Aucun nombre à virgule flottante (`float`) pour les montants et les quantités.
- Aucun secret dans le code : voir `.env.example`.
- Code en anglais ; interface, messages et documentation en français.

Licence : propriétaire, voir [`LICENSE`](LICENSE).
