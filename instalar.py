#!/usr/bin/env python3
"""
instalar.py — Instalador universal do SpotiDown.
Funciona em Windows, Linux e macOS.

Uso:
    Windows : python instalar.py
    Linux   : python3 instalar.py
"""

import os
import sys
import shutil
import subprocess
import platform
import urllib.request
import zipfile
import io
import json
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LIN = sys.platform == "linux"

# Download direto do ZIP (elimina a necessidade do 'git' estar instalado)
REPO = "https://github.com/neroios/spotidown/archive/refs/heads/main.zip"

# ── Cores ─────────────────────────────────────────────────────────────────────
class C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

def enable_ansi():
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def c(text, *codes):
    return "".join(codes) + str(text) + C.RESET

def ok(msg):   print(c(f"  ✔ {msg}", C.GREEN))
def info(msg): print(c(f"  ~ {msg}", C.YELLOW))
def err(msg):  print(c(f"  ✗ {msg}", C.RED))
def step(msg): print(c(f"\n  {msg}", C.CYAN, C.BOLD))

def run(*args, **kwargs):
    """Roda um comando e retorna True se sucesso."""
    try:
        r = subprocess.run(list(args), **kwargs,
                           capture_output=True, text=True, timeout=180)
        return r.returncode == 0, r.stdout + r.stderr
    except Exception as e:
        return False, str(e)

def tool_is_working(cmd, test_flag="-version"):
    """
    Verifica se o programa existe no PATH e se ele executa corretamente.
    Evita falsos positivos com arquivos corrompidos de 0 KB.
    """
    if not shutil.which(cmd):
        return False
    success, _ = run(cmd, test_flag)
    return success

def add_to_windows_path(new_dir: str):
    """
    Adiciona um diretório ao PATH do usuário via Registro do Windows.
    Substitui o 'setx' para evitar o bug de truncamento de 1024 caracteres.
    """
    if not IS_WIN: return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
            try:
                current_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""
            
            # Se a pasta já não estiver no PATH, adicionamos de forma segura
            if new_dir.lower() not in current_path.lower():
                sep = ";" if current_path and not current_path.endswith(";") else ""
                updated_path = current_path + sep + new_dir
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated_path)
                os.environ["PATH"] += f";{new_dir}"  # Atualiza na sessão atual também
    except Exception as e:
        info(f"Falha ao modificar PATH no Registro: {e}")

# ── Verificações ──────────────────────────────────────────────────────────────
def check_python_version():
    step("Verificando Python...")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        err(f"Python 3.10+ necessário. Você tem {major}.{minor}.")
        if IS_WIN:
            print(c("    → Baixe em: https://python.org/downloads", C.CYAN))
        sys.exit(1)
    ok(f"Python {major}.{minor} OK")

def ensure_linux_base():
    """Garante pacotes base (pip, venv, pipx) detectando a distro do usuário."""
    if not IS_LIN:
        return

    step("Verificando pacotes base do Linux...")
    
    success_venv, _ = run(sys.executable, "-c", "import venv")
    success_pip, _ = run(sys.executable, "-m", "pip", "--version")
    
    if success_venv and success_pip:
        ok("Pacotes base do Linux OK")
        return

    info("Faltam dependências. Detectando gerenciador de pacotes...")

    # Mapeamento para as distros mais populares (sem precisar forçar o 'git')
    managers = [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq"], ["python3-venv", "python3-pip"]),
        ("pacman",  ["sudo", "pacman", "-S", "--noconfirm", "--needed"], ["python-pip", "python-pipx"]),
        ("dnf5",    ["sudo", "dnf5", "install", "-y", "-q"], ["python3-pip"]),
        ("dnf",     ["sudo", "dnf", "install", "-y", "-q"], ["python3-pip"]),
        ("zypper",  ["sudo", "zypper", "install", "-y", "-q"], ["python3-pip"]),
        ("apk",     ["sudo", "apk", "add", "-q"], ["py3-pip"])
    ]

    for pkg_mgr, cmd_base, pkgs in managers:
        if shutil.which(pkg_mgr):
            info(f"Instalando via {pkg_mgr} (pode pedir senha sudo)...")
            if pkg_mgr == "apt-get":
                run("sudo", "apt-get", "update", "-qq")
                
            success, out = run(*(cmd_base + pkgs))
            if success:
                ok(f"Pacotes base instalados via {pkg_mgr}!")
                return
            else:
                err(f"Falha ao instalar via {pkg_mgr}.")
                print(c(f"    Saída: {out[:300]}", C.DIM))
                sys.exit(1)
                
    err("Gerenciador de pacotes não reconhecido.")
    print(c("    → Por favor, instale o 'pip' e o 'venv' do Python manualmente.", C.CYAN))
    sys.exit(1)

