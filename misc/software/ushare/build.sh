#!/usr/bin/env bash

build_ushare() {
  sh $SVNDIR/misc/software/ushare/ushare-0.9.8.shar
  cd /usr/ports/net/ushare

  make clean
  make

  return 0
}

install_ushare() {
  cd /usr/ports/net/ushare

  install -vs work/ushare-*/src/ushare $FREENAS/usr/local/bin

  return 0
}
