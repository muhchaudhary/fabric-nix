{
  lib,
  fetchFromGitHub,
  buildPythonPackage,
  ninja,
  meson,
  gtk3,
  glib,
  gtk-layer-shell,
  gobject-introspection,
  python3Packages,
  libdbusmenu-gtk3,
  pkg-config,
  wrapGAppsHook,
  gdk-pixbuf,
  cairo,
  librsvg,
  pkgconf,
}:
buildPythonPackage rec {
  pname = "fabric";
  version = "0.0.1";
  src = fetchFromGitHub {
    owner = "its-darsh";
    repo = "fabric";
    rev = "db3903756238a18fb3e5292e4e4c0e0041240658";
    sha256 = "sha256-huc8LJwkeQMQ3jELul5IpPhvwHXk4fWY98xvhYohwGQ=";
  };
  format = "setuptools";

  # unit tests will fail with hyprland module
  doCheck = false;

  nativeBuildInputs = [
    gobject-introspection
    python3Packages.setuptools
    python3Packages.meson
    ninja
    meson
  ];

  propagatedBuildInputs = [
    glib
    libdbusmenu-gtk3
    gtk3
    gtk-layer-shell
    gdk-pixbuf
    cairo
    librsvg
    pkgconf

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
