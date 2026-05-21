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

REPO = "https://github.com/neroios/spotidown/archive/refs/heads/main.zip"

# Pasta base onde o instalador salva ffmpeg e nodejs portáteis
SPOTIDOWN_DIR = Path.home() / ".spotidown"
FFMPEG_DIR    = SPOTIDOWN_DIR / "ffmpeg"
NODEJS_DIR    = SPOTIDOWN_DIR / "nodejs"

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
    try:
        r = subprocess.run(list(args), **kwargs,
                           capture_output=True, text=True, timeout=180)
        return r.returncode == 0, r.stdout + r.stderr
    except Exception as e:
        return False, str(e)

def cmd_works(cmd, flag="-version"):
    """Verifica se um binário existe no PATH e executa corretamente."""
    path = shutil.which(cmd)
    if not path:
        return False
    try:
        r = subprocess.run([path, flag], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

def add_to_path_permanent(new_dir: str):
    """Adiciona ao PATH do usuário via Registro (Windows) sem bug de truncamento."""
    if not IS_WIN:
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0,
                            winreg.KEY_ALL_ACCESS) as key:
            try:
                current_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""
            if new_dir.lower() not in current_path.lower():
                sep = ";" if current_path and not current_path.endswith(";") else ""
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ,
                                  current_path + sep + new_dir)
    except Exception as e:
        info(f"Aviso: não foi possível escrever no Registro: {e}")

def add_to_path_session(new_dir: str):
    """Adiciona ao PATH da sessão ATUAL (processo Python rodando agora)."""
    if new_dir.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = new_dir + os.pathsep + os.environ.get("PATH", "")

def add_to_path(new_dir: str):
    """Adiciona ao PATH permanentemente E na sessão atual."""
    add_to_path_permanent(new_dir)
    add_to_path_session(new_dir)

# ── Verificações base ─────────────────────────────────────────────────────────
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
    if not IS_LIN:
        return
    step("Verificando pacotes base do Linux...")
    s1, _ = run(sys.executable, "-c", "import venv")
    s2, _ = run(sys.executable, "-m", "pip", "--version")
    if s1 and s2:
        ok("Pacotes base OK")
        return
    info("Instalando dependências base...")
    managers = [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq"], ["python3-venv", "python3-pip"]),
        ("pacman",  ["sudo", "pacman", "-S", "--noconfirm", "--needed"], ["python-pip"]),
        ("dnf5",    ["sudo", "dnf5", "install", "-y", "-q"], ["python3-pip"]),
        ("dnf",     ["sudo", "dnf", "install", "-y", "-q"], ["python3-pip"]),
        ("zypper",  ["sudo", "zypper", "install", "-y", "-q"], ["python3-pip"]),
        ("apk",     ["sudo", "apk", "add", "-q"], ["py3-pip"]),
    ]
    for mgr, base_cmd, pkgs in managers:
        if shutil.which(mgr):
            if mgr == "apt-get":
                run("sudo", "apt-get", "update", "-qq")
            ok_i, out = run(*(base_cmd + pkgs))
            if ok_i:
                ok(f"Instalado via {mgr}")
                return
            err(f"Falha via {mgr}: {out[:200]}")
            sys.exit(1)
    err("Gerenciador de pacotes não reconhecido. Instale pip manualmente.")
    sys.exit(1)

def ensure_pip():
    s, _ = run(sys.executable, "-m", "pip", "--version")
    if not s:
        info("Instalando pip...")
        run(sys.executable, "-m", "ensurepip", "--upgrade")

def ensure_pipx() -> list:
    step("Verificando pipx...")
    if cmd_works("pipx", "--version"):
        ok("pipx encontrado")
        return ["pipx"]
    s, _ = run(sys.executable, "-m", "pipx", "--version")
    if s:
        ok("pipx disponível via python -m")
        return [sys.executable, "-m", "pipx"]
    info("Instalando pipx...")
    ensure_pip()
    for extra in [[], ["--break-system-packages"]]:
        s, _ = run(sys.executable, "-m", "pip", "install", "pipx", "--quiet", *extra)
        if s:
            break
    else:
        err("Não foi possível instalar pipx. Rode: pip install pipx")
        sys.exit(1)
    run(sys.executable, "-m", "pipx", "ensurepath")
    ok("pipx instalado")
    return [sys.executable, "-m", "pipx"]

# ── Node.js ───────────────────────────────────────────────────────────────────
def _node_works():
    """Checa se node está no PATH atual e funciona."""
    return cmd_works("node", "--version")

