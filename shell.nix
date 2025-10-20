{
  pkgs,
  python-depends,
  astal-depends,
}:
pkgs.mkShell {
  name = "fabric-shell";
  packages = with pkgs;
    [
      ruff # Linter
      basedpyright # Language server

      # Required for Devshell
      gtk3
      gtk-layer-shell
      cairo
      gobject-introspection
      libdbusmenu-gtk3
      gdk-pixbuf
      gnome-bluetooth
      cinnamon-desktop

      # Addional packages
      fabric-libgray
      fabric-libglace
      networkmanager
      playerctl
      librsvg

      (python312.withPackages (
        ps:
          with ps;
            [
              setuptools
              wheel
              build
              pyopengl
              numpy
              pygobject-stubs
            ]
            ++ (builtins.attrValues python-depends)
      ))
    ]
    ++ astal-depends;

  shellHook = ''
    # ${pkgs.python312.interpreter} ./nix/tt.py
    # cp -rn "${pkgs.python312Packages.pygobject-stubs}/lib/python3.12/site-packages/gi-stubs/repository/." "/home/$USER/.local/lib/python3.12/site-packages/gi/repository/"
    export GDK_PIXBUF_MODULEDIR=${pkgs.librsvg}/lib/gdk-pixbuf-2.0/2.10.0/loaders
  '';
}
