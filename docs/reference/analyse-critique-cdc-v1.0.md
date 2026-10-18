# Analyse critique du cahier des charges « Prototype de gestion comptable intégré multi-sites » (v1.0)

**Verdict : le document est un bon point de départ, au-dessus de la moyenne en contrôle interne, mais il n'est pas encore une base sûre pour coder. Note globale : 5,2/10. Recommandation : Go avec modifications.** Trois corrections sont nécessaires avant toute ligne de code : (1) placer la synchronisation au cœur de l'architecture dès l'étape 2, et non à l'étape 6 ; (2) adopter un modèle de « propriété » des données par site ; (3) intégrer les exigences camerounaises de 2026 sur la piste d'audit informatique.

## TL;DR

- **Points forts :** contrôles métier solides (contre-mouvements, transferts liés, idempotence, verrouillage des périodes, transit) et architecture « outbox/inbox + UUID » conforme aux patterns éprouvés.
- **Faiblesses :**
  - le planning place la synchronisation à l'étape 6, alors que le test T07 (hors ligne) doit être réussi dès l'étape 3 ;
  - le modèle de données ignore les tiers, les achats et ventes, la TVA (19,25 %), les périodes, le multi-sociétés et les pièces jointes ;
  - le document ne décide pas si la base SQLite est par poste ou par site, ce qui détermine tout le risque de stock négatif et de conflits.
- **Effort estimé :** 32 à 52 semaines pour un développeur solo assisté par IA sur le périmètre complet, soit 8 à 12 mois avant un pilote robuste.
  - Un MVP réaliste (1 société, 2 sites, stocks + transferts + caisse + écritures en brouillon + synchronisation) est atteignable en 16 à 22 semaines si l'on coupe la comptabilité validée, les états et les conflits multi-maîtres.
  - Si le besoin est standard, comparer sérieusement avec Odoo Community + localisation l10n_cm ou une solution locale avant de construire.

---

## 1. Synthèse du document

**Objectif.** Le document décrit une application Windows de gestion intégrée pour 3 à 5 sites et 6 à 20 utilisateurs simultanés. Elle doit continuer à fonctionner pendant les coupures Internet, avec une base locale par site synchronisée avec un serveur central au retour de la connexion.

**Périmètre V1 :**
- paramétrage ;
- articles et stocks ;
- transferts inter-dépôts ;
- caisses ;
- synchronisation ;
- premières écritures comptables.

La RH, la paie et les fonctions commerciales avancées sont reportées.

**Modules (7) :** Paramétrage, Stocks, Transferts, Caisses, Comptabilité initiale, Synchronisation, Administration.

**Architecture :**
- client lourd Python + PySide6 ;
- SQLite par site ;
- PostgreSQL central ;
- API FastAPI en HTTPS ;
- SQLAlchemy avec migrations versionnées ;
- exports PDF et Excel ;
- synchronisation applicative par file d'envoi (outbox) et déduplication à la réception (inbox), avec clés UUID générées localement.

**Livrables de pilotage :**
- 22 tables décrites ;
- 14 écrans ;
- 16 tests d'acceptation (T01–T16) ;
- 8 étapes de réalisation ;
- 7 points à trancher (section 13) ;
- critères de réception d'un pilote limité.

Le document est lucide sur son statut (« pas encore développé ni testé ») et sur la nécessité d'une validation par un professionnel comptable. C'est un signe de maturité.

## 2. Points forts

1. **Contrôle interne pensé dès la conception :**
   - mouvements validés non supprimables et corrections par contre-mouvement ;
   - annulation avec motif et autorisation ;
   - clôture de caisse impossible sans comptage ou dérogation justifiée ;
   - transferts de caisse liés.

   Ces règles correspondent directement à l'article 20 de l'AUDCIF, qui impose que les livres soient « tenus sans blanc ni altération d'aucune sorte » et que toute correction s'effectue « exclusivement par inscription en négatif des éléments erronés ». [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf)
2. **Cycle de transfert réaliste :** les quantités expédiées et reçues sont distinctes, la réception peut être partielle, les écarts sont tracés, et un emplacement logique « en transit » est prévu avec sortie du stock à l'expédition. C'est la bonne recommandation.
3. **Synchronisation fondée sur un pattern reconnu.** Le document combine :
   - l'inscription dans l'outbox dans la même transaction que la donnée métier ;
   - l'envoi idempotent ;
   - la conservation par le serveur des identifiants déjà traités ;
   - un accusé de réception obligatoire avant d'afficher « consolidé ».

   C'est exactement le « Transactional outbox » décrit par Chris Richardson (microservices.io). Ce pattern garantit que les messages sont émis si et seulement si la transaction est validée, mais impose un consommateur idempotent « by tracking the IDs of the messages that it has already processed ». [microservices](https://microservices.io/patterns/data/transactional-outbox.html) Le document l'a compris.
