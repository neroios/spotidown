#!/usr/bin/env python3
"""
instalar.py — Instalador universal do SpotiDown.
Funciona em Windows 10/11, Linux (apt/pacman/dnf/zypper/apk) e macOS.

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
import urllib.error
import zipfile
import tarfile
import io
import json
import ssl
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LIN = sys.platform == "linux"

REPO          = "https://github.com/neroios/spotidown/archive/refs/heads/main.zip"
SPOTIDOWN_DIR = Path.home() / ".spotidown"
FFMPEG_DIR    = SPOTIDOWN_DIR / "ffmpeg"
NODEJS_DIR    = SPOTIDOWN_DIR / "nodejs"

# Tamanho mínimo aceitável para um binário real (10 MB)
MIN_BINARY_SIZE = 10 * 1024 * 1024

# SSL permissivo (VMs e redes corporativas costumam ter problemas de cert)
try:
    SSL_CTX = ssl._create_unverified_context()
except AttributeError:
    SSL_CTX = None

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

def run(*args, timeout=180, **kwargs):
    try:
        r = subprocess.run(list(args), capture_output=True, text=True,
                           timeout=timeout, **kwargs)
        return r.returncode == 0, r.stdout + r.stderr
    except Exception as e:
        return False, str(e)

def cmd_works(cmd, flag="--version"):
    path = shutil.which(cmd)
    if not path:
        return False
    try:
        r = subprocess.run([path, flag], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

def http_download(url, desc="Baixando", timeout=300):
    """
    Baixa uma URL com barra de progresso. Retorna bytes ou lança exceção.
    Tenta primeiro com SSL verificado, depois sem verificação.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "spotidown-installer/2.0"})
    for ctx in [None, SSL_CTX]:
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                chunks = []
                downloaded = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded / total * 30)
                        bar = "█" * pct + "░" * (30 - pct)
                        mb  = downloaded / 1024 / 1024
                        print(f"\r    [{bar}] {mb:.1f} MB", end="", flush=True)
                print()
                return b"".join(chunks)
        except ssl.SSLError:
            continue
        except Exception as e:
            raise e
    raise Exception("Falha no download após tentativas com e sem SSL")

def add_to_path_permanent(new_dir: str):
    """Registro do Windows — sem bug de truncamento do setx."""
    if not IS_WIN:
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0,
                             winreg.KEY_ALL_ACCESS)
        try:
            cur, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            cur = ""
        if new_dir.lower() not in cur.lower():
            sep = ";" if cur and not cur.endswith(";") else ""
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, cur + sep + new_dir)
        winreg.CloseKey(key)
    except Exception as e:
        info(f"Aviso PATH registro: {e}")

def add_to_path_session(new_dir: str):
    if new_dir.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = new_dir + os.pathsep + os.environ.get("PATH", "")

def add_to_path(new_dir: str):
    add_to_path_permanent(new_dir)
    add_to_path_session(new_dir)

# ── Python ────────────────────────────────────────────────────────────────────
def check_python_version():
    step("Verificando Python...")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        err(f"Python 3.10+ necessário. Você tem {major}.{minor}.")
        if IS_WIN:
            print(c("    → Baixe em: https://python.org/downloads", C.CYAN))
        sys.exit(1)
    ok(f"Python {major}.{minor}")

# ── Linux base ────────────────────────────────────────────────────────────────
def ensure_linux_base():
    if not IS_LIN:
        return
    step("Verificando pacotes base do Linux...")
    s1, _ = run(sys.executable, "-c", "import venv")
    s2, _ = run(sys.executable, "-m", "pip", "--version")
    if s1 and s2:
        ok("pip e venv OK")
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
            s, out = run(*(base_cmd + pkgs))
            if s:
                ok(f"Instalado via {mgr}")
                return
            err(f"Falha via {mgr}: {out[:200]}")
            sys.exit(1)
    err("Gerenciador de pacotes não reconhecido.")
    sys.exit(1)

def ensure_pip():
    s, _ = run(sys.executable, "-m", "pip", "--version")
    if not s:
        run(sys.executable, "-m", "ensurepip", "--upgrade")

