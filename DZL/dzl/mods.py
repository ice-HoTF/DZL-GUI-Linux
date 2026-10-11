import re
import shutil
from pathlib import Path

_NAME_RE = re.compile(r'^\s*name\s*=\s*"(.*)";')
_AUTHOR_RE = re.compile(r'^\s*author\s*=\s*"(.*)";')

def read_mod_name(mod_dir: Path) -> str:
    meta = mod_dir / "meta.cpp"
    if meta.is_file():
        try:
            for line in meta.read_text(errors="replace").splitlines():
                m = _NAME_RE.match(line.rstrip("\r"))
                if m:
                    return m.group(1)
        except OSError:
            pass
    return mod_dir.name

def read_mod_author(mod_dir: Path) -> str:
    cpp = mod_dir / "mod.cpp"
    if cpp.is_file():
        try:
            for line in cpp.read_text(errors="replace").splitlines():
                m = _AUTHOR_RE.match(line.rstrip("\r"))
                if m:
                    return m.group(1)
        except OSError:
            pass
    return ""

def list_mods(mods_dir: Path):
    if not mods_dir.is_dir():
        return []
    out = []
    for child in mods_dir.iterdir():
        if child.is_dir() and child.name.isdigit():
            out.append({
                "id": child.name,
                "name": read_mod_name(child),
                "path": child,
            })
    out.sort(key=lambda x: x["name"].casefold())
    return out

def newest_mtime(mod_dir: Path) -> float:
    newest = 0.0
    try:
        for p in mod_dir.rglob("*"):
            if p.is_file():
                newest = max(newest, p.stat().st_mtime)
    except OSError:
        pass
    return newest

def dir_size(mod_dir: Path) -> int:
    total = 0
    try:
        for p in mod_dir.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    except OSError:
        pass
    return total

def human_size(n: int) -> str:
    units = ["B", "K", "M", "G"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.0f}{u}" if u == "B" else f"{f:.1f}{u}"
        f /= 1024
    return f"{n}B"

def delete_all_mods(mods_dir: Path, downloads_dir: Path, game_dir: Path):
    if mods_dir.is_dir():
        for child in mods_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    if downloads_dir.is_dir():
        for child in downloads_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    if game_dir.is_dir():
        for link in game_dir.glob("@*"):
            try:
                if link.is_symlink() or link.is_file():
                    link.unlink()
                elif link.is_dir():
                    shutil.rmtree(link, ignore_errors=True)
            except OSError:
                pass