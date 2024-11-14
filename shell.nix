{pkgs ? import <nixpgs> {}}:
pkgs.mkShell {
  name = "fabric-shell";
  packages = with pkgs; [
    ruff # Linter
    basedpyright # Language server

    # Required for Devshell
    gtk3
    gtk-layer-shell
    cairo
    gobject-introspection
    libdbusmenu-gtk3
    gdk-pixbuf
    gnome.gnome-bluetooth
    cinnamon.cinnamon-desktop

    (python3.withPackages (
      ps:
        with ps; [
          setuptools
          wheel
          build
          python-fabric

          # Additional Packages
          psutil
          colorthief
          requests
          lxml
          pam
          thefuzz
          pywayland-custom
          setuptools
        ]
    ))

    # Additional packages
    fabric-libgray
    fabric-libglace
    rlottie-python
    networkmanager
    playerctl
  ];
}
