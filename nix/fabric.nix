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
    rev = "55276ab6e8ebfe2d4377e2e4d3b4234d657c5cb8";
    sha256 = "sha256-xPTwIvQzoapMXMZlZn4JTsJgp50SHWsnt/e4KsQiEjQ=";
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
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    # To be changed later
    license = with licenses; [lgpl21Only mpl11];
    platforms = lib.platforms.linux;
  };
}
