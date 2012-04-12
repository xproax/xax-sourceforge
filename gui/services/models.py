#+
# Copyright 2010 iXsystems, Inc.
# All rights reserved
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted providing that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
#####################################################################
import datetime
import hashlib
import hmac
import uuid

from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.core.validators import (MinValueValidator, MaxValueValidator,
    RegexValidator)

# Do not change import path to do not cause unnecessary migration
from freeadmin.models import Model, UserField, GroupField, PathField

from freenasUI import choices
from freenasUI.middleware.notifier import notifier
from freenasUI.network.models import Alias
from freenasUI.services.exceptions import ServiceFailed
from freenasUI.storage.models import Volume, Disk


class services(Model):
    srv_service = models.CharField(
            max_length=120,
            verbose_name=_("Service"),
            help_text=_("Name of Service, should be auto-generated at build time")
            )
    srv_enable = models.BooleanField(
            verbose_name=_("Enable Service"))

    class Meta:
        verbose_name = _("Services")
        verbose_name_plural = _("Services")

    def __unicode__(self):
        return self.srv_service

    def save(self, *args, **kwargs):
        super(services, self).save(*args, **kwargs)


class CIFS(Model):
    cifs_srv_authmodel = models.CharField(
            max_length=10,
            choices=choices.CIFSAUTH_CHOICES,
            verbose_name=_("Authentication Model"),
            help_text=_("Using Active Directory or LDAP authentication will supersede this option"),
            )
    cifs_srv_netbiosname = models.CharField(
            max_length=120,
            verbose_name=_("NetBIOS name")
            )
    cifs_srv_workgroup = models.CharField(
            max_length=120,
            verbose_name=_("Workgroup"),
            help_text=_("Workgroup the server will appear to be in when queried by clients (maximum 15 characters).")
            )
    cifs_srv_description = models.CharField(
            max_length=120,
            verbose_name=_("Description"),
            blank=True,
            help_text=_("Server description. This can usually be left blank.")
            )
    cifs_srv_doscharset = models.CharField(
            max_length=120,
            choices=choices.DOSCHARSET_CHOICES,
            default = "CP437",
            verbose_name=_("DOS charset")
            )
    cifs_srv_unixcharset = models.CharField(
            max_length=120,
            choices=choices.UNIXCHARSET_CHOICES,
            default = "UTF-8",
            verbose_name=_("UNIX charset")
            )
    cifs_srv_loglevel = models.CharField(
            max_length=120,
            choices=choices.LOGLEVEL_CHOICES,
            default=choices.LOGLEVEL_CHOICES[0][0],
            verbose_name=_("Log level")
            )
    cifs_srv_localmaster = models.BooleanField(
            verbose_name=_("Local Master"))
    cifs_srv_timeserver = models.BooleanField(
            verbose_name=_("Time Server for Domain"))
    cifs_srv_guest = UserField(
            max_length=120,
            default="nobody",
            exclude=["root"],
            verbose_name=_("Guest account"),
            help_text=_("Use this option to override the username ('nobody' by default) which will be used for access to services which are specified as guest. Whatever privileges this user has will be available to any client connecting to the guest service. This user must exist in the password file, but does not require a valid login. The user root can not be used as guest account.")
            )
    cifs_srv_filemask = models.CharField(
            max_length=120,
            verbose_name=_("File mask"),
            blank=True,
            help_text=_("Use this option to override the file creation mask (0666 by default).")
            )
    cifs_srv_dirmask = models.CharField(
            max_length=120,
            verbose_name=_("Directory mask"),
            blank=True,
            help_text=_("Use this option to override the directory creation mask (0777 by default).")
            )
    cifs_srv_largerw = models.BooleanField(
            verbose_name=_("Large RW support"))
    cifs_srv_sendfile = models.BooleanField(
            verbose_name=_("Send files with sendfile(2)"))
    cifs_srv_easupport = models.BooleanField(
            verbose_name=_("EA Support"))
    cifs_srv_dosattr = models.BooleanField(
            verbose_name=_("Support DOS File Attributes"))
    cifs_srv_nullpw = models.BooleanField(
            verbose_name=_("Allow Empty Password"))
    cifs_srv_smb_options = models.TextField(
            verbose_name=_("Auxiliary parameters"),
            blank=True,
            help_text=_("These parameters are added to [global] section of smb.conf")
            )
    cifs_srv_homedir_enable = models.BooleanField(
            verbose_name=_("Enable home directories"),
            help_text=_("Enable/disable home directories for samba user.")
            )
    cifs_srv_homedir_browseable_enable = models.BooleanField(
            verbose_name=_("Enable home directories browsing"),
            help_text=_("Enable/disable home directories browsing for samba user."),
            default=False,
            )
    cifs_srv_homedir = PathField(
            verbose_name=_("Home directories"),
            blank=True,
            )
    cifs_srv_homedir_aux = models.TextField(
            verbose_name=_("Homes auxiliary parameters"),
            blank=True,
            help_text=_("These parameters are added to [homes] section of smb.conf")
            )
    cifs_srv_unixext = models.BooleanField(
            verbose_name=_("Unix Extensions"),
            default=True,
            help_text=_("These extensions enable Samba to better serve UNIX CIFS clients by supporting features such as symbolic links, hard links, etc..."),
            )
    cifs_srv_aio_enable = models.BooleanField(
            default=False,
            verbose_name=_("Enable AIO"),
            help_text=_("Enable/disable AIO support.")
            )
    cifs_srv_aio_rs = models.IntegerField(
            max_length=120,
            verbose_name=_("Minimum AIO read size"),
            help_text=_("Samba will read asynchronously if request size is larger than this value."),
            default=4096,
            )
    cifs_srv_aio_ws = models.IntegerField(
            max_length=120,
            verbose_name=_("Minimum AIO write size"),
            help_text=_("Samba will write asynchronously if request size is larger than this value."),
            default=4096,
            )
    cifs_srv_zeroconf = models.BooleanField(
            verbose_name=_("Zeroconf share discovery"),
            default=True,
            help_text=_("Zeroconf support via Avahi allows clients (the Mac OSX finder in particular) to automatically discover the CIFS shares on the system similar to the Computer Browser service in Windows."),
            )

    class Meta:
        verbose_name = _(u"CIFS")
        verbose_name_plural = _(u"CIFS")

    class FreeAdmin:
        deletable = False
        icon_model = u"CIFSIcon"

