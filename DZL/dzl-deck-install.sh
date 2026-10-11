#!/bin/bash
set -u

DIR="$(dirname "$(readlink -f "$0")")"
PKG="$(ls -1 "$DIR"/dzl-*-any.pkg.tar.zst 2>/dev/null | tail -n 1)"

if [ -z "$PKG" ]; then
    echo "ERROR: no dzl-*-any.pkg.tar.zst found next to this script."
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: run this as your normal user, not root. It uses sudo itself."
    exit 1
fi

echo "Package: $PKG"
echo "This unlocks the system partition, installs DZL, then locks it again."
echo "A SteamOS update will probably remove the install. Run this again then."
echo

sudo -v || { echo "ERROR: sudo failed. Set a password first with: passwd"; exit 1; }

relock() {
    echo "Locking the system partition again"
    sudo steamos-readonly enable
}

echo "Unlocking the system partition"
sudo steamos-readonly disable || { echo "ERROR: could not unlock."; exit 1; }
trap relock EXIT

echo "Setting up pacman keys"
sudo pacman-key --init
sudo pacman-key --populate archlinux
sudo pacman-key --populate holo

echo "Installing DZL"
if ! sudo pacman -U "$PKG"; then
    echo
    echo "First attempt failed. Refreshing package databases and retrying once."
    sudo pacman -Sy
    if ! sudo pacman -U "$PKG"; then
        echo
        echo "ERROR: install failed. Copy the error text above and send it back."
        exit 1
    fi
fi

echo
echo "Done. Start DZL from the application menu (Games) or run: dzl"
