{
  lib,
  fetchFromGitHub,
  buildPythonPackage,
  cairo,
  gtk3,
  glib,
  gtk-layer-shell,
  gobject-introspection,
  loguru,
  setuptools,
  pycairo,
  pygobject3,
  pygobject-stubs,
  libdbusmenu-gtk3,
  click,
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
    rev = "cb3336ee1686c45f1530269dd9606cf31902825f";
    sha256 = "sha256-VvZX6ncqS8AU3Ku6lnD0jTqTwLaFVxdc90Nay+gabhg=";
  };
  format = "setuptools";

  # unit tests will fail with hyprland module
  doCheck = false;

  nativeBuildInputs = [
    wrapGAppsHook
    gobject-introspection
    pkg-config
  ];

  propagatedBuildInputs = [
    glib
    cairo
    libdbusmenu-gtk3
    gtk-layer-shell
    gtk3
    setuptools # added for pyproject
    pygobject3
    pygobject-stubs
    pycairo
    loguru
    gdk-pixbuf
    librsvg
    click
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    # To be changed later
    license = with licenses; [lgpl21Only mpl11];
    platforms = lib.platforms.linux;
  };
}
