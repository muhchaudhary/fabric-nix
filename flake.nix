{
  description = "My Fabric Bar Test V1";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/24.05";
    unstable.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    fabric.url = "github:Fabric-Development/fabric";
    fabric-libgray.url = "github:Fabric-Development/gray";
    fabric-libglace.url = "github:Fabric-Development/glace/hyprland";
  };

  outputs = {
    self,
    nixpkgs,
    unstable,
    utils,
    fabric,
    ...
  } @ inputs:
    utils.lib.eachDefaultSystem (
      system: let
        overlays = [
          (final: prev: {basedpyright = unstable.legacyPackages.${system}.basedpyright;})
          (final: prev: {fabric-libgray = inputs.fabric-libgray.packages.${system}.default;})
          (final: prev: {fabric-libglace = inputs.fabric-libglace.packages.${system}.default;})
          (final: prev: {rlottie-python = pkgs.python3Packages.callPackage ./nix/rolttie-python.nix {};})
          (final: prev: {pywayland-custom = pkgs.python3Packages.callPackage ./nix/pywayland.nix {};})

          fabric.overlays.${system}.default
        ];

        pkgs = import nixpkgs {
          system = system;
          overlays = overlays;
        };
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {inherit pkgs;};
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
