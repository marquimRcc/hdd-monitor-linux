#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
DESKTOP_FILE="$HOME/.local/share/applications/hddmonitor.desktop"
PYTHON_CMD=""

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERRO]${NC} $*"; exit 1; }

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

find_python311() {
    for cmd in python3.11 python311; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
            if [ "$ver" = "3.11" ]; then
                PYTHON_CMD="$(command -v "$cmd")"
                return 0
            fi
        fi
    done
    return 1
}

install_python311() {
    info "Instalando Python 3.11..."

    case "$DISTRO_ID" in
        opensuse*|sles|regataos)
            sudo zypper install -y python311 python311-pip python311-tk python311-venv 2>/dev/null \
                || sudo zypper install -y python3.11 python3.11-pip python3.11-tk python3.11-venv 2>/dev/null \
                || sudo zypper install -y python311-base python311-pip python311-tk 2>/dev/null \
                || {
                    warn "Pacote python311 não encontrado nos repos padrão."
                    warn "Tentando via devel:languages:python..."
                    sudo zypper ar -f "https://download.opensuse.org/repositories/devel:/languages:/python/openSUSE_Tumbleweed/" devel-python 2>/dev/null || true
                    sudo zypper --gpg-auto-import-keys ref
                    sudo zypper install -y python311 python311-pip python311-tk 2>/dev/null || true
                }
            ;;
        ubuntu|pop)
            sudo apt update
            if ! apt-cache show python3.11 &>/dev/null; then
                info "Adicionando PPA deadsnakes..."
                sudo apt install -y software-properties-common
                sudo add-apt-repository -y ppa:deadsnakes/ppa
                sudo apt update
            fi
            sudo apt install -y python3.11 python3.11-venv python3.11-tk python3.11-distutils
            if ! python3.11 -m pip --version &>/dev/null; then
                curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.11
            fi
            ;;
        debian)
            sudo apt update
            sudo apt install -y python3.11 python3.11-venv python3.11-tk 2>/dev/null || {
                warn "python3.11 não disponível nos repos do Debian."
                install_python311_from_source
            }
            ;;
        linuxmint)
            sudo apt update
            if ! apt-cache show python3.11 &>/dev/null; then
                sudo apt install -y software-properties-common
                sudo add-apt-repository -y ppa:deadsnakes/ppa
                sudo apt update
            fi
            sudo apt install -y python3.11 python3.11-venv python3.11-tk python3.11-distutils
            if ! python3.11 -m pip --version &>/dev/null; then
                curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.11
            fi
            ;;
        fedora)
            sudo dnf install -y python3.11 python3.11-tkinter python3.11-pip 2>/dev/null || {
                install_python311_from_source
            }
            ;;
        arch|manjaro|endeavouros)
            if command -v yay &>/dev/null; then
                yay -S --noconfirm python311 2>/dev/null || true
            elif command -v paru &>/dev/null; then
                paru -S --noconfirm python311 2>/dev/null || true
            fi
            if ! find_python311; then
                install_python311_from_source
            fi
            ;;
        *)
            if echo "$DISTRO_LIKE" | grep -qi "suse"; then
                sudo zypper install -y python311 python311-pip python311-tk 2>/dev/null || true
            elif echo "$DISTRO_LIKE" | grep -qi "debian\|ubuntu"; then
                sudo apt update
                sudo apt install -y python3.11 python3.11-venv python3.11-tk 2>/dev/null || {
                    sudo apt install -y software-properties-common
                    sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
                    sudo apt update
                    sudo apt install -y python3.11 python3.11-venv python3.11-tk 2>/dev/null || true
                }
            elif echo "$DISTRO_LIKE" | grep -qi "fedora\|rhel"; then
                sudo dnf install -y python3.11 python3.11-tkinter 2>/dev/null || true
            else
                install_python311_from_source
            fi
            ;;
    esac
}

