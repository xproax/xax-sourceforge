#+
# Copyright 2010 iXsystems
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
# $FreeBSD$
#####################################################################

import base64
import re

from django.shortcuts import render_to_response                
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext as _

#TODO do not import *
from freenasUI.services.models import *                         
from freenasUI.storage.models import *
from freenasUI.common.forms import ModelForm
from freenasUI.common.forms import Form
from freenasUI.common.freenasldap import FreeNAS_Users, FreeNAS_Groups
from freenasUI.middleware.notifier import notifier
from storage.forms import UnixPermissionField
from dojango import forms
from dojango.forms import fields, widgets

""" Services """

attrs_dict = { 'class': 'required' }

class servicesForm(ModelForm):
    class Meta:
        model = services

class CIFSForm(ModelForm):
    class Meta:
        model = CIFS
    cifs_srv_guest = forms.ChoiceField(choices=(),
                                       widget=forms.Select(attrs=attrs_dict),
                                       label=_('Guest Account')
                                       )
    def __init__(self, *args, **kwargs):
        super(CIFSForm, self).__init__(*args, **kwargs)
        self.fields['cifs_srv_guest'].widget = widgets.ComboBox()
        self.fields['cifs_srv_guest'].choices = ((x.bsdusr_username,
                                                  x.bsdusr_username)
                                                  for x in FreeNAS_Users()
                                                 )

    def clean(self):
        home = self.cleaned_data['cifs_srv_homedir_enable']
        browse = self.cleaned_data['cifs_srv_homedir_browseable_enable']
        cleaned_data = self.cleaned_data
        if browse and not home:
            self._errors['cifs_srv_homedir_enable'] = self.error_class([_("This field is required for \"Enable home directories browsing\"."),])
            del cleaned_data['cifs_srv_homedir_enable']
        return cleaned_data

    def save(self):
        super(CIFSForm, self).save()
        notifier().reload("cifs")

class AFPForm(ModelForm):
    class Meta:
        model = AFP
    afp_srv_guest_user = forms.ChoiceField(choices=(),
                                           widget=forms.Select(attrs=attrs_dict),
                                           label = _("Guest Account")
                                           )
    def __init__(self, *args, **kwargs):
        super(AFPForm, self).__init__(*args, **kwargs)
        self.fields['afp_srv_guest_user'].widget = widgets.ComboBox()
        self.fields['afp_srv_guest_user'].choices = ((x.bsdusr_username,
                                                      x.bsdusr_username)
                                                     for x in FreeNAS_Users())
    def save(self):
        super(AFPForm, self).save()
        notifier().restart("afp")

class NFSForm(ModelForm):
    class Meta:
        model = NFS
    def save(self):
        super(NFSForm, self).save()
        notifier().restart("nfs")

