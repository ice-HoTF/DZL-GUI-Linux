import base64
import os
import shutil
import subprocess
from pathlib import Path

DAYZ_APPID = "221100"

def find_steamapps() -> Path:
    home = Path.home()
    for p in (
        home / ".steam/debian-installation/steamapps",
        home / ".steam/steam/steamapps",
    ):
        if p.is_dir():
            return p
    raise RuntimeError(
        "Steam folder not found in ~/.steam"
    )

def steam_binary() -> str:
    exe = shutil.which("steam")
    if not exe:
        raise RuntimeError("steam binary not found in PATH")
    return exe

def encode_mod_id(workshop_id: str) -> str:
    """Decimal id -> little-endian minimal bytes -> base64url without padding."""
    n = int(workshop_id)
    buf = bytearray()
    while True:
        buf.append(n & 0xFF)
        n >>= 8
        if n == 0:
            break
    b64 = base64.b64encode(bytes(buf)).decode()
    return b64.replace("/", "-").replace("+", "_").rstrip("=")

def mod_link_name(workshop_id: str) -> str:
    return "@" + encode_mod_id(workshop_id)

def download_mod(workshop_id: str, steamapps: Path):
    """Run the exact Bash-script invocation. Blocking; call from a thread."""
    exe = steam_binary()
    cmd = [exe, f"steam+workshop_download_item {DAYZ_APPID} {workshop_id}"]
    subprocess.run(cmd, check=False)

def acf_path(steamapps: Path) -> Path:
    return steamapps / f"workshop/appworkshop_{DAYZ_APPID}.acf"

def acf_needs_download(acf: Path) -> bool:
    if not acf.is_file():
        return True
    try:
        text = acf.read_text(errors="replace")
    except OSError:
        return True
    import re
    return bool(re.search(r'"NeedsDownload"\s+"1"', text))

def launch_dayz(steamapps: Path, mod_folders, ip_port: str,
                query_port: str, name: str):
    exe = steam_binary()
    mods = ";".join(mod_folders)
    cmd = [
        exe, "-applaunch", DAYZ_APPID,
        f"-mod={mods}",
        f"-connect={ip_port}",
        "--port", str(query_port),
        f"-name={name}",
        "-nolauncher",
        "-world=empty",
    ]
    subprocess.Popen(cmd)

def prepare_join(steamapps: Path, game_dir: Path):
    """Mirror the Bash cleanup: remove acf files, downloads, @* symlinks."""
    for acf in (
        steamapps / "workshop" / f"appworkshop_{DAYZ_APPID}.acf",
        steamapps / "workshop" / "appworkshop_241100.acf",
    ):
        if acf.is_file():
            acf.unlink()
    dl = steamapps / "workshop" / "downloads"
    if dl.is_dir():
        for child in dl.iterdir():
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

def link_mod(game_dir: Path, mods_dir: Path, workshop_id: str):
    src = mods_dir / workshop_id
    dst = game_dir / mod_link_name(workshop_id)
    if dst.is_symlink() or dst.exists():
        try:
            dst.unlink()
        except OSError:
            shutil.rmtree(dst, ignore_errors=True)
    if src.is_dir():
        rel = os.path.relpath(src.resolve(), game_dir.resolve())
        dst.symlink_to(rel, target_is_directory=True)
