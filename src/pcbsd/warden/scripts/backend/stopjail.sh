#!/bin/sh 
# Script to stop a jail
# Args $1 = jail-name
#######################################################################

# Source our functions
PROGDIR="/usr/local/share/warden"

# Source our variables
. ${PROGDIR}/scripts/backend/functions.sh

JAILNAME="${1}"
if [ "${2}" = "FAST" ]
then
  FAST="Y"
fi

if [ -z "${JAILNAME}" ]
then
  echo "ERROR: No jail specified to delete!"
  exit 5
fi

if [ -z "${JDIR}" ]
then
  echo "ERROR: JDIR is unset!!!!"
  exit 5
fi

JAILDIR="${JDIR}/${JAILNAME}"

if [ ! -d "${JAILDIR}" ]
then
  echo "ERROR: No jail located at ${JAILDIR}"
  exit 5
fi


HOST="`cat ${JMETADIR}/host`"

# End of error checking, now shutdown this jail
##################################################################

echo -e "Stopping the jail...\c"

# Get the JailID for this jail
JID="`jls | grep ${JAILDIR}$ | tr -s " " | cut -d " " -f 2`"

echo -e ".\c"

# Check if we need umount x mnts
if [ -e "${JMETADIR}/jail-portjail" ] ; then umountjailxfs ${JAILNAME} ; fi

# Get list of IPs for this jail
IP=
if [ -e "${JMETADIR}/ip" ] ; then
   IP=`cat "${JMETADIR}/ip"`
fi

_epairb=`jexec ${JID} ifconfig -a | grep '^epair' | cut -f1 -d:`
if [ -n "${_epairb}" ] ; then
   _epaira=`echo ${_epairb} | sed -E 's|b$|a|'`
   _bridgeif=

   for _bridge in `ifconfig -a | grep -E '^bridge[0-9]+' | cut -f1 -d:`
   do
      for _member in `ifconfig ${_bridge} | grep member | awk '{ print $2 }'`
      do
         if [ "${_member}" = "${_epaira}" ] ; then
            _bridgeif="${_bridge}"
             break
         fi
      done
      if [ -n "${_bridgeif}" ] ; then
         break
      fi
   done

   jexec ${JID} ifconfig ${_epairb} down
   ifconfig ${_epaira} down
   ifconfig ${_epaira} destroy
   _count=`ifconfig ${_bridgeif} | grep member | awk '{ print $2 }' | wc -l`
   if [ "${_count}" -le "1" ] ; then
      ifconfig ${_bridgeif} destroy
   fi
fi

if [ -e "${JMETADIR}/jail-linux" ] ; then LINUXJAIL="YES" ; fi

if [ "$LINUXJAIL" = "YES" ] ; then
  # If we have a custom stop script
  if [ -e "${JMETADIR}/jail-stop" ] ; then
    sCmd=`cat ${JMETADIR}/jail-stop`
    echo "Stopping jail with: ${sCmd}"
    if [ -n "${JID}" ] ; then
      jexec ${JID} ${sCmd} 2>&1
    fi
  else
    # Check for different init styles
    if [ -e "${JAILDIR}/etc/init.d/rc" ] ; then
      if [ -n "${JID}" ] ; then
        jexec ${JID} /bin/sh /etc/init.d/rc 0 2>&1
      fi
    elif [ -e "${JAILDIR}/etc/rc" ] ; then
      if [ -n "${JID}" ] ; then
        jexec ${JID} /bin/sh /etc/rc 0 2>&1
      fi
    fi
  fi
  sleep 3

  umount -f ${JAILDIR}/sys 2>/dev/null
  umount -f ${JAILDIR}/dev/fd 2>/dev/null
  umount -f ${JAILDIR}/dev 2>/dev/null
  umount -f ${JAILDIR}/lib/init/rw 2>/dev/null
else
  # If we have a custom stop script
  if [ -e "${JMETADIR}/jail-stop" ] ; then
    if [ -n "${JID}" ] ; then
      sCmd=`cat ${JMETADIR}/jail-stop`
      echo "Stopping jail with: ${sCmd}"
      jexec ${JID} ${sCmd} 2>&1
    fi
  else
    if [ -n "${JID}" ] ; then
      echo "Stopping jail with: /etc/rc.shutdown"
      jexec ${JID} /bin/sh /etc/rc.shutdown >/dev/null 2>/dev/null
    fi
  fi
fi

umount -f ${JAILDIR}/dev >/dev/null 2>/dev/null

echo -e ".\c"

# Skip the time consuming portion if we are shutting down
if [ "$FAST" != "Y" ]
then

# We asked nicely, so now kill the jail for sure
killall -j ${JID} -TERM 2>/dev/null
sleep 1
killall -j ${JID} -KILL 2>/dev/null

echo -e ".\c"

# Check if we need to unmount the devfs in jail
mount | grep "${JAILDIR}/dev" >/dev/null 2>/dev/null
if [ "$?" = "0" ]
then
  # Setup a 60 second timer to try and umount devfs, since takes a bit
  SEC="0"
  while
   i=1
  do
   sleep 2

   # Try to unmount dev
   umount -f "${JAILDIR}/dev" 2>/dev/null
   if [ "$?" = "0" ]
   then
      break
   fi

   SEC="`expr $SEC + 2`"
   echo -e ".\c"

   if [ ${SEC} -gt 60 ]
   then
      break
   fi

  done
fi

# Check if we need to unmount any extra dirs
mount | grep "${JAILDIR}/proc" >/dev/null 2>/dev/null
if [ "$?" = "0" ]; then
  umount -f "${JAILDIR}/proc"
fi

if [ -e "${JMETADIR}/jail-portjail" ] ; then
  umountjailxfs
fi

fi # End of FAST check

echo -e ".\c"

if [ -n "${JID}" ] ; then
  jail -r ${JID}
fi

echo -e "Done"