def ensure_nodejs():
    step("Verificando Node.js (necessário para o yt-dlp funcionar no YouTube)...")

    # Primeiro: adiciona a pasta portátil ao PATH da sessão, caso já tenha sido extraída antes
    if IS_WIN:
        NODE_VERSION = "v20.12.2"
        portable_bin = NODEJS_DIR / f"node-{NODE_VERSION}-win-x64"
        if portable_bin.exists():
            add_to_path_session(str(portable_bin))

    if _node_works():
        ok("Node.js OK")
        return

    info("Node.js não encontrado. Instalando...")

    if IS_WIN:
        NODE_VERSION = "v20.12.2"
        portable_bin = NODEJS_DIR / f"node-{NODE_VERSION}-win-x64"

        # Tenta winget primeiro
        if shutil.which("winget"):
            info("Tentando via winget...")
            run("winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e",
                "--accept-package-agreements", "--accept-source-agreements", "--silent")
            # winget instala em Program Files; adiciona ao PATH da sessão
            for candidate in [
                r"C:\Program Files\nodejs",
                r"C:\Program Files (x86)\nodejs",
            ]:
                if os.path.exists(os.path.join(candidate, "node.exe")):
                    add_to_path(candidate)
                    break
            if _node_works():
                ok("Node.js instalado via winget")
                return

        # Fallback: baixa ZIP portátil
        info(f"Baixando Node.js portátil {NODE_VERSION}...")
        NODEJS_DIR.mkdir(parents=True, exist_ok=True)
        if portable_bin.exists():
            shutil.rmtree(portable_bin, ignore_errors=True)

        node_url = f"https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-win-x64.zip"
        try:
            print(c("    Baixando (pode demorar)...", C.DIM), end="", flush=True)
            with urllib.request.urlopen(node_url, timeout=180) as resp:
                content = resp.read()
            print(c(" OK", C.GREEN))

            with zipfile.ZipFile(io.BytesIO(content)) as z:
                z.extractall(NODEJS_DIR)

            # Adiciona ao PATH permanente E na sessão atual
            add_to_path(str(portable_bin))

            if _node_works():
                ok(f"Node.js portátil instalado em {portable_bin}")
                return
            else:
                err("Node.js extraído mas não foi possível executar. Reinicie o terminal.")
        except Exception as e:
            err(f"Falha ao baixar Node.js: {e}")

        print(c("    → Baixe manualmente em: https://nodejs.org (LTS)", C.CYAN))

    elif IS_MAC:
        if shutil.which("brew"):
            run("brew", "install", "node")
            if _node_works():
                ok("Node.js instalado via brew")
                return
        err("Instale com: brew install node")

    else:
        for mgr, cmd in [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq", "nodejs"]),
            ("pacman",  ["sudo", "pacman",  "-S", "--noconfirm", "nodejs"]),
            ("dnf5",    ["sudo", "dnf5",    "install", "-y", "nodejs"]),
            ("dnf",     ["sudo", "dnf",     "install", "-y", "nodejs"]),
        ]:
            if shutil.which(mgr):
                info(f"Instalando Node.js via {mgr}...")
                s, _ = run(*cmd)
                if s:
                    ok("Node.js instalado")
                    return
                break
        err("Instale Node.js manualmente para a sua distro.")

# ── ffmpeg ────────────────────────────────────────────────────────────────────
def _ffmpeg_works():
    return cmd_works("ffmpeg") and cmd_works("ffprobe")

