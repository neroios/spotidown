#!/usr/bin/env python3
"""
spotidown - Baixa playlists/albuns/musicas do Spotify em MP3 via YouTube.
Nao precisa de conta Premium, API key ou autenticacao.

Uso:
    spotidown "LINK_SPOTIFY"
    spotidown "LINK_SPOTIFY" "PASTA_DESTINO"
    spotidown "artista album ou musica"
    spotidown "metallica ride the lightning"
"""

import re
import sys
import os
import json
import shutil
import zipfile
import tempfile
import argparse
import unicodedata
import subprocess
import ssl
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote, urlencode

try:
    SSL_CTX = ssl._create_unverified_context()
except AttributeError:
    SSL_CTX = None

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

SPOTIDOWN_DIR = Path.home() / ".spotidown"

FFMPEG_PATH = None
YTDLP_CMD   = None

# ── Cores ANSI ────────────────────────────────────────────────────────────────
class C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

def enable_windows_ansi():
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def c(text, *codes):
    return "".join(codes) + str(text) + C.RESET

def print_banner():
    print(c("\n  SpotiDown", C.GREEN, C.BOLD) + c("  -- Spotify -> MP3 -> ZIP", C.DIM))
    print(c("  " + "-" * 40, C.DIM))

def print_section(label):
    print(c(f"\n  {label}", C.CYAN, C.BOLD))

def safe_filename(name):
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "download"

def truncate(s, n=48):
    return s[:n-3] + "..." if len(s) > n else s

# ── HTTP ──────────────────────────────────────────────────────────────────────
def http_get(url, timeout=20):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 spotidown/5.0"})
    with urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read()

# ── Localizar yt-dlp de forma robusta ────────────────────────────────────────
def find_ytdlp():
    """
    Procura o yt-dlp em todas as localizações possíveis:
    1. No PATH do sistema
    2. No venv do pipx onde o spotidown foi instalado (caso mais comum no Windows)
    3. Nos venvs do pipx do usuário
    4. Via python -m yt_dlp (qualquer python no PATH)
    """

    # 1. No PATH diretamente
    found = shutil.which("yt-dlp")
    if found and _ytdlp_works([found]):
        return [found]

    # 2. No mesmo venv do spotidown (pipx instala tudo junto)
    #    __file__ aponta para dentro do venv: .../pipx/venvs/spotidown/Lib/site-packages/...
    try:
        venv_scripts = Path(sys.executable).parent
        candidates = [
            venv_scripts / "yt-dlp.exe",
            venv_scripts / "yt-dlp",
        ]
        for p in candidates:
            if p.exists() and _ytdlp_works([str(p)]):
                return [str(p)]
    except Exception:
        pass

    # 3. Venvs do pipx: procura em ~/.local/pipx/venvs e ~/pipx/venvs
    pipx_roots = [
        Path.home() / ".local" / "pipx" / "venvs",
        Path.home() / "pipx" / "venvs",
        Path.home() / "AppData" / "Local" / "pipx" / "venvs",
    ]
    for root in pipx_roots:
        if not root.exists():
            continue
        for venv in root.iterdir():
            for rel in ["Scripts/yt-dlp.exe", "Scripts/yt-dlp", "bin/yt-dlp"]:
                p = venv / rel
                if p.exists() and _ytdlp_works([str(p)]):
                    return [str(p)]

    # 4. python -m yt_dlp com qualquer python disponível
    for py in [sys.executable, "python3", "python"]:
        cmd = [py, "-m", "yt_dlp"]
        if _ytdlp_works(cmd):
            return cmd

    return None

