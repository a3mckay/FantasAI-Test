{pkgs}: {
  deps = [
    pkgs.git
    pkgs.libxcrypt
    pkgs.cacert
    pkgs.libuv
    pkgs.zlib
    pkgs.openssl
    pkgs.grpc
    pkgs.c-ares
    pkgs.pkg-config
    pkgs.libffi
    pkgs.rustc
    pkgs.libiconv
    pkgs.cargo
    pkgs.glibcLocales
  ];
}
