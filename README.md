# ♫ SpotiDown

Baixa músicas, álbuns e playlists do Spotify em MP3 320kbps e salva em ZIP.
Sem conta Premium. Sem API key. Funciona em Windows, Linux e macOS.

---

## Instalação (uma vez só)

### Pré-requisito: Python 3.10+

- **Windows** → https://python.org/downloads  
  ⚠ Marque **"Add Python to PATH"** na instalação!
- **Linux** → já vem instalado. Se não: `sudo apt install python3`
- **macOS** → já vem instalado. Se não: `brew install python`

---

### Instalar o SpotiDown

**Windows** (PowerShell):
```
python instalar.py
ou
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/neroios/spotidown/main/instalar.py" -OutFile "instalar.py"; python instalar.py
```

**Linux / macOS** (Terminal):
```
python3 instalar.py
ou
curl -O https://raw.githubusercontent.com/neroios/spotidown/main/instalar.py && python3 instalar.py
```

O instalador cuida de tudo:
- instala pipx
- instala ffmpeg
- instala o spotidown
- configura o PATH

Feche e reabra o terminal depois. Pronto.

---

## Como usar

```
spotidown "nome da música ou álbum"
spotidown "angra fireworks"
spotidown "metallica ride the lightning"
spotidown "https://open.spotify.com/album/xxx"
```

Salvando em pasta específica:
```
spotidown "judas priest painkiller" ~/Musicas
spotidown "judas priest painkiller" C:\Users\Voce\Music
```

---

## Resultado

O programa cria um ZIP com pasta interna nomeada automaticamente:

```
Painkiller - Judas Priest.zip
└── Painkiller - Judas Priest/
    ├── 001 - Judas Priest - Painkiller.mp3
    ├── 002 - Judas Priest - Hell Patrol.mp3
    └── ...
```

---

## Atualizar

```
spotidown --update
```

Ou rode o `instalar.py` novamente.

