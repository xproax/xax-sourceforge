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

import glob
import logging
import os
import pwd
import re
import subprocess

from django.conf import settings
from django.contrib.formtools.wizard.views import SessionWizardView
from django.core.files.storage import FileSystemStorage
from django.forms import FileField
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.utils.translation import ugettext_lazy as _

from dojango import forms
from freenasUI import choices
from freenasUI.common.forms import ModelForm, Form
from freenasUI.freeadmin.forms import CronMultiple
from freenasUI.middleware.exceptions import MiddlewareError
from freenasUI.middleware.notifier import notifier
from freenasUI.storage.models import MountPoint
from freenasUI.system import models

log = logging.getLogger('system.forms')


class FileWizard(SessionWizardView):

    file_storage = FileSystemStorage(location='/var/tmp/firmware')

    def done(self, form_list, **kwargs):
        response = render_to_response('system/done.html', {
            #'form_list': form_list,
            'retval': getattr(self, 'retval', None),
        })
        if not self.request.is_ajax():
            response.content = ("<html><body><textarea>"
            + response.content +
            "</textarea></boby></html>")
        return response

    def get_template_names(self):
        return [
            'system/wizard_%s.html' % self.get_step_index(),
            'system/wizard.html',
            ]

    def process_step(self, form):
        proc = super(FileWizard, self).process_step(form)
        """
        We execute the form done method if there is one, for each step
        """
        if hasattr(form, 'done'):
            retval = form.done(request=self.request,
                form_list=self.form_list,
                wizard=self)
            if self.get_step_index() == self.steps.count - 1:
                self.retval = retval
        return proc

    def render_to_response(self, context, **kwargs):
        response = super(FileWizard, self).render_to_response(context,
            **kwargs)
        # This is required for the workaround dojo.io.frame for file upload
        if not self.request.is_ajax():
            return HttpResponse("<html><body><textarea>"
            + response.rendered_content +
            "</textarea></boby></html>")
        return response


class FirmwareWizard(FileWizard):

    def done(self, form_list, **kwargs):
        cleaned_data = self.get_all_cleaned_data()
        firmware = cleaned_data.get('firmware')
        path = self.file_storage.path(firmware.name)

        #form = form_list[1]
        #return self.render_revalidation_failure('1', form)

        retval = notifier().validate_update(path)
        if not retval:
            #msg = _(u"Invalid firmware")
            #self._errors["firmware"] = self.error_class([msg])
            #del cleaned_data["firmware"]
            self.file_storage.delete(firmware.name)
            raise MiddlewareError("Invalid firmware")
        elif 'sha256' in cleaned_data:
            checksum = notifier().checksum(path)
            if checksum != str(cleaned_data['sha256']).strip():
                self.file_storage.delete(firmware.name)
                raise MiddlewareError("Invalid firmware")
                #msg = _(u"Invalid checksum")
                #self._errors["firmware"] = self.error_class([msg])
                #del cleaned_data["firmware"]

        notifier().apply_update(path)
        self.request.session['allow_reboot'] = True

        response = render_to_response('system/done.html', {
            #'form_list': form_list,
            'retval': getattr(self, 'retval', None),
        })
        if not self.request.is_ajax():
            response.content = ("<html><body><textarea>"
            + response.content +
            "</textarea></boby></html>")
        return response