def _ytdlp_works(cmd):
    try:
        r = subprocess.run(cmd + ["--version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

# ── Localizar ffmpeg de forma robusta ────────────────────────────────────────
def find_ffmpeg():
    # 1. No PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 2. Pasta portátil do instalador
    portable = SPOTIDOWN_DIR / "ffmpeg" / ("ffmpeg.exe" if IS_WIN else "ffmpeg")
    if portable.exists():
        return str(portable)

    if IS_WIN:
        # 3. Locais comuns de instalação no Windows
        common = [
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            r"C:\Windows\System32\ffmpeg.exe",
        ]
        # 4. Busca no winget/programdata
        for p in common:
            if Path(p).exists():
                return p

        # 5. Dentro do venv do pipx (algumas builds incluem ffmpeg)
        try:
            venv_scripts = Path(sys.executable).parent
            p = venv_scripts / "ffmpeg.exe"
            if p.exists():
                return str(p)
        except Exception:
            pass

    return None

def install_ytdlp():
    print(c("  >> Instalando yt-dlp...", C.YELLOW))
    # Tenta instalar no venv atual (que é o do pipx, quando rodando via spotidown)
    for extra in [[], ["--break-system-packages"]]:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "yt-dlp", "--quiet"] + extra,
                capture_output=True, timeout=120)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    return False

def install_ffmpeg_linux():
    print(c("  >> Instalando ffmpeg...", C.YELLOW))
    for mgr, cmd in [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "-qq", "ffmpeg"]),
        ("pacman",  ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"]),
        ("dnf",     ["sudo", "dnf", "install", "-y", "ffmpeg"]),
    ]:
        if shutil.which(mgr):
            try:
                if mgr == "apt-get":
                    subprocess.run(["sudo", "apt-get", "update", "-qq"], timeout=60)
                r = subprocess.run(cmd, timeout=120)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
    return False

def install_ffmpeg_windows_portable():
    """Baixa ffmpeg estático do GitHub como fallback."""
    import io
    print(c("  >> Baixando ffmpeg portátil...", C.YELLOW))
    ffmpeg_dir = SPOTIDOWN_DIR / "ffmpeg"
    if ffmpeg_dir.exists():
        shutil.rmtree(ffmpeg_dir, ignore_errors=True)
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    try:
        api = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
        req = Request(api, headers={"User-Agent": "spotidown"})
        data = json.loads(urlopen(req, timeout=15, context=SSL_CTX).read())
        url = next(
            (a["browser_download_url"] for a in data.get("assets", [])
             if "win64" in a["name"] and a["name"].endswith(".zip")), None)
        if not url:
            return False
        with urlopen(url, timeout=180, context=SSL_CTX) as resp:
            content = resp.read()
        extracted = 0
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            for name in z.namelist():
                base = os.path.basename(name)
                if base in ("ffmpeg.exe", "ffprobe.exe"):
                    dest = ffmpeg_dir / base
                    dest.write_bytes(z.read(name))
                    extracted += 1
                if extracted == 2:
                    break
        return extracted >= 1
    except Exception as e:
        print(c(f"  ! Falha: {e}", C.RED))
        return False

def check_dependencies():
    global FFMPEG_PATH, YTDLP_CMD
    ok = True

    # yt-dlp
    YTDLP_CMD = find_ytdlp()
    if not YTDLP_CMD:
        print(c("  ~ yt-dlp nao encontrado. Instalando...", C.YELLOW))
        install_ytdlp()
        YTDLP_CMD = find_ytdlp()
    if YTDLP_CMD:
        print(c("  OK yt-dlp: " + YTDLP_CMD[0], C.GREEN))
    else:
        print(c("  ERRO: nao foi possivel encontrar/instalar yt-dlp", C.RED))
        ok = False

    # ffmpeg
    FFMPEG_PATH = find_ffmpeg()
    if not FFMPEG_PATH:
        if IS_WIN:
            install_ffmpeg_windows_portable()
        elif not IS_MAC:
            install_ffmpeg_linux()
        FFMPEG_PATH = find_ffmpeg()
    if FFMPEG_PATH:
        print(c("  OK ffmpeg: " + FFMPEG_PATH, C.GREEN))
    else:
        print(c("  ERRO: ffmpeg nao encontrado. Rode o instalar.py novamente.", C.RED))
        ok = False

    return ok

