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
}:
buildPythonPackage rec {
  pname = "fabric";
  version = "0.0.1";
  src = fetchFromGitHub {
    owner = "Fabric-Development";
    repo = "fabric";
    rev = "0ff0248d131e1212ecab1f853eae8ac47acfb76d";
    sha256 = "sha256-bUZcHfff67yyPlP67uF9Kixnw9pZ7E7kfO839+LRiuI=";
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
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    # To be changed later
    license = with licenses; [lgpl21Only mpl11];
    platforms = lib.platforms.linux;
  };
}