class SettingsForm(ModelForm):

    class Meta:
        model = models.Settings
        widgets = {
            'stg_timezone': forms.widgets.FilteringSelect(),
            'stg_language': forms.widgets.FilteringSelect(),
            'stg_kbdmap': forms.widgets.FilteringSelect(),
        }

    def __init__(self, *args, **kwargs):
        super(SettingsForm, self).__init__(*args, **kwargs)
        self.instance._original_stg_guiprotocol = self.instance.stg_guiprotocol
        self.instance._original_stg_guiaddress = self.instance.stg_guiaddress
        self.instance._original_stg_guiport = self.instance.stg_guiport
        self.instance._original_stg_syslogserver = self.instance.stg_syslogserver
        self.fields['stg_language'].choices = settings.LANGUAGES
        self.fields['stg_language'].label = _("Language (Require UI reload)")
        self.fields['stg_guiaddress'] = forms.ChoiceField(
            label=self.fields['stg_guiaddress'].label
            )
        self.fields['stg_guiaddress'].choices = [['0.0.0.0', '0.0.0.0']] + list(choices.IPChoices())

    def clean_stg_guiport(self):
        val = self.cleaned_data.get("stg_guiport")
        if val == '':
            return val
        try:
            val = int(val)
            if val < 1 or val > 65535:
                raise forms.ValidationError(_("You must specify a number between 1 and 65535, inclusive."))
        except ValueError:
            raise forms.ValidationError(_("Number is required."))
        return val

    def save(self):
        super(SettingsForm, self).save()
        if self.instance._original_stg_syslogserver != self.instance.stg_syslogserver:
            notifier().restart("syslogd")
        notifier().reload("timeservices")

    def done(self, request, events):
        if self.instance._original_stg_guiprotocol != self.instance.stg_guiprotocol or \
            self.instance._original_stg_guiaddress != self.instance.stg_guiaddress or \
            self.instance._original_stg_guiport != self.instance.stg_guiport:
            if self.instance.stg_guiaddress == "0.0.0.0":
                address = request.META['HTTP_HOST'].split(':')[0]
            else:
                address = self.instance.stg_guiaddress
            newurl = "%s://%s" % (self.instance.stg_guiprotocol,
                                    address
                                    )
            if self.instance.stg_guiport != '':
                newurl += ":" + self.instance.stg_guiport
            if self.instance._original_stg_guiprotocol == 'http':
                notifier().start_ssl("nginx")
            events.append("restartHttpd('%s')" % newurl)


