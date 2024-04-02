{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    systems.url = "github:nix-systems/default";
    gtk-session-lock.url = "github:Cu3PO42/gtk-session-lock";
  };

  outputs = {
    systems,
    nixpkgs,
    ...
  } @ inputs: let
    eachSystem = f:
      nixpkgs.lib.genAttrs (import systems) (
        system:
          f (import nixpkgs {
            inherit system;
            overlays = [
              (final: _: let
                gtk-session-lock = inputs.gtk-session-lock.packages.${system}.default;
              in {
                inherit gtk-session-lock;
              })
            ];
          })
      );
  in {
    devShells = eachSystem (pkgs: let
      fabric = pkgs.python3Packages.callPackage ./nix/fabric.nix {};
      gir-cvc = pkgs.callPackage ./nix/gir-cvc.nix {};
    in {
      default = pkgs.mkShell {
        buildInputs = with pkgs; [
          # Custom Packages
          fabric
          gir-cvc

          # add aditional python packages here
          python3Packages.psutil
          python3Packages.colorthief
          python3Packages.requests
          python3Packages.lxml
          python3Packages.pam

          ruff # Formatter
        ];
        nativeBuildInputs = with pkgs; [
          gobject-introspection

          # non python aditional packages
          gtk-session-lock # For gtk lock screen
          playerctl # For mpirs
          gnome.gnome-bluetooth # For bluetooth
          networkmanager # For network
          libgweather # For weather
        ];
        # shellHook = ''
        #   export GDK_PIXBUF_MODULEDIR=${pkgs.librsvg}/lib/gdk-pixbuf-2.0/2.10.0/loaders
        # '';
      };
    });
  };
}
