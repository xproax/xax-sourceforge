#!/usr/bin/env python
#-
# Copyright (c) 2010-2011 iXsystems, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#

""" Helper for FreeNAS to execute command line tools

This helper class abstracts operating system operations like starting,
stopping, restarting services out from the normal Django stuff and makes
future extensions/changes to the command system easier.  When used as a
command line utility, this helper class can also be used to do these
actions.
"""

from collections import OrderedDict
import ctypes
import errno
import glob
import grp
import logging
import os
import platform
import pwd
import re
import select
import shlex
import shutil
import signal
import sqlite3
import stat
from subprocess import Popen, PIPE
import subprocess
import sys
import syslog
import tempfile
import threading
import time
import types

WWW_PATH = "/usr/local/www"
FREENAS_PATH = os.path.join(WWW_PATH, "freenasUI")
NEED_UPDATE_SENTINEL = '/data/need-update'
VERSION_FILE = '/etc/version'

sys.path.append(WWW_PATH)
sys.path.append(FREENAS_PATH)

os.environ["DJANGO_SETTINGS_MODULE"] = "freenasUI.settings"

from django.db import models
from django.db.models import Q

from freenasUI.common.acl import ACL_FLAGS_OS_WINDOWS, ACL_WINDOWS_FILE
from freenasUI.common.freenasacl import ACL, ACL_Hierarchy
from freenasUI.common.locks import mntlock
from freenasUI.common.pbi import pbi_add, pbi_delete, \
    PBI_ADD_FLAGS_NOCHECKSIG, PBI_ADD_FLAGS_INFO, \
    PBI_ADD_FLAGS_EXTRACT_ONLY, PBI_ADD_FLAGS_OUTDIR, \
    PBI_ADD_FLAGS_FORCE
from freenasUI.common.jail import Jls, Jexec
from freenasUI.common.system import get_mounted_filesystems, umount
from middleware import zfs
from freenasUI.middleware.exceptions import MiddlewareError

log = logging.getLogger('middleware.notifier')


class StartNotify(threading.Thread):
    """
    Use kqueue to watch for an event before actually calling start/stop
    This should help against synchronization issues under VM

    If the given pid file exists attach on it, otherwise use the parent folder
    """

    def __init__(self, pidfile, *args, **kwargs):
        self._pidfile = pidfile
        super(StartNotify, self).__init__(*args, **kwargs)

    def run(self):

        if not self._pidfile:
            return None

        if os.path.exists(self._pidfile):
            _file = self._pidfile
        else:
            _file = os.path.dirname(self._pidfile)
        fd = os.open(_file, os.O_RDONLY)
        evts = [
            select.kevent(fd,
                filter=select.KQ_FILTER_VNODE,
                flags=select.KQ_EV_ADD|select.KQ_EV_ONESHOT,
                fflags=select.KQ_NOTE_WRITE|select.KQ_NOTE_EXTEND|select.KQ_NOTE_DELETE),
            ]
        kq = select.kqueue()
        ev = kq.control(evts, 1, 3)


