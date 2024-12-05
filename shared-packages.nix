# shared-packages.nix
{pkgs}: {
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
