#!/bin/sh
#########################################

firefly_pbi_path=/usr/pbi/firefly-$(uname -m)/

mkdir -p ${firefly_pbi_path}/mnt
mkdir -p ${firefly_pbi_path}/www

pw user add daapd -d ${firefly_pbi_path}
