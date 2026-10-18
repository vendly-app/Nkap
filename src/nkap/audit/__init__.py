"""Journal d'audit chaîné (décision 007).

Chaque ligne du journal contient l'empreinte (SHA-256) de la ligne précédente. Modifier,
supprimer ou intercaler une ligne casse la chaîne, ce qui se détecte immédiatement.
Le journal est aussi répliqué au central, qui vérifie la chaîne de chaque site.
"""
