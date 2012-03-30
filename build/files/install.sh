#!/bin/sh

# Setup a semi-sane environment
PATH=/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin
export PATH
HOME=/root
export HOME
TERM=${TERM:-cons25}
export TERM

. /etc/avatar.conf

get_product_path()
{
    echo "/cdrom"
}

get_image_name()
{
    find "$(get_product_path)" -name "$AVATAR_PROJECT-$AVATAR_ARCH.img.xz" -type f
}

# Convert /etc/version* to /etc/avatar.conf
#
# 1 - old /etc/version* file
# 2 - dist version of avatar.conf
# 3 - destination avatar.conf
upgrade_version_to_avatar_conf()
{
    local destconf srcconf srcversion
    local project version revision arch

    srcversion=$1
    srcconf=$2
    destconf=$3

    set -- $(sed -E -e 's/-amd64/-x64/' -e 's/-i386/-x86/' -e 's/(.*)-([^-]+) \((.*)\)/\1-\3-\2/' -e 's/-/ /' -e 's/-([^-]+)$/ \1/' -e 's/-([^-]+)$/ \1/' < $srcversion)

    project=$1
    version=$2
    revision=$3
    arch=$4

    sed \
        -e "s/^AVATAR_ARCH=\".*\"/AVATAR_ARCH=\"$arch\"/g" \
        -e "s/^AVATAR_BUILD_NUMBER=\".*\"\$/AVATAR_BUILD_NUMBER=\"$revision\"/g" \
        -e "s/^AVATAR_PROJECT=\".*\"\$/AVATAR_PROJECT=\"$project\"/g" \
        -e "s/^AVATAR_VERSION=\".*\"\$/AVATAR_VERSION=\"$version\"/g" \
        < $srcconf > $destconf.$$

    mv $destconf.$$ $destconf
}

build_config()
{
    # build_config ${_disk} ${_image} ${_config_file}

    local _disk=$1
    local _image=$2
    local _config_file=$3

    cat << EOF > "${_config_file}"
# Added to stop pc-sysinstall from complaining
installMode=fresh
installInteractive=no
installType=FreeBSD
installMedium=dvd
packageType=tar

disk0=${_disk}
partition=image
image=${_image}
bootManager=bsd
commitDiskPart
EOF
}

wait_keypress()
{
    local _tmp
    read -p "Press ENTER to continue." _tmp
}

get_physical_disks_list()
{
    local _disks
    local _list
    local _d

    _list=""
    _disks=`sysctl -n kern.disks`
    for _d in ${_disks}; do
        case "${_d}" in
        cd*)
            ;;
        *)
            _list="${_list}${_d} "
	    ;;
        esac
    done

    VAL="${_list}"
    export VAL
}

get_media_description()
{
    local _media
    local _description
    local _cap

    _media=$1
    VAL=""
    if [ -n "${_media}" ]; then
        _description=`pc-sysinstall disk-list -c |grep "^${_media}"\
            | awk -F':' '{print $2}'|sed -E 's|.*<(.*)>.*$|\1|'`
        _cap=`diskinfo ${_media} | awk '{
            capacity = $3;
            if (capacity >= 1099511627776) {
                printf("%.1f TiB", capacity / 1099511627776.0);
            } else if (capacity >= 1073741824) {
                printf("%.1f GiB", capacity / 1073741824.0);
            } else if (capacity >= 1048576) {
                printf("%.1f MiB", capacity / 1048576.0);
            } else {
                printf("%d Bytes", capacity);
        }}'`
        VAL="${_description} -- ${_cap}"
    fi
    export VAL
}

disk_is_mounted()
{
    local _dev

    _dev="/dev/$1"
    mount -v|grep -qE "^${_dev}[sp][0-9]+"
    return $?
}


