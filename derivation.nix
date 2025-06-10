{
  lib,
  pkgs,
  buildPythonApplication,
  gtk3,
  gtk-layer-shell,
  cairo,
  gobject-introspection,
  libdbusmenu-gtk3,
  gdk-pixbuf,
  gnome,
  wrapGAppsHook3,
  # Custom Packages
  fabric-libgray,
  fabric-libglace,
  pywayland-custom,
  rlottie-python,
  python-fabric,
  psutil,
  requests,
  lxml,
  pam,
  thefuzz,
  colorthief,
  setuptools,
  ...
}:
buildPythonApplication {
  pname = "fabric-nix-example";
  version = "0.0.1";
  pyproject = true;

  src = ./.;

  nativeBuildInputs = [
    wrapGAppsHook3
    gtk3
    gobject-introspection
    cairo
  ];
  buildInputs = with pkgs; [
    # Additional packages
    fabric-libgray
    fabric-libglace
    networkmanager
    playerctl
    librsvg
    libdbusmenu-gtk3
    gtk-layer-shell
    gnome-bluetooth
    cinnamon-desktop
    gdk-pixbuf
  ];

  propagatedBuildInputs = [
    python-fabric
    psutil
    requests
    lxml
    pam
    thefuzz
    pywayland-custom
    setuptools
    colorthief
  ];

  doCheck = false;
  dontWrapGApps = true;

  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
  '';

  meta = {
    changelog = "";
    description = ''
      Fabrix Bar Example
    '';
    homepage = "https://github.com/wholikeel/fabric";
    license = lib.licenses.agpl3Only;
  };
}
