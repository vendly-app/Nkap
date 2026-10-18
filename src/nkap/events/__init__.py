"""Événements de synchronisation.

Un site n'envoie jamais « modifie telle ligne » au central : il envoie des **événements
métier immuables** (« note créée », « transfert expédié »...). Chaque événement est rangé
dans une **enveloppe** commune (``EventEnvelope``) qui porte son numéro d'ordre sur le
site (``site_seq``), et un **contenu** (``payload``) dont la forme dépend du type
d'événement et de sa version (``EventRegistry``).
"""
