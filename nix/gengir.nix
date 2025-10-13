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

  postPatch = ''
    # Ensure GIR files are read as bytes so lxml accepts XML with encoding declarations
    # Try multiple forms for opening the GIR path
    substituteInPlace gengir/main.py \
      --replace "with open(args['gir_path']) as f:" "with open(args['gir_path'], 'rb') as f:" || true
    substituteInPlace gengir/main.py \
      --replace 'with open(args["gir_path"]) as f:' 'with open(args["gir_path"], "rb") as f:' || true
    substituteInPlace gengir/main.py \
      --replace "open(args['gir_path'])" "open(args['gir_path'], 'rb')" || true
    substituteInPlace gengir/main.py \
      --replace 'open(args["gir_path"])' 'open(args["gir_path"], "rb")' || true

    # Ensure the XML() call receives bytes
    substituteInPlace gengir/main.py \
      --replace "root = XML(content, parser)" "root = XML(content if isinstance(content, (bytes, bytearray)) else content.encode('utf-8'), parser)" || true
  '';

  propagatedBuildInputs = [
    typer
    astor
    lxml
  ];
}
