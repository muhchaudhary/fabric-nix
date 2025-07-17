{
  description = "My Fabric Bar Test V1";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    fabric.url = "github:Fabric-Development/fabric";
    fabric-libgray.url = "github:Fabric-Development/gray";
    fabric-libglace.url = "github:muhchaudhary/glace/hyprland";
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
          (final: prev: {
            fabric-libglace = inputs.fabric-libglace.packages.${system}.default;
            basedpyright = nixpkgs.legacyPackages.${system}.basedpyright;
            fabric-libgray = inputs.fabric-libgray.packages.${system}.default;
          })
          (final: prev: {
            gengir = pkgs.python3Packages.callPackage ./nix/gengir.nix {
              typer = pkgs.python3Packages.typer;
              astor = pkgs.python3Packages.astor;
              lxml = pkgs.python3Packages.lxml;
            };
            rlottie-python = pkgs.python3Packages.callPackage ./nix/rolttie-python.nix {
              distlib = pkgs.python3Packages.distlib;
              flit-core = pkgs.python3Packages.flit-core;
              tomli = pkgs.python3Packages.tomli;
              click = pkgs.python3Packages.click;
            };
          })
          fabric.overlays.default
        ];

        pkgs = import nixpkgs {
          inherit system overlays;
        };

        python-depends = {
          lxml = pkgs.python3Packages.lxml;
          psutil = pkgs.python3Packages.psutil;
          requests = pkgs.python3Packages.requests;
          pam = pkgs.python3Packages.pam;
          colorthief = pkgs.python3Packages.colorthief;
          thefuzz = pkgs.python3Packages.thefuzz;
          gengir = pkgs.gengir;
          python-fabric = fabric.packages.${system}.python-fabric;
          pywayland-custom = pkgs.python3Packages.callPackage ./nix/pywayland.nix {};
        };
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {
          inherit pkgs python-depends;
        };
        packages.default = pkgs.python3Packages.callPackage ./derivation.nix {
          inherit (pkgs) lib python-depends;
        };
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/fabric-config";
        };
      }
    );
}
