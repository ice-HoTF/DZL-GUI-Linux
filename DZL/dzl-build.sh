#!/bin/bash
set -u

VERSION="1.0.0"
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE" || exit 1

TARBALL_FILES="PKGBUILD README.md LICENSE dzl-deck-install.sh dzl-restore.sh dzl-build.sh Build_Install.txt"
SOURCE_FILES="dzl.desktop dzl.png README_Build.txt"

echo "DZL build"
echo "Project folder: $HERE"
echo

if [ ! -f dzl/main.py ] || [ ! -f PKGBUILD ]; then
    echo "ERROR: run this script from the project folder that holds PKGBUILD and the dzl/ folder."
    exit 1
fi

MISSING=0
for f in $TARBALL_FILES $SOURCE_FILES; do
    if [ ! -f "$f" ]; then
        echo "ERROR: missing file: $f"
        MISSING=1
    fi
done
if [ "$MISSING" -eq 1 ]; then
    exit 1
fi

echo "Checking the Python source"
if ! python3 -m py_compile dzl/*.py; then
    echo "ERROR: the source has a syntax error. Fix it and run this again."
    exit 1
fi

echo "Cleaning leftovers"
rm -rf "dzl/dzl-$VERSION" "dzl/dzl-$VERSION.tar.gz" dzl/dzl.png
find dzl -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
rm -rf pkg src "dzl-$VERSION" "dzl-$VERSION.tar.gz"

echo "Creating the source tarball"
mkdir -p "dzl-$VERSION" || exit 1
cp -r dzl/ "dzl-$VERSION/" || exit 1
cp $TARBALL_FILES "dzl-$VERSION/" || exit 1
tar czf "dzl-$VERSION.tar.gz" "dzl-$VERSION/" || exit 1
rm -rf "dzl-$VERSION"

if ! command -v makepkg >/dev/null 2>&1; then
    echo
    echo "makepkg not found. The tarball is ready. Build on an Arch system with: makepkg -f"
    exit 0
fi

echo "Building the package"
if ! makepkg -f; then
    echo
    echo "ERROR: makepkg failed. Copy the error text above and send it back."
    exit 1
fi

rm -rf pkg src

echo
echo "Done. Install with: sudo pacman -U dzl-$VERSION-1-any.pkg.tar.zst"
