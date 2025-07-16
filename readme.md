# Gaulix Alerte Réseau D'urgence Intervention Assistée Meshtastic - GARDIA-M v1.0.0

Serveur d'urgence pour OpenWrt avec transmission Meshtastic/Gaulix sur le canal Fr-Emcom.

Script créé via claude.ai, idée et correction F4FWH

## 🚀 Installation

### 1. Prérequis OpenWrt
```bash
opkg update
opkg install python3 python3-pip
opkg install python3-dbus-fast
opkg install python3-yaml
opkg install kmod-usb-serial-cp210x
opkg install kmod-usb-acm
pip3 install bottle meshtastic pubsub
```

### 2. Structure des fichiers
```
emergency-server/
├── emergency_server.py    # Script principal
├── config.yaml           # Configuration (généré automatiquement)
├── templates/
│   └── index.html        # Template HTML de la page
└── static/               # Fichiers statiques (optionnel)
    ├── logo1.png         # Logo 1 (optionnel)
    ├── logo2.png         # Logo 2 (optionnel)
    └── logo3.png         # Logo 3 (optionnel)
```

### 3. Installation
```bash
# Créer le répertoire
mkdir -p /opt/emergency-server/templates
mkdir -p /opt/emergency-server/static

# Copier les fichiers
cp emergency_server.py /opt/emergency-server/
cp index.html /opt/emergency-server/templates/

# Copier les logos (optionnel)
# cp logo1.png /opt/emergency-server/static/
# cp logo2.png /opt/emergency-server/static/
# cp logo3.png /opt/emergency-server/static/

# Rendre exécutable
chmod +x /opt/emergency-server/emergency_server.py
```

## ⚙️ Configuration

Le fichier `config.yaml` est créé automatiquement au premier lancement avec les valeurs par défaut.

### Configuration principale :
```yaml
app:
  name: Gaulix Alerte Réseau D'urgence Intervention Assistée Meshtastic - GARDIA-M
  version: 1.0.0
  build_date: "2025-07-15"

web:
  debug: false
  host: 0.0.0.0
  port: 8080
  template_dir: ./templates
  static_dir: ./static

admin:
  enabled: true
  username: admin
  password: admin123      # À CHANGER IMPÉRATIVEMENT !
  session_timeout: 3600

meshtastic:
  channel_index: 1
  channel_name: Fr-Emcom
  device: /dev/ttyACM0		#ou /dev/ttyACM0
  max_message_length: 200

logging:
  format: '%(asctime)s - %(levelname)s - %(message)s'
  level: INFO
  log_all_data: true
  
alert_types:
  Autre: 3
  Incendie: 1
  Secours à Personnes: 2

logos:
  enabled: true
  logo1:
    file: logo1.png
    alt: Logo Organisation 1
    link: ''
  logo2:
    file: logo2.png
    alt: Logo Organisation 2
    link: ''
  logo3:
    file: logo3.png
    alt: Logo Organisation 3
    link: ''
```

## 🖼️ **Configuration des logos**

### Ajout de logos optionnels :

1. **Placez vos logos** dans le répertoire `static/` :
   - `logo1.png`, `logo2.png`, `logo3.png`
   - Formats supportés : PNG, JPG, GIF, SVG
   - Taille recommandée : 120x60 pixels maximum

2. **Configuration dans `config.yaml`** :
```yaml
logos:
  enabled: true  # Activer/désactiver l'affichage
  logo1:
    file: "mairie.png"
    alt: "Mairie de la ville"
    link: "https://www.mairie-ville.fr"  # Lien optionnel
  logo2:
    file: "prefecture.png"
    alt: "Préfecture"
    link: ""  # Pas de lien
  logo3:
    file: "pompiers.png"
    alt: "Sapeurs-Pompiers"
    link: "https://www.pompiers.fr"
```

3. **Désactiver les logos** :
```yaml
logos:
  enabled: false  # Les logos ne s'afficheront pas
```

## 🔧 Utilisation

### Démarrage simple
```bash
cd /opt/emergency-server
python3 emergency_server.py
```

### Démarrage avec configuration personnalisée
```bash
python3 emergency_server.py /path/to/custom_config.yaml
```

### Accès aux interfaces
- **Formulaire d'urgence** : `http://IP:8080/`
- **Interface d'administration** : `http://IP:8080/admin`

## 🛠️ **Interface d'Administration**

### Fonctionnalités de l'admin :
1. **Page de connexion sécurisée** avec authentification
2. **Tableau de bord** avec état du système
3. **Éditeur de configuration** YAML intégré
4. **Gestion des sessions** avec timeout configurable
5. **Sauvegarde automatique** avant modification

### Sécurité :
- **Authentification obligatoire** avec username/password
- **Sessions temporaires** avec expiration automatique
- **Logging des connexions** et modifications
- **Sauvegarde automatique** avant chaque modification
- **Validation YAML** avant sauvegarde

### Première connexion :
```
URL: http://IP:8080/admin
Username: admin
Password: admin123
```

**⚠️ IMPORTANT : Changez immédiatement le mot de passe par défaut !**

### Configuration de l'admin :
```yaml
admin:
  enabled: true               # Activer/désactiver l'interface
  username: "votre_admin"     # Nom d'utilisateur personnalisé
  password: "MotDePasseComplexe123!"  # Mot de passe fort
  session_timeout: 1800       # 30 minutes au lieu d'1 heure
```

