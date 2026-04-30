{
  description = "My Fabric Bar Test V1";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # Pygobject3 is broken, use an older version until it is fixed
    nixpkgsPygobject3.url = "github:NixOS/nixpkgs/b681065d0919f7eb5309a93cea2cfa84dec9aa88";
    utils.url = "github:numtide/flake-utils";
    fabric.url = "github:Fabric-Development/fabric";
    fabric-libgray.url = "github:Fabric-Development/gray";
    fabric-libglace.url = "github:muhchaudhary/glace/hyprland";
    hyprland-overview-rs.url = "github:muhchaudhary/overview-rs";
  };

  outputs = {
    self,
    nixpkgs,
    nixpkgsPygobject3,
    utils,
    fabric,
    ...
  } @ inputs:
    utils.lib.eachDefaultSystem (
      system: let
        # Change this single value to switch Python version across the flake.
        pythonPackagesAttr = "python314Packages";
        pythonAttr = builtins.replaceStrings ["Packages"] [""] pythonPackagesAttr;
        pygobject3Pkgs = import nixpkgsPygobject3 {
          inherit system;
        };

        overlays = [
          fabric.overlays.${system}.default
          (final: prev: {
            "${pythonPackagesAttr}" = prev.${pythonPackagesAttr}.overrideScope (
              pyfinal: pyprev: {
                pygobject3 = pyprev.pygobject3.overridePythonAttrs (_: {
                  inherit (pygobject3Pkgs.${pythonPackagesAttr}.pygobject3) version src;
                });
                python-fabric = pyfinal.callPackage ./nix/fabric.nix {
                  gtk3 = final.gtk3;
                  glib = final.glib;
                  gtk-layer-shell = final.gtk-layer-shell;
                  gobject-introspection = final.gobject-introspection;
                  libdbusmenu-gtk3 = final.libdbusmenu-gtk3;
                  gdk-pixbuf = final.gdk-pixbuf;
                  librsvg = final.librsvg;
                  webkitgtk_4_1 = final.webkitgtk_4_1;
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