4. **Règle explicite interdisant SQLite sur lecteur réseau.** Elle est juste : la documentation SQLite (« How To Corrupt An SQLite Database File ») recense les problèmes de verrouillage des systèmes de fichiers réseau comme cause de corruption, et le mode WAL ne fonctionne pas sur un système de fichiers réseau. [sqlite](https://sqlite.org/howtocorrupt.html?s=09) [kunalganglani](https://www.kunalganglani.com/blog/single-file-web-app-sqlite)
5. **Sécurité de principe correcte :**
   - contrôle des droits côté API et non seulement dans l'interface ;
   - secrets hors du code ;
   - comptes nominatifs ;
   - restauration testée ;
   - journal d'audit append-only.
6. **Honnêteté réglementaire :** le SYSCOHADA est « envisagé sous réserve », et la réception du prototype « ne vaut pas validation réglementaire ».
7. **Tests orientés risques :** T07, T09, T10 et T16 visent précisément les scénarios où les systèmes hors ligne échouent (doublons, double effet, conflits, charge).

## 3. Lacunes, ambiguïtés et contradictions

### 3.1 Contradictions internes (à corriger en priorité)

| # | Contradiction | Conséquence |
|---|---|---|
| C1 | Le test T07 (« deux sites créent des transferts hors ligne ») conditionne la fin de l'étape 3, mais la synchronisation n'est construite qu'à l'étape 6. | Impossible à tenir. Ajouter la synchronisation après coup oblige à réécrire le modèle de données. |
| C2 | Le § 2 dit que les utilisateurs d'un site « accèdent à un service local ou au serveur central », mais le document ne précise pas si SQLite est installé sur chaque poste ou sur un serveur de site. | Si la base est par poste, chaque PC devient un maître autonome, et le risque de stock négatif et de conflits explose. |
| C3 | Le stock disponible est « vérifié au moment de la validation », mais il ne sort qu'à l'expédition, et la « réservation éventuelle » n'est pas décidée. | Entre validation et expédition, une autre sortie peut consommer le même stock. |
| C4 | Le transfert a un « numéro unique global », mais deux méthodes sont laissées ouvertes : « plage réservée » ou « code site + compteur ». | Il faut en choisir une, car le format et les tests en dépendent. |
| C5 | Les journaux ont des « codes uniques par société », alors que les tables `accounts` et `journals` n'ont pas de `company_id`. Les comptes n'ont pas de rattachement à une société. | Le multi-sociétés est annoncé (§ 3.1) mais non modélisé. |
| C6 | L'écran Journal affiche un libellé et une pièce source, alors que `journal_lines` n'a ni libellé ni référence de pièce. | Écart entre les écrans et le modèle de données. |
| C7 | La « clôture de période » est exigée (§ 3.7, § 6), mais il n'existe aucune table de périodes ou d'exercices comptables. | La règle de verrouillage est inapplicable telle quelle. |
| C8 | La saisie de caisse prévoit un « centre analytique éventuel », mais `cash_transactions` n'a ni `cost_center_id` ni compte d'imputation. | Impossible de générer l'écriture comptable automatiquement. |
| C9 | Les permissions sont prévues « par rôle, société, site, caisse et dépôt » (§ 11), mais le schéma `user_roles` n'a pas de portée (scope). | Le test T02 n'est pas réalisable proprement. |

### 3.2 Manques fonctionnels

- **Tiers et flux commerciaux :**
  - il n'existe ni fournisseurs, ni clients, ni achats, ni ventes ;
  - d'où viennent les entrées de stock et leur `unit_cost` ? Où partent les sorties ?
  - sans pièce d'origine, le coût d'entrée n'est pas justifiable. Or l'AUDCIF exige « la justification des écritures par des pièces datées » (art. 17). [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf)
- **TVA :** totalement absente. Au Cameroun, le taux normal est de 19,25 % (17,5 % en principal majoré de 10 % de centimes additionnels communaux). [lefisk +2](https://lefisk.cm/fiscalite/tva) Il faut aussi prévoir :
  - les exonérations et le taux zéro à l'export ; [lefisk](https://lefisk.cm/fiscalite/tva)
  - le précompte et la retenue à la source pour les clients habilités : l'arrêté MINFI/DGI n°00001 du 5 janvier 2026 liste ces entités pour 2026 ; [impots](https://www.impots.cm/sites/default/files/documents/arr%C3%AAt%C3%A9%20RTS%202026%20VF.pdf) [lefisk](https://lefisk.cm/blog/liste-entreprises-habilitees-retenue-source-cameroun)
  - la règle de non-déductibilité de la TVA en cas de paiement en espèces : le dépliant TVA de la DGI (impots.cm) pose comme condition de déduction de « ne pas avoir payé en espèces au-delà de 100 000 FCFA ». Elle concerne directement le module Caisse.
- **Devises :**
  - le champ `currency` existe, mais il n'y a ni taux de change, ni écarts de conversion, ni règle d'arrondi ;
  - le FCFA (XAF) s'utilise sans décimales ;
  - l'AUDCIF impose la tenue dans « l'unité monétaire ayant cours légal ». [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf)
- **Valorisation des stocks :**
  - le champ `stock_method` existe, mais rien n'est prévu pour stocker le coût moyen courant ou les couches FIFO ;
  - rien n'est dit sur le traitement d'un mouvement antidaté qui recalcule le CMUP ;
  - rien n'est dit sur l'inventaire permanent ou intermittent.
- **Pièces justificatives :** pas de table de pièces jointes (scan, PDF), pas de stockage, et pas de synchronisation de fichiers volumineux sur des liens lents.
- **Reprise initiale :** rien n'est prévu pour l'import des articles, des soldes d'ouverture de stock, de caisse et des comptes, du plan comptable, ni pour un inventaire de démarrage.
- **Import/export :** le document mentionne PDF et Excel, mais pas l'export du fichier des écritures comptables exigé en cas de contrôle (voir § 6).
- **Langue :** l'AUDCIF impose la tenue dans « la langue officielle ». [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf) Le Cameroun est bilingue : faut-il prévoir le FR/EN ?
- **Impression :** pas de bons de livraison ou de transfert imprimés, pas de reçus de caisse, pas de lecture de codes-barres.

### 3.3 Exigences non fonctionnelles absentes

- **Volumétrie :** nombre d'articles, de mouvements par jour, de lignes par transfert, historique sur 10 ans.
- **Performance :** temps de réponse cibles pour T16 (« performances acceptées », sans seuil chiffré).
- **Objectifs de reprise après incident :**
  - perte de données maximale tolérable (RPO) par site ;
  - durée maximale d'interruption (RTO) ;
  - durée maximale hors ligne (renvoyée à la section 13 mais non chiffrée).
- **Environnement :** versions de Windows, matériel minimal, onduleur, bande passante.
- **Exploitation :**
  - déploiement et mise à jour des postes (installeur, mise à jour automatique, compatibilité entre versions de client et de serveur pendant une migration) ;
  - supervision ;
  - support (niveaux de service, astreinte) ;
  - licence du logiciel (propriété du code si projet client).
- **UX :** maquettes non jointes, alors que l'étape 1 les exige ; pas de règles de saisie rapide ni de mode dégradé visible.

## 4. Revue technique de l'architecture

### 4.1 Le choix des composants : solide mais à préciser

| Composant | Avis | Points d'attention |
|---|---|---|
| Python + PySide6 | Réaliste pour un développeur solo ; la licence LGPLv3 permet une application propriétaire. [pythonguis](https://www.pythonguis.com/faq/not-an-open-source-application-which-one-to-use-pyqt5-or-pyside2/) | L'application doit lier PySide6 dynamiquement, inclure la licence LGPL et permettre son remplacement. [pythonguis](https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/) Les exécutables PyInstaller ou Nuitka déclenchent des faux positifs antivirus (l'issue GitHub #8164 de PyInstaller rapporte que « Somewhere between 15-18 AV vendors (mostly low-tier, but also including McAfee and Bitdefender…) flag my executable as malware ») : prévoir la signature de code et un installeur (Inno Setup, MSI). |
| SQLite local | Bon pour un stockage embarqué à un seul écrivain. | Il doit être utilisé par **un seul processus** (le service de site) en mode WAL. Jamais par plusieurs PC. [sqlite](https://sqlite.org/howtocorrupt.html?s=09) |
| PostgreSQL central | Choix standard et adapté. | Aucun. |
| FastAPI + HTTPS | Adapté. | Utiliser des jetons courts avec rotation, un TLS épinglé côté client, et valider les charges utiles. |
| SQLAlchemy + migrations (Alembic) | Indispensable. | Deux dialectes (SQLite et PostgreSQL) donnent deux comportements : types décimaux, contraintes, `ALTER TABLE` limités sous SQLite. Les migrations doivent être testées sur les deux. |

### 4.2 La décision structurante que le document n'a pas prise : la topologie par site

**Recommandation forte :** chaque site dispose d'un **nœud de site**, c'est-à-dire un mini-PC serveur alimenté par onduleur, qui exécute un service FastAPI local et la base du site. Les postes PySide6 du site parlent à ce service par le réseau local. Seul le nœud de site synchronise avec le central.

Ce choix :
- respecte la règle « pas de SQLite sur lecteur réseau » ;
- fait de chaque site un **écrivain unique** pour ses dépôts et ses caisses ;
- élimine la quasi-totalité des conflits.

Avec 6 à 20 utilisateurs répartis sur 3 à 5 sites, on compte environ 2 à 6 utilisateurs par site. SQLite en WAL derrière un seul processus suffit. Si l'on veut plus de marge, un PostgreSQL local par site est une option crédible : même moteur partout, des migrations uniques, de vraies contraintes et des sauvegardes `pg_dump`, au prix d'une installation plus lourde.

### 4.3 Robustesse de la synchronisation : points à durcir

1. **Propriété des données (« ownership »), à écrire noir sur blanc :**
   - les dépôts, caisses, sessions et mouvements ne sont écrits que par le site propriétaire ;
   - les référentiels (articles, comptes, rôles, utilisateurs) ne sont écrits que par le central ;
   - les clôtures de période sont décidées uniquement par le central.

   Avec ce modèle, T10 (« modifier la même donnée sur deux sites ») ne concerne plus que de rares cas, et la stratégie « dernier écrivain gagne » n'est jamais appliquée à des données comptables.
2. **Événements métier immuables plutôt que réplication de lignes.** Envoyer « TransferShipped {lignes, coûts} » plutôt que « UPDATE transfers SET status… ».
   - C'est un *event sourcing léger* : on garde des tables d'état, mais le journal des mouvements fait foi.
   - Le CRDT est **sur-dimensionné et inadapté** : il garantit la convergence, pas des invariants comme « stock ≥ 0 » ou « débit = crédit ».
   - L'event sourcing complet (reconstruire tout l'état par rejeu) est aussi excessif pour un développeur solo.
3. **Ordre et complétude :**
   - ajouter un **numéro de séquence monotone par site** (`site_seq`) à chaque événement, pour que le central détecte les trous et applique les événements dans l'ordre ;
   - prévoir des lots atomiques (un document égale un lot) ;
   - versionner le schéma de la charge utile (`payload_version`) ;
   - prévoir une inbox **aussi côté site**, pour les référentiels descendants, avec un curseur de reprise.
4. **Horloges :**
   - ne jamais ordonner les événements avec l'horloge murale d'un PC ;
   - conserver trois dates : la date métier ou comptable (saisie), l'horodatage local, et l'heure de réception serveur ;
   - pour l'ordre causal, utiliser `site_seq`, ou une horloge logique hybride (HLC) si plusieurs écrivains existent. Une HLC combine temps physique et compteur logique, et elle préserve la causalité même quand les horloges divergent ; [medium](https://medium.com/@armironenko/distributed-systems-logical-time-explained-5f97949f180f)
   - bloquer la saisie si l'horloge locale dérive de plus de X minutes par rapport à la dernière heure serveur connue. Ce cas doit faire l'objet d'un test.
5. **Stock négatif hors ligne.** Avec un écrivain unique par dépôt, le contrôle local fait autorité : aucun risque lié à la concurrence entre sites. Le risque restant est opérationnel :
   - une réception physique arrive avant que le document d'expédition ait été synchronisé.

   Solution : prévoir une « réception sur bordereau en attente », rapprochée à la synchronisation, ou faire circuler le bon de transfert imprimé avec son UUID et un QR code.
6. **Transferts inter-dépôts concurrents.** L'expédition est écrite par le site source et la réception par le site destination : ce sont deux événements distincts, donc sans conflit. Il faut des règles explicites pour trois cas :
   - annulation après expédition (interdite : passer par un retour) ;
   - réception supérieure à l'expédié ;
   - transfert intra-site (sans transit).
7. **Clôtures de période et synchronisation.** Un site resté hors ligne peut envoyer des opérations datées d'une période déjà clôturée au central. L'AUDCIF (art. 22, 4°) donne la règle : « lorsque la date de valeur comptable correspond à une période déjà clôturée, l'opération concernée est enregistrée au premier jour de la période non encore clôturée », avec mention distincte de la date de valeur. [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf) **Il faut implémenter exactement cela**, et ne pas rejeter ces opérations.
8. **Numérotation :**
   - adopter le format « préfixe site + compteur local », plus simple qu'une réservation de plages ;
   - pour la comptabilité, définir des journaux par site (par ex. `CAI-S02`) et attribuer le numéro définitif **à la validation**, pour garantir une chronologie sans trou par journal.
9. **Alternative « prête à l'emploi » :** SymmetricDS synchronise SQLite et PostgreSQL avec détection de conflits. Mais, selon le guide utilisateur SymmetricDS 3.15, « without any overriding configuration, the system uses a detection of USE_CHANGED_DATA and a resolution of NEWER_WINS by default » (le plus récent gagne), ce qui est dangereux pour des données comptables, et il faut une JVM sur chaque site. C'est une option à considérer pour les référentiels, pas pour les documents validés.

### 4.4 Sauvegarde, chiffrement et packaging

- **Sauvegarde SQLite :** ne jamais copier le fichier pendant l'exécution. Utiliser l'API Online Backup (`Connection.backup` en Python) ou `VACUUM INTO`. [oneuptime](https://oneuptime.com/blog/post/2026-09-08-back-up-wal-mode-sqlite-safely/view) [comcomponent](https://comcomponent.com/en/blog/csharp-sqlite-practical-guide/)
  - En mode WAL, le fichier principal seul ne contient pas les dernières transactions validées. [comcomponent](https://comcomponent.com/en/blog/csharp-sqlite-practical-guide/)
  - Lancer `PRAGMA integrity_check` sur la copie.
  - Garder une copie hors site, par exemple chiffrée vers le central.
- **Chiffrement au repos :**
  - BitLocker sur le nœud de site, au minimum ;
  - ou SQLCipher (AES-256, édition communautaire sous licence BSD) ; [charlesleifer](https://charlesleifer.com/blog/encrypted-sqlite-databases-with-python-and-sqlcipher/)
  - SQLAlchemy dispose d'un dialecte `pysqlcipher`. [sqlite](https://blog.sqlite.ai/sqlite-python-sqlalchemy)

  Le document ne mentionne pas le chiffrement, alors qu'un PC volé contient la comptabilité et les données personnelles.
- **Packaging et mise à jour :**
  - installeur signé ;
  - mise à jour automatique avec compatibilité N/N-1 entre client et serveur ;
  - migrations exécutées par le nœud de site avant de servir les clients ;
  - possibilité de revenir en arrière (rollback).

  Rien de tout cela n'est spécifié.

## 5. Revue métier et comptable

### 5.1 Applicabilité du référentiel

L'AUDCIF, adopté le 26 janvier 2017 et applicable aux comptes personnels depuis le 1er janvier 2018, fait du SYSCOHADA révisé le référentiel des entités commerciales du Cameroun. [ohada +2](https://www.ohada.com/actualite/3349/publication-du-nouvel-acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere-audcif.html) Deux exceptions à vérifier :
- les établissements de crédit, de microfinance, d'assurance et les entités à but non lucratif sont exclus du SYSCOHADA (art. 5) ; [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf)
- les petites entités relèvent du **Système minimal de trésorerie (SMT)** sous des seuils de chiffre d'affaires hors taxes : 60 millions FCFA pour le négoce, 40 millions pour l'artisanat, 30 millions pour les services (art. 13). [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf)

Le statut de l'entité doit donc être tranché d'abord (point 1 de la section 13).

### 5.2 Ce que l'AUDCIF impose au logiciel (art. 17, 19, 20, 22, 24)

- **Partie double :** chaque écriture affecte au moins deux comptes et respecte total débit = total crédit. [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf) La règle T13 est conforme.
- **Livres obligatoires** (art. 19) : livre-journal, grand-livre, balance générale et livre d'inventaire. [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf) Le document prévoit le grand livre et la balance, mais **oublie le livre-journal centralisé et le livre d'inventaire**.
- **Irréversibilité** (art. 22, 2°) : « l'irréversibilité des traitements effectués interdise toute suppression, addition ou modification ultérieure d'enregistrement ». La validation doit intervenir périodiquement. [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf)
- **Clôture informatique** (art. 22, 3°) : une « procédure périodique dite "clôture informatique" au moins trimestrielle », au plus tard à la fin du trimestre suivant. [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf) Le document parle de « clôture de période » sans fréquence : **il faut l'écrire**.
- **Chemin de révision** (art. 22, 6°) : il doit pouvoir être reconstitué, et la documentation des traitements doit être accessible. [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf) La pièce source doit être reliée à l'écriture, ce que le document prévoit.
- **Conservation :** 10 ans pour les livres et les pièces (art. 24). [naturaljustice](https://naturaljustice.org/wp-content/uploads/2022/04/Acte-uniforme-relatif-au-droit-comptable-et-a-linformation-financiere.pdf) Il faut un archivage lisible indépendamment du logiciel. [arapl](https://www.arapl.org/utilisation-dun-logiciel-de-comptabilite/)
- **Brouillon et validation :** l'approche « pièces en brouillon, validation après vérification » est conforme. Mais le brouillon ne doit pas rester indéfiniment : il faut un délai maximal avant la clôture informatique.

### 5.3 Valorisation et cohérence stock / compta

- Le SYSCOHADA révisé autorise le **CMUP et le PEPS (FIFO)** pour les biens interchangeables. Le **DEPS (LIFO) est interdit**. L'art. 44 impose la même méthode pour des stocks de nature et d'usage similaires. [revue-isg](https://revue-isg.com/index.php/home/article/download/1452/1166/5095) [msg-innov](https://www.msg-innov.online/gallery/ACTE%20UNIFORME%20SYSCOHADA%20REVISE.pdf)
  - **Recommandation V1 : CMUP « après chaque entrée », par société** (et non par dépôt, sauf avis contraire de l'expert-comptable). C'est plus simple et plus robuste hors ligne que le FIFO.
  - Problème : un site hors ligne qui reçoit un achat modifie le CMUP vu par les autres. Il faut un CMUP calculé par le central et des sorties valorisées provisoirement au dernier CMUP connu, avec écriture d'ajustement. **À valider par l'expert-comptable.**
- **Inventaire permanent ou intermittent :** générer une écriture à chaque mouvement suppose un inventaire permanent comptable. En pratique SYSCOHADA, le compte 31 est souvent ajusté à l'inventaire via la variation de stock (6031). [plan-comptable-ohada](https://plan-comptable-ohada.com/nouvelle-norme-2016/plan-comptable-syscohada.html) [kiboerp](https://kiboerp.com/ressources/plan-comptable-syscohada) Choisir l'une des deux approches détermine tout le module de génération d'écritures.
- **Transit :** pour un transfert entre dépôts **d'une même société**, il n'y a pas de changement de propriétaire. Le « transit » peut rester un emplacement logistique, avec au besoin un suivi analytique, sans écriture en comptabilité générale.
  - Le plan SYSCOHADA comporte un compte 38 « stocks en cours de route ». [kiboerp](https://kiboerp.com/ressources/plan-comptable-syscohada) Son usage pour des transferts internes doit être **validé par l'expert-comptable**.
  - Entre deux sociétés du groupe, c'est une vente/achat interne avec TVA.
- **Caisse :**
  - comptes 57 (caisse) ;
  - virements internes entre caisses via un compte de virements de fonds (classe 58), ce qui garantit l'absence de double comptabilisation (T12) ;
  - écarts de caisse vers des comptes de charges ou produits divers, avec plafond de tolérance.

  **Plan d'imputation à faire valider.**
- **Paiements en espèces :** prévoir une alerte au-delà de 100 000 FCFA payés en espèces sur un achat taxable, car le dépliant TVA de la DGI (impots.cm) exige de « ne pas avoir payé en espèces au-delà de 100 000 FCFA » pour déduire la TVA.

### 5.4 Nouvelles exigences fiscales camerounaises (loi de finances 2026)

La loi n° 2025/012, signée le 17 décembre 2025 selon Bloomberg Tax (« The Cameroonian President Dec. 17, 2025, signed Law No. 2025/012, the 2026 Finance Law »), renforce les obligations sur les comptabilités informatisées.

- **Article L 19 (2) du CGI :**
  - remise du fichier des écritures comptables (FEC) sous forme dématérialisée exploitable dès le début d'une vérification ; [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf)
  - interdiction de toute modification ensuite. [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf)

  Selon la rédaction du projet de loi, « les systèmes comptables doivent conserver un journal technique d'audit (logs) non altérable retraçant toute création, modification ou suppression d'écritures, avec horodatage et identifiant utilisateur », pendant au moins 10 ans. [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf) Deloitte confirme l'adoption de l'obligation de remise du FEC et de conservation sur 10 ans. [deloitte](https://blog.avocats.deloitte.fr/cameroun-les-principales-innovations-de-la-loi-de-finances-pour-2026/) [deloitte](https://blog.avocats.deloitte.fr/cameroun-les-principales-innovations-de-la-loi-de-finances-pour-2026/)
- **Article L 30 bis :** il permet le rejet d'une comptabilité informatisée en cas d'altération des écritures ou d'« entrave à l'audit informatique ». [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf) [bstp-cameroun](https://bstp-cameroun.cm/assets/files/articlefile/125-0.pdf)
- **Article L 8 bis :** il impose un suivi électronique de la facturation par l'administration fiscale. [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf) [impots](https://www.impots.cm/fr/actualites/code-general-des-impots-mis-jour-au-1er-janvier-2023)
- **Article L 8 sexies :** il crée un régime de « taxation en temps réel » avec dispositifs « agréés par l'administration fiscale ». [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf) Ce régime vise « certaines opérations » définies par arrêté, et non toutes les entreprises. [bstp-cameroun](https://bstp-cameroun.cm/assets/files/articlefile/125-0.pdf) [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf)

Je n'ai trouvé **aucune homologation générale des logiciels de comptabilité** par la DGI camerounaise. En revanche, les charges justifiées par des factures émises hors du système de suivi électronique sont non déductibles (CGI 2024, art. 8 bis). [impots](https://www.impots.cm/sites/default/files/documents/CGI%202024%20version%20francaise.pdf)

**Conséquences pour le cahier des charges :**
- **Export FEC obligatoire** dans le périmètre.
- **Journal d'audit technique horodaté, non altérable et conservé 10 ans** : chaînage par hachage, et réplication vers le central.
- **Prévoir une interface future** avec la facturation électronique de la DGI dès qu'il y aura des ventes.

**À faire confirmer par l'expert-comptable ou le conseil fiscal :** le texte promulgué de la loi et les arrêtés d'application, qui n'ont pas été vérifiés mot à mot.

## 6. Sécurité et conformité

- **Mots de passe :**
  - imposer **Argon2id** avec au minimum 19 MiB de mémoire, 2 itérations et un parallélisme de 1, conformément à l'OWASP Password Storage Cheat Sheet (« Use Argon2id with a minimum configuration of 19 MiB of memory, an iteration count of 2, and 1 degree of parallelism »), via la bibliothèque `argon2-cffi` ;
  - à défaut, bcrypt avec un facteur de coût d'au moins 10 (l'OWASP le réserve aux « legacy systems », avec une limite de 72 octets par mot de passe).

  Le document dit seulement « algorithme adapté » : à préciser.
- **Authentification hors ligne :**
  - le nœud de site doit garder une copie des empreintes de mots de passe, ce qui expose à une attaque hors ligne en cas de vol ;
  - un compte révoqué au central reste actif sur un site déconnecté jusqu'à la prochaine synchronisation.

  Il faut donc :
  - une durée maximale de validité des droits hors ligne, par exemple 72 h ;
  - un verrouillage après N échecs ;
  - le chiffrement du disque.
- **Moindre privilège :**
  - permissions avec portée (société, site, dépôt, caisse) ;
  - séparation des tâches : le caissier ne clôture pas sa propre caisse sans contrôle, l'auteur d'une écriture ne la valide pas ;
  - compte technique de synchronisation distinct, avec certificat par site.
- **Journal d'audit append-only :**
  - interdire UPDATE et DELETE par déclencheur ;
  - chaîner les entrées par hachage (chaque ligne contient le hash de la précédente) ;
  - répliquer au central ;
  - conserver 10 ans (exigence L 19 ci-dessus).
- **Secrets :**
  - stockage via le gestionnaire d'identifiants Windows (DPAPI) côté site, et un coffre ou des variables protégées côté serveur ;
  - rotation des jetons ;
  - TLS de bout en bout.
- **Sauvegardes :**
  - règle 3-2-1 ;
  - chiffrement des copies ;
  - test de restauration trimestriel ;
  - procédure de reconstruction d'un nœud de site à partir du central (la plus utile en pratique).
- **Données personnelles :**
  - la loi n° 2024/017 du 23 décembre 2024 encadre désormais les traitements au Cameroun ; [labase-lextenso](https://www.labase-lextenso.fr/l-essentiel-droits-africains-des-affaires/2025-n2/cameroun-adoption-d-une-loi-dediee-a-la-protection-des-donnees-a-caractere-personnel-DAA202v2)
  - elle prévoit un régime d'autorisation préalable auprès de l'autorité de protection, des droits des personnes et des notifications de violation ; [anove](https://www.anove.ai/fr/regulations/cameroon-law-2024-017) [taxafrica](https://taxafrica.cm/loi-n2024-017-un-nouveau-cadre-pour-la-protection-des-donnees-personnelles-au-cameroun/)
  - une période transitoire de 18 mois est prévue (art. 73). [anove](https://www.anove.ai/fr/regulations/cameroon-law-2024-017)

  Même sans paie, le logiciel traite des données d'employés (utilisateurs, journaux d'audit) et bientôt de clients.

  À prévoir :
  - un registre des traitements ; [obs-cc](https://obs-cc.org/gouvernance/protection-donnees-personelles/)
  - une minimisation des données ;
  - des durées de conservation ;
  - l'encadrement des transferts si le serveur central est hébergé hors du Cameroun.

  **À faire valider par un juriste**, notamment l'état d'installation de l'autorité et les décrets d'application.

## 7. Plan de tests d'acceptation

**Couverture actuelle :** bonne sur le cœur métier et la synchronisation de base. Environ 60 % des risques majeurs sont couverts.

**Tests manquants recommandés :**

| Nouveau test | Scénario | Critère de réception |
|---|---|---|
| T17 | Coupure de courant pendant une validation ou une synchronisation (arrêt brutal du processus) | Base intègre (`integrity_check`), aucune opération à moitié appliquée, reprise automatique |
| T18 | Montée de version du schéma avec des sites en N-1 hors ligne | Les sites en N-1 restent utilisables ; la synchronisation reprend après migration ; pas de perte |
| T19 | Horloge d'un poste décalée de +/- 2 jours | Saisie bloquée ou alertée ; ordre des événements correct côté central |
| T20 | Site hors ligne 30 jours avec environ 5 000 opérations | Synchronisation complète en moins de X minutes ; aucune perte ; opérations sur période clôturée reportées selon l'art. 22 |
| T21 | Volumétrie : 50 000 articles et 1 million de mouvements | Consultation du stock en moins de 2 s ; balance en moins de 10 s |
| T22 | Sécurité : injection, rejeu d'un jeton volé, élévation de privilège par l'API directe, force brute | Refus et journalisation ; verrouillage du compte |
| T23 | Tentative de modification directe de la base (UPDATE SQL sur une écriture validée ou une ligne d'audit) | Détection par la chaîne de hachage ; alerte |
| T24 | Perte totale d'un nœud de site | Reconstruction depuis le central en moins de X heures, avec perte limitée aux opérations non synchronisées, qui sont listées |
| T25 | Réception physique avant synchronisation de l'expédition | Réception en attente, rapprochement automatique |
| T26 | Export FEC et édition livre-journal / grand-livre / balance sur un exercice | Totaux concordants ; format exploitable |
| T27 | Opération datée d'une période clôturée | Enregistrement au premier jour de la période ouverte, avec mention de la date de valeur |

**Critères de réception à chiffrer :**
- seuils de performance (T16 dit seulement « acceptées ») ;
- 0 écart entre la somme des mouvements et les soldes ;
- balance équilibrée à 0 FCFA ;
- 100 % des événements de l'outbox acquittés ou en erreur visible ;
- tests automatisés (pytest) rejouables en intégration continue, pas seulement des captures d'écran.

## 8. Planification et faisabilité

**Diagnostic :** l'ordre des étapes est le principal défaut du document. La synchronisation et le modèle de propriété des données doivent être conçus à l'étape 2. Sinon, les étapes 3 à 5 seront réécrites.

Ces estimations sont les miennes. Elles supposent un développeur solo expérimenté en Python, assisté par IA, à temps plein. L'IA accélère le code CRUD et les écrans de 30 à 50 %, mais très peu la conception de la synchronisation, le débogage de la concurrence et la validation comptable.

| Étape | Effort (j-h) | Durée (sem.) | Commentaire |
|---|---|---|---|
| 1. Validation (règles, maquettes, avis de l'expert-comptable) | 10–15 | 2–3 | Inclure le schéma de propriété des données et le plan d'imputation |
| 2. Socle + **squelette de synchronisation** | 25–35 | 5–7 | Nœud de site, authentification, migrations, outbox/inbox, installeur signé |
| 3. Stocks + transferts | 25–35 | 5–7 | CMUP, transit, réception partielle |
| 4. Caisses | 12–18 | 3–4 | Sessions, clôture, virements |
| 5. Comptabilité initiale | 20–30 | 4–6 | Génération d'écritures, journaux, balance, export FEC, clôture |
| 6. Durcissement de la synchronisation et des conflits | 20–35 | 4–7 | Séquences, reprise, longues coupures, tableau d'état |
| 7. Pilote 1–2 sites | 20–30 | 4–6 | Corrections, formation, reprise des données |
| 8. Extension | 15–30 | 4–8 | Déploiement, support |
| **Total** | **150–230** | **32–52** | Soit 8 à 12 mois |

**Chemin critique :** décision de topologie et de propriété → modèle de données et événements → synchronisation minimale → stocks et transferts → pilote.

**Risques majeurs :**
1. Synchronisation sous-estimée : c'est le risque n° 1.
2. Règles comptables non validées, entraînant une réécriture du générateur d'écritures.
3. Développeur unique (bus factor = 1) et support de 5 sites.
4. Packaging et antivirus sur les postes.
5. Code généré par IA non testé sur les invariants.
6. Glissement du périmètre vers les ventes, achats et paie.

**MVP réellement livrable (16 à 22 semaines) :**
- 1 société, 2 sites, CMUP, transferts avec transit ;
- caisse avec clôture ;
- écritures générées **en brouillon** et export vers le logiciel comptable existant ou vers l'expert-comptable ;
- synchronisation montante (site → central) et descendante (référentiels) ;
- sauvegarde et restauration.

**À reporter :**
- validation comptable dans l'outil et états financiers ;
- multi-sociétés ;
- multi-devises ;
- résolution interactive des conflits (inutile avec le modèle de propriété) ;
- FIFO ;
- états analytiques avancés.

## 9. Positionnement marché : construire ou adopter ?

| Option | Forces | Faiblesses pour ce besoin |
|---|---|---|
| **Odoo Community + l10n_cm** (+ modules SYSCOHADA de la communauté, comme AITE pour Odoo 18) | Stocks multi-dépôts, comptabilité, intégrateurs locaux à Douala et Yaoundé, coût de licence nul en Community [github +2](https://github.com/BigWenceslas/AITE-SYSCO-OHADA) | Le mode hors ligne se limite au point de vente : la documentation Odoo 18.0 indique qu'il fonctionne « even if you are temporarily offline », et selon le forum officiel Odoo « You cannot open a new POS session without internet—only existing sessions continue to work offline. » Les stocks ne sont pas mis à jour hors ligne. Pas de vrai multi-site hors ligne sans une instance par site et de la synchronisation sur mesure. |
| **ERPNext / Frappe** | Open source, multi-entrepôts, comptabilité | Le hors ligne natif est faible. La synchronisation multi-instances (« event streaming ») est jugée peu fiable par des intégrateurs, et des solutions tierces existent (GPOS avec base locale). [clefincode](https://clefincode.com/blog/extra-notes-for-you/en/solving-offline-erp-challenges-with-a-custom-erpnext-synchronization-solution) [erpgulf](https://cloud.erpgulf.com/blog/news/gpos) |
| **Sage (gamme 100 / Saari) et logiciels de bureau locaux** | Connus des comptables, conformes aux usages locaux | Peu adaptés au multi-site hors ligne, licences par poste. |
| **SaaS locaux** (SangoCompta, Omamori à partir de 15 000 FCFA/mois, CloudFacile, zBilling…) | Prix bas, localisation fiscale (DSF, TVA), certains annoncent un mode hors ligne [sangocompta +2](https://sangocompta.com/) | Affirmations commerciales non vérifiées. La profondeur du hors ligne multi-dépôts est à tester avant tout engagement. |
| **Sur mesure (ce cahier des charges)** | Hors ligne natif conçu pour les coupures, maîtrise totale, potentiel de produit SaaS pour le marché camerounais | 8 à 12 mois-homme, maintenance et support permanents, risque réglementaire porté par l'éditeur |

**Coût/bénéfice :**
- **Pour un client unique au besoin standard** (négoce multi-dépôts), adopter Odoo ou un SaaS local et adapter est presque toujours moins cher. Ordre de grandeur : quelques semaines d'intégration contre 8 à 12 mois de développement.
- **Le sur-mesure se justifie si** l'une de ces conditions est remplie :
  - les coupures longues (plusieurs jours) sont fréquentes et bloquantes ;
  - le fondateur vise un **produit** réutilisable pour plusieurs PME : un « ERP hors ligne pour l'Afrique centrale » est un vrai différenciateur ;
  - le client finance le développement et accepte un pilote.

Dans le cas d'un projet client, clarifier par écrit :
- la propriété du code ;
- la licence ;
- la maintenance ;
- la responsabilité réglementaire.

## 10. Recommandations priorisées (avant de coder)

**A. Décisions de la section 13 à trancher (avec recommandation)**
1. **Référentiel :** confirmer le SYSCOHADA révisé, système normal ou SMT selon le chiffre d'affaires. Faire valider par l'expert-comptable.
2. **Valorisation :** CMUP après chaque entrée, calculé par société. FIFO reporté.
3. **Sortie de stock à l'expédition**, vers un emplacement « transit » logistique. Traitement comptable du transit à faire valider.
4. **Politique de caisse :**
   - plafond par caisse ;
   - double validation des dépenses au-delà d'un seuil ;
   - écart toléré chiffré ;
   - clôture par une personne distincte ou avec visa.
5. **Serveur central hébergé** (VPS ou cloud avec sauvegarde) plutôt qu'au site principal, car un site principal tombe avec son électricité.
6. **Durée hors ligne maximale :** par exemple 7 jours en exploitation, 30 jours testés. Synchronisation toutes les 1 à 5 minutes quand le lien existe.
7. **Matrice rôles × sites × opérations,** jointe en annexe.

**B. Décisions oubliées par le document**
8. Topologie : nœud de site à écrivain unique, postes en clients légers.
9. Modèle de propriété des données et événements métier immuables avec `site_seq`.
10. Tiers minimum (fournisseurs) et document d'achat simple pour justifier les entrées et leurs coûts.
11. TVA 19,25 % paramétrable, exonérations, alerte sur les paiements en espèces au-delà de 100 000 FCFA (condition de déduction posée par le dépliant TVA de la DGI).
12. Tables manquantes :
    - `fiscal_periods` ;
    - `attachments` ;
    - `item_costs` ;
    - `company_id` partout ;
    - libellé et pièce sur les lignes d'écriture ;
    - portée des rôles.
13. Clôture informatique au moins trimestrielle et report sur la première période ouverte (art. 22 AUDCIF).
14. Export FEC et journal d'audit non altérable conservé 10 ans (art. L 19 CGI). [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf)
15. Exigences non fonctionnelles chiffrées : volumétrie, temps de réponse, RPO/RTO, matériel.
16. Packaging : installeur signé, mise à jour automatique, compatibilité N/N-1.
17. Conformité à la loi 2024/017 : registre, minimisation, hébergement.
18. Reprise initiale des données et inventaire d'ouverture.

**C. Architecture V1 simplifiée**
- **Poste :** PySide6 en client léger, sans base locale, qui appelle le service du site.
- **Nœud de site :**
  - FastAPI local et SQLite en WAL (un seul processus) ou PostgreSQL local ;
  - outbox/inbox ;
  - sauvegarde par `VACUUM INTO` toutes les heures ;
  - BitLocker ;
  - onduleur.
- **Central :**
  - FastAPI et PostgreSQL ;
  - inbox dédupliquée par (`site_id`, `site_seq`, `event_id`) ;
  - projection des soldes ;
  - référentiels ;
  - clôtures ;
  - comptabilité consolidée.
- **Règles de base :** pas de multi-maîtres sur les documents ; conflits limités aux référentiels, que seul le central modifie.

**D. Ordre de développement recommandé**
1. Squelette de bout en bout : authentification, nœud de site, outbox, central, un événement factice synchronisé et acquitté.
2. Référentiels descendants.
3. Mouvements de stock et soldes.
4. Transferts avec transit.
5. Caisses.
6. Génération d'écritures en brouillon et exports.
7. Durcissement : longues coupures, migrations, sauvegarde et restauration, sécurité.
8. Pilote.
9. Validation comptable, clôtures et FEC dans l'outil.

## 11. Verdict chiffré final

| Dimension | Note /10 | Justification |
|---|---|---|
| Clarté | 7,5 | Structure, vocabulaire et règles nets ; quelques choix laissés ouverts (numérotation, réservation, topologie) |
| Complétude | 4,5 | Manquent : tiers, TVA, périodes, multi-sociétés réel, pièces jointes, exigences non fonctionnelles, reprise, déploiement, FEC |
| Faisabilité technique | 6,5 | Pile réaliste pour un développeur solo ; risque de packaging et de double dialecte SQLite/PostgreSQL |
| Robustesse de la synchronisation | 5 | Bons principes (outbox, idempotence, accusés de réception) ; manquent la propriété des données, l'ordonnancement, les horloges, la topologie par site et le traitement des périodes clôturées |
| Rigueur comptable | 5 | Partie double et contre-passation corrects ; manquent la clôture informatique, le livre-journal et le livre d'inventaire, la TVA, le plan d'imputation et le choix d'inventaire permanent ou intermittent |
| Sécurité | 5,5 | Principes justes mais non opérationnalisés (algorithme, chiffrement, hors ligne, chaîne d'audit, loi 2024/017) |
| Testabilité | 6 | 16 tests pertinents ; manquent les tests de panne, de migration, d'horloge, de longue coupure, de volume et de sécurité, ainsi que des seuils chiffrés |
| Réalisme du planning | 3 | Synchronisation placée trop tard (contradiction T07), aucune estimation, périmètre trop large pour un développeur solo |
| **Note globale** | **5,2 / 10** | Moyenne simple des 8 dimensions, arrondie |

**Recommandation : GO AVEC MODIFICATIONS.**

Le socle intellectuel est bon. Les règles de contrôle interne et le choix outbox/inbox montrent qu'on peut construire un système fiable. Mais coder maintenant reviendrait à bâtir les étapes 3 à 5 sur une synchronisation non conçue, puis à les réécrire.

Avant le démarrage :
- réviser le document en v1.1 (1 à 2 semaines) en intégrant les points A et B ;
- faire valider le plan d'imputation par un expert-comptable inscrit à l'ONECCA ;
- comparer en une journée avec une démonstration d'Odoo + l10n_cm et d'un SaaS local.

Si le besoin hors ligne multi-site est confirmé comme critique, ou si l'objectif est un produit, construire en suivant l'ordre D.

## Caveats

- **Estimations :** les estimations d'effort sont des jugements d'expert, pas des mesures. Elles varient fortement selon l'expérience du développeur avec la concurrence et la comptabilité.
- **Fiscalité camerounaise 2026 :**
  - les articles L 8 sexies, L 19 et L 105 quinquies ont été analysés dans la rédaction du **projet** de loi de finances 2026 ; [dgb](https://www.dgb.cm/wp-content/uploads/2025/11/PROJET-DE-LOI-FINANCES-2026_FR_26112025.pdf)
  - leur adoption est confirmée par la brochure DGI et Deloitte, mais le texte promulgué et les arrêtés d'application n'ont pas été vérifiés mot à mot ; [deloitte](https://blog.avocats.deloitte.fr/cameroun-les-principales-innovations-de-la-loi-de-finances-pour-2026/) [bstp-cameroun](https://bstp-cameroun.cm/assets/files/articlefile/125-0.pdf)
  - aucun calendrier officiel de facturation électronique généralisée n'a été trouvé. Des sources secondaires (briefings sectoriels) affirment une obligation pour tous les assujettis à la TVA ; [vatupdate](https://www.vatupdate.com/2026/03/14/briefing-document-podcast-e-invoicing-e-reporting-in-cameroon/) cela n'est pas cohérent avec le texte, qui vise « certaines opérations ». [casskai](https://casskai.app/en/solutions/cameroun)
- **Comptes SYSCOHADA :** les comptes cités (31, 38, 57, 58, 6031) sont donnés à titre indicatif. Le plan d'imputation doit être établi par un professionnel comptable.
- **Concurrents :** les fonctionnalités annoncées par les éditeurs SaaS locaux (« hors ligne », « e-facturation DGI ») sont des affirmations commerciales non testées.
- **Loi 2024/017 :** l'état de mise en place de l'autorité de protection des données et des textes d'application est à confirmer auprès d'un juriste.