class AFP(Model):
    afp_srv_name = models.CharField(
            max_length=120,
            verbose_name=_("Server Name"),
            help_text=_("Name of the server. If this field is left empty the default server is specified.")
            )
    afp_srv_guest = models.BooleanField(
            verbose_name=_("Guest Access"),
            help_text=_("Allows guest access to all apple shares on this box.")
            )
    afp_srv_guest_user = UserField(
            max_length=120,
            default="nobody",
            exclude=["root"],
            verbose_name=_("Guest account"),
            help_text=_("Use this option to override the username ('nobody' by default) which will be used for access to services which are specified as guest. Whatever privileges this user has will be available to any client connecting to the guest service. This user must exist in the password file, but does not require a valid login. The user root can not be used as guest account.")
            )
    afp_srv_connections_limit = models.IntegerField(
            max_length=120,
            verbose_name=_('Max. Connections'),
            validators=[MinValueValidator(1), MaxValueValidator(1000)],
            help_text=_('Maximum number of connections permitted via AFP. The default limit is 50.'),
            default=50,
            )

    class Meta:
        verbose_name = _(u"AFP")
        verbose_name_plural = _(u"AFP")

    class FreeAdmin:
        deletable = False
        icon_model = u"AFPIcon"

class NFS(Model):
    nfs_srv_servers = models.PositiveIntegerField(
            default=4,
            verbose_name=_("Number of servers"),
            help_text=_("Specifies how many servers to create. There should be enough to handle the maximum level of concurrency from its clients, typically four to six.")
            )
    nfs_srv_async = models.BooleanField(
            default = False,
            verbose_name = _("Asynchronous mode"),
            help_text = _("Enable asynchronous mode, which will help "
                          "performance beyond gigabit network speed.")
            )

    class Meta:
        verbose_name = _("NFS")
        verbose_name_plural = _("NFS")

    class FreeAdmin:
        deletable = False
        icon_model = u"NFSIcon"

class iSCSITargetGlobalConfiguration(Model):
    iscsi_basename = models.CharField(
            max_length=120,
            verbose_name=_("Base Name"),
            help_text=_("The base name (e.g. iqn.2007-09.jp.ne.peach.istgt, see RFC 3720 and 3721 for details) will append the target name that is not starting with 'iqn.'")
            )
    iscsi_discoveryauthmethod = models.CharField(
            max_length=120,
            choices=choices.AUTHMETHOD_CHOICES,
            default='Auto',
            verbose_name=_("Discovery Auth Method")
            )
    iscsi_discoveryauthgroup = models.IntegerField(
            max_length=120,
            verbose_name=_("Discovery Auth Group"),
            blank=True,
            null=True,
            )
    iscsi_iotimeout = models.IntegerField(
            max_length=120,
            default=30,
            verbose_name=_("I/O Timeout"),
            help_text=_("I/O timeout in seconds (30 by default).")
            )
    iscsi_nopinint = models.IntegerField(
            max_length=120,
            default=20,
            verbose_name=_("NOPIN Interval"),
            help_text=_("NOPIN sending interval in seconds (20 by default).")
            )
    iscsi_maxsesh = models.IntegerField(
            max_length=120,
            default=16,
            verbose_name=_("Max. sessions"),
            help_text=_("Maximum number of sessions holding at same time (16 by default).")
            )
    iscsi_maxconnect = models.IntegerField(
            max_length=120,
            default=8,
            verbose_name=_("Max. connections"),
            help_text=_("Maximum number of connections in each session (8 by default).")
            )
    iscsi_r2t = models.IntegerField(
            max_length=120,
            default=32,
            verbose_name=_("Max. pre-send R2T"),
            help_text=_("Maximum number of pre-send R2T in each connection (32 by default). The actual number is limited to QueueDepth of the target."),
            )
    iscsi_maxoutstandingr2t = models.IntegerField(
            max_length=120,
            default=16,
            verbose_name=_("MaxOutstandingR2T"),
            help_text=_("iSCSI initial parameter (16 by default).")
            )
    iscsi_firstburst = models.IntegerField(
            max_length=120,
            default=65536,
            verbose_name=_("First burst length"),
            help_text=_("iSCSI initial parameter (65536 by default).")
            )
    iscsi_maxburst = models.IntegerField(
            max_length=120,
            default=262144,
            verbose_name=_("Max burst length"),
            help_text=_("iSCSI initial parameter (262144 by default).")
            )
    iscsi_maxrecdata = models.IntegerField(
            max_length=120,
            default=262144,
            verbose_name=_("Max receive data segment length"),
            help_text=_("iSCSI initial parameter (262144 by default).")
            )
    iscsi_defaultt2w = models.IntegerField(
            max_length=120,
            default=2,
            verbose_name=_("DefaultTime2Wait"),
            help_text=_("iSCSI initial parameter (2 by default).")
            )
    iscsi_defaultt2r = models.IntegerField(
            max_length=120,
            default=60,
            verbose_name=_("DefaultTime2Retain"),
            help_text=_("iSCSI initial parameter (60 by default)."),
            )
    # TODO: This should not be here.  When enabled, all these fields became mandatory.
    iscsi_toggleluc = models.BooleanField(
            default=False,
            verbose_name=_("Enable LUC"))
    iscsi_lucip =  models.IPAddressField(
            max_length=120,
            default = "127.0.0.1",
            verbose_name=_("Controller IP address"),
            help_text=_("Logical Unit Controller IP address (127.0.0.1(localhost) by default)"),
            blank=True,
            )
    iscsi_lucport =  models.IntegerField(
            default=3261,
            verbose_name=_("Controller TCP port"),
            help_text=_("Logical Unit Controller TCP port (3261 by default)"),
            blank=True,
            null=True,
            )
    iscsi_luc_authnetwork = models.CharField(
            max_length=120,
            verbose_name=_("Controller Authorized Network"),
            default="127.0.0.0/8",
            help_text=_("Logical Unit Controller Authorized netmask "
                "(127.0.0.0/8 by default)"),
            blank=True,
            )
    iscsi_luc_authmethod = models.CharField(
            max_length=120,
            choices=choices.AUTHMETHOD_CHOICES,
            default="chap",
            verbose_name=_("Controller Auth Method"),
            help_text=_("The method can be accepted in the controller."),
            blank=True,
            )
    iscsi_luc_authgroup = models.IntegerField(
            max_length=120,
            verbose_name=_("Controller Auth Group"),
            help_text=_("The istgtcontrol can access the targets with correct "
                "user and secret in specific Auth Group."),
            blank=True,
            null=True,
            )

    class Meta:
        verbose_name = _(u"Target Global Configuration")
        verbose_name_plural = _(u"Target Global Configuration")

    class FreeAdmin:
        deletable = False
        menu_child_of = "services.ISCSI"
        icon_model = u"SettingsIcon"
        nav_extra = {'type': 'iscsi'}


