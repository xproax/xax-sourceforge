#!/bin/sh
# Script to create a new jail based on given flags
#####################################################################

# Source our functions
PROGDIR="/usr/local/share/warden"

# Source our variables
. ${PROGDIR}/scripts/backend/functions.sh

# Location of the chroot environment
isDirZFS "${JDIR}"
if [ $? -eq 0 ] ; then
  WORLDCHROOT="${JDIR}/.warden-chroot-${ARCH}"
  export WORLDCHROOT
else
  WORLDCHROOT="${JDIR}/.warden-chroot-${ARCH}.tbz"
  export WORLDCHROOT
fi

setup_linux_jail()
{
  echo "Setting up linux jail..."

  mkdir -p ${JMETADIR}
  echo "${HOST}" > ${JMETADIR}/host
  echo "${IP}" > ${JMETADIR}/ip
  if [ "$STARTUP" = "YES" ] ; then
    touch "${JMETADIR}/autostart"
  fi
  touch "${JMETADIR}/jail-linux"

  if [ -n "$LINUXARCHIVE_FILE" ] ; then
    echo "Extracting ${LINUXARCHIVE_FILE}..."
    tar xvf ${LINUXARCHIVE_FILE} -C "${JDIR}/${IP}" 2>/dev/null
    if [ $? -ne 0 ] ; then
       echo "Failed Extracting ${LINUXARCHIVE_FILE}"
       warden delete --confirm ${IP} 2>/dev/null
       exit 1
    fi
  else
    sh ${LINUX_JAIL_SCRIPT} "${JDIR}/${IP}" "${IP}" "${JMETADIR}"
    if [ $? -ne 0 ] ; then
       echo "Failed running ${LINUX_JAIL_SCRIPT}"
       warden delete --confirm ${IP} 2>/dev/null
       exit 1
    fi
  fi
  
  # Create the master.passwd
  echo "root::0:0::0:0:Charlie &:/root:/bin/bash" > ${JDIR}/${IP}/etc/master.passwd
  pwd_mkdb -d ${JDIR}/${IP}/tmp -p ${JDIR}/${IP}/etc/master.passwd 2>/dev/null
  mv ${JDIR}/${IP}/tmp/master.passwd ${JDIR}/${IP}/etc/
  mv ${JDIR}/${IP}/tmp/pwd.db ${JDIR}/${IP}/etc/
  mv ${JDIR}/${IP}/tmp/spwd.db ${JDIR}/${IP}/etc/
  rm ${JDIR}/${IP}/tmp/passwd

  # Copy resolv.conf
  cp /etc/resolv.conf ${JDIR}/${IP}/etc/resolv.conf

  # Do some touch-up to make linux happy
  echo '#!/bin/bash
cd /etc
pwconv
grpconv
touch /etc/fstab
touch /etc/mtab
' > ${JDIR}/${IP}/.fixSH
  chmod 755 ${JDIR}/${IP}/.fixSH
  chroot ${JDIR}/${IP} /.fixSH
  rm ${JDIR}/${IP}/.fixSH

  # If we are auto-starting the jail, do it now
  if [ "$STARTUP" = "YES" ] ; then warden start ${IP} ; fi

  echo "Success! Linux jail created at ${JDIR}/${IP}"
}

# Load our passed values
IP="${1}"
HOST="${2}"
SOURCE="${3}"
PORTS="${4}"
STARTUP="${5}"
PORTJAIL="${6}"
LINUXJAIL="${7}"
ARCHIVEFILE="${8}"

# See if we are overriding the default archive file
if [ ! -z "$ARCHIVEFILE" ] ; then
   WORLDCHROOT="$ARCHIVEFILE"
fi

if [ -z "$IP" -o -z "${HOST}" -o -z "$SOURCE" -o -z "${PORTS}" -o -z "${STARTUP}" ] 
then
  echo "ERROR: Missing required data!"
  exit 6
fi

JAILDIR="${JDIR}/${IP}"
set_warden_metadir

if [ -e "${JAILDIR}" ]
then
  echo "ERROR: This Jail directory already exists!"
  exit 5
fi

# Make sure we don't have a host already with this name
for i in `ls -d ${JDIR}/.*.meta 2>/dev/null`
do
  if [ ! -e "${i}/host" ] ; then continue ; fi
  if [ "`cat ${i}/host`" = "$HOST" ] ; then
    echo "ERROR: A jail with this hostname already exists!"
    exit 5
  fi
done

# Check if we need to download the chroot file
if [ ! -e "${WORLDCHROOT}" -a "${LINUXJAIL}" != "YES" ] ; then downloadchroot ; fi


