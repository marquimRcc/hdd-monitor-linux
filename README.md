# 💾 HddMonitor

Ferramenta gráfica para diagnóstico e monitoramento de discos rígidos (HDD/SSD/NVMe) no Linux.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Linux-orange.svg)

## 🚀 Instalação Rápida

```bash
git clone https://github.com/seu-usuario/hddmonitor.git
cd hddmonitor
bash install.sh
```

O instalador detecta sua distro automaticamente e instala tudo: Python, dependências do sistema, bibliotecas Python (em venv isolado) e cria atalho no menu.

### Distros suportadas
- openSUSE / Regata OS / SLES
- Ubuntu / Debian / Linux Mint / Pop!_OS
- Fedora / RHEL / CentOS
- Arch / Manjaro / EndeavourOS

### Executar

```bash
# Sem root (funcionalidade limitada)
bash run.sh

# Com root (acesso SMART completo - recomendado)
sudo -E bash run.sh
```

Ou pelo menu de aplicativos: **HDD Monitor**

## ✨ Funcionalidades

### Dashboard
- 📊 Monitoramento em tempo real de todos os discos
- 🌡️ Temperatura com indicadores coloridos
- 💽 Detecção automática de HDD, SSD e NVMe
- 📈 Barra de uso com alertas visuais
- 🔄 Atualização automática a cada 3 segundos

### Diagnóstico
- ⚡ **Verificação Rápida** (~5s) - SMART + Saúde + Fake Detection
- 🔬 **Diagnóstico Completo** (~3min) - Inclui testes de leitura e velocidade
- 🎭 **Detecção de Disco Fake** - Usa f3probe para detectar pendrives/SSDs falsificados
- ⚙️ **Testes Avançados** - badblocks, SMART extended, etc.

### Relatórios
- 📄 Geração de relatório HTML detalhado
- 🌐 Abre automaticamente no navegador
- 💾 Salvo em `~/Documents/hddmonitor-reports/`

## 🔧 Requisitos

- Linux (qualquer distro moderna)
- Python 3.8+ (instalado automaticamente pelo `install.sh`)
- Acesso root (sudo) para leitura SMART

## 📁 Estrutura do Projeto

```
hddmonitor/
├── install.sh                # Instalador automático
├── run.sh                    # Launcher (criado pelo install.sh)
├── app.py                    # Ponto de entrada principal
├── core/
│   ├── config.py             # Configurações e constantes
│   ├── disk_service.py       # Serviço de detecção de discos
│   ├── smart_parser.py       # Parser de dados SMART
│   ├── health_score.py       # Cálculo de pontuação de saúde
│   ├── fake_detector.py      # Detecção de discos falsificados
│   ├── fake_remediation.py   # Ações pós-detecção de fake
│   └── test_runner.py        # Executor de testes diagnósticos
├── ui/
│   ├── components.py         # Componentes UI reutilizáveis
│   ├── dashboard.py          # Tela principal
│   ├── diagnostic_wizard.py  # Assistente de diagnóstico
│   ├── diagnostic_controller.py
│   ├── diagnostic_service.py
│   ├── fake_action_panel.py  # Painel de ações para disco fake
│   └── report_generator.py   # Gerador de relatórios HTML
├── requirements.txt
├── LICENSE
└── README.md
```

### Testes Disponíveis

| Teste | Tempo | Destrutivo | Descrição |
|-------|-------|------------|-----------|
| Informações SMART | ~2s | ❌ | Coleta dados SMART básicos |
| Verificação de Saúde | ~2s | ❌ | Calcula score de saúde (0-100%) |
| Detecção Rápida de Fake | ~5s | ❌ | Verifica HPA e consistência |
| SMART Short Test | ~2min | ❌ | Teste curto interno do disco |
| Leitura Amostral | ~1min | ❌ | Lê amostras aleatórias |
| Teste de Velocidade | ~30s | ❌ | Mede velocidade de leitura |
| f3probe | ~5min | ✅ | Teste definitivo de disco fake |
| Badblocks (Leitura) | 2-8h | ❌ | Verifica setores defeituosos |
| Badblocks (Destrutivo) | 4-24h | ✅ | Teste completo com escrita |

> ⚠️ **Atenção:** Testes marcados como destrutivos APAGAM TODOS OS DADOS do disco!

## 🐛 Troubleshooting

### "no display name and no $DISPLAY environment variable"
Use `sudo -E bash run.sh` (com `-E`)

### Permissão negada ao gerar relatório
```bash
sudo chown -R $USER:$USER ~/Documents/hddmonitor-reports/
```

### Temperatura mostra N/A
- Verifique se o smartmontools está instalado
- Alguns discos USB não suportam leitura de temperatura

### Disco não aparece
- Verifique se está conectado: `lsblk`
- Dispositivos loop, snap e tmpfs são filtrados automaticamente

### Reinstalar do zero
```bash
rm -rf .venv
bash install.sh
```

## 📝 Licença

MIT License - Veja [LICENSE](LICENSE) para detalhes.

## 👨‍💻 Autor

Desenvolvido por **Marquim.rcc** com auxílio do **Claude AI (Opus 4.5)**

---

⚠️ **Aviso:** Use por sua conta e risco. Sempre faça backups antes de executar diagnósticos em discos importantes!