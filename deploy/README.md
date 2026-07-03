# Déploiement

Mise en production sur VPS (Ubuntu) : services persistants + reverse proxy + HTTPS.

## Architecture

```
Internet ──80/443──> nginx ──proxy──> Next.js (127.0.0.1:3000) ──> FastAPI (127.0.0.1:8000)
```

Seuls les ports 80 et 443 sont exposés. L'API et le frontend restent internes.

## Prérequis

```bash
# venv Python + dépendances
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/refresh_all.py

# frontend buildé
cd web && npm install && npm run build && cd ..

# nginx
sudo apt install -y nginx
```

## Installation des services

```bash
bash deploy/install.sh
```

Cela installe deux services systemd (`footstats-api`, `footstats-web`) qui
démarrent au boot et redémarrent en cas de crash, et configure nginx en
reverse proxy sur le port 80.

## HTTPS (nécessite un nom de domaine)

Let's Encrypt ne délivre pas de certificat pour une IP nue. Il faut un domaine
pointant vers l'IP du VPS (enregistrement A).

1. Édite `deploy/nginx/footstats.conf` : remplace `server_name _;` par ton domaine.
2. Recharge : `sudo cp deploy/nginx/footstats.conf /etc/nginx/sites-available/ && sudo systemctl reload nginx`
3. Installe certbot et génère le certificat :

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pitch.tondomaine.fr
```

Certbot configure automatiquement le HTTPS et le renouvellement.

## Mise à jour de l'app

```bash
git pull
# si le backend a changé :
sudo systemctl restart footstats-api
# si le frontend a changé :
cd web && npm run build && cd .. && sudo systemctl restart footstats-web
```