class iSCSITargetExtent(Model):
    iscsi_target_extent_name = models.CharField(
            max_length=120,
            unique=True,
            verbose_name = _("Extent Name"),
            help_text = _("String identifier of the extent."),
            )
    iscsi_target_extent_type = models.CharField(
            max_length=120,
            verbose_name = _("Extent Type"),
            help_text = _("Type used as extent."),
            choices=choices.ISCSI_TARGET_EXTENT_TYPE_CHOICES,
            )
    iscsi_target_extent_path = models.CharField(
            max_length=120,
            verbose_name = _("Path to the extent"),
            help_text = _("File path (e.g. /mnt/sharename/extent/extent0) used as extent."),
            )
    iscsi_target_extent_filesize = models.CharField(
            max_length=120,
            default=0,
            verbose_name = _("Extent size"),
            help_text = _("Size of extent, 0 means auto, a raw number is bytes, or suffix with KB, MB, TB for convenience."),
            )
    iscsi_target_extent_comment = models.CharField(
            blank=True,
            max_length=120,
            verbose_name = _("Comment"),
            help_text = _("You may enter a description here for your reference."),
            )
    class Meta:
        verbose_name = _("Extent")
    class FreeAdmin:
        delete_form = "ExtentDelete"
        delete_form_filter = {'iscsi_target_extent_type__exact': 'File'} #FIXME hack for DevExtent
        menu_child_of = "services.ISCSI"
        icon_object = u"ExtentIcon"
        icon_model = u"ExtentIcon"
        icon_add = u"AddExtentIcon"
        icon_view = u"ViewAllExtentsIcon"

    def __unicode__(self):
        return unicode(self.iscsi_target_extent_name)

    def get_device(self):
        if self.iscsi_target_extent_type not in ("Disk", "ZVOL"):
            return self.iscsi_target_extent_path
        else:
            try:
                disk = Disk.objects.get(id=self.iscsi_target_extent_path)
                if disk.disk_multipath_name:
                    return "/dev/%s" % disk.devname
                else:
                    return "/dev/%s" % notifier().identifier_to_device(disk.disk_identifier)
            except:
                return self.iscsi_target_extent_path

    def delete(self):
        if self.iscsi_target_extent_type in ("Disk", "ZVOL"):
            try:
                disk = Disk.objects.get(id=self.iscsi_target_extent_path)
                if self.iscsi_target_extent_type == "Disk":
                    devname = disk.identifier_to_device()
                    if devname:
                        notifier().unlabel_disk(disk.identifier_to_device())
                        notifier().sync_disk(devname)
                    else:
                        disk.disk_enabled = False
                        disk.save()
                expected_iscsi_volume_name = 'iscsi:' + self.iscsi_target_extent_name
                vol = Volume.objects.get(vol_name = expected_iscsi_volume_name)
                vol.delete()
            except:
                pass

        for te in iSCSITargetToExtent.objects.filter(iscsi_extent=self):
            te.delete()
        super(iSCSITargetExtent, self).delete()

class iSCSITargetPortal(Model):
    iscsi_target_portal_tag = models.IntegerField(
            max_length=120,
            default=1,
            verbose_name = _("Portal Group ID"),
            )
    iscsi_target_portal_comment = models.CharField(
            max_length=120,
            blank=True,
            verbose_name = _("Comment"),
            help_text = _("You may enter a description here for your reference.")
            )

    class Meta:
        verbose_name = _("Portal")

    class FreeAdmin:
        menu_child_of = "services.ISCSI"
        icon_object = u"PortalIcon"
        icon_model = u"PortalIcon"
        icon_add = u"AddPortalIcon"
        icon_view = u"ViewAllPortalsIcon"
        inlines = [
            {
                'form': 'iSCSITargetPortalIPForm',
                'prefix': 'portalip_set',
            },
        ]

    def __unicode__(self):
        if self.iscsi_target_portal_comment != "":
            return u"%s (%s)" % (self.iscsi_target_portal_tag, self.iscsi_target_portal_comment)
        else:
            return unicode(self.iscsi_target_portal_tag)

    def delete(self):
        super(iSCSITargetPortal, self).delete()
        portals = iSCSITargetPortal.objects.all().order_by('iscsi_target_portal_tag')
        for portal, idx in zip(portals, xrange(1, len(portals) + 1)):
            portal.iscsi_target_portal_tag = idx
            portal.save()
        started = notifier().reload("iscsitarget")
        if started is False and services.objects.get(srv_service='iscsitarget').srv_enable:
            raise ServiceFailed("iscsitarget", _("The iSCSI service failed to reload."))

class iSCSITargetPortalIP(Model):
    iscsi_target_portalip_portal = models.ForeignKey(
            iSCSITargetPortal,
            verbose_name=_("Portal"),
            )
    iscsi_target_portalip_ip =  models.IPAddressField(
            verbose_name=_("IP Address"),
            )
    iscsi_target_portalip_port =  models.SmallIntegerField(
            verbose_name=_("Port"),
            default=3260,
            validators=[MinValueValidator(1), MaxValueValidator(65535)],
            )

    class Meta:
        unique_together = (
            ('iscsi_target_portalip_ip', 'iscsi_target_portalip_port'),
            )
        verbose_name = _("Portal IP")

