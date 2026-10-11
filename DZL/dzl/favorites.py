import json
import re
from pathlib import Path

_SANITIZE_RE = re.compile(r'[^A-Za-z0-9_.-]')

def sanitize_name(name: str) -> str:
    return _SANITIZE_RE.sub("_", name)

class Favorites:
    def __init__(self, path: Path):
        self.path = path
        self._data = []
        self.load()

    def load(self):
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text())
            except Exception:
                self._data = []
        else:
            self._data = []

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def all(self):
        return list(self._data)

    def find(self, ip_port: str) -> int:
        for i, f in enumerate(self._data):
            if f.get("ip_port") == ip_port:
                return i
        return -1

    def add(self, name: str, mod_folders, ip_port: str,
            query_port: str, username: str):
        entry = {
            "name": name,
            "mod_folders": list(mod_folders),
            "ip_port": ip_port,
            "query_port": str(query_port),
            "username": username,
        }
        self._data.append(entry)
        self.save()
        return entry

    def rename(self, index: int, new_name: str):
        if 0 <= index < len(self._data):
            self._data[index]["name"] = new_name
            self.save()

    def update(self, index: int, ip_port: str, query_port: str):
        if 0 <= index < len(self._data):
            self._data[index]["ip_port"] = ip_port
            self._data[index]["query_port"] = str(query_port)
            self.save()

    def delete(self, index: int):
        if 0 <= index < len(self._data):
            del self._data[index]
            self.save()

    def get(self, index: int):
        if 0 <= index < len(self._data):
            return self._data[index]
        return None
