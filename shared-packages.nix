# shared-packages.nix
{pkgs}: {
  sharedPackages = with pkgs; [
    # gengir
    fabric-libgray
    fabric-libglace
    networkmanager
    playerctl
    librsvg
  ];

  sharedPythonPackages = with pkgs.python3Packages;
    [
      psutil
      colorthief
      requests
      lxml
      pam
      thefuzz
      numpy
      magic
    ]
    ++ [
      # custom python packages
      pkgs.rlottie-python
      pkgs.gengir
      pkgs.pywayland-custom
    ];
}