new_install_verify()
{
    local _type="$1"
    local _disk="$2"
    local _tmpfile="/tmp/msg"
    cat << EOD > "${_tmpfile}"
WARNING:
- This will erase ALL partitions and data on ${_disk}.
- You can't use ${_disk} for sharing data.

NOTE:
- Installing on flash media is preferred to installing on a
  hard drive.

Proceed with the ${_type}?
EOD
    _msg=`cat "${_tmpfile}"`
    rm -f "${_tmpfile}"
    dialog --title "$AVATAR_PROJECT ${_type}" --yesno "${_msg}" 13 74
    [ $? -eq 0 ] || exit 1
}

ask_upgrade()
{
    local _disk="$1"
    local _tmpfile="/tmp/msg"
    cat << EOD > "${_tmpfile}"
The $AVATAR_PROJECT installer can preserve your existing parameters, or
it can do a fresh install overwriting the current settings,
configuration, etc.

Would you like to upgrade the installation on ${_disk}?
EOD
    _msg=`cat "${_tmpfile}"`
    rm -f "${_tmpfile}"
    dialog --title "Upgrade this $AVATAR_PROJECT installation" --yesno "${_msg}" 8 74
    return $?
}

disk_is_freenas()
{
    local _disk="$1"
    local _rv=1

    mkdir -p /tmp/data_old
    mount /dev/${_disk}s4 /tmp/data_old
    ls /tmp/data_old > /tmp/data_old.ls
    if [ -f /tmp/data_old/freenas-v1.db ]; then
        _rv=0
    fi
    cp -pR /tmp/data_old /tmp/data_preserved
    umount /tmp/data_old
    if [ $_rv -eq 0 ]; then
	mount /dev/${_disk}s1a /tmp/data_old
        # ah my old friend, the can't see the mount til I access the mountpoint
        # bug
        ls /tmp/data_old > /dev/null
        cp -p /tmp/data_old/conf/base/etc/hostid /tmp/
        if [ -d /tmp/data_old/root/.ssh ]; then
            cp -pR /tmp/data_old/root/.ssh /tmp/
        fi
        if [ -d /tmp/data_old/boot/modules ]; then
            mkdir -p /tmp/modules
            for i in `ls /tmp/data_old/boot/modules`
            do
                cp -p /tmp/data_old/boot/modules/$i /tmp/modules/
            done
        fi
        if [ -d /tmp/data_old/usr/local/fusionio ]; then
            cp -pR /tmp/data_old/usr/local/fusionio /tmp/
        fi
        umount /tmp/data_old
    fi
    rmdir /tmp/data_old

    if [ -f /tmp/hostid ]; then
        return 0
    else
        return 1
    fi
}