class NTPForm(ModelForm):

    force = forms.BooleanField(label=_("Force"), required=False)

    class Meta:
        model = models.NTPServer

    def __init__(self, *args, **kwargs):
        super(NTPForm, self).__init__(*args, **kwargs)
        self.usable = True

    def clean_ntp_address(self):
        addr = self.cleaned_data.get("ntp_address")
        p1 = subprocess.Popen(["ntpq", "-c", "rv", addr],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        data = p1.communicate()[0]
        #TODO: ntpq does not return error code in case of errors
        if not re.search(r'version=', data):
            self.usable = False
        return addr

    def clean_ntp_maxpoll(self):
        maxp = self.cleaned_data.get("ntp_maxpoll")
        minp = self.cleaned_data.get("ntp_minpoll")
        if not maxp > minp:
            raise forms.ValidationError(_("Max Poll should be higher than Min Poll"))
        return maxp

    def clean(self):
        cdata = self.cleaned_data
        if not cdata.get("force", False) and not self.usable:
            self._errors['ntp_address'] = self.error_class([_("Server could not be reached. Check \"Force\" to continue regardless.")])
            del cdata['ntp_address']
        return cdata

    def save(self):
        super(NTPForm, self).save()
        notifier().start("ix-ntpd")
        notifier().restart("ntpd")


class AdvancedForm(ModelForm):

    class Meta:
        exclude = ('adv_zeroconfbonjour', 'adv_tuning', 'adv_firmwarevc', 'adv_systembeep')
        model = models.Advanced

    def __init__(self, *args, **kwargs):
        super(AdvancedForm, self).__init__(*args, **kwargs)
        self.instance._original_adv_motd = self.instance.adv_motd
        self.instance._original_adv_consolemenu = self.instance.adv_consolemenu
        self.instance._original_adv_powerdaemon = self.instance.adv_powerdaemon
        self.instance._original_adv_serialconsole = self.instance.adv_serialconsole
        self.instance._original_adv_consolescreensaver = self.instance.adv_consolescreensaver
        self.instance._original_adv_consolemsg = self.instance.adv_consolemsg
        self.instance._original_adv_advancedmode = self.instance.adv_advancedmode

    def save(self):
        super(AdvancedForm, self).save()
        if self.instance._original_adv_motd != self.instance.adv_motd:
            notifier().start("motd")
        if self.instance._original_adv_consolemenu != self.instance.adv_consolemenu:
            notifier().start("ttys")
        if self.instance._original_adv_powerdaemon != self.instance.adv_powerdaemon:
            notifier().restart("powerd")
        if self.instance._original_adv_serialconsole != self.instance.adv_serialconsole:
            notifier().start("ttys")
            notifier().start("loader")
        if self.instance._original_adv_consolescreensaver != self.instance.adv_consolescreensaver:
            if self.instance.adv_consolescreensaver == 0:
                notifier().stop("saver")
            else:
                notifier().start("saver")
            notifier().start("loader")

    def done(self, request, events):
        if self.instance._original_adv_consolemsg != self.instance.adv_consolemsg:
            if self.instance.adv_consolemsg:
                events.append("_msg_start()")
            else:
                events.append("_msg_stop()")
        if self.instance._original_adv_advancedmode != self.instance.adv_advancedmode:
            #Invalidate cache
            request.session.pop("adv_mode", None)


class EmailForm(ModelForm):
    em_pass1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput,
        required=False)
    em_pass2 = forms.CharField(
        label=_("Password confirmation"),
        widget=forms.PasswordInput,
        help_text=_("Enter the same password as above, for verification."),
        required=False)

    class Meta:
        model = models.Email
        exclude = ('em_pass',)

    def __init__(self, *args, **kwargs):
        super(EmailForm, self).__init__(*args, **kwargs)
        try:
            self.fields['em_pass1'].initial = self.instance.em_pass
            self.fields['em_pass2'].initial = self.instance.em_pass
        except:
            pass
        self.fields['em_smtp'].widget.attrs['onChange'] = ('javascript:'
            'toggleGeneric("id_em_smtp", ["id_em_pass1", "id_em_pass2", '
            '"id_em_user"], true);')
        ro = True

        if len(self.data) > 0:
            if self.data.get("em_smtp", None) == "on":
                ro = False
        else:
            if self.instance.em_smtp == True:
                ro = False
        if ro:
            self.fields['em_user'].widget.attrs['disabled'] = 'disabled'
            self.fields['em_pass1'].widget.attrs['disabled'] = 'disabled'
            self.fields['em_pass2'].widget.attrs['disabled'] = 'disabled'

    def clean_em_user(self):
        if self.cleaned_data['em_smtp'] == True and \
                self.cleaned_data['em_user'] == "":
            raise forms.ValidationError(_("This field is required"))
        return self.cleaned_data['em_user']

    def clean_em_pass1(self):
        if self.cleaned_data['em_smtp'] == True and \
                self.cleaned_data['em_pass1'] == "":
            raise forms.ValidationError(_("This field is required"))
        return self.cleaned_data['em_pass1']

    def clean_em_pass2(self):
        if self.cleaned_data['em_smtp'] == True and \
                self.cleaned_data.get('em_pass2', "") == "":
            raise forms.ValidationError(_("This field is required"))
        pass1 = self.cleaned_data.get("em_pass1", "")
        pass2 = self.cleaned_data.get("em_pass2", "")
        if pass1 != pass2:
            raise forms.ValidationError(_("The two password fields didn't match."))
        return pass2

    def save(self, commit=True):
        email = super(EmailForm, self).save(commit=False)
        if commit:
            email.em_pass = self.cleaned_data['em_pass2']
            email.save()
        return email


class SSLForm(ModelForm):

    class Meta:
        model = models.SSL

    def save(self):
        super(SSLForm, self).save()
        notifier().start_ssl("nginx")


