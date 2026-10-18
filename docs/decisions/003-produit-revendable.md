# 003 — Un produit revendable : rien de propre au client dans le code

Date : 2026-10-18 · Statut : accepté

## Contexte

Le premier client est la **Boulangerie de la Paix** (Dschang). Si le logiciel donne
satisfaction, Baobab Labs souhaite le revendre à d'autres structures. Il faut donc éviter
qu'il soit taillé sur mesure pour un seul client.

## Décision

1. **Aucune donnée propre à un client dans le code** : nom, sites, dépôts, plan de comptes,
   taux, plafonds de caisse, etc. sont du **paramétrage** ou des données de départ chargées
   à l'installation.
2. **Une installation par client** : chaque client a son propre central (sa propre base
   PostgreSQL). Pas de serveur partagé entre clients en V1 : isolement simple, sauvegarde et
   restauration par client, aucun risque de mélange de données entre clients.
3. **`company_id` sur toutes les tables** : un client peut avoir plusieurs sociétés plus tard,
   et un mode « plusieurs clients sur un même serveur » restera envisageable.
4. Les règles comptables et fiscales sont **paramétrables** (SYSCOHADA révisé proposé par
   défaut, comme exemple à valider), marquées `TODO(expert-comptable)`.
5. Interface **français / anglais** dès le départ.
6. Les besoins propres au métier du premier client (voir ci-dessous) seront construits comme
   des **modules génériques** et activables, pas comme du code spécifique « boulangerie ».

## Points à traiter hors du code

- **Propriété du code** : à écrire dans le contrat avec la Boulangerie de la Paix
  (Baobab Labs garde la propriété du logiciel ; le client reçoit une licence d'utilisation).
  Sans cette clause, la revente peut être contestée. À faire valider par un juriste.
- **Métier de la boulangerie** : le cahier des charges v1.0 ne couvre ni la **fabrication**
  (recettes : farine, sucre, levure → pains), ni les **produits périssables** (invendus,
  pertes, dates limites), ni les **ventes au comptoir** article par article. Ces points sont
  à cadrer avec le client **avant l'étape 3 (stocks)** : sans fabrication, le stock de
  matières premières ne peut pas rester juste.

## Conséquences

- Il faudra un outil d'installation qui crée un client, ses sociétés et ses sites (étape 8).
- Un peu plus de paramétrage au départ, mais pas de « fork » par client à maintenir.
