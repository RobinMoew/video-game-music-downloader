import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse as urlparse
import urllib.request as urllib2
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    from tqdm import tqdm

    TQDM_AVAILABLE = False
    print("Note: Pour avoir des barres de progression, installez tqdm avec: pip install tqdm")

try:
    import mutagen
    from mutagen.flac import FLAC

    MUTAGEN_AVAILABLE = True
except ImportError:
    from mutagen.flac import FLAC

    MUTAGEN_AVAILABLE = False
    print("Note: Pour ajouter des métadonnées, installez mutagen avec: pip install mutagen")

# Configuration de base
BASE_URL = 'https://downloads.khinsider.com'
CONFIG_FILE = 'khinsider_config.json'
DEFAULT_CONFIG = {
    'output_directory': os.path.join(os.path.expanduser('~'), 'E:\\Musique'),
    'max_threads': 3,
    'format_preference': ['flac', 'mp3'],
    'include_track_number': True,
    'retry_attempts': 3,
    'retry_delay': 5
}

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("khinsider_downloader.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("KHInsiderDownloader")


def load_config():
    """Charge la configuration depuis le fichier ou utilise les valeurs par défaut"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Mise à jour de la config par défaut avec les valeurs chargées
                merged_config = DEFAULT_CONFIG.copy()
                merged_config.update(config)

                return merged_config
        except Exception as e:
            logger.warning(f"Erreur lors du chargement de la configuration: {e}")

    return DEFAULT_CONFIG


def save_config(config):
    """Sauvegarde la configuration dans un fichier"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info(f"Configuration sauvegardée dans {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")


def validate_url(url):
    """Vérifie si l'URL est une URL valide de KHInsider"""
    if not url.strip():
        return False
    if '//downloads.khinsider.com/game-soundtracks/album/' not in url:
        return False

    return True


def safe_request(url, retry_count=3, retry_delay=5):
    """Effectue une requête avec gestion d'erreur et tentatives multiples"""
    for attempt in range(retry_count):
        try:
            return urllib2.urlopen(url)
        except urllib.error.URLError as e:
            logger.warning(f"Erreur de connexion (tentative {attempt + 1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                logger.info(f"Nouvelle tentative dans {retry_delay} secondes...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Échec après {retry_count} tentatives: {url}")
                raise


def get_album_info(url, config):
    """Extrait les informations de l'album depuis l'URL"""
    try:
        response = safe_request(url, config['retry_attempts'], config['retry_delay'])
        soup = BeautifulSoup(response, features="html.parser")

        # Récupérer le titre de l'album
        album_title = soup.find('h2').text.strip() if soup.find('h2') else "Unknown Album"
        album_title = sanitize_filename(album_title)

        # Créer un dictionnaire pour stocker les informations
        album_info = {
            'title': album_title,
            'url': url,
            'tracks': []
        }

        # Trouver la liste des chansons
        song_list = soup.find(id="songlist")
        if not song_list:
            logger.error("Impossible de trouver la liste des chansons")

            return None

        # Trouver toutes les lignes du tableau
        rows = song_list.find_all('tr')

        track_count = 0
        for row in rows:
            # Chercher les cellules avec la classe "clickable-row"
            cells = row.find_all('td', class_="clickable-row")
            if cells and len(cells) > 0:
                # Prendre le premier lien de la première cellule clickable
                link = cells[0].find('a')
                if link and link.get('href'):
                    href = link.get('href')
                    track_name = link.text.strip()

                    # Utiliser directement l'URL du MP3 comme URL de la page de détail
                    # Cette URL contient toutes les informations nécessaires
                    detail_url = BASE_URL + href

                    track_count += 1
                    album_info['tracks'].append(
                        {
                            'name': track_name,
                            'url': detail_url
                        }
                    )

        logger.info(f"Album trouvé: {album_title} ({track_count} pistes)")

        return album_info
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction des informations de l'album: {e}")

        return None


def get_track_download_url(track_url, format_preference):
    """Récupère l'URL de téléchargement pour un format spécifié"""
    try:
        # Si l'URL pointe directement vers un fichier MP3, extraire l'URL de la page de détail
        if track_url.endswith('.mp3'):
            # Utiliser directement l'URL du MP3 comme URL de la page de détail
            detail_url = track_url
        else:
            detail_url = track_url

        response = safe_request(detail_url)
        soup = BeautifulSoup(response, features="html.parser")

        # Récupérer le titre de la piste
        track_title = None
        title_element = soup.find('p', align="left")
        if title_element:
            bold_elements = title_element.find_all('b')
            if len(bold_elements) > 1:
                track_title = bold_elements[1].text.strip()

        # Si le titre n'est pas trouvé, utiliser le nom du fichier
        if not track_title:
            # Extraire le nom du fichier de l'URL
            track_title = os.path.basename(detail_url).replace('%20', ' ')
            if track_title.endswith('.mp3'):
                track_title = track_title[:-4]

        # Chercher les liens de téléchargement avec le texte "Click here to download as FLAC/MP3"
        download_links = {}
        for format_type in format_preference:
            links = soup.find_all('a')
            for link in links:
                # Vérifier si le lien contient le texte de téléchargement pour ce format
                if link.text and f"Click here to download as {format_type.upper()}" in link.text:
                    href = link.get('href')
                    if href:
                        # Trouver la taille du fichier
                        file_size = 0
                        size_text = link.parent.text if link.parent else ""
                        if "MB" in size_text:
                            try:
                                size_str = size_text.split('(')[1].split(' MB')[0]
                                file_size = float(size_str)
                            except:
                                pass

                        download_links[format_type] = {
                            'url': href,
                            'format': format_type,
                            'title': track_title,
                            'size': file_size
                        }

        # Retourner le premier format disponible selon la préférence
        for format_type in format_preference:
            if format_type in download_links:
                # Encode l'URL pour qu'elle soit sûre à utiliser avec urllib
                url = download_links[format_type]['url']
                # D'abord, décoder l'URL si elle contient des séquences comme %2520
                url = urllib.parse.unquote(url)
                # Ensuite, encoder correctement pour la requête HTTP
                url = urllib.parse.quote(url, safe='/:')
                download_links[format_type]['url'] = url

                return download_links[format_type]

        # Si aucun lien n'est trouvé, essayer de trouver un élément audio
        audio = soup.find('audio')
        if audio and audio.get('src'):
            audio_src = audio.get('src')
            # Décoder puis encoder correctement l'URL
            audio_src = urllib.parse.unquote(audio_src)
            audio_src = urllib.parse.quote(audio_src, safe='/:')

            format_type = 'mp3'  # Par défaut

            # Vérifier si une version FLAC est disponible
            if 'flac' in format_preference:
                flac_url = audio_src.replace('.mp3', '.flac')
                try:
                    # Utiliser l'URL encodée pour la vérification
                    urllib2.urlopen(flac_url)

                    return {
                        'url': flac_url,
                        'format': 'flac',
                        'title': track_title,
                        'size': 0
                    }
                except:
                    pass

            return {
                'url': audio_src,
                'format': format_type,
                'title': track_title,
                'size': 0
            }

        logger.warning(f"Aucun lien de téléchargement trouvé pour {detail_url}")

        return None
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'URL de téléchargement: {e}")

        return None


def download_file(url, file_path, expected_size=None, retry_count=3, retry_delay=5):
    """Télécharge un fichier avec gestion des interruptions et vérification de taille"""
    for attempt in range(retry_count):
        try:
            # Vérifier si le fichier existe déjà et a la bonne taille
            if os.path.exists(file_path) and expected_size:
                existing_size = os.path.getsize(file_path) / (1024 * 1024)  # Convertir en Mo
                if abs(existing_size - expected_size) < 0.1:  # Tolérance de 0.1 Mo
                    logger.info(f"Le fichier existe déjà et a la bonne taille: {file_path}")

                    return True

            # Télécharger le fichier
            response = safe_request(url)
            total_size = int(response.info().get('Content-Length', 0))
            downloaded = 0
            chunk_size = 1024 * 8  # 8KB

            with open(file_path, 'wb') as f:
                if TQDM_AVAILABLE:
                    pbar = tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(file_path))

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if TQDM_AVAILABLE:
                        pbar.update(len(chunk))

                if TQDM_AVAILABLE:
                    pbar.close()

            # Vérifier la taille du fichier téléchargé
            if 0 < total_size != downloaded:
                logger.warning(f"Taille du fichier incomplète: {downloaded} sur {total_size} octets")
                if attempt < retry_count - 1:
                    logger.info(f"Nouvelle tentative dans {retry_delay} secondes...")
                    time.sleep(retry_delay)
                    continue
                else:
                    return False

            logger.info(f"Téléchargement terminé: {file_path}")

            return True

        except Exception as e:
            logger.error(f"Erreur de téléchargement (tentative {attempt + 1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                logger.info(f"Nouvelle tentative dans {retry_delay} secondes...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Échec du téléchargement après {retry_count} tentatives")

                return False


def set_metadata(file_path, track_filename, album_info, track_number=None):
    """Ajoute des métadonnées aux fichiers audio téléchargés"""
    if not MUTAGEN_AVAILABLE:
        return

    try:
        file_format = os.path.splitext(file_path)[1].lower()

        if file_format == '.flac':
            audio = FLAC(file_path)
            audio['TITLE'] = track_filename
            audio['ALBUM'] = album_info['title']
            if track_number is not None:
                audio['TRACKNUMBER'] = str(track_number)
            audio.save()

        elif file_format == '.mp3':
            # Pour les fichiers MP3, il faudrait utiliser ID3 de mutagen
            # Cette partie est simplement un exemple et pourrait être étendue
            pass

        logger.info(f"Métadonnées ajoutées pour {file_path}")
    except Exception as e:
        logger.warning(f"Impossible d'ajouter des métadonnées: {e}")


def download_track(track, album_info, output_dir, config, track_number=None):
    """Télécharge une piste spécifique"""
    try:
        track_info = get_track_download_url(track['url'], config['format_preference'])
        if not track_info:
            logger.error(f"Impossible de récupérer l'URL de téléchargement pour {track['name']}")

            return False

        # Créer un nom de fichier sanitisé
        track_filename = track['name']
        if config['include_track_number'] and track_number is not None:
            track_filename = f"{track_number:02d} - {track_filename}"

        file_path = os.path.join(output_dir, f"{track_filename}.{track_info['format']}")

        # Télécharger le fichier
        success = download_file(
            track_info['url'],
            file_path,
            track_info['size'],
            config['retry_attempts'],
            config['retry_delay']
        )

        if success and MUTAGEN_AVAILABLE:
            set_metadata(file_path, track_filename, album_info, track_number)

        return success
    except Exception as e:
        logger.error(f"Erreur lors du téléchargement de la piste {track['name']}: {e}")

        return False


def download_album(album_url, config):
    """Télécharge un album complet"""
    if not validate_url(album_url):
        logger.error(f"URL invalide: {album_url}")

        return False

    logger.info(f"Récupération des informations de l'album: {album_url}")
    album_info = get_album_info(album_url, config)

    if not album_info or not album_info['tracks']:
        logger.error(f"Aucune piste trouvée pour l'album: {album_url}")

        return False

    # Créer le répertoire de sortie
    album_output_dir = os.path.join(config['output_directory'], album_info['title'])

    if not os.path.exists(config['output_directory']):
        os.makedirs(config['output_directory'])

    if not os.path.exists(album_output_dir):
        os.makedirs(album_output_dir)

    logger.info(f"Téléchargement de {len(album_info['tracks'])} pistes vers {album_output_dir}")

    # Téléchargement des pistes avec multithreading
    success_count = 0
    with ThreadPoolExecutor(max_workers=config['max_threads']) as executor:
        futures = []
        for i, track in enumerate(album_info['tracks']):
            futures.append(
                executor.submit(
                    download_track, track, album_info, album_output_dir, config, i + 1
                )
            )

        # Attendre la fin des téléchargements
        for future in futures:
            if future.result():
                success_count += 1

    logger.info(f"Album téléchargé: {success_count}/{len(album_info['tracks'])} pistes réussies")

    return success_count == len(album_info['tracks'])


def sanitize_filename(filename):
    """Supprime les caractères spéciaux interdits dans les noms de fichiers Windows"""
    # Caractères interdits dans les noms de fichiers Windows: \ / : * ? " < > |
    forbidden_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    for char in forbidden_chars:
        filename = filename.replace(char, '_')
    return filename


def main():
    """Fonction principale du script"""
    # Charger la configuration
    config = load_config()

    # Analyser les arguments de ligne de commande
    parser = argparse.ArgumentParser(description="Téléchargeur d'albums KHInsider")
    parser.add_argument('-u', '--url', help='URL de l\'album à télécharger')
    parser.add_argument('-i', '--input-file', help='Fichier contenant des URLs d\'albums (une par ligne)')
    parser.add_argument('-o', '--output-dir', help='Répertoire de sortie pour les téléchargements')
    parser.add_argument('-t', '--threads', type=int, help='Nombre maximum de téléchargements simultanés')
    parser.add_argument('-f', '--format', help='Format préféré (flac,mp3)')
    parser.add_argument('--no-track-numbers', action='store_true', help='Ne pas inclure les numéros de piste')
    parser.add_argument('--save-config', action='store_true', help='Sauvegarder la configuration actuelle')

    args = parser.parse_args()

    # Mettre à jour la configuration avec les arguments
    if args.output_dir:
        config['output_directory'] = args.output_dir
    if args.threads:
        config['max_threads'] = args.threads
    if args.format:
        config['format_preference'] = args.format.split(',')
    if args.no_track_numbers:
        config['include_track_number'] = False

    # Sauvegarder la configuration si demandé
    if args.save_config:
        save_config(config)

    # Liste des URLs à traiter
    urls_to_process = []

    # Ajouter l'URL depuis les arguments
    if args.url:
        urls_to_process.append(args.url)

    # Ajouter les URLs depuis le fichier d'entrée
    if args.input_file and os.path.exists(args.input_file):
        try:
            with open(args.input_file, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):
                        urls_to_process.append(url)
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du fichier d'entrée: {e}")

    # Si aucune URL n'est spécifiée, demander à l'utilisateur
    if not urls_to_process:
        print("\nTéléchargeur d'albums KHInsider")
        print("===========================")
        print("\nVeuillez entrer l'URL d'un album (ou tapez 'q' pour quitter):")
        print("Exemple: https://downloads.khinsider.com/game-soundtracks/album/minecraft")

        while True:
            url = input("\nURL: ")
            if url.lower() == 'q':
                sys.exit(0)

            if validate_url(url):
                urls_to_process.append(url)
                break
            else:
                print("URL invalide. Veuillez entrer une URL valide de KHInsider.")

    # Télécharger chaque album
    success_count = 0
    for url in urls_to_process:
        if download_album(url, config):
            success_count += 1

    logger.info(f"Téléchargement terminé: {success_count}/{len(urls_to_process)} albums réussis")
    print(f"\nTéléchargement terminé: {success_count}/{len(urls_to_process)} albums réussis")
    print(f"Les albums sont sauvegardés dans: {config['output_directory']}")


if __name__ == "__main__":
    main()
