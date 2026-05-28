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
        # Change this single value to switch Python version across the flake.
        pythonPackagesAttr = "python314Packages";
        pythonAttr = builtins.replaceStrings ["Packages"] [""] pythonPackagesAttr;

        overlays = [
          fabric.overlays.${system}.default
          (final: prev: {
            "${pythonPackagesAttr}" = prev.${pythonPackagesAttr}.overrideScope (
              pyfinal: pyprev: {
                pygobject3 = pyprev.pygobject3.overridePythonAttrs (_: {
                  version = "3.50.0";
                  src = final.fetchurl {
                    url = "mirror://gnome/sources/pygobject/3.50/pygobject-3.50.0.tar.xz";
                    hash = "sha256-jYNudbWogdRX7hYiyuSjK826KKC6ViGTrbO7tHJHIhI=";
                  };
                });
                python-fabric = final.callPackage "${inputs.fabric}/default.nix" {
                  python312Packages = pyfinal;
                };
              }
            );
            fabric-libglace = inputs.fabric-libglace.packages.${system}.default;
            basedpyright = nixpkgs.legacyPackages.${system}.basedpyright;
            fabric-libgray = inputs.fabric-libgray.packages.${system}.default;
            hyprland-overview-rs = inputs.hyprland-overview-rs.packages.${system}.default;
            gengir = final.${pythonPackagesAttr}.callPackage ./nix/gengir.nix {
              typer = final.${pythonPackagesAttr}.typer;
              astor = final.${pythonPackagesAttr}.astor;
              lxml = final.${pythonPackagesAttr}.lxml;
            };
            rlottie-python = final.${pythonPackagesAttr}.callPackage ./nix/rolttie-python.nix {
              distlib = final.${pythonPackagesAttr}.distlib;
              flit-core = final.${pythonPackagesAttr}.flit-core;
              tomli = final.${pythonPackagesAttr}.tomli;
              click = final.${pythonPackagesAttr}.click;
            };
          })
        ];

        pkgs = import nixpkgs {
          inherit system overlays;
        };
        python = pkgs.${pythonAttr};
        pythonPackages = pkgs.${pythonPackagesAttr};

        python-depends = [
          pythonPackages.pyinstrument
          pythonPackages.lxml
          pythonPackages.psutil
          pythonPackages.requests
          pythonPackages.python-pam
          pythonPackages.colorthief
          pythonPackages.thefuzz
          pkgs.gengir
          pythonPackages.python-fabric
          (pythonPackages.callPackage ./nix/pywayland.nix {})
          pythonPackages.qrcode
          pythonPackages.ijson
          pythonPackages.debugpy
          pythonPackages.magic
        ];

        astal-depends = [pkgs.astal.network pkgs.dart-sass];
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {
          inherit pkgs python pythonPackages python-depends astal-depends;
        };
        packages.default = pythonPackages.callPackage ./derivation.nix {
          inherit (pkgs) lib;
          python-fabric = pythonPackages.python-fabric;
          psutil = pythonPackages.psutil;
          requests = pythonPackages.requests;
          lxml = pythonPackages.lxml;
          pam = pythonPackages.python-pam;
          thefuzz = pythonPackages.thefuzz;
          colorthief = pythonPackages.colorthief;
          pywayland-custom = pythonPackages.callPackage ./nix/pywayland.nix {};
        };
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/fabric-config";
        };
      }
    );
}