menu_install()
{
    local _action
    local _disklist
    local _tmpfile
    local _answer
    local _cdlist
    local _items
    local _disk
    local _config_file
    local _desc
    local _list
    local _msg
    local _i
    local _do_upgrade
    local _menuheight

    local readonly CD_UPGRADE_SENTINEL="/data/cd-upgrade"
    local readonly NEED_UPDATE_SENTINEL="/data/need-update"

    get_physical_disks_list
    _disklist="${VAL}"

    _list=""
    _items=0
    for _disk in ${_disklist}; do
        get_media_description "${_disk}"
        _desc="${VAL}"
        _list="${_list} ${_disk} '${_desc}'"
        _items=$((${_items} + 1))
    done

    _tmpfile="/tmp/answer"
    if [ ${_items} -ge 10 ]; then
        _items=10
        _menuheight=20
    else
        _menuheight=8
        _menuheight=$((${_menuheight} + ${_items}))
    fi
    eval "dialog --title 'Choose destination media' \
          --menu 'Select the drive where $AVATAR_PROJECT should be installed.' \
          ${_menuheight} 60 ${_items} ${_list}" 2>${_tmpfile}
    [ $? -eq 0 ] || exit 1
    _disk=`cat "${_tmpfile}"`
    rm -f "${_tmpfile}"

    # Debugging seatbelts
    if disk_is_mounted "${_disk}" ; then
        dialog --msgbox "The destination drive is already in use!" 4 74
        exit 1
    fi

    _do_upgrade=0
    _action="installation"
    if disk_is_freenas ${_disk} ; then
        if ask_upgrade ${_disk} ; then
            _do_upgrade=1
            _action="upgrade"
        fi
    fi
    new_install_verify "$_action" ${_disk}
    _config_file="/tmp/pc-sysinstall.cfg"

    # Start critical section.
    trap "set +x; read -p \"The $AVATAR_PROJECT $_action on $_disk has failed. Press any key to continue.. \" junk" EXIT
    set -ex

    #  _disk, _image, _config_file
    # we can now build a config file for pc-sysinstall
    build_config  ${_disk} "$(get_image_name)" ${_config_file}

    if [ ${_do_upgrade} -eq 1 ]
    then
        /etc/rc.d/dmesg start
        mkdir /tmp/data
        mount /dev/${_disk}s1a /tmp/data
        # pre-avatar.conf build. Convert it!
        if [ ! -e /tmp/data/etc/avatar.conf ]
        then
            upgrade_version_to_avatar_conf \
		    /tmp/data/etc/version* \
		    /etc/avatar.conf \
		    /tmp/data/etc/avatar.conf
        fi
        install_worker.sh -D /tmp/data -m / pre-install
        umount /tmp/data
        rmdir /tmp/data
    fi

    # Run pc-sysinstall against the config generated

    # Hack #1
    export ROOTIMAGE=1
    # Hack #2
    ls $(get_product_path) > /dev/null
    /rescue/pc-sysinstall -c ${_config_file}
    if [ ${_do_upgrade} -eq 1 ]; then
        # Mount: /data
        mkdir -p /tmp/data
        mount /dev/${_disk}s4 /tmp/data
        ls /tmp/data > /dev/null
        cp -pR /tmp/data_preserved/ /tmp/data
        : > /tmp/$NEED_UPDATE_SENTINEL
        : > /tmp/$CD_UPGRADE_SENTINEL
        umount /tmp/data
        # Mount: /
        mount /dev/${_disk}s1a /tmp/data
        ls /tmp/data > /dev/null
        cp -p /tmp/hostid /tmp/data/conf/base/etc
        if [ -d /tmp/.ssh ]; then
            cp -pR /tmp/.ssh /tmp/data/root/
        fi
        if [ -d /tmp/modules ]; then
            for i in `ls /tmp/modules`
            do
                cp -p /tmp/modules/$i /tmp/data/boot/modules
            done
        fi
        if [ -d /tmp/fusionio ]; then
            cp -pR /tmp/fusionio /tmp/data/usr/local/
        fi
        umount /tmp/data
        rmdir /tmp/data
	dialog --msgbox "The installer has preserved your database file.
$AVATAR_PROJECT will migrate this file, if necessary, to the current format." 6 74
    fi

    # End critical section.
    set +e

    trap - EXIT
    dialog --msgbox "The $AVATAR_PROJECT $_action on ${_disk} succeeded!
Please remove the CDROM and reboot." 6 74

    return 0
}

menu_shell()
{
    /bin/sh
}

menu_reboot()
{
    echo "Rebooting..."
    reboot >/dev/null
}

menu_shutdown()
{
    echo "Halting and powering down..."
    halt -p >/dev/null
}

main()
{
    local _tmpfile="/tmp/answer"
    local _number

    while :; do

        dialog --clear --title "$AVATAR_PROJECT $AVATAR_VERSION Console Setup" --menu "" 12 73 6 \
            "1" "Install/Upgrade" \
            "2" "Shell" \
            "3" "Reboot System" \
            "4" "Shutdown System" \
            2> "${_tmpfile}"
        _number=`cat "${_tmpfile}"`
        case "${_number}" in
            1) menu_install ;;
            2) menu_shell ;;
            3) menu_reboot ;;
            4) menu_shutdown ;;
        esac
    done
}
main
