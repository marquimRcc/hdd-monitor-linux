#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  HddMonitor - Instalador automático
#  Detecta a distro, instala dependências e cria atalho
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=8
DESKTOP_FILE="$HOME/.local/share/applications/hddmonitor.desktop"

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }

# ── Detecta distro ──────────────────────────────────────────
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-$DISTRO_ID}"
        DISTRO_NAME="${PRETTY_NAME:-$DISTRO_ID}"
    else
        DISTRO_ID="unknown"
        DISTRO_LIKE="unknown"
        DISTRO_NAME="Desconhecida"
    fi
    info "Distro detectada: $DISTRO_NAME"
}

# ── Detecta melhor Python disponível (>= 3.8) ──────────────
find_python() {
    local candidates=(
        python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3
    )
    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
            if [ -n "$ver" ]; then
                local major minor
                major=$(echo "$ver" | cut -d. -f1)
                minor=$(echo "$ver" | cut -d. -f2)
                if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
                    PYTHON_CMD="$cmd"
                    PYTHON_VER="$ver"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

# ── Instala pacotes do sistema ──────────────────────────────
install_system_deps() {
    info "Instalando dependências do sistema..."

    case "$DISTRO_ID" in
        opensuse*|sles)
            sudo zypper install -y python3 python3-pip python3-venv python3-tk \
                smartmontools hdparm e2fsprogs f3 || true
            ;;
        ubuntu|debian|linuxmint|pop)
            sudo apt update
            sudo apt install -y python3 python3-pip python3-venv python3-tk \
                smartmontools hdparm e2fsprogs f3 || true
            ;;
        fedora)
            sudo dnf install -y python3 python3-pip python3-tkinter \
                smartmontools hdparm e2fsprogs f3 || true
            ;;
        arch|manjaro|endeavouros)
            sudo pacman -Sy --noconfirm python python-pip tk \
                smartmontools hdparm e2fsprogs f3 || true
            ;;
        *)
            # Tenta adivinhar pelo ID_LIKE
            if echo "$DISTRO_LIKE" | grep -qi "suse"; then
                sudo zypper install -y python3 python3-pip python3-venv python3-tk \
                    smartmontools hdparm e2fsprogs f3 || true
            elif echo "$DISTRO_LIKE" | grep -qi "debian\|ubuntu"; then
                sudo apt update
                sudo apt install -y python3 python3-pip python3-venv python3-tk \
                    smartmontools hdparm e2fsprogs f3 || true
            elif echo "$DISTRO_LIKE" | grep -qi "fedora\|rhel"; then
                sudo dnf install -y python3 python3-pip python3-tkinter \
                    smartmontools hdparm e2fsprogs f3 || true
            else
                warn "Distro não reconhecida. Instale manualmente:"
                warn "  Python 3.8+, pip, tkinter, smartmontools, hdparm, e2fsprogs, f3"
            fi
            ;;
    esac
}

# ── Cria venv e instala deps Python ─────────────────────────
setup_venv() {
    info "Configurando ambiente virtual Python..."

    if [ ! -d "$VENV_DIR" ]; then
        "$PYTHON_CMD" -m venv "$VENV_DIR" 2>/dev/null || {
            # Fallback: tenta sem venv (algumas distros não incluem por padrão)
            warn "Falha ao criar venv. Tentando instalar python3-venv..."
            case "$DISTRO_ID" in
                ubuntu|debian|linuxmint|pop)
                    sudo apt install -y python3-venv
                    ;;
                opensuse*|sles)
                    sudo zypper install -y python3-venv
                    ;;
            esac
            "$PYTHON_CMD" -m venv "$VENV_DIR" || error "Não foi possível criar o ambiente virtual"
        }
    fi

    # Ativa e instala
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install customtkinter psutil -q
    deactivate
    success "Dependências Python instaladas no venv"
}

