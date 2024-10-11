{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    systems.url = "github:nix-systems/default";
    gtk-session-lock.url = "github:Cu3PO42/gtk-session-lock";
    astal.url = "github:aylur/astal";
    fabric-libgray.url = "github:Fabric-Development/gray";
    fabric-libglace.url = "github:Fabric-Development/glace";
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
              (final: _: let
                astal-notifd = inputs.astal.packages.${system}.notifd;
              in {
                inherit astal-notifd;
              })
              (final: _: let
                fabric-libgray = inputs.fabric-libgray.packages.${system}.default;
              in {
                inherit fabric-libgray;
              })
              (final: _: let
                fabric-libglace = inputs.fabric-libglace.packages.${system}.default;
              in {
                inherit fabric-libglace;
              })
            ];
          })
      );
  in {
    devShells = eachSystem (pkgs: let
      fabric = pkgs.python3Packages.callPackage ./nix/fabric.nix {};
      gir-cvc = pkgs.callPackage ./nix/cvc/gir-cvc.nix {};
      rlottie-python = pkgs.python3Packages.callPackage ./nix/rolttie-python.nix {};
    in {
      default = pkgs.mkShell {
        buildInputs = with pkgs; [
          # Custom Packages
          fabric
          astal-notifd
          fabric-libgray
          fabric-libglace

          rlottie-python

          # add aditional python packages here
          python3Packages.psutil
          python3Packages.colorthief
          python3Packages.requests
          python3Packages.lxml
          python3Packages.pam
          python3Packages.thefuzz

          ruff # Formatter
          vala-language-server # for vala code completions
        ];
        nativeBuildInputs = with pkgs; [
          rlottie # for animated images
          vala # Vala compiler
          gobject-introspection
          gir-cvc
          sox

          # non python aditional packages
          gtk-session-lock # For gtk lock screen
          playerctl # For mpirs
          gnome-bluetooth # For bluetooth
          networkmanager # For network
          libgweather # For weather
          libgudev # For uevent monitoring
        ];
      };
    });
  };
}