class notifier:
    from os import system as ___system
    from pwd import getpwnam as ___getpwnam
    IDENTIFIER = 'notifier'
    def __system(self, command):
        log.debug("Executing: %s", command)
        # TODO: python's signal class should be taught about sigprocmask(2)
        # This is hacky hack to work around this issue.
        libc = ctypes.cdll.LoadLibrary("libc.so.7")
        omask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        mask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        pmask = ctypes.pointer(mask)
        pomask = ctypes.pointer(omask)
        libc.sigprocmask(signal.SIGQUIT, pmask, pomask)
        try:
            self.___system("(" + command + ") 2>&1 | logger -p daemon.notice -t %s"
                           % (self.IDENTIFIER, ))
        finally:
            libc.sigprocmask(signal.SIGQUIT, pomask, None)
        log.debug("Executed: %s", command)

    def __system_nolog(self, command):
        log.debug("Executing: %s", command)
        # TODO: python's signal class should be taught about sigprocmask(2)
        # This is hacky hack to work around this issue.
        libc = ctypes.cdll.LoadLibrary("libc.so.7")
        omask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        mask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        pmask = ctypes.pointer(mask)
        pomask = ctypes.pointer(omask)
        libc.sigprocmask(signal.SIGQUIT, pmask, pomask)
        try:
            retval = self.___system("(" + command + ") >/dev/null 2>&1")
        finally:
            libc.sigprocmask(signal.SIGQUIT, pomask, None)
        retval >>= 8
        log.debug("Executed: %s; returned %d", command, retval)
        return retval

    def __pipeopen(self, command):
        log.debug("Popen()ing: %s", command)
        return Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True, close_fds=True)

    def _do_nada(self):
        pass

    def _simplecmd(self, action, what):
        log.debug("Calling: %s(%s) ", action, what)
        f = getattr(self, '_' + action + '_' + what, None)
        if f is None:
            # Provide generic start/stop/restart verbs for rc.d scripts
            if action in ("start", "stop", "restart", "reload"):
                if action == 'restart':
                    self.__system("/usr/sbin/service " + what + " forcestop ")
                self.__system("/usr/sbin/service " + what + " " + action)
                f = self._do_nada
            else:
                raise ValueError("Internal error: Unknown command")
        f()


    __service2daemon = {
            'ssh': ('sshd', '/var/run/sshd.pid'),
            'rsync': ('rsync', '/var/run/rsyncd.pid'),
            'nfs': ('nfsd', None),
            'afp': ('afpd', None),
            'cifs': ('smbd', '/var/run/samba/smbd.pid'),
            'dynamicdns': ('inadyn', None),
            'snmp': ('bsnmpd', '/var/run/snmpd.pid'),
            'ftp': ('proftpd', '/var/run/proftpd.pid'),
            'tftp': ('inetd', '/var/run/inetd.pid'),
            'iscsitarget': ('istgt', '/var/run/istgt.pid'),
            'ups': ('upsd', '/var/db/nut/upsd.pid'),
            'smartd': ('smartd', '/var/run/smartd.pid'),
            'webshell': (None, '/var/run/webshell.pid'),
        }

    def _started_notify(self, what):
        """
        The check for started [or not] processes is currently done in 2 steps
        This is the first step which involves a thread StartNotify that watch for event
        before actually start/stop rc.d scripts

        Returns:
            StartNotify object if the service is known or None otherwise
        """

        if what in self.__service2daemon:
            procname, pidfile = self.__service2daemon[what]
            sn = StartNotify(pidfile=pidfile)
            sn.start()
            return sn
        else:
            return None

    def _started(self, what, notify=None):
        """
        This is the second step::
        Wait for the StartNotify thread to finish and then check for the
        status of pidfile/procname using pgrep

        Returns:
            True whether the service is alive, False otherwise
        """

        if what in self.__service2daemon:
            procname, pidfile = self.__service2daemon[what]
            if notify:
                notify.join()

            if pidfile:
                procname = " " + procname if procname else ""
                retval = self.__pipeopen("/bin/pgrep -F %s%s" % (pidfile, procname)).wait()
            else:
                retval = self.__pipeopen("/bin/pgrep %s" % (procname,)).wait()

            if retval == 0:
                return True
            else:
                return False
        else:
            return False

    def init(self, what, objectid = None, *args, **kwargs):
        """ Dedicated command to create "what" designated by an optional objectid.

        The helper will use method self._init_[what]() to create the object"""
        if objectid == None:
            self._simplecmd("init", what)
        else:
            f = getattr(self, '_init_' + what)
            f(objectid, *args, **kwargs)

    def destroy(self, what, objectid = None):
        if objectid == None:
            raise ValueError("Calling destroy without id")
        else:
            f = getattr(self, '_destroy_' + what)
            f(objectid)

    def start(self, what):
        """ Start the service specified by "what".

        The helper will use method self._start_[what]() to start the service.
        If the method does not exist, it would fallback using service(8)."""
        sn = self._started_notify(what)
        self._simplecmd("start", what)
        return self.started(what, sn)

    def started(self, what, sn=None):
        """ Test if service specified by "what" has been started. """
        try:
            f = getattr(self, '_started_' + what)
            return f()
        except:
            return self._started(what, sn)

    def stop(self, what):
        """ Stop the service specified by "what".

        The helper will use method self._stop_[what]() to stop the service.
        If the method does not exist, it would fallback using service(8)."""
        sn = self._started_notify(what)
        self._simplecmd("stop", what)
        return self.started(what, sn)

    def restart(self, what):
        """ Restart the service specified by "what".

        The helper will use method self._restart_[what]() to restart the service.
        If the method does not exist, it would fallback using service(8)."""
        sn = self._started_notify(what)
        self._simplecmd("restart", what)
        return self.started(what, sn)

    def reload(self, what):
        """ Reload the service specified by "what".

        The helper will use method self._reload_[what]() to reload the service.
        If the method does not exist, the helper will try self.restart of the
        service instead."""
        try:
            self._simplecmd("reload", what)
        except:
            self.restart(what)
        return self.started(what)

    def change(self, what):
        """ Notify the service specified by "what" about a change.

        The helper will use method self.reload(what) to reload the service.
        If the method does not exist, the helper will try self.start the
        service instead."""
        try:
            self.reload(what)
        except:
            self.start(what)

    def _start_webshell(self):
        self.__system_nolog("/usr/local/bin/python /usr/local/www/freenasUI/tools/webshell.py")

    def _restart_webshell(self):
        try:
            with open('/var/run/webshell.pid', 'r') as f:
                pid = f.read()
                os.kill(int(pid), signal.SIGHUP)
                time.sleep(0.2)
        except:
            pass
        self.__system_nolog("/usr/local/bin/python /usr/local/www/freenasUI/tools/webshell.py")

    def _restart_iscsitarget(self):
        self.__system("/usr/sbin/service ix-istgt quietstart")
        self.__system("/usr/sbin/service istgt forcestop")
        self.__system("/usr/sbin/service istgt restart")

    def _restart_collectd(self):
        self.__system("/usr/sbin/service ix-collectd quietstart")
        self.__system("/usr/sbin/service collectd restart")

    def _start_iscsitarget(self):
        self.__system("/usr/sbin/service ix-istgt quietstart")
        self.__system("/usr/sbin/service istgt restart")

    def _stop_iscsitarget(self):
        self.__system("/usr/sbin/service istgt forcestop")

    def _reload_iscsitarget(self):
        self.__system("/usr/sbin/service ix-istgt quietstart")
        self.__system("/usr/sbin/service istgt reload")

    def _start_sysctl(self):
        self.__system("/usr/sbin/service sysctl start")
        self.__system("/usr/sbin/service ix-sysctl quietstart")

    def _reload_sysctl(self):
        self.__system("/usr/sbin/service sysctl start")
        self.__system("/usr/sbin/service ix-sysctl reload")

    def _start_network(self):
        c = self.__open_db()
        c.execute("SELECT COUNT(n.id) FROM network_interfaces n LEFT JOIN network_alias a ON a.alias_interface_id=n.id WHERE int_ipv6auto = 1 OR int_ipv6address != '' OR alias_v6address != ''")
        ipv6_interfaces = c.fetchone()[0]
        if ipv6_interfaces > 0:
            try:
                auto_linklocal = self.sysctl("net.inet6.ip6.auto_linklocal", _type='INT')
            except AssertionError:
                auto_linklocal = 0
            if auto_linklocal == 0:
                self.__system("/sbin/sysctl net.inet6.ip6.auto_linklocal=1")
                self.__system("/usr/sbin/service autolink auto_linklocal quietstart")
                self.__system("/usr/sbin/service netif stop")
        self.__system("/etc/netstart")

    def ifconfig_alias(self, iface, oldip=None, newip=None, oldnetmask=None, newnetmask=None):
        if not iface:
            return False

        cmd = "/sbin/ifconfig %s" % iface
        if newip and newnetmask:
            cmd += " alias %s/%s" % (newip, newnetmask) 

        elif newip:
            cmd += " alias %s" % newip

        else:
            cmd = None

        if cmd:
            p = self.__pipeopen(cmd)
            if p.wait() != 0:
                return False

        cmd = "/sbin/ifconfig %s" % iface
        if newip:
            cmd += " -alias %s" % oldip
            p = self.__pipeopen(cmd)
            if p.wait() != 0:
                return False

        if newnetmask and not newip:
            cmd += " alias %s/%s" % (oldip, newnetmask)

        else:
            cmd = None
        
        if cmd:
            p = self.__pipeopen(cmd)
            if p.wait() != 0:
                return False

        return True

    def _reload_named(self):
        self.__system("/usr/sbin/service named reload")

    def _reload_networkgeneral(self):
        self.__system('/bin/hostname ""')
        self.__system("/usr/sbin/service ix-hostname quietstart")
        self.__system("/usr/sbin/service hostname quietstart")
        self.__system("/usr/sbin/service routing restart")

    def _reload_timeservices(self):
        self.__system("/usr/sbin/service ix-localtime quietstart")
        self.__system("/usr/sbin/service ix-ntpd quietstart")
        self.__system("/usr/sbin/service ntpd restart")
        c = self.__open_db()
        c.execute("SELECT stg_timezone FROM system_settings ORDER BY -id LIMIT 1")
        os.environ['TZ'] = c.fetchone()[0]
        time.tzset()

    def _reload_ssh(self):
        self.__system("/usr/sbin/service ix-sshd quietstart")
        self.__system("/usr/sbin/service sshd restart")

    def _restart_smartd(self):
        self.__system("/usr/sbin/service ix-smartd quietstart")
        self.__system("/usr/sbin/service smartd restart")

    def _restart_ssh(self):
        self.__system("/usr/sbin/service ix-sshd quietstart")
        self.__system("/usr/sbin/service sshd restart")

    def _reload_rsync(self):
        self.__system("/usr/sbin/service ix-rsyncd quietstart")
        self.__system("/usr/sbin/service rsyncd restart")

    def _restart_rsync(self):
        self.__system("/usr/sbin/service ix-rsyncd quietstart")
        self.__system("/usr/sbin/service rsyncd restart")

    def _start_ldap(self):
        self.__system("/usr/sbin/service ix-ldap quietstart")
        self.___system("(/usr/sbin/service ix-cache quietstart) &")
        self.__system("/usr/sbin/service ix-nsswitch quietstart")
        self.__system("/usr/sbin/service ix-pam quietstart")
        self.__system("/usr/sbin/service ix-samba quietstart")
        self.__system("/usr/sbin/service samba forcestop")
        self.__system("/usr/bin/killall nmbd")
        self.__system("/usr/bin/killall smbd")
        self.__system("/usr/bin/killall winbindd")
        self.__system("/bin/sleep 5")
        self.__system("/usr/sbin/service samba quietstart")

        if (self.__system_nolog('/usr/sbin/service ix-ldap status') != 0):
            return False

        return True

    def _started_ldap(self):
        from freenasUI.common.freenasldap import FreeNAS_LDAP, LDAPEnabled, FLAGS_DBINIT

        ret = False
        if LDAPEnabled():
            f = FreeNAS_LDAP(flags=FLAGS_DBINIT)
            f.open()
            if f.isOpen():
                ret = True
            else:
                ret = False
            f.close()

        return ret

    def _stop_ldap(self):
        self.__system("/usr/sbin/service ix-ldap quietstart")
        self.___system("(/usr/sbin/service ix-cache quietstop) &")
        self.__system("/usr/sbin/service ix-nsswitch quietstart")
        self.__system("/usr/sbin/service ix-pam quietstart")
        self.__system("/usr/sbin/service ix-samba quietstart")
        self.__system("/usr/sbin/service samba forcestop")
        self.__system("/usr/bin/killall nmbd")
        self.__system("/usr/bin/killall smbd")
        self.__system("/usr/bin/killall winbindd")
        self.__system("/bin/sleep 5")
        self.__system("/usr/sbin/service samba quietstart")
        return False

    def _restart_ldap(self):
        self._stop_ldap()
        self._start_ldap()

    def _started_activedirectory(self):
        from freenasUI.common.freenasldap import FreeNAS_ActiveDirectory, ActiveDirectoryEnabled, FLAGS_DBINIT

        for srv in ('kinit', 'activedirectory', ):
            if (self.__system_nolog('/usr/sbin/service ix-%s status' % (srv, ))
                != 0):
                return False

        ret = False
        if ActiveDirectoryEnabled():
            f = FreeNAS_ActiveDirectory(flags=FLAGS_DBINIT)
            f.open()
            if f.isOpen():
                ret = True
            else:
                ret = False
            f.close()

        return ret

    def _start_activedirectory(self):
        self.__system("/usr/sbin/service ix-kerberos quietstart")
        self.__system("/usr/sbin/service ix-nsswitch quietstart")
        self.__system("/usr/sbin/service ix-pam quietstart")
        self.__system("/usr/sbin/service ix-samba quietstart")
        self.__system("/usr/sbin/service ix-kinit quietstart")
        if self.__system_nolog('/usr/sbin/service ix-kinit status') != 0:
            # XXX: Exceptions don't work here on all versions, e.g. 8.0.2.
            #raise Exception('Failed to get a kerberos ticket.')
            return False
        if self.__system_nolog("/usr/sbin/service ix-activedirectory quietstart") != 0:
            return False
        if (self.__system_nolog('/usr/sbin/service ix-activedirectory status')
            != 0):
            # XXX: Exceptions don't work here on all versions, e.g. 8.0.2.
            #raise Exception('Failed to associate with the domain.')
            return False
        self.___system("(/usr/sbin/service ix-cache quietstart) &")
        self.__system("/usr/sbin/service winbindd quietstart")
        return True

    def _stop_activedirectory(self):
        self.__system("/usr/sbin/service ix-kerberos quietstart")
        self.__system("/usr/sbin/service ix-nsswitch quietstart")
        self.__system("/usr/sbin/service ix-pam quietstart")
        self.__system("/usr/sbin/service ix-samba quietstart")
        self.__system("/usr/sbin/service ix-kinit forcestop")
        self.__system("/usr/sbin/service ix-activedirectory forcestop")
        self.___system("(/usr/sbin/service ix-cache quietstop) &")
        self.__system("/usr/sbin/service winbindd forcestop")
        return False

    def _restart_activedirectory(self):
        self._stop_activedirectory()
        self._start_activedirectory()

    def _restart_syslogd(self):
        self.__system("/usr/sbin/service ix-syslogd quietstart")
        self.__system("/usr/sbin/service syslogd restart")

    def _start_syslogd(self):
        self.__system("/usr/sbin/service ix-syslogd quietstart")
        self.__system("/usr/sbin/service syslogd start")

    def _reload_tftp(self):
        self.__system("/usr/sbin/service ix-inetd quietstart")
        self.__system("/usr/sbin/service inetd forcestop")
        self.__system("/usr/sbin/service inetd restart")

    def _restart_tftp(self):
        self.__system("/usr/sbin/service ix-inetd quietstart")
        self.__system("/usr/sbin/service inetd forcestop")
        self.__system("/usr/sbin/service inetd restart")

    def _restart_cron(self):
        self.__system("/usr/sbin/service ix-crontab quietstart")
        self.__system("/usr/sbin/service cron restart")

    def _start_motd(self):
        self.__system("/usr/sbin/service ix-motd quietstart")
        self.__system("/usr/sbin/service motd quietstart")

    def _start_ttys(self):
        self.__system("/usr/sbin/service ix-ttys quietstart")

    def _reload_ftp(self):
        self.__system("/usr/sbin/service ix-proftpd quietstart")
        self.__system("/usr/sbin/service proftpd restart")

    def _restart_ftp(self):
        self.__system("/usr/sbin/service ix-proftpd quietstart")
        self.__system("/usr/sbin/service proftpd forcestop")
        self.__system("/usr/sbin/service proftpd restart")
        self.__system("sleep 1")

    def _start_ftp(self):
        self.__system("/usr/sbin/service ix-proftpd quietstart")
        self.__system("/usr/sbin/service proftpd start")

    def _start_ups(self):
        self.__system("/usr/sbin/service ix-ups quietstart")
        self.__system("/usr/sbin/service nut start")
        self.__system("/usr/sbin/service nut_upsmon start")
        self.__system("/usr/sbin/service nut_upslog start")

    def _stop_ups(self):
        self.__system("/usr/sbin/service nut_upslog forcestop")
        self.__system("/usr/sbin/service nut_upsmon forcestop")
        self.__system("/usr/sbin/service nut forcestop")

    def _restart_ups(self):
        self.__system("/usr/sbin/service ix-ups quietstart")
        self.__system("/usr/sbin/service nut restart")
        self.__system("/usr/sbin/service nut_upsmon restart")
        self.__system("/usr/sbin/service nut_upslog restart")

    def _load_afp(self):
        self.__system("/usr/sbin/service ix-afpd quietstart")
        self.__system("/usr/sbin/service dbus quietstart")
        self.__system("/usr/sbin/service avahi-daemon quietstart")
        self.__system("/usr/sbin/service netatalk quietstart")

    def _start_afp(self):
        self.__system("/usr/sbin/service ix-afpd start")
        self.__system("/usr/sbin/service dbus start")
        self.__system("/usr/sbin/service avahi-daemon start")
        self.__system("/usr/sbin/service netatalk start")

    def _stop_afp(self):
        # XXX: fix rc.d/netatalk to honor the force verbs properly.
        self.__system("killall afpd")
        self.__system("/usr/sbin/service avahi-daemon forcestop")
        self.__system("/usr/sbin/service dbus forcestop")

    def _restart_afp(self):
        self._stop_afp()
        self._start_afp()

    def _reload_afp(self):
        self.__system("/usr/sbin/service ix-afpd quietstart")
        self.__system("killall -1 avahi-daemon")
        self.__system("killall -1 afpd")

    def _reload_nfs(self):
        self.__system("/usr/sbin/service ix-nfsd quietstart")
        self.__system("/usr/sbin/service mountd reload")

    def _restart_nfs(self):
        self.__system("/usr/sbin/service lockd forcestop")
        self.__system("/usr/sbin/service statd forcestop")
        self.__system("/usr/sbin/service mountd forcestop")
        self.__system("/usr/sbin/service nfsd forcestop")
        self.__system("/usr/sbin/service ix-nfsd quietstart")
        self.__system("/usr/sbin/service mountd quietstart")
        self.__system("/usr/sbin/service nfsd quietstart")
        self.__system("/usr/sbin/service statd quietstart")
        self.__system("/usr/sbin/service lockd quietstart")

    def _stop_nfs(self):
        self.__system("/usr/sbin/service lockd forcestop")
        self.__system("/usr/sbin/service statd forcestop")
        self.__system("/usr/sbin/service mountd forcestop")
        self.__system("/usr/sbin/service nfsd forcestop")

    def _start_nfs(self):
        self.__system("/usr/sbin/service ix-nfsd quietstart")
        self.__system("/usr/sbin/service mountd quietstart")
        self.__system("/usr/sbin/service nfsd quietstart")
        self.__system("/usr/sbin/service statd quietstart")
        self.__system("/usr/sbin/service lockd quietstart")

    def _start_plugins_jail(self):
        self.__system("/usr/sbin/service ix-jail quietstart")
        self.__system_nolog("/usr/sbin/service ix-plugins start")

    def _stop_plugins_jail(self):
        self.__system_nolog("/usr/sbin/service ix-plugins forcestop")
        self.__system("/usr/sbin/service ix-jail forcestop")

    def _force_stop_jail(self):
        self.__system("/usr/sbin/service jail forcestop")

    def _restart_plugins_jail(self):
        self._stop_plugins_jail()
        self._start_plugins_jail()
    
    def _started_plugins_jail(self):
        c = self.__open_db()
        c.execute("SELECT jail_name FROM services_pluginsjail ORDER BY -id LIMIT 1")
        jail_name = c.fetchone()[0]

        retval = 1
        idfile = "/var/run/jail_%s.id" % jail_name
        if os.access(idfile, os.F_OK):
            jail_id = int(open(idfile).read().strip())
            retval = self.__system_nolog("jls -j %d" % jail_id)

        if retval == 0:
            return True
        else:
            return False

    def _start_plugins(self, plugin=None):
        if plugin is not None:
            self.__system_nolog("/usr/sbin/service ix-plugins forcestart %s" % plugin)
        else:
            self.__system_nolog("/usr/sbin/service ix-plugins forcestart")

    def _stop_plugins(self, plugin=None):
        if plugin is not None:
            self.__system_nolog("/usr/sbin/service ix-plugins forcestop %s" % plugin)
        else:
            self.__system_nolog("/usr/sbin/service ix-plugins forcestop")

    def _restart_plugins(self, plugin=None):
        self._stop_plugins(plugin)
        self._start_plugins(plugin)

    def _started_plugins(self, plugin=None):
        res = False
        if plugin is not None:
            if self.__system_nolog("/usr/sbin/service ix-plugins status %s" % plugin) == 0:
                res = True 
        else: 
            if self.__system_nolog("/usr/sbin/service ix-plugins status") == 0:
                res = True 
        return res

    def plugins_jail_configured(self):
        res = False
        c = self.__open_db()
        c.execute("SELECT count(*) from services_pluginsjail")
        if int(c.fetchone()[0]) > 0:
            c.execute("""
            SELECT
                jail_path,
                jail_name,
                jail_ip_id,
                plugins_path
            FROM
                services_pluginsjail
            ORDER BY
                -id
            LIMIT 1
            """)
            sp = c.fetchone()
            for i in sp:
                if i not in (None, ''):
                    res = True
                    break
        return res

    def start_ssl(self, what=None):
        if what is not None:
            self.__system("/usr/sbin/service ix-ssl quietstart %s" % what)
        else:
            self.__system("/usr/sbin/service ix-ssl quietstart")

    def _restart_dynamicdns(self):
        self.__system("/usr/sbin/service ix-inadyn quietstart")
        self.__system("/usr/sbin/service inadyn restart")

    def _restart_system(self):
        self.__system("/bin/sleep 3 && /sbin/shutdown -r now &")

    def _stop_system(self):
        self.__system("/sbin/shutdown -p now")

    def _reload_cifs(self):
        self.__system("/usr/sbin/service ix-samba quietstart")
        self.__system("killall -1 avahi-daemon")
        self.__system("/usr/sbin/service samba forcereload")

    def _restart_cifs(self):
        self.__system("/usr/sbin/service dbus forcestop")
        self.__system("/usr/sbin/service dbus restart")
        self.__system("/usr/sbin/service avahi-daemon forcestop")
        self.__system("/usr/sbin/service avahi-daemon restart")
        self.__system("/usr/sbin/service smbd forcestop")
        self.__system("/usr/sbin/service nmbd forcestop")
        self.__system("/usr/sbin/service smbd quietrestart")
        self.__system("/usr/sbin/service nmbd quietrestart")

    def _start_cifs(self):
        self.__system("/usr/sbin/service dbus quietstart")
        self.__system("/usr/sbin/service avahi-daemon quietstart")
        self.__system("/usr/sbin/service smbd quietstart")
        self.__system("/usr/sbin/service nmbd quietstart")

    def _stop_cifs(self):
        self.__system("/usr/sbin/service dbus forcestop")
        self.__system("/usr/sbin/service dbus restart")
        self.__system("/usr/sbin/service avahi-daemon forcestop")
        self.__system("/usr/sbin/service avahi-daemon restart")
        self.__system("/usr/sbin/service smbd forcestop")
        self.__system("/usr/sbin/service nmbd forcestop")

    def _restart_snmp(self):
        self.__system("/usr/sbin/service ix-bsnmpd quietstart")
        self.__system("/usr/sbin/service bsnmpd forcestop")
        self.__system("/usr/sbin/service bsnmpd quietstart")

    def _restart_http(self):
        self.__system("/usr/sbin/service ix-nginx quietstart")
        self.__system("/usr/sbin/service nginx restart")

    def _reload_http(self):
        self.__system("/usr/sbin/service ix-nginx reload")

    def _reload_loader(self):
        self.__system("/usr/sbin/service ix-loader reload")

    def _start_loader(self):
        self.__system("/usr/sbin/service ix-loader quietstart")

    def __saver_loaded(self):
        pipe = os.popen("kldstat|grep daemon_saver")
        out = pipe.read().strip('\n')
        pipe.close()
        return (len(out) > 0)

    def _start_saver(self):
        if not self.__saver_loaded():
            self.__system("kldload daemon_saver")

    def _stop_saver(self):
        if self.__saver_loaded():
            self.__system("kldunload daemon_saver")

    def _restart_saver(self):
        self._stop_saver()
        self._start_saver()

    def __open_db(self, ret_conn=False):
        """Open and return a cursor object for database access."""
        try:
            from freenasUI.settings import DATABASES
            dbname = DATABASES['default']['NAME']
        except:
            dbname = '/data/freenas-v1.db'

        conn = sqlite3.connect(dbname)
        c = conn.cursor()
        if ret_conn:
            return c, conn
        return c

    def __gpt_labeldisk(self, type, devname, test4k=False, swapsize=2):
        """Label the whole disk with GPT under the desired label and type"""
        if test4k:
            # Taste the disk to know whether it's 4K formatted.
            # requires > 8.1-STABLE after r213467
            ret_4kstripe = self.__system_nolog("geom disk list %s "
                                               "| grep 'Stripesize: 4096'" % (devname))
            ret_512bsector = self.__system_nolog("geom disk list %s "
                                                 "| grep 'Sectorsize: 512'" % (devname))
            # Make sure that the partition is 4k-aligned, if the disk reports 512byte sector
            # while using 4k stripe, use an offset of 64.
            need4khack = (ret_4kstripe == 0) and (ret_512bsector == 0)
        else:
            need4khack = False

        # Calculate swap size.
        swapgb = swapsize
        swapsize = swapsize * 1024 * 1024 * 2
        # Round up to nearest whole integral multiple of 128 and subtract by 34
        # so next partition starts at mutiple of 128.
        swapsize = ((swapsize+127)/128)*128
        # To be safe, wipe out the disk, both ends... before we start
        self.__system("dd if=/dev/zero of=/dev/%s bs=1m count=1" % (devname))
        try:
            p1 = self.__pipeopen("diskinfo %s" % devname)
            size = int(re.sub(r'\s+', ' ', p1.communicate()[0]).split()[2]) / (1024)
        except:
            pass
        else:
            if size*2 < swapsize:
                raise MiddlewareError('Your disk size must be higher than %dGB' % swapgb)
            # HACK: force the wipe at the end of the disk to always succeed. This
            # is a lame workaround.
            self.__system("dd if=/dev/zero of=/dev/%s bs=1m oseek=%s" % (devname, size*1024 - 4))

        commands = []
        commands.append("gpart create -s gpt /dev/%s" % (devname))
        if swapsize > 0:
            commands.append("gpart add -b 128 -t freebsd-swap -s %d %s" % (swapsize, devname))
            commands.append("gpart add -t %s %s" % (type, devname))
        else:
            commands.append("gpart add -b 128 -t %s %s" % (type, devname))

        # Install a dummy boot block so system gives meaningful message if booting
        # from the wrong disk.
        commands.append("gpart bootcode -b /boot/pmbr-datadisk /dev/%s" % (devname))

        for command in commands:
            proc = self.__pipeopen(command)
            proc.wait()
            if proc.returncode != 0:
                raise MiddlewareError('Unable to GPT format the disk "%s"' % devname)

        # We might need to sync with reality (e.g. devname -> uuid)
        # Invalidating confxml is required or changes wont be seen
        self.__confxml = None
        self.sync_disk(devname)

        return need4khack

    def __gpt_unlabeldisk(self, devname):
        """Unlabel the disk"""
        swapdev = self.part_type_from_device('swap', devname)
        if swapdev != '':
            self.__system("swapoff /dev/%s" % self.part_type_from_device('swap', devname))
        self.__system("gpart destroy -F /dev/%s" % devname)

        # Wipe out the partition table by doing an additional iterate of create/destroy
        self.__system("gpart create -s gpt /dev/%s" % devname)
        self.__system("gpart destroy -F /dev/%s" % devname)

        # We might need to sync with reality (e.g. uuid -> devname)
        # Invalidating confxml is required or changes wont be seen
        self.__confxml = None
        self.sync_disk(devname)

    def unlabel_disk(self, devname):
        # TODO: Check for existing GPT or MBR, swap, before blindly call __gpt_unlabeldisk
        self.__gpt_unlabeldisk(devname)

    def __prepare_zfs_vdev(self, disks, swapsize, force4khack):
        vdevs = ['']
        gnop_devs = []
        if force4khack == None:
            test4k = False
            want4khack = False
        else:
            test4k = not force4khack
            want4khack = force4khack
        first = True
        for disk in disks:
            rv = self.__gpt_labeldisk(type = "freebsd-zfs",
                                      devname = disk,
                                      test4k = (first and test4k),
                                      swapsize=swapsize)
            first = False
            if test4k:
                test4k = False
                want4khack = rv

        for disk in disks:

            devname = self.part_type_from_device('zfs', disk)
            if want4khack:
                self.__system("gnop create -S 4096 /dev/%s" % devname)
                devname = '/dev/%s.nop' % devname
                gnop_devs.append(devname)
            else:
                devname = "/dev/%s" % devname
            vdevs.append(devname)

        return vdevs, gnop_devs, want4khack

    def __create_zfs_volume(self, volume, swapsize, groups, force4khack=False, path=None):
        """Internal procedure to create a ZFS volume identified by volume id"""
        z_id = volume.id
        z_name = str(volume.vol_name)
        z_vdev = ""
        need4khack = False
        # Grab all disk groups' id matching the volume ID
        self.__system("swapoff -a")
        gnop_devs = []

        want4khack = force4khack

        for name, vgrp in groups.items():
            vgrp_type = vgrp['type']
            if vgrp_type != 'stripe':
                z_vdev += " " + vgrp_type
            if vgrp_type in ('cache', 'log'):
                vdev_swapsize = 0
            else:
                vdev_swapsize = swapsize
            # Prepare disks nominated in this group
            vdevs, gnops, want4khack = self.__prepare_zfs_vdev(vgrp['disks'], vdev_swapsize, want4khack)
            z_vdev += " ".join(vdevs)
            gnop_devs += gnops

        # Finally, create the zpool.
        # TODO: disallowing cachefile may cause problem if there is
        # preexisting zpool having the exact same name.
        if not os.path.isdir("/data/zfs"):
            os.makedirs("/data/zfs")

        altroot = 'none' if path else '/mnt'
        mountpoint = path if path else ('/mnt/%s' % z_name)
        p1 = self.__pipeopen("zpool create -o cachefile=/data/zfs/zpool.cache "
                      "-O aclmode=passthrough -O aclinherit=passthrough "
                      "-f -m %s -o altroot=%s %s %s" % (mountpoint, altroot, z_name, z_vdev))
        if p1.wait() != 0:
            error = ", ".join(p1.communicate()[1].split('\n'))
            raise MiddlewareError('Unable to create the pool: %s' % error)

        #We've our pool, lets retrieve the GUID
        p1 = self.__pipeopen("zpool get guid %s" % z_name)
        if p1.wait() == 0:
            line = p1.communicate()[0].split('\n')[1].strip()
            volume.vol_guid = re.sub('\s+', ' ', line).split(' ')[2]
            volume.save()
        else:
            log.warn("The guid of the pool %s could not be retrieved", z_name)

        self.zfs_inherit_option(z_name, 'mountpoint')

        # If we have 4k hack then restore system to whatever it should be
        if want4khack:
            self.__system("zpool export %s" % (z_name))
            for gnop in gnop_devs:
                self.__system("gnop destroy %s" % gnop)
            self.__system("zpool import -R /mnt %s" % (z_name))

        self.__system("zpool set cachefile=/data/zfs/zpool.cache %s" % (z_name))

    def zfs_volume_attach_group(self, volume, group, force4khack=False):
        """Attach a disk group to a zfs volume"""
        c = self.__open_db()
        c.execute("SELECT adv_swapondrive FROM system_advanced ORDER BY -id LIMIT 1")
        swapsize=c.fetchone()[0]

        assert volume.vol_fstype == 'ZFS'
        z_name = volume.vol_name
        z_vdev = ""

        # FIXME swapoff -a is overkill
        self.__system("swapoff -a")
        vgrp_type = group['type']
        if vgrp_type != 'stripe':
            z_vdev += " " + vgrp_type

        # Prepare disks nominated in this group
        vdevs = self.__prepare_zfs_vdev(group['disks'], swapsize, force4khack)[0]
        z_vdev += " ".join(vdevs)

        # Finally, attach new groups to the zpool.
        self.__system("zpool add -f %s %s" % (z_name, z_vdev))
        self._reload_disk()

    def create_zfs_vol(self, name, size, props=None):
        """Internal procedure to create ZFS volume"""
        options = " "
        if props:
            assert type(props) is types.DictType
            for k in props.keys():
                if props[k] != 'inherit':
                    options += "-o %s=%s " % (k, props[k])
        zfsproc = self.__pipeopen("/sbin/zfs create %s -V %s %s" % (options, size, name))
        zfs_err = zfsproc.communicate()[1]
        zfs_error = zfsproc.wait()
        return zfs_error, zfs_err

    def create_zfs_dataset(self, path, props=None):
        """Internal procedure to create ZFS volume"""
        options = " "
        if props:
            assert type(props) is types.DictType
            for k in props.keys():
                if props[k] != 'inherit':
                    options += "-o %s=%s " % (k, props[k])
        zfsproc = self.__pipeopen("/sbin/zfs create %s %s" % (options, path))
        zfs_output, zfs_err = zfsproc.communicate()
        zfs_error = zfsproc.wait()
        if zfs_error == 0:
            self.restart("collectd")
        return zfs_error, zfs_err

    def list_zfs_datasets(self, path="", recursive=False):
        """Return a dictionary that contains all ZFS dataset list and their mountpoints"""
        if recursive:
            zfsproc = self.__pipeopen("/sbin/zfs list -Hr -t filesystem %s" % (path))
        else:
            zfsproc = self.__pipeopen("/sbin/zfs list -H -t filesystem %s" % (path))
        zfs_output, zfs_err = zfsproc.communicate()
        zfs_output = zfs_output.split('\n')
        zfslist = zfs.ZFSList()
        for line in zfs_output:
            if line:
                data = line.split('\t')
                # root filesystem is not treated as dataset by us
                if data[0].find('/') != -1:
                    zfslist.append(zfs.ZFSDataset(path=data[0], mountpoint=data[4]))
        return zfslist

    def list_zfs_vols(self, volname):
        """Return a dictionary that contains all ZFS volumes list"""
        zfsproc = self.__pipeopen("/sbin/zfs list -H -o name,volsize -t volume -r %s" % (str(volname),))
        zfs_output, zfs_err = zfsproc.communicate()
        zfs_output = zfs_output.split('\n')
        retval = {}
        for line in zfs_output:
            if line != "":
                data = line.split('\t')
                retval[data[0]] = {
                    'volsize': data[1],
                }
        return retval

    def list_zfs_fsvols(self):

        proc = self.__pipeopen("/sbin/zfs list -H -o name -t volume,filesystem")
        out, err = proc.communicate()
        out = out.split('\n')
        retval = OrderedDict()
        if proc.returncode == 0:
            for line in out:
                if not line:
                    continue
                retval[line] = line
        return retval

    def __snapshot_hold(self, name):
        """
        Check if a given snapshot is being hold by the replication system
        DISCLAIMER: mntlock has to be acquired before this call
        """
        zfsproc = self.__pipeopen("zfs get -H freenas:state %s" % (name))
        output = zfsproc.communicate()[0]
        if output != '':
            fsname, attrname, value, source = output.split('\n')[0].split('\t')
            if value != '-' and value != 'NEW':
                return True
        return False

    def destroy_zfs_dataset(self, path, recursive=False):
        retval = None
        if '@' in path:
            try:
                with mntlock(blocking=False) as MNTLOCK:
                    if self.__snapshot_hold(path):
                        retval = 'Held by replication system.'
            except IOError:
                retval = 'Try again later.'
        elif recursive:
            try:
                with mntlock(blocking=False) as MNTLOCK:
                    zfsproc = self.__pipeopen("/sbin/zfs list -Hr -t snapshot -o name %s" % (path))
                    snaps = zfsproc.communicate()[0]
                    for snap in filter(None, snaps.splitlines()):
                        if self.__snapshot_hold(snap):
                            retval = '%s: Held by replication system.' % snap
                            break
            except IOError:
                retval = 'Try again later.'
        if retval == None:
            if recursive:
                zfsproc = self.__pipeopen("zfs destroy -r %s" % (path))
            else:
                zfsproc = self.__pipeopen("zfs destroy %s" % (path))
            retval = zfsproc.communicate()[1]
            if zfsproc.returncode == 0:
                from storage.models import Task, Replication
                Task.objects.filter(task_filesystem=path).delete()
                Replication.objects.filter(repl_filesystem=path).delete()
        if not retval:
            try:
                self.__rmdir_mountpoint(path)
            except MiddlewareError as me:
                retval = str(me)

        return retval

    def destroy_zfs_vol(self, name):
        zfsproc = self.__pipeopen("zfs destroy %s" % (str(name),))
        retval = zfsproc.communicate()[1]
        return retval

    def __destroy_zfs_volume(self, volume):
        """Internal procedure to destroy a ZFS volume identified by volume id"""
        vol_name = str(volume.vol_name)
        # First, destroy the zpool.
        disks = volume.get_disks()
        self.__system("zpool destroy -f %s" % (vol_name, ))

        # Clear out disks associated with the volume
        for disk in disks:
            self.__gpt_unlabeldisk(devname=disk)

    def __create_ufs_volume(self, volume, swapsize, group):
        geom_vdev = ""
        u_name = str(volume.vol_name)
        # TODO: We do not support multiple GEOM levels for now.
        geom_type = group['type']

        if geom_type == '':
            # Grab disk from the group
            disk = group['disks'][0]
            self.__gpt_labeldisk(type = "freebsd-ufs", devname = disk, swapsize=swapsize)
            devname = self.part_type_from_device('ufs', disk)
            # TODO: Need to investigate why /dev/gpt/foo can't have label /dev/ufs/bar
            # generated automatically
            p1 = self.__pipeopen("newfs -U -L %s /dev/%s" % (u_name, devname))
            stderr = p1.communicate()[1]
            if p1.returncode != 0:
                error = ", ".join(stderr.split('\n'))
                raise MiddlewareError('Volume creation failed: "%s"' % error)
        else:
            # Grab all disks from the group
            for disk in group['disks']:
                # FIXME: turn into a function
                self.__system("dd if=/dev/zero of=/dev/%s bs=1m count=1" % (disk,))
                self.__system("dd if=/dev/zero of=/dev/%s bs=1m oseek=`diskinfo %s "
                      "| awk '{print int($3 / (1024*1024)) - 4;}'`" % (disk, disk))
                geom_vdev += " /dev/" + disk
                #TODO gpt label disks
            self.__system("geom %s load" % (geom_type))
            p1 = self.__pipeopen("geom %s label %s %s" % (geom_type, volume.vol_name, geom_vdev))
            stdout, stderr = p1.communicate()
            if p1.returncode != 0:
                error = ", ".join(stderr.split('\n'))
                raise MiddlewareError('Volume creation failed: "%s"' % error)
            ufs_device = "/dev/%s/%s" % (geom_type, volume.vol_name)
            self.__system("newfs -U -L %s %s" % (u_name, ufs_device))

    def __destroy_ufs_volume(self, volume):
        """Internal procedure to destroy a UFS volume identified by volume id"""
        u_name = str(volume.vol_name)

        disks = volume.get_disks()
        provider = self.get_label_consumer('ufs', u_name)
        if not provider:
            return None
        geom_type = provider.xpathEval("../../name")[0].content.lower()

        if geom_type not in ('mirror', 'stripe', 'raid3'):
            # Grab disk from the group
            disk = disks[0]
            self.__system("umount -f /dev/ufs/" + u_name)
            self.__gpt_unlabeldisk(devname = disk)
        else:
            g_name = provider.xpathEval("../name")[0].content
            self.__system("swapoff -a")
            self.__system("umount -f /dev/ufs/" + u_name)
            self.__system("geom %s stop %s" % (geom_type, g_name))
            # Grab all disks from the group
            for disk in disks:
                self.__system("geom %s clear %s" % (geom_type, disk))
                self.__system("dd if=/dev/zero of=/dev/%s bs=1m count=1" % (disk,))
                self.__system("dd if=/dev/zero of=/dev/%s bs=1m oseek=`diskinfo %s "
                      "| awk '{print int($3 / (1024*1024)) - 4;}'`" % (disk, disk))

    def _init_volume(self, volume, *args, **kwargs):
        """Initialize a volume designated by volume_id"""
        c = self.__open_db()
        c.execute("SELECT adv_swapondrive FROM system_advanced ORDER BY -id LIMIT 1")
        swapsize=c.fetchone()[0]
        c.close()

        assert volume.vol_fstype == 'ZFS' or volume.vol_fstype == 'UFS'
        if volume.vol_fstype == 'ZFS':
            self.__create_zfs_volume(volume, swapsize, kwargs.pop('groups', False), kwargs.pop('force4khack', False), kwargs.pop('path', None))
        elif volume.vol_fstype == 'UFS':
            self.__create_ufs_volume(volume, swapsize, kwargs.pop('groups')['root'])

    def zfs_replace_disk(self, volume, from_label, to_disk):
        """Replace disk in zfs called `from_label` to `to_disk`"""
        c = self.__open_db()
        c.execute("SELECT adv_swapondrive FROM system_advanced ORDER BY -id LIMIT 1")
        swapsize = c.fetchone()[0]

        assert volume.vol_fstype == 'ZFS'

        # TODO: Test on real hardware to see if ashift would persist across replace
        from_disk = self.label_to_disk(from_label)
        from_swap = self.part_type_from_device('swap', from_disk)

        if from_swap != '':
            self.__system('/sbin/swapoff /dev/%s' % (from_swap))

        # to_disk _might_ have swap on, offline it before gpt label
        to_swap = self.part_type_from_device('swap', to_disk)
        if to_swap != '':
            self.__system('/sbin/swapoff /dev/%s' % (to_swap))

        # Replace in-place
        if from_disk == to_disk:
            self.__system('/sbin/zpool offline %s %s' % (volume.vol_name, from_label))

        self.__gpt_labeldisk(type="freebsd-zfs", devname=to_disk, swapsize=swapsize)

        # There might be a swap after __gpt_labeldisk
        to_swap = self.part_type_from_device('swap', to_disk)
        # It has to be a freebsd-zfs partition there
        to_label = self.part_type_from_device('zfs', to_disk)
        if to_label == '':
            raise MiddlewareError('freebsd-zfs partition could not be found')

        if to_swap != '':
            self.__system('/sbin/swapon /dev/%s' % (to_swap))

        if from_disk == to_disk:
            self.__system('/sbin/zpool online %s %s' % (volume.vol_name, to_label))
            ret = self.__system_nolog('/sbin/zpool replace %s %s' % (volume.vol_name, to_label))
            if ret == 256:
                ret = self.__system_nolog('/sbin/zpool scrub %s' % (volume.vol_name))
        else:
            p1 = self.__pipeopen('/sbin/zpool replace %s %s %s' % (volume.vol_name, from_label, to_label))
            stdout, stderr = p1.communicate()
            ret = p1.returncode
            if ret != 0:
                if from_swap != '':
                    self.__system('/sbin/swapon /dev/%s' % (from_swap))
                error = ", ".join(stderr.split('\n'))
                if to_swap != '':
                    self.__system('/sbin/swapoff /dev/%s' % (to_swap))
                raise MiddlewareError('Disk replacement failed: "%s"' % error)

        if to_swap:
            self.__system('/sbin/swapon /dev/%s' % (to_swap))

        return ret

    def zfs_offline_disk(self, volume, label):

        assert volume.vol_fstype == 'ZFS'

        # TODO: Test on real hardware to see if ashift would persist across replace
        disk = self.label_to_disk(label)
        swap = self.part_type_from_device('swap', disk)

        if swap != '':
            self.__system('/sbin/swapoff /dev/%s' % (swap))

        # Replace in-place
        p1 = self.__pipeopen('/sbin/zpool offline %s %s' % (volume.vol_name, label))
        stderr = p1.communicate()[1]
        if p1.returncode != 0:
            error = ", ".join(stderr.split('\n'))
            raise MiddlewareError('Disk offline failed: "%s"' % error)

    def zfs_detach_disk(self, volume, label):
        """Detach a disk from zpool
           (more technically speaking, a replaced disk.  The replacement actually
           creates a mirror for the device to be replaced)"""

        assert volume.vol_fstype == 'ZFS'

        from_disk = self.label_to_disk(label)
        from_swap = self.part_type_from_device('swap', from_disk)

        # Remove the swap partition for another time to be sure.
        # TODO: swap partition should be trashed instead.
        if from_swap != '':
            self.__system('/sbin/swapoff /dev/%s' % (from_swap,))

        ret = self.__system_nolog('/sbin/zpool detach %s %s' % (volume.vol_name, label))
        # TODO: This operation will cause damage to disk data which should be limited
        self.__gpt_unlabeldisk(from_disk)
        return ret

    def zfs_remove_disk(self, volume, label):
        """
        Remove a disk from zpool
        Cache disks, inactive hot-spares (and log devices in zfs 28) can be removed
        """

        assert volume.vol_fstype == 'ZFS'

        from_disk = self.label_to_disk(label)
        from_swap = self.part_type_from_device('swap', from_disk)

        if from_swap != '':
            self.__system('/sbin/swapoff /dev/%s' % (from_swap,))

        p1 = self.__pipeopen('/sbin/zpool remove %s %s' % (volume.vol_name, label))
        stderr = p1.communicate()[1]
        if p1.returncode != 0:
            error = ", ".join(stderr.split('\n'))
            raise MiddlewareError('Disk could not be removed: "%s"' % error)
        # TODO: This operation will cause damage to disk data which should be limited

        self.__gpt_unlabeldisk(from_disk)

    def detach_volume_swaps(self, volume):
        """Detach all swaps associated with volume"""
        disks = volume.get_disks()
        for disk in disks:
            swapdev = self.part_type_from_device('swap', disk)
            if swapdev != '':
                self.__system("swapoff /dev/%s" % swapdev)

    def __get_mountpath(self, name, fstype, mountpoint_root='/mnt'):
        """Determine the mountpoint for a volume or ZFS dataset

        It tries to divine the location of the volume or dataset from the
        relevant command, and if all else fails, falls back to a less
        elegant method of representing the mountpoint path.

        This is done to ensure that in the event that the database and
        reality get out of synch, the user can nuke the volume/mountpoint.

        XXX: this should be done more elegantly by calling getfsent from C.

        Required Parameters:
            name: textual name for the mountable vdev or volume, e.g. 'tank',
                  'stripe', 'tank/dataset', etc.
            fstype: filesystem type for the vdev or volume, e.g. 'UFS', 'ZFS',
                    etc.

        Optional Parameters:
            mountpoint_root: the root directory where all of the datasets and
                             volumes shall be mounted. Defaults to '/mnt'.

        Returns:
            the absolute path for the volume on the system.
        """
        mountpoint = None
        if fstype == 'ZFS':
            p1 = self.__pipeopen('zfs list -H -o mountpoint %s' % (name, ))
            stdout = p1.communicate()[0]
            if not p1.returncode:
                return stdout.strip()
        elif fstype == 'UFS':
            p1 = self.__pipeopen('mount -p')
            stdout = p1.communicate()[0]
            if not p1.returncode:
                flines = filter(lambda x: x and x.split()[0] == \
                                                '/dev/ufs/' + name,
                                stdout.splitlines())
                if flines:
                    return flines[0].split()[1]

        return os.path.join(mountpoint_root, name)

    def _destroy_volume(self, volume):
        """Destroy a volume on the system

        This either destroys a zpool or umounts a generic volume (e.g. NTFS,
        UFS, etc) and nukes it.

        In the event that the volume is still in use in the OS, the end-result
        is implementation defined depending on the filesystem, and the set of
        commands used to export the filesystem.

        Finally, this method goes and cleans up the mountpoint, as it's
        assumed to be no longer needed. This is also a sanity check to ensure
        that cleaning up everything worked.

        XXX: doing recursive unmounting here might be a good idea.
        XXX: better feedback about files in use might be a good idea...
             someday. But probably before getting to this point. This is a
             tricky problem to fix in a way that doesn't unnecessarily suck up
             resources, but also ensures that the user is provided with
             meaningful data.
        XXX: divorce this from storage.models; depending on storage.models
             introduces a circular dependency and creates design ugliness.
        XXX: implement destruction algorithm for non-UFS/-ZFS.

        Parameters:
            volume: a storage.models.Volume object.

        Raises:
            MiddlewareError: the volume could not be detached cleanly.
            MiddlewareError: the volume's mountpoint couldn't be removed.
            ValueError: 'destroy' isn't implemented for the said filesystem.
        """

        # volume_detach compatibility.
        vol_name, vol_fstype = volume.vol_name, volume.vol_fstype

        vol_mountpath = self.__get_mountpath(vol_name, vol_fstype)

        if vol_fstype == 'ZFS':
            self.__destroy_zfs_volume(volume)
        elif vol_fstype == 'UFS':
            self.__destroy_ufs_volume(volume)
        else:
            raise ValueError("destroy isn't implemented for the %s filesystem"
                             % (vol_fstype, ))


        self._reload_disk()


        self.__rmdir_mountpoint(vol_mountpath)

    def _reload_disk(self):
        self.__system("/usr/sbin/service ix-fstab quietstart")
        self.__system("/usr/sbin/service swap1 quietstart")
        self.__system("/usr/sbin/service mountlate quietstart")
        self.restart("collectd")
        self.__confxml = None

    # Create a user in system then samba
    def __pw_with_password(self, command, password):
        pw = self.__pipeopen(command)
        msg = pw.communicate("%s\n" % password)[1]
        if pw.returncode != 0:
            raise MiddlewareError("Operation could not be performed. %s" % msg)

        if msg != "":
            log.debug("Command reports %s", msg)

    def __smbpasswd(self, username, password):
        """
        Add the user ``username'' to samba using ``password'' as
        the current password

        Returns:
            True whether the user has been successfully added and False otherwise
        """
        command = '/usr/local/bin/smbpasswd -D 0 -s -a "%s"' % (username)
        smbpasswd = self.__pipeopen(command)
        smbpasswd.communicate("%s\n%s\n" % (password, password))
        return smbpasswd.returncode == 0

    def __issue_pwdchange(self, username, command, password):
        self.__pw_with_password(command, password)
        self.__smbpasswd(username, password)

    def user_create(self, username, fullname, password, uid=-1, gid=-1,
                    shell="/sbin/nologin",
                    homedir='/mnt', homedir_mode=0o755,
                    password_disabled=False, locked=False):
        """Create a user.

        This goes and compiles the invocation needed to execute via pw(8),
        then goes and creates a home directory. Then it goes and adds the
        user via pw(8), and finally adds the user's to the samba user
        database. If adding the user fails for some reason, it will remove
        the directory.

        Required parameters:

        username - a textual identifier for the user (should conform to
                   all constraints with Windows, Unix and OSX usernames).
                   Example: 'root'.
        fullname - a textual 'humanized' identifier for the user. Example:
                   'Charlie Root'.
        password - passphrase used to login to the system; this is
                   ignored if password_disabled is True.

        Optional parameters:

        uid - uid for the user. Defaults to -1 (defaults to the next UID
              via pw(8)).
        gid - gid for the user. Defaults to -1 (defaults to the next GID
              via pw(8)).
        shell - login shell for a user when logging in interactively.
                Defaults to /sbin/nologin.
        homedir - where the user will be put, or /nonexistent if
                  the user doesn't need a directory; defaults to /mnt.
        homedir_mode - mode to use when creating the home directory;
                       defaults to 0755.
        password_disabled - should password based logins be allowed for 
                            the user? Defaults to False.
        locked - allows the administrator to restrict the account s.t.
                 it can't be used for logins (until some precondition is
                 met, i.e. the user changes his or her password).

        XXX: the default for the home directory seems like a bad idea.
             Should this be a required parameter instead, or default
             to /var/empty?
        XXX: seems like the password_disabled and password fields could
             be rolled into one property.
        XXX: the homedir mode isn't set today by the GUI; the default
             is set to the FreeBSD default when calling pw(8).
        XXX: smbpasswd errors aren't being caught today.
        XXX: invoking smbpasswd for each user add seems like an
             expensive operation.
        XXX: why are we returning the password hashes?

        Returns:
            A tuple of the user's UID, GID, the Unix encrypted password
            hash, and the encrypted SMB password hash.

        Raises:
            MiddlewareError - tried to create a home directory under a
                              subdirectory on the /mnt memory disk.
            MiddlewareError - failed to create the home directory for
                              the user.
            MiddlewareError - failed to run pw useradd successfully.
        """
        command = '/usr/sbin/pw useradd "%s" -c "%s" -d "%s" -s "%s"' % \
            (username, fullname, homedir, shell, )
        if password_disabled:
            command += ' -h -'
        else:
            command += ' -h 0'
        if uid >= 0:
            command += " -u %d" % (uid)
        if gid >= 0:
            command += " -g %d" % (gid)
        if homedir != '/nonexistent':
            # Populate the home directory with files from /usr/share/skel .
            command += ' -m'

        # Is this a new directory or not? Let's not nuke existing directories,
        # e.g. /, /root, /mnt/tank/my-dataset, etc ;).
        new_homedir = False

        if homedir != '/nonexistent':
            # Kept separate for cleanliness between formulating what to do
            # and executing the formulated plan.

            # You're probably wondering why pw -m doesn't suffice. Here's why:
            # 1. pw(8) doesn't create home directories if the base directory
            #    doesn't exist; example: if /mnt/tank/homes doesn't exist and
            #    the user specified /mnt/tank/homes/user, then the home
            #    directory won't be created.
            # 2. pw(8) allows me to specify /mnt/md_size (a regular file) for
            #    the home directory.
            # 3. If some other random path creation error occurs, it's already
            #    too late to roll back the user create.
            try:
                os.makedirs(homedir, mode=homedir_mode)
                if os.stat(homedir).st_dev == os.stat('/mnt').st_dev:
                    # HACK: ensure the user doesn't put their homedir under
                    # /mnt
                    # XXX: fix the GUI code and elsewhere to enforce this, then
                    # remove the hack.
                    raise MiddlewareError('Path for the home directory (%s) '
                                          'must be under a volume or dataset'
                                          % (homedir, ))
            except OSError as oe:
                if oe.errno == errno.EEXIST:
                    if not os.path.isdir(homedir):
                        raise MiddlewareError('Path for home directory already '
                                              'exists and is not a directory')
                else:
                    raise MiddlewareError('Failed to create the home directory '
                                          '(%s) for user: %s'
                                          % (homedir, str(oe)))
            else:
                new_homedir = True

        try:
            self.__issue_pwdchange(username, command, password)
            if locked:
                self.user_lock(username)
            if password_disabled:
                smb_hash = ""
            else:
                """
                Make sure to use -d 0 for pdbedit, otherwise it will bomb
                if CIFS debug level is anything different than 'Minimum'
                """
                smb_command = "/usr/local/bin/pdbedit -d 0 -w %s" % username
                smb_cmd = self.__pipeopen(smb_command)
                smb_hash = smb_cmd.communicate()[0].split('\n')[0]
        except:
            if new_homedir:
                # Be as atomic as possible when creating the user if
                # commands failed to execute cleanly.
                shutil.rmtree(homedir)
            raise

        user = self.___getpwnam(username)
        return (user.pw_uid, user.pw_gid, user.pw_passwd, smb_hash)

    def user_lock(self, username):
        self.__system('/usr/local/bin/smbpasswd -d "%s"' % (username))
        self.__system('/usr/sbin/pw lock "%s"' % (username))
        return self.user_gethashedpassword(username)

    def user_unlock(self, username):
        self.__system('/usr/local/bin/smbpasswd -e "%s"' % (username))
        self.__system('/usr/sbin/pw unlock "%s"' % (username))
        return self.user_gethashedpassword(username)

    def user_changepassword(self, username, password):
        """Changes user password"""
        command = '/usr/sbin/pw usermod "%s" -h 0' % (username)
        self.__issue_pwdchange(username, command, password)
        return self.user_gethashedpassword(username)

    def user_gethashedpassword(self, username):
        """
        Get the samba hashed password for ``username''

        Returns:
            tuple -> (user password, samba hash)
        """

        """
        Make sure to use -d 0 for pdbedit, otherwise it will bomb
        if CIFS debug level is anything different than 'Minimum'
        """
        smb_command = "/usr/local/bin/pdbedit -d 0 -w %s" % username
        smb_cmd = self.__pipeopen(smb_command)
        smb_hash = smb_cmd.communicate()[0].split('\n')[0]
        user = self.___getpwnam(username)
        return (user.pw_passwd, smb_hash)

    def user_deleteuser(self, username):
        self.__system('/usr/sbin/pw userdel "%s"' % (username))

    def user_deletegroup(self, groupname):
        self.__system('/usr/sbin/pw groupdel "%s"' % (groupname))

    def user_getnextuid(self):
        command = "/usr/sbin/pw usernext"
        pw = self.__pipeopen(command)
        uidgid = pw.communicate()
        uid = uidgid[0].split(':')[0]
        return uid

    def user_getnextgid(self):
        command = "/usr/sbin/pw groupnext"
        pw = self.__pipeopen(command)
        uidgid = pw.communicate()
        gid = uidgid[0]
        return gid

    def save_pubkey(self, homedir, pubkey, username, groupname):
        homedir = str(homedir)
        pubkey = str(pubkey).strip()
        if pubkey:
            pubkey = '%s\n' % pubkey
        sshpath = '%s/.ssh' % (homedir)
        keypath = '%s/.ssh/authorized_keys' % (homedir)
        try:
            oldpubkey = open(keypath).read()
            if oldpubkey == pubkey:
                return
        except:
            pass

        if homedir == '/root':
            self.__system("/sbin/mount -uw -onoatime /")
        saved_umask = os.umask(077)
        if not os.path.isdir(sshpath):
            os.makedirs(sshpath)
        if not os.path.isdir(sshpath):
            return # FIXME: need better error reporting here
        if pubkey == '' and os.path.exists(keypath):
            os.unlink(keypath)
        else:
            fd = open(keypath, 'w')
            fd.write(pubkey)
            fd.close()
            self.__system("/usr/sbin/chown -R %s:%s %s" % (username, groupname, sshpath))
        if homedir == '/root':
            self.__system("/sbin/mount -ur /")
        os.umask(saved_umask)

    def _reload_user(self):
        self.__system("/usr/sbin/service ix-passwd quietstart")
        self.__system("/usr/sbin/service ix-aliases quietstart")
        self.reload("cifs")

    def mp_change_permission(self, path='/mnt', user='root', group='wheel',
                             mode='0755', recursive=False, acl='unix'):

        winacl = os.path.join(path, ACL_WINDOWS_FILE)
        winexists = (ACL.get_acl_ostype(path) == ACL_FLAGS_OS_WINDOWS)
        if acl == 'windows' and not winexists:
            open(winacl, 'a').close()
        elif acl == 'unix' and winexists:
            os.unlink(winacl)

        hier = ACL_Hierarchy(path)
        hier.set_defaults(recursive=recursive)
        hier.chown(user + ":" + group, recursive)
        hier.chmod(mode, recursive)
        hier.close()

    def mp_get_permission(self, path):
        if os.path.isdir(path):
            return stat.S_IMODE(os.stat(path)[stat.ST_MODE])

    def mp_get_owner(self, path):
        """Gets the owner/group for a given mountpoint.

        Defaults to root:wheel if the owner of the mountpoint cannot be found.

        XXX: defaulting to root:wheel is wrong if the users/groups are out of
             synch with the remote hosts. These cases should really raise
             Exceptions and be handled differently in the GUI.

        Raises:
            OSError - the path provided isn't a directory.
        """
        if os.path.isdir(path):
            stat_info = os.stat(path)
            uid = stat_info.st_uid
            gid = stat_info.st_gid
            try:
                pw = pwd.getpwuid(uid)
                user = pw.pw_name
            except KeyError:
                user = 'root'
            try:
                gr = grp.getgrgid(gid)
                group = gr.gr_name
            except KeyError:
                group = 'wheel'
            return (user, group, )
        raise OSError('Invalid mountpoint %s' % (path, ))

    def change_upload_location(self, path):
        vardir = "/var/tmp/firmware"

        self.__system("/bin/rm -rf %s" % vardir)
        self.__system("/bin/mkdir -p %s/.freenas" % path)
        self.__system("/usr/sbin/chown www:www %s/.freenas" % path)
        self.__system("/bin/ln -s %s/.freenas %s" % (path, vardir))


    def validate_update(self, path):

        os.chdir(os.path.dirname(path))

        # XXX: ugly
        self.__system("rm -rf */")

        if self.__system_nolog('/usr/bin/tar -xJpf %s' % (path, )):
            os.chdir('/')
            raise MiddlewareError('The firmware is invalid')
        try:
            subprocess.check_output(
                                    ['bin/install_worker.sh', 'pre-install'],
                                    stderr=subprocess.STDOUT,
                                    )
        except subprocess.CalledProcessError, cpe:
            raise MiddlewareError('The firmware is does not meet the '
                                  'pre-install criteria: %s' % (str(cpe), ))
        finally:
            os.chdir('/')
        # XXX: bleh
        return True


    def apply_update(self, path):
        os.chdir(os.path.dirname(path))
        try:
            subprocess.check_output(
                                    ['bin/install_worker.sh', 'install'],
                                    stderr=subprocess.STDOUT,
                                    )
        except subprocess.CalledProcessError, cpe:
            raise MiddlewareError('The update failed: %s' % (str(cpe), ))
        finally:
            os.chdir('/')
            os.unlink(path)
        open(NEED_UPDATE_SENTINEL, 'w').close()

    def __umount_filesystems_within(self, path):
        """
        Try to umount filesystems within a certain path

        Raises:
            MiddlewareError - Could not umount
        """
        for mounted in get_mounted_filesystems():
            if mounted['fs_file'].startswith(path):
                if not umount(mounted['fs_file']):
                    raise MiddlewareError('Unable to umount %s' % (
                        mounted['fs_file'],
                        ))

    def install_pbi(self):
        """
        Install a .pbi file into the plugins jail

        Returns:
            bool: installation successful?

        Raises::
            MiddlewareError: pbi_add failed
        """
        from freenasUI.services.models import RPCToken
        ret = False

        if not self._started_plugins_jail():
            return False

        (c, conn) = self.__open_db(ret_conn=True)

        c.execute("SELECT jail_path, jail_name, plugins_path FROM services_pluginsjail ORDER BY -id LIMIT 1")
        row = c.fetchone()
        if not row:
            return False
        jail_path, jail_name, plugins_path = row

        jail = None
        for j in Jls():
            if j.hostname == jail_name:
                jail = j
                break

        # this stuff needs better error checking.. .. ..
        if jail is None:
            raise MiddlewareError("The plugins jail is not running, start "
                "it before proceeding")
        pbi = pbiname = prefix = name = version = arch = None

        p = pbi_add(flags=PBI_ADD_FLAGS_INFO, pbi="/mnt/plugins/.freenas/pbifile.pbi")
        out = p.info(True, jail.jid, 'pbi information for', 'prefix', 'name', 'version', 'arch')

        if not out:
            raise MiddlewareError("This file was not identified as in PBI "
                "format, it might as well be corrupt.")

        for pair in out:
            (var, val) = pair.split('=', 1)

            var = var.lower()
            if var == 'pbi information for':
                pbiname = val
                pbi = "%s.pbi" % val

            elif var == 'prefix':
                prefix = val

            elif var == 'name':
                name = val

            elif var == 'version':
                version = val

            elif var == 'arch':
                arch = val

        self.__system("/bin/mv /var/tmp/firmware/pbifile.pbi %s/%s" % (plugins_path, pbi))

        p = pbi_add(flags=PBI_ADD_FLAGS_NOCHECKSIG, pbi="/mnt/plugins/%s" % pbi)
        res = p.run(jail=True, jid=jail.jid)
        if res and res[0] == 0:
            kwargs = {}
            kwargs['path'] = prefix
            kwargs['enabled'] = True
            kwargs['ip'] = jail.ip
            kwargs['name'] = name
            kwargs['arch'] = arch
            kwargs['version'] = version
            kwargs['pbiname'] = pbiname

            # icky, icky icky, this is how we roll though.
            port = 12345
            c.execute("SELECT count(*) FROM plugins_plugins")
            count = c.fetchone()[0]
            if count > 0:
                c.execute("SELECT plugin_port FROM plugins_plugins ORDER BY plugin_port DESC LIMIT 1")
                port = int(c.fetchone()[0])

            kwargs['port'] = port + 1

            rpctoken = RPCToken.new()
            kwargs['secret_id'] = rpctoken.id

            oauth_file = "%s/%s/%s/.oauth" % (jail_path, jail_name, kwargs["path"])

            fd = os.open(oauth_file, os.O_WRONLY|os.O_CREAT, 0600)
            os.write(fd,"key = %s\n" % rpctoken.key)
            os.write(fd, "secret = %s\n" % rpctoken.secret)
            os.close(fd)

            sqlvars = ""
            sqlvals = ""
            for key in kwargs:
                sqlvars += "plugin_%s," % key
                sqlvals += ":%s," % key

            sqlvars = sqlvars.rstrip(',')
            sqlvals = sqlvals.rstrip(',')

            sql = "INSERT INTO plugins_plugins(%s) VALUES(%s)" % (sqlvars, sqlvals)
            try:
                c.execute(sql, kwargs)
                conn.commit()
                ret = True

            except Exception, err:
                ret = False

        elif res and res[0] != 0:
            # pbid seems to return 255 for any kind of error
            # lets use error str output to find out what happenned
            if re.search(r'failed checksum', res[1], re.I|re.S|re.M):
                raise MiddlewareError("The file %s seems to be "
                    "corrupt, please try download it again." % (
                        pbiname,
                        )
                    )
            raise MiddlewareError(p.error)

        return ret

    def install_jail_pbi(self, path, name, plugins_path):
        """
        Install the plugins jail PBI

        Returns::
            bool: installation succeeded?

        Raises::
            MiddlewareError: pbi file corrupt or invalid
        """
        ret = False

        prefix = ename = pbi = None
        p = pbi_add(flags=PBI_ADD_FLAGS_INFO, pbi="/var/tmp/firmware/pbifile.pbi")
        out = p.info(False, -1, 'prefix', 'pbi information for')

        if not out:
            raise MiddlewareError("This file was not identified as in PBI "
                "format, it might as well be corrupt.")

        for pair in out:
            (var, val) = pair.split('=', 1)
            var = var.lower()
            if var == 'prefix':
                prefix = val
            elif var == 'pbi information for':
                pbi = "%s.pbi" % val

        parts = prefix.split('/')

        ename = parts[0]
        if len(parts) > 1:
            ename = parts[len(parts) - 1]

        p = pbi_add(flags=PBI_ADD_FLAGS_EXTRACT_ONLY|PBI_ADD_FLAGS_OUTDIR|PBI_ADD_FLAGS_NOCHECKSIG|PBI_ADD_FLAGS_FORCE,
            pbi="/var/tmp/firmware/pbifile.pbi", outdir=path)
        res = p.run()

        if res and res[0] == 0:
            src = os.path.join(path, ename)
            dst = os.path.join(path, name)
            if src != dst:
                self.__system("/bin/mv '%s' '%s'" % (src, dst))
            self.__system("/bin/mv /var/tmp/firmware/pbifile.pbi %s/%s" % (plugins_path, pbi))
            ret = True
        else:
            # pbid seems to return 255 for any kind of error
            # lets use error str output to find out what happenned
            if re.search(r'failed checksum', res[1], re.I|re.S|re.M):
                raise MiddlewareError("The PBI file ('%s') is corrupt"
                                      % (os.path.basename(path), ) )
            raise MiddlewareError(p.error)

        return ret

    def import_jail(self, jail_path, jail_ip, plugins_path):
        ret = False

        if not jail_path:
            return ret
        if not jail_ip:
            return ret
        if not plugins_path:
            return ret

        if not os.access(jail_path, os.F_OK):
            return ret
        if not os.access(plugins_path, os.F_OK):
            return ret

        parts = jail_path.split('/')
        if not parts:
            return ret

        jail_path = '/'.join(parts[:-1])
        if not jail_path:
            jail_path = "/"
        jail_name = parts[-1]

        #
        # XXX: At some point (soon), plugins/jail need to support IPv6
        #
        (c, conn) = self.__open_db(ret_conn=True)
        c.execute("SELECT alias_interface_id, alias_v4address, alias_v4netmaskbit "
            "FROM network_alias WHERE alias_v4address = :jail_ip", { 'jail_ip': jail_ip })
        (alias_id, alias_addr, alias_mask) = c.fetchone()

        sqlvars = "jail_path, jail_name, jail_ip_id, plugins_path"
        sqlvals = "'%s', '%s', '%s', '%s'" % (jail_path, jail_name, alias_id, plugins_path)

        sql = "INSERT INTO services_pluginsjail (%s) VALUES (%s)" % (sqlvars, sqlvals)
        try:
            c.execute(sql)
            conn.commit()
            ret = True

        except Exception, err:
            syslog.syslog(syslog.LOG_DEBUG, "import_jail: failed %s" % (str(err), ))
            ret = False

        return ret

    def delete_pbi(self, plugin):
        ret = False

        (c, conn) = self.__open_db(ret_conn=True)
        c.execute("SELECT jail_name, jail_path FROM services_pluginsjail ORDER BY -id LIMIT 1")
        row = c.fetchone()
        if not row:
            log.debug("delete_pbi: plugins jail info not in database")
            return False
        jail_name, jail_path = row

        jail = None
        for j in Jls():
            if j.hostname == jail_name:
                jail = j
                break

        if jail is not None:

            pbi_path = os.path.join(
                jail_path,
                jail_name,
                "usr/pbi",
                "%s-%s" % (plugin.plugin_name, platform.machine()),
                )
            self.__umount_filesystems_within(pbi_path)

            p = pbi_delete(pbi=plugin.plugin_pbiname)
            res = p.run(jail=True, jid=jail.jid)
            if res and res[0] == 0:
                try:
                    plugin.delete()
                    ret = True

                except Exception, err:
                    log.debug("delete_pbi: unable to delete pbi %s from database (%s)", plugin, err)
                    ret = False

        return ret

    def delete_plugins_jail(self, jail_id):
        (c, conn) = self.__open_db(ret_conn=True)
        ret = False

        log.debug("delete_plugins_jail: stopping plugins")
        self._stop_plugins()

        log.debug("delete_plugins_jail: getting plugins id's from the database")
        c.execute("SELECT id FROM plugins_plugins")
        plugin_ids = [p[0] for p in c.fetchall()]
        for plugin_id in plugin_ids:
            try:
                assert self.delete_pbi(plugin_id)
            except Exception:
                log.debug("delete_plugins_jail: unable to delete plugin %d", plugin_id)

        log.debug("delete_plugins_jail: stopping plugins jail")
        self._stop_plugins_jail()

        log.debug("delete_plugins_jail: checking if jail stopped")
        if self._started_plugins_jail():
            log.debug("delete_plugins_jail: plugins jail not stopped, forcing")
            self._force_stop_jail()

        log.debug("delete_plugins_jail: checking if jail stopped")
        if self._started_plugins_jail():
            log.debug("delete_plugins_jail: unable to stop plugins jail")
            return False

        log.debug("delete_plugins_jail: getting jail info from database")
        c.execute("SELECT jail_name, jail_path, plugins_path "
            "FROM services_pluginsjail WHERE id = :jail_id", {'jail_id': jail_id})
        jail_info = c.fetchone()
        if not jail_info:
            log.debug("delete_plugins_jail: plugins jail info not in database")
            return False

        (jail_name, jail_path, plugins_path) = jail_info
        full_jail_path = os.path.join(jail_path, jail_name)

        log.debug("delete_plugins_jail: checking jail path in filesystem")
        if not os.access(full_jail_path, os.F_OK):
            log.debug("delete_plugins_jail: unable to access %s", full_jail_path)
            return False

        self.__umount_filesystems_within(full_jail_path)

        cmd = "/usr/bin/find %s|/usr/bin/xargs /bin/chflags noschg" % full_jail_path
        log.debug("delete_plugins_jail: %s", cmd)
        p = self.__pipeopen(cmd)
        p.wait()
        if p.returncode != 0:
            log.debug("delete_plugins_jail: unable to chflags on %s", full_jail_path)
            return False

        cmd = "/bin/rm -rf %s" % full_jail_path
        log.debug("delete_plugins_jail: %s", cmd)
        p = self.__pipeopen(cmd)
        p.wait()
        if p.returncode != 0:
            log.debug("delete_plugins_jail: unable to rm -rf %s", full_jail_path)
            return False

        pbi_path = "%s/%s" % (plugins_path, "pbi")
        cmd = "/bin/rm -rf %s" % pbi_path
        log.debug("delete_plugins_jail: %s", cmd)
        p = self.__pipeopen(cmd)
        p.wait()
        if p.returncode != 0:
            log.debug("delete_plugins_jail: unable to rm -rf %s/*", pbi_path)

        log.debug("delete_plugins_jail: deleting jail from database")
        try:
            c.execute("DELETE FROM services_pluginsjail WHERE id = :jail_id", {'jail_id': jail_id})
            c.execute("UPDATE services_services set srv_enabled = 0 WHERE srv_service = 'plugins'")
            conn.commit()
            ret = True

        except Exception, err:
            log.debug("delete_plugins_jail: unable to delete plugins jail from database (%s)", err)
            ret = False

        log.debug("delete_plugins_jail: returning %s", ret)
        return ret


    def get_volume_status(self, name, fs):
        status = 'UNKNOWN'
        if fs == 'ZFS':
            p1 = self.__pipeopen('zpool list -H -o health %s' % str(name))
            if p1.wait() == 0:
                status = p1.communicate()[0].strip('\n')
        elif fs == 'UFS':

            provider = self.get_label_consumer('ufs', name)
            if not provider:
                return 'UNKNOWN'
            gtype = provider.xpathEval("../../name")[0].content

            if gtype in ('MIRROR', 'STRIPE', 'RAID3'):

                search = provider.xpathEval("../config/State")
                if len(search) > 0:
                    status = search[0].content

            else:
                p1 = self.__pipeopen('mount|grep "/dev/ufs/%s"' % (name, ))
                p1.communicate()
                if p1.returncode == 0:
                    status = 'HEALTHY'
                else:
                    status = 'DEGRADED'

        if status in ('UP', 'COMPLETE', 'ONLINE'):
            status = 'HEALTHY'
        return status

    def checksum(self, path, algorithm='sha256'):
        algorithm2map = {
            'sha256' : '/sbin/sha256 -q',
        }
        hasher = self.__pipeopen('%s %s' % (algorithm2map[algorithm], path))
        sum = hasher.communicate()[0].split('\n')[0]
        return sum

    def get_disks(self):
        """
        Grab usable disks and pertinent info about them
        This accounts for:
            - all the disks the OS found
                (except the ones that are providers for multipath)
            - multipath geoms providers

        Returns:
            Dict of disks
        """
        disksd = {}

        disks = self.__get_disks()

        """
        Replace devnames by its multipath equivalent
        """
        for mp in self.multipath_all():
            for dev in mp.devices:
                if dev in disks:
                    disks.remove(dev)
            disks.append(mp.devname)

        for disk in disks:
            info = self.__pipeopen('/usr/sbin/diskinfo %s' % disk).communicate()[0].split('\t')
            if len(info) > 3:
                disksd.update({
                    disk: {
                        'devname': info[0],
                        'capacity': info[2],
                    },
                })

        return disksd

    def get_partitions(self, try_disks=True):
        disks = self.get_disks().keys()
        partitions = {}
        for disk in disks:

            listing = glob.glob('/dev/%s[a-fps]*' % disk)
            if try_disks is True and len(listing) == 0:
                listing = [disk]
            for part in list(listing):
                toremove = len([i for i in listing if i.startswith(part) and i != part]) > 0
                if toremove:
                    listing.remove(part)

            for part in listing:
                p1 = Popen(["/usr/sbin/diskinfo", part], stdin=PIPE, stdout=PIPE)
                info = p1.communicate()[0].split('\t')
                partitions.update({
                    part: {
                        'devname': info[0].replace("/dev/", ""),
                        'capacity': info[2]
                    },
                })
        return partitions

    def precheck_partition(self, dev, fstype):

        if fstype == 'UFS':
            p1 = self.__pipeopen("/sbin/fsck_ufs -p %s" % dev)
            p1.communicate()
            if p1.returncode == 0:
                return True
        elif fstype == 'NTFS':
            return True
        elif fstype == 'MSDOSFS':
            p1 = self.__pipeopen("/sbin/fsck_msdosfs -p %s" % dev)
            p1.communicate()
            if p1.returncode == 0:
                return True
        elif fstype == 'EXT2FS':
            p1 = self.__pipeopen("/sbin/fsck_ext2fs -p %s" % dev)
            p1.communicate()
            if p1.returncode == 0:
                return True

        return False

    def label_disk(self, label, dev, fstype=None):
        """
        Label the disk being manually imported
        Currently UFS, NTFS, MSDOSFS and EXT2FS are supported
        """

        if fstype == 'UFS':
            p1 = Popen(["/sbin/tunefs", "-L", label, dev], stdin=PIPE, stdout=PIPE)
        elif fstype == 'NTFS':
            p1 = Popen(["/usr/local/sbin/ntfslabel", dev, label], stdin=PIPE, stdout=PIPE)
        elif fstype == 'MSDOSFS':
            p1 = Popen(["/usr/local/bin/mlabel", "-i", dev, "::%s" % label], stdin=PIPE, stdout=PIPE)
        elif fstype == 'EXT2FS':
            p1 = Popen(["/usr/local/sbin/tune2fs", "-L", label, dev], stdin=PIPE, stdout=PIPE)
        elif fstype is None:
            p1 = Popen(["/sbin/geom", "label", "label", label, dev], stdin=PIPE, stdout=PIPE)
        else:
            return False
        if p1.wait() == 0:
            return True
        return False

    def detect_volumes(self, extra=None):
        """
        Responsible to detect existing volumes by running
        g{mirror,stripe,raid3},zpool commands

        Used by: Automatic Volume Import
        """

        volumes = []
        doc = self.__geom_confxml()
        # Detect GEOM mirror, stripe and raid3
        for geom in ('mirror', 'stripe', 'raid3'):
            search = doc.xpathEval("//class[name = '%s']/geom/config" % (geom.upper(),))
            for entry in search:
                label = entry.xpathEval('../name')[0].content
                disks = []
                for consumer in entry.xpathEval('../consumer/provider'):
                    provider = consumer.prop("ref")
                    device = doc.xpathEval("//class[name = 'DISK']//provider[@id = '%s']/name" % provider)
                    disks.append( {'name': device[0].content} )

                # Next thing is find out whether this is a raw block device or has GPT
                #TODO: MBR?
                search = doc.xpathEval("//class[name = 'PART']/geom[name = '%s/%s']/provider//config[type = 'freebsd-ufs']" % (geom,label))
                if len(search) > 0:
                    label = search[0].xpathEval("../name")[0].content.split('/', 1)[1]
                volumes.append({
                    'label': label,
                    'type': 'geom',
                    'group_type': geom,
                    'disks': {'vdevs': [{'disks': disks, 'name': geom}]},
                    })

        pool_name = re.compile(r'pool: (?P<name>%s)' % (zfs.ZPOOL_NAME_RE, ), re.I)
        p1 = self.__pipeopen("zpool import")
        res = p1.communicate()[0]

        for pool in pool_name.findall(res):
            # get status part of the pool
            status = res.split('pool: %s\n' % pool)[1].split('pool:')[0]
            roots = zfs.parse_status(pool, doc, status)

            if roots[pool].status != 'UNAVAIL':
                volumes.append({
                    'label': pool,
                    'type': 'zfs',
                    'id': roots.id,
                    'group_type': 'none',
                    'cache': roots['cache'].dump() if roots['cache'] else None,
                    'log': roots['logs'].dump() if roots['logs'] else None,
                    'spare': roots['spares'].dump() if roots['spares'] else None,
                    'disks': roots['data'].dump(),
                    })

        return volumes

    def zfs_import(self, name, id):
        imp = self.__pipeopen('zpool import -f -R /mnt %s' % id)
        stdout, stderr = imp.communicate()
        if imp.returncode == 0:
            # Reset all mountpoints in the zpool
            self.zfs_inherit_option(name, 'mountpoint', True)
            # Remember the pool cache
            self.__system("zpool set cachefile=/data/zfs/zpool.cache %s" % (name))
            # These should probably be options that are configurable from the GUI
            self.__system("zfs set aclmode=passthrough %s" % name)
            self.__system("zfs set aclinherit=passthrough %s" % name)
            return True
        return False

    def volume_detach(self, vol_name, vol_fstype):
        """Detach a volume from the system

        This either executes exports a zpool or umounts a generic volume (e.g.
        NTFS, UFS, etc).

        In the event that the volume is still in use in the OS, the end-result
        is implementation defined depending on the filesystem, and the set of
        commands used to export the filesystem.

        Finally, this method goes and cleans up the mountpoint. This is a
        sanity check to ensure that things are in synch.

        XXX: recursive unmounting / needs for recursive unmounting here might
             be a good idea.
        XXX: better feedback about files in use might be a good idea...
             someday. But probably before getting to this point. This is a
             tricky problem to fix in a way that doesn't unnecessarily suck up
             resources, but also ensures that the user is provided with
             meaningful data.
        XXX: this doesn't work with the alternate mountpoint functionality
             available in UFS volumes.

        Parameters:
            vol_name: a textual name for the volume, e.g. tank, stripe, etc.
            vol_fstype: the filesystem type for the volume; valid values are:
                        'EXT2FS', 'MSDOSFS', 'UFS', 'ZFS'.

        Raises:
            MiddlewareError: the volume could not be detached cleanly.
            MiddlewareError: the volume's mountpoint couldn't be removed.
        """

        vol_mountpath = self.__get_mountpath(vol_name, vol_fstype)
        if vol_fstype == 'ZFS':
            cmds = [ 'zpool export %s' % (vol_name, ) ]
        else:
            cmds = [ 'umount %s' % (vol_mountpath, ) ]

        for cmd in cmds:
            p1 = self.__pipeopen(cmd)
            stdout, stderr = p1.communicate()
            if p1.returncode:
                raise MiddlewareError('Failed to detach %s with "%s" (exited '
                                      'with %d): %s'
                                      % (vol_name, cmd, p1.returncode,
                                         stderr, )) 
        self.__rmdir_mountpoint(vol_mountpath)


    def __rmdir_mountpoint(self, path):
        """Remove a mountpoint directory designated by path

        This only nukes mountpoints that exist in /mnt as alternate mointpoints
        can be specified with UFS, which can take down mission critical
        subsystems.

        This purposely doesn't use shutil.rmtree to avoid removing files that
        were potentially hidden by the mount.

        Parameters:
            path: a path suffixed with /mnt that points to a mountpoint that
                  needs to be nuked.

        XXX: rewrite to work outside of /mnt and handle unmounting of
             non-critical filesystems.
        XXX: remove hardcoded reference to /mnt .

        Raises:
            MiddlewareError: the volume's mountpoint couldn't be removed.
        """

        if path.startswith('/mnt'):
            # UFS can be mounted anywhere. Don't nuke /etc, /var, etc as the
            # underlying contents might contain something of value needed for
            # the system to continue operating.
            try:
                if os.path.isdir(path):
                    os.rmdir(path)
            except OSError as ose:
                raise MiddlewareError('Failed to remove mountpoint %s: %s'
                                      % (path, str(ose), ))


    def zfs_scrub(self, name, stop=False):
        if stop:
            imp = self.__pipeopen('zpool scrub -s %s' % str(name))
        else:
            imp = self.__pipeopen('zpool scrub %s' % str(name))
        stdout, stderr = imp.communicate()
        if imp.returncode != 0:
            raise MiddlewareError('Unable to scrub %s: %s' % (name, stderr))
        return True

    def zfs_snapshot_list(self, path=None):
        fsinfo = dict()

        zfsproc = self.__pipeopen("/sbin/zfs list -t volume -o name -H")
        zvols = filter(lambda y: y != '', zfsproc.communicate()[0].split('\n'))

        if path:
            zfsproc = self.__pipeopen("/sbin/zfs list -r -t snapshot -H -S creation %s" % path)
        else:
            zfsproc = self.__pipeopen("/sbin/zfs list -t snapshot -H -S creation")
        lines = zfsproc.communicate()[0].split('\n')
        for line in lines:
            if line != '':
                list = line.split('\t')
                snapname = list[0]
                used = list[1]
                refer = list[3]
                fs, name = snapname.split('@')
                try:
                    snaplist = fsinfo[fs]
                    mostrecent = False
                except:
                    snaplist = []
                    mostrecent = True
                snaplist.insert(0, dict([('fullname', snapname), ('name', name), ('used', used), ('refer', refer), ('mostrecent', mostrecent), ('parent', 'filesystem' if fs not in zvols else 'volume')]))
                fsinfo[fs] = snaplist
        return fsinfo

    def zfs_mksnap(self, path, name, recursive):
        if recursive:
            p1 = self.__pipeopen("/sbin/zfs snapshot -r %s@%s" % (path, name))
        else:
            p1 = self.__pipeopen("/sbin/zfs snapshot %s@%s" % (path, name))
        if p1.wait() != 0:
            err = p1.communicate()[1]
            raise MiddlewareError("Snapshot could not be taken: %s" % err)
        return True

    def zfs_clonesnap(self, snapshot, dataset):
        zfsproc = self.__pipeopen('zfs clone %s %s' % (snapshot, dataset))
        retval = zfsproc.communicate()[1]
        return retval

    def rollback_zfs_snapshot(self, snapshot):
        zfsproc = self.__pipeopen('zfs rollback %s' % (snapshot))
        retval = zfsproc.communicate()[1]
        return retval

    def config_restore(self):
        os.unlink("/data/freenas-v1.db")
        save_path = os.getcwd()
        os.chdir(FREENAS_PATH)
        self.__system("/usr/local/bin/python manage.py syncdb --noinput --migrate")
        self.__system("/usr/local/bin/python manage.py createadmin")
        os.chdir(save_path)

    def config_upload(self, uploaded_file_fd):
        config_file_name = tempfile.mktemp(dir='/var/tmp/firmware')
        try:
            with open(config_file_name, 'wb') as config_file_fd:
                for chunk in uploaded_file_fd.chunks():
                    config_file_fd.write(chunk)
            conn = sqlite3.connect(config_file_name)
            try:
                cur = conn.cursor()
                cur.execute("""SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name;""")
            finally:
                conn.close()
        except:
            os.unlink(config_file_name)
            return False

        shutil.move(config_file_name, '/data/uploaded.db')
        # Now we must run the migrate operation in the case the db is older
        open(NEED_UPDATE_SENTINEL, 'w+').close()

        return True

    def zfs_get_options(self, name):
        data = {}
        noinherit_fields = ['quota', 'refquota', 'reservation', 'refreservation']
        zfsname = str(name)

        zfsproc = self.__pipeopen("/sbin/zfs get -H -o property,value,source all %s" % (zfsname))
        zfs_output = zfsproc.communicate()[0]
        zfs_output = zfs_output.split('\n')
        retval = {}
        for line in zfs_output:
            if line != "":
                data = line.split('\t')
                if (not data[0] in noinherit_fields) and (data[2] == 'default' or data[2].startswith('inherited')):
                    retval[data[0]] = "inherit"
                else:
                    retval[data[0]] = data[1]
        return retval

    def zfs_set_option(self, name, item, value):
        """
        Set a ZFS attribute using zfs set

        Returns:
            tuple(bool, str)
                bool -> Success?
                str -> Error message in case of error
        """
        name = str(name)
        item = str(item)
        value = str(value)
        zfsproc = self.__pipeopen('zfs set %s=%s "%s"' % (item, value, name))
        err = zfsproc.communicate()[1]
        if zfsproc.returncode == 0:
            return True, None
        return False, err

    def zfs_inherit_option(self, name, item, recursive=False):
        """
        Inherit a ZFS attribute using zfs inherit

        Returns:
            tuple(bool, str)
                bool -> Success?
                str -> Error message in case of error
        """
        name = str(name)
        item = str(item)
        if recursive:
            zfscmd = 'zfs inherit -r %s %s' % (item, name)
        else:
            zfscmd = 'zfs inherit %s %s' % (item, name)
        zfsproc = self.__pipeopen(zfscmd)
        err = zfsproc.communicate()[1]
        if zfsproc.returncode == 0:
            return True, None
        return False, err

    def zfs_dataset_release_snapshots(self, name, recursive=False):
        name = str(name)
        retval = None
        if recursive:
            zfscmd = "/sbin/zfs list -Ht snapshot -o name,freenas:state -r %s" % (name)
        else:
            zfscmd = "/sbin/zfs list -Ht snapshot -o name,freenas:state -r -d 1 %s" % (name)
        try:
            with mntlock(blocking=False) as MNTLOCK:
                zfsproc = self.__pipeopen(zfscmd)
                output = zfsproc.communicate()[0]
                if output != '':
                    snapshots_list = output.splitlines()
                for snapshot_item in filter(None, snapshots_list):
                    snapshot, state = snapshot_item.split('\t')
                    if state != '-':
                        self.zfs_inherit_option(snapshot, 'freenas:state')
        except IOError:
            retval = 'Try again later.'
        return retval

    # Reactivate replication on all snapshots
    def zfs_dataset_reset_replicated_snapshots(self, name, recursive=False):
        name = str(name)
        retval = None
        if recursive:
            zfscmd = "/sbin/zfs list -Ht snapshot -o name,freenas:state -r %s" % (name)
        else:
            zfscmd = "/sbin/zfs list -Ht snapshot -o name,freenas:state -r -d 1 %s" % (name)
        try:
            with mntlock(blocking=False) as MNTLOCK:
                zfsproc = self.__pipeopen(zfscmd)
                output = zfsproc.communicate()[0]
                if output != '':
                    snapshots_list = output.splitlines()
                for snapshot_item in filter(None, snapshots_list):
                    snapshot, state = snapshot_item.split('\t')
                    if state != 'NEW':
                        self.zfs_set_option(snapshot, 'freenas:state', 'NEW')
        except IOError:
            retval = 'Try again later.'
        return retval

    def geom_disk_replace(self, volume, to_disk):
        """Replace disk in ``volume`` for ``to_disk``

        Raises:
            ValueError: Volume not found

        Returns:
            0 if the disk was replaced, > 0 otherwise
        """

        assert volume.vol_fstype == 'UFS'

        provider = self.get_label_consumer('ufs', volume.vol_name)
        if not provider:
            raise ValueError("UFS Volume %s not found" % (volume.vol_name,))
        class_name = provider.xpathEval("../../name")[0].content
        geom_name = provider.xpathEval("../name")[0].content

        if class_name == "MIRROR":
            rv = self.__system_nolog("geom mirror forget %s" % (geom_name,))
            if rv != 0:
                return rv
            p1 = self.__pipeopen("geom mirror insert %s /dev/%s" % (str(geom_name), str(to_disk),))
            stdout, stderr = p1.communicate()
            if p1.returncode != 0:
                error = ", ".join(stderr.split('\n'))
                raise MiddlewareError('Replacement failed: "%s"' % error)
            return 0

        elif class_name == "RAID3":
            numbers = provider.xpathEval("../consumer/config/Number")
            ncomponents =int( provider.xpathEval("../config/Components")[0].content)
            numbers = [int(node.content) for node in numbers]
            lacking = [x for x in xrange(ncomponents) if x not in numbers][0]
            p1 = self.__pipeopen("geom raid3 insert -n %d %s %s" % \
                                        (lacking, str(geom_name), str(to_disk),))
            stdout, stderr = p1.communicate()
            if p1.returncode != 0:
                error = ", ".join(stderr.split('\n'))
                raise MiddlewareError('Replacement failed: "%s"' % error)
            return 0

        return 1

    def iface_destroy(self, name):
        self.__system("ifconfig %s destroy" % name)

    def interface_mtu(self, iface, mtu):
        self.__system("ifconfig %s mtu %s" % (iface, mtu))

    def lagg_remove_port(self, lagg, iface):
        return self.__system_nolog("ifconfig %s -laggport %s" % (lagg, iface))

    def __init__(self):
        self.__confxml = None
        self.__diskserial = {}

    def __geom_confxml(self):
        if self.__confxml == None:
            from libxml2 import parseDoc
            self.__confxml = parseDoc(self.sysctl('kern.geom.confxml'))
        return self.__confxml

    def serial_from_device(self, devname):
        if devname in self.__diskserial:
            return self.__diskserial.get(devname)
        p1 = Popen(["/usr/local/sbin/smartctl", "-i", "/dev/%s" % devname], stdout=PIPE)
        output = p1.communicate()[0]
        search = re.search(r'^Serial Number:[ \t\s]+(?P<serial>.+)', output, re.I|re.M)
        if search:
            serial = search.group("serial")
            self.__diskserial[devname] = serial
            return serial
        return None

    def label_to_disk(self, name):
        """
        Given a label go through the geom tree to find out the disk name
        label = a geom label or a disk partition
        """
        doc = self.__geom_confxml()

        # try to find the provider from GEOM_LABEL
        search = doc.xpathEval("//class[name = 'LABEL']//provider[name = '%s']/../consumer/provider/@ref" % name)
        if len(search) > 0:
            provider = search[0].content
        else:
            # the label does not exist, try to find it in GEOM DEV
            search = doc.xpathEval("//class[name = 'DEV']/geom[name = '%s']//provider/@ref" % name)
            if len(search) > 0:
                provider = search[0].content
            else:
                return None
        search = doc.xpathEval("//provider[@id = '%s']/../name" % provider)
        disk = search[0].content
        return disk

    def device_to_identifier(self, name):
        name = str(name)
        doc = self.__geom_confxml()

        serial = self.serial_from_device(name)
        if serial:
            return "{serial}%s" % serial

        search = doc.xpathEval("//class[name = 'PART']/..//*[name = '%s']//config[type = 'freebsd-zfs']/rawuuid" % name)
        if len(search) > 0:
            return "{uuid}%s" % search[0].content
        search = doc.xpathEval("//class[name = 'PART']/geom/..//*[name = '%s']//config[type = 'freebsd-ufs']/rawuuid" % name)
        if len(search) > 0:
            return "{uuid}%s" % search[0].content

        search = doc.xpathEval("//class[name = 'LABEL']/geom[name = '%s']/provider/name" % name)
        if len(search) > 0:
            return "{label}%s" % search[0].content

        search = doc.xpathEval("//class[name = 'DEV']/geom[name = '%s']" % name)
        if len(search) > 0:
            return "{devicename}%s" % name

        return None

    def identifier_to_device(self, ident):

        if not ident:
            return None

        doc = self.__geom_confxml()

        search = re.search(r'\{(?P<type>.+?)\}(?P<value>.+)', ident)
        if not search:
            return None

        tp = search.group("type")
        value = search.group("value")

        if tp == 'uuid':
            search = doc.xpathEval("//class[name = 'PART']/geom//config[rawuuid = '%s']/../../name" % value)
            if len(search) > 0:
                for entry in search:
                    if not entry.content.startswith("label"):
                        return entry.content
            return None

        elif tp == 'label':
            search = doc.xpathEval("//class[name = 'LABEL']/geom//provider[name = '%s']/../name" % value)
            if len(search) > 0:
                return search[0].content
            return None

        elif tp == 'serial':
            for devname in self.__get_disks():
                serial = self.serial_from_device(devname)
                if serial == value:
                    return devname
            return None

        elif tp == 'devicename':
            search = doc.xpathEval("//class[name = 'DEV']/geom[name = '%s']" % value)
            if len(search) > 0:
                return value
            return None
        else:
            raise NotImplementedError

    def part_type_from_device(self, name, device):
        """
        Given a partition a type and a disk name (adaX)
        get the first partition that matches the type
        """
        doc = self.__geom_confxml()
        #TODO get from MBR as well?
        search = doc.xpathEval("//class[name = 'PART']/geom[name = '%s']//config[type = 'freebsd-%s']/../name" % (device, name))
        if len(search) > 0:
            return search[0].content
        else:
            return ''

    def swap_from_diskid(self, diskid):
        from storage.models import Disk
        disk = Disk.objects.get(id=diskid)
        return self.part_type_from_device('swap', disk.devname)

    def swap_from_identifier(self, ident):
        return self.part_type_from_device('swap', self.identifier_to_device(ident))

    def get_label_consumer(self, geom, name):
        """
        Get the label consumer of a given ``geom`` with name ``name``

        Returns:
            The provider xmlnode if found, None otherwise
        """
        doc = self.__geom_confxml()
        xpath = doc.xpathEval("//class[name = 'LABEL']//provider[name = '%s']/../consumer/provider/@ref" % "%s/%s" % (geom, name))
        if not xpath:
            return None
        providerid = xpath[0].content
        provider = doc.xpathEval("//provider[@id = '%s']" % providerid)[0]

        class_name = provider.xpathEval("../../name")[0].content

        # We've got a GPT over the softraid, not raw UFS filesystem
        # So we need to recurse one more time
        if class_name == 'PART':
            providerid = provider.xpathEval("../consumer/provider/@ref")[0].content
            newprovider = doc.xpathEval("//provider[@id = '%s']" % providerid)[0]
            class_name = newprovider.xpathEval("../../name")[0].content
            # if this PART is really backed up by softraid the hypothesis was correct
            if class_name in ('STRIPE', 'MIRROR', 'RAID3'):
                return newprovider

        return provider

    def get_disks_from_provider(self, provider):
        disks = []
        geomname = provider.xpathEval("../../name")[0].content
        if geomname in ('DISK', 'PART'):
            disks.append(provider.xpathEval("../name")[0].content)
        elif geomname in ('STRIPE', 'MIRROR', 'RAID3'):
            doc = self.__geom_confxml()
            for prov in provider.xpathEval("../consumer/provider/@ref"):
                prov2 = doc.xpathEval("//provider[@id = '%s']" % prov.content)[0]
                disks.append(prov2.xpathEval("../name")[0].content)
        else:
            #TODO log, could not get disks
            pass
        return disks

    def zpool_parse(self, name):
        doc = self.__geom_confxml()
        p1 = self.__pipeopen("zpool status %s" % name)
        res = p1.communicate()[0]
        parse = zfs.parse_status(name, doc, res)
        return parse

    def sync_disk(self, devname):
        from storage.models import Disk

        self.__diskserial.clear()

        ident = self.device_to_identifier(devname)
        qs = Disk.objects.filter(disk_identifier=ident)
        if qs.exists():
            disk = qs[0]
            disk.disk_name = devname
            disk.disk_enabled = True
        else:
            qs = Disk.objects.filter(disk_name=devname)
            if qs.exists():
                disk = qs[0]
                if qs.count() > 1:
                    Disk.objects.filter(disk_name=devname).exclude(self=disk).delete()
            else:
                disk = Disk()
            disk.disk_name = devname
            disk.disk_identifier = ident
            disk.disk_enabled = True
            disk.disk_serial = self.serial_from_device(devname) or ''
        disk.save()

    def sync_disks(self):
        from storage.models import Disk

        disks = self.__get_disks()
        self.__diskserial.clear()

        in_disks = {}
        serials = []
        for disk in Disk.objects.all():

            dskname = self.identifier_to_device(disk.disk_identifier)
            if not dskname:
                dskname = disk.disk_name
                disk.disk_identifier = self.device_to_identifier(dskname)
                if not disk.disk_identifier:
                    disk.disk_enabled = False
                else:
                    disk.disk_enabled = True
                    disk.disk_serial = self.serial_from_device(dskname) or ''
            elif dskname in in_disks:
                # We are probably dealing with with multipath here
                disk.delete()
                continue
            else:
                disk.disk_enabled = True
                if dskname != disk.disk_name:
                    disk.disk_name = dskname

            if disk.disk_serial:
                serials.append(disk.disk_serial)

            if dskname not in disks:
                disk.disk_enabled = False
                if disk._original_state.get("disk_enabled"):
                    disk.save()
                else:
                    #Duplicated disk entries in database
                    disk.delete()
            else:
                disk.save()
            in_disks[dskname] = disk

        for disk in disks:
            if disk not in in_disks:
                d = Disk()
                d.disk_name = disk
                d.disk_identifier = self.device_to_identifier(disk)
                d.disk_serial = self.serial_from_device(disk) or ''
                if d.disk_serial:
                    if d.disk_serial in serials:
                        #Probably dealing with multipath here, do not add another
                        continue
                    else:
                        serials.append(d.disk_serial)
                d.save()

    def geom_disks_dump(self, volume):
        """
        Raises:
            ValueError: UFS volume not found
        """
        #FIXME: This should not be here
        from django.core.urlresolvers import reverse
        from django.utils import simplejson
        from storage.models import Disk
        provider = self.get_label_consumer('ufs', volume.vol_name)
        if not provider:
            raise ValueError("UFS Volume %s not found" % (volume,))
        class_name = provider.xpathEval("../../name")[0].content

        items = []
        uid = 1
        if class_name in ('MIRROR', 'RAID3', 'STRIPE'):
            if class_name == 'STRIPE':
                statepath = "../config/State"
                status = provider.xpathEval("../config/Status")[0].content
                ncomponents = int(re.search(r'Total=(?P<total>\d+)', status).group("total"))
            else:
                statepath = "./config/State"
                ncomponents = int(provider.xpathEval("../config/Components")[0].content)
            consumers = provider.xpathEval("../consumer")
            doc = self.__geom_confxml()
            for consumer in consumers:
                provid = consumer.xpathEval("./provider/@ref")[0].content
                status = consumer.xpathEval(statepath)[0].content
                name = doc.xpathEval("//provider[@id = '%s']/../name" % provid)[0].content
                qs = Disk.objects.filter(disk_name=name).order_by('disk_enabled')
                if qs:
                    actions = {'edit_url': reverse('freeadmin_model_edit',
                        kwargs={
                        'app':'storage',
                        'model': 'Disk',
                        'oid': qs[0].id,
                        })+'?deletable=false'}
                else:
                    actions = {}
                items.append({
                    'type': 'disk',
                    'name': name,
                    'id': uid,
                    'status': status,
                    'actions': simplejson.dumps(actions),
                })
                uid += 1
            for i in xrange(len(consumers), ncomponents):
                #FIXME: This should not be here
                actions = {
                    'replace_url': reverse('storage_geom_disk_replace', kwargs={'vname': volume.vol_name})
                }
                items.append({
                    'type': 'disk',
                    'name': 'UNAVAIL',
                    'id': uid,
                    'status': 'UNAVAIL',
                    'actions': simplejson.dumps(actions),
                })
                uid += 1
        elif class_name == 'PART':
            name = provider.xpathEval("../name")[0].content
            qs = Disk.objects.filter(disk_name=name).order_by('disk_enabled')
            if qs:
                actions = {'edit_url': reverse('freeadmin_model_edit',
                    kwargs={
                    'app':'storage',
                    'model': 'Disk',
                    'oid': qs[0].id,
                    })+'?deletable=false'}
            else:
                actions = {}
            items.append({
                'type': 'disk',
                'name': name,
                'id': uid,
                'status': 'ONLINE',
                'actions': simplejson.dumps(actions),
            })
        return items

    def multipath_all(self):
        """
        Get all available gmultipath instances

        Returns:
            A list of Multipath objects
        """
        from middleware.multipath import Multipath
        doc = self.__geom_confxml()
        return [Multipath(doc=doc, xmlnode=geom) \
                for geom in doc.xpathEval("//class[name = 'MULTIPATH']/geom")
            ]

    def multipath_create(self, name, consumers):
        """
        Create an Active/Passive GEOM_MULTIPATH provider
        with name ``name`` using ``consumers`` as the consumers for it

        Returns:
            True in case the label succeeded and False otherwise
        """
        p1 = subprocess.Popen(["/sbin/gmultipath", "label", name] + consumers, stdout=subprocess.PIPE)
        if p1.wait() != 0:
            return False
        # We need to invalidate confxml cache
        self.__confxml = None
        return True

    def multipath_next(self):
        """
        Find out the next available name for a multipath named diskX
        where X is a crescenting value starting from 1

        Returns:
            The string of the multipath name to be created
        """
        RE_NAME = re.compile(r'[a-z]+(\d+)')
        numbers = sorted([int(RE_NAME.search(mp.name).group(1)) \
                        for mp in self.multipath_all() if RE_NAME.match(mp.name)
                        ])
        if not numbers:
            numbers = [0]
        for number in xrange(1, numbers[-1]+2):
            if number not in numbers:
                break
        else:
            raise ValueError('Could not find multipaths')
        return "disk%d" % number

    def multipath_sync(self):
        """Synchronize multipath disks

        Every distinct GEOM_DISK that shares an ident (aka disk serial)
        is considered a multpath and will be handled by GEOM_MULTIPATH

        If the disk is not currently in use by some Volume or iSCSI Disk Extent
        then a gmultipath is automatically created and will be available for use
        """
        from freenasUI.storage.models import Volume, Disk

        doc = self.__geom_confxml()

        mp_disks = []
        for geom in doc.xpathEval("//class[name = 'MULTIPATH']/geom"):
            for provref in geom.xpathEval("./consumer/provider/@ref"):
                prov = doc.xpathEval("//provider[@id = '%s']" % provref.content)[0]
                class_name = prov.xpathEval("../../name")[0].content
                #For now just DISK is allowed
                if class_name != 'DISK':
                    continue
                disk = prov.xpathEval("../name")[0].content
                mp_disks.append(disk)

        reserved = [self.__find_root_dev()]

        # disks already in use count as reserved as well
        for vol in Volume.objects.all():
            reserved.extend(vol.get_disks())

        disks = []
        serials = {}
        RE_CD = re.compile('^cd[0-9]')
        for geom in doc.xpathEval("//class[name = 'DISK']/geom"):
            name = geom.xpathEval("./name")[0].content
            if RE_CD.match(name) or name in reserved or name in mp_disks:
                continue
            serial = self.serial_from_device(name)
            if not serial:
                disks.append(name)
            else:
                if not serials.has_key(serial):
                    serials[serial] = [name]
                else:
                    serials[serial].append(name)

        disks = sorted(disks)

        for serial, disks in serials.items():
            if not len(disks) > 1:
                continue
            name = self.multipath_next()
            self.multipath_create(name, disks)

        # Grab confxml again to take new multipaths into account
        doc = self.__geom_confxml()
        mp_ids = []
        for geom in doc.xpathEval("//class[name = 'MULTIPATH']/geom"):
            _disks = []
            for provref in geom.xpathEval("./consumer/provider/@ref"):
                prov = doc.xpathEval("//provider[@id = '%s']" % provref.content)[0]
                class_name = prov.xpathEval("../../name")[0].content
                #For now just DISK is allowed
                if class_name != 'DISK':
                    continue
                disk = prov.xpathEval("../name")[0].content
                _disks.append(disk)
            qs = Disk.objects.filter(
                Q(disk_name__in=_disks)|Q(disk_multipath_member__in=_disks)
                )
            if qs.exists():
                diskobj = qs[0]
                mp_ids.append(diskobj.id)
                diskobj.disk_multipath_name = geom.xpathEval("./name")[0].content
                if diskobj.disk_name in _disks:
                    _disks.remove(diskobj.disk_name)
                if _disks:
                    diskobj.disk_multipath_member = _disks.pop()
                diskobj.save()

        Disk.objects.exclude(id__in=mp_ids).update(disk_multipath_name='', disk_multipath_member='')


    def __find_root_dev(self):
        """Find the root device.

        The original algorithm was adapted from /root/updatep*, but this
        grabs the relevant information from geom's XML facility.

        Returns:
             The root device name in string format, e.g. FreeNASp1,
             FreeNASs2, etc.

        Raises:
             AssertionError: the root device couldn't be determined.
        """
        # XXX: circular dependency
        import common.system

        sw_name = common.system.get_sw_name()
        doc = self.__geom_confxml()

        for pref in doc.xpathEval("//class[name = 'LABEL']/geom/provider[" \
                "starts-with(name, 'ufs/%s')]/../consumer/provider/@ref" \
                % (sw_name, )):
            prov = doc.xpathEval("//provider[@id = '%s']" % pref.content)[0]
            pid = prov.xpathEval("../consumer/provider/@ref")[0].content
            prov = doc.xpathEval("//provider[@id = '%s']" % pid)[0]
            name = prov.xpathEval("../name")[0].content
            return name
        raise AssertionError('Root device not found (!)')


    def __get_disks(self):
        """Return a list of available storage disks.

        The list excludes all devices that cannot be reserved for storage,
        e.g. the root device, CD drives, etc.

        Returns:
            A list of available devices (ada0, da0, etc), or an empty list if
            no devices could be divined from the system.
        """

        disks = self.sysctl('kern.disks').split()
        disks.reverse()

        root_dev = self.__find_root_dev()

        device_blacklist_re = re.compile('(a?cd[0-9]+|%s)' % (root_dev, ))

        return filter(lambda x: not device_blacklist_re.match(x), disks)


    def kern_module_is_loaded(self, module):
        """Determine whether or not a kernel module (or modules) is loaded.

        Parameter:
            module_name - a module to look for in kldstat -v output (.ko is
                          added automatically for you).

        Returns:
            A boolean to denote whether or not the module was found.
        """

        pipe = self.__pipeopen('/sbin/kldstat -v')

        return 0 < pipe.communicate()[0].find(module + '.ko')


    def zfs_get_version(self):
        """Get the ZFS (SPA) version reported via zfs(4).

        This allows us to better tune warning messages and provide
        conditional support for features in the GUI/CLI.

        Returns:
            An integer corresponding to the version retrieved from zfs(4) or
            0 if the module hasn't been loaded.

        Raises:
            ValueError: the ZFS version could not be parsed from sysctl(8).
        """

        if not self.kern_module_is_loaded('zfs'):
            return 0

        try:
            version = self.sysctl('vfs.zfs.version.spa', _type='INT')
        except ValueError, ve:
            raise ValueError('Could not determine ZFS version: %s'
                             % (str(ve), ))
        if 0 < version:
            return version
        raise ValueError('Invalid ZFS (SPA) version: %d' % (version, ))

    def __sysctl_error(self, libc, name):
        errloc = getattr(libc,'__error')
        errloc.restype = ctypes.POINTER(ctypes.c_int)
        error = errloc().contents.value
        if error == errno.ENOENT:
            msg = "The name is unknown."
        elif error == errno.ENOMEM:
            msg = "The length pointed to by oldlenp is too short to hold " \
                  "the requested value."
        else:
            msg = "Unknown error (%d)" % (error, )
        raise AssertionError("Sysctl by name (%s) failed: %s" % (name, msg))

    def sysctl(self, name, value=None, _type='CHAR'):
        """Get any sysctl value using libc call

        This cut down the overhead of launching subprocesses

        XXX: reimplment with a C extension because ctypes.CDLL can be leaky and
             has a tendency to crash given the right inputs.

        Returns:
            The value of the given ``name'' sysctl

        Raises:
            AssertionError: sysctlbyname(3) returned an error
        """

        log.debug("sysctlbyname: %s", name)

        if value:
            #TODO: set sysctl
            raise NotImplementedError

        libc = ctypes.CDLL('libc.so.7')
        size = ctypes.c_size_t()

        if _type == 'CHAR':
            #We need find out the size
            rv = libc.sysctlbyname(str(name), None, ctypes.byref(size), None, 0)
            if rv != 0:
                self.__sysctl_error(libc, name)

            buf = ctypes.create_string_buffer(size.value)
            arg = buf

        else:
            buf = ctypes.c_int()
            size.value = ctypes.sizeof(buf)
            arg = ctypes.byref(buf)

        # Grab the sysctl value
        rv = libc.sysctlbyname(str(name), arg, ctypes.byref(size), None, 0)
        if rv != 0:
            self.__sysctl_error(libc, name)

        return buf.value

    def staticroute_delete(self, sr):
        """
        Delete a static route from the route table

        Raises:
            MiddlewareError in case the operation failed
        """
        import ipaddr
        netmask = ipaddr.IPNetwork(sr.sr_destination)
        masked = netmask.masked().compressed
        p1 = self.__pipeopen("/sbin/route delete %s" % masked)
        if p1.wait() != 0:
            raise MiddlewareError("Failed to remove the route %s" % sr.sr_destination)

    def mount_volume(self, volume):
        """
        Mount a volume.
        The volume must be in /etc/fstab

        Returns:
            True if volume was sucessfully mounted, False otherwise
        """
        if volume.vol_fstype == 'ZFS':
            raise NotImplementedError("No donuts for you!")

        prov = self.get_label_consumer(volume.vol_fstype.lower(),
            str(volume.vol_name))
        if not prov:
            return False

        proc = self.__pipeopen("mount /dev/%s/%s" % (
            volume.vol_fstype.lower(),
            volume.vol_name,
            ))
        if proc.wait() != 0:
            return False
        return True

def usage():
    usage_str = """usage: %s action command
    Action is one of:
        start: start a command
        stop: stop a command
        restart: restart a command
        reload: reload a command (try reload; if unsuccessful do restart)
        change: notify change for a command (try self.reload; if unsuccessful do start)""" \
        % (os.path.basename(sys.argv[0]), )
    sys.exit(usage_str)

# When running as standard-alone script
if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage()
    else:
        n = notifier()
        f = getattr(n, sys.argv[1], None)
        if f is None:
            sys.stderr.write("Unknown action: %s\n" % sys.argv[1])
            usage()
        print f(*sys.argv[2:])
