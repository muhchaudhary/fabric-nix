# shared-packages.nix
{pkgs}: {
  sharedPythonPackages = with pkgs.python3Packages;
    [
      psutil
      requests
      lxml
      pam
      thefuzz
      numpy
      magic
      colorthief
    ]
    ++ [
      pkgs.gengir
      pkgs.pywayland-custom
    ];
}
