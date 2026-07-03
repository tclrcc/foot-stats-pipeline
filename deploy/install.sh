#!/usr/bin/env bash
#
# Installe et démarre les services persistants (API + Web) et le reverse proxy.
# À lancer depuis la racine du dépôt : bash deploy/install.sh
#
# Prérequis :
#   - .venv Python créé avec les dépendances (pip install -r requirements.txt)
#   - Base générée (python src/refresh_all.py)
#   - Frontend buildé (cd web && npm install && npm run build)
#   - nginx installé (sudo apt install -y nginx)

set -e
REPO="/home/ubuntu/foot-stats-pipeline"
cd "$REPO"

echo "▶ 1/4 Installation des services systemd…"
sudo cp deploy/systemd/footstats-api.service /etc/systemd/system/
sudo cp deploy/systemd/footstats-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now footstats-api.service
sudo systemctl enable --now footstats-web.service

echo "▶ 2/4 Vérification des services…"
sleep 3
sudo systemctl --no-pager --lines=0 status footstats-api.service || true
sudo systemctl --no-pager --lines=0 status footstats-web.service || true

echo "▶ 3/4 Configuration nginx…"
sudo cp deploy/nginx/footstats.conf /etc/nginx/sites-available/footstats.conf
sudo ln -sf /etc/nginx/sites-available/footstats.conf /etc/nginx/sites-enabled/footstats.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "▶ 4/4 Terminé."
echo "  API   : http://127.0.0.1:8000/health (interne)"
echo "  Site  : http://<IP_ou_domaine>/ (via nginx port 80)"
echo ""
echo "Commandes utiles :"
echo "  sudo systemctl status footstats-web    # état du frontend"
echo "  sudo journalctl -u footstats-api -f     # logs API en direct"
echo "  sudo journalctl -u footstats-web -f     # logs Web en direct"
