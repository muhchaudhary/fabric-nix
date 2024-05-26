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
  webkitgtk_4_1,
}:
buildPythonPackage rec {
  pname = "fabric";
  version = "0.0.1";

  src = fetchFromGitHub {
    owner = "Fabric-Development";
    repo = "fabric";
    rev = "667ca7591856b03f3abef847c4e716dadb5e12e2";
    sha256 = "sha256-Cj/+OXx0fkx+fO2KKU2Y3ET7wiO7s57bpLlzFW7EnXs=";
  };

  # unit tests will fail with hyprland module
  doCheck = false;

  nativeBuildInputs = [
    gobject-introspection
  ];

  propagatedBuildInputs = [
    glib
    libdbusmenu-gtk3
    gtk3
    gtk-layer-shell
    gdk-pixbuf
    librsvg
    webkitgtk_4_1

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
