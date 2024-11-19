# shared-packages.nix
{pkgs}: {
  sharedPackages = with pkgs; [
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
    ]
    ++ [
      # custom python packages
      pkgs.rlottie-python
      pkgs.pywayland-custom
    ];
}
