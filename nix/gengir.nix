{
  buildPythonPackage,
  fetchPypi,
  python,
  typer,
  astor,
  lxml,
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

  propagatedBuildInputs = [
    typer
    astor
    lxml
  ];
}
