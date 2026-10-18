# Gestion comptable intégrée multi-sites — Brief d'implémentation pour Claude Code

> **Comment l'utiliser :** place ce fichier à la racine du nouveau dépôt (sous le nom `BRIEF.md`, ou copie-le dans `CLAUDE.md`), puis lance Claude Code avec le **prompt de démarrage** de la section 0.

---

## 0. Prompt de démarrage (à coller dans Claude Code)

```
Lis intégralement BRIEF.md avant toute action. C'est la référence du projet.

1. Ne code rien tout de suite. Commence par l'ÉTAPE 0 : confirme que tu as compris le brief,
   liste les questions bloquantes de la section 14 (maximum 5, les plus importantes),
   puis propose un plan détaillé de l'étape 1 et attends mon feu vert.
2. Respecte le protocole de travail de la section 1 : c'est moi (Roosevelt) qui pousse sur GitHub
   via VS Code. Donne-moi toujours les commandes exactes (PowerShell, Windows) à exécuter.
3. Avance par petits blocs testés : une fonctionnalité, ses tests, un commit.
   N'avance jamais à l'étape suivante tant que les tests de l'étape courante ne passent pas.
```

---

## 1. Protocole de travail (à respecter dans toute la session)

- Le code est créé ici, mais **c'est Roosevelt qui pousse sur GitHub via VS Code**. Donne toujours les commandes exactes (PowerShell sur Windows : environnement virtuel, installation, migrations, tests, `git add` / `git commit` / `git push`). Ne suppose jamais un push, un déploiement ou une installation automatique.
- **Explore l'existant avant d'écrire du code** : si un dépôt ou des fichiers existent déjà, lis-les et ne suppose rien sur la stack. Sur d'autres projets de Roosevelt, des hypothèses non vérifiées (stack, canal d'envoi) se sont révélées fausses une fois le vrai code lu.
- **Un incrément = une fonctionnalité + ses tests + un commit** avec un message clair. Explique chaque bloc de code important en français simple : Roosevelt doit comprendre ce que fait son produit même s'il ne code pas lui-même.
- **Décisions d'architecture :** consigne chaque décision structurante dans `docs/decisions/NNN-titre.md` (contexte, décision, conséquences). C'est la mémoire du projet.
- **Ne jamais inventer de règle comptable ou fiscale.** Tout ce qui relève du plan de comptes, de la TVA, de la valorisation des stocks ou des écritures doit être **paramétrable** et marqué `TODO(expert-comptable)` dans le code et dans la doc. Le jeu de comptes fourni par défaut est un exemple de démarrage, jamais une référence validée.
- **Aucun secret dans le code source** (clés, mots de passe, jetons) : fichier `.env` non versionné + `.env.example` documenté.
- **Langue :** code et identifiants en anglais (comme dans le modèle de données), interface utilisateur, messages d'erreur et documentation en français. Prévois l'internationalisation dès le départ (fichiers de traduction FR/EN), car le Cameroun est bilingue.

---

## 2. Contexte produit

Application **Windows** de gestion intégrée pour une société exploitant **3 à 5 sites**, avec dépôts et caisses, **6 à 20 utilisateurs simultanés**, qui doit **continuer à fonctionner en cas de coupure Internet**. Chaque site travaille avec une base locale et se synchronise avec un serveur central au retour de la connexion.

Le périmètre initial est : paramétrage, articles, stocks, transferts inter-dépôts, caisses, synchronisation, premières écritures comptables en brouillon. RH, paie et fonctions commerciales avancées sont hors périmètre.

Ce brief reprend le cahier des charges technique v1.0 **et** les corrections issues de son analyse critique (note 5,2/10, « Go avec modifications »). En cas de contradiction entre le cahier des charges v1.0 et ce brief, **ce brief prévaut**.

---

## 3. Décisions d'architecture (v1.1 — à respecter)

### 3.1 Pile technique