class iSCSITargetAuthorizedInitiator(Model):
    iscsi_target_initiator_tag = models.IntegerField(
            default=1,
            unique=True,
            verbose_name = _("Group ID"),
            )
    iscsi_target_initiator_initiators = models.TextField(
            max_length=2048,
            verbose_name = _("Initiators"),
            default = "ALL",
            help_text = _("Initiator authorized to access to the iSCSI target. It takes a name or 'ALL' for any initiators.")
            )
    iscsi_target_initiator_auth_network = models.TextField(
            max_length=2048,
            verbose_name = _("Authorized network"),
            default = "ALL",
            help_text = _("Network authorized to access to the iSCSI target. It takes IP or CIDR addresses or 'ALL' for any IPs.")
            )
    iscsi_target_initiator_comment = models.CharField(
            max_length=120,
            blank=True,
            verbose_name = _("Comment"),
            help_text = _("You may enter a description here for your reference.")
            )

    class Meta:
        verbose_name = _("Initiator")

    class FreeAdmin:
        menu_child_of = "services.ISCSI"
        icon_object = u"InitiatorIcon"
        icon_model = u"InitiatorIcon"
        icon_add = u"AddInitiatorIcon"
        icon_view = u"ViewAllInitiatorsIcon"

    def __unicode__(self):
        if self.iscsi_target_initiator_comment != "":
            return u"%s (%s)" % (self.iscsi_target_initiator_tag, self.iscsi_target_initiator_comment)
        else:
            return unicode(self.iscsi_target_initiator_tag)

    def delete(self):
        super(iSCSITargetAuthorizedInitiator, self).delete()
        portals = iSCSITargetAuthorizedInitiator.objects.all().order_by('iscsi_target_initiator_tag')
        idx = 1
        for portal in portals:
            portal.iscsi_target_initiator_tag = idx
            portal.save()
            idx += 1

class iSCSITargetAuthCredential(Model):
    iscsi_target_auth_tag = models.IntegerField(
            default=1,
            verbose_name = _("Group ID"),
            )
    iscsi_target_auth_user = models.CharField(
            max_length=120,
            verbose_name = _("User"),
            help_text = _("Target side user name. It is usually the initiator name by default."),
            )
    iscsi_target_auth_secret = models.CharField(
            max_length=120,
            verbose_name = _("Secret"),
            help_text = _("Target side secret."),
            )
    iscsi_target_auth_peeruser = models.CharField(
            max_length=120,
            blank=True,
            verbose_name = _("Peer User"),
            help_text = _("Initiator side secret. (for mutual CHAP authentication)"),
            )
    iscsi_target_auth_peersecret = models.CharField(
            max_length=120,
            verbose_name = _("Peer Secret"),
            help_text = _("Initiator side secret. (for mutual CHAP authentication)"),
            )

    class Meta:
        verbose_name = _("Authorized Access")
        verbose_name_plural = _("Authorized Accesses")

    class FreeAdmin:
        menu_child_of = "services.ISCSI"
        icon_object = u"AuthorizedAccessIcon"
        icon_model = u"AuthorizedAccessIcon"
        icon_add = u"AddAuthorizedAccessIcon"
        icon_view = u"ViewAllAuthorizedAccessIcon"

    def __unicode__(self):
        return unicode(self.iscsi_target_auth_tag)


class iSCSITarget(Model):
    iscsi_target_name = models.CharField(
            unique=True,
            max_length=120,
            verbose_name = _("Target Name"),
            help_text = _("Base Name will be appended automatically when starting without 'iqn.'."),
            )
    iscsi_target_alias = models.CharField(
            unique=True,
            blank=True,
            null=True,
            max_length=120,
            verbose_name = _("Target Alias"),
            help_text = _("Optional user-friendly string of the target."),
            )
    iscsi_target_serial = models.CharField(
            verbose_name=_("Serial"),
            max_length=16,
            default="10000001",
            help_text=_("Serial number for the logical unit")
            )
    iscsi_target_type = models.CharField(
            max_length=120,
            choices=choices.ISCSI_TARGET_TYPE_CHOICES,
            default='Disk',
            verbose_name = _("Type"),
            help_text = _("Logical Unit Type mapped to LUN."),
            )
    iscsi_target_flags = models.CharField(
            max_length=120,
            choices=choices.ISCSI_TARGET_FLAGS_CHOICES,
            default='rw',
            verbose_name = _("Target Flags"),
            )
    iscsi_target_portalgroup = models.ForeignKey(
            iSCSITargetPortal,
            verbose_name = _("Portal Group ID"),
            )
    iscsi_target_initiatorgroup = models.ForeignKey(
            iSCSITargetAuthorizedInitiator,
            verbose_name = _("Initiator Group ID"),
            )
    iscsi_target_authtype = models.CharField(
            max_length=120,
            choices = choices.AUTHMETHOD_CHOICES,
            default = "Auto",
            verbose_name = _("Auth Method"),
            help_text = _("The method can be accepted by the target. Auto means both none and authentication."),
            )
    iscsi_target_authgroup = models.IntegerField(
            max_length=120,
            verbose_name = _("Authentication Group ID"),
            null=True,
            blank=True,
            )
    iscsi_target_initialdigest = models.CharField(
            max_length=120,
            default = "Auto",
            verbose_name = _("Auth Method"),
            help_text = _("The method can be accepted by the target. Auto means both none and authentication."),
            )
    iscsi_target_queue_depth = models.IntegerField(
            max_length=3,
            default=32,
            verbose_name = _("Queue Depth"),
            help_text = _("0=disabled, 1-255=enabled command queuing with specified depth. The recommended queue depth is 32."),
            )
    iscsi_target_logical_blocksize = models.IntegerField(
            max_length=3,
            default=512,
            verbose_name = _("Logical Block Size"),
            help_text = _("You may specify logical block length (512 by default). The recommended length for compatibility is 512."),
            )

    class Meta:
        verbose_name = _("Target")

    class FreeAdmin:
        menu_child_of = "services.ISCSI"
        icon_object = u"TargetIcon"
        icon_model = u"TargetIcon"
        icon_add = u"AddTargetIcon"
        icon_view = u"ViewAllTargetsIcon"

    def __unicode__(self):
        return self.iscsi_target_name

    def delete(self):
        for te in iSCSITargetToExtent.objects.filter(iscsi_target=self):
            te.delete()
        super(iSCSITarget, self).delete()