# ── Metadados: Odesli ─────────────────────────────────────────────────────────
def fetch_odesli(url):
    m    = re.search(r"spotify\.com/(album|playlist|track)/", url)
    kind = m.group(1) if m else "track"
    api  = "https://api.song.link/v1-alpha.1/links?url=" + quote(url) + "&userCountry=BR"
    data = json.loads(http_get(api))
    ents = data.get("entitiesByUniqueId", {})
    key  = next((k for k in ents if k.startswith("SPOTIFY")), None)
    if not key:
        return kind, "", ""
    e = ents[key]
    return kind, e.get("title", ""), e.get("artistName", "")

# ── Metadados: iTunes ─────────────────────────────────────────────────────────
def fetch_itunes(artist, album):
    term   = (artist + " " + album).strip()
    params = urlencode({"term": term, "media": "music", "entity": "song",
                        "limit": "200", "country": "BR"})
    data    = json.loads(http_get("https://itunes.apple.com/search?" + params))
    results = data.get("results", [])
    if not results:
        return []

    album_low  = album.lower()
    artist_low = artist.lower()

    matched = [r for r in results
               if album_low == r.get("collectionName", "").lower()
               and artist_low in r.get("artistName", "").lower()]

    if not matched:
        matched = [r for r in results
                   if album_low in r.get("collectionName", "").lower()
                   and artist_low in r.get("artistName", "").lower()]
        if "live" not in album_low and "vivo" not in album_low:
            matched = [r for r in matched
                       if "live" not in r.get("collectionName", "").lower()
                       and "vivo" not in r.get("collectionName", "").lower()]

    if not matched:
        matched = [r for r in results
                   if artist_low in r.get("artistName", "").lower()]
    if not matched:
        matched = results

    matched.sort(key=lambda r: (r.get("discNumber", 1), r.get("trackNumber", 999)))

    seen, tracks = set(), []
    for r in matched:
        title = r.get("trackName", "")
        art   = r.get("artistName", artist)
        clean_title = re.sub(
            r'(?i)\s*[\(\-\[].*?(remaster|live|vivo|deluxe|bonus|edit|ac[uú]stico|acoustic).*?[\)\-\]]',
            '', title).strip()
        key_t = clean_title.lower()
        if clean_title and key_t not in seen:
            seen.add(key_t)
            tracks.append({"title": clean_title, "artist": art,
                           "query": art + " - " + clean_title})
    return tracks

# ── Metadados: MusicBrainz ────────────────────────────────────────────────────
def fetch_musicbrainz(artist, album):
    queries = [
        'release:"' + album + '" AND artist:"' + artist + '"',
        'release:' + album + ' AND artist:' + artist,
    ]
    releases = []
    for q in queries:
        try:
            params = urlencode({"query": q, "fmt": "json", "limit": "10"})
            data   = json.loads(http_get(
                "https://musicbrainz.org/ws/2/release?" + params, timeout=15))
            releases = data.get("releases", [])
            if releases:
                break
        except Exception:
            continue
    if not releases:
        return []

    def score(r):
        return (1 if r.get("status", "").lower() == "official" else 0,
                r.get("track-count", 0))

    rid = max(releases, key=score)["id"]
    try:
        detail = json.loads(http_get(
            "https://musicbrainz.org/ws/2/release/" + rid + "?inc=recordings&fmt=json",
            timeout=15))
    except Exception:
        return []

    tracks = []
    for medium in detail.get("media", []):
        for t in medium.get("tracks", []):
            title = t.get("title", "") or t.get("recording", {}).get("title", "")
            if title:
                tracks.append({"title": title, "artist": artist,
                               "query": artist + " - " + title})
    return tracks

