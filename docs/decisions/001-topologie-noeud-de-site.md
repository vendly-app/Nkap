# 001 — Topologie : un nœud de site, seul écrivain de la base du site

Date : 2026-10-18 · Statut : accepté

## Contexte

Le logiciel doit fonctionner sur 3 à 5 sites, avec 6 à 20 utilisateurs, y compris pendant
des coupures Internet de plusieurs jours. Le cahier des charges v1.0 prévoit une base SQLite
par site, sans préciser si elle est installée sur chaque poste ou sur un serveur de site.

Si chaque poste avait sa propre base, chaque PC deviendrait un « maître » indépendant :
risques de stock négatif, de doublons et de conflits à chaque synchronisation.
Partager un fichier SQLite sur un lecteur réseau est interdit : c'est une cause connue de
corruption (verrouillage de fichiers peu fiable, mode WAL inutilisable).

## Décision

1. Chaque site possède un **nœud de site** : un PC serveur (alimenté par onduleur) qui
   exécute le service Nkap du site et détient **la** base du site (SQLite en mode WAL).
2. Un seul processus écrit dans cette base : le service du site.
3. Les postes Windows (interface PySide6) sont des **clients légers** : aucune base locale,
   ils appellent le service du site par le réseau local.
4. **Seul le nœud de site** communique avec le serveur central.
5. Le service de site doit fonctionner **plusieurs jours sans Internet** (valeur par défaut
   retenue : 7 jours en exploitation, 30 jours testés).
6. Le central (service + PostgreSQL) est **hébergé** (VPS ou cloud avec sauvegardes),
   et non installé sur un site sujet aux coupures de courant.
7. Le code d'accès aux données reste neutre vis-à-vis du moteur : si SQLite devenait un
   frein, un PostgreSQL local par site doit rester possible sans réécriture.

## Conséquences

- Le service refuse d'ouvrir une base SQLite placée sur un lecteur réseau.
- Pendant une coupure Internet, un site reste autonome pour **ses** dépôts et **ses** caisses.
- Si le nœud de site tombe en panne, les postes du site s'arrêtent : d'où l'onduleur,
  les sauvegardes horaires et la procédure de reconstruction depuis le central (étape 7).
- Matériel à prévoir par site : un PC dédié, un onduleur, un réseau local.
