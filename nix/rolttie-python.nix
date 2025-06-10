{
  lib,
  fetchPypi,
  buildPythonPackage,
  python3Packages,
  pkg-config,
  cmake,
  rlottie,
  distlib,
  flit-core,
  tomli,
  click,
}: let
  pybuild = buildPythonPackage rec {
    pname = "py-build-cmake";
    version = "0.1.8";
    pyproject = true;
    src = fetchPypi {
      inherit version pname;
      sha256 = "sha256-+QuOK5onNnD+clHnROrt51Ey55jlQCR3KCpHASsuW9s=";
    };
    doCheck = false;
    dontUseCmakeConfigure = true;
    nativeBuildInputs = [
      cmake
    ];
    propagatedBuildInputs = [
      distlib
      flit-core
      tomli
      click
    ];
  };
in
  buildPythonPackage rec {
    pname = "rlottie_python";
    version = "1.3.6";
    pyproject = true;

    src = fetchPypi {
      inherit pname version;
      sha256 = "sha256-VuzBkq3sPHGEiX2/MTTfp5rqf1nIv8Lal9LIBDBQrAQ=";
    };

    doCheck = false;
    dontUseCmakeConfigure = true;

    nativeBuildInputs = [
      cmake
      python3Packages.cmake
      pybuild
    ];

    patches = [
      ./pyproject.patch
    ];

    build-system = [
      pybuild
    ];

    meta = with lib; {
      description = "next-gen GTK+ based desktop widgets python framework";
      homepage = "http://github.com/Fabric-Development/fabric";
      # To be changed later
      license = with licenses; [lgpl21Only mpl11];
      platforms = lib.platforms.linux;
    };
  }
