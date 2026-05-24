#!/usr/bin/env python3
"""
uninstall.py — Desinstalador do SpotiDown.
Funciona em Windows, Linux e macOS.

Uso:
    python uninstall.py       (Windows)
    python3 uninstall.py      (Linux / macOS)
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

IS_WIN = sys.platform == "win32"


class C:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def c(text, *codes):
    return "".join(codes) + str(text) + C.RESET


def ok(msg):
    print(c(f"  OK {msg}", C.GREEN))


def info(msg):
    print(c(f"  ~ {msg}", C.YELLOW))


def err(msg):
    print(c(f"  ERRO {msg}", C.RED))


def run(*args, timeout=60):
    try:
        r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout + r.stderr
    except Exception as e:
        return False, str(e)


def uninstall_pipx():
    print(c("\n  Removendo pacote pipx...", C.BOLD))
    pipx_candidates = [
        shutil.which("pipx"),
    ]
    if sys.executable:
        pipx_candidates.append(sys.executable)

    for pipx_cmd_base in pipx_candidates:
        if not pipx_cmd_base:
            continue
        pipx_cmd = [pipx_cmd_base, "-m", "pipx"] if pipx_cmd_base == sys.executable else [pipx_cmd_base]
        s, out = run(*pipx_cmd, "list")
        if s and "spotidown" in out:
            s2, _ = run(*pipx_cmd, "uninstall", "spotidown")
            if s2:
                ok("spotidown removido do pipx")
                return
            err(f"falha ao remover: {out[:200]}")
            return
    info("spotidown nao encontrado no pipx (ja removido)")


def remove_spotidown_dir():
    spotidown_dir = Path.home() / ".spotidown"
    if spotidown_dir.exists():
        shutil.rmtree(spotidown_dir, ignore_errors=True)
        ok(f"pasta {spotidown_dir} removida")
    else:
        info("pasta .spotidown nao encontrada")


def remove_path_entries():
    if not IS_WIN:
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            cur, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            cur = ""

        entries_to_remove = [
            str(Path.home() / ".spotidown" / "ffmpeg"),
        ]

        new_parts = []
        changed = False
        for part in cur.split(";"):
            if part and part not in entries_to_remove:
                new_parts.append(part)
            elif part:
                changed = True

        if changed:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(new_parts))
            ok("entradas do PATH no registro removidas")
        else:
            info("nenhuma entrada do spotidown no PATH do registro")

        winreg.CloseKey(key)
    except Exception as e:
        info(f"nao foi possivel limpar PATH do registro: {e}")


def main():
    print(c(f"\n  ♫ SpotiDown — Desinstalador", C.GREEN, C.BOLD))
    print(c(f"  {platform.system()} {platform.release()}", C.DIM))
    print(c("  " + "-" * 40, C.DIM))

    print()
    answer = input(c("  Deseja remover o SpotiDown? (s/N): ", C.YELLOW)).strip().lower()
    if answer != "s":
        print(c("  Cancelado.", C.RED))
        sys.exit(0)

    uninstall_pipx()
    remove_spotidown_dir()
    remove_path_entries()

    print()
    print(c("  " + "-" * 40, C.DIM))
    print(c("  Desinstalacao concluida!", C.GREEN, C.BOLD))
    if IS_WIN:
        print(c("  Feche e reabra o PowerShell para atualizar o PATH.", C.YELLOW))
    print()


if __name__ == "__main__":
    main()
