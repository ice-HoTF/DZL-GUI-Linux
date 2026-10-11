import json, socket, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LAUNCHER_URL = "https://dayzsalauncher.com/api/v1/launcher/servers/dayz"
QUERY_URL    = "https://dayzsalauncher.com/api/v1/query/{ip}/{port}"
STEAM_DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

def _ua() -> str:
    return "dzl/1.0"

def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _ua()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def fetch_server_list(cache: Path, cache_ttl: int = 600):
    """Return parsed .result list, using a 10-minute on-disk cache."""
    if cache.is_file() and (time.time() - cache.stat().st_mtime) < cache_ttl:
        try:
            data = json.loads(cache.read_text())
            if isinstance(data.get("result"), list):
                return data["result"]
        except Exception:
            pass
    try:
        raw = _get(LAUNCHER_URL, timeout=60)
        data = json.loads(raw)
        if not isinstance(data.get("result"), list):
            raise ValueError("bad schema")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
        return data["result"]
    except Exception:
        if cache.is_file():
            try:
                data = json.loads(cache.read_text())
                if isinstance(data.get("result"), list):
                    return data["result"]
            except Exception:
                pass
        raise

def search_servers(servers, query: str):
    words = [w for w in query.lower().split() if w]
    def clean(s):
        return "".join(ch for ch in s if ch.isprintable())
    out = []
    for s in servers:
        name = clean(s.get("name") or "")
        if all(w in name.lower() for w in words):
            out.append({
                "name": name,
                "players": s.get("players", 0),
                "max_players": s.get("maxPlayers", 0),
                "password": bool(s.get("password")),
                "ip": (s.get("endpoint") or {}).get("ip", ""),
                "game_port": s.get("gamePort", 2302),
                "query_port": (s.get("endpoint") or {}).get("port", 27016),
            })
    out.sort(key=lambda x: x["players"], reverse=True)
    return out[:100]

def fetch_server_mods(ip: str, query_port: int):
    """Returns (mod_ids, vanilla). Raises RuntimeError on API failure."""
    raw = _get(QUERY_URL.format(ip=ip, port=query_port), timeout=10)
    data = json.loads(raw)
    mods = (data.get("result") or {}).get("mods")
    if mods is None:
        raise RuntimeError(
            "Missing data from API response. Try again in a few seconds"
        )
    if not isinstance(mods, list):
        raise RuntimeError(
            "Missing data from API response. Try again in a few seconds"
        )
    if len(mods) == 0:
        return [], True
    ids = [str(m["steamWorkshopId"]) for m in mods if "steamWorkshopId" in m]
    ids = [i for i in ids if i.isascii() and i.isdigit()]
    return ids, False

def fetch_server_mods_detailed(ip: str, query_port: int):
    raw = _get(QUERY_URL.format(ip=ip, port=query_port), timeout=10)
    data = json.loads(raw)
    mods = (data.get("result") or {}).get("mods")
    if not isinstance(mods, list):
        raise RuntimeError(
            "Missing data from API response. Try again in a few seconds"
        )
    out = []
    for m in mods:
        wid = str(m.get("steamWorkshopId", ""))
        if wid.isascii() and wid.isdigit():
            out.append({"id": wid, "name": str(m.get("name") or "")})
    return out

A2S_INFO = b"\xFF\xFF\xFF\xFFTSource Engine Query\x00"

def _ping_one(ip: str, port, timeout: float):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        t0 = time.perf_counter()
        s.sendto(A2S_INFO, (ip, int(port)))
        s.recv(1400)
        return int((time.perf_counter() - t0) * 1000)
    except Exception:
        return None
    finally:
        s.close()

def ping_servers(targets, timeout: float = 1.5, workers: int = 20):
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [
            ((ip, str(port)), ex.submit(_ping_one, ip, port, timeout))
            for ip, port in targets
        ]
        for key, f in futs:
            out[key] = f.result()
    return out

def check_updates(ids, mods_dir: Path):
    """Return list of outdated ids. Raises RuntimeError on network/JSON failure."""
    outdated = []
    ids = [str(i) for i in ids]
    for i in range(0, len(ids), 100):
        chunk = ids[i:i+100]
        body = urllib.parse.urlencode(
            [("itemcount", len(chunk))] +
            [(f"publishedfileids[{j}]", v) for j, v in enumerate(chunk)]
        ).encode()
        req = urllib.request.Request(
            STEAM_DETAILS_URL, data=body,
            headers={"User-Agent": _ua()},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        details = (data.get("response") or {}).get("publishedfiledetails")
        if details is None:
            raise RuntimeError("Update check failed")
        for d in details:
            if d.get("result") != 1:
                continue
            wid = str(d["publishedfileid"])
            tu = int(d.get("time_updated", 0))
            folder = mods_dir / wid
            newest = 0.0
            if folder.is_dir():
                for p in folder.rglob("*"):
                    if p.is_file():
                        try:
                            newest = max(newest, p.stat().st_mtime)
                        except OSError:
                            pass
            if newest <= tu:
                outdated.append(wid)
    return outdated

def fetch_workshop_info(item_id: str):
    """Return dict with time_updated/time_created/subscriptions or None."""
    body = urllib.parse.urlencode(
        [("itemcount", 1), ("publishedfileids[0]", str(item_id))]
    ).encode()
    req = urllib.request.Request(
        STEAM_DETAILS_URL, data=body,
        headers={"User-Agent": _ua()}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        d = (data.get("response") or {}).get("publishedfiledetails", [{}])[0]
        if d.get("result") != 1:
            return None
        return {
            "time_updated": int(d.get("time_updated", 0)),
            "time_created": int(d.get("time_created", 0)),
            "subscriptions": d.get("subscriptions", 0),
        }
    except Exception:
        return None
