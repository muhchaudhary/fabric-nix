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
      magic
    ]
    ++ [
      # custom python packages
      pkgs.rlottie-python
      pkgs.pywayland-custom
    ];
}
