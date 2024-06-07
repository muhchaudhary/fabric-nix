{
  gobject-introspection,
  meson,
  pkg-config,
  ninja,
  vala,
  glib,
  libdbusmenu-gtk3,
  gtk3,
}:
mkDerrivation {
  pname = "libglace";
  version = "0.01";
  src = fetchFromGitHub {
    owner = "Fabric-Development";
    repo = "glace";
    rev = "0b1aee8d30a36b2245789bd071e1e5876e529eeb";
    sha256 = "sha256-TLH+ByqTzdDYFOTpREWTAuGSHMlEKNCK0h1nS0CHHwM=";
  };
  outputs = ["out" "dev"];
  nativeBuildInputs = with pkgs; [
    gobject-introspection
    meson
    pkg-config
    ninja
    vala
  ];

  buildInputs = with pkgs; [
    glib
    libdbusmenu-gtk3
    gtk3
  ];
}
