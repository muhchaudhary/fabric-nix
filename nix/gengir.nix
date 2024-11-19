{
  lib,
  rustPlatform,
  fetchFromGitHub,
  pkg-config,
}:
rustPlatform.buildRustPackage rec {
  pname = "gengir";
  version = "1.1.0";

  src = fetchFromGitHub {
    owner = "its-darsh";
    repo = "gengir";
    rev = "0081b579d1d5cfa984fa91ae886195dbbf04c54f";
    sha256 = "sha256-iLbrC6UQSgaiJe+D04fjdK3u+tIKjJKo1rW2frfz8Mk=";
  };
  cargoHash = "sha256-Y5eoHc7AjbLaTaYtgckDEiaAgJlTo4p/P06vvmShxrg=";
  allowBuiltinFetchGit = true;
  #   cargoLock = {
  #     lockFile = "${src}/Cargo.lock";
  # allowBuiltinFetchGit = true;
  # outputHashes = {
  #   "xml-rs-0.8" = "d2d7d3948613f75c98fd9328cfdcc45acc4d360655289d0a7d4ec931392200a3";
  #   "lazy_static-1.4.0" = "e2abad23fbc42b3700f2f279844dc832adb2b2eb069b2df918f455c4e18cc646";
  #   "regex-1.5.4" = "d07a8629359eb56f1e2fb1652bb04212c072a87ba68546a04065d525673ac461";
  #   "if_chain-1.0.2" = "cb56e1aa765b4b4f3aadfab769793b7087bb03a4ea4920644a6d238e2df5b9ed";
  #   "clap-3.0.0-rc.7" = "d2d7d3948613f75c98fd9328cfdcc45acc4d360655289d0a7d4ec931392200a3";
  #   "indexmap-1.7.0" = "bc633605454125dec4b66843673f01c7df2b89479b32e0ed634e43a91cff62a5";
  #   #   "aho-corasick-0.7.18" = "sha256-rESQz5jjNpVfIuTaRCAV2TLeUs09lOaLZVACsb/3Adg=";
  #   #   "atty-0.2.14" = "sha256-CpND9SxPwFmXe6fINrvd/7+HHzESh/O4GMJzaKQIjc8=";
  #   #   "autocfg-1.0.1" = "sha256-LjM7LH6rL3moCKxVsA+RUL9lfnvY31IrqHa9pDIAZNE=";
  # };
  #   };

  nativeBuildInputs = [pkg-config];
}
