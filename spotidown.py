#!/usr/bin/env python3
"""
spotidown - Baixa playlists/albuns/musicas do Spotify em MP3 via YouTube.
Nao precisa de conta Premium, API key ou autenticacao.

Uso:
    python3 spotidown.py "LINK_SPOTIFY" "PASTA_DESTINO"
    python3 spotidown.py "LINK_SPOTIFY"
    python3 spotidown.py "artista album ou musica" "PASTA_DESTINO"
    python3 spotidown.py "metallica ride the lightning"

Requer apenas Python 3.10+ instalado. O resto e instalado automaticamente.
"""

import re
import sys
import json
import shutil
import zipfile
import tempfile
import argparse
import unicodedata
import subprocess
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote, urlencode

# ── Plataforma ────────────────────────────────────────────────────────────────
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

FFMPEG_WIN_PATHS = [
    str(Path.home() / ".spotidown" / "ffmpeg" / "ffmpeg.exe"),
    r"C:\Users\Admin\Downloads\LosslessCut-win-x64\resources\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
]

# Globals preenchidos em check_dependencies()
FFMPEG_PATH = None
YTDLP_CMD   = None

# ── Cores ANSI ───────────────────────────────────────────────────────────────
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
    with urlopen(req, timeout=timeout) as r:
        return r.read()

# ── Dependencias ──────────────────────────────────────────────────────────────
def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    if IS_WIN:
        for p in FFMPEG_WIN_PATHS:
            if Path(p).exists():
                return p
    return None

def find_ytdlp():
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    try:
        r = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"],
                           capture_output=True, timeout=10)
        if r.returncode == 0:
            return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        pass
    return None

def install_ytdlp():
    print(c("  >> Instalando yt-dlp...", C.YELLOW))
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
    print(c("  >> Instalando ffmpeg via apt...", C.YELLOW))
    try:
        subprocess.run(["sudo", "apt-get", "update", "-qq"], timeout=60, check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "ffmpeg"],
                       timeout=120, check=True)
        return True
    except Exception:
        return False

def install_ffmpeg_windows():
    print(c("  >> Baixando ffmpeg (GitHub)...", C.YELLOW))
    try:
        import io
        ffmpeg_dir = Path.home() / ".spotidown" / "ffmpeg"
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        api  = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
        data = json.loads(urlopen(
            Request(api, headers={"User-Agent": "spotidown"}), timeout=15).read())
        url  = next(
            (a["browser_download_url"] for a in data.get("assets", [])
             if "win64" in a["name"] and a["name"].endswith(".zip")), None)
        if not url:
            return False
        with urlopen(url, timeout=180) as resp:
            content = resp.read()
        import zipfile as zf
        with zf.ZipFile(io.BytesIO(content)) as z:
            for name in z.namelist():
                if name.endswith("ffmpeg.exe"):
                    (ffmpeg_dir / "ffmpeg.exe").write_bytes(z.read(name))
                    return True
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
        print(c("  OK yt-dlp", C.GREEN))
    else:
        print(c("  ERRO: instale manualmente: pip install yt-dlp", C.RED))
        ok = False

    # ffmpeg
    FFMPEG_PATH = find_ffmpeg()
    if not FFMPEG_PATH:
        print(c("  ~ ffmpeg nao encontrado. Instalando...", C.YELLOW))
        if IS_WIN:
            install_ffmpeg_windows()
        elif not IS_MAC:
            install_ffmpeg_linux()
        else:
            print(c("  ! macOS: brew install ffmpeg", C.YELLOW))
        FFMPEG_PATH = find_ffmpeg()
    if FFMPEG_PATH:
        print(c("  OK ffmpeg", C.GREEN))
    else:
        if IS_MAC:
            print(c("  ERRO: brew install ffmpeg", C.RED))
        else:
            print(c("  ERRO: nao foi possivel instalar ffmpeg", C.RED))
        ok = False

    return ok

# ── Metadados: Odesli (nome + artista) ───────────────────────────────────────
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