install_python311_from_source() {
    info "Compilando Python 3.11.9 do source..."

    if command -v apt &>/dev/null; then
        sudo apt install -y build-essential zlib1g-dev libncurses5-dev \
            libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev \
            libsqlite3-dev wget libbz2-dev tk-dev
    elif command -v dnf &>/dev/null; then
        sudo dnf groupinstall -y "Development Tools"
        sudo dnf install -y zlib-devel bzip2-devel openssl-devel \
            ncurses-devel sqlite-devel readline-devel tk-devel \
            libffi-devel wget
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y -t pattern devel_basis
        sudo zypper install -y zlib-devel libbz2-devel libopenssl-devel \
            ncurses-devel sqlite3-devel readline-devel tk-devel \
            libffi-devel wget
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm base-devel openssl zlib tk sqlite wget
    fi

    local build_dir="/tmp/python311-build"
    mkdir -p "$build_dir"
    cd "$build_dir"

    if [ ! -f "Python-3.11.9.tgz" ]; then
        wget -q "https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz"
    fi
    tar xzf Python-3.11.9.tgz
    cd Python-3.11.9

    ./configure --enable-optimizations --prefix=/usr/local 2>&1 | tail -5
    make -j"$(nproc)" 2>&1 | tail -5
    sudo make altinstall 2>&1 | tail -5

    cd "$APP_DIR"
    rm -rf "$build_dir"

    if command -v python3.11 &>/dev/null; then
        success "Python 3.11 compilado e instalado em /usr/local/bin/python3.11"
    else
        error "Falha ao compilar Python 3.11. Instale manualmente."
    fi
}

ensure_tkinter() {
    info "Verificando tkinter para Python 3.11..."

    if "$PYTHON_CMD" -c "import tkinter" 2>/dev/null; then
        success "tkinter disponível"
        return 0
    fi

    warn "tkinter não encontrado. Instalando..."

    case "$DISTRO_ID" in
        opensuse*|sles|regataos)
            sudo zypper install -y python311-tk 2>/dev/null \
                || sudo zypper install -y python3-tk 2>/dev/null \
                || true
            ;;
        ubuntu|debian|linuxmint|pop)
            sudo apt install -y python3.11-tk 2>/dev/null \
                || sudo apt install -y python3-tk 2>/dev/null \
                || true
            ;;
        fedora)
            sudo dnf install -y python3.11-tkinter 2>/dev/null \
                || sudo dnf install -y python3-tkinter 2>/dev/null \
                || true
            ;;
        arch|manjaro|endeavouros)
            sudo pacman -Sy --noconfirm tk 2>/dev/null || true
            ;;
        *)
            if echo "$DISTRO_LIKE" | grep -qi "suse"; then
                sudo zypper install -y python311-tk 2>/dev/null || true
            elif echo "$DISTRO_LIKE" | grep -qi "debian\|ubuntu"; then
                sudo apt install -y python3.11-tk 2>/dev/null || true
            elif echo "$DISTRO_LIKE" | grep -qi "fedora\|rhel"; then
                sudo dnf install -y python3.11-tkinter 2>/dev/null || true
            fi
            ;;
    esac

    if "$PYTHON_CMD" -c "import tkinter" 2>/dev/null; then
        success "tkinter instalado com sucesso"
    else
        error "Não foi possível instalar tkinter para Python 3.11.\n   Instale manualmente: sudo zypper install python311-tk"
    fi
}

install_system_tools() {
    info "Instalando ferramentas de diagnóstico..."

    case "$DISTRO_ID" in
        opensuse*|sles|regataos)
            sudo zypper install -y smartmontools hdparm e2fsprogs f3 || true
            ;;
        ubuntu|debian|linuxmint|pop)
            sudo apt install -y smartmontools hdparm e2fsprogs f3 || true
            ;;
        fedora)
            sudo dnf install -y smartmontools hdparm e2fsprogs f3 || true
            ;;
        arch|manjaro|endeavouros)
            sudo pacman -Sy --noconfirm smartmontools hdparm e2fsprogs f3 || true
            ;;
        *)
            if echo "$DISTRO_LIKE" | grep -qi "suse"; then
                sudo zypper install -y smartmontools hdparm e2fsprogs f3 || true
            elif echo "$DISTRO_LIKE" | grep -qi "debian\|ubuntu"; then
                sudo apt install -y smartmontools hdparm e2fsprogs f3 || true
            elif echo "$DISTRO_LIKE" | grep -qi "fedora\|rhel"; then
                sudo dnf install -y smartmontools hdparm e2fsprogs f3 || true
            else
                warn "Instale manualmente: smartmontools hdparm e2fsprogs f3"
            fi
            ;;
    esac
}

