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
    url = "https://github.com/linuxmint/cinnamon-desktop/archive/refs/tags/master.lmde6.tar.gz";
    hash = "sha256-r2/YKXMqIKxKPN91cZA5fHKCGDtcb14aXnEwF2cfJ4Q=";
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

  meta = with lib; {
    description = "Library for passing menu structures across DBus";
    homepage = "https://launchpad.net/dbusmenu";
    license = with licenses; [gpl3 lgpl21 lgpl3];
    platforms = platforms.linux;
    maintainers = [maintainers.msteen];
  };
})
