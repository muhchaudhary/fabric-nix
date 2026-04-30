{
  description = "My Fabric Bar Test V1";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    fabric.url = "github:Fabric-Development/fabric";
    fabric-libgray.url = "github:Fabric-Development/gray";
    fabric-libglace.url = "github:muhchaudhary/glace/hyprland";
    hyprland-overview-rs.url = "github:muhchaudhary/overview-rs";
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
        pythonVerson = pkgs.python312;

        overlays = [
          fabric.overlays.${system}.default
          (final: prev: {
            fabric-libglace = inputs.fabric-libglace.packages.${system}.default;
            basedpyright = nixpkgs.legacyPackages.${system}.basedpyright;
            fabric-libgray = inputs.fabric-libgray.packages.${system}.default;
            hyprland-overview-rs = inputs.hyprland-overview-rs.packages.${system}.pythonPackage;
            gengir = final.python312Packages.callPackage ./nix/gengir.nix {
              typer = final.python312Packages.typer;
              astor = final.python312Packages.astor;
              lxml = final.python312Packages.lxml;
            };
            rlottie-python = final.python312Packages.callPackage ./nix/rolttie-python.nix {
              distlib = final.python312Packages.distlib;
              flit-core = final.python312Packages.flit-core;
              tomli = final.python312Packages.tomli;
              click = final.python312Packages.click;
            };
          })
        ];

        pkgs = import nixpkgs {
          inherit system overlays;
        };

        python-depends = {
          pyinstrument = pkgs.python312Packages.pyinstrument;
          lxml = pkgs.python312Packages.lxml;
          psutil = pkgs.python312Packages.psutil;
          requests = pkgs.python312Packages.requests;
          pam = pkgs.python312Packages.python-pam;
          colorthief = pkgs.python312Packages.colorthief;
          thefuzz = pkgs.python312Packages.thefuzz;
          gengir = pkgs.gengir;
          python-fabric = pkgs.python312Packages.python-fabric;
          pywayland-custom = pkgs.python312Packages.callPackage ./nix/pywayland.nix {};
          hyprland-overview-rs = pkgs.hyprland-overview-rs;
          qrcode = pkgs.python312Packages.qrcode;
          ijson = pkgs.python312Packages.ijson;
          debugpy = pkgs.python312Packages.debugpy;
        };

        astal-depends = [pkgs.astal.network pkgs.dart-sass];
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {
          inherit pkgs python-depends astal-depends;
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