class FTPForm(ModelForm):

    ftp_filemask = UnixPermissionField(label=_('File Permission'))
    ftp_dirmask = UnixPermissionField(label=_('Directory Permission'))
    class Meta:
        model = FTP 

    def __init__(self, *args, **kwargs):

        if kwargs.has_key('instance'):
            instance = kwargs['instance']
            mask = int(instance.ftp_filemask)
            instance.ftp_filemask = "%.3o" % (~mask & 0o666)

            mask = int(instance.ftp_dirmask)
            instance.ftp_dirmask = "%.3o" % (~mask & 0o777)

        super(FTPForm, self).__init__(*args, **kwargs)

    def clean_ftp_port(self):
        port = self.cleaned_data['ftp_port']
        if port < 0 or port > 65535:
            raise forms.ValidationError(_("This value must be between 0 and 65535, inclusive."))
        return port

    def clean_ftp_clients(self):
        clients = self.cleaned_data['ftp_clients']
        if clients < 0 or clients > 10000:
            raise forms.ValidationError(_("This value must be between 0 and 10000, inclusive."))
        return clients

    def clean_ftp_ipconnections(self):
        conn = self.cleaned_data['ftp_ipconnections']
        if conn < 0 or conn > 1000:
            raise forms.ValidationError(_("This value must be between 0 and 1000, inclusive."))
        return conn

    def clean_ftp_loginattempt(self):
        attempt = self.cleaned_data['ftp_loginattempt']
        if attempt < 0 or attempt > 1000:
            raise forms.ValidationError(_("This value must be between 0 and 1000, inclusive."))
        return attempt

    def clean_ftp_timeout(self):
        timeout = self.cleaned_data['ftp_timeout']
        if timeout < 0 or timeout > 10000:
            raise forms.ValidationError(_("This value must be between 0 and 10000, inclusive."))
        return timeout

    def clean_ftp_passiveportsmin(self):
        ports = self.cleaned_data['ftp_passiveportsmin']
        if (ports < 1024 or ports > 65535) and ports != 0:
            raise forms.ValidationError(_("This value must be between 1024 and 65535, inclusive. 0 for default"))
        return ports

    def clean_ftp_passiveportsmax(self):
        ports = self.cleaned_data['ftp_passiveportsmax']
        if (ports < 1024 or ports > 65535) and ports != 0:
            raise forms.ValidationError(_("This value must be between 1024 and 65535, inclusive. 0 for default."))
        return ports

    def clean_ftp_filemask(self):
        perm = self.cleaned_data['ftp_filemask']
        perm = int(perm, 8)
        mask = (~perm & 0o666)
        return "%.3o" % mask

    def clean_ftp_dirmask(self):
        perm = self.cleaned_data['ftp_dirmask']
        print perm, type(perm)
        perm = int(perm, 8)
        mask = (~perm & 0o777)
        return "%.3o" % mask

    def clean_ftp_anonpath(self):
        anon = self.cleaned_data['ftp_onlyanonymous']
        path = self.cleaned_data['ftp_anonpath']
        if anon and not path:
            raise forms.ValidationError(_("This field is required for anonymous login"))
        return path

    def save(self):
        super(FTPForm, self).save()
        notifier().reload("ftp")

class TFTPForm(ModelForm):
    tftp_username = forms.ChoiceField(choices=(),
                                      widget=forms.Select(attrs=attrs_dict),
                                      label = _("Username")
                                      )
    def __init__(self, *args, **kwargs):
        super(TFTPForm, self).__init__(*args, **kwargs)
        self.fields['tftp_username'].widget = widgets.ComboBox()
        self.fields['tftp_username'].choices = ((x.bsdusr_username, x.bsdusr_username)
                                                for x in FreeNAS_Users())
    def save(self):
        super(TFTPForm, self).save()
        notifier().reload("tftp")
    class Meta:
        model = TFTP 

class SSHForm(ModelForm):
    def save(self):
        super(SSHForm, self).save()
        notifier().reload("ssh")
    class Meta:
        model = SSH 

class iSCSITargetForm(ModelForm):
    class Meta:
        model = iSCSITarget

class DynamicDNSForm(ModelForm):
    class Meta:
        model = DynamicDNS

class SNMPForm(ModelForm):
    class Meta:
        model = SNMP

class UPSForm(ModelForm):
    class Meta:
        model = UPS


class ActiveDirectoryForm(ModelForm):
    #file = forms.FileField(label="Kerberos Keytab File", required=False)
    def save(self):
        if self.files.has_key('file'):
            self.instance.ad_keytab = base64.encodestring(self.files['file'].read())
        super(ActiveDirectoryForm, self).save()
        notifier().restart("activedirectory")
    class Meta:
        model = ActiveDirectory
        exclude = ('ad_keytab','ad_spn','ad_spnpw')
        widgets = {'ad_adminpw': forms.widgets.PasswordInput(render_value=True), } 

class LDAPForm(ModelForm):
    def save(self):
        super(LDAPForm, self).save()
        notifier().restart("ldap")
    class Meta:
        model = LDAP
        widgets = {'ldap_rootbindpw': forms.widgets.PasswordInput(render_value=True), } 

