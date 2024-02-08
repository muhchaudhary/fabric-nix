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
    ];
    nativeBuildInputs = with pkgs; [
      wrapGAppsHook
      gobject-introspection
      pkg-config
    ];
  }
