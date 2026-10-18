# 004 — Identifiants : UUIDv7 générés localement, numéros lisibles par site

Date : 2026-10-18 · Statut : accepté

## Contexte

Un site hors ligne doit pouvoir créer des documents sans demander de numéro au central,
sans jamais entrer en collision avec un autre site. Les utilisateurs ont aussi besoin de
numéros lisibles (bons de transfert, pièces comptables).

## Décision

1. **Clé technique** : chaque enregistrement a un **UUID version 7** (RFC 9562) généré
   localement. 74 bits aléatoires rendent les collisions pratiquement impossibles ; les
   48 premiers bits (l'heure en millisecondes) rangent les nouvelles lignes en fin d'index.
   L'heure contenue dans l'UUID n'a **aucune valeur métier** et ne sert jamais à ordonner.
2. **Numéro lisible des transferts** : `TRF-<CODE_SITE>-<ANNÉE>-<COMPTEUR_LOCAL>`, par
   exemple `TRF-S02-2026-000001`. Pas de réservation de plages de numéros.
3. **Numéros de pièces et d'écritures comptables** : attribués **à la validation**, par
   journal et par site (ex. journal `CAI-S02`), sans trou.
4. **Compteurs** : table `site_sequences` (un compteur par nom), incrémentée dans la même
   transaction que l'opération qui consomme le numéro. Le compteur `sync` produit le
   `site_seq` des événements de synchronisation.
5. L'implémentation UUIDv7 est dans `nkap.core.ids` (Python 3.12 n'en fournit pas).

## Conséquences

- Aucun aller-retour avec le central pour créer un document : le hors-ligne est total.
- Un numéro lisible est unique **par site** grâce au code du site ; l'UUID reste la seule
  clé utilisée par les programmes et la synchronisation.
