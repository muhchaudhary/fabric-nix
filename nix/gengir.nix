{
  lib,
  buildPythonPackage,
  fetchPypi,
  python,
  python3Packages,
  pkg-config,
}:
buildPythonPackage rec {
  pname = "gengir";
  version = "1.0.2";
  format = "setuptools";
  doCheck = false;
  src = fetchPypi {
    inherit pname version;
    hash = "sha256-cM+6HZ9JHuU31croD8Kdh4bQl9AYlXHOufd4D7TUtHU=";
  };

  dependencies = with python3Packages; [
    typer
    astor
    lxml
  ];
}
