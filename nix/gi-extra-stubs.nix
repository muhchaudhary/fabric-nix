# Type stubs for the typelibs this project imports that pygobject-stubs
# doesn't ship. Generated with pygobject-stubs' own generator (from its
# source, `pygobject-stubs-src`) so they match the rest of gi-stubs; flake.nix
# copies them into pygobject-stubs' gi-stubs/repository. They can't be merged
# in by python.withPackages: that turns gi-stubs into a directory of symlinks,
# which basedpyright's partial-stub handling doesn't follow.
{
  lib,
  stdenvNoCC,
  python3,
  pygobject-stubs-src,
  gobject-introspection,
  glib,
  gtk3,
  gtk-layer-shell,
  libdbusmenu-gtk3,
  networkmanager,
  astal,
  cinnamon-desktop,
  fabric-libgray,
  fabric-libglace,
}:
let
  # "Namespace:version" for each typelib to generate
  modules = [
    "AstalNetwork:0.1"
    "Cvc:1.0"
    "Glace:0.1"
    "Gray:0.1"
    "GtkLayerShell:0.1"
    "NM:1.0"
  ];
  # the generator needs GIRepository 3.0, so it runs with nixpkgs' unpinned
  # pygobject rather than the version this project pins at runtime
  generator-python = python3.withPackages (ps: [ ps.pygobject3 ]);
in
stdenvNoCC.mkDerivation {
  pname = "gi-extra-stubs";
  inherit (pygobject-stubs-src) version src;

  nativeBuildInputs = [
    generator-python
    gobject-introspection
  ];
  buildInputs = [
    glib
    gtk3
    gtk-layer-shell
    libdbusmenu-gtk3
    networkmanager
    astal.network
    cinnamon-desktop # Cvc
    fabric-libgray
    fabric-libglace
  ];

  # the generator calls BaseInfo.get_type() and GIRepository.InfoType, which
  # newer pygobject removed; this check is only reached for enums/flags with
  # non-identifier names (NM has some), and EnumInfo covers both
  postPatch = ''
    substituteInPlace tools/generate.py \
      --replace-fail "interface.get_type() in (" "isinstance(interface, (" \
      --replace-fail "GIRepository.InfoType.FLAGS," "GI.EnumInfo,)" \
      --replace-fail "GIRepository.InfoType.ENUM," ""
  '';

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    for module in ${lib.concatStringsSep " " modules}; do
      python tools/generate.py "''${module%%:*}" "''${module##*:}" > "$out/''${module%%:*}.pyi"
    done
    runHook postInstall
  '';
}
