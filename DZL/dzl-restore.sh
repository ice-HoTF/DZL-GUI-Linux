#!/bin/bash
set -u

VERSION="1.0.0"
DEST="${2:-$PWD/DZL-Rebuilt}"
SRC="${1:-}"
TMP=""

cleanup() {
    if [ -n "$TMP" ]; then
        rm -rf "$TMP"
    fi
}
trap cleanup EXIT

echo "DZL project restore"
echo "Usage: $0 [package.pkg.tar.zst | extracted-folder] [target-folder]"
echo

if [ -z "$SRC" ]; then
    HERE="$(dirname "$(readlink -f "$0")")"
    GUESS="$(readlink -f "$HERE/../../../..")"
    PKG="$(ls -1 "$PWD"/dzl-*-any.pkg.tar.zst "$HERE"/dzl-*-any.pkg.tar.zst 2>/dev/null | head -n 1)"
    if [ -d "$GUESS/usr/lib/dzl/dzl" ] && [ -d "$GUESS/usr/share/dzl/build" ]; then
        ROOT="$GUESS"
        echo "Using the package files around this script: $ROOT"
    elif [ -n "$PKG" ]; then
        SRC="$PKG"
    else
        echo "ERROR: no package found. Pass the .pkg.tar.zst file or the extracted folder."
        exit 1
    fi
fi

if [ -n "$SRC" ]; then
    if [ -f "$SRC" ]; then
        TMP="$(mktemp -d)"
        echo "Extracting $SRC"
        if ! tar --zstd -xf "$SRC" -C "$TMP"; then
            echo "ERROR: could not extract the package. Is zstd installed?"
            exit 1
        fi
        ROOT="$TMP"
    elif [ -d "$SRC" ]; then
        ROOT="$(readlink -f "$SRC")"
    else
        echo "ERROR: $SRC is not a file or folder."
        exit 1
    fi
fi

SRC_CODE="$ROOT/usr/lib/dzl/dzl"
SRC_BUILD="$ROOT/usr/share/dzl/build"

if [ ! -d "$SRC_CODE" ] || [ ! -d "$SRC_BUILD" ]; then
    echo "ERROR: the package does not contain usr/lib/dzl/dzl and usr/share/dzl/build."
    exit 1
fi

if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    echo "ERROR: $DEST already exists and is not empty. Choose another folder."
    exit 1
fi

echo "Restoring the project to $DEST"
mkdir -p "$DEST" || exit 1
cp -r "$SRC_CODE" "$DEST/dzl" || exit 1
cp "$SRC_BUILD"/* "$DEST/" || exit 1

echo "Removing leftover junk from the source folder"
rm -rf "$DEST/dzl/dzl-$VERSION" "$DEST/dzl/dzl-$VERSION.tar.gz" "$DEST/dzl/dzl.png"
find "$DEST/dzl" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

cd "$DEST" || exit 1

echo "Creating the source tarball"
rm -rf "dzl-$VERSION" "dzl-$VERSION.tar.gz"
mkdir -p "dzl-$VERSION"
cp -r dzl/ "dzl-$VERSION/"
cp PKGBUILD README.md LICENSE dzl-deck-install.sh dzl-restore.sh dzl-build.sh Build_Install.txt "dzl-$VERSION/" || exit 1
tar czf "dzl-$VERSION.tar.gz" "dzl-$VERSION/" || exit 1

echo
echo "Project restored in: $DEST"
ls
echo

if command -v makepkg >/dev/null 2>&1; then
    read -r -p "Build the package now with makepkg -f? [y/N] " ANSWER
    if [ "$ANSWER" = "y" ] || [ "$ANSWER" = "Y" ]; then
        makepkg -f
        echo
        echo "Install with: sudo pacman -U dzl-$VERSION-1-any.pkg.tar.zst"
    else
        echo "Build later with: cd \"$DEST\" && makepkg -f"
    fi
else
    echo "makepkg not found. Build on an Arch system with: makepkg -f"
fi