def ensure_pip():
    """Garante que pip está disponível."""
    success, _ = run(sys.executable, "-m", "pip", "--version")
    if not success:
        info("Instalando pip...")
        run(sys.executable, "-m", "ensurepip", "--upgrade")

def ensure_pipx() -> list:
    """Retorna o comando pipx como lista. Instala se necessário."""
    step("Verificando pipx...")

    if tool_is_working("pipx", "--version"):
        ok("pipx encontrado no PATH")
        return ["pipx"]

    success, _ = run(sys.executable, "-m", "pipx", "--version")
    if success:
        ok("pipx disponível via python -m pipx")
        return [sys.executable, "-m", "pipx"]

    info("pipx não encontrado. Instalando via pip...")
    ensure_pip()

    cmds = [
        [sys.executable, "-m", "pip", "install", "pipx", "--quiet"],
        [sys.executable, "-m", "pip", "install", "pipx", "--quiet", "--break-system-packages"],
    ]
    installed = False
    for cmd in cmds:
        success, _ = run(*cmd)
        if success:
            installed = True
            break

    if not installed:
        err("Não foi possível instalar pipx automaticamente.")
        print(c("    → Rode manualmente: pip install pipx", C.CYAN))
        sys.exit(1)

    run(sys.executable, "-m", "pipx", "ensurepath")
    ok("pipx instalado")
    return [sys.executable, "-m", "pipx"]

def ensure_nodejs():
    """Garante que o Node.js está instalado para o yt-dlp não falhar no YouTube."""
    step("Verificando Node.js (JavaScript runtime)...")

    if tool_is_working("node", "-v") or tool_is_working("node", "--version"):
        ok("Node.js encontrado e funcionando")
        return

    info("Node.js não encontrado ou corrompido. Instalando...")

    if IS_WIN:
        if shutil.which("winget"):
            success, _ = run("winget", "install", "OpenJS.NodeJS",
                             "--accept-package-agreements",
                             "--accept-source-agreements", "--silent")
            if success and tool_is_working("node", "-v"):
                ok("Node.js instalado via winget")
                return
        err("Não foi possível instalar Node.js automaticamente.")
        print(c("    → Instale baixando em: https://nodejs.org", C.CYAN))

    elif IS_MAC:
        if shutil.which("brew"):
            success, _ = run("brew", "install", "node")
            if success:
                ok("Node.js instalado via brew")
                return
        err("Instale com: brew install node")

    else:
        for pkg_mgr, cmd in [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq", "nodejs"]),
            ("pacman",  ["sudo", "pacman",  "-S", "--noconfirm", "nodejs"]),
            ("dnf5",    ["sudo", "dnf5",    "install", "-y", "nodejs"]),
            ("dnf",     ["sudo", "dnf",     "install", "-y", "nodejs"]),
        ]:
            if shutil.which(pkg_mgr):
                info(f"Instalando Node.js via {pkg_mgr}...")
                success, _ = run(*cmd)
                if success:
                    ok("Node.js instalado")
                    return
                break
        err("Não foi possível instalar Node.js.")
        print(c("    → Instale manualmente dependendo da sua distro.", C.CYAN))