### Service systemd (optionnel)
Créer `/etc/init.d/guardia-m` :
```ini
#!/bin/sh /etc/rc.common

START=99
STOP=10

SCRIPT="emergency_server.py"
WORKDIR="/opt/emergency-server"
LOGFILE="/tmp/emergency-server.log"

start() {
    echo "Starting Emergency Server..."
    cd "$WORKDIR" || {
        echo "Failed to change directory to $WORKDIR"
        return 1
    }

    python3 "$SCRIPT" > "$LOGFILE" 2>&1 &
    echo $! > /var/run/emergency-server.pid
}

stop() {
    echo "Stopping Emergency Server..."
    if [ -f /var/run/emergency-server.pid ]; then
        kill "$(cat /var/run/emergency-server.pid)" 2>/dev/null
        rm -f /var/run/emergency-server.pid
    else
        # fallback si le PID n'existe plus
        pkill -f "$WORKDIR/$SCRIPT"
    fi
}
```

Puis :
```bash
/etc/init.d/guardia-m enable
/etc/init.d/guardia-m start
```

## 📱 API Endpoints

- `GET /` - Page du formulaire d'urgence
- `POST /submit` - Soumission du formulaire
- `GET /health` - État de santé du service
- `GET /version` - Informations de version
- `GET /static/<filename>` - Fichiers statiques (logos, CSS, JS)

### Endpoints d'administration :
- `GET /admin` - Page de connexion admin
- `POST /admin/login` - Authentification admin
- `GET /admin/dashboard` - Tableau de bord admin
- `GET /admin/config` - Édition de la configuration
- `POST /admin/config` - Sauvegarde de la configuration
- `GET /admin/logout` - Déconnexion admin

### Exemples d'utilisation :

#### Health check
```bash
curl http://192.168.1.1:8080/health
```
Réponse :
```json
{
  "status": "OK",
  "version": "1.2.0",
  "meshtastic": "OK",
  "template_file": "FOUND",
  "timestamp": "2025-07-15 14:30:22"
}
```

#### Version info
```bash
curl http://192.168.1.1:8080/version
```

## 📝 Logs

### Exemple de logs lors d'une alerte :
```
2025-07-15 14:30:22 - INFO - ==================================================
2025-07-15 14:30:22 - INFO - 📝 NOUVELLE ALERTE REÇUE
2025-07-15 14:30:22 - INFO - Nom/Prénom: Jean Dupont
2025-07-15 14:30:22 - INFO - Téléphone: 06.12.34.56.78
2025-07-15 14:30:22 - INFO - Adresse: 123 Rue de la Paix, Caen
2025-07-15 14:30:22 - INFO - Type sinistre: Incendie
2025-07-15 14:30:22 - INFO - Timestamp: 15/07/2025 14:30:22
2025-07-15 14:30:22 - INFO - IP source: 192.168.1.100
2025-07-15 14:30:22 - INFO - ==================================================
2025-07-15 14:30:22 - INFO - Message JSON final: 89 caractères
2025-07-15 14:30:22 - INFO - Contenu: {"type":1,"nom":"Jean Dupont","tel":"06.12.34.56.78","adresse":"123 Rue de la Paix, Caen"}
2025-07-15 14:30:22 - INFO - 📡 Message envoyé sur canal 1 (Fr-Emcom)
2025-07-15 14:30:22 - INFO - ✅ Alerte envoyée avec succès - Jean Dupont - Incendie
```

#### Message Meshtastic envoyé :
```json
{"type":1,"nom":"Jean Dupont","tel":"06.12.34.56.78","adresse":"123 Rue de la Paix, Caen"}
```

#### Décodage du message :
- **Type 1** = Incendie
- **Nom** = Jean Dupont  
- **Téléphone** = 06.12.34.56.78
- **Adresse** = 123 Rue de la Paix, Caen

## 🛡️ Sécurité

### Logging des données personnelles
Pour désactiver le logging des données personnelles :
```yaml
logging:
  log_all_data: false
```

### Limite de caractères Meshtastic
Le système vérifie automatiquement la limite de 200 caractères et tronque intelligemment si nécessaire.

## 🔧 Personnalisation

### Template HTML
Le fichier `templates/index.html` peut être personnalisé. Variables disponibles :
- `{{app_version}}` - Version de l'application
- `{{channel_name}}` - Nom du canal Meshtastic
- `{{channel_index}}` - Index du canal
- `<!-- SUCCESS_MESSAGE -->` - Placeholder pour messages de succès
- `<!-- ERROR_MESSAGE -->` - Placeholder pour messages d'erreur

### Stratégie de troncature
La troncature des messages suit cette priorité (max 200caractères dans un message):
1. Raccourcissement de l'adresse (> 50 caractères)
2. Raccourcissement des détails (> 50 caractères)
3. Format minimal
4. Troncature brutale si nécessaire

## 📊 Monitoring

### Surveillance avec health check
```bash
#!/bin/bash
# Script de surveillance
STATUS=$(curl -s http://localhost:8080/health | jq -r '.status')
if [ "$STATUS" != "OK" ]; then
    echo "ALERTE: Service emergency-server en erreur"
    # Ajouter notification (email, webhook, etc.)
fi
```

## 🐛 Dépannage

### Problèmes courants

#### Template non trouvé
```
2025-07-15 14:30:22 - WARNING - Template non trouvé: ./templates/index.html, utilisation du template intégré
```
Solution : Vérifier que le fichier `templates/index.html` existe et est lisible.

#### Erreur Meshtastic
```
2025-07-15 14:30:22 - ERROR - Erreur connexion Meshtastic: [Errno 2] No such file or directory: '/dev/ttyUSB0'
```
Solution : Vérifier le port série dans la configuration.

#### Message trop long
```
2025-07-15 14:30:22 - WARNING - Message trop long (200 caractères), troncature nécessaire
```
Normal : Le système tronque automatiquement pour respecter la limite Meshtastic.

## 📋 Changelog

### v1.0.0 (2025-07-16)