# ── Metadados: iTunes Search API (tracklist completa, sem auth) ───────────────
def fetch_itunes(artist, album):
    # Busca com album + artista
    term   = (artist + " " + album).strip()
    params = urlencode({"term": term, "media": "music", "entity": "song",
                        "limit": "200", "country": "BR"})
    data    = json.loads(http_get("https://itunes.apple.com/search?" + params))
    results = data.get("results", [])
    if not results:
        return []

    album_low  = album.lower()
    artist_low = artist.lower()

    # Tenta filtrar pelo album exato
    matched = [r for r in results
               if album_low in r.get("collectionName", "").lower()
               and artist_low in r.get("artistName", "").lower()]

    # Relaxa: so artista
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
        
        # Filtra sufixos como (Remastered), - Live, [Deluxe] para limpar o nome
        clean_title = re.sub(r'(?i)\s*[\(\-\[].*?(remaster|live|deluxe|bonus|edit).*?[\)\-\]]', '', title).strip()
        
        # Usa o nome limpo como chave para evitar duplicatas
        # (ex: "Música" e "Música (Remastered)" se tornarão a mesma coisa e a 2ª será ignorada)
        key_t = clean_title.lower()
        
        if clean_title and key_t not in seen:
            seen.add(key_t)
            # Adiciona "official audio" na busca oculta do YouTube para fugir de shows ao vivo
            query_str = art + " - " + clean_title + " official audio"
            tracks.append({"title": clean_title, "artist": art, "query": query_str})
            
    return tracks
# ── Metadados: MusicBrainz (fallback) ────────────────────────────────────────
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
        official = 1 if r.get("status", "").lower() == "official" else 0
        return (official, r.get("track-count", 0))

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
                       "--no-warnings", "--quiet", url]
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


# ── Busca por texto no iTunes ─────────────────────────────────────────────────
def search_and_resolve(query: str) -> dict:
    """
    Recebe texto livre ("metallica ride the lightning") e:
    1. Busca no iTunes pra achar artista + album
    2. Retorna metadados completos do album
    """
    print_section("Buscando no iTunes: " + query + "...")

    params = urlencode({
        "term":    query,
        "media":   "music",
        "entity":  "song",
        "limit":   "10",
        "country": "BR",
    })
    try:
        data    = json.loads(http_get("https://itunes.apple.com/search?" + params))
        results = data.get("results", [])
        if not results:
            print(c("  ✗ Nenhum resultado encontrado para: " + query, C.RED))
            return {}

        # Pega o primeiro resultado com album
        first   = results[0]
        artist  = first.get("artistName", "")
        album   = first.get("collectionName", "")
        song    = first.get("trackName", "")

        if not artist or not album:
            print(c("  ✗ Nao foi possivel identificar o album.", C.RED))
            return {}

        print(c("  ✔ Encontrado: " + album + " — " + artist, C.GREEN))
        print(c("  (faixa: " + song + ")", C.DIM))

        # Busca o album completo
        tracks = fetch_itunes(artist, album)
        if tracks:
            print(c("  ✔ " + str(len(tracks)) + " faixa(s) no album", C.GREEN))
            return {"name": album, "artist": artist, "tracks": tracks}
    except Exception as e:
        print(c("  ✗ Erro na busca: " + str(e), C.RED))
    return {}

