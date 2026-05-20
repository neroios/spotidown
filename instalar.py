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
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LIN = sys.platform == "linux"

REPO = "git+https://github.com/neroios/spotidown"

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

def ensure_pip():
    """Garante que pip está disponível."""
    success, _ = run(sys.executable, "-m", "pip", "--version")
    if not success:
        info("Instalando pip...")
        run(sys.executable, "-m", "ensurepip", "--upgrade")

def ensure_pipx() -> list:
    """
    Retorna o comando pipx como lista.
    Instala se necessário. No Windows usa 'python -m pipx' se pipx não estiver no PATH.
    """
    step("Verificando pipx...")

    if shutil.which("pipx"):
        ok("pipx encontrado no PATH")
        return ["pipx"]

    success, _ = run(sys.executable, "-m", "pipx", "--version")
    if success:
        ok("pipx disponível via python -m pipx")
        return [sys.executable, "-m", "pipx"]

    info("pipx não encontrado. Instalando...")
    ensure_pip()

    cmds = [
        [sys.executable, "-m", "pip", "install", "pipx", "--quiet"],
        [sys.executable, "-m", "pip", "install", "pipx", "--quiet", "--break-system-packages"],
    ]
    installed = False
    for cmd in cmds:
        success, out = run(*cmd)
        if success:
            installed = True
            break

    if not installed:
        err("Não foi possível instalar pipx automaticamente.")
        if IS_WIN:
            print(c("    → Rode: python -m pip install pipx", C.CYAN))
        else:
            print(c("    → Rode: pip install pipx", C.CYAN))
        sys.exit(1)

    run(sys.executable, "-m", "pipx", "ensurepath")
    ok("pipx instalado")
    return [sys.executable, "-m", "pipx"]

def ensure_nodejs():
    """Garante que o Node.js está instalado para o yt-dlp não falhar no YouTube."""
    step("Verificando Node.js (JavaScript runtime)...")

    if shutil.which("node"):
        ok("Node.js encontrado")
        return

    info("Node.js não encontrado. Instalando...")

    if IS_WIN:
        if shutil.which("winget"):
            success, _ = run("winget", "install", "OpenJS.NodeJS",
                             "--accept-package-agreements",
                             "--accept-source-agreements", "--silent")
            if success and shutil.which("node"):
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
            ("dnf",     ["sudo", "dnf",     "install", "-y", "nodejs"]),
            ("pacman",  ["sudo", "pacman",  "-S", "--noconfirm", "nodejs"]),
        ]:
            if shutil.which(pkg_mgr):
                info(f"Instalando Node.js via {pkg_mgr}...")
                success, _ = run(*cmd)
                if success:
                    ok("Node.js instalado")
                    return
                break
        err("Não foi possível instalar Node.js.")
        print(c("    → Rode: sudo apt install nodejs", C.CYAN))

def ensure_ffmpeg():
    """Instala ffmpeg e ffprobe se não estiverem disponíveis."""
    step("Verificando ffmpeg/ffprobe...")

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        ok("ffmpeg e ffprobe encontrados")
        return

    info("ffmpeg ou ffprobe não encontrados. Instalando...")

    if IS_WIN:
        if shutil.which("winget"):
            success, _ = run("winget", "install", "ffmpeg",
                             "--accept-package-agreements",
                             "--accept-source-agreements", "--silent")
            if success and shutil.which("ffmpeg"):
                ok("ffmpeg/ffprobe instalados via winget")
                return

        info("Tentando baixar ffmpeg via yt-dlp estático...")
        ffmpeg_dir = Path.home() / ".spotidown" / "ffmpeg"
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)

        try:
            import urllib.request, zipfile, io, json as _json
            api = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
            req = urllib.request.Request(api, headers={"User-Agent": "spotidown-installer"})
            data = _json.loads(urllib.request.urlopen(req, timeout=15).read())
            asset_url = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if "win64" in a["name"] and a["name"].endswith(".zip")),
                None
            )
            if asset_url:
                print(c("    Baixando ffmpeg estático (pode demorar)...", C.DIM), end="", flush=True)
                with urllib.request.urlopen(asset_url, timeout=120) as resp:
                    content = resp.read()
                print(c(" OK", C.GREEN))
                
                # MUDANÇA AQUI: Extraindo ffmpeg E ffprobe
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    extracted = 0
                    for name in z.namelist():
                        if name.endswith("ffmpeg.exe") or name.endswith("ffprobe.exe"):
                            file_name = os.path.basename(name)
                            (ffmpeg_dir / file_name).write_bytes(z.read(name))
                            extracted += 1
                        if extracted == 2:
                            break

                current = os.environ.get("PATH", "")
                ffmpeg_str = str(ffmpeg_dir)
                if ffmpeg_str not in current:
                    subprocess.run(
                        ["setx", "PATH", f"{current};{ffmpeg_str}"],
                        capture_output=True
                    )
                ok(f"ffmpeg e ffprobe instalados em {ffmpeg_dir}")
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
            ("dnf",     ["sudo", "dnf",     "install", "-y", "ffmpeg"]),
            ("pacman",  ["sudo", "pacman",  "-S", "--noconfirm", "ffmpeg"]),
        ]:
            if shutil.which(pkg_mgr):
                info(f"Instalando ffmpeg via {pkg_mgr}...")
                success, _ = run(*cmd)
                if success:
                    ok("ffmpeg instalado")
                    return
                break
        err("Não foi possível instalar ffmpeg.")
        print(c("    → Rode: sudo apt install ffmpeg", C.CYAN))

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
                current = os.environ.get("PATH", "")
                if str(d) not in current:
                    subprocess.run(
                        ["setx", "PATH", f"{current};{d}"],
                        capture_output=True
                    )
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
    ensure_pip()
    pipx_cmd = ensure_pipx()
    ensure_nodejs()  # <--- NOVA ETAPA DE VERIFICAÇÃO ADICIONADA AQUI
    ensure_ffmpeg()
    install_spotidown(pipx_cmd)
    ensure_path(pipx_cmd)
    print_success()

if __name__ == "__main__":
    main()
