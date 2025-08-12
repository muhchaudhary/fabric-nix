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
          fabric.overlays.${system}.default
          (final: prev: {
            fabric-libglace = inputs.fabric-libglace.packages.${system}.default;
            basedpyright = nixpkgs.legacyPackages.${system}.basedpyright;
            fabric-libgray = inputs.fabric-libgray.packages.${system}.default;
            gengir = pkgs.python312Packages.callPackage ./nix/gengir.nix {
              typer = pkgs.python312Packages.typer;
              astor = pkgs.python312Packages.astor;
              lxml = pkgs.python312Packages.lxml;
            };
            rlottie-python = pkgs.python312Packages.callPackage ./nix/rolttie-python.nix {
              distlib = pkgs.python312Packages.distlib;
              flit-core = pkgs.python312Packages.flit-core;
              tomli = pkgs.python312Packages.tomli;
              click = pkgs.python312Packages.click;
            };
          })
        ];

        pkgs = import nixpkgs {
          inherit system overlays;
        };

        python-depends = {
          lxml = pkgs.python312Packages.lxml;
          psutil = pkgs.python312Packages.psutil;
          requests = pkgs.python312Packages.requests;
          pam = pkgs.python312Packages.pam;
          colorthief = pkgs.python312Packages.colorthief;
          thefuzz = pkgs.python312Packages.thefuzz;
          gengir = pkgs.gengir;
          python-fabric = pkgs.python312Packages.python-fabric;
          pywayland-custom = pkgs.python312Packages.callPackage ./nix/pywayland.nix {};
        };
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {
          inherit pkgs python-depends;
        };
        packages.default = pkgs.python312Packages.callPackage ./derivation.nix {
          inherit (pkgs) lib python-depends;
        };
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/fabric-config";
        };
      }
    );
}