def ensure_ffmpeg():
    """Instala ffmpeg e ffprobe se não estiverem disponíveis."""
    step("Verificando ffmpeg/ffprobe...")

    if tool_is_working("ffmpeg") and tool_is_working("ffprobe"):
        ok("ffmpeg e ffprobe encontrados e funcionando")
        return

    info("ffmpeg ou ffprobe ausentes/corrompidos. Instalando...")

    if IS_WIN:
        if shutil.which("winget"):
            success, _ = run("winget", "install", "ffmpeg",
                             "--accept-package-agreements",
                             "--accept-source-agreements", "--silent")
            if success and tool_is_working("ffmpeg") and tool_is_working("ffprobe"):
                ok("ffmpeg/ffprobe instalados via winget")
                return

        info("Tentando baixar versão estática (GitHub)...")
        ffmpeg_dir = Path.home() / ".spotidown" / "ffmpeg"
        
        # AUTO-LIMPEZA
        if ffmpeg_dir.exists():
            shutil.rmtree(ffmpeg_dir, ignore_errors=True)
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)

        try:
            api = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
            req = urllib.request.Request(api, headers={"User-Agent": "spotidown-installer"})
            data = json.loads(urllib.request.urlopen(req, timeout=15).read())
            asset_url = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if "win64" in a["name"] and a["name"].endswith(".zip")),
                None
            )
            if asset_url:
                print(c("    Baixando pacote ZIP (pode demorar)...", C.DIM), end="", flush=True)
                with urllib.request.urlopen(asset_url, timeout=120) as resp:
                    content = resp.read()
                print(c(" OK", C.GREEN))
                
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    extracted = 0
                    for name in z.namelist():
                        if name.endswith("ffmpeg.exe") or name.endswith("ffprobe.exe"):
                            file_name = os.path.basename(name)
                            dest_file = ffmpeg_dir / file_name
                            dest_file.write_bytes(z.read(name))
                            
                            if dest_file.stat().st_size < 1000:
                                raise Exception(f"Arquivo {file_name} extraído corrompido.")
                            extracted += 1
                        if extracted == 2:
                            break

                add_to_windows_path(str(ffmpeg_dir))
                ok(f"ffmpeg e ffprobe extraídos em {ffmpeg_dir}")
                info("Reinicie o terminal para o PATH ser atualizado.")
                return
        except Exception as e:
            info(f"Download automático falhou: {e}")

        err("Não foi possível instalar ffmpeg automaticamente.")
        print(c("    → Instale manualmente: winget install ffmpeg", C.CYAN))

    elif IS_MAC:
        if shutil.which("brew"):
            success, _ = run("brew", "install", "ffmpeg")
            if success:
                ok("ffmpeg instalado via brew")
                return
        err("Instale com: brew install ffmpeg")

    else:
        for pkg_mgr, cmd in [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq", "ffmpeg"]),
            ("pacman",  ["sudo", "pacman",  "-S", "--noconfirm", "ffmpeg"]),
            ("dnf5",    ["sudo", "dnf5",    "install", "-y", "ffmpeg"]),
            ("dnf",     ["sudo", "dnf",     "install", "-y", "ffmpeg"]),
        ]:
            if shutil.which(pkg_mgr):
                info(f"Instalando ffmpeg via {pkg_mgr}...")
                success, _ = run(*cmd)
                if success:
                    ok("ffmpeg instalado")
                    return
                break
        err("Não foi possível instalar ffmpeg.")
        print(c("    → Instale o pacote 'ffmpeg' manualmente.", C.CYAN))

def install_spotidown(pipx_cmd: list):
    """Instala ou atualiza o spotidown via pipx."""
    step("Instalando SpotiDown...")

    success, out = run(*pipx_cmd, "upgrade", "spotidown")
    if success:
        ok("SpotiDown atualizado!")
        return

    success, out = run(*pipx_cmd, "install", REPO)
    if success:
        ok("SpotiDown instalado!")
        return

    err("Falha ao instalar SpotiDown.")
    print(c(f"    Saída: {out[:300]}", C.DIM))
    sys.exit(1)

def ensure_path(pipx_cmd: list):
    """Garante que o diretório bin do pipx está no PATH."""
    step("Configurando PATH...")
    run(*pipx_cmd, "ensurepath")

    if IS_WIN:
        pipx_bin = Path.home() / ".local" / "bin"
        apps_bin = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Scripts"
        for d in [pipx_bin, apps_bin]:
            if d.exists():
                add_to_windows_path(str(d))
    ok("PATH configurado")

def print_success():
    print(c("\n  " + "─" * 38, C.DIM))
    print(c("  ✔ Instalação concluída!", C.GREEN, C.BOLD))
    print(c("  " + "─" * 38, C.DIM))
    print()
    print(c("  Como usar:", C.CYAN, C.BOLD))
    print(c('  spotidown "angra fireworks"', C.GREEN))
    print(c('  spotidown "metallica" ~/Music', C.GREEN))
    print(c('  spotidown "https://open.spotify.com/album/xxx"', C.GREEN))
    print()
    if IS_WIN:
        print(c("  ⚠  Feche e reabra o PowerShell antes de usar.", C.YELLOW))
    else:
        print(c("  ⚠  Rode: source ~/.bashrc  (ou abra novo terminal)", C.YELLOW))
    print()

def main():
    enable_ansi()
    print(c("\n  ♫ SpotiDown — Instalador Universal", C.GREEN, C.BOLD))
    print(c(f"  Sistema: {platform.system()} {platform.release()}", C.DIM))
    print(c("  " + "─" * 38, C.DIM))

    check_python_version()
    ensure_linux_base()
    ensure_pip()
    pipx_cmd = ensure_pipx()
    ensure_nodejs()
    ensure_ffmpeg()
    install_spotidown(pipx_cmd)
    ensure_path(pipx_cmd)
    print_success()

if __name__ == "__main__":
    main()
