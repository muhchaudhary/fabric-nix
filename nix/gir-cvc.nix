{
  stdenv,
  fetchurl,
  lib,
  pkg-config,
  gobject-introspection,
  meson,
  ninja,
  cmake,
  gdk-pixbuf,
  gtk3,
  systemd,
  xkeyboard_config,
  libxkbfile,
  libpulseaudio,
}:
stdenv.mkDerivation (finalAttrs: {
  pname = "libcvc-gir";
  # random version lol
  version = "22.0";

  src = fetchurl {
    url = "https://github.com/linuxmint/cinnamon-desktop/archive/refs/tags/master.mint22.tar.gz";
    hash = "sha256-lZjJqNqVTFMZLyoozoX8aACEqqBTfPMDvJWBwxrvLms=";
  };

  nativeBuildInputs = [meson ninja pkg-config gobject-introspection];

  # unsure if this patch actually gets applied
  patches = [
    ./meson.build.patch
  ];

  buildInputs = [
    cmake
    gdk-pixbuf
    gtk3
    systemd
    xkeyboard_config
    libxkbfile
    libpulseaudio
  ];

  installPhase = ''
    meson install
    cd libcvc
  '';

  doCheck = false;

  installFlags = [
    "sysconfdir=${placeholder "out"}/etc"
    "localstatedir=\${TMPDIR}"
    "typelibdir=${placeholder "out"}/lib/girepository-1.0"
  ];
})
