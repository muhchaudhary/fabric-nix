{
  description = "My Fabric Bar Test V1";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    fabric.url = "github:Fabric-Development/fabric";
    fabric-libgray.url = "github:Fabric-Development/gray";
    fabric-libglace.url = "github:muhchaudhary/glace/hyprland";
    toplevel-streamer-rs.url = "github:muhchaudhary/toplevel-streamer-rs";
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
                  version = "3.50.0"; # pygobject is STILL broken
                  src = final.fetchurl {
                    url = "mirror://gnome/sources/pygobject/3.50/pygobject-3.50.0.tar.xz";
                    hash = "sha256-jYNudbWogdRX7hYiyuSjK826KKC6ViGTrbO7tHJHIhI=";
                  };
                });
                # Stubs default to GTK4; this project (and Fabric) use GTK3.
                # Overridden in the scope so transitive users get the same build.
                pygobject-stubs = pyprev.pygobject-stubs.overridePythonAttrs (old: {
                  PYGOBJECT_STUB_CONFIG = "Gtk3,Gdk3";
                  # Mark the stubs partial (PEP 561) so type checkers fall back to
                  # the real gi package for modules they don't cover, such as
                  # gi._propertyhelper, which Fabric's Property subclasses
                  # Also add stubs for the typelibs it doesn't ship (Gray, NM, ...)
                  postInstall = (old.postInstall or "") + ''
                    echo partial > $out/${pyfinal.python.sitePackages}/gi-stubs/py.typed
                    cp ${
                      final.callPackage ./nix/gi-extra-stubs.nix {
                        python3 = prev.${pythonAttr};
                        pygobject-stubs-src = pyprev.pygobject-stubs;
                      }
                    }/*.pyi $out/${pyfinal.python.sitePackages}/gi-stubs/repository/
                  '';
                });
                python-fabric = final.callPackage "${inputs.fabric}/default.nix" {
                  python312Packages = pyfinal;
                };
              }
            );
            fabric-libglace = inputs.fabric-libglace.packages.${system}.default;
            fabric-libgray = inputs.fabric-libgray.packages.${system}.default;
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

        python-depends = with pythonPackages;
          [
            pyinstrument
            lxml
            psutil
            requests
            python-pam
            colorthief
            thefuzz
            python-fabric
            (callPackage ./nix/pywayland.nix {})
            qrcode
            ijson
            debugpy
            magic
          ]
          ++ [
            # Hyprland window frame capture (Rust/pyo3 extension). abi3 wheel, so
            # this prebuilt module imports under whatever Python this flake uses.
            (inputs.toplevel-streamer-rs.lib.${system}.pythonPackage pythonPackages)
          ];

        astal-depends = [pkgs.astal.network pkgs.dart-sass];
      in {
        formatter = pkgs.nixfmt-rfc-style;
        devShells.default = pkgs.callPackage ./shell.nix {
          inherit pkgs python pythonPackages python-depends astal-depends;
        };
        packages.default = pythonPackages.callPackage ./derivation.nix {
          inherit astal-depends;
          toplevel-streamer = inputs.toplevel-streamer-rs.lib.${system}.pythonPackage pythonPackages;
        };
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/fabric-config";
        };
      }
    );
}
