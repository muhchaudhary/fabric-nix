let
  pkgs = import <nixpkgs> {};
  fabric = pkgs.python3Packages.callPackage ./nix/fabric.nix {};
  gir-cvc = pkgs.callPackage ./nix/gir-cvc.nix {};
in
  pkgs.mkShell {
    buildInputs = with pkgs; [
      fabric
      gir-cvc

      # add aditional python packages here
      python311Packages.psutil
      python311Packages.colorthief
      python311Packages.requests

      # non python aditional packages
      ruff
      playerctl # For mpirs
      gnome.gnome-bluetooth # For bluetooth
      networkmanager # For network
    ];
    nativeBuildInputs = with pkgs; [
      gobject-introspection
    ];
    # fix svg
    shellHook = ''
      export GDK_PIXBUF_MODULEDIR=${pkgs.librsvg}/lib/gdk-pixbuf-2.0/2.10.0/loaders
    '';
  }
