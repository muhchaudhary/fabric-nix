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
    rev = "0b1aee8d30a36b2245789bd071e1e5876e529eeb";
    sha256 = "sha256-TLH+ByqTWdDYFOTpREWTAuGSHMlEKNCK0h1nS0CHHwM=";
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
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    # To be changed later
    license = with licenses; [lgpl21Only mpl11];
    platforms = lib.platforms.linux;
  };
}