# ── pipx ──────────────────────────────────────────────────────────────────────
def ensure_pipx() -> list:
    step("Verificando pipx...")
    if cmd_works("pipx"):
        ok("pipx OK")
        return ["pipx"]
    s, _ = run(sys.executable, "-m", "pipx", "--version")
    if s:
        ok("pipx OK (via python -m)")
        return [sys.executable, "-m", "pipx"]
    info("Instalando pipx...")
    ensure_pip()
    for extra in [[], ["--break-system-packages"]]:
        s, _ = run(sys.executable, "-m", "pip", "install", "pipx", "--quiet", *extra)
        if s:
            break
    else:
        err("Não foi possível instalar pipx.")
        sys.exit(1)
    run(sys.executable, "-m", "pipx", "ensurepath")
    ok("pipx instalado")
    return [sys.executable, "-m", "pipx"]

# ── ffmpeg ────────────────────────────────────────────────────────────────────
def _ffmpeg_ok():
    """Verifica ffmpeg E ffprobe com tamanho mínimo."""
    for name in (["ffmpeg", "-version"], ["ffprobe", "-version"]):
        path = shutil.which(name[0])
        if not path:
            # Tenta na pasta portátil diretamente
            ext  = ".exe" if IS_WIN else ""
            path = str(FFMPEG_DIR / (name[0] + ext))
            if not Path(path).exists():
                return False
        try:
            # Verifica tamanho — arquivo corrompido/parcial rejeita aqui
            if Path(path).stat().st_size < MIN_BINARY_SIZE:
                return False
            r = subprocess.run([path, name[1]], capture_output=True, timeout=10)
            if r.returncode != 0:
                return False
        except Exception:
            return False
    return True

def _download_ffmpeg_windows():
    """
    Baixa ffmpeg para Windows de fontes confiáveis em ordem de preferência.
    Fonte 1: BtbN/FFmpeg-Builds (releases estáveis, tamanho real ~70MB)
    Fonte 2: yt-dlp/FFmpeg-Builds (fallback)
    """
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

    sources = [
        # BtbN — builds oficiais estáveis para Windows
        {
            "api":    "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest",
            "filter": lambda a: "win64" in a["name"] and "gpl" in a["name"]
                                and a["name"].endswith(".zip")
                                and "shared" not in a["name"],
        },
        # yt-dlp/FFmpeg-Builds — fallback
        {
            "api":    "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest",
            "filter": lambda a: "win64" in a["name"] and a["name"].endswith(".zip"),
        },
    ]

    for src in sources:
        try:
            info(f"Buscando release em {src['api'].split('/repos/')[1].split('/releases')[0]}...")
            req  = urllib.request.Request(
                src["api"], headers={"User-Agent": "spotidown-installer"})
            data = json.loads(urllib.request.urlopen(req, timeout=15, context=SSL_CTX).read())
            url  = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if src["filter"](a)),
                None)
            if not url:
                info("Nenhum asset encontrado nessa fonte, tentando próxima...")
                continue

            info(f"Baixando ffmpeg (~70MB)...")
            content = http_download(url)

            if len(content) < MIN_BINARY_SIZE:
                info(f"Download suspeito ({len(content)//1024}KB), tentando próxima fonte...")
                continue

            # Extrai ffmpeg.exe e ffprobe.exe de qualquer subpasta do ZIP
            extracted = {}
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for entry in z.namelist():
                    base = os.path.basename(entry).lower()
                    if base in ("ffmpeg.exe", "ffprobe.exe") and base not in extracted:
                        data_bytes = z.read(entry)
                        if len(data_bytes) < MIN_BINARY_SIZE:
                            continue  # pula arquivo interno corrompido
                        dest = FFMPEG_DIR / os.path.basename(entry)
                        dest.write_bytes(data_bytes)
                        extracted[base] = dest
                    if len(extracted) == 2:
                        break

            if len(extracted) < 2:
                info(f"Só encontrei {len(extracted)}/2 binários, tentando próxima fonte...")
                shutil.rmtree(FFMPEG_DIR, ignore_errors=True)
                FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
                continue

            add_to_path(str(FFMPEG_DIR))
            ok(f"ffmpeg instalado em {FFMPEG_DIR}")
            return True

        except Exception as e:
            info(f"Falha nessa fonte: {e}")
            continue

    return False

