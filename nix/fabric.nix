{
  lib,
  fetchFromGitHub,
  buildPythonPackage,
  gtk3,
  glib,
  gtk-layer-shell,
  gobject-introspection,
  libdbusmenu-gtk3,
  gdk-pixbuf,
  librsvg,
  webkitgtk_4_1,
  click,
  loguru,
  pycairo,
  pygobject3,
  psutil,
  setuptools,
}:
buildPythonPackage rec {
  pname = "python-fabric";
  version = "0.0.1";
  format = "setuptools";

  src = fetchFromGitHub {
    owner = "Fabric-Development";
    repo = "fabric";
    rev = "23cab85fc61f1cdbb5f60db0027dc57026ba05b7";
    sha256 = "sha256-l5H9z9kq8QKbO57xigIU132NaLWPULg23oVOS9E5Sqk=";
  };

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

    click
    loguru
    pycairo
    pygobject3
    psutil
    setuptools
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    license = with licenses; [agpl3Only];
    platforms = lib.platforms.linux;
  };
}