class iSCSITargetAuthCredentialForm(ModelForm):
    iscsi_target_auth_secret1 = forms.CharField(label=_("Secret"), 
            widget=forms.PasswordInput, help_text=_("Target side secret."))
    iscsi_target_auth_secret2 = forms.CharField(label=_("Secret (Confirm)"), 
            widget=forms.PasswordInput, 
            help_text=_("Enter the same secret above for verification."))
    iscsi_target_auth_peersecret1 = forms.CharField(label=_("Initiator Secret"),
            widget=forms.PasswordInput, help_text=
            _("Initiator side secret. (for mutual CHAP authentication)"),
            required=False)
    iscsi_target_auth_peersecret2 = forms.CharField(
            label=_("Initiator Secret (Confirm)"), 
            widget=forms.PasswordInput, 
            help_text=_("Enter the same secret above for verification."),
            required=False)

    def _clean_secret_common(self, secretprefix):
        secret1 = self.cleaned_data.get(("%s1" % secretprefix), "")
        secret2 = self.cleaned_data[("%s2" % secretprefix)]
        if secret1 != secret2:
            raise forms.ValidationError(_("Secret does not match"))
        return secret2

    def clean_iscsi_target_auth_secret2(self):
        return self._clean_secret_common("iscsi_target_auth_secret")

    def clean_iscsi_target_auth_peersecret2(self):
        return self._clean_secret_common("iscsi_target_auth_peersecret")

    def clean(self):
        cdata = self.cleaned_data

        if len(cdata.get('iscsi_target_auth_peeruser', '')) > 0:
            if len(cdata.get('iscsi_target_auth_peersecret1', '')) == 0:
                del cdata['iscsi_target_auth_peersecret1']
                self._errors['iscsi_target_auth_peersecret1'] = self.error_class([_("The peer secret is required if you set a peer user.")])
                self._errors['iscsi_target_auth_peersecret2'] = self.error_class([_("The peer secret is required if you set a peer user.")])
            elif cdata.get('iscsi_target_auth_peersecret1', '') == cdata.get('iscsi_target_auth_secret1', ''):
                del cdata['iscsi_target_auth_peersecret1']
                self._errors['iscsi_target_auth_peersecret1'] = self.error_class([_("The peer secret cannot be the same as user secret.")])

        return cdata

    class Meta:
        model = iSCSITargetAuthCredential
        exclude = ('iscsi_target_auth_secret', 'iscsi_target_auth_peersecret',)

    def save(self, commit=True):
        oAuthCredential = super(iSCSITargetAuthCredentialForm, self).save(commit=False)
        oAuthCredential.iscsi_target_auth_secret = self.cleaned_data["iscsi_target_auth_secret1"]
        oAuthCredential.iscsi_target_auth_peersecret = self.cleaned_data["iscsi_target_auth_peersecret1"]
        if commit:
            oAuthCredential.save()
        notifier().reload("iscsitarget")
        return oAuthCredential

    def __init__(self, *args, **kwargs):
        super(iSCSITargetAuthCredentialForm, self).__init__(*args, **kwargs)
        self.fields.keyOrder = [
            'iscsi_target_auth_tag',
            'iscsi_target_auth_user',
            'iscsi_target_auth_secret1',
            'iscsi_target_auth_secret2',
            'iscsi_target_auth_peeruser',
            'iscsi_target_auth_peersecret1',
            'iscsi_target_auth_peersecret2']

        try:
            self.fields['iscsi_target_auth_secret1'].initial = self.instance.iscsi_target_auth_secret
            self.fields['iscsi_target_auth_secret2'].initial = self.instance.iscsi_target_auth_secret
            self.fields['iscsi_target_auth_peersecret1'].initial = self.instance.iscsi_target_auth_peersecret
            self.fields['iscsi_target_auth_peersecret2'].initial = self.instance.iscsi_target_auth_peersecret
        except:
            pass

class iSCSITargetToExtentForm(ModelForm):
    class Meta:
        model = iSCSITargetToExtent
    def clean_iscsi_target_lun(self):
        try:
            obj = iSCSITargetToExtent.objects.get(iscsi_target=self.cleaned_data.get('iscsi_target'),
                                                  iscsi_target_lun=self.cleaned_data.get('iscsi_target_lun'))
            raise forms.ValidationError(_("LUN already exists in the same target."))
        except ObjectDoesNotExist:
            return self.cleaned_data.get('iscsi_target_lun')

    def save(self):
        super(iSCSITargetToExtentForm, self).save()
        notifier().reload("iscsitarget")