setup_venv() {
    info "Configurando ambiente virtual com Python 3.11..."

    if [ -d "$VENV_DIR" ]; then
        local venv_python
        venv_python=$("$VENV_DIR/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0")
        if [ "$venv_python" != "3.11" ]; then
            warn "Venv existente usa Python $venv_python. Recriando com 3.11..."
            rm -rf "$VENV_DIR"
        fi
    fi

    if [ ! -d "$VENV_DIR" ]; then
        "$PYTHON_CMD" -m venv "$VENV_DIR" --system-site-packages 2>/dev/null || {
            warn "Falha ao criar venv. Instalando módulo venv..."
            case "$DISTRO_ID" in
                ubuntu|debian|linuxmint|pop)
                    sudo apt install -y python3.11-venv
                    ;;
                opensuse*|sles|regataos)
                    sudo zypper install -y python311-venv 2>/dev/null || true
                    ;;
            esac
            "$PYTHON_CMD" -m venv "$VENV_DIR" --system-site-packages || error "Não foi possível criar o ambiente virtual com Python 3.11"
        }
    fi

    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install -r "$APP_DIR/requirements.txt" -q
    deactivate

    local venv_ver
    venv_ver=$("$VENV_DIR/bin/python" --version 2>&1)
    success "Venv configurado: $venv_ver"

    info "Verificando tkinter dentro do venv..."
    if "$VENV_DIR/bin/python" -c "import tkinter" 2>/dev/null; then
        success "tkinter acessível no venv"
    else
        error "tkinter não acessível no venv.\n   Instale: sudo zypper install python311-tk\n   Depois rode: rm -rf .venv && bash install.sh"
    fi
}

create_launcher() {
    info "Criando launcher..."

    cat > "$APP_DIR/run.sh" << 'LAUNCHER'
#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Ambiente não configurado. Execute primeiro:"
    echo "   bash install.sh"
    exit 1
fi

PYTHON="$VENV_DIR/bin/python"

PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
if [ "$PY_VER" != "3.11" ]; then
    echo "⚠️  Venv não está com Python 3.11 (encontrado: $PY_VER)"
    echo "   Execute: bash install.sh"
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo ""
    echo "💡 Para acesso SMART completo:"
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

check_tools() {
    echo ""
    info "Verificando ferramentas:"
    local tools=("smartctl:smartmontools" "hdparm:hdparm" "badblocks:e2fsprogs" "f3probe:f3")
    for entry in "${tools[@]}"; do
        local cmd="${entry%%:*}"
        local pkg="${entry##*:}"
        if command -v "$cmd" &>/dev/null; then
            success "  $cmd"
        else
            warn "  $cmd NÃO encontrado (pacote: $pkg)"
        fi
    done
}

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  💾 HddMonitor - Instalador (Python 3.11)    ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo ""

detect_distro

if find_python311; then
    success "Python 3.11 encontrado: $PYTHON_CMD"
else
    warn "Python 3.11 não encontrado. Instalando..."
    install_python311
    if ! find_python311; then
        error "Não foi possível instalar Python 3.11. Instale manualmente e rode novamente."
    fi
    success "Python 3.11 instalado: $PYTHON_CMD"
fi

ensure_tkinter
install_system_tools
setup_venv
create_launcher
create_desktop_entry
check_tools

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Instalação concluída! (Python 3.11)${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  Para executar:"
echo -e "    ${BOLD}bash run.sh${NC}              (sem root, funcionalidade limitada)"
echo -e "    ${BOLD}sudo -E bash run.sh${NC}      (com root, acesso SMART completo)"
echo ""
echo -e "  Ou pelo menu de aplicativos: ${BOLD}HDD Monitor${NC}"
echo ""