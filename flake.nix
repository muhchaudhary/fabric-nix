{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    systems.url = "github:nix-systems/default";
    gtk-session-lock.url = "github:Cu3PO42/gtk-session-lock";
  };

  outputs = {
    systems,
    nixpkgs,
    gtk-session-lock,
    ...
  } @ inputs: let
    eachSystem = f:
      nixpkgs.lib.genAttrs (import systems) (
        system:
          f nixpkgs.legacyPackages.${system}
      );
  in {
    devShells = eachSystem (pkgs: let
      fabric = pkgs.python3Packages.callPackage ./nix/fabric.nix {};
      gir-cvc = pkgs.callPackage ./nix/gir-cvc.nix {};
    in {
      default = pkgs.mkShell {
        buildInputs = with pkgs; [
          fabric
          gir-cvc
          gtk-session-lock.packages.${system}

          # add aditional python packages here
          python311Packages.psutil
          python311Packages.colorthief
          python311Packages.requests

          # non python aditional packages
          gtk-session-lock # for ext-session-lock
          ruff
          playerctl # For mpirs
          gnome.gnome-bluetooth # For bluetooth
          networkmanager # For network
        ];
        nativeBuildInputs = with pkgs; [
          gobject-introspection
        ];
        shellHook = ''
          export GDK_PIXBUF_MODULEDIR=${pkgs.librsvg}/lib/gdk-pixbuf-2.0/2.10.0/loaders
        '';
      };
    });
  };
}
