"""Nkap : gestion intégrée multi-sites qui continue de fonctionner sans Internet.

Organisation du code :

- ``nkap.core`` : briques techniques communes (horloge, identifiants, montants...).
- ``nkap.events`` : format des événements échangés entre un site et le central.
- ``nkap.audit`` : journal d'audit chaîné (infalsifiable).
- ``nkap.site_node`` : service qui tourne sur le PC serveur de chaque site.
- ``nkap.central`` : serveur central qui consolide les données de tous les sites.
"""

__version__ = "0.1.0"