# If we are setting up a linux jail, lets do it now
if [ "$LINUXJAIL" = "YES" ] ; then
   isDirZFS "${JDIR}"
   if [ $? -eq 0 ] ; then
     # Create ZFS mount
     tank=`getZFSTank "$JDIR"`
     zfs create -o mountpoint=${JAILDIR} -p ${tank}${JAILDIR}
   else
     mkdir -p "${JAILDIR}"
   fi
   setup_linux_jail
   exit 0
fi

echo "Building new Jail... Please wait..."

isDirZFS "${JDIR}"
if [ $? -eq 0 ] ; then
   # Create ZFS CLONE
   tank=`getZFSTank "$JDIR"`
   zfsp=`getZFSRelativePath "${WORLDCHROOT}"`
   jailp=`getZFSRelativePath "${JAILDIR}"`
   zfs clone ${tank}${zfsp}@clean ${tank}${jailp}
   if [ $? -ne 0 ] ; then exit_err "Failed creating clean ZFS base clone"; fi
else
   # Running on UFS
   mkdir -p "${JAILDIR}"
   echo "Installing world..."
   tar xvf ${WORLDCHROOT} -C "${JAILDIR}" 2>/dev/null
   echo "Done"
fi


mkdir ${JMETADIR}
echo "${HOST}" > ${JMETADIR}/host
echo "${IP}" > ${JMETADIR}/ip

if [ "$SOURCE" = "YES" ]
then
  echo "Installing source..."
  mkdir -p "${JAILDIR}/usr/src"
  if [ ! -e "/usr/src/COPYRIGHT" ] ; then
     echo "No system-sources on host.. You will need to manually download these in the jail."
  else
    tar cvf - -C /usr/src . 2>/dev/null | tar xvf - -C "${JAILDIR}/usr/src" 2>/dev/null
    echo "Done"
  fi
fi

if [ "$PORTS" = "YES" ]
then
  echo "Fetching ports..."
  mkdir -p "${JAILDIR}/usr/ports"
  cat /usr/sbin/portsnap | sed 's|! -t 0|-z '1'|g' | /bin/sh -s "fetch" "extract" "update" "-p" "${JAILDIR}/usr/ports" >/dev/null 2>/dev/null
  if [ $? -eq 0 ] ; then
    echo "Done"
  else
    echo "Failed! Please run \"portsnap fetch extract update\" within the jail."
  fi
fi

# Create an empty fstab
touch "${JDIR}/${IP}/etc/fstab"

# If this isn't a fresh jail, we can skip to not clobber existing setup
if [ -z "$ARCHIVEFILE" ] ; then
  # Setup rc.conf
  echo "portmap_enable=\"NO\"
sshd_enable=\"YES\"
sendmail_enable=\"NO\"
hostname=\"${HOST}\"
devfs_enable=\"YES\"
devfs_system_ruleset=\"devfsrules_common\"" > "${JDIR}/${IP}/etc/rc.conf"

  # Create the host for this device
  echo "# : src/etc/hosts,v 1.16 2003/01/28 21:29:23 dbaker Exp $
#
# Host Database
#
# This file should contain the addresses and aliases for local hosts that
# share this file.  Replace 'my.domain' below with the domainname of your
# machine.
#
# In the presence of the domain name service or NIS, this file may
# not be consulted at all; see /etc/nsswitch.conf for the resolution order.
#
#
::1                     localhost localhost.localdomain
127.0.0.1               localhost localhost.localdomain ${HOST}
${IP}			${HOST}" > "${JDIR}/${IP}/etc/hosts"

  # Copy resolv.conf
  cp /etc/resolv.conf "${JDIR}/${IP}/etc/resolv.conf"


  # Check if ipv6
  isV6 "${IP}"
  if [ $? -eq 0 ] ; then
    sed -i '' "s|#ListenAddress ::|ListenAddress ${IP}|g" ${JDIR}/${IP}/etc/ssh/sshd_config
  fi

fi # End of ARCHIVEFILE check

if [ "$STARTUP" = "YES" ] ; then
  touch "${JMETADIR}/autostart"
fi

# Check if we need to copy the timezone file
if [ -e "/etc/localtime" ] ; then
   cp /etc/localtime ${JDIR}/${IP}/etc/localtime
fi

# Set the default meta-pkg set
mkdir -p ${JDIR}/${IP}/usr/local/etc >/dev/null 2>/dev/null
echo "PCBSD_METAPKGSET: warden" > ${JDIR}/${IP}/usr/local/etc/pcbsd.conf

# Copy over the pbid scripts
checkpbiscripts "${JDIR}/${IP}"

# Check if making a portjail
if [ "$PORTJAIL" = "YES" ] ; then mkportjail "${JDIR}/${IP}" ; fi

# If we are auto-starting the jail, do it now
if [ "$STARTUP" = "YES" ] ; then warden start ${IP} ; fi

echo "Success!"
echo "Jail created at ${JDIR}/${IP}"

exit 0