# ── Cria script launcher ────────────────────────────────────
create_launcher() {
    info "Criando launcher..."

    cat > "$APP_DIR/run.sh" << 'LAUNCHER'
#!/usr/bin/env bash
# HddMonitor - Launcher
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Ambiente não configurado. Execute primeiro:"
    echo "   bash install.sh"
    exit 1
fi

PYTHON="$VENV_DIR/bin/python"

# Verifica se precisa de sudo para SMART completo
if [ "$(id -u)" -ne 0 ]; then
    echo ""
    echo "💡 Para acesso SMART completo, use:"
    echo "   sudo -E bash run.sh"
    echo ""
    echo "   Iniciando sem sudo (funcionalidade limitada)..."
    echo ""
fi

exec "$PYTHON" "$APP_DIR/app.py" "$@"
LAUNCHER

    chmod +x "$APP_DIR/run.sh"
    success "Launcher criado: run.sh"
}

# ── Cria atalho .desktop ────────────────────────────────────
create_desktop_entry() {
    info "Criando atalho no menu de aplicativos..."

    mkdir -p "$(dirname "$DESKTOP_FILE")"

    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=HDD Monitor
Comment=Diagnóstico e monitoramento de discos (HDD/SSD/NVMe)
Exec=bash -c 'pkexec env DISPLAY=\$DISPLAY XAUTHORITY=\$XAUTHORITY $APP_DIR/.venv/bin/python $APP_DIR/app.py'
Icon=drive-harddisk
Terminal=false
Type=Application
Categories=System;Monitor;
Keywords=disk;hdd;ssd;nvme;smart;diagnostic;
EOF

    # Também cria uma versão sem pkexec (sem root)
    cat > "${DESKTOP_FILE%.desktop}-noroot.desktop" << EOF
[Desktop Entry]
Name=HDD Monitor (sem root)
Comment=Diagnóstico e monitoramento de discos (funcionalidade limitada)
Exec=$APP_DIR/.venv/bin/python $APP_DIR/app.py
Icon=drive-harddisk
Terminal=false
Type=Application
Categories=System;Monitor;
Keywords=disk;hdd;ssd;nvme;smart;diagnostic;
EOF

    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    success "Atalho criado no menu de aplicativos"
}

# ── Verifica ferramentas opcionais ──────────────────────────
check_tools() {
    echo ""
    info "Verificando ferramentas do sistema:"
    local tools=("smartctl:smartmontools" "hdparm:hdparm" "badblocks:e2fsprogs" "f3probe:f3")
    local missing=()
    for entry in "${tools[@]}"; do
        local cmd="${entry%%:*}"
        local pkg="${entry##*:}"
        if command -v "$cmd" &>/dev/null; then
            success "  $cmd encontrado"
        else
            warn "  $cmd NÃO encontrado (pacote: $pkg)"
            missing+=("$pkg")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        warn "Pacotes faltando (opcional): ${missing[*]}"
    fi
}

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  💾 HddMonitor - Instalador                  ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo ""

detect_distro

# 1. Python disponível?
if find_python; then
    success "Python encontrado: $PYTHON_CMD ($PYTHON_VER)"
else
    warn "Python >= $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR não encontrado. Instalando..."
    install_system_deps
    if ! find_python; then
        error "Não foi possível instalar Python. Instale manualmente: python3 >= 3.8"
    fi
    success "Python instalado: $PYTHON_CMD ($PYTHON_VER)"
fi

# 2. Instala deps do sistema (smartmontools, etc)
install_system_deps

# 3. Configura venv + deps Python
setup_venv

# 4. Cria launcher
create_launcher

# 5. Cria atalho .desktop
create_desktop_entry

# 6. Verifica ferramentas
check_tools

# Resultado final
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Instalação concluída!${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  Para executar:"
echo -e "    ${BOLD}bash run.sh${NC}              (sem root, funcionalidade limitada)"
echo -e "    ${BOLD}sudo -E bash run.sh${NC}      (com root, acesso SMART completo)"
echo ""
echo -e "  Ou pelo menu de aplicativos: ${BOLD}HDD Monitor${NC}"
echo ""