class iSCSITargetToExtent(Model):
    iscsi_target = models.ForeignKey(
            iSCSITarget,
            verbose_name = _("Target"),
            help_text = _("Target this extent belongs to"),
            )
    iscsi_extent = models.ForeignKey(
            iSCSITargetExtent,
            unique=True,
            verbose_name = _("Extent"),
            )

    class Meta:
        verbose_name = _("Target / Extent")
        verbose_name_plural = _("Targets / Extents")

    def __unicode__(self):
        return unicode(self.iscsi_target) + u' / ' + unicode(self.iscsi_extent)

    def delete(self):
        super(iSCSITargetToExtent, self).delete()
        started = notifier().reload("iscsitarget")
        if started is False and services.objects.get(srv_service='iscsitarget').srv_enable:
            raise ServiceFailed("iscsitarget", _("The iSCSI service failed to reload."))

    class FreeAdmin:
        menu_child_of = "services.ISCSI"
        icon_object = u"TargetExtentIcon"
        icon_model = u"TargetExtentIcon"
        icon_add = u"AddTargetExtentIcon"
        icon_view = u"ViewAllTargetExtentsIcon"

class DynamicDNS(Model):
    ddns_provider = models.CharField(
            max_length=120,
            choices=choices.DYNDNSPROVIDER_CHOICES,
            default='dyndns',
            blank=True,
            verbose_name = _("Provider")
            )
    ddns_domain = models.CharField(
            max_length=120,
            verbose_name = _("Domain name"),
            blank=True,
            help_text = _("A host name alias. This option can appear multiple times, for each domain that has the same IP. Use a space to separate multiple alias names.")
            )
    ddns_username = models.CharField(
            max_length=120,
            verbose_name = _("Username")
            )
    ddns_password = models.CharField(
            max_length=120,
            verbose_name = _("Password")
            ) # need to make this a 'password' field, but not available in django Models
    ddns_updateperiod = models.CharField(
            max_length=120,
            verbose_name=_("Update period"),
            blank=True,
            help_text=_("Time in seconds. Default is about 1 min.")
            )
    ddns_fupdateperiod = models.CharField(
            max_length=120,
            verbose_name = _("Forced update period"),
            blank=True
            )
    ddns_options = models.TextField(
            verbose_name = _("Auxiliary parameters"),
            blank=True,
            help_text = _("These parameters will be added to global settings in inadyn.conf.")
            )

    class Meta:
        verbose_name = _("Dynamic DNS")
        verbose_name_plural = _("Dynamic DNS")

    class FreeAdmin:
        deletable = False
        icon_model = u"DDNSIcon"


class PluginsJail(Model):
    jail_path = PathField(
            verbose_name=_("Plugins jail path"),
            help_text=_("Path to the plugins jail"),
            blank=False
            )
    jail_name = models.CharField(
            max_length=120,
            verbose_name=_("Jail name"),
            help_text=_("Name of the plugins jail"),
            default='',
            validators=[RegexValidator(regex="^[a-zA-Z][a-zA-Z0-9_]+$",
                message=_("Jail name can only contain letters, numbers and "
                    "underscores."))]
            )
    jail_ip = models.ForeignKey(
            Alias,
            on_delete=models.SET_NULL,
            null=True,
            verbose_name=_("Jail IP address"),
            )
    plugins_path = PathField(
            verbose_name=_("Plugins archive path"),
            help_text=_("Path where the plugins are saved after installation"),
            blank=False
            )

    class Meta:
        verbose_name = _("Plugins")
        verbose_name_plural = _("Plugins")

    class FreeAdmin:
        deletable = False
        delete_form = "PluginsJailDeleteForm"
        icon_model = u"SettingsIcon"

    def delete(self, *args, **kwargs):
        notifier().delete_plugins_jail(self.id)
        super(PluginsJail, self).delete(*args, **kwargs)
        services.objects.filter(srv_service='plugins').update(srv_enable=False)


class SNMP(Model):
    snmp_location = models.CharField(
            max_length=255,
            verbose_name = _("Location"),
            blank=True,
            help_text = _("Location information, e.g. physical location of this system: 'Floor of building, Room xyzzy'.")
            )
    snmp_contact = models.CharField(
            max_length=120,
            verbose_name = _("Contact"),
            blank=True,
            help_text = _("Contact information, e.g. name or email of the person responsible for this system: 'admin@email.address'.")
            )
    snmp_community = models.CharField(
            max_length=120,
            verbose_name = _("Community"),
            help_text = _("In most cases, 'public' is used here.")
            )
    snmp_traps = models.BooleanField(
            verbose_name = _("Send SNMP Traps"))
    snmp_options = models.TextField(
            verbose_name = _("Auxiliary parameters"),
            blank=True,
            help_text = _("These parameters will be added to global settings in inadyn.conf.")
            )

    class Meta:
        verbose_name = _("SNMP")
        verbose_name_plural = _("SNMP")

    class FreeAdmin:
        deletable = False
        icon_model = u"SNMPIcon"
        advanced_fields = ('snmp_traps',)

class UPS(Model):
    ups_identifier = models.CharField(
            max_length=120,
            verbose_name = _("Identifier"),
            help_text = _("This name is used to uniquely identify your UPS on this system.")
            )
    ups_driver = models.CharField(
            max_length=120,
            verbose_name = _("Driver"),
            choices=choices.UPSDRIVER_CHOICES(),
            blank=True,
            help_text = _("The driver used to communicate with your UPS.")
            )
    ups_port = models.CharField(
            max_length=120,
            verbose_name = _("Port"),
            blank=True,
            help_text = _("The serial or USB port where your UPS is connected.")
            )
    ups_options = models.TextField(
            verbose_name = _("Auxiliary parameters (ups.conf)"),
            blank=True,
            help_text = _("Additional parameters to the hardware-specific part of the driver.")
            )
    ups_description = models.CharField(
            max_length=120,
            verbose_name = _("Description"),
            blank=True
            )
    ups_shutdown = models.CharField(
            max_length=120,
            choices=choices.UPS_CHOICES,
            default='batt',
            verbose_name = _("Shutdown mode")
            )
    ups_shutdowntimer = models.CharField(
            max_length=120,
            verbose_name = _("Shutdown timer"),
            help_text = _("The time in seconds until shutdown is initiated. If the UPS happens to come back before the time is up the shutdown is canceled.")
            )
    ups_masterpwd = models.CharField(
            max_length=30,
            default="fixmepass",
            verbose_name=_("UPS Master User Password"),
            )
    ups_extrausers = models.TextField(
            blank=True,
            verbose_name=_("Extra users (upsd.users)"),
            )
    ups_rmonitor = models.BooleanField(
            verbose_name = _("Remote Monitor"))
    ups_emailnotify = models.BooleanField(
            verbose_name = _("Send Email Status Updates"))
    ups_toemail = models.CharField(
            max_length=120,
            verbose_name = _("To email"),
            blank=True,
            help_text = _("Destination email address. Separate email addresses by semi-colon.")
            )
    ups_subject = models.CharField(
            max_length=120,
            verbose_name = _("Email Subject"),
            help_text = _("The subject of the email. You can use the following parameters for substitution:<br /><ul><li>%d - Date</li><li>%h - Hostname</li></ul>")
            )

    class Meta:
        verbose_name = _("UPS")
        verbose_name_plural = _("UPS")

    class FreeAdmin:
        deletable = False
        icon_model = u"UPSIcon"

