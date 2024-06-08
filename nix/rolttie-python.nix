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
  pname = "rlottie-python";
  version = "1.3.5";

  src = fetchFromGitHub {
    owner = "laggykiller";
    repo = "rlottie-python";
    rev = "52623947f1fd270bcc1c98a89bc3219cde958d2c";
    sha256 = "sha256-TLH+ByqTWdDYFOTpREWTAuGSHMlEKNCK0h1nS0CHzwM=";
  };

  # unit tests will fail with hyprland module
  doCheck = false;

  nativeBuildInputs = [
    cmake
  ];

  propagatedBuildInputs = [
    # defined in requirements.txt
    python3Packages.cmake
  ];

  meta = with lib; {
    description = "next-gen GTK+ based desktop widgets python framework";
    homepage = "http://github.com/Fabric-Development/fabric";
    # To be changed later
    license = with licenses; [lgpl21Only mpl11];
    platforms = lib.platforms.linux;
  };
}
