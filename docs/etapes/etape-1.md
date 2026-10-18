# Étape 1 — Squelette de bout en bout : rapport

Date : 2026-10-18 · Statut : **terminée, en attente de validation par Roosevelt**
Branche : `ccr-0269e16a-nbri2p` (dépôt `vendly-app/Nkap`)

## Résumé en 5 lignes

1. **Ce qui marche** : une saisie sur un site (note factice) est enregistrée avec son
   événement et sa ligne d'audit en une seule transaction, envoyée au central, appliquée une
   seule fois, dans l'ordre, puis affichée « synchronisée » uniquement après l'accusé du central.
2. Coupure d'Internet, réponse perdue, double envoi, processus tué en pleine écriture, heure de
   PC fausse, central restauré depuis une vieille sauvegarde : tous testés, sans perte ni doublon.
3. Le journal d'audit est chaîné et en ajout seul ; une falsification est détectée, même si les
   protections de la base sont contournées, et le central vérifie la chaîne de chaque site.
4. **Reste à faire** (étape 2) : utilisateurs et droits, référentiels descendants, sauvegarde,
   premiers écrans PySide6. Aucune fonction métier (stock, caisse) n'existe encore.
5. **Risques** : le métier « boulangerie » (fabrication, invendus, ventes) n'est pas cadré ; le
   dépôt GitHub est public ; l'hébergement du central n'est pas choisi.

## Critères de passage de l'étape 1

| Critère | Résultat | Où |
|---|---|---|
| T08 — saisie hors ligne conservée et marquée en attente | ✅ | `tests/acceptance/test_t08_saisie_hors_ligne.py` |
| T09 — double synchronisation sans double effet | ✅ | `tests/acceptance/test_t09_double_synchronisation.py` |
| T17 — arrêt brutal : base intègre, rien à moitié appliqué, reprise | ✅ (vrais processus tués) | `tests/acceptance/test_t17_arret_brutal.py` |
| Migrations validées sur SQLite **et** PostgreSQL | ✅ (montée, descente, schéma identique aux modèles) | `tests/unit/*/test_*_migrations.py` |
| Décisions consignées | ✅ 001 à 008 | `docs/decisions/` |
| Intégration continue Linux (+ PostgreSQL) et Windows | ✅ | `.github/workflows/ci.yml` |

En plus : préparation de T07 (deux sites hors ligne en même temps, aucun doublon) et de T19
(horloges décalées de ±2 jours : ordre correct, alerte levée) dans
`tests/acceptance/test_preparation_t07_t19.py`.

## Ce qui a été construit, en français simple

| Brique | À quoi ça sert |
|---|---|
| `nkap.core` | Outils communs : horloge pilotable (pour les tests), identifiants uniques créés hors ligne (UUIDv7), montants en entiers et quantités exactes (jamais de `float`), réglages sûrs de SQLite (refus des lecteurs réseau, écriture garantie sur disque). |
| `nkap.events` | Le « format » des messages site → central : chaque événement est numéroté (1, 2, 3...) et porte une empreinte qui prouve qu'il n'a pas été modifié. |
| `nkap.audit` | Le journal d'audit chaîné : chaque ligne contient l'empreinte de la précédente. |
| `nkap.site_node` | Le service du nœud de site : base locale, file d'envoi, envoi automatique toutes les 60 s (et tout de suite après une saisie), état de la liaison, API pour les futurs postes, commandes `nkap-site`. |
| `nkap.central` | Le serveur central : sites autorisés par jeton secret, réception sans doublon et dans l'ordre, refus motivés, API, commandes `nkap-central`. |
| `tests/support/bench.py` | Le banc de simulation : plusieurs sites, chacun avec son horloge et sa liaison réseau qu'on peut couper. |
| `tests/support/crash.py` | L'outil qui lance un vrai processus et le tue sans prévenir. |

## Tests

- **≈ 300 tests automatisés**, rejouables (`pytest`), exécutés sur SQLite et PostgreSQL, sous
  Linux et Windows à chaque envoi sur GitHub.
- Essai réel effectué (hors tests) : central et site lancés par leurs commandes, note créée par
  l'API, synchronisée en 2 s ; central arrêté, saisie conservée « hors ligne », central relancé,
  renvoi automatique au bout de 16 s.

## Choix faits en cours de route (à connaître)

1. **`httpx2` au lieu de `httpx`** : Starlette 1.9 (sous FastAPI) a basculé sur `httpx2`,
   successeur officiel de `httpx` (même auteur, maintenu par l'équipe Pydantic). Il vérifie les
   certificats HTTPS avec le magasin de Windows, ce qui simplifie l'installation chez le client.
2. **Écriture sur disque garantie** (`synchronous=FULL`) : un peu plus lent, mais une opération
   confirmée survit à une coupure de courant juste après. Important à Dschang.
3. **Battement de cœur** : quand il n'y a rien à envoyer, le site interroge quand même le central.
   Il sait ainsi qu'il est de nouveau en ligne, mesure l'écart d'horloge, et renvoie seul ce
   qu'un central restauré aurait perdu.
4. **Audit obligatoire** : une opération métier sans ligne d'audit est refusée par le code.
5. **Événement refusé = envoi bloqué** à cet endroit (jamais de saut silencieux) : la procédure
   de déblocage par un administrateur sera définie à l'étape 7.

## Limites connues (prévues plus tard)

| Limite | Prévu à |
|---|---|
| L'API du site n'a pas encore d'utilisateurs : elle n'écoute que sur la machine elle-même | Étape 2 |
| Le jeton de synchronisation est dans le fichier `.env` (pas encore dans le coffre de Windows) | Étape 8 |
| Pas encore de sauvegarde automatique ni de restauration testée (T15) | Étape 2 |
| Les journaux techniques du service ne sont pas encore écrits dans un fichier | Étape 8 |
| Les événements acquittés ne sont jamais purgés du site (conservation prévue : 90 jours) | Étape 7 |
| Le central accepte SQLite pour les essais ; en production, PostgreSQL uniquement | — |

## Questions pour l'étape 2 (et avant l'étape 3)

1. **Structure réelle de la Boulangerie de la Paix** : combien de sites (un fournil et des
   points de vente ?), combien d'utilisateurs par site, quels PC disponibles ?
2. **Métier boulangerie** (décision 003) : faut-il en V1 la fabrication (recettes : farine,
   levure → pains), les invendus et pertes, les ventes au comptoir article par article ?
   Sans fabrication, le stock de matières premières ne peut pas rester juste.
3. **Hébergement du central** : fournisseur, pays, budget (nécessaire dès l'étape 2).
4. **Rôles** : qui fait quoi, sur quel site (caissier, gérant, comptable, administrateur...) ?
5. **Contrat client** : propriété du code à Baobab Labs (à confirmer, c'est le nom inscrit dans
   `LICENSE`), licence d'utilisation pour la boulangerie. À faire valider par un juriste.

## Commandes exactes (PowerShell, Windows)

Récupérer le travail et lancer les tests :

```powershell
cd C:\chemin\vers\Nkap          # ou : git clone https://github.com/vendly-app/Nkap.git
git fetch origin
git checkout ccr-0269e16a-nbri2p
git pull origin ccr-0269e16a-nbri2p
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Essayer un central et un site sur le même PC : voir la section « Essayer » du `README.md`.
