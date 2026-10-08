{
  lib,
  pkgs,
  buildPythonApplication,
  setuptools,
  wrapGAppsHook3,
  gobject-introspection,
  # Python dependencies
  python-fabric,
  psutil,
  thefuzz,
  pillow,
  toplevel-streamer,
  # Extra typelibs / tools supplied by the flake
  astal-depends ? [ ],
  fabric-libgray,
  fabric-libglace,
  ...
}:
let
  # Executables the bar spawns. Appended to PATH (--suffix), so versions
  # installed on the system still take precedence. Compositor-side tools
  # (hyprctl, hyprlock, uwsm) and nvidia-smi are expected from the system.
  runtimeTools = with pkgs; [
    dart-sass # compiles the SCSS at startup
    brightnessctl
    cliphist
    wl-clipboard
    ffmpegthumbnailer
    hyprshot
    slurp
    grim # copy text: capture the selected region
    (tesseract.override { enableLanguages = [ "eng" ]; }) # copy text (OCR)
    wf-recorder
    swappy
    libnotify # notify-send
    psmisc # killall
    procps # pidof
    xdg-utils
    sox # play (notification sound)
    dconf
    pulseaudio # pactl (default sink/source lookup)
    cava # desktop audio visualizer
  ];
in
buildPythonApplication {
  pname = "fabric-config";
  version = "0.0.1";
  pyproject = true;

  src = ./.;

  build-system = [ setuptools ];

  nativeBuildInputs = [
    wrapGAppsHook3
    gobject-introspection
  ];

  # GObject typelibs loaded at runtime via gi.require_version
  buildInputs =
    (with pkgs; [
      gtk3
      gtk-layer-shell
      gdk-pixbuf
      librsvg # Rsvg
      networkmanager # NM
      geoclue2 # Geoclue
      gnome-bluetooth # GnomeBluetooth (fabric.bluetooth)
      cinnamon-desktop # Cvc (fabric.audio)
      libdbusmenu-gtk3 # tray menus (Gray)
    ])
    ++ [
      fabric-libgray # Gray
      fabric-libglace # Glace
    ]
    ++ astal-depends; # AstalNetwork (and dart-sass, also on PATH below)

  dependencies = [
    python-fabric
    psutil
    thefuzz
    pillow
    toplevel-streamer
  ];

  doCheck = false;
  dontWrapGApps = true;

  preFixup = ''
    makeWrapperArgs+=("''${gappsWrapperArgs[@]}")
    makeWrapperArgs+=(--suffix PATH : ${lib.makeBinPath runtimeTools})
  '';

  meta = {
    description = "Fabric (GTK3) status bar and overlays for Hyprland";
    mainProgram = "fabric-config";
    platforms = lib.platforms.linux;
  };
}
