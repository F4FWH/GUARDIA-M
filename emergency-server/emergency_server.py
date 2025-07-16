#!/usr/bin/env python3
"""
Gaulix Alerte Réseau D'urgence Intervention Assistée Meshtastic - GARDIA-M
Script OpenWrt pour formulaire d'urgence avec transmission Meshtastic
Utilise Bottle pour le serveur web et YAML pour la configuration

Version: 1.0.0
Auteur: Assistant Claude
Date: 2025-07-16
"""

# Version du script
VERSION = "1.0.0"
BUILD_DATE = "2025-07-16"

import logging
import yaml
import time
import json
import hashlib
import base64
import urllib.parse
from bottle import Bottle, request, response, run, static_file, template, redirect
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import os
import sys

# Configuration par défaut
DEFAULT_CONFIG = {
    'app': {
        'name': 'Emergency Meshtastic Server',
        'version': VERSION,
        'build_date': BUILD_DATE
    },
    'web': {
        'host': '0.0.0.0',
        'port': 8080,
        'debug': False,
        'template_dir': './templates',
        'static_dir': './static'
    },
    'admin': {
        'enabled': True,
        'username': 'admin',
        'password': 'admin123',  # À changer impérativement !
        'session_timeout': 3600  # 1 heure en secondes
    },
    'meshtastic': {
        'device': '/dev/ttyUSB0',
        'channel_index': 1,
        'channel_name': 'Fr-Emcom',
        'max_message_length': 200
    },
    'logging': {
        'level': 'INFO',
        'format': '%(asctime)s - %(levelname)s - %(message)s',
        'log_all_data': True
    },
    'alert_types': {
        'Incendie': 1,
        'Secours à Personnes': 2,
        'Autre': 3
    },
    'logos': {
        'enabled': True,
        'logo1': {
            'file': 'logo1.png',
            'alt': 'Logo 1',
            'link': ''
        },
        'logo2': {
            'file': 'logo2.png', 
            'alt': 'Logo 2',
            'link': ''
        },
        'logo3': {
            'file': 'logo3.png',
            'alt': 'Logo 3', 
            'link': ''
        }
    }
}

class ConfigManager:
    def __init__(self, config_file='config.yaml'):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self):
        """Charge la configuration depuis le fichier YAML"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    # Fusion avec la configuration par défaut
                    merged_config = self.merge_config(DEFAULT_CONFIG, config)
                    print(f"✅ Configuration chargée depuis {self.config_file}")
                    return merged_config
            except Exception as e:
                print(f"❌ Erreur lors du chargement de {self.config_file}: {e}")
                print("📝 Utilisation de la configuration par défaut")
        else:
            print(f"📝 Fichier {self.config_file} non trouvé, création avec la configuration par défaut")
            self.save_default_config()
        
        return DEFAULT_CONFIG
    
    def merge_config(self, default, custom):
        """Fusionne la configuration personnalisée avec celle par défaut"""
        result = default.copy()
        for key, value in custom.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_default_config(self):
        """Sauvegarde la configuration par défaut"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, allow_unicode=True)
            print(f"✅ Fichier de configuration par défaut créé: {self.config_file}")
        except Exception as e:
            print(f"❌ Erreur lors de la création du fichier de configuration: {e}")
    
    def get(self, key_path, default=None):
        """Récupère une valeur de configuration par chemin (ex: 'web.port')"""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

class MeshtasticHandler:
    def __init__(self, config_manager):
        self.config = config_manager
        self.interface = None
        self.device_path = self.config.get('meshtastic.device')
        self.channel_index = self.config.get('meshtastic.channel_index')
        self.channel_name = self.config.get('meshtastic.channel_name')
        self.connect()
    
    def connect(self):
        """Connexion au module Meshtastic"""
        try:
            self.interface = meshtastic.serial_interface.SerialInterface(self.device_path)
            logger.info(f"Connexion Meshtastic établie sur {self.device_path}")
            return True
        except Exception as e:
            logger.error(f"Erreur connexion Meshtastic: {e}")
            return False
    
    def send_message(self, message):
        """Envoie un message sur le canal spécifié"""
        try:
            if not self.interface:
                if not self.connect():
                    return False
            
            # Vérification finale de la limite de caractères
            max_length = self.config.get('meshtastic.max_message_length', 200)
            if len(message) > max_length:
                logger.error(f"Message trop long pour Meshtastic: {len(message)} caractères (limite: {max_length})")
                return False
            
            # Envoie le message sur le canal spécifié
            self.interface.sendText(message, channelIndex=self.channel_index)
            logger.info(f"📡 Message envoyé sur canal {self.channel_index} ({self.channel_name})")
            logger.debug(f"Contenu: {message}")
            return True
        except Exception as e:
            logger.error(f"Erreur envoi message: {e}")
            return False
    
    def close(self):
        """Ferme la connexion Meshtastic"""
        if self.interface:
            self.interface.close()
            logger.info("Connexion Meshtastic fermée")

