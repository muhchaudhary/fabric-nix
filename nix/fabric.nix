{
  lib,
  fetchFromGitHub,
  buildPythonPackage,
  gtk3,
  glib,
  gtk-layer-shell,
  gobject-introspection,
  python3Packages,
  libdbusmenu-gtk3,
  pkg-config,
  wrapGAppsHook,
  gdk-pixbuf,
  librsvg,
}:
buildPythonPackage rec {
  pname = "fabric";
  version = "0.0.1";
  src = fetchFromGitHub {
    owner = "Fabric-Development";
    repo = "fabric";
    rev = "0babdf6e498995305652dc73d96c614138395b31";
    sha256 = "sha256-u02VLZiQBqwcaIRjzf/4x8wER/fnB+P7vcW8HjjCALg=";
  };
  format = "setuptools";

  # unit tests will fail with hyprland module
  doCheck = false;

  nativeBuildInputs = [
    gobject-introspection
    python3Packages.setuptools
  ];

  propagatedBuildInputs = [
    glib
    libdbusmenu-gtk3
    gtk3
    gtk-layer-shell
    gdk-pixbuf
    librsvg

    # defined in requirements.txt
    python3Packages.click
    python3Packages.loguru
    python3Packages.pycairo
    python3Packages.pygobject3
    python3Packages.pygobject-stubs
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    # To be changed later
    license = with licenses; [lgpl21Only mpl11];
    platforms = lib.platforms.linux;
  };
}