class SMARTTestForm(ModelForm):

    class Meta:
        model = models.SMARTTest
        widgets = {
            'smarttest_hour': CronMultiple(
                attrs={'numChoices': 24, 'label': _("hour")}
                ),
            'smarttest_daymonth': CronMultiple(
                attrs={'numChoices': 31, 'start': 1, 'label': _("day of month")}
                ),
            'smarttest_dayweek': forms.CheckboxSelectMultiple(
                choices=choices.WEEKDAYS_CHOICES
                ),
            'smarttest_month': forms.CheckboxSelectMultiple(
                choices=choices.MONTHS_CHOICES
                ),
        }

    def __init__(self, *args, **kwargs):
        if 'instance' in kwargs:
            ins = kwargs.get('instance')
            ins.smarttest_month = ins.smarttest_month.replace("10", "a").replace("11", "b").replace("12", "c")
            if ins.smarttest_daymonth == "..":
                ins.smarttest_daymonth = '*/1'
            elif ',' in ins.smarttest_daymonth:
                days = [int(day) for day in ins.smarttest_daymonth.split(',')]
                gap = days[1] - days[0]
                everyx = range(0, 32, gap)[1:]
                if everyx == days:
                    ins.smarttest_daymonth = '*/%d' % gap
            if ins.smarttest_hour == "..":
                ins.smarttest_hour = '*/1'
            elif ',' in ins.smarttest_hour:
                hours = [int(hour) for hour in ins.smarttest_hour.split(',')]
                gap = hours[1] - hours[0]
                everyx = range(0, 24, gap)
                if everyx == hours:
                    ins.smarttest_hour = '*/%d' % gap
        super(SMARTTestForm, self).__init__(*args, **kwargs)
        self.fields.keyOrder.remove('smarttest_disks')
        self.fields.keyOrder.insert(0, 'smarttest_disks')

    def save(self):
        super(SMARTTestForm, self).save()
        notifier().restart("smartd")

    def clean_smarttest_hour(self):
        h = self.cleaned_data.get("smarttest_hour")
        if h.startswith('*/'):
            each = int(h.split('*/')[1])
            if each == 1:
                return ".."
        return h

    def clean_smarttest_daymonth(self):
        h = self.cleaned_data.get("smarttest_daymonth")
        if h.startswith('*/'):
            each = int(h.split('*/')[1])
            if each == 1:
                return ".."
        return h

    def clean_smarttest_month(self):
        m = eval(self.cleaned_data.get("smarttest_month"))
        m = ",".join(m)
        m = m.replace("a", "10").replace("b", "11").replace("c", "12")
        return m

    def clean_smarttest_dayweek(self):
        w = eval(self.cleaned_data.get("smarttest_dayweek"))
        w = ",".join(w)
        return w

    def clean(self):
        disks = self.cleaned_data.get("smarttest_disks")
        test = self.cleaned_data.get("smarttest_type")
        used_disks = []
        for disk in disks:
            qs = models.SMARTTest.objects.filter(
                smarttest_disks__in=[disk],
                smarttest_type=test,
                )
            if self.instance.id:
                qs = qs.exclude(id=self.instance.id)
            if qs.count() > 0:
                used_disks.append(disk.disk_name)
        if used_disks:
            self._errors['smarttest_disks'] = self.error_class([
                _("The following disks already have tests for this type: "
                    "%s" % (
                        ', '.join(used_disks),
                    )),
                ])
            self.cleaned_data.pop("smarttest_disks", None)
        return self.cleaned_data


class FirmwareTemporaryLocationForm(Form):
    mountpoint = forms.ChoiceField(
        label=_("Place to temporarily place firmware file"),
        help_text=_("The system will use this place to temporarily store the "
            "firmware file before it's being applied."),
        choices=(),
        widget=forms.Select(attrs={'class': 'required'}),
        )

    def __init__(self, *args, **kwargs):
        super(FirmwareTemporaryLocationForm, self).__init__(*args, **kwargs)
        self.fields['mountpoint'].choices = [(x.mp_path, x.mp_path) for x in MountPoint.objects.exclude(mp_volume__vol_fstype='iscsi')]

    def done(self, *args, **kwargs):
        notifier().change_upload_location(self.cleaned_data["mountpoint"].__str__())