# ── Orquestracao de metadados ─────────────────────────────────────────────────
def fetch_metadata(url):
    print_section("Buscando metadados...")

    # 1. yt-dlp flat
    name, artist, tracks = fetch_ytdlp_flat(url)
    if tracks:
        print(c("  OK " + str(len(tracks)) + " faixa(s) via yt-dlp", C.GREEN))
        return {"name": name, "artist": artist, "tracks": tracks}

    # 2. Odesli -> nome + artista
    kind, name, artist = "", "", ""
    try:
        kind, name, artist = fetch_odesli(url)
        if name and artist:
            print(c("  OK identificado: " + name + " -- " + artist, C.GREEN))
    except Exception as e:
        print(c("  ~ Odesli falhou: " + str(e), C.YELLOW))

    # 3. iTunes -> tracklist (mais rapido e confiavel)
    if name and artist and kind != "playlist":
        try:
            tracks = fetch_itunes(artist, name)
            if tracks:
                print(c("  OK " + str(len(tracks)) + " faixa(s) via iTunes", C.GREEN))
                return {"name": name, "artist": artist, "tracks": tracks}
            print(c("  ~ iTunes nao encontrou faixas", C.YELLOW))
        except Exception as e:
            print(c("  ~ iTunes falhou: " + str(e), C.YELLOW))

    # 4. MusicBrainz -> fallback
    if name and artist and kind != "playlist":
        try:
            tracks = fetch_musicbrainz(artist, name)
            if tracks:
                print(c("  OK " + str(len(tracks)) + " faixa(s) via MusicBrainz", C.GREEN))
                return {"name": name, "artist": artist, "tracks": tracks}
            print(c("  ~ MusicBrainz nao encontrou faixas", C.YELLOW))
        except Exception as e:
            print(c("  ~ MusicBrainz falhou: " + str(e), C.YELLOW))

    # 5. Faixa unica
    if name and artist:
        print(c("  ~ Baixando como faixa unica: " + name, C.YELLOW))
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
    out_template = str(out_dir / (str(index).zfill(3) + " - %(artist)s - %(title)s.%(ext)s"))
    cmd = YTDLP_CMD + [
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--postprocessor-args", "ffmpeg:-b:a 320k",
        "--embed-thumbnail",
        "--add-metadata",
        "--ffmpeg-location", FFMPEG_PATH,
        "--output", out_template,
        "--quiet",
        "--no-warnings",
        "ytsearch1:" + query,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        return r.returncode == 0
    except Exception:
        return False

def download_all(tracks, out_dir):
    total = len(tracks)
    fails = 0
    print()
    for i, track in enumerate(tracks, 1):
        label = truncate(track["artist"] + " - " + track["title"])
        print("\r  " + progress_bar(i-1, total) + "  " + c(label, C.DIM) + "          ",
              end="", flush=True)
        if not download_track(track["query"], out_dir, i):
            fails += 1
    print("\r  " + progress_bar(total, total) + "                              ", flush=True)
    print()
    if fails:
        print(c("  ~ " + str(fails) + " faixa(s) nao encontradas no YouTube", C.YELLOW))
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
    print(c("  Pasta interna: " + zip_name + "/", C.DIM))
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

    parser = argparse.ArgumentParser(
        prog="spotidown",
        description="Baixa playlists/albuns do Spotify via YouTube. Sem Premium, sem API key.",
    )
    parser.add_argument("url",   help="Link do Spotify OU busca por texto (ex: \"metallica ride the lightning\")")
    parser.add_argument("pasta", nargs="?", default="~/Music",
                        help="Pasta de destino (padrao: ~/Music)")
    parser.add_argument("--nome", "-n", default=None,
                        help="Sobrescreve o nome automatico do ZIP")

    args     = parser.parse_args()
    query    = args.url.strip()
    dest_dir = Path(args.pasta).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    print_section("Verificando dependencias...")
    if not check_dependencies():
        sys.exit(1)

    # Detecta se e link ou busca por texto
    is_link = "spotify.com" in query or query.startswith("http")
    if is_link:
        meta = fetch_metadata(query)
    else:
        meta = search_and_resolve(query)
    if not meta or not meta.get("tracks"):
        print(c("\n  ERRO: Nao foi possivel obter as faixas.", C.RED))
        print(c("    Verifique se o link e publico no Spotify.", C.DIM))
        sys.exit(1)

    tracks = meta["tracks"]
    if args.nome:
        zip_name = safe_filename(args.nome)
    elif meta.get("name") and meta.get("artist"):
        zip_name = safe_filename(meta["name"] + " - " + meta["artist"])
    else:
        zip_name = safe_filename(meta.get("name", "download"))

    print(c("\n  Destino: " + str(dest_dir), C.DIM))
    print(c("  ZIP    : " + zip_name + ".zip", C.DIM))
    print(c("  Faixas : " + str(len(tracks)), C.DIM))

    print_section("Baixando musicas via YouTube...")
    tmp_dir = Path(tempfile.mkdtemp(prefix="spotidown_"))
    try:
        files = download_all(tracks, tmp_dir)
        if not files:
            print(c("  ERRO: Nenhuma musica baixada.", C.RED))
            sys.exit(1)
        print(c("  OK " + str(len(files)) + " musica(s) baixada(s)", C.GREEN))

        zip_path = build_zip(files, dest_dir, zip_name)
        size_mb  = zip_path.stat().st_size / (1024 * 1024)
        print(c("\n  Concluido!", C.GREEN, C.BOLD))
        print(c("  Arquivo: " + str(zip_path), C.CYAN))
        print(c("  Tamanho: " + f"{size_mb:.1f}" + " MB  (" + str(len(files)) + " musica(s))", C.DIM))
        print()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
