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
      python311Packages.pillow
      python311Packages.colorthief

      playerctl
    ];
    nativeBuildInputs = with pkgs; [
      wrapGAppsHook
      gobject-introspection
      pkg-config
    ];
    # fix svg
    shellHook = ''
      export GDK_PIXBUF_MODULEDIR=${pkgs.librsvg}/lib/gdk-pixbuf-2.0/2.10.0/loaders
    '';
  }
