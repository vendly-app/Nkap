# 006 — Migrations : deux jeux Alembic (site, central), testés sur les deux moteurs

Date : 2026-10-18 · Statut : accepté

## Contexte

La base d'un site et la base centrale n'ont pas le même contenu (file d'envoi côté site,
file de réception côté central). Les deux schémas évolueront à chaque version, alors que
des sites peuvent rester hors ligne, donc en retard d'une version, pendant des jours.

## Décision

1. **Deux jeux de migrations Alembic** indépendants :
   `nkap.site_node:migrations` (révisions `s0001`, `s0002`...) et
   `nkap.central:migrations` (révisions `c0001`...).
2. Chaque migration est **écrite pour SQLite et PostgreSQL** (un site pourra passer à
   PostgreSQL si besoin, décision 001) et testée sur les deux :
   montée, descente, remontée, et comparaison exacte avec les modèles (`compare_metadata`).
3. Une migration s'exécute **en une seule transaction**, y compris sous SQLite : si elle
   échoue, la base reste dans son état précédent.
4. Noms de contraintes et d'index **prévisibles** (convention de nommage commune).
5. Protections en base (déclencheurs « contenu immuable », « ajout seul ») créées par les
   migrations, pour chaque moteur. **Attention** : sous SQLite, une migration qui recrée une
   table (mode « batch ») supprime ses déclencheurs ; elle doit les recréer. Un test vérifie
   la présence des déclencheurs après chaque montée de version.
6. Le nœud de site applique ses migrations **avant** de servir les postes ; le central est
   toujours mis à jour **avant** les sites.
7. Évolutions compatibles (« ajouter d'abord, retirer plus tard ») : une colonne nouvelle est
   d'abord facultative ; une colonne n'est supprimée qu'une fois tous les sites à jour.

## Conséquences

- Commandes : `nkap-site migrate` et `nkap-central migrate` (incréments suivants) ;
  dans le code, `nkap.core.migrations.upgrade_database()`.
- Créer une nouvelle migration : la rédiger à la main (modèle `script.py.mako`), puis laisser
  le test de comparaison confirmer qu'elle correspond aux modèles.