class iSCSITargetGlobalConfigurationForm(ModelForm):
    iscsi_luc_authgroup = forms.ChoiceField(label=_("Controller Auth Group"),
            help_text=_("The istgtcontrol can access the targets with correct user and secret in specific Auth Group."))
    iscsi_discoveryauthgroup = forms.ChoiceField(label=_("Discovery Auth Group"))
    class Meta:
        model = iSCSITargetGlobalConfiguration
    def __init__(self, *args, **kwargs):
        super(iSCSITargetGlobalConfigurationForm, self).__init__(*args, **kwargs)
        self.fields['iscsi_luc_authgroup'].required = False
        self.fields['iscsi_luc_authgroup'].choices = [(-1, _('None'))] + [(i['iscsi_target_auth_tag'], i['iscsi_target_auth_tag']) for i in iSCSITargetAuthCredential.objects.all().values('iscsi_target_auth_tag').distinct()]
        self.fields['iscsi_discoveryauthgroup'].required = False
        self.fields['iscsi_discoveryauthgroup'].choices = [('-1', _('None'))] + [(i['iscsi_target_auth_tag'], i['iscsi_target_auth_tag']) for i in iSCSITargetAuthCredential.objects.all().values('iscsi_target_auth_tag').distinct()]
        self.fields['iscsi_toggleluc'].widget.attrs['onChange'] = 'javascript:toggleLuc(this);'
        ro = True
        if len(self.data) > 0:
            if self.data.get("iscsi_toggleluc", None) == "on":
                ro = False
        else:
            if self.instance.iscsi_toggleluc == True:
                ro = False
        if ro:
            self.fields['iscsi_lucip'].widget.attrs['disabled'] = 'disabled'
            self.fields['iscsi_lucport'].widget.attrs['disabled'] = 'disabled'
            self.fields['iscsi_luc_authnetwork'].widget.attrs['disabled'] = 'disabled'
            self.fields['iscsi_luc_authmethod'].widget.attrs['disabled'] = 'disabled'
            self.fields['iscsi_luc_authgroup'].widget.attrs['disabled'] = 'disabled'

    def _clean_number_range(self, field, start, end):
        f = self.cleaned_data[field]
        if f < start  or f > end:
            raise forms.ValidationError(_("This value must be between %d and %d, inclusive.") % (start, end))
        return f

    def clean_iscsi_discoveryauthgroup(self):
        discoverymethod = self.cleaned_data['iscsi_discoveryauthmethod']
        discoverygroup = self.cleaned_data['iscsi_discoveryauthgroup']
        if discoverymethod in ('CHAP', 'CHAP Mutual'):
            if int(discoverygroup) == -1:
                raise forms.ValidationError(_("This field is required."))
        elif int(discoverygroup) == -1:
            return None
        return discoverygroup

    def clean_iscsi_iotimeout(self):
        return self._clean_number_range("iscsi_iotimeout", 0, 300)

    def clean_iscsi_nopinint(self):
        return self._clean_number_range("iscsi_nopinint", 0, 300)

    def clean_iscsi_maxsesh(self):
        return self._clean_number_range("iscsi_maxsesh", 1, 64)

    def clean_iscsi_maxconnect(self):
        return self._clean_number_range("iscsi_maxconnect", 1, 64)

    def clean_iscsi_r2t(self):
        return self._clean_number_range("iscsi_r2t", 1, 255)

    def clean_iscsi_maxoutstandingr2t(self):
        return self._clean_number_range("iscsi_maxoutstandingr2t", 1, 255)

    def clean_iscsi_firstburst(self):
        return self._clean_number_range("iscsi_firstburst", 1, pow(2,32))

    def clean_iscsi_maxburst(self):
        return self._clean_number_range("iscsi_maxburst", 1, pow(2,32))

    def clean_iscsi_maxrecdata(self):
        return self._clean_number_range("iscsi_maxrecdata", 1, pow(2,32))

    def clean_iscsi_defaultt2w(self):
        return self._clean_number_range("iscsi_defaultt2w", 1, 300)

    def clean_iscsi_defaultt2r(self):
        return self._clean_number_range("iscsi_defaultt2r", 1, 300)

    def clean_iscsi_lucport(self):
        if self.cleaned_data.get('iscsi_toggleluc', False):
            return self._clean_number_range("iscsi_lucport", 1000, pow(2,16))
        return None

    def clean_iscsi_luc_authgroup(self):
        lucmethod = self.cleaned_data['iscsi_luc_authmethod']
        lucgroup = self.cleaned_data['iscsi_luc_authgroup']
        if lucmethod in ('CHAP', 'CHAP Mutual'):
            if lucgroup != '' and int(lucgroup) == -1:
                raise forms.ValidationError(_("This field is required."))
        elif lucgroup != '' and int(lucgroup) == -1:
            return None
        return lucgroup

    def clean(self):
        cdata = self.cleaned_data

        luc = cdata.get("iscsi_toggleluc", False)
        if luc:
            for field in ('iscsi_lucip', 'iscsi_luc_authnetwork', 
                    'iscsi_luc_authmethod', 'iscsi_luc_authgroup'):
                if cdata.has_key(field) and cdata[field] == '':
                    self._errors[field] = self.error_class([_("This field is required.")])
                    del cdata[field]
        else:
            cdata['iscsi_lucip'] = None
            cdata['iscsi_lucport'] = None
            cdata['iscsi_luc_authgroup'] = None

        return cdata

    def save(self):
        super(iSCSITargetGlobalConfigurationForm, self).save()
        notifier().reload("iscsitarget")

