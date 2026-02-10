# 💾 HddMonitor

Ferramenta gráfica para diagnóstico e monitoramento de discos rígidos (HDD/SSD/NVMe) no Linux.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Linux-orange.svg)

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

### Sistema
- Linux (testado em openSUSE, Ubuntu, Fedora)
- Python 3.11+
- Acesso root (sudo) para leitura SMART

### Dependências Python
```bash
pip3.11 install --user customtkinter psutil
```

### Ferramentas do Sistema
```bash
# openSUSE
sudo zypper install smartmontools hdparm e2fsprogs f3

# Ubuntu/Debian
sudo apt install smartmontools hdparm e2fsprogs f3

# Fedora
sudo dnf install smartmontools hdparm e2fsprogs f3
```

## 🚀 Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/hddmonitor.git
cd hddmonitor

# Instale dependências Python
pip3.11 install --user customtkinter psutil

# Execute (com acesso SMART completo)
sudo -E python3.11 app.py

# Ou sem sudo (funcionalidade limitada)
python3.11 app.py
```

> ⚠️ **Importante:** Use `sudo -E` (não apenas `sudo`) para preservar o ambiente gráfico ($DISPLAY).

## 📁 Estrutura do Projeto

```
hddmonitor/
├── app.py                    # Ponto de entrada principal
├── core/
│   ├── __init__.py
│   ├── config.py             # Configurações e constantes
│   ├── disk_service.py       # Serviço de detecção de discos
│   ├── smart_parser.py       # Parser de dados SMART
│   ├── health_score.py       # Cálculo de pontuação de saúde
│   ├── fake_detector.py      # Detecção de discos falsificados
│   └── test_runner.py        # Executor de testes diagnósticos
├── ui/
│   ├── __init__.py
│   ├── components.py         # Componentes UI reutilizáveis
│   ├── dashboard.py          # Tela principal
│   ├── diagnostic_wizard.py  # Assistente de diagnóstico
│   ├── diagnostic_controller.py
│   ├── diagnostic_service.py
│   └── report_generator.py   # Gerador de relatórios HTML
└── README.md
```

## 🎯 Uso

### Execução
```bash
# Com acesso SMART completo (recomendado)
sudo -E python3.11 app.py

# Sem sudo (funcionalidade limitada)
python3.11 app.py
```

### Corrigir permissões (se necessário)
Se você rodou com `sudo` antes e agora tem problemas de permissão:
```bash
sudo chown -R $USER:$USER ~/Documents/hddmonitor-reports/
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

## 🔒 Segurança

- Sempre faça backup antes de executar testes destrutivos
- Execute como root apenas quando necessário
- Desmonte o disco antes de testes que exigem acesso exclusivo

## 🐛 Troubleshooting

### "no display name and no $DISPLAY environment variable"
- **Causa:** `sudo` não herda variáveis de ambiente
- **Solução:** Use `sudo -E python3.11 app.py` (com `-E`)

### Permissão negada ao gerar relatório
- **Causa:** Pasta criada pelo root em execução anterior
- **Solução:** 
  ```bash
  sudo chown -R $USER:$USER ~/Documents/hddmonitor-reports/
  ```

### Temperatura mostra N/A
- Verifique se o smartmontools está instalado
- Alguns discos USB não suportam leitura de temperatura
- Tente: `sudo smartctl -a /dev/sdX`

### Permissão negada
- Execute com `sudo`
- Verifique se o usuário está no grupo `disk`

### Disco não aparece
- Verifique se está montado: `lsblk`
- Pode ser filtrado (loop, snap, tmpfs são ignorados)

## 📝 Licença

MIT License - Veja [LICENSE](LICENSE) para detalhes.

## 👨‍💻 Autor

Desenvolvido por **Marquim.rcc** com auxílio do **Claude AI (Opus 4.5)**

---

⚠️ **Aviso:** Use por sua conta e risco. Sempre faça backups antes de executar diagnósticos em discos importantes!
