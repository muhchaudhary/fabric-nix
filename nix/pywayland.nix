{
  lib,
  buildPythonPackage,
  fetchPypi,
  fetchurl,
  python,
  cffi,
  pkg-config,
  wayland,
  wayland-scanner,
  pytestCheckHook,
}:
buildPythonPackage rec {
  pname = "pywayland";
  version = "0.4.18";
  format = "setuptools";

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-WYreAng6rQWjKPZjtRtpTFq2i9XR4JJsDaPFISxWZTM=";
  };

  wayland-xml = fetchurl {
    url = "https://gitlab.freedesktop.org/wayland/wayland/-/raw/38f91fe6adb1c4e6347dc34111e17514dac4a439/protocol/wayland.xml";
    hash = "sha256-1fekIEi/CxNNLEQxUx8zMMVm4iQjQm0Humdea4gY9K8=";
  };

  hyprland-toplevel-export-v1-xml = fetchurl {
    url = "https://raw.githubusercontent.com/hyprwm/hyprland-protocols/301733ae466b229066ba15a53e6d8b91c5dcef5b/protocols/hyprland-toplevel-export-v1.xml";
    hash = "sha256-K44W2iLfMzSUthaiyDOU3MmqwEQF2lNRJtaBBnhkQa0=";
  };

  wlr-foreign-toplevel-management-unstable-v1-xml = fetchurl {
    url = "https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/raw/005d69d048ccceb2af3f5b86665821e8fa9a87b8/unstable/wlr-foreign-toplevel-management-unstable-v1.xml";
    hash = "sha256-TsxFiIWOKf5oCjNSHh8ivPIgcdZtFVP+lrTd7APVkdI=";
  };

  depsBuildBuild = [pkg-config];
  nativeBuildInputs = [wayland-scanner];
  propagatedNativeBuildInputs = [cffi];
  buildInputs = [wayland];
  propagatedBuildInputs = [cffi];
  # nativeCheckInputs = [pytestCheckHook];

  doCheck = false;

  postBuild = ''
    ${python.pythonOnBuildForHost.interpreter} pywayland/ffi_build.py
  '';

  postInstall = ''
    ${python.pythonOnBuildForHost.interpreter} -m pywayland.scanner -i \
        ${wayland-xml} \
        ${wlr-foreign-toplevel-management-unstable-v1-xml} \
        ${hyprland-toplevel-export-v1-xml} \
        -o "$out/${python.sitePackages}/$pname/protocol"
  '';

  meta = with lib; {
    homepage = "https://github.com/flacjacket/pywayland";
    description = "Python bindings to wayland using cffi";
    mainProgram = "pywayland-scanner";
    license = licenses.ncsa;
    maintainers = with maintainers; [chvp];
  };
}