class iSCSITargeExtentEditForm(ModelForm):
    class Meta:
        model = iSCSITargetExtent
        exclude = ('iscsi_target_extent_type', 'iscsi_target_extent_path',)
    def save(self):
        super(iSCSITargetExtentEditForm, self).save()
        notifier().reload("iscsitarget")

class iSCSITargetFileExtentForm(ModelForm):
    class Meta:
        model = iSCSITargetExtent
        exclude = ('iscsi_target_extent_type')
    def clean_iscsi_target_extent_filesize(self):
        size = self.cleaned_data['iscsi_target_extent_filesize']
        try:
            int(size)
        except ValueError:
            suffixes = ['KB', 'MB', 'GB', 'TB']
            for x in suffixes:
                if size.upper().endswith(x):
                    m = re.match(r'(\d+)\s*?(%s)' % x, size)
                    if m:
                        return "%s%s" % (m.group(1), m.group(2))
            raise forms.ValidationError(_("This value can be a size in bytes, or can be postfixed with KB, MB, GB, TB"))
        return size
    def save(self, commit=True):
        oExtent = super(iSCSITargetFileExtentForm, self).save(commit=False)
        oExtent.iscsi_target_extent_type = 'File'
        if commit:
            oExtent.save()
        notifier().reload("iscsitarget")
        return oExtent

