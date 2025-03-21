# KHInsider Downloader

Un outil en ligne de commande pour télécharger des albums musicaux de jeux vidéo depuis le site downloads.khinsider.com.

## Fonctionnalités

- Téléchargement d'albums complets
- Préférence de format (FLAC, MP3)
- Support multithreading pour des téléchargements simultanés
- Ajout de métadonnées aux fichiers audio (via mutagen)
- Gestion des erreurs et des tentatives de téléchargement
- Suivi de la progression avec barres d'avancement (via tqdm)
- Configuration personnalisable et sauvegardable

## Prérequis

- Python 3.6 ou supérieur
- Bibliothèques requises:
  - BeautifulSoup4
  - tqdm (optionnel, pour les barres de progression)
  - mutagen (optionnel, pour les métadonnées)

## Installation

1. Clonez ce dépôt ou téléchargez le script
2. Installez les dépendances:

```bash
pip install beautifulsoup4
pip install tqdm  # Pour les barres de progression
pip install mutagen  # Pour les métadonnées
```

## Utilisation

### Utilisation basique

Exécutez le script sans arguments pour le mode interactif:

```bash
python downloader.py
```

### Arguments en ligne de commande

```bash
python downloader.py -u URL_DE_L_ALBUM
```

### Options disponibles

```
-u, --url URL               URL de l'album à télécharger
-i, --input-file FICHIER    Fichier contenant des URLs d'albums (une par ligne)
-o, --output-dir DOSSIER    Répertoire de sortie pour les téléchargements
-t, --threads NOMBRE        Nombre maximum de téléchargements simultanés
-f, --format FORMAT         Format préféré (flac,mp3)
--no-track-numbers          Ne pas inclure les numéros de piste
--save-config               Sauvegarder la configuration actuelle
```

### Exemples

Télécharger un album spécifique:
```bash
python downloader.py -u https://downloads.khinsider.com/game-soundtracks/album/minecraft
```

Télécharger en FLAC avec 5 threads simultanés:
```bash
python downloader.py -u https://downloads.khinsider.com/game-soundtracks/album/minecraft -f flac -t 5
```

Télécharger plusieurs albums depuis un fichier:
```bash
python downloader.py -i albums.txt -o E:\Musique
```

## Configuration

Le script utilise un fichier `khinsider_config.json` pour stocker la configuration. Les valeurs par défaut sont:

```json
{
    "output_directory": "E:\\Musique",
    "max_threads": 3,
    "format_preference": ["flac", "mp3"],
    "include_track_number": true,
    "retry_attempts": 3,
    "retry_delay": 5
}
```

Vous pouvez sauvegarder votre configuration actuelle avec l'option `--save-config`.

## Journalisation

Le script enregistre toutes les actions dans un fichier `khinsider_downloader.log`, ce qui permet de suivre le processus de téléchargement et d'identifier les problèmes potentiels.

## Remarques

- Le script respecte les conditions d'utilisation du site en limitant le nombre de téléchargements simultanés.
- Les albums sont organisés dans des dossiers portant le nom de l'album.
- Si disponible, les métadonnées sont ajoutées aux fichiers téléchargés.
