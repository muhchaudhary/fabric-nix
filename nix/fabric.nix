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
    rev = "581a38ad5f224d382a98639afa2611ebb5039cd5";
    sha256 = "sha256-goG7uIbyJTk/+G40hUyOv9DvRAotZkVgajjxHjCMZzc=";
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