# ── Metadados: yt-dlp flat ────────────────────────────────────────────────────
def fetch_ytdlp_flat(url):
    cmd = YTDLP_CMD + ["--flat-playlist", "--dump-single-json",
                       "--no-warnings", "--quiet", "--no-check-certificates", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0 or not r.stdout.strip():
            return "", "", []
        data    = json.loads(r.stdout)
        entries = data.get("entries", [])
        if not entries:
            return "", "", []
        name   = data.get("title", "")
        artist = data.get("uploader", "") or data.get("channel", "")
        tracks = []
        for e in entries:
            t = e.get("title", "")
            a = e.get("artist", "") or e.get("uploader", "") or artist
            tracks.append({"title": t, "artist": a,
                           "query": (a + " - " + t) if a else t})
        return name, artist, tracks
    except Exception:
        return "", "", []

# ── Busca por texto ───────────────────────────────────────────────────────────
def search_and_resolve(query: str) -> dict:
    print_section("Buscando no iTunes: " + query + "...")
    params = urlencode({"term": query, "media": "music", "entity": "song",
                        "limit": "10", "country": "BR"})
    try:
        data    = json.loads(http_get("https://itunes.apple.com/search?" + params))
        results = data.get("results", [])
        if not results:
            print(c("  ✗ Nenhum resultado: " + query, C.RED))
            return {}
        first  = results[0]
        artist = first.get("artistName", "")
        album  = first.get("collectionName", "")
        song   = first.get("trackName", "")
        if not artist or not album:
            return {}
        print(c("  ✔ Encontrado: " + album + " — " + artist, C.GREEN))
        print(c("  (faixa: " + song + ")", C.DIM))
        tracks = fetch_itunes(artist, album)
        if tracks:
            print(c("  ✔ " + str(len(tracks)) + " faixa(s) no album", C.GREEN))
            return {"name": album, "artist": artist, "tracks": tracks}
    except Exception as e:
        print(c("  ✗ Erro: " + str(e), C.RED))
    return {}

# ── Orquestracao de metadados ─────────────────────────────────────────────────
def fetch_metadata(url):
    print_section("Buscando metadados...")

    name, artist, tracks = fetch_ytdlp_flat(url)
    if tracks:
        print(c("  OK " + str(len(tracks)) + " faixa(s) via yt-dlp", C.GREEN))
        return {"name": name, "artist": artist, "tracks": tracks}

    kind, name, artist = "", "", ""
    try:
        kind, name, artist = fetch_odesli(url)
        if name and artist:
            print(c("  OK: " + name + " -- " + artist, C.GREEN))
    except Exception as e:
        print(c("  ~ Odesli falhou: " + str(e), C.YELLOW))

    if name and artist and kind != "playlist":
        try:
            tracks = fetch_itunes(artist, name)
            if tracks:
                print(c("  OK " + str(len(tracks)) + " faixa(s) via iTunes", C.GREEN))
                return {"name": name, "artist": artist, "tracks": tracks}
        except Exception as e:
            print(c("  ~ iTunes falhou: " + str(e), C.YELLOW))

    if name and artist and kind != "playlist":
        try:
            tracks = fetch_musicbrainz(artist, name)
            if tracks:
                print(c("  OK " + str(len(tracks)) + " faixa(s) via MusicBrainz", C.GREEN))
                return {"name": name, "artist": artist, "tracks": tracks}
        except Exception as e:
            print(c("  ~ MusicBrainz falhou: " + str(e), C.YELLOW))

    if name and artist:
        return {"name": name, "artist": artist,
                "tracks": [{"title": name, "artist": artist,
                            "query": artist + " - " + name}]}
    return {}

# ── Progresso ─────────────────────────────────────────────────────────────────
def progress_bar(done, total, width=22):
    filled = int(done / total * width) if total else 0
    bar    = chr(9608) * filled + chr(9617) * (width - filled)
    pct    = str(int(done / total * 100)).rjust(3) + "%" if total else "..."
    return "[" + c(bar, C.GREEN) + "] " + pct + "  " + str(done) + "/" + str(total)

# ── Download ──────────────────────────────────────────────────────────────────
def download_track(query, out_dir, index):
    out_template = str(out_dir / (str(index).zfill(3) + " - %(title)s.%(ext)s"))
    ffmpeg_dir   = str(Path(FFMPEG_PATH).parent)

    cmd = YTDLP_CMD + [
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--postprocessor-args", "ffmpeg:-b:a 320k",
        "--embed-thumbnail",
        "--add-metadata",
        "--ffmpeg-location", ffmpeg_dir,
        "--output", out_template,
        "--no-check-certificates",
        "--no-warnings",
        "ytsearch1:" + query,
    ]

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if r.returncode != 0:
            # Loga o erro real para o arquivo de log (não polui o terminal)
            log = SPOTIDOWN_DIR / "errors.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n=== {query} ===\n{r.stderr}\n")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False