class EmergencyApp:
    def __init__(self, config_file='config.yaml'):
        self.config = ConfigManager(config_file)
        self.config_file = config_file
        self.setup_logging()
        self.meshtastic_handler = MeshtasticHandler(self.config)
        self.app = Bottle()
        self.admin_sessions = {}  # Sessions d'administration actives
        self.setup_routes()
    
    def setup_logging(self):
        """Configure le système de logging"""
        level = getattr(logging, self.config.get('logging.level', 'INFO'))
        format_str = self.config.get('logging.format')
        logging.basicConfig(level=level, format=format_str)
        global logger
        logger = logging.getLogger(__name__)
    
    def setup_routes(self):
        """Configure les routes Bottle"""
        self.app.route('/', method='GET', callback=self.index)
        self.app.route('/submit', method='POST', callback=self.submit_form)
        self.app.route('/health', method='GET', callback=self.health_check)
        self.app.route('/version', method='GET', callback=self.version_info)
        self.app.route('/static/<filename>', method='GET', callback=self.static_files)
        
        # Routes d'administration
        if self.config.get('admin.enabled', True):
            self.app.route('/admin', method='GET', callback=self.admin_login_page)
            self.app.route('/admin/login', method='POST', callback=self.admin_login)
            self.app.route('/admin/dashboard', method='GET', callback=self.admin_dashboard)
            self.app.route('/admin/config', method='GET', callback=self.admin_config_edit)
            self.app.route('/admin/config', method='POST', callback=self.admin_config_save)
            self.app.route('/admin/logout', method='GET', callback=self.admin_logout)
    
    def index(self):
        """Page d'accueil avec le formulaire"""
        channel_name = self.config.get('meshtastic.channel_name')
        channel_index = self.config.get('meshtastic.channel_index')
        app_version = self.config.get('app.version', VERSION)
        
        # Chercher le template HTML
        template_dir = self.config.get('web.template_dir', './templates')
        template_file = os.path.join(template_dir, 'index.html')
        
        if os.path.exists(template_file):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Remplacement des variables dans le template
                html_content = html_content.replace('{{channel_name}}', channel_name)
                html_content = html_content.replace('{{channel_index}}', str(channel_index))
                html_content = html_content.replace('{{app_version}}', app_version)
                
                # Gestion des logos
                html_content = self.process_logos(html_content)
                
                # Gestion des messages conditionnels avec décodage
                success_message = request.query.get('success', '')
                error_message = request.query.get('error', '')
                
                # Décoder les messages pour corriger l'encodage
                if success_message:
                    # Décoder les + en espaces et supprimer l'encodage URL
                    success_message = success_message.replace('+', ' ')
                    import urllib.parse
                    try:
                        success_message = urllib.parse.unquote(success_message)
                    except:
                        pass
                
                if error_message:
                    # Décoder les + en espaces
                    error_message = error_message.replace('+', ' ')
                    import urllib.parse
                    try:
                        error_message = urllib.parse.unquote(error_message)
                    except:
                        pass
                
                if success_message:
                    success_block = f'<div class="success">{success_message}</div>'
                    html_content = html_content.replace('<!-- SUCCESS_MESSAGE -->', success_block)
                
                if error_message:
                    error_block = f'<div class="error">{error_message}</div>'
                    html_content = html_content.replace('<!-- ERROR_MESSAGE -->', error_block)
                
                # Supprimer les placeholders non utilisés
                html_content = html_content.replace('<!-- SUCCESS_MESSAGE -->', '')
                html_content = html_content.replace('<!-- ERROR_MESSAGE -->', '')
               
                return html_content
                
            except Exception as e:
                logger.error(f"Erreur lors du chargement du template: {e}")
                return self.get_fallback_html(channel_name, channel_index, app_version)
        else:
            logger.warning(f"Template non trouvé: {template_file}, utilisation du template intégré")
            return self.get_fallback_html(channel_name, channel_index, app_version)
    
    def process_logos(self, html_content):
        """Traite les logos dans le template HTML"""
        if not self.config.get('logos.enabled', True):
            # Supprimer la section logos si désactivée
            html_content = html_content.replace('<!-- LOGOS_SECTION -->', '')
            return html_content
        
        static_dir = self.config.get('web.static_dir', './static')
        logos_html = '<div class="logos-container">'
        
        for i in range(1, 4):  # logo1, logo2, logo3
            logo_config = self.config.get(f'logos.logo{i}', {})
            logo_file = logo_config.get('file', f'logo{i}.png')
            logo_alt = logo_config.get('alt', f'Logo {i}')
            logo_link = logo_config.get('link', '')
            
            logo_path = os.path.join(static_dir, logo_file)
            
            # Vérifier si le fichier logo existe
            if os.path.exists(logo_path):
                if logo_link:
                    logos_html += f'<a href="{logo_link}" target="_blank" class="logo-link">'
                    logos_html += f'<img src="/static/{logo_file}" alt="{logo_alt}" class="logo logo{i}">'
                    logos_html += '</a>'
                else:
                    logos_html += f'<img src="/static/{logo_file}" alt="{logo_alt}" class="logo logo{i}">'
        
        logos_html += '</div>'
        
        # Remplacer le placeholder par le HTML des logos
        html_content = html_content.replace('<!-- LOGOS_SECTION -->', logos_html)
        
        return html_content
    
    def get_fallback_html(self, channel_name, channel_index, app_version):
        """Template HTML de secours intégré"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Formulaire d'Urgence - Meshtastic v{app_version}</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #d32f2f;
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .version {{
                    text-align: center;
                    color: #666;
                    font-size: 12px;
                    margin-bottom: 20px;
                }}
                .form-group {{
                    margin-bottom: 20px;
                }}
                label {{
                    display: block;
                    font-weight: bold;
                    margin-bottom: 5px;
                    color: #333;
                }}
                input[type="text"], input[type="tel"], textarea, select {{
                    width: 100%;
                    padding: 10px;
                    border: 2px solid #ddd;
                    border-radius: 5px;
                    font-size: 16px;
                    box-sizing: border-box;
                }}
                input[type="text"]:focus, input[type="tel"]:focus, textarea:focus, select:focus {{
                    border-color: #4CAF50;
                    outline: none;
                }}
                textarea {{
                    height: 80px;
                    resize: vertical;
                }}
                select {{
                    height: 45px;
                }}
                .submit-btn {{
                    background-color: #d32f2f;
                    color: white;
                    padding: 15px 30px;
                    border: none;
                    border-radius: 5px;
                    font-size: 18px;
                    font-weight: bold;
                    cursor: pointer;
                    width: 100%;
                    margin-top: 20px;
                }}
                .submit-btn:hover {{
                    background-color: #b71c1c;
                }}
                .required {{
                    color: red;
                }}
                .info {{
                    background-color: #e3f2fd;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    border-left: 4px solid #2196F3;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚨 FORMULAIRE D'URGENCE</h1>
                <div class="version">Version {app_version} - Template de secours</div>
                <div class="info">
                    <strong>Information:</strong> Ce formulaire transmet votre alerte via Meshtastic sur le canal {channel_index} ({channel_name}).
                </div>
                
                <form method="post" action="/submit">
                    <div class="form-group">
                        <label for="nom_prenom">Nom et Prénom <span class="required">*</span></label>
                        <input type="text" id="nom_prenom" name="nom_prenom" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="telephone">Numéro de Téléphone <span class="required">*</span></label>
                        <input type="tel" id="telephone" name="telephone" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="adresse">Adresse <span class="required">*</span></label>
                        <textarea id="adresse" name="adresse" required placeholder="Adresse complète du sinistre"></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="type_sinistre">Type de Sinistre <span class="required">*</span></label>
                        <select id="type_sinistre" name="type_sinistre" required>
                            <option value="">-- Sélectionnez le type --</option>
                            <option value="Incendie">🔥 Incendie</option>
                            <option value="Secours à Personnes">🚑 Secours à Personnes</option>
                            <option value="Autre">⚠️ Autre</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="details">Détails</label>
                        <textarea id="details" name="details" placeholder="Précisions : nombre de victimes, gravité, moyens nécessaires... Ce champ peut se retrouver tronqué lors de l'envoi du message"></textarea>
                    </div>
                    
                    <button type="submit" class="submit-btn">📡 ENVOYER L'ALERTE</button>
                </form>
            </div>
      	    <div class="footer">
            	Gaulix Alerte Réseau D'urgence Intervention Assistée Meshtastic - GARDIA-M v{app_version}<br>
            	Canal: {channel_index} ({channel_name})
            </div>
	    <!-- Lien d'administration (optionnel) -->
	    <div class="admin-link" style="text-align: center; margin-top: 20px;">
    		<a href="/admin" style="color: #666; font-size: 12px; text-decoration: none;">Administration</a>
	    </div>
        </body>
        </html>
        """
    
    def submit_form(self):
        """Traite la soumission du formulaire avec gestion d'erreur robuste"""
        from bottle import HTTPResponse
		
        try:
            # Récupération des données avec gestion d'encodage robuste
            def get_form_data_safe(field_name):
                """Récupère les données du formulaire avec correction d'encodage"""
                try:
                    # Méthode 1: récupération normale
                    data = request.forms.get(field_name, '').strip()
                    
                    # Correction d'encodage si nécessaire
                    if 'Ã©' in data or 'Ã¨' in data or 'Ã ' in data:
                        # Corrections courantes d'encodage
                        corrections = {
                            'Ã©': 'é', 'Ã¨': 'è', 'Ã ': 'à', 'Ã§': 'ç',
                            'Ã´': 'ô', 'Ã®': 'î', 'Ã»': 'û', 'Ã¹': 'ù',
                            'Ã¢': 'â', 'Ã¼': 'ü', 'Ã¯': 'ï', 'Ã±': 'ñ'
                        }
                        
                        for wrong, correct in corrections.items():
                            data = data.replace(wrong, correct)
                        
                        logger.info(f"Correction encodage appliquée sur {field_name}")
                    
                    return data
                    
                except Exception as e:
                    logger.error(f"Erreur récupération {field_name}: {e}")
                    return ""
            
            # Récupération des données avec correction automatique
            nom_prenom = get_form_data_safe('nom_prenom')
            telephone = get_form_data_safe('telephone')
            adresse = get_form_data_safe('adresse')
            type_sinistre = get_form_data_safe('type_sinistre')
            details = get_form_data_safe('details')  # Nouveau champ
            
            # Log des données reçues (après correction)
            logger.info(f"Formulaire reçu - Nom: '{nom_prenom}', Tel: '{telephone}', Type: '{type_sinistre}'")
            if len(adresse) > 50:
                logger.info(f"Adresse: '{adresse[:50]}...'")
            else:
                logger.info(f"Adresse: '{adresse}'")
            
            if details:
                if len(details) > 50:
                    logger.info(f"Détails: '{details[:50]}...'")
                else:
                    logger.info(f"Détails: '{details}'")
            
            # Validation des données (détails optionnel)
            if not all([nom_prenom, telephone, adresse, type_sinistre]):
                logger.warning("Tentative de soumission avec des champs manquants")
                return redirect("/?error=Tous les champs obligatoires doivent être remplis")
            
            # Logging complet des informations reçues (si activé dans la config)
            if self.config.get('logging.log_all_data', True):
                logger.info("=" * 50)
                logger.info("📝 NOUVELLE ALERTE REÇUE")
                logger.info(f"Nom/Prénom: {nom_prenom}")
                logger.info(f"Téléphone: {telephone}")
                logger.info(f"Adresse: {adresse}")
                logger.info(f"Type sinistre: {type_sinistre}")
                if details:
                    logger.info(f"Détails: {details}")
                logger.info(f"Timestamp: {time.strftime('%d/%m/%Y %H:%M:%S')}")
                logger.info(f"IP source: {request.environ.get('REMOTE_ADDR', 'Unknown')}")
                logger.info("=" * 50)
            else:
                logger.info(f"Nouvelle alerte reçue - Type: {type_sinistre} - IP: {request.environ.get('REMOTE_ADDR', 'Unknown')}")
            
            # Formatage du message pour Meshtastic
            message, is_truncated = self.format_emergency_message(nom_prenom, telephone, adresse, type_sinistre, details)
            
            # Log du message final
            logger.info(f"Message formaté ({len(message)} caractères): {message}")
            if is_truncated:
                logger.warning("⚠️ Message tronqué pour respecter la limite de 200 caractères")
            
            # Envoi via Meshtastic
            success = False
            try:
                success = self.meshtastic_handler.send_message(message)
                logger.info(f"Résultat envoi Meshtastic: {success}")
            except Exception as send_err:
                logger.error(f"Exception lors de l'envoi Meshtastic: {send_err}")
                success = False
            
            if success:
                logger.info(f"✅ Alerte envoyée avec succès - {nom_prenom} - {type_sinistre}")
                success_msg = "Message d'urgence envoye avec succes ! Votre alerte a ete transmise."
                if is_truncated:
                    success_msg += " (Message adapte a la limite Meshtastic de 200 caracteres)"
                
                # Simplifier le redirect sans encodage complexe
                return redirect(f"/?success={success_msg.replace(' ', '+')}")
            else:
                logger.error(f"❌ Échec d'envoi de l'alerte - {nom_prenom} - {type_sinistre}")
                return redirect("/?error=Erreur+lors+de+l+envoi+via+Meshtastic.+Veuillez+reessayer.")
        except HTTPResponse:
            # Les redirections Bottle sont normales, on les laisse passer
            raise        
        except Exception as e:
            logger.error(f"Erreur traitement formulaire: {e}")
            return redirect("/?error=Erreur interne du serveur")
    
    def format_emergency_message(self, nom_prenom, telephone, adresse, type_sinistre, details=None):
        """Formate le message d'urgence pour Meshtastic au format JSON avec codes numériques"""
        
        # Récupération du code numérique pour le type d'alerte
        alert_codes = self.config.get('alert_types', {
            'Incendie': 1,
            'Secours à Personnes': 2,
            'Autre': 3
        })
        
        type_code = alert_codes.get(type_sinistre, 3)  # 3 = "Autre" par défaut
        
        # Structure JSON du message
        message_data = {
            "type": type_code,
            "nom": nom_prenom,
            "tel": telephone,
            "adresse": adresse
        }
        
        # Ajouter les détails si présents
        if details and details.strip():
            message_data["details"] = details.strip()
        
        # Conversion en JSON compact (sans espaces)
        message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
        
        # Vérification de la limite de caractères (configurable)
        max_length = self.config.get('meshtastic.max_message_length', 200)
        is_truncated = False
        
        if len(message) > max_length:
            is_truncated = True
            logger.warning(f"Message JSON trop long ({len(message)} caractères), troncature nécessaire")
            
            # Stratégie de troncature intelligente - PRIORITÉ À L'ADRESSE
            # 1. Essayer de raccourcir les détails en premier
            if details and len(details) > 30:
                details_court = details[:27] + "..."
                message_data["details"] = details_court
                message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Étape 1 - Détails raccourcis: {len(message)} caractères")
            
            # 2. Essayer de raccourcir le nom
            if len(message) > max_length and len(nom_prenom) > 20:
                nom_court = nom_prenom[:17] + "..."
                message_data["nom"] = nom_court
                message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Étape 2 - Nom raccourci: {len(message)} caractères")
            
            # 3. Si toujours trop long, raccourcir davantage le nom
            if len(message) > max_length and len(nom_prenom) > 10:
                nom_tres_court = nom_prenom[:7] + "..."
                message_data["nom"] = nom_tres_court
                message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Étape 3 - Nom très raccourci: {len(message)} caractères")
            
            # 4. Supprimer les détails complètement si nécessaire
            if len(message) > max_length and "details" in message_data:
                del message_data["details"]
                message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Étape 4 - Détails supprimés: {len(message)} caractères")
            
            # 5. Si toujours trop long, nom minimal
            if len(message) > max_length:
                nom_minimal = nom_prenom[:5] + "..." if len(nom_prenom) > 5 else nom_prenom
                message_data["nom"] = nom_minimal
                message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
                logger.info(f"Étape 5 - Nom minimal: {len(message)} caractères")
            
            # 6. En dernier recours, raccourcir l'adresse mais le moins possible
            if len(message) > max_length:
                # Calculer l'espace disponible pour l'adresse
                # Créer un message de base sans adresse pour calculer l'espace
                temp_data = {
                    "type": type_code,
                    "nom": message_data["nom"],
                    "tel": telephone,
                    "adresse": ""
                }
                message_base = json.dumps(temp_data, ensure_ascii=False, separators=(',', ':'))
                espace_disponible = max_length - len(message_base) + 2  # +2 pour les guillemets de l'adresse vide
                
                if espace_disponible > 10:  # Si on a au moins 10 caractères pour l'adresse
                    adresse_tronquee = adresse[:espace_disponible-3] + "..."
                    message_data["adresse"] = adresse_tronquee
                    message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
                else:
                    # Adresse ultra-minimale
                    message_data["adresse"] = adresse[:35] + "..." if len(adresse) > 35 else adresse
                    message = json.dumps(message_data, ensure_ascii=False, separators=(',', ':'))
                
                logger.warning(f"Étape 6 - Adresse raccourcie en dernier recours: {len(message)} caractères")
            
            # 7. Troncature brutale finale si vraiment nécessaire
            if len(message) > max_length:
                message = message[:max_length-3] + "..."
                logger.warning("Troncature brutale appliquée au JSON")
        
        logger.info(f"Message JSON final: {len(message)} caractères")
        logger.info(f"Contenu: {message}")
        return message, is_truncated
    
    def version_info(self):
        """Retourne les informations de version"""
        return {
            "app_name": self.config.get('app.name', 'Gaulix Alerte Réseau D urgence Intervention Assistée Meshtastic - GARDIA-M'),
            "version": self.config.get('app.version', VERSION),
            "build_date": self.config.get('app.build_date', BUILD_DATE),
            "python_version": sys.version,
            "config_version": self.config.get('app.version', VERSION)
        }
    
    def static_files(self, filename):
        """Sert les fichiers statiques (logos, CSS, JS)"""
        static_dir = self.config.get('web.static_dir', './static')
        try:
            return static_file(filename, root=static_dir)
        except:
            response.status = 404
            return "Fichier non trouvé"
    
    def health_check(self):
        """Point de contrôle de santé du service"""
        try:
            meshtastic_status = "OK" if self.meshtastic_handler.interface else "ERROR"
            template_dir = self.config.get('web.template_dir', './templates')
            template_exists = os.path.exists(os.path.join(template_dir, 'index.html'))
            
            return {
                "status": "OK",
                "version": self.config.get('app.version', VERSION),
                "meshtastic": meshtastic_status,
                "template_file": "FOUND" if template_exists else "NOT_FOUND",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            response.status = 500
            return {"status": "ERROR", "error": str(e), "version": VERSION}
    
    # === ADMINISTRATION ===
    
    def generate_session_id(self):
        """Génère un ID de session unique"""
        return hashlib.sha256(f"{time.time()}{os.urandom(16)}".encode()).hexdigest()
    
    def check_admin_session(self):
        """Vérifie si l'utilisateur a une session admin valide"""
        session_id = request.get_cookie('admin_session')
        if not session_id or session_id not in self.admin_sessions:
            return False
        
        session = self.admin_sessions[session_id]
        timeout = self.config.get('admin.session_timeout', 3600)
        
        if time.time() - session['created'] > timeout:
            del self.admin_sessions[session_id]
            return False
        
        # Mettre à jour l'heure de dernière activité
        session['last_activity'] = time.time()
        return True
    
    def admin_login_page(self):
        """Page de connexion administrateur"""
        if not self.config.get('admin.enabled', True):
            response.status = 404
            return "Administration désactivée"
        
        if self.check_admin_session():
            return redirect('/admin/dashboard')
        
        error_message = request.query.get('error', '')
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Administration - Gaulix Alerte Réseau D'urgence Intervention Assistée Meshtastic - GARDIA-M</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f5f5f5;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                }}
                .login-container {{
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    width: 100%;
                    max-width: 400px;
                }}
                h1 {{
                    text-align: center;
                    color: #333;
                    margin-bottom: 30px;
                }}
                .form-group {{
                    margin-bottom: 20px;
                }}
                label {{
                    display: block;
                    margin-bottom: 5px;
                    font-weight: bold;
                    color: #333;
                }}
                input[type="text"], input[type="password"] {{
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #ddd;
                    border-radius: 5px;
                    font-size: 16px;
                    box-sizing: border-box;
                }}
                input[type="text"]:focus, input[type="password"]:focus {{
                    border-color: #4CAF50;
                    outline: none;
                }}
                .btn {{
                    background-color: #2196F3;
                    color: white;
                    padding: 12px 24px;
                    border: none;
                    border-radius: 5px;
                    font-size: 16px;
                    cursor: pointer;
                    width: 100%;
                }}
                .btn:hover {{
                    background-color: #1976D2;
                }}
                .error {{
                    background-color: #ffebee;
                    color: #c62828;
                    padding: 10px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    border-left: 4px solid #f44336;
                }}
                .back-link {{
                    text-align: center;
                    margin-top: 20px;
                }}
                .back-link a {{
                    color: #666;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="login-container">
                <h1>🔐 Administration</h1>
                
                {f'<div class="error">{error_message}</div>' if error_message else ''}
                
                <form method="post" action="/admin/login">
                    <div class="form-group">
                        <label for="username">Nom d'utilisateur:</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="password">Mot de passe:</label>
                        <input type="password" id="password" name="password" required>
                    </div>
                    
                    <button type="submit" class="btn">Se connecter</button>
                </form>
                
                <div class="back-link">
                    <a href="/">← Retour au formulaire d'urgence</a>
                </div>
            </div>
        </body>
        </html>
        """
    
    def admin_login(self):
        """Traitement de la connexion administrateur"""
        if not self.config.get('admin.enabled', True):
            response.status = 404
            return "Administration désactivée"
        
        username = request.forms.get('username', '').strip()
        password = request.forms.get('password', '').strip()
        
        expected_username = self.config.get('admin.username', 'admin')
        expected_password = self.config.get('admin.password', 'admin123')
        
        if username == expected_username and password == expected_password:
            # Créer une session
            session_id = self.generate_session_id()
            self.admin_sessions[session_id] = {
                'created': time.time(),
                'last_activity': time.time(),
                'username': username
            }
            
            response.set_cookie('admin_session', session_id, max_age=self.config.get('admin.session_timeout', 3600))
            logger.info(f"Connexion admin réussie pour {username} depuis {request.environ.get('REMOTE_ADDR', 'Unknown')}")
            return redirect('/admin/dashboard')
        else:
            logger.warning(f"Tentative de connexion admin échouée pour {username} depuis {request.environ.get('REMOTE_ADDR', 'Unknown')}")
            return redirect('/admin?error=Nom d\'utilisateur ou mot de passe incorrect')
    
    def admin_dashboard(self):
        """Tableau de bord administrateur"""
        if not self.check_admin_session():
            return redirect('/admin')
        
        app_name = self.config.get('app.name', 'Gaulix Alerte Réseau D urgence Intervention Assistée Meshtastic - GARDIA-M')
        app_version = self.config.get('app.version', VERSION)
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Administration - {app_name}</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #eee;
                }}
                h1 {{
                    color: #333;
                    margin: 0;
                }}
                .logout-btn {{
                    background-color: #f44336;
                    color: white;
                    padding: 8px 16px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-size: 14px;
                }}
                .logout-btn:hover {{
                    background-color: #d32f2f;
                }}
                .menu-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .menu-card {{
                    background: #f9f9f9;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #2196F3;
                }}
                .menu-card h3 {{
                    margin-top: 0;
                    color: #333;
                }}
                .btn {{
                    background-color: #2196F3;
                    color: white;
                    padding: 10px 20px;
                    text-decoration: none;
                    border-radius: 5px;
                    display: inline-block;
                    margin-top: 10px;
                }}
                .btn:hover {{
                    background-color: #1976D2;
                }}
                .btn-success {{
                    background-color: #4CAF50;
                }}
                .btn-success:hover {{
                    background-color: #45a049;
                }}
                .status {{
                    display: flex;
                    gap: 20px;
                    margin-top: 20px;
                }}
                .status-item {{
                    background: white;
                    padding: 15px;
                    border-radius: 5px;
                    border: 1px solid #ddd;
                    flex: 1;
                }}
                .status-ok {{
                    border-left: 4px solid #4CAF50;
                }}
                .status-error {{
                    border-left: 4px solid #f44336;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🛠️ Administration - {app_name}</h1>
                    <a href="/admin/logout" class="logout-btn">Déconnexion</a>
                </div>
                
                <div class="menu-grid">
                    <div class="menu-card">
                        <h3>⚙️ Configuration</h3>
                        <p>Modifier les paramètres du serveur, les types d'alerte, les logos et autres options.</p>
                        <a href="/admin/config" class="btn">Éditer la configuration</a>
                    </div>
                    
                    <div class="menu-card">
                        <h3>📊 État du système</h3>
                        <p>Vérifier l'état du serveur Meshtastic et des services.</p>
                        <a href="/health" class="btn btn-success" target="_blank">Voir l'état</a>
                    </div>
                    
                    <div class="menu-card">
                        <h3>📋 Informations</h3>
                        <p>Version du logiciel et informations techniques.</p>
                        <a href="/version" class="btn" target="_blank">Voir les détails</a>
                    </div>
                </div>
                
                <div class="status">
                    <div class="status-item status-ok">
                        <strong>Version:</strong> {app_version}
                    </div>
                    <div class="status-item status-ok">
                        <strong>Meshtastic:</strong> {'Connecté' if self.meshtastic_handler.interface else 'Déconnecté'}
                    </div>
                    <div class="status-item status-ok">
                        <strong>Sessions admin:</strong> {len(self.admin_sessions)}
                    </div>
                </div>
                
                <div style="margin-top: 30px; text-align: center;">
                    <a href="/" class="btn">← Retour au formulaire d'urgence</a>
                </div>
            </div>
        </body>
        </html>
        """
    
    def admin_config_edit(self):
        """Page d'édition de la configuration"""
        if not self.check_admin_session():
            return redirect('/admin')
        
        try:
            # Lire le fichier avec gestion d'encodage robuste
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_content = f.read()
            
            # Corriger immédiatement les problèmes d'encodage à la lecture
            config_content = config_content.replace('Ã ', 'à')
            config_content = config_content.replace('Ã©', 'é')
            config_content = config_content.replace('Ã¨', 'è')
            config_content = config_content.replace('Ã§', 'ç')
            config_content = config_content.replace('É ', 'à')
            config_content = config_content.replace('Secours Ã  Personnes', 'Secours à Personnes')
            
            # Si on a trouvé des problèmes d'encodage, corriger le fichier directement
            if 'Ã' in config_content or 'É ' in config_content:
                logger.warning("Problèmes d'encodage détectés à la lecture, correction du fichier...")
                try:
                    # Réécrire le fichier avec l'encodage correct
                    with open(self.config_file, 'w', encoding='utf-8') as f:
                        f.write(config_content)
                    logger.info("Fichier corrigé automatiquement")
                except Exception as fix_err:
                    logger.error(f"Impossible de corriger le fichier: {fix_err}")
            
        except UnicodeDecodeError:
            # Problème d'encodage à la lecture, essayer latin1 puis corriger
            logger.warning("Erreur UTF-8, tentative de lecture avec latin1")
            try:
                with open(self.config_file, 'r', encoding='latin1') as f:
                    config_content = f.read()
                
                # Conversion des caractères latin1 vers UTF-8
                config_content = config_content.replace('Ã ', 'à')
                config_content = config_content.replace('Ã©', 'é')
                config_content = config_content.replace('Ã¨', 'è')
                
                # Réécrire le fichier en UTF-8 propre
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    f.write(config_content)
                logger.info("Fichier converti de latin1 vers UTF-8")
                
            except Exception as e:
                logger.error(f"Erreur de lecture du fichier: {e}")
                config_content = f"# Erreur lors du chargement: {e}"
        except Exception as e:
            logger.error(f"Erreur générale de lecture: {e}")
            config_content = f"# Erreur lors du chargement: {e}"
        
        success_message = request.query.get('success', '')
        error_message = request.query.get('error', '')
        
        # Décoder les messages pour corriger l'encodage
        if success_message:
            import urllib.parse
            try:
                success_message = urllib.parse.unquote(success_message)
            except:
                pass
        
        if error_message:
            import urllib.parse
            try:
                error_message = urllib.parse.unquote(error_message)
            except:
                pass
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Édition Configuration - GARDIA-M</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1000px;
                    margin: 0 auto;
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #eee;
                }}
                h1 {{
                    color: #333;
                    margin: 0;
                }}
                .back-btn {{
                    background-color: #666;
                    color: white;
                    padding: 8px 16px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-size: 14px;
                }}
                .back-btn:hover {{
                    background-color: #555;
                }}
                textarea {{
                    width: 100%;
                    height: 500px;
                    font-family: 'Courier New', monospace;
                    font-size: 14px;
                    padding: 15px;
                    border: 2px solid #ddd;
                    border-radius: 5px;
                    box-sizing: border-box;
                    resize: vertical;
                }}
                textarea:focus {{
                    border-color: #4CAF50;
                    outline: none;
                }}
                .form-actions {{
                    margin-top: 20px;
                    display: flex;
                    gap: 10px;
                }}
                .btn {{
                    padding: 12px 24px;
                    border: none;
                    border-radius: 5px;
                    font-size: 16px;
                    cursor: pointer;
                    text-decoration: none;
                    display: inline-block;
                }}
                .btn-primary {{
                    background-color: #4CAF50;
                    color: white;
                }}
                .btn-primary:hover {{
                    background-color: #45a049;
                }}
                .btn-secondary {{
                    background-color: #2196F3;
                    color: white;
                }}
                .btn-secondary:hover {{
                    background-color: #1976D2;
                }}
                .success {{
                    background-color: #e8f5e8;
                    color: #2e7d32;
                    padding: 10px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    border-left: 4px solid #4CAF50;
                }}
                .error {{
                    background-color: #ffebee;
                    color: #c62828;
                    padding: 10px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    border-left: 4px solid #f44336;
                }}
                .warning {{
                    background-color: #fff3e0;
                    color: #ef6c00;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    border-left: 4px solid #ff9800;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚙️ Édition de la configuration</h1>
                    <a href="/admin/dashboard" class="back-btn">← Retour</a>
                </div>
                
                {f'<div class="success">✅ {success_message}</div>' if success_message else ''}
                {f'<div class="error">❌ {error_message}</div>' if error_message else ''}
                
                <div class="warning">
                    <strong>⚠️ Attention:</strong> Modifiez cette configuration avec précaution. 
                    Une erreur de syntaxe peut empêcher le serveur de fonctionner. 
                    Sauvegardez toujours avant de modifier.
                    <br><br>
                    <strong>💡 Conseils:</strong>
                    <ul>
                        <li>Utilisez uniquement des guillemets droits (" et ') et non typographiques (" " ' ')</li>
                        <li>Les caractères accentués (é, à, ç, etc.) sont autorisés et préservés</li>
                        <li>Respectez l'indentation YAML (espaces, pas de tabulations)</li>
                        <li>Les mots de passe peuvent contenir: lettres, chiffres, accents, !@#$%^&*()-_=+</li>
                        <li>Évitez de copier-coller depuis Word (caractères invisibles)</li>
                    </ul>
                </div>
                
                <form method="post" action="/admin/config" accept-charset="UTF-8" enctype="application/x-www-form-urlencoded">
                    <textarea name="config_content" required>{config_content}</textarea>
                    
                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">💾 Sauvegarder</button>
                        <button type="button" class="btn btn-secondary" onclick="location.reload()">🔄 Recharger</button>
                        <a href="/admin/dashboard" class="btn" style="background-color: #666; color: white;">❌ Annuler</a>
                    </div>
                </form>
                
                <div style="margin-top: 30px; font-size: 12px; color: #666;">
                    <strong>Fichier:</strong> {self.config_file}<br>
                    <strong>Dernière modification:</strong> {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(os.path.getmtime(self.config_file))) if os.path.exists(self.config_file) else 'N/A'}
                </div>
            </div>
            
            <script>
                // Avertissement avant de quitter si des modifications non sauvegardées
                let originalContent = document.querySelector('textarea').value;
                
                window.addEventListener('beforeunload', function(e) {{
                    if (document.querySelector('textarea').value !== originalContent) {{
                        e.preventDefault();
                        e.returnValue = '';
                    }}
                }});
                
                // Marquer comme sauvegardé lors de la soumission
                document.querySelector('form').addEventListener('submit', function() {{
                    originalContent = document.querySelector('textarea').value;
                }});
            </script>
        </body>
        </html>
        """
    
    def admin_config_save(self):
        """Sauvegarde de la configuration avec correction d'encodage radicale"""
        if not self.check_admin_session():
            return redirect('/admin')
        
        logger.info("=== DEBUT SAUVEGARDE AVEC CORRECTION ENCODAGE ===")
        
        # Méthode radicale : récupérer les données brutes du POST
        try:
            # Récupérer les données POST brutes
            raw_post_data = request.body.read()
            logger.info(f"Données POST brutes reçues: {len(raw_post_data)} bytes")
            
            # Décoder les données POST
            if isinstance(raw_post_data, bytes):
                try:
                    # Essayer UTF-8 d'abord
                    post_string = raw_post_data.decode('utf-8')
                except UnicodeDecodeError:
                    # Fallback vers latin1
                    post_string = raw_post_data.decode('latin1')
                    logger.info("Décodage POST en latin1")
            else:
                post_string = str(raw_post_data)
            
            # Extraire le contenu du formulaire (après config_content=)
            import urllib.parse
            parsed_data = urllib.parse.parse_qs(post_string)
            
            if 'config_content' not in parsed_data:
                return redirect('/admin/config?error=Pas de donnees config_content')
            
            # Prendre le premier élément (peut y en avoir plusieurs)
            raw_content = parsed_data['config_content'][0]
            logger.info(f"Contenu brut extrait: {len(raw_content)} caractères")
            
        except Exception as extract_err:
            logger.error(f"Erreur extraction données: {extract_err}")
            # Fallback vers la méthode normale
            raw_content = request.forms.get('config_content', '')
            logger.info("Fallback vers méthode normale")
        
        # CORRECTION RADICALE DES ENCODAGES
        content = raw_content
        
        # Étape 1: Identifier le type de corruption
        logger.info("=== DETECTION CORRUPTION ENCODAGE ===")
        
        # Rechercher les patterns de corruption
        corruption_detected = False
        
        # Pattern 1: Double encodage UTF-8 (\xc3\x83\xc2\xa0 pour 'à')
        if 'Ã' in content and '€' in content:
            logger.info("Pattern détecté: Double encodage UTF-8 classique")
            corruption_detected = True
            # Méthode 1: Conversion via latin1
            try:
                temp_bytes = content.encode('latin1')
                temp_bytes = temp_bytes.replace(b'\xc3\x83\xe2\x82\xac', b'\xc3\xa0')  # à
                temp_bytes = temp_bytes.replace(b'\xc3\x83\xc2\xa0', b'\xc3\xa0')      # à variante
                content = temp_bytes.decode('utf-8')
                logger.info("Correction double encodage appliquée (méthode 1)")
            except:
                pass
        
        # Pattern 2: Corruption HTML/URL
        if '%C3%A0' in content:
            logger.info("Pattern détecté: Encodage URL")
            corruption_detected = True
            import urllib.parse
            content = urllib.parse.unquote(content)
        
        # Pattern 3: Corrections directes textuelles
        corrections = [
            ('Ã€', 'À'), ('Ãƒ', 'Ã'), ('Ã‚', 'Â'), ('Ãƒâ€š', 'Â'),
            ('Ã ', 'à'), ('Ãƒ ', 'à'), ('Ã¡', 'á'), ('Ã¢', 'â'),
            ('Ã£', 'ã'), ('Ã¤', 'ä'), ('Ã¥', 'å'), ('Ã§', 'ç'),
            ('Ã¨', 'è'), ('Ã©', 'é'), ('Ãª', 'ê'), ('Ã«', 'ë'),
            ('Ã¬', 'ì'), ('Ã­', 'í'), ('Ã®', 'î'), ('Ã¯', 'ï'),
            ('Ã±', 'ñ'), ('Ã²', 'ò'), ('Ã³', 'ó'), ('Ã´', 'ô'),
            ('Ãµ', 'õ'), ('Ã¶', 'ö'), ('Ã¹', 'ù'), ('Ãº', 'ú'),
            ('Ã»', 'û'), ('Ã¼', 'ü'), ('Ã½', 'ý'), ('Ã¿', 'ÿ'),
            # Corrections spécifiques détectées
            ('Ã€\u00a0', 'à'), ('Ã\u0081\u00a0', 'à'), 
            ('Secours Ã  Personnes', 'Secours à Personnes'),
            ('Secours Ã€ Personnes', 'Secours à Personnes'),
            ('Secours Ã\u0081 Personnes', 'Secours à Personnes'),
        ]
        
        corrections_applied = []
        for wrong, correct in corrections:
            if wrong in content:
                content = content.replace(wrong, correct)
                corrections_applied.append(f"{wrong} → {correct}")
                corruption_detected = True
        
        # Étape 2: Nettoyage général
        content = content.replace('\r\n', '\n').replace('\r', '\n').strip()
        
        if corruption_detected:
            logger.info(f"Corrections appliquées: {len(corrections_applied)}")
            for correction in corrections_applied[:5]:  # Limiter l'affichage
                logger.info(f"  - {correction}")
        else:
            logger.info("Aucune corruption détectée")
        
        # Étape 3: Validation YAML
        try:
            parsed = yaml.safe_load(content)
            if not parsed:
                return redirect('/admin/config?error=Configuration vide')
            logger.info("YAML validé avec succès")
        except Exception as yaml_err:
            logger.error(f"Erreur YAML: {yaml_err}")
            return redirect(f'/admin/config?error=YAML invalide')
        
        # Étape 4: Sauvegarde forcée en UTF-8
        try:
            # Créer une sauvegarde avant modification
            import shutil
            backup_file = f"{self.config_file}.bak"
            if os.path.exists(self.config_file):
                shutil.copy2(self.config_file, backup_file)
            
            # Écriture avec encodage explicite UTF-8 sans BOM
            with open(self.config_file, 'wb') as f:
                f.write(content.encode('utf-8'))
            
            logger.info("Sauvegarde réussie en UTF-8 binaire")
            
        except Exception as write_err:
            logger.error(f"Erreur écriture: {write_err}")
            return redirect('/admin/config?error=Erreur ecriture fichier')
        
        # Étape 5: Vérification finale
        try:
            # Relire et vérifier
            with open(self.config_file, 'r', encoding='utf-8') as f:
                verification = f.read()
            
            logger.info(f"Verification: fichier relu, {len(verification)} caractères")
            
            # Test YAML final
            yaml.safe_load(verification)
            logger.info("Verification: YAML valide")
            
            # Vérifier les caractères spécifiques
            if 'Secours à Personnes' in verification:
                logger.info("✅ SUCCES: 'Secours à Personnes' correctement écrit")
                success_msg = "Configuration sauvee - encodage UTF-8 corrige !"
            elif 'Secours' in verification:
                secours_line = [line for line in verification.split('\n') if 'Secours' in line]
                if secours_line:
                    logger.info(f"⚠️ Ligne Secours finale: '{secours_line[0]}'")
                    success_msg = "Configuration sauvee - verifiez les accents"
                else:
                    success_msg = "Configuration sauvee"
            else:
                success_msg = "Configuration sauvee avec succes"
            
            logger.info("=== SAUVEGARDE TERMINEE AVEC SUCCES ===")
            
        except Exception as verify_err:
            logger.error(f"Erreur vérification: {verify_err}")
            # Même si la vérification échoue, le fichier est sauvé donc on considère que c'est OK
            logger.info("Fichier sauvé malgré erreur de vérification")
            success_msg = "Configuration sauvee avec succes (verification ignoree)"
        
        # Toujours retourner un succès puisque le log dit "TERMINEE AVEC SUCCES"
        # Encoder le message pour éviter les problèmes d'affichage
        import urllib.parse
        encoded_msg = urllib.parse.quote(success_msg)
        return redirect(f'/admin/config?success={encoded_msg}')
    
    def admin_logout(self):
        """Déconnexion administrateur"""
        session_id = request.get_cookie('admin_session')
        if session_id and session_id in self.admin_sessions:
            del self.admin_sessions[session_id]
            logger.info(f"Déconnexion admin pour session {session_id}")
        
        response.delete_cookie('admin_session')
        return redirect('/admin?success=Déconnexion réussie')
    
    def run(self):
        """Démarre le serveur Bottle"""
        host = self.config.get('web.host')
        port = self.config.get('web.port')
        debug = self.config.get('web.debug')
        
        print("=" * 60)
        print("🚨 Gaulix Alerte Réseau D'urgence Intervention Assistée Meshtastic - GARDIA-M")
        print(f"📌 Version: {self.config.get('app.version', VERSION)} ({self.config.get('app.build_date', BUILD_DATE)})")
        print("=" * 60)
        print(f"🌐 Serveur web: http://{host}:{port}")
        print(f"📡 Meshtastic: {self.config.get('meshtastic.device')}")
        print(f"📱 Canal: {self.config.get('meshtastic.channel_index')} ({self.config.get('meshtastic.channel_name')})")
        print(f"📄 Template: {self.config.get('web.template_dir')}/index.html")
        if self.config.get('admin.enabled', True):
            print(f"🔐 Administration: http://{host}:{port}/admin")
        print("=" * 60)
        
        try:
            run(self.app, host=host, port=port, debug=debug, quiet=not debug)
        except KeyboardInterrupt:
            print("\n🛑 Arrêt du serveur...")
            self.meshtastic_handler.close()
            print("✅ Serveur arrêté proprement")
        except Exception as e:
            logger.error(f"Erreur fatale: {e}")
            self.meshtastic_handler.close()

def main():
    """Fonction principale"""
    config_file = 'config.yaml'
    
    # Vérifier si un fichier de configuration a été spécifié
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    # Créer et lancer l'application
    app = EmergencyApp(config_file)
    app.run()

if __name__ == "__main__":
    main()