def ensure_ffmpeg():
    step("Verificando ffmpeg/ffprobe...")

    # Adiciona pasta portátil ao PATH da sessão se já existir
    if IS_WIN and FFMPEG_DIR.exists():
        add_to_path_session(str(FFMPEG_DIR))

    if _ffmpeg_works():
        ok("ffmpeg e ffprobe OK")
        return

    info("ffmpeg/ffprobe ausentes. Instalando...")

    if IS_WIN:
        # Tenta winget
        if shutil.which("winget"):
            info("Tentando via winget...")
            run("winget", "install", "ffmpeg",
                "--accept-package-agreements", "--accept-source-agreements", "--silent")
            # winget pode instalar em vários lugares; tenta os mais comuns
            for candidate in [
                r"C:\ProgramData\chocolatey\bin",
                r"C:\ffmpeg\bin",
                r"C:\Program Files\ffmpeg\bin",
            ]:
                if os.path.exists(os.path.join(candidate, "ffmpeg.exe")):
                    add_to_path(candidate)
                    break
            if _ffmpeg_works():
                ok("ffmpeg instalado via winget")
                return

        # Fallback: baixa build estática do GitHub (yt-dlp/FFmpeg-Builds)
        info("Baixando ffmpeg estático (GitHub yt-dlp/FFmpeg-Builds)...")
        if FFMPEG_DIR.exists():
            shutil.rmtree(FFMPEG_DIR, ignore_errors=True)
        FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

        try:
            api = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
            req = urllib.request.Request(api, headers={"User-Agent": "spotidown-installer"})
            data = json.loads(urllib.request.urlopen(req, timeout=15).read())
            asset_url = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if "win64" in a["name"] and a["name"].endswith(".zip")),
                None,
            )
            if not asset_url:
                raise Exception("Nenhum asset win64.zip encontrado na release.")

            print(c("    Baixando (pode demorar)...", C.DIM), end="", flush=True)
            with urllib.request.urlopen(asset_url, timeout=180) as resp:
                content = resp.read()
            print(c(" OK", C.GREEN))

            extracted = 0
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for name in z.namelist():
                    basename = os.path.basename(name)
                    if basename in ("ffmpeg.exe", "ffprobe.exe"):
                        dest = FFMPEG_DIR / basename
                        dest.write_bytes(z.read(name))
                        if dest.stat().st_size < 1000:
                            raise Exception(f"{basename} extraído parece corrompido.")
                        extracted += 1
                    if extracted == 2:
                        break

            if extracted < 2:
                raise Exception("Não foi possível encontrar ffmpeg.exe e ffprobe.exe no ZIP.")

            # PATH permanente + sessão atual
            add_to_path(str(FFMPEG_DIR))

            if _ffmpeg_works():
                ok(f"ffmpeg e ffprobe instalados em {FFMPEG_DIR}")
                return
            else:
                err("Arquivos extraídos mas não executam. Reinicie o terminal.")
        except Exception as e:
            err(f"Falha ao baixar ffmpeg: {e}")

        print(c("    → Instale manualmente: winget install ffmpeg", C.CYAN))

    elif IS_MAC:
        if shutil.which("brew"):
            run("brew", "install", "ffmpeg")
            if _ffmpeg_works():
                ok("ffmpeg instalado via brew")
                return
        err("Instale com: brew install ffmpeg")

    else:
        for mgr, cmd in [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq", "ffmpeg"]),
            ("pacman",  ["sudo", "pacman",  "-S", "--noconfirm", "ffmpeg"]),
            ("dnf5",    ["sudo", "dnf5",    "install", "-y", "ffmpeg"]),
            ("dnf",     ["sudo", "dnf",     "install", "-y", "ffmpeg"]),
        ]:
            if shutil.which(mgr):
                info(f"Instalando ffmpeg via {mgr}...")
                s, _ = run(*cmd)
                if s:
                    ok("ffmpeg instalado")
                    return
                break
        err("Instale o pacote 'ffmpeg' manualmente.")

# ── SpotiDown via pipx ────────────────────────────────────────────────────────
def install_spotidown(pipx_cmd: list):
    step("Instalando SpotiDown...")
    s, out = run(*pipx_cmd, "upgrade", "spotidown")
    if s:
        ok("SpotiDown atualizado!")
        return
    s, out = run(*pipx_cmd, "install", REPO)
    if s:
        ok("SpotiDown instalado!")
        return
    err("Falha ao instalar SpotiDown.")
    print(c(f"    Saída: {out[:400]}", C.DIM))
    sys.exit(1)

def ensure_path(pipx_cmd: list):
    step("Configurando PATH...")
    run(*pipx_cmd, "ensurepath")
    if IS_WIN:
        for d in [
            Path.home() / ".local" / "bin",
            Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Scripts",
            Path.home() / "AppData" / "Roaming" / "Python" / "Scripts",
        ]:
            if d.exists():
                add_to_path(str(d))
    ok("PATH configurado")

def print_success():
    print(c("\n  " + "─" * 42, C.DIM))
    print(c("  ✔ Instalação concluída!", C.GREEN, C.BOLD))
    print(c("  " + "─" * 42, C.DIM))
    print()
    print(c("  Como usar:", C.CYAN, C.BOLD))
    print(c('  spotidown "angra fireworks"', C.GREEN))
    print(c('  spotidown "metallica ride the lightning"', C.GREEN))
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
    print(c("  " + "─" * 42, C.DIM))

    check_python_version()
    ensure_linux_base()
    ensure_pip()
    pipx_cmd = ensure_pipx()
    ensure_nodejs()   # Node.js antes do yt-dlp
    ensure_ffmpeg()   # ffmpeg depois do Node.js
    install_spotidown(pipx_cmd)
    ensure_path(pipx_cmd)
    print_success()

if __name__ == "__main__":
    main()
