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
  gdk-pixbuf,
  cairo,
  librsvg,
  # For Cvc
  libpulseaudio,
}:
buildPythonPackage rec {
  pname = "fabric";
  version = "0.0.1";
  src = fetchFromGitHub {
    owner = "its-darsh";
    repo = "fabric";
    rev = "db3903756238a18fb3e5292e4e4c0e0041240658";
    sha256 = "sha256-j0mvQm9cwogUb0m2ilUxEigSUytkQIlOm+9Kdpyyheo=";
    fetchSubmodules = true;
  };
  # We have a custom setup
  format = "other";

  # unit tests will fail with hyprland module
  doCheck = false;

  nativeBuildInputs = [
    gobject-introspection
    python3Packages.setuptools
    python3Packages.meson-python
    pkg-config
    ninja
    meson
  ];

  dependencies = [
    python3Packages.pygobject3
    python3Packages.pycairo
    python3Packages.loguru
    python3Packages.click
  ];

  buildPhase = ''
    meson --prefix=$out build
    ninja -C build
  '';

  installPhase = ''
    meson install -C build
  '';

  propagatedBuildInputs = [
    # Cvc
    libpulseaudio

    libdbusmenu-gtk3
    gtk-layer-shell
    gdk-pixbuf
    librsvg
    cairo
    glib
    gtk3
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    # To be changed later
    platforms = lib.platforms.linux;
  };
}
