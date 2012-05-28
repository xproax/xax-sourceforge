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
import os
import re

from django.utils.translation import ugettext_lazy as _

from dojango import forms
from freenasUI.sharing import models
from freenasUI.middleware.notifier import notifier
from freenasUI.common.forms import ModelForm
from freenasUI.services.models import services
from freenasUI.storage.widgets import UnixPermissionField
from ipaddr import IPAddress, IPNetwork, \
                   AddressValueError, NetmaskValueError


class CIFS_ShareForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super(CIFS_ShareForm, self).__init__(*args, **kwargs)
        self.fields['cifs_guestok'].widget.attrs['onChange'] = ('javascript:'
            'toggleGeneric("id_cifs_guestok", ["id_cifs_guestonly"], true);')
        if self.data:
            if self.data.get('cifs_guestok') is False:
                self.fields['cifs_guestonly'].widget.attrs['disabled'] = \
                    'disabled'
        elif self.instance.cifs_guestok is False:
            self.fields['cifs_guestonly'].widget.attrs['disabled'] = 'disabled'

    class Meta:
        model = models.CIFS_Share

    def clean_cifs_hostsallow(self):
        net = self.cleaned_data.get("cifs_hostsallow")
        net = re.sub(r'\s{2,}|\n', ' ', net).strip()
        return net

    def clean_cifs_hostsdeny(self):
        net = self.cleaned_data.get("cifs_hostsdeny")
        net = re.sub(r'\s{2,}|\n', ' ', net).strip()
        return net

    def save(self):
        ret = super(CIFS_ShareForm, self).save()
        notifier().reload("cifs")
        return ret

    def done(self, request, events):
        if not services.objects.get(srv_service='cifs').srv_enable:
            events.append('ask_service("cifs")')


class AFP_ShareForm(ModelForm):

    afp_sharepw2 = forms.CharField(max_length=50,
            label=_("Confirm Share Password"),
            widget=forms.widgets.PasswordInput(render_value=False),
            required=False,
            )

    class Meta:
        model = models.AFP_Share
        widgets = {
            'afp_sharepw': forms.widgets.PasswordInput(render_value=False),
        }

    def __init__(self, *args, **kwargs):
        super(AFP_ShareForm, self).__init__(*args, **kwargs)
        self.fields['afp_fperm'] = UnixPermissionField(
            label=self.fields['afp_fperm'].label,
            )
        self.fields['afp_dperm'] = UnixPermissionField(
            label=self.fields['afp_dperm'].label,
            )
        if self.instance.id:
            self.fields['afp_sharepw2'].initial = self.instance.afp_sharepw

    def clean_afp_sharepw2(self):
        password1 = self.cleaned_data.get("afp_sharepw")
        password2 = self.cleaned_data.get("afp_sharepw2")
        if password1 != password2:
            raise forms.ValidationError(
                _("The two password fields didn't match.")
                )
        return password2

    def clean(self):
        cdata = self.cleaned_data
        if not cdata.get("afp_sharepw"):
            cdata['afp_sharepw'] = self.instance.afp_sharepw
        return cdata

    def save(self):
        ret = super(AFP_ShareForm, self).save()
        notifier().reload("afp")
        return ret

    def done(self, request, events):
        if not services.objects.get(srv_service='afp').srv_enable:
            events.append('ask_service("afp")')

AFP_ShareForm.base_fields.keyOrder.remove('afp_sharepw2')
AFP_ShareForm.base_fields.keyOrder.insert(4, 'afp_sharepw2')


class NFS_ShareForm(ModelForm):

    class Meta:
        model = models.NFS_Share

    def clean_nfs_path(self):
        path = self.cleaned_data.get("nfs_path")
        if not os.path.exists(path):
            raise forms.ValidationError(_("The path %s does not exist") % (
                path,
                ))
        return path

    def clean_nfs_network(self):
        net = self.cleaned_data['nfs_network']
        net = re.sub(r'\s{2,}|\n', ' ', net).strip()
        if not net:
            return net
        #only one address = CIDR or IP
        if net.find(" ") == -1:
            try:
                IPNetwork(net.encode('utf-8'))
            except NetmaskValueError:
                IPAddress(net.encode('utf-8'))
            except (AddressValueError, ValueError):
                raise forms.ValidationError(
                    _("The field is a not a valid IP address or network")
                    )
        else:
            for ip in net.split(' '):
                try:
                    IPAddress(ip.encode('utf-8'))
                except (AddressValueError, ValueError):
                    raise forms.ValidationError(
                        _("The IP '%s' is not valid.") % ip
                        )
        return net

    def clean(self):
        cdata = self.cleaned_data
        for field in ('nfs_maproot_user', 'nfs_maproot_group',
                        'nfs_mapall_user', 'nfs_mapall_group'):
            if cdata.get(field, None) in ('', '-----'):
                cdata[field] = None

        if (cdata.get('nfs_maproot_group', None) != None and
            cdata.get('nfs_maproot_user', None) == None):
            self._errors['nfs_maproot_group'] = self.error_class([
                _("Maproot group requires Maproot user"),
                ])
        if (cdata.get('nfs_mapall_group', None) != None and
            cdata.get('nfs_mapall_user', None) == None):
            self._errors['nfs_mapall_group'] = self.error_class([
                _("Mapall group requires Mapall user"),
                ])
        if (cdata.get('nfs_maproot_user', None) != None or
            cdata.get('nfs_maproot_group', None) != None):
            if cdata.get('nfs_mapall_user', None) != None:
                self._errors['nfs_mapall_user'] = self.error_class([
                    _("Maproot user/group disqualifies Mapall"),
                    ])
                del cdata['nfs_mapall_user']
            if cdata.get('nfs_mapall_group', None) != None:
                self._errors['nfs_mapall_group'] = self.error_class([
                    _("Maproot user/group disqualifies Mapall"),
                    ])
                del cdata['nfs_mapall_group']

        return cdata

    def save(self, *args, **kwargs):
        super(NFS_ShareForm, self).save(*args, **kwargs)
        notifier().reload("nfs")

    def done(self, request, events):
        if not services.objects.get(srv_service='nfs').srv_enable:
            events.append('ask_service("nfs")')