class iSCSITargetDeviceExtentForm(ModelForm):
    iscsi_extent_disk = forms.ChoiceField(choices=(), 
            widget=forms.Select(attrs=attrs_dict), label = _('Disk device'))
    def __init__(self, *args, **kwargs):
        super(iSCSITargetDeviceExtentForm, self).__init__(*args, **kwargs)
        self.fields['iscsi_extent_disk'].choices = self._populate_disk_choices()
        self.fields['iscsi_extent_disk'].choices.sort()
    # TODO: This is largely the same with disk wizard.
    def _populate_disk_choices(self):
        from os import popen
        import re
    
        diskchoices = dict()
    
        # Grab disk list
        # NOTE: This approach may fail if device nodes are not accessible.
        pipe = popen("/usr/sbin/diskinfo ` /sbin/sysctl -n kern.disks` | /usr/bin/cut -f1,3")
        diskinfo = pipe.read().strip().split('\n')
        for disk in diskinfo:
            devname, capacity = disk.split('\t')
            capacity = int(capacity)
            if capacity >= 1099511627776:
                    capacity = "%.1f TiB" % (capacity / 1099511627776.0)
            elif capacity >= 1073741824:
                    capacity = "%.1f GiB" % (capacity / 1073741824.0)
            elif capacity >= 1048576:
                    capacity = "%.1f MiB" % (capacity / 1048576.0)
            else:
                    capacity = "%d Bytes" % (capacity)
            diskchoices[devname] = "%s (%s)" % (devname, capacity)
        # Exclude the root device
        rootdev = popen("""glabel status | grep `mount | awk '$3 == "/" {print $1}' | sed -e 's/\/dev\///'` | awk '{print $3}'""").read().strip()
        rootdev_base = re.search('[a-z/]*[0-9]*', rootdev)
        if rootdev_base != None:
            try:
                del diskchoices[rootdev_base.group(0)]
            except:
                pass
        # Exclude what's already added
        for devname in [ x['disk_disks'] for x in Disk.objects.all().values('disk_disks')]:
            try:
                del diskchoices[devname]
            except:
                pass
        return diskchoices.items()
    class Meta:
        model = iSCSITargetExtent
        exclude = ('iscsi_target_extent_type', 'iscsi_target_extent_path', 'iscsi_target_extent_filesize')
    def save(self, commit=True):
        oExtent = super(iSCSITargetDeviceExtentForm, self).save(commit=False)
        oExtent.iscsi_target_extent_type = 'Disk'
        oExtent.iscsi_target_extent_filesize = 0
        oExtent.iscsi_target_extent_path = '/dev/' + self.cleaned_data["iscsi_extent_disk"]
        if commit:
            oExtent.save()
            # Construct a corresponding volume.
            volume_name = 'iscsi:' + self.cleaned_data["iscsi_extent_disk"]
            volume_fstype = 'iscsi'

            volume = Volume(vol_name = volume_name, vol_fstype = volume_fstype)
            volume.save()

            disk_list = [ self.cleaned_data["iscsi_extent_disk"] ]

            mp = MountPoint(mp_volume=volume, mp_path=volume_name, mp_options='noauto')
            mp.save()

            grp = DiskGroup(group_name= volume_name, group_type = 'raw', group_volume = volume)
            grp.save()

            diskobj = Disk(disk_name = self.cleaned_data["iscsi_extent_disk"],
                           disk_disks = self.cleaned_data["iscsi_extent_disk"],
                           disk_description = 'iSCSI exported disk',
                           disk_group = grp)
            diskobj.save()
        notifier().reload("iscsitarget")
        return oExtent

class iSCSITargetPortalForm(ModelForm):
    class Meta:
        model = iSCSITargetPortal
    def save(self):
        super(iSCSITargetPortalForm, self).save()
        notifier().reload("iscsitarget")

class iSCSITargetAuthorizedInitiatorForm(ModelForm):
    class Meta:
        model = iSCSITargetAuthorizedInitiator
    def save(self):
        super(iSCSITargetAuthorizedInitiatorForm, self).save()
        notifier().reload("iscsitarget")

class iSCSITargetForm(ModelForm):
    iscsi_target_authgroup = forms.ChoiceField(label=_("Authentication Group number"))
    class Meta:
        model = iSCSITarget
        exclude = ('iscsi_target_initialdigest',)
    def __init__(self, *args, **kwargs):
        super(iSCSITargetForm, self).__init__(*args, **kwargs)
        self.fields['iscsi_target_authgroup'].required = False
        self.fields['iscsi_target_authgroup'].choices = [(-1, _('None'))] + [(i['iscsi_target_auth_tag'], i['iscsi_target_auth_tag']) for i in iSCSITargetAuthCredential.objects.all().values('iscsi_target_auth_tag').distinct()]

    def clean_iscsi_target_authgroup(self):
        method = self.cleaned_data['iscsi_target_authtype']
        group = self.cleaned_data['iscsi_target_authgroup']
        if method in ('CHAP', 'CHAP Mutual'):
            if group != '' and int(group) == -1:
                raise forms.ValidationError(_("This field is required."))
        elif group != '' and int(group) == -1:
            return None
        return int(group)

    def clean_iscsi_target_alias(self):
        alias = self.cleaned_data['iscsi_target_alias']
        if not alias:
            alias = None
        return alias

    def save(self):
        super(iSCSITargetForm, self).save()
        notifier().reload("iscsitarget")
