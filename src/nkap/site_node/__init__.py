"""Nœud de site : le service qui tourne sur le PC serveur de chaque site.

Il est le seul à écrire dans la base du site (décision 001). Il enregistre chaque
opération avec, dans la même transaction, l'événement à envoyer au central (outbox),
puis envoie ces événements dès que la connexion le permet.
"""