class FirmwareUploadForm(Form):
    firmware = FileField(label=_("New image to be installed"), required=True)
    sha256 = forms.CharField(label=_("SHA256 sum for the image"), required=True)


class ConfigUploadForm(Form):
    config = FileField(label=_("New config to be installed"))


class CronJobForm(ModelForm):

    class Meta:
        model = models.CronJob
        widgets = {
            'cron_command': forms.widgets.TextInput(),
            'cron_minute': CronMultiple(
                attrs={'numChoices': 60, 'label': _("minute")}
                ),
            'cron_hour': CronMultiple(
                attrs={'numChoices': 24, 'label': _("hour")}
                ),
            'cron_daymonth': CronMultiple(
                attrs={'numChoices': 31, 'start': 1, 'label': _("day of month")}
                ),
            'cron_dayweek': forms.CheckboxSelectMultiple(
                choices=choices.WEEKDAYS_CHOICES
                ),
            'cron_month': forms.CheckboxSelectMultiple(
                choices=choices.MONTHS_CHOICES
                ),
        }

    def __init__(self, *args, **kwargs):
        if 'instance' in kwargs:
            ins = kwargs.get('instance')
            if ins.cron_month == '*':
                ins.cron_month = "1,2,3,4,5,6,7,8,9,a,b,c"
            else:
                ins.cron_month = ins.cron_month.replace("10", "a").replace("11", "b").replace("12", "c")
            if ins.cron_dayweek == '*':
                ins.cron_dayweek = "1,2,3,4,5,6,7"
        super(CronJobForm, self).__init__(*args, **kwargs)

    def clean_cron_user(self):
        user = self.cleaned_data.get("cron_user")
        # See #1061 or FreeBSD PR 162976
        if len(user) > 17:
            raise forms.ValidationError("Usernames cannot exceed 17 characters for cronjobs")
        # Windows users can have spaces in their usernames
        # http://www.freebsd.org/cgi/query-pr.cgi?pr=164808
        if ' ' in user:
            raise forms.ValidationError("Usernames cannot have spaces")
        return user

    def clean_cron_month(self):
        m = eval(self.cleaned_data.get("cron_month"))
        if len(m) == 12:
            return '*'
        m = ",".join(m)
        m = m.replace("a", "10").replace("b", "11").replace("c", "12")
        return m

    def clean_cron_dayweek(self):
        w = eval(self.cleaned_data.get("cron_dayweek"))
        if len(w) == 7:
            return '*'
        w = ",".join(w)
        return w

    def save(self):
        super(CronJobForm, self).save()
        notifier().restart("cron")