class FTP(Model):
    ftp_port = models.PositiveIntegerField(
            default=21,
            verbose_name = _("Port"),
            validators=[MinValueValidator(1), MaxValueValidator(65535)],
            help_text = _("Port to bind FTP server.")
            )
    ftp_clients = models.PositiveIntegerField(
            default=32,
            verbose_name = _("Clients"),
            validators=[MinValueValidator(0), MaxValueValidator(10000)],
            help_text = _("Maximum number of simultaneous clients.")
            )
    ftp_ipconnections = models.PositiveIntegerField(
            default=0,
            verbose_name = _("Connections"),
            validators=[MinValueValidator(0), MaxValueValidator(1000)],
            help_text = _("Maximum number of connections per IP address (0 = unlimited).")
            )
    ftp_loginattempt = models.PositiveIntegerField(
            default=3,
            verbose_name = _("Login Attempts"),
            validators=[MinValueValidator(0), MaxValueValidator(1000)],
            help_text = _("Maximum number of allowed password attempts before disconnection.")
            )
    ftp_timeout = models.PositiveIntegerField(
            default=120,
            verbose_name = _("Timeout"),
            validators=[MinValueValidator(0), MaxValueValidator(10000)],
            help_text = _("Maximum idle time in seconds.")
            )
    ftp_rootlogin = models.BooleanField(
            verbose_name = _("Allow Root Login"))
    ftp_onlyanonymous = models.BooleanField(
            verbose_name = _("Allow Anonymous Login"))
    ftp_anonpath = PathField(
        blank=True,
        verbose_name = _("Path"))
    ftp_onlylocal = models.BooleanField(
            verbose_name = _("Allow Local User Login"))
    ftp_banner = models.TextField(
            max_length=120,
            verbose_name = _("Banner"),
            blank=True,
            help_text = _("Greeting banner displayed by FTP when a connection first comes in.")
            )
    ftp_filemask = models.CharField(
            max_length=3,
            default = "077",
            verbose_name = _("File mask"),
            help_text = _("Use this option to override the file creation mask (077 by default).")
            )
    ftp_dirmask = models.CharField(
            max_length=3,
            default="077",
            verbose_name = _("Directory mask"),
            help_text = _("Use this option to override the file creation mask (077 by default).")
            )
    ftp_fxp = models.BooleanField(
            verbose_name = _("Enable FXP"))
    ftp_resume = models.BooleanField(
            verbose_name = _("Allow Transfer Resumption"))
    ftp_defaultroot = models.BooleanField(
            verbose_name = _("Always Chroot")) # Is this right?
    ftp_ident = models.BooleanField(
            verbose_name = _("Require IDENT Authentication"))
    ftp_reversedns = models.BooleanField(
            verbose_name = _("Require Reverse DNS for IP"))
    ftp_masqaddress = models.CharField(
            verbose_name = _("Masquerade address"),
            blank = True,
            max_length = 120,
            help_text = _("Causes the server to display the network information for the specified address to the client, on the assumption that IP address or DNS host is acting as a NAT gateway or port forwarder for the server.")
            )
    ftp_passiveportsmin = models.PositiveIntegerField(
            default = 0,
            verbose_name = _("Minimum passive port"),
            validators=[MinValueValidator(0), MaxValueValidator(10000)],
            help_text = _("The minimum port to allocate for PASV style data connections (0 = use any port).")
            )
    ftp_passiveportsmax = models.PositiveIntegerField(
            default = 0,
            verbose_name = _("Maximum passive port"),
            help_text = _("The maximum port to allocate for PASV style data connections (0 = use any port). Passive ports restricts the range of ports from which the server will select when sent the PASV command from a client. The server will randomly choose a number from within the specified range until an open port is found. The port range selected must be in the non-privileged range (eg. greater than or equal to 1024). It is strongly recommended that the chosen range be large enough to handle many simultaneous passive connections (for example, 49152-65534, the IANA-registered ephemeral port range).")
            )
    ftp_localuserbw = models.PositiveIntegerField(
            default=0,
            verbose_name = _("Local user upload bandwidth"),
            help_text = _("Local user upload bandwidth in KB/s. Zero means infinity.")
            )
    ftp_localuserdlbw = models.PositiveIntegerField(
            default=0,
            verbose_name = _("Local user download bandwidth"),
            help_text = _("Local user download bandwidth in KB/s. Zero means infinity.")
            )
    ftp_anonuserbw = models.PositiveIntegerField(
            default=0,
            verbose_name = _("Anonymous user upload bandwidth"),
            help_text = _("Anonymous user upload bandwidth in KB/s. Zero means infinity.")
            )
    ftp_anonuserdlbw = models.PositiveIntegerField(
            default=0,
            verbose_name = _("Anonymous user download bandwidth"),
            help_text = _("Anonymous user download bandwidth in KB/s. Zero means infinity.")
            )
    ftp_ssltls = models.BooleanField(
            verbose_name = _("Enable SSL/TLS"))
    ftp_options = models.TextField(
            max_length=120,
            verbose_name = _("Auxiliary parameters"),
            blank=True,
            help_text = _("These parameters are added to proftpd.conf.")
            )

    class Meta:
        verbose_name = _("FTP")
        verbose_name_plural = _("FTP")

    class FreeAdmin:
        deletable = False
        icon_model = "FTPIcon"