def download_all(tracks, out_dir):
    total = len(tracks)
    fails = []
    print()
    for i, track in enumerate(tracks, 1):
        label = truncate(track["artist"] + " - " + track["title"])
        print("\r  " + progress_bar(i-1, total) + "  " + c(label, C.DIM) + "          ",
              end="", flush=True)
        if not download_track(track["query"], out_dir, i):
            fails.append(track)
    print("\r  " + progress_bar(total, total) + "                                ", flush=True)
    print()

    if fails:
        print(c(f"  ~ {len(fails)} faixa(s) com erro (veja ~/.spotidown/errors.log)", C.YELLOW))

    audio_exts = {".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav"}
    return [f for f in sorted(out_dir.glob("*.*")) if f.suffix.lower() in audio_exts]

# ── ZIP ───────────────────────────────────────────────────────────────────────
def build_zip(files, dest_dir, zip_name):
    zip_path = dest_dir / (zip_name + ".zip")
    counter  = 1
    while zip_path.exists():
        zip_path = dest_dir / (zip_name + " (" + str(counter) + ").zip")
        counter += 1
    print_section("Criando ZIP...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, f in enumerate(files, 1):
            zf.write(f, zip_name + "/" + f.name)
            print("\r  " + progress_bar(i, len(files)) + "  ", end="", flush=True)
    print()
    return zip_path

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    enable_windows_ansi()
    print_banner()

    if "--update" in sys.argv:
        print("Atualizando o SpotiDown...")
        pipx = shutil.which("pipx")
        if pipx:
            subprocess.run([pipx, "upgrade", "spotidown"])
        else:
            subprocess.run([sys.executable, "-m", "pipx", "upgrade", "spotidown"])
        sys.exit(0)

    parser = argparse.ArgumentParser(prog="spotidown")
    parser.add_argument("url",   help='Link Spotify ou busca: "metallica ride the lightning"')
    parser.add_argument("pasta", nargs="?", default="~/Music")
    parser.add_argument("--nome", "-n", default=None)

    args     = parser.parse_args()
    query    = args.url.strip()
    dest_dir = Path(args.pasta).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    print_section("Verificando dependencias...")
    if not check_dependencies():
        sys.exit(1)

    is_link = "spotify.com" in query or query.startswith("http")
    meta    = fetch_metadata(query) if is_link else search_and_resolve(query)

    if not meta or not meta.get("tracks"):
        print(c("\n  ERRO: Nao foi possivel obter as faixas.", C.RED))
        sys.exit(1)

    tracks = meta["tracks"]
    if args.nome:
        zip_name = safe_filename(args.nome)
    elif meta.get("name") and meta.get("artist"):
        zip_name = safe_filename(meta["artist"] + " - " + meta["name"])
    else:
        zip_name = safe_filename(meta.get("name", "download"))

    print(c("\n  Destino : " + str(dest_dir), C.DIM))
    print(c("  ZIP     : " + zip_name + ".zip", C.DIM))
    print(c("  Faixas  : " + str(len(tracks)), C.DIM))

    print_section("Baixando musicas via YouTube...")
    tmp_dir = Path(tempfile.mkdtemp(prefix="spotidown_"))
    try:
        files = download_all(tracks, tmp_dir)
        if not files:
            log = SPOTIDOWN_DIR / "errors.log"
            print(c("  ERRO: Nenhuma musica foi baixada.", C.RED))
            print(c(f"  Detalhes do erro em: {log}", C.YELLOW))
            sys.exit(1)
        print(c("  OK " + str(len(files)) + " musica(s) baixada(s)", C.GREEN))

        zip_path = build_zip(files, dest_dir, zip_name)
        size_mb  = zip_path.stat().st_size / (1024 * 1024)
        print(c("\n  Concluido!", C.GREEN, C.BOLD))
        print(c("  Arquivo : " + str(zip_path), C.CYAN))
        print(c("  Tamanho : " + f"{size_mb:.1f}" + " MB  (" + str(len(files)) + " faixa(s))", C.DIM))
        print()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
