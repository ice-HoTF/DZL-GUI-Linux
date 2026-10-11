DZL - BUILD NOTES
=================

The build files are shipped inside the package, so the whole project can be
restored from dzl-1.0.0-1-any.pkg.tar.zst on another PC.
They are installed to /usr/share/dzl/build/ on the target system.


1. RESTORE THE PROJECT FROM THE PACKAGE (script)
------------------------------------------------
Where: any folder. The package file or the installed package is the source.
What: rebuilds the project folder, removes leftover junk files, creates the
source tarball, and offers to run makepkg.

From the package file:

    bash dzl-restore.sh dzl-1.0.0-1-any.pkg.tar.zst ./DZL-Rebuilt

From an already extracted package folder (the one that contains usr/):

    bash dzl-restore.sh /path/to/extracted-folder ./DZL-Rebuilt

From the installed package (no arguments):

    bash /usr/share/dzl/build/dzl-restore.sh

The target folder must not exist or must be empty. The default is
./DZL-Rebuilt. The script needs zstd to read a .pkg.tar.zst file.


2. RESTORE BY HAND (same steps as the script)
---------------------------------------------
    mkdir -p ./DZL-Rebuilt
    cp -r usr/lib/dzl/dzl ./DZL-Rebuilt/dzl
    cp usr/share/dzl/build/* ./DZL-Rebuilt/
    cd ./DZL-Rebuilt
    rm -rf dzl/dzl-1.0.0 dzl/dzl-1.0.0.tar.gz dzl/dzl.png


3. TARBALL STEP
---------------
Where: project folder, before makepkg. Also in Build_Install.txt.
Why: PKGBUILD copies the build files out of the tarball, so they must be
inside it or the build fails.

    rm -rf dzl-1.0.0 dzl-1.0.0.tar.gz
    mkdir -p dzl-1.0.0
    cp -r dzl/ dzl-1.0.0/
    cp PKGBUILD README.md LICENSE dzl-deck-install.sh dzl-restore.sh dzl-build.sh Build_Install.txt dzl-1.0.0/
    tar czf dzl-1.0.0.tar.gz dzl-1.0.0/


4. PKGBUILD
-----------
The loop in package() that installs the build files must list the same
files as the tarball step above:

    for f in PKGBUILD README.md LICENSE dzl-deck-install.sh dzl-restore.sh dzl-build.sh Build_Install.txt; do
      install -Dm644 "$srcdir/dzl-1.0.0/$f" "$pkgdir/usr/share/dzl/build/$f"
    done

These are separate source files next to PKGBUILD, listed in source=() and
installed one by one at the end of package():

    dzl.desktop
    dzl.png
    README_Build.txt

Files installed with install -Dm644 lose the executable bit. Run the scripts
with bash, for example: bash dzl-restore.sh


5. BUILD
--------
    makepkg -f
    sudo pacman -U dzl-1.0.0-1-any.pkg.tar.zst


6. BUILD WITH ONE SCRIPT
------------------------
Where: the project folder that holds PKGBUILD and the dzl/ folder.
What: dzl-build.sh checks the source, removes leftover junk, creates the
source tarball and runs makepkg -f. It stops if a needed file is missing.

    bash dzl-build.sh