class TFTP(Model):
    tftp_directory = PathField(
            verbose_name = _("Directory"),
            help_text = _("The directory containing the files you want to publish. The remote host does not need to pass along the directory as part of the transfer."),
            )
    tftp_newfiles = models.BooleanField(
            verbose_name = _("Allow New Files"))
    tftp_port = models.PositiveIntegerField(
            verbose_name = _("Port"),
            validators=[MinValueValidator(1), MaxValueValidator(65535)],
            help_text = _("The port to listen to. The default is to listen to the tftp port specified in /etc/services.")
            )
    tftp_username = UserField(
            max_length=120,
            default = "nobody",
            verbose_name = _("Username"),
            help_text = _("Specifies the username which the service will run as.")
            )
    tftp_umask = models.CharField(
            max_length=120,
            verbose_name = _("umask"),
            help_text = _("Set the umask for newly created files to the specified value. The default is 022 (everyone can read, nobody can write).")
            )
    tftp_options = models.CharField(
            max_length=120,
            verbose_name = _("Extra options"),
            blank=True,
            help_text = _("Extra command line options (usually empty).")
            )

    class Meta:
        verbose_name = _("TFTP")
        verbose_name_plural = _("TFTP")

    class FreeAdmin:
        deletable = False
        icon_model = "TFTPIcon"

class SSH(Model):
    ssh_tcpport = models.PositiveIntegerField(
            verbose_name = _("TCP Port"),
            validators=[MinValueValidator(1), MaxValueValidator(65535)],
            help_text = _("Alternate TCP port. Default is 22"),
            )
    ssh_rootlogin = models.BooleanField(
            verbose_name = _("Login as Root with password"),
            help_text = _("Disabled: Root can only login via public key authentication; Enabled: Root login permitted with password")
            )
    ssh_passwordauth = models.BooleanField(
            verbose_name = _("Allow Password Authentication"))
    ssh_tcpfwd = models.BooleanField(
            verbose_name = _("Allow TCP Port Forwarding"))
    ssh_compression = models.BooleanField(
            verbose_name = _("Compress Connections"))
    ssh_privatekey = models.TextField(
            max_length=1024,
            verbose_name = _("Host Private Key"),
            blank=True,
            help_text = _("Paste a RSA PRIVATE KEY in PEM format here.")
            )
    ssh_options = models.TextField(
            max_length=120,
            verbose_name = _("Extra options"),
            blank=True,
            help_text = _("Extra options to /etc/ssh/sshd_config (usually empty). Note, incorrect entered options prevent SSH service to be started.")
            )
    ssh_host_dsa_key = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )
    ssh_host_dsa_key_pub = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )
    ssh_host_ecdsa_key = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )
    ssh_host_ecdsa_key_pub = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )
    ssh_host_key = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )
    ssh_host_key_pub = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )
    ssh_host_rsa_key = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )
    ssh_host_rsa_key_pub = models.TextField(
            max_length=1024,
            editable=False,
            blank=True,
            null=True
            )

    class Meta:
        verbose_name = _("SSH")
        verbose_name_plural = _("SSH")

    class FreeAdmin:
        deletable = False
        icon_model = "OpenSSHIcon"

class ActiveDirectory(Model):
    ad_dcname = models.CharField(
            max_length=120,
            verbose_name = _("Domain Controller Name"),
            help_text = _("AD or PDC name.")
            )
    ad_domainname = models.CharField(
            max_length=120,
            verbose_name = _("Domain Name (DNS/Realm-Name)"),
            help_text = _("Domain Name, eg example.com")
            )
    ad_netbiosname = models.CharField(
            max_length=120,
            verbose_name = _("NetBIOS Name"),
            help_text = _("System hostname")
            )
    ad_workgroup = models.CharField(
            max_length=120,
            verbose_name = _("Workgroup Name"),
            help_text = _("Workgroup or domain name in old format, eg WORKGROUP")
            )
    ad_allow_trusted_doms = models.BooleanField(
            default=False,
            verbose_name=_("Allow Trusted Domains"),
            )
    ad_adminname = models.CharField(
            max_length=120,
            verbose_name = _("Administrator Name"),
            help_text = _("Domain Administrator account name")
            )
    ad_adminpw = models.CharField(
            max_length=120,
            verbose_name = _("Administrator Password"),
            help_text = _("Domain Administrator account password.")
            )

    class Meta:
        verbose_name = _("Active Directory")
        verbose_name_plural = _("Active Directory")

    class FreeAdmin:
        deletable = False
        icon_model = "ActiveDirectoryIcon"

class LDAP(Model):
    ldap_hostname = models.CharField(
            max_length=120,
            verbose_name = _("Hostname"),
            blank=True,
            help_text = _("The name or IP address of the LDAP server")
            )
    ldap_basedn = models.CharField(
            max_length=120,
            verbose_name = _("Base DN"),
            blank=True,
            help_text = _("The default base Distinguished Name (DN) to use for searches, eg dc=test,dc=org")
            )
    ldap_anonbind = models.BooleanField(
            verbose_name = _("Allow Anonymous Binding"))
    ldap_rootbasedn = models.CharField(
            max_length=120,
            verbose_name = _("Root bind DN"),
            blank=True,
            help_text = _("The distinguished name with which to bind to the directory server, e.g. cn=admin,dc=test,dc=org")
            )
    ldap_rootbindpw = models.CharField(
            max_length=120,
            verbose_name = _("Root bind password"),
            blank=True,
            help_text = _("The credentials with which to bind.")
            )
    ldap_pwencryption = models.CharField(
            max_length=120,
            choices=choices.PWEncryptionChoices,
            verbose_name = _("Password Encryption"),
            help_text = _("The password change protocol to use.")
            )
    ldap_usersuffix = models.CharField(
            max_length=120,
            blank=True,
            verbose_name = _("User Suffix"),
            help_text = _("This parameter specifies the suffix that is used for users when these are added to the LDAP directory, e.g. ou=Users")
            )
    ldap_groupsuffix = models.CharField(
            max_length=120,
            blank=True,
            verbose_name = _("Group Suffix"),
            help_text = _("This parameter specifies the suffix that is used for groups when these are added to the LDAP directory, e.g. ou=Groups")
            )
    ldap_passwordsuffix = models.CharField(
            max_length=120,
            verbose_name = _("Password Suffix"),
            blank=True,
            help_text = _("This parameter specifies the suffix that is used for passwords when these are added to the LDAP directory, e.g. ou=Passwords")
            )
    ldap_machinesuffix = models.CharField(
            max_length=120,
            verbose_name = _("Machine Suffix"),
            blank=True,
            help_text = _("This parameter specifies the suffix that is used for machines when these are added to the LDAP directory, e.g. ou=Computers")
            )
    ldap_ssl = models.CharField(
            choices = choices.LDAP_SSL_CHOICES,
            max_length=120,
            verbose_name = _("Encryption Mode"),
            help_text = _("This parameter specifies whether to use SSL/TLS, e.g. on/off/start_tls")
            )
    ldap_tls_cacertfile = models.TextField(
            verbose_name = _("Self signed certificate"),
            blank=True,
            help_text = _("Place the contents of your self signed certificate file here.")
            )
    ldap_options = models.TextField(
            max_length=120,
            verbose_name = _("Auxiliary Parameters"),
            blank=True,
            help_text = _("These parameters are added to ldap.conf.")
            )

    class Meta:
        verbose_name = _("LDAP")
        verbose_name_plural = _("LDAP")

    class FreeAdmin:
        deletable = False
        icon_model = "LDAPIcon"

