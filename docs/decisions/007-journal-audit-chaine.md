# 007 — Journal d'audit chaîné, en ajout seul, répliqué au central

Date : 2026-10-18 · Statut : accepté

## Contexte

L'AUDCIF (art. 22) exige l'irréversibilité des traitements et un chemin de révision.
La loi de finances camerounaise 2026 (art. L 19 du CGI, à confirmer sur le texte promulgué)
demande un journal technique d'audit **non altérable**, horodaté, avec l'identifiant de
l'utilisateur, conservé au moins 10 ans. Un administrateur ayant accès à la base pourrait
pourtant tenter de modifier ce journal.

## Décision

1. Table `audit_log` sur chaque site (et plus tard au central) : numéro de chaîne, auteur,
   action, objet, détails, heure, **empreinte de la ligne précédente** et **empreinte de la
   ligne** (SHA-256 du contenu en JSON canonique).
2. **Ajout seul**, imposé par la base elle-même : déclencheurs qui refusent `UPDATE`,
   `DELETE` (et `TRUNCATE` sous PostgreSQL), et qui refusent une ligne mal chaînée
   (numéro non consécutif ou empreinte précédente fausse).
3. Une **tête de chaîne** (`audit_chain_head`) mémorise le dernier numéro et la dernière
   empreinte ; elle ne peut qu'avancer d'une ligne existante.
4. **Toute transaction qui modifie des données métier doit écrire une ligne d'audit** ;
   sinon elle est refusée (`MissingAuditError`).
5. Chaque ligne d'audit est **répliquée au central** par un événement `AuditEntryRecorded`,
   dans la même transaction que l'opération. Le central vérifiera la continuité de la chaîne
   de chaque site (incrément 6) : un site qui réécrirait son journal serait repéré.
6. Vérification complète à la demande (`verify_audit_log`) : numéros, chaînage, empreintes,
   tête de chaîne.

## Limites connues

- Un utilisateur ayant tous les droits sur la base peut désactiver les déclencheurs, puis
  recalculer toute la chaîne. Il sera détecté **dès que le central compare** avec la copie
  qu'il a reçue. D'où la réplication, et à l'étape 7 : retrait des droits de modification au
  compte applicatif PostgreSQL, et chiffrement du disque des nœuds de site (BitLocker).
- Conservation 10 ans et export lisible hors logiciel : à traiter avec l'archivage (étape 7).
