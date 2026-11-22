# Collecte quotidienne des flux (revue de presse politique)
- feeds.txt : « Média|URL du flux » (copie de la colonne E du tableau Claude Docs).
- gnews_sites.txt : médias sans flux, collectés via Google Actualités (site:domaine).
- collect.py : lit tous les flux, garde les 4 derniers jours, écrit data/latest.json.
- .github/workflows/collecte.yml : lancé chaque jour par GitHub (05h30 et 10h Paris), commit de data/latest.json.
Les tâches de la frise lisent data/latest.json au lieu de visiter chaque site.

- Texte intégral (champ « texte ») pour les articles des 2 derniers jours des médias gratuits ; médias payants ou texte trop court : « pay »: true, titre + chapô seulement.

## Dépôt public
Ce dépôt est public : `data/latest.json` ne contient que média, titre, lien, date et chapô (jamais le texte intégral des articles).