class Rsyncd(Model):
    rsyncd_port = models.IntegerField(
            default=873,
            verbose_name=_("TCP Port"),
            help_text=_("Alternate TCP port. Default is 873"),
            )
    rsyncd_auxiliary = models.TextField(
            blank=True,
            verbose_name = _("Auxiliary parameters"),
            help_text = _("These parameters will be added to [global] settings in rsyncd.conf"),
            )

    class Meta:
        verbose_name = _("Configure Rsyncd")
        verbose_name_plural = _("Configure Rsyncd")

    class FreeAdmin:
        deletable = False
        menu_child_of = "services.Rsync"
        icon_model = u"rsyncdIcon"


class RsyncMod(Model):
    rsyncmod_name = models.CharField(
            max_length=120,
            verbose_name=_("Module name"),
            )
    rsyncmod_comment = models.CharField(
            max_length=120,
            blank=True,
            verbose_name=_("Comment"),
            )
    rsyncmod_path = PathField(
            verbose_name=_("Path"),
            help_text=_("Path to be shared"),
            )
    rsyncmod_mode = models.CharField(
            max_length=120,
            choices=choices.ACCESS_MODE,
            default="rw",
            verbose_name=_("Access Mode"),
            help_text=_("This controls the access a remote host has to this module"),
            )
    rsyncmod_maxconn = models.IntegerField(
            default=0,
            verbose_name=_("Maximum connections"),
            help_text=_("Maximum number of simultaneous connections. Default is 0 (unlimited)"),
            )
    rsyncmod_user = UserField(
            max_length=120,
            default="nobody",
            verbose_name=_("User"),
            help_text=_("This option specifies the user name that file transfers to and from that module should take place. In combination with the 'Group' option this determines what file permissions are available. Leave this field empty to use default settings"),
            blank=True,
            )
    rsyncmod_group = GroupField(
            max_length=120,
            default="nobody",
            verbose_name=_("Group"),
            help_text=_("This option specifies the group name that file transfers to and from that module should take place. Leave this field empty to use default settings"),
            blank=True,
            )
    rsyncmod_hostsallow = models.TextField(
            verbose_name = _("Hosts allow"),
            help_text = _("This option is a comma, space, or tab delimited set of hosts which are permitted to access this module. You can specify the hosts by name or IP number. Leave this field empty to use default settings"),
            blank=True,
            )
    rsyncmod_hostsdeny = models.TextField(
            verbose_name = _("Hosts deny"),
            help_text = _("This option is a comma, space, or tab delimited set of host which are NOT permitted to access this module. Where the lists conflict, the allow list takes precedence. In the event that it is necessary to deny all by default, use the keyword ALL (or the netmask 0.0.0.0/0) and then explicitly specify to the hosts allow parameter those hosts that should be permitted access. Leave this field empty to use default settings"),
            blank=True,
            )
    rsyncmod_auxiliary = models.TextField(
            verbose_name = _("Auxiliary parameters"),
            help_text = _("These parameters will be added to the module configuration in rsyncd.conf"),
            blank=True,
            )

    class Meta:
        verbose_name = _("Rsync Module")
        verbose_name_plural = _("Rsync Modules")
        ordering = ["rsyncmod_name"]

    class FreeAdmin:
        menu_child_of = 'services.Rsync'
        icon_model = u"rsyncModIcon"

    def __unicode__(self):
        return unicode(self.rsyncmod_name)

class SMART(Model):
    smart_interval = models.IntegerField(
            default=30,
            verbose_name=_("Check interval"),
            help_text=_("Sets the interval between disk checks to N minutes. The default is 30 minutes"),
            )
    smart_powermode = models.CharField(
            choices=choices.SMART_POWERMODE,
            default="never",
            max_length=60,
            verbose_name=_("Power mode"),
            )
    smart_difference = models.IntegerField(
            default=0,
            verbose_name=_("Difference"),
            help_text=_("Report if the temperature had changed by at least N degrees Celsius since last report. 0 to disable"),
            )
    smart_informal = models.IntegerField(
            default=0,
            verbose_name=_("Informal"),
            help_text=_("Report if the temperature is greater or equal than N degrees Celsius. 0 to disable"),
            )
    smart_critical = models.IntegerField(
            default=0,
            verbose_name=_("Critical"),
            help_text=_("Report if the temperature is greater or equal than N degrees Celsius. 0 to disable"),
            )
    smart_email = models.CharField(
            verbose_name=_("Email to report"),
            max_length=255,
            blank=True,
            help_text=_("Destination email address. Separate email addresses by semi-colon"),
            )
    class Meta:
        verbose_name = _("S.M.A.R.T.")
        verbose_name_plural = _("S.M.A.R.T.")
    class FreeAdmin:
        deletable = False
        icon_model = u"SMARTIcon"


class RPCToken(Model):

    key = models.CharField(max_length=1024)
    secret = models.CharField(max_length=1024)
    plugin = models.ForeignKey('plugins.Plugins', null=True)

    @classmethod
    def new(cls, plugin=None):
        key = str(uuid.uuid4())
        h = hmac.HMAC(key=key, digestmod=hashlib.sha512)
        secret = str(h.hexdigest())
        instance = cls.objects.create(
            key=key,
            secret=secret,
            plugin=plugin,
            )
        return instance
