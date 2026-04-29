#!/bin/bash
# =============================================================================
# update.sh — Actualizar y monitorear Aduanex
# Uso: bash update.sh [--full]
#   Sin flags  : git pull + restart + logs del servicio
#   --full     : git pull + upgrade con log detallado de Odoo + restart
# =============================================================================

ODOO_BIN="/opt/odoo18/odoo/odoo-bin"
ODOO_VENV="/opt/odoo18/venv/bin/python"
ODOO_DB="aduanex_pro_v1"
ODOO_USER="odoo18"
MODULE="modulo_aduana_odoo"
SERVICE="odoo18"

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${CYAN}==>${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }

# ── 1. Git pull ───────────────────────────────────────────────────────────────
step "Actualizando código (git pull)..."
git pull
if [ $? -ne 0 ]; then
    fail "git pull falló. Revisa conflictos antes de continuar."
    exit 1
fi
ok "Código actualizado"

# ── Modo full: upgrade con log detallado ─────────────────────────────────────
if [ "$1" == "--full" ]; then
    step "Deteniendo servicio para upgrade..."
    sudo systemctl stop $SERVICE
    sleep 2

    step "Corriendo upgrade del módulo (log completo)..."
    echo -e "${YELLOW}--- INICIO LOG ODOO ---${NC}"
    sudo -u $ODOO_USER $ODOO_VENV $ODOO_BIN \
        -u $MODULE \
        -d $ODOO_DB \
        --stop-after-init \
        --log-level=info 2>&1
    UPGRADE_EXIT=$?
    echo -e "${YELLOW}--- FIN LOG ODOO ---${NC}"

    if [ $UPGRADE_EXIT -ne 0 ]; then
        fail "El upgrade terminó con errores (código $UPGRADE_EXIT). Revisa el log arriba."
        warn "El servicio NO se reinició para que puedas diagnosticar."
        exit 1
    fi
    ok "Upgrade completado sin errores"

    step "Reiniciando servicio..."
    sudo systemctl start $SERVICE
    sleep 3
    STATUS=$(systemctl is-active $SERVICE)
    if [ "$STATUS" == "active" ]; then
        ok "Servicio activo"
    else
        fail "El servicio no levantó (status: $STATUS)"
        sudo journalctl -u $SERVICE -n 30 --no-pager
        exit 1
    fi

# ── Modo rápido: restart normal ───────────────────────────────────────────────
else
    step "Reiniciando servicio..."
    sudo systemctl restart $SERVICE
    sleep 2
    STATUS=$(systemctl is-active $SERVICE)
    if [ "$STATUS" == "active" ]; then
        ok "Servicio activo"
    else
        fail "El servicio no levantó (status: $STATUS)"
        sudo journalctl -u $SERVICE -n 50 --no-pager
        exit 1
    fi
fi

# ── 3. Monitorear logs ────────────────────────────────────────────────────────
step "Monitoreando logs (Ctrl+C para salir)..."
sudo journalctl -u $SERVICE -f
