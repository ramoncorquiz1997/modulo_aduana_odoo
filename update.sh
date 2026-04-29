#!/bin/bash
# =============================================================================
# update.sh — Actualizar y monitorear Aduanex
# Uso: bash update.sh [--full]
#   Sin flags  : git pull + restart + journalctl -f continuo
#   --full     : git pull + verificar imports + upgrade con log completo
#                + restart + journalctl -f continuo
# =============================================================================

ODOO_BIN="/opt/odoo18/odoo/odoo-bin"
ODOO_VENV="/opt/odoo18/venv/bin/python"
ODOO_ADDONS="/opt/odoo18/addons-custom"
ODOO_DB="aduanex_pro_v1"
ODOO_USER="odoo18"
MODULE="modulo_aduana_odoo"
SERVICE="odoo18"

# Config file de Odoo (necesario para que odoo-bin vea addons-custom)
# Intenta rutas conocidas, luego busca con find si no hay ninguna
ODOO_CONF=""
for _f in /etc/odoo18/odoo.conf /etc/odoo18.conf /etc/odoo/odoo18.conf /opt/odoo18/odoo18.conf /opt/odoo18/odoo.conf /etc/odoo.conf; do
    if [ -f "$_f" ]; then
        ODOO_CONF="$_f"
        break
    fi
done
# Si no encontró nada, busca con find
if [ -z "$ODOO_CONF" ]; then
    ODOO_CONF=$(find /etc /opt/odoo18 -maxdepth 3 -name "*.conf" 2>/dev/null \
        | xargs grep -l "addons_path" 2>/dev/null | head -1)
fi

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

    # Mostrar qué config se usará
    if [ -n "$ODOO_CONF" ]; then
        ok "Config detectado: $ODOO_CONF"
    else
        warn "Config NO encontrado en rutas conocidas — se usará --addons-path"
        warn "Si falla, ejecuta: sudo find /etc /opt/odoo18 -name '*.conf' | xargs grep -l addons_path 2>/dev/null"
        warn "Luego edita ODOO_CONF= en este script"
    fi

    step "Deteniendo servicio para upgrade..."
    sudo systemctl stop $SERVICE
    sleep 2

    step "Corriendo upgrade del módulo (log completo)..."
    if [ -n "$ODOO_CONF" ]; then
        ok "Usando config: $ODOO_CONF"
    else
        warn "No se encontró config de Odoo — se usará --addons-path directo"
    fi
    echo ""

    if [ -n "$ODOO_CONF" ]; then
        UPGRADE_LOG=$(sudo -u $ODOO_USER $ODOO_VENV $ODOO_BIN \
            --config "$ODOO_CONF" \
            -u $MODULE \
            -d $ODOO_DB \
            --stop-after-init \
            --log-level=info 2>&1)
    else
        UPGRADE_LOG=$(sudo -u $ODOO_USER $ODOO_VENV $ODOO_BIN \
            --addons-path "/opt/odoo18/odoo/addons,$ODOO_ADDONS" \
            -u $MODULE \
            -d $ODOO_DB \
            --stop-after-init \
            --log-level=info 2>&1)
    fi

    echo "$UPGRADE_LOG"

    # Detectar errores reales aunque el exit code sea 0
    if echo "$UPGRADE_LOG" | grep -qE "not installable|inconsistent states|ERROR|Traceback"; then
        echo ""
        fail "Se detectaron errores en el upgrade:"
        echo "$UPGRADE_LOG" | grep -E "not installable|inconsistent|ERROR|Traceback|File \"|raise " | head -30
        warn "El servicio NO se reinició. Revisa los errores arriba."
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

# ── Monitorear logs en tiempo real (siempre al final) ────────────────────────
step "Monitoreando logs en tiempo real (Ctrl+C para salir)..."
sudo journalctl -u $SERVICE -f -n 50
