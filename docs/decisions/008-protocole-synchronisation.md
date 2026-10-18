# 008 — Protocole de synchronisation : événements numérotés, accusés, tout-ou-rien

Date : 2026-10-18 · Statut : accepté

## Contexte

Les sites travaillent hors ligne pendant des jours, puis envoient leurs opérations au
central sur des liaisons lentes et instables. Une réponse peut se perdre, un envoi être
répété, un PC avoir une heure fausse. Il ne faut jamais perdre une opération, ni l'appliquer
deux fois, ni annoncer « consolidé » à tort.

## Décision

### Côté site : la file d'envoi (« transactional outbox »)

1. Chaque opération écrit, **dans la même transaction**, sa donnée métier, sa ligne d'audit
   et ses **événements** dans `sync_outbox` (décisions 004, 007).
2. Chaque événement reçoit un numéro **`site_seq`** : 1, 2, 3… sans trou. C'est le **seul
   ordre** qui fait foi. L'heure du PC (`occurred_at`) est conservée à titre indicatif.
3. Les événements d'une même transaction partagent `tx_id` et `tx_size` : ils voyagent et
   sont appliqués **ensemble**. Un lot ne coupe jamais une transaction en deux.
4. Le contenu d'un événement est **immuable** et son empreinte vérifiée avant envoi.

### Côté central : réception idempotente et ordonnée

5. Le site est identifié par son **jeton** (jamais par le contenu du lot). Un événement au
   nom d'un autre site ou d'une autre société est refusé (403).
6. Pour chaque transaction du lot, dans l'ordre :
   - **doublon** (mêmes `event_id` et même empreinte) : ignoré sans effet ;
   - même `event_id` mais contenu différent : **conflit** (anomalie grave) ;
   - numéro déjà utilisé par un autre événement : **conflit** (cas typique : base du site
     restaurée depuis une vieille sauvegarde) ;
   - numéro supérieur au numéro attendu : **trou** (`gap`) — le central ne l'applique pas et
     indique `expected_next` ;
   - transaction incomplète : **refus** ;
   - sinon application **tout-ou-rien** (point de sauvegarde) : chaque événement est vérifié
     (type connu, contenu valide, chaîne d'audit continue) puis appliqué et archivé dans
     `sync_inbox`. Au premier refus, la transaction entière est annulée et l'envoi s'arrête.
7. Réponse : `acked_through` = dernier numéro **contigu** enregistré. Les transactions
   précédentes du lot restent acquises.
8. `sync_inbox` est en ajout seul : c'est le journal des événements reçus, qui servira à
   reconstruire un nœud de site perdu (étape 7).

### Accusé de réception et affichage

9. Le site ne marque un événement « acquitté », et la donnée « synchronisée », **qu'à
   réception de l'accusé**. Jamais avant (garde-fou du brief).
10. Un événement refusé bloque la suite des envois de ce site : l'ordre n'est jamais violé.
    L'erreur est visible et doit être traitée (correction côté central, ou procédure
    d'administration à définir à l'étape 7). Pas de saut silencieux.

### Compatibilité des versions

11. Chaque type d'événement a des versions de contenu (`payload_version`). Le central garde
    les anciennes versions : **le central est toujours mis à jour avant les sites**, et un site
    en version N-1 peut continuer à se synchroniser.

### Conservation côté site

12. Les événements acquittés restent dans l'outbox du site pendant une durée de conservation
    (90 jours par défaut, purge à l'étape 7) : ils permettent de renvoyer au central ce qu'il
    aurait perdu en cas de restauration du central.

## Conséquences

- Une coupure, une réponse perdue ou un double envoi n'ont aucun effet néfaste : le site
  renvoie, le central ignore les doublons.
- Pas de résolution automatique de conflit sur les documents : avec la décision 002, les
  conflits ne peuvent venir que d'une anomalie, qui doit être examinée.
- Valeurs par défaut : lots de 200 événements maximum (jamais une transaction coupée),
  tentative toutes les 60 s quand le lien existe, attente progressive en cas d'échec.
