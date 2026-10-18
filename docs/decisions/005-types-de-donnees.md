# 005 — Types de données : pas de float, dates en UTC, même comportement partout

Date : 2026-10-18 · Statut : accepté

## Contexte

Les nombres à virgule flottante (`float`) produisent des erreurs d'arrondi
(0,1 + 0,2 = 0,30000000000000004) : inacceptable pour de l'argent ou du stock.
Par ailleurs SQLite et PostgreSQL ne gèrent pas les décimaux et les dates de la même façon :
SQLite convertirait même un décimal en `float` en silence.

## Décision

1. **Montants** : entiers dans la plus petite unité de la devise (le FCFA n'a pas de
   décimales : 12 500 FCFA = `12500`). Type Python `Money` (montant + devise),
   colonne `AmountType` (BIGINT) qui **refuse** tout `float` ou décimal.
   Le nombre de décimales d'une devise vient du référentiel `currencies` (étape 2).
2. **Quantités** : `Decimal`. La précision est celle de l'unité (`units.decimals`, de 0 à 6).
   En base, colonne `QuantityType` : entier de **millionièmes** (BIGINT). Résultat : calculs
   exacts, y compris les sommes faites par la base, à l'identique sur SQLite et PostgreSQL.
   Toute perte de précision est une **erreur**, jamais un arrondi silencieux.
3. **Dates-heures** : toujours avec fuseau, stockées en **UTC** (`UTCDateTime`), relues en UTC.
   Une date-heure sans fuseau est refusée. La date métier d'une opération est une simple date
   (type `Date`), calculée par défaut dans le fuseau du site (`Africa/Douala`).
4. **Identifiants** : type standard `Uuid` de SQLAlchemy (voir décision 004).
5. **JSON canonique** (`nkap.core.canonical`) pour toute empreinte : clés triées, dates en
   UTC au format fixe, décimaux en texte, `float` refusés.
6. Les arrondis (calcul du coût moyen, TVA...) ne sont **pas** décidés ici : ce sont des règles
   comptables, à faire valider (`TODO(expert-comptable)`).

## Conséquences

- Un test dédié vérifie que chaque type se comporte à l'identique sur les deux moteurs.
- La règle de lint `DTZ` (ruff) interdit dans le code les dates sans fuseau.
- Quantité maximale stockable : environ 9 000 milliards d'unités, largement suffisant.
