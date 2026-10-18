# 002 — Propriété des données : un seul écrivain par donnée

Date : 2026-10-18 · Statut : accepté

## Contexte

Quand plusieurs sites travaillent hors ligne en même temps, deux sites peuvent modifier
la même donnée. Les stratégies automatiques du type « le dernier qui écrit gagne » font
perdre des données en silence : c'est inacceptable pour un stock ou une comptabilité.

## Décision

Chaque catégorie de données a **un seul écrivain autorisé** :

| Données | Seul écrivain |
|---|---|
| Mouvements de stock, transferts (côté expédition), sessions et transactions de caisse d'un site | Le site propriétaire |
| Réception d'un transfert | Le site destinataire |
| Référentiels : sociétés, sites, dépôts, articles, unités, catégories, comptes, journaux, rôles, utilisateurs | Le central |
| Clôture de période, validation comptable | Le central |

Règles associées :

- La stratégie « dernier écrivain gagne » est **interdite** sur toute donnée comptable ou de stock.
- Le central **vérifie** la propriété : un site ne peut envoyer que des événements à son nom
  (identifiant de site authentifié), et ne peut modifier que les documents qui lui appartiennent.
- Un transfert est découpé en deux événements distincts, chacun écrit par son propriétaire :
  l'expédition (site source) et la réception (site destinataire). Il n'y a donc pas de conflit.
- Les rares conflits restants (référentiels) sont **signalés**, jamais écrasés en silence.

## Conséquences

- Pas de mécanisme de fusion automatique à écrire pour les documents : le risque n° 1 de la
  synchronisation disparaît presque entièrement.
- Un site ne peut pas créer un article ou un compte hors ligne : il faut passer par le central.
  À vérifier avec le client (à l'étape 2) que cette contrainte est acceptable au quotidien.
