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
  libdbusmenu-gtk3,
  click,
  pkg-config,
  wrapGAppsHook,
  gdk-pixbuf,
  librsvg,
  src,
}:
buildPythonPackage rec {
  pname = "fabric";
  version = "0.0.1";
  src = fetchFromGitHub {
    owner = "Fabric-Development";
    repo = "fabric";
    rev = "9adb28d7659d9068ff05f1410767334608fa4095";
    sha256 = "sha256-U9lA+nht23tXoSredZEnXOzW/lTH0rr29nQF5zP9eEo=";
  };
  format = "setuptools";

  # unit tests will fail with hyprland module
  doCheck = false;

  nativeBuildInputs = [
    gobject-introspection
  ];

  propagatedBuildInputs = [
    librsvg
    glib
    cairo
    libdbusmenu-gtk3
    gtk-layer-shell
    gtk3
    setuptools # added for pyproject
    pygobject3
    pycairo
    loguru
    gdk-pixbuf
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