class RsyncForm(ModelForm):

    class Meta:
        model = models.Rsync
        widgets = {
            'rsync_minute': CronMultiple(
                attrs={'numChoices': 60, 'label': _("minute")}
                ),
            'rsync_hour': CronMultiple(
                attrs={'numChoices': 24, 'label': _("hour")}
                ),
            'rsync_daymonth': CronMultiple(
                attrs={'numChoices': 31, 'start': 1, 'label': _("day of month")}
                ),
            'rsync_dayweek': forms.CheckboxSelectMultiple(
                choices=choices.WEEKDAYS_CHOICES
                ),
            'rsync_month': forms.CheckboxSelectMultiple(
                choices=choices.MONTHS_CHOICES
                ),
        }

    def __init__(self, *args, **kwargs):
        if 'instance' in kwargs:
            ins = kwargs.get('instance')
            if ins.rsync_month == '*':
                ins.rsync_month = "1,2,3,4,5,6,7,8,9,a,b,c"
            else:
                ins.rsync_month = ins.rsync_month.replace("10", "a").replace("11", "b").replace("12", "c")
            if ins.rsync_dayweek == '*':
                ins.rsync_dayweek = "1,2,3,4,5,6,7"
        super(RsyncForm, self).__init__(*args, **kwargs)
        self.fields['rsync_mode'].widget.attrs['onChange'] = "rsyncModeToggle();"

    def clean_rsync_user(self):
        user = self.cleaned_data.get("rsync_user")
        # See #1061 or FreeBSD PR 162976
        if len(user) > 17:
            raise forms.ValidationError("Usernames cannot exceed 17 "
                "characters for rsync tasks")
        # Windows users can have spaces in their usernames
        # http://www.freebsd.org/cgi/query-pr.cgi?pr=164808
        if ' ' in user:
            raise forms.ValidationError("Usernames cannot have spaces")
        return user

    def clean_rsync_remotemodule(self):
        mode = self.cleaned_data.get("rsync_mode")
        val = self.cleaned_data.get("rsync_remotemodule")
        if mode == 'module' and not val:
            raise forms.ValidationError(_("This field is required"))
        return val

    def clean_rsync_remotepath(self):
        mode = self.cleaned_data.get("rsync_mode")
        val = self.cleaned_data.get("rsync_remotepath")
        if mode == 'ssh' and not val:
            raise forms.ValidationError(_("This field is required"))
        return val

    def clean_rsync_month(self):
        m = eval(self.cleaned_data.get("rsync_month"))
        if len(m) == 12:
            return '*'
        m = ",".join(m)
        m = m.replace("a", "10").replace("b", "11").replace("c", "12")
        return m

    def clean_rsync_dayweek(self):
        w = eval(self.cleaned_data.get("rsync_dayweek"))
        if len(w) == 7:
            return '*'
        w = ",".join(w)
        return w

    def clean_rsync_extra(self):
        extra = self.cleaned_data.get("rsync_extra")
        if extra:
            extra = extra.replace('\n', ' ')
        return extra

    def clean(self):
        cdata = self.cleaned_data
        mode = cdata.get("rsync_mode")
        user = cdata.get("rsync_user")
        if mode == 'ssh':
            try:
                home = pwd.getpwnam(user).pw_dir
                search = os.path.join(home, ".ssh", "id_[edr]*.*")
                if not glob.glob(search):
                    raise ValueError
            except (KeyError, ValueError, AttributeError, TypeError):
                self._errors['rsync_user'] = self.error_class([
                    _("In order to use rsync over SSH you need a user<br />"
                      "with a public key (DSA/ECDSA/RSA) set up in home dir."),
                    ])
                cdata.pop('rsync_user', None)
        return cdata

    def save(self):
        super(RsyncForm, self).save()
        notifier().restart("cron")

"""
TODO: Move to a unittest .py file.

invalid_sysctls = [
    'a.0',
    'a.b',
    'a..b',
    'a._.b',
    'a.b._.c',
    '0',
    '0.a',
    'a-b',
    'a',
]

valid_sysctls = [
    'ab.0',
    'ab.b',
    'smbios.system.version',
    'dev.emu10kx.0.multichannel_recording',
    'hw.bce.tso0',
    'kern.sched.preempt_thresh',
    'net.inet.tcp.tso',
]

assert len(filter(SYSCTL_VARNAME_FORMAT_RE.match, invalid_sysctls)) == 0
assert len(filter(SYSCTL_VARNAME_FORMAT_RE.match, valid_sysctls)) == len(valid_sysctls)
"""

# NOTE:
# - setenv in the kernel is more permissive than this, but we want to reduce
#   user footshooting.
# - this doesn't reject all benign input; it just rejects input that would
#   break system boots.
# XXX: note that I'm explicitly rejecting input for root sysctl nodes.
SYSCTL_TUNABLE_VARNAME_FORMAT = """Variable names must:
1. Start with a letter.
2. End with a letter or number.
3. Can contain a combination of alphanumeric characters, numbers, underscores,
   and/or periods.
"""
SYSCTL_VARNAME_FORMAT_RE = \
    re.compile('[a-z][a-z0-9_]+\.([a-z0-9_]+\.)*[a-z0-9_]+', re.I)

