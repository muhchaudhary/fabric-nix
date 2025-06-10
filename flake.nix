{
  description = "My Fabric Bar Test V1";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";

    fabric = {
      url = "github:Fabric-Development/fabric";
      # inputs.nixpkgs.follows = "nixpkgs";
    };
    fabric-libgray = {
      url = "github:Fabric-Development/gray";
      # inputs.nixpkgs.follows = "nixpkgs";
    };
    fabric-libglace = {
      url = "github:muhchaudhary/glace/hyprland";
      # inputs.nixpkgs.follows = "nixpkgs";
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

          (final: prev: {
            gengir = pkgs.python3Packages.callPackage ./nix/gengir.nix {
              typer = pkgs.python3Packages.typer;
              astor = pkgs.python3Packages.astor;
              lxml = pkgs.python3Packages.lxml;
            };
          })
          (final: prev: {
            rlottie-python = pkgs.python3Packages.callPackage ./nix/rolttie-python.nix {
              distlib = pkgs.python3Packages.distlib;
              flit-core = pkgs.python3Packages.flit-core;
              tomli = pkgs.python3Packages.tomli;
              click = pkgs.python3Packages.click;
            };
          })
          (final: prev: {pywayland-custom = pkgs.python3Packages.callPackage ./nix/pywayland.nix {};})
          (final: prev: {run-widget = fabric.packages.${system}.run-widget;})

          fabric.overlays.${system}.default
        ];

        pkgs = import nixpkgs {
          system = system;
          overlays = overlays;
        };
        python-depends = {
          lxml = pkgs.python3Packages.lxml;
          psutil = pkgs.python3Packages.psutil;
          python-fabric = pkgs.python3Packages.python-fabric;
          requests = pkgs.python3Packages.requests;
          thefuzz = pkgs.python3Packages.thefuzz;
          pam = pkgs.python3Packages.pam;
          colorthief = pkgs.python3Packages.colorthief;
        };
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {
          inherit pkgs;
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
