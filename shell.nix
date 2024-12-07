{pkgs ? import <nixpgs> {}}: let
  shared = import ./shared-packages.nix {inherit pkgs;};
in
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

      # Addional packages

      fabric-libgray
      fabric-libglace
      networkmanager
      playerctl
      librsvg

      (python3.withPackages (
        ps:
          with ps;
            [
              setuptools
              wheel
              build
              python-fabric
            ]
            ++ shared.sharedPythonPackages
      ))
    ];

    shellHook = ''
      # ${pkgs.python3.interpreter} ./nix/tt.py
      # cp -a "$(dirname "$(which python)")"/../${pkgs.python3.sitePackages}/gi-stubs/repository/. "/home/$USERNAME/.local/lib/python3.11/site-packages/gi/repository/"
      # chmod -R ugo+rw "/home/$USERNAME/.local/lib/python3.11/site-packages/gi/repository/"
      export GDK_PIXBUF_MODULEDIR=${pkgs.librsvg}/lib/gdk-pixbuf-2.0/2.10.0/loaders
    '';
  }