TUNABLE_VARNAME_FORMAT_RE = \
    re.compile('[a-z][a-z0-9_]+\.*([a-z0-9_]+\.)*[a-z0-9_]+', re.I)


class SysctlForm(ModelForm):
    class Meta:
        model = models.Sysctl

    def clean_sysctl_comment(self):
        return self.cleaned_data.get('sysctl_comment').strip()

    def clean_sysctl_mib(self):
        value = self.cleaned_data.get('sysctl_mib').strip()
        if SYSCTL_VARNAME_FORMAT_RE.match(value):
            return value
        raise forms.ValidationError(_(SYSCTL_TUNABLE_VARNAME_FORMAT))

    def clean_sysctl_value(self):
        value = self.cleaned_data.get('sysctl_value')
        if '"' in value or "'" in value:
            raise forms.ValidationError(_('Quotes are not allowed'))
        return value

    def save(self):
        super(SysctlForm, self).save()
        notifier().reload("sysctl")


class TunableForm(ModelForm):
    class Meta:
        model = models.Tunable

    def clean_ldr_comment(self):
        return self.cleaned_data.get('ldr_comment').strip()

    def clean_ldr_value(self):
        value = self.cleaned_data.get('ldr_value')
        if '"' in value or "'" in value:
            raise forms.ValidationError(_('Quotes are not allowed'))
        return value

    def clean_ldr_var(self):
        value = self.cleaned_data.get('ldr_var').strip()
        if TUNABLE_VARNAME_FORMAT_RE.match(value):
            return value
        raise forms.ValidationError(_(SYSCTL_TUNABLE_VARNAME_FORMAT))

    def save(self):
        super(TunableForm, self).save()
        notifier().reload("loader")


class DebugForm(Form):
    ad = forms.BooleanField(
        label=_("Dump Active Directory Configuration"),
        initial=True,
        required=False,
        )
    adcache = forms.BooleanField(
        label=_("Dump (AD|LDAP) Cache"),
        initial=False,
        required=False,
        )
    geom = forms.BooleanField(
        label=_("Dump GEOM configuration"),
        initial=True,
        required=False,
        )
    hardware = forms.BooleanField(
        label=_("Dump Hardware Configuration"),
        initial=True,
        required=False,
        )
    ldap = forms.BooleanField(
        label=_("Dump LDAP Configuration"),
        initial=True,
        required=False,
        )
    loader = forms.BooleanField(
        label=_("Loader Configuration Information"),
        initial=True,
        required=False,
        )
    network = forms.BooleanField(
        label=_("Dump Network Configuration"),
        initial=True,
        required=False,
        )
    ssl = forms.BooleanField(
        label=_("Dump SSL Configuration"),
        initial=True,
        required=False,
        )
    sysctl = forms.BooleanField(
        label=_("Dump Sysctl Configuration"),
        initial=True,
        required=False,
        )
    system = forms.BooleanField(
        label=_("Dump System Information"),
        initial=True,
        required=False,
        )
    zfs = forms.BooleanField(
        label=_("Dump ZFS configuration"),
        initial=True,
        required=False,
        )

    def get_options(self):
        opts = []
        if self.cleaned_data.get("ad"):
            opts.append("-a")
        if self.cleaned_data.get("adcache"):
            opts.append("-c")
        if self.cleaned_data.get("geom"):
            opts.append("-g")
        if self.cleaned_data.get("hardware"):
            opts.append("-h")
        if self.cleaned_data.get("ldap"):
            opts.append("-l")
        if self.cleaned_data.get("loader"):
            opts.append("-T")
        if self.cleaned_data.get("network"):
            opts.append("-n")
        if self.cleaned_data.get("ssl"):
            opts.append("-s")
        if self.cleaned_data.get("sysctl"):
            opts.append("-y")
        if self.cleaned_data.get("system"):
            opts.append("-t")
        if self.cleaned_data.get("zfs"):
            opts.append("-z")
        return opts
