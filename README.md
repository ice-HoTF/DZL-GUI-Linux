# DZL - DayZ Mod Launcher

A native desktop launcher for DayZ on Linux. Search for a server, download the mods it needs through Steam, and join with one click. It is a Python and PySide6 (Qt6) port of the Bash script `DZL.sh`.

## Features

- **Server search:** find servers by name. All words you type must match. Results show players, password flag, IP and game port, query port and ping.
- **Favorites:** click the star on any server to save it. The Favorites page works like the Servers page.
- **One-click join:** DZL reads the server's mod list, checks for updates, downloads missing mods, links them and launches DayZ.
- **Mod Settings:** per server, choose Server Info (details and required mods), Verify Mods or Remove Mods Used By This Server.
- **Mods page:** lists installed mods with size, last updated and Workshop ID. Update, delete, view info, check all for updates, or delete all.
- **Ping:** measured with a single UDP query to each server's query port.
- **Appearance:** change colors and bold text under Settings. Everything defaults to your system theme.
- **Manual Setup:** join any server by IP, game port and query port.

## Requirements

- Arch Linux or an Arch-based distribution
- The official Steam package. Flatpak Steam is not supported.
- `python` and `pyside6`
- DayZ installed through Steam, with Steam running on the same user account

## Install

Build and install the package from the project folder:

```
mkdir -p dzl-1.0.0
cp -r dzl/ dzl-1.0.0/
tar czf dzl-1.0.0.tar.gz dzl-1.0.0/
makepkg -f
sudo pacman -U dzl-1.0.0-1-any.pkg.tar.zst
```

Start it from the application menu (Games) or run:

```
dzl
```

Run it straight from the source tree without installing:

```
python3 -m dzl
```

Remove it:

```
sudo pacman -R dzl
```

Your settings stay in `~/.config/dzl/` and `~/.cache/dzl/` after removal.

## Steam Deck

SteamOS locks its system partition, so `pacman -U` needs `sudo steamos-readonly disable` first, and a SteamOS update will probably remove the install. Use Desktop Mode. The script `dzl-deck-install.sh` automates these steps. Steam Deck support is untested.

## When DZL makes network requests

DZL never polls in the background. Requests happen only when you act:

- **On launch, Search and Refresh:** downloads the server list from dayzsalauncher.com and pings the listed servers.
- **Join, Server Info, Verify Mods, Remove Mods:** asks dayzsalauncher.com for that server's mod list.
- **Join, Update and Check All For Updates:** asks the Steam Web API for mod update times.
- **Mod Info:** asks the Steam Web API for one mod.

## Where data is stored

| Path | Contents |
|---|---|
| `~/.config/dzl/username.conf` | Your username |
| `~/.config/dzl/favorites.json` | Favorite servers |
| `~/.config/dzl/colors.json` | Appearance settings |
| `~/.cache/dzl/servers_cache.json` | Last downloaded server list |

Mods are stored in Steam's own workshop folder for DayZ.

## Known limitations

- Steam must be found at `~/.steam/steam` or `~/.steam/debian-installation`.
- Mod download progress comes from Steam's workshop state file, not a live progress bar.
- Servers that ignore UDP queries show `-` as their ping.

## Credits and disclaimer

Server data comes from the DayZ SA Launcher API, and mod data from the Steam Web API. This project is not affiliated with Bohemia Interactive, Valve, or DayZ SA Launcher. DayZ and Steam are trademarks of their respective owners.

## License

MIT. See the `LICENSE` file. Copyright (c) 2026 Jonas Braastad.