| Couche | Choix |
|---|---|
| Langage | Python 3.12 |
| Interface Windows | PySide6 (licence LGPLv3 : lien dynamique, licence incluse, bibliothèque remplaçable) |
| API | FastAPI + Pydantic, HTTPS |
| Base d'un site | SQLite en mode WAL, **un seul processus écrivain** (le nœud de site) |
| Base centrale | PostgreSQL |
| Accès aux données | SQLAlchemy 2.x + Alembic (migrations testées sur **les deux** moteurs) |
| Mots de passe | `argon2-cffi`, Argon2id (au minimum 19 MiB de mémoire, 2 itérations, parallélisme 1) |
| Tests | pytest (+ outils de simulation de réseau et d'horloge, section 9) |
| Qualité | ruff, mypy sur les modules du cœur (sync, stock, compta) |
| Exports | PDF et Excel (bibliothèques à proposer et faire valider) |
| Packaging | PyInstaller ou Nuitka + installeur (Inno Setup ou MSI), signature de code à prévoir |

### 3.2 Topologie : le nœud de site (décision structurante)

- Chaque site possède un **nœud de site** : un PC serveur (alimenté par onduleur) qui exécute un **service FastAPI local** et la base du site.
- Les **postes PySide6 du site sont des clients légers** : pas de base locale propre, ils parlent au service du site par le réseau local.
- **Seul le nœud de site synchronise avec le central.**
- **Interdit** : plusieurs postes ouvrant le même fichier SQLite par partage réseau.
- Le service de site doit pouvoir fonctionner **sans aucune connexion Internet** pendant plusieurs jours.
- Si SQLite devient un frein (montée en charge, migrations), l'alternative documentée est un PostgreSQL local par site. Garde la couche d'accès aux données assez neutre pour permettre ce changement.

### 3.3 Propriété des données (« ownership ») — règle de conflit

| Données | Seul écrivain autorisé |
|---|---|
| Mouvements de stock, transferts (côté expédition), sessions et transactions de caisse d'un site | **Le site propriétaire** |
| Réception d'un transfert | **Le site destinataire** |
| Référentiels : sociétés, sites, dépôts, articles, unités, catégories, comptes, journaux, rôles, utilisateurs | **Le central** |
| Clôture de période, validation comptable | **Le central** |

Conséquence : pas de multi-maîtres sur les documents. La stratégie « dernier écrivain gagne » est **interdite** sur toute donnée comptable ou de stock. Les conflits ne concernent que de rares cas de référentiels, et sont signalés (jamais écrasés silencieusement).

### 3.4 Synchronisation : événements métier immuables

- Le site n'envoie pas « UPDATE de lignes » mais des **événements métier immuables** (ex. `TransferShipped`, `StockMovementValidated`, `CashSessionClosed`), écrits dans l'**outbox dans la même transaction** que la donnée métier.
- Chaque événement porte : `event_id` (UUID), `site_id`, **`site_seq`** (compteur monotone par site, sans trou), `entity_type`, `entity_id`, `version`, `payload_version`, horodatage local.
- Le **central** déduplique (clé unique sur `event_id` et sur `(site_id, site_seq)`), **détecte les trous** de `site_seq` et réclame le renvoi à partir du dernier numéro contigu. L'application des événements est dans l'ordre de `site_seq`.
- Un document = un lot atomique (tout ou rien).
- Le central renvoie un **accusé de réception** ; tant qu'il n'est pas reçu, l'interface n'affiche jamais « consolidé ».
- Descente des référentiels : **inbox côté site** avec curseur de reprise par type de référentiel.
- Échec temporaire : nouvelle tentative avec temporisation progressive ; erreur permanente : visible dans l'écran Synchronisation et signalée à l'administrateur.
- **CRDT et event sourcing intégral : hors sujet** (sur-dimensionnés). Les tables d'état restent, le journal des mouvements fait foi.

### 3.5 Horloges

- **Ne jamais ordonner les événements avec l'horloge murale d'un PC.** Ordre = `site_seq`.
- Conserver trois dates : date métier/comptable (saisie), horodatage local, heure de réception serveur.
- Si l'horloge locale dérive de plus de N minutes (paramétrable, défaut 10) par rapport à la dernière heure serveur connue, **bloquer ou alerter** la saisie.
- Dans le code, passer par une **abstraction d'horloge injectable** (indispensable pour les tests).

### 3.6 Numérotation

- Numéro lisible des transferts : `TRF-<CODE_SITE>-<ANNÉE>-<COMPTEUR_LOCAL>` (ex. `TRF-S02-2026-000001`). L'UUID reste la clé technique. Pas de réservation de plages.
- Numéros de pièces et d'écritures comptables : définitifs **à la validation**, par journal et par site, sans trou (journaux par site, ex. `CAI-S02`).
- Les compteurs locaux sont dans une table dédiée (`site_sequences`) mise à jour dans la même transaction que l'opération.

### 3.7 Types de données

- **Interdit : `float`** pour les montants et quantités.
- Montants : **entiers** dans la plus petite unité de la devise (le FCFA n'a pas de décimales ; table `currencies` avec `decimals`).
- Quantités : `Decimal` avec précision définie par l'unité (`units.decimals`), via un `TypeDecorator` au comportement **identique** sur SQLite et PostgreSQL (test dédié).
- Tous les champs « de synchronisation » du cahier des charges v1.0 restent : `id` (UUID), `company_id`, `site_id`, `created_at`, `updated_at`, `created_by`, `version`, `sync_status`, `deleted_at` si la suppression logique est permise.

---

## 4. Modèle de données

Pars des 22 tables du cahier des charges v1.0 (`companies`, `sites`, `warehouses`, `cash_accounts`, `users`, `roles`/`permissions`, `items`, `units`, `stock_movements`, `transfers`, `transfer_lines`, `cash_sessions`, `cash_transactions`, `cash_transfers`, `accounts`, `journals`, `journal_entries`, `journal_lines`, `cost_centers`, `sync_outbox`, `sync_inbox`, `audit_log`) et **corrige les manques** suivants :

| Ajout / correction | Pourquoi |
|---|---|
| `company_id` sur `accounts`, `journals`, `cost_centers`, etc. | Le multi-sociétés est annoncé mais non modélisé |
| `fiscal_periods` (exercice, période, statut ouvert/clôturé, date de clôture) | La clôture de période est exigée mais sans table |
| `user_role_scopes` (portée : société, site, dépôt, caisse) | Permissions « par site/caisse/dépôt » impossibles sans portée |
| `currencies` (code, decimals) | Précision des montants |
| `journal_lines` : `label`, `source_document_ref` | L'écran Journal affiche libellé et pièce source |
| `cash_transactions` : `cost_center_id`, `account_id` d'imputation | Nécessaire pour générer l'écriture |
| `site_sequences` | Compteurs locaux de numérotation |
| `sync_cursors` | Reprise de la descente des référentiels |
| `partners` (fournisseurs, V1 minimal) + document d'entrée simple | Un coût d'entrée de stock doit être justifié par une pièce |
| `item_costs` (coût moyen courant par article et par société) | Support de la valorisation CMUP |
| `attachments` (métadonnées seulement en V1 : nom, empreinte, taille, lien) | Pièces justificatives ; le stockage de gros fichiers viendra plus tard |
| `stock_locations` ou emplacement logique « en transit » rattaché à un dépôt virtuel | Suivi du transit |
| `audit_log` : colonne `prev_hash` / `hash` | Chaînage anti-altération (section 7) |

Règles inchangées et à faire respecter **par des contraintes en base**, pas seulement par le code : codes uniques (par société/site), mouvements validés non supprimables (corrections par contre-mouvement), écriture validée équilibrée (débit = crédit), débit/crédit non négatifs avec une seule colonne positive par ligne, caisse rattachée à un site, `audit_log` en ajout seul.

Les soldes de stock et de caisse sont calculés depuis les mouvements validés ou maintenus par des agrégats contrôlés ; **les mouvements sources restent la seule preuve**.

---

## 5. Règles métier à implémenter

### 5.1 Stocks
- Entrées, sorties, ajustements autorisés, inventaires, seuils d'alerte, historique.
- **Valorisation : CMUP après chaque entrée, calculé par société** (FIFO reporté). Un site hors ligne valorise provisoirement ses sorties au dernier CMUP connu ; le central recalcule et émet des **écritures d'ajustement** si nécessaire. `TODO(expert-comptable)`.
- Stock négatif : interdit par défaut (contrôle local, le site étant seul écrivain de ses dépôts) ; exception paramétrable et tracée.

### 5.2 Transferts inter-dépôts
- Statuts : Brouillon → Validé → Expédié/en transit → Réception partielle → Réceptionné ; Annulé (jamais d'effacement, contre-mouvement si nécessaire, motif et autorisation obligatoires).
- **Le stock sort du dépôt source à l'expédition** et entre dans un emplacement logique **« en transit »** jusqu'à réception. À la réception, seule la quantité réellement reçue entre ; l'écart est conservé et signalé.
- Interdits : transfert vers le même dépôt, annulation après expédition (passer par un retour), vérification du stock disponible à la validation et à l'expédition.
- **Réception avant synchronisation de l'expédition** (cas réel) : la réception est enregistrée en « attente de rapprochement » et rapprochée automatiquement dès que l'expédition arrive au central. Le bon de transfert imprimé porte l'UUID et un QR code.
- Réception supérieure à la quantité expédiée : règle explicite (blocage ou écart signalé, à paramétrer).

### 5.3 Caisses
- Ouverture/clôture, encaissements, décaissements, transferts entre caisses, solde théorique, comptage physique, écart et justificatif.
- Une caisse ne se clôture pas sans comptage (ou dérogation autorisée et justifiée). **Séparation des tâches** : la clôture n'est pas validée par la personne qui a tenu la caisse sans visa.
- Plafonds, seuil de double validation des dépenses et écart toléré : **paramétrables** (valeurs par défaut à confirmer avec Roosevelt).
- Transfert de caisse à caisse : un seul mouvement lié (sortie + entrée), imputé via un compte de virements internes, jamais comptabilisé deux fois.
- **Alerte** pour tout paiement en espèces de plus de 100 000 FCFA sur un achat taxable (condition de déduction de la TVA). `TODO(expert-comptable)` pour confirmer le seuil en vigueur.

### 5.4 Comptabilité initiale
- Plan de comptes paramétrable (jeu de départ de type SYSCOHADA révisé, marqué « exemple à valider »), journaux, écritures équilibrées, pièce source obligatoire, **brouillon puis validation**.
- **Pour le MVP : les opérations de stock et de caisse génèrent des écritures en brouillon uniquement.** La validation comptable dans l'outil, les états financiers et la clôture complète viennent après le pilote.
- Après validation : **irréversibilité** (pas de modification ni suppression ; correction par inscription en négatif).
- **Période clôturée :** une opération arrivée tardivement avec une date de valeur dans une période close est enregistrée au **premier jour de la première période ouverte**, avec la date de valeur d'origine conservée dans un champ distinct ; elle n'est jamais rejetée. `TODO(expert-comptable)` pour confirmer.
- Fréquence de clôture informatique : au moins **trimestrielle** (paramétrable).
- Livres à pouvoir éditer : livre-journal, grand livre, balance. Prévoir l'**export du fichier des écritures comptables (FEC)** dans un format exploitable ; format exact à confirmer.
- Inventaire permanent ou intermittent : **non tranché**, à faire décider par l'expert-comptable avant de coder la génération d'écritures de stock ; le moteur d'écritures doit être découplé pour supporter les deux.
- TVA (taux normal 19,25 %) paramétrable, exonérations possibles ; prévoir un point d'extension pour une future facturation électronique.

---

## 6. Synchronisation — comportements précis

- Toute opération locale : transaction locale + ligne dans `sync_outbox` (atomique).
- Les envois sont **idempotents** : un même événement reçu N fois produit un seul effet.
- Les opérations qui changent un solde ou un document déjà validé ne sont **jamais fusionnées automatiquement**.
- Écran Synchronisation : à envoyer / en cours / synchronisé / en erreur / conflit, avec relance et détail technique contrôlé.
- Prévoir un **mode dégradé visible** : bandeau « hors ligne depuis X », compteur d'éléments en attente.
- Prévoir la **compatibilité de versions N / N-1** : un site en N-1 hors ligne doit rester utilisable et se resynchroniser après la migration du central.
- Procédure de **reconstruction d'un nœud de site** à partir du central (poste perdu ou endommagé) : à implémenter et à tester, avec liste des opérations non synchronisées perdues.

---

## 7. Sécurité, audit et sauvegardes

- **Authentification :** Argon2id ; verrouillage après N échecs ; durée maximale de validité des droits hors ligne (défaut 72 h, paramétrable) ; compte révoqué au central bloqué à la prochaine synchronisation.
- **Autorisation :** contrôlée **côté API** (jamais seulement dans l'interface), moindre privilège par rôle et par portée (société, site, dépôt, caisse). Compte technique de synchronisation distinct par site.
- **API :** HTTPS, jetons courts avec rotation, validation stricte des charges utiles.
- **Journal d'audit :** ajout seul (déclencheurs refusant `UPDATE`/`DELETE`), **chaîné par hachage** (chaque ligne contient l'empreinte de la précédente), répliqué au central, conservé 10 ans. Toute création, modification, suppression ou annulation d'écriture y figure (utilisateur, horodatage, objet, action).
- **Secrets :** gestionnaire d'identifiants Windows (DPAPI) côté site ; variables protégées côté central.
- **Chiffrement au repos :** BitLocker recommandé sur les nœuds de site ; SQLCipher en option documentée.
- **Sauvegardes :**
  - SQLite : jamais de copie du fichier en cours d'utilisation ; utiliser l'API de sauvegarde en ligne (`sqlite3.Connection.backup`) ou `VACUUM INTO`, puis `PRAGMA integrity_check` sur la copie ; fréquence horaire par défaut ; copie chiffrée envoyée au central.
  - PostgreSQL : sauvegardes planifiées (`pg_dump`), copie indépendante, politique de rétention définie, règle 3-2-1.
  - **Test de restauration documenté** (au moins trimestriel).
- **Données personnelles :** minimiser, tenir un registre des traitements, définir des durées de conservation (la loi camerounaise n° 2024/017 s'applique) ; à faire valider par un juriste.

---

## 8. Écrans (clients PySide6)

Connexion · Tableau de bord · Paramètres · Catalogue articles · Stocks par dépôt · Mouvements de stock · Nouveau transfert · Suivi des transferts · Caisse — ouverture · Saisie caisse · Caisse — clôture · Journal comptable · Synchronisation · Audit.

Règles d'interface : l'écran Connexion affiche l'état de connexion et le dernier succès de synchronisation ; aucune règle de sécurité ne repose sur l'interface seule ; saisie rapide au clavier, messages d'erreur clairs en français. Fournis des maquettes simples (ou captures commentées) pour validation avant de développer chaque groupe d'écrans.

---

## 9. Plan de tests (automatisés d'abord)

Les tests sont des **tests pytest rejouables**, pas seulement des captures. Construis dès l'étape 1 un **banc de simulation** : plusieurs sites en mémoire/processus, réseau coupable à volonté, horloge injectable par site, injection de pannes (arrêt brutal pendant une transaction).

**Tests du cahier des charges (T01–T16)** : connexion valide/invalide ; accès inter-sites refusé et journalisé ; article + entrée de stock ; transfert d'une quantité disponible ; transfert supérieur au stock ; réception partielle ; deux sites créant des transferts hors ligne (aucun doublon) ; coupure Internet puis saisie ; resynchronisation double (aucun double effet) ; conflit sur une même donnée ; ouverture/mouvement/clôture de caisse ; transfert entre caisses ; écriture déséquilibrée refusée ; annulation par contre-mouvement ; restauration d'une sauvegarde ; charge de 6 à 20 utilisateurs simulés.

**Tests ajoutés par l'analyse (T17–T27)** :

| ID | Scénario | Critère |
|---|---|---|
| T17 | Arrêt brutal pendant une validation ou une synchronisation | Base intègre (`integrity_check`), aucune opération à moitié appliquée, reprise automatique |
| T18 | Montée de version du schéma avec des sites en N-1 hors ligne | Sites utilisables, resynchronisation sans perte |
| T19 | Horloge d'un poste décalée de ±2 jours | Saisie bloquée ou alertée ; ordre central correct (via `site_seq`) |
| T20 | Site hors ligne 30 jours, ~5 000 opérations | Synchronisation complète, aucune perte, opérations sur période close reportées selon 5.4 |
| T21 | 50 000 articles, 1 million de mouvements | Consultation de stock < 2 s ; balance < 10 s |
| T22 | Sécurité : injection, rejeu de jeton, élévation de privilège par appel direct à l'API, force brute | Refus, journalisation, verrouillage |
| T23 | `UPDATE` SQL direct sur une écriture validée ou une ligne d'audit | Refus ou détection par la chaîne de hachage |
| T24 | Perte totale d'un nœud de site | Reconstruction depuis le central ; opérations non synchronisées listées |
| T25 | Réception physique avant synchronisation de l'expédition | Réception en attente puis rapprochement automatique |
| T26 | Export FEC et édition livre-journal / grand livre / balance | Totaux concordants ; fichier exploitable |
| T27 | Opération datée d'une période clôturée | Enregistrée au premier jour de la période ouverte, date de valeur conservée |

**Critères chiffrés pour le pilote :** 0 écart entre la somme des mouvements et les soldes ; balance équilibrée à 0 FCFA ; 100 % des événements de l'outbox acquittés ou en erreur visible ; 0 perte et 0 doublon observés ; seuils de performance de T16/T21 respectés (à fixer avec Roosevelt).

Chaque test documenté : résultat obtenu, journaux utiles, date, responsable.

---

## 10. Séquencement (livrable → critère de passage)

Chaque étape se termine par : tests de l'étape verts, migrations validées sur SQLite **et** PostgreSQL, décision(s) consignée(s) dans `docs/decisions`, **commandes git exactes fournies à Roosevelt**.

| Étape | Contenu | Critère de passage |
|---|---|---|
| **0. Cadrage** | Lecture du brief, questions bloquantes, plan détaillé de l'étape 1, schéma de propriété des données | Feu vert de Roosevelt |
| **1. Squelette de bout en bout** | Structure du dépôt, nœud de site, central, outbox/inbox, `site_seq`, **un événement factice synchronisé, acquitté, dédupliqué**, banc de simulation, journal d'audit chaîné | T08, T09 sur l'événement factice ; T17 |
| **2. Socle** | Authentification Argon2id, rôles avec portée, référentiels descendants, migrations, sauvegarde SQLite en ligne, client PySide6 minimal (Connexion, Paramètres) | T01, T02, T15 (sauvegarde de base), T22 partiel |
| **3. Stocks** | Articles, unités, mouvements, soldes, CMUP, seuils | T03, T05 ; invariants de solde |
| **4. Transferts** | Cycle complet, transit, réception partielle et en attente, numérotation | T04, T06, T07, T14, T25 |
| **5. Caisses** | Sessions, mouvements, virements internes, clôture avec comptage | T11, T12 |
| **6. Écritures en brouillon et exports** | Génération depuis stock/caisse, journaux, balance, livre-journal, grand livre, export FEC, PDF/Excel | T13, T26, T27 |
| **7. Durcissement** | Longues coupures, conflits de référentiels, compatibilité N/N-1, reconstruction d'un nœud, performances, sécurité | T10, T16, T18–T24 |
| **8. Packaging et pilote** | Installeur signé, mise à jour avec retour arrière, documentation d'exploitation, installation sur 1 à 2 sites de test | Tous les tests critiques réussis, anomalies bloquantes corrigées |
| **9. Extension (après pilote)** | Déploiement sur les autres sites ; puis validation comptable dans l'outil, états financiers, clôture complète | Formation, procédure de support, validation utilisateur |

Estimation indicative pour un développeur solo assisté par IA : **16 à 22 semaines pour le MVP** (étapes 0 à 8 réduites comme ci-dessus), 32 à 52 semaines pour le périmètre complet. La synchronisation est le risque n° 1 : ne la repousse jamais.

---

## 11. Hors périmètre du MVP (à ne pas construire sans demande explicite)

Validation comptable complète et états financiers dans l'outil · multi-sociétés réel · multi-devises avec écarts de conversion · résolution **interactive** des conflits · valorisation FIFO · ventes, achats complets, clients · RH et paie · facturation électronique · stockage de gros fichiers joints · états analytiques avancés.

---

## 12. Garde-fous

- Ne **jamais** supprimer une donnée validée ; contre-mouvement ou annulation traçable uniquement.
- Ne **jamais** afficher une opération comme consolidée sans accusé de réception du central.
- Ne **jamais** activer de comportement réglementaire (validation comptable, clôture) sans la validation de l'expert-comptable ; le code doit pouvoir l'activer par paramètre une fois validé.
- Ne **jamais** résoudre un conflit sur un solde ou un document validé par fusion automatique.
- Si une instruction de ce brief semble contradictoire ou dangereuse, **dis-le avant de coder** plutôt que de choisir silencieusement.

---

## 13. Livrables attendus à chaque étape

1. Code + tests + migrations.
2. Mise à jour de `docs/decisions/` et d'un `README.md` (installation, lancement, tests).
3. Résumé en 5 lignes maximum : ce qui marche, ce qui reste, risques.
4. Les **commandes exactes** à exécuter (venv, installation, migrations, tests, git).

---

## 14. Questions à poser à Roosevelt (avant l'étape 1, et seulement si elles se posent)

1. Ce logiciel est-il un **produit pour Baobab Labs** ou un projet **pour un client précis** ? (propriété du code, licence, maintenance, responsabilité réglementaire)
2. **Statut juridique de l'entité** utilisatrice et référentiel comptable : SYSCOHADA système normal ou système minimal de trésorerie ? Un expert-comptable est-il identifié ?
3. **Nom exact et URL du dépôt GitHub** à utiliser (ou création d'un nouveau dépôt).
4. Nombre réel de sites, utilisateurs par site, qualité de la connexion, **durée maximale de coupure** à tenir, matériel disponible pour les nœuds de site (PC, onduleur).
5. **Hébergement du serveur central** (VPS ou cloud avec sauvegarde, plutôt qu'un site principal sujet aux coupures de courant).
6. **Rôles, sites et opérations autorisées** par profil (matrice rôles × sites × opérations).
7. **Politique de caisse :** plafonds, seuil de double validation, écart toléré, droit de clôture.
8. **Reprise de données initiale :** y a-t-il des articles, soldes de stock et de caisse à importer ? Format source ?
9. Inventaire **permanent ou intermittent** (à trancher avec l'expert-comptable avant l'étape 6).
