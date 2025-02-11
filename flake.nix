{
  description = "My Fabric Bar Test V1";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";

    fabric = {
      url = "github:nikitax44/fabric/run-widget_qol";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    fabric-libgray = {
      url = "github:Fabric-Development/gray";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    fabric-libglace = {
      url = "github:muhchaudhary/glace/hyprland";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    utils,
    fabric,
    ...
  } @ inputs:
    utils.lib.eachDefaultSystem (
      system: let
        overlays = [
          (final: prev: {fabric-libglace = inputs.fabric-libglace.packages.${system}.default;})
          (final: prev: {basedpyright = nixpkgs.legacyPackages.${system}.basedpyright;})
          (final: prev: {fabric-libgray = inputs.fabric-libgray.packages.${system}.default;})

          (final: prev: {gengir = pkgs.python3Packages.callPackage ./nix/gengir.nix {};})
          (final: prev: {rlottie-python = pkgs.python3Packages.callPackage ./nix/rolttie-python.nix {};})
          (final: prev: {pywayland-custom = pkgs.python3Packages.callPackage ./nix/pywayland.nix {};})
          (final: prev: {run-widget = fabric.packages.${system}.run-widget;})

          fabric.overlays.${system}.default
        ];

        pkgs = import nixpkgs {
          system = system;
          overlays = overlays;
        };
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {
          inherit pkgs;
        };
        packages.default = pkgs.callPackage ./derivation.nix {
          inherit (pkgs) lib python3Packages;
        };
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/fabric-config";
        };
      }
    );
}