def ensure_ffmpeg():
    step("Verificando ffmpeg/ffprobe...")

    # Sempre adiciona a pasta portátil ao PATH da sessão
    if FFMPEG_DIR.exists():
        add_to_path_session(str(FFMPEG_DIR))

    if _ffmpeg_ok():
        ok("ffmpeg e ffprobe OK")
        return

    # Arquivos corrompidos/parciais: limpa e recomeça
    if FFMPEG_DIR.exists():
        info("Arquivos ffmpeg inválidos encontrados. Limpando e reinstalando...")
        shutil.rmtree(FFMPEG_DIR, ignore_errors=True)

    info("ffmpeg não encontrado ou corrompido. Instalando...")

    if IS_WIN:
        if _download_ffmpeg_windows():
            if _ffmpeg_ok():
                return
            err("ffmpeg baixado mas não executa corretamente.")
        else:
            err("Não foi possível baixar ffmpeg automaticamente.")
        print(c("    → Instale manualmente: winget install ffmpeg", C.CYAN))
        print(c("    → Ou baixe em: https://ffmpeg.org/download.html", C.CYAN))

    elif IS_MAC:
        if shutil.which("brew"):
            info("Instalando via brew...")
            s, _ = run("brew", "install", "ffmpeg", timeout=300)
            if s and _ffmpeg_ok():
                ok("ffmpeg instalado via brew")
                return
        err("Instale com: brew install ffmpeg")

    else:  # Linux
        managers = [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq", "ffmpeg"]),
            ("pacman",  ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"]),
            ("dnf5",    ["sudo", "dnf5", "install", "-y", "ffmpeg-free"]),
            ("dnf",     ["sudo", "dnf", "install", "-y", "ffmpeg-free"]),
            ("zypper",  ["sudo", "zypper", "install", "-y", "ffmpeg"]),
            ("apk",     ["sudo", "apk", "add", "ffmpeg"]),
        ]
        for mgr, cmd in managers:
            if shutil.which(mgr):
                info(f"Instalando via {mgr}...")
                if mgr == "apt-get":
                    run("sudo", "apt-get", "update", "-qq")
                s, _ = run(*cmd, timeout=300)
                if s and _ffmpeg_ok():
                    ok("ffmpeg instalado")
                    return
                break
        err("Não foi possível instalar ffmpeg. Instale manualmente.")

# ── SpotiDown ─────────────────────────────────────────────────────────────────
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

def ensure_path_entries(pipx_cmd: list):
    step("Configurando PATH...")
    run(*pipx_cmd, "ensurepath")
    if IS_WIN:
        candidates = [
            Path.home() / "pipx" / "bin",
            Path.home() / ".local" / "bin",
            Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Scripts",
            Path.home() / "AppData" / "Roaming" / "Python" / "Scripts",
        ]
        for d in candidates:
            if d.exists():
                add_to_path(str(d))
    ok("PATH configurado")

def print_success():
    print(c("\n  " + "─" * 44, C.DIM))
    print(c("  ✔ Instalação concluída!", C.GREEN, C.BOLD))
    print(c("  " + "─" * 44, C.DIM))
    print()
    print(c("  Como usar:", C.CYAN, C.BOLD))
    print(c('  spotidown "angra fireworks"', C.GREEN))
    print(c('  spotidown "metallica ride the lightning"', C.GREEN))
    print(c('  spotidown "https://open.spotify.com/album/xxx"', C.GREEN))
    print()
    if IS_WIN:
        print(c("  ⚠  Feche e reabra o PowerShell antes de usar.", C.YELLOW, C.BOLD))
    else:
        print(c("  ⚠  Abra um novo terminal antes de usar.", C.YELLOW, C.BOLD))
    print()

def main():
    enable_ansi()
    print(c("\n  ♫ SpotiDown — Instalador Universal", C.GREEN, C.BOLD))
    print(c(f"  {platform.system()} {platform.release()} | Python {sys.version.split()[0]}", C.DIM))
    print(c("  " + "─" * 44, C.DIM))

    check_python_version()
    ensure_linux_base()
    ensure_pip()
    pipx_cmd = ensure_pipx()
    ensure_ffmpeg()
    install_spotidown(pipx_cmd)
    ensure_path_entries(pipx_cmd)
    print_success()

if __name__ == "__main__":
    main()
