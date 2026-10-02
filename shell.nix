{
  pkgs,
  python,
  pythonPackages,
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
      geoclue2
      sox

      (python.withPackages (
        ps:
          with ps;
            [
              setuptools
              wheel
              build
              pyopengl
              numpy
              # pygobject-stubs comes from python-depends (via python-fabric), pinned
              # to GTK3 in flake.nix; listing ps.pygobject-stubs here would add the
              # unpinned GTK4 build and conflict with it
            ]
            ++ python-depends
      ))
    ]
    ++ astal-depends;

  # shellHook = ''
  #   ${python.interpreter} ${./nix/tt.py}
  #   export GDK_PIXBUF_MODULEDIR=${pkgs.librsvg}/lib/gdk-pixbuf-2.0/2.10.0/loaders
  # '';
}
