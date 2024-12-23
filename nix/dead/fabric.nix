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
    rev = "d672fa1bac48dc40bbb00e11c2f99d6410316549";
    sha256 = "sha256-sLGJTl4ZEzdIDTi0tFefk/YXQqSKZ9ifktmtW/pR1bQ=";
  };

  # Unit tests will fail with hyprland module
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

    # Defined in requirements.txt
    python3Packages.click
    python3Packages.loguru
    python3Packages.pycairo
    python3Packages.pygobject3
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    license = with licenses; [agpl3Only];
    platforms = lib.platforms.linux;
  };
}
