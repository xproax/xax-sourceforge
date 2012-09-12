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
from django.db import models
from django.utils.translation import ugettext_lazy as _

from freenasUI.freeadmin.models import Model, PathField
from freenasUI.middleware.notifier import notifier


class bsdGroups(Model):
    bsdgrp_gid = models.IntegerField(
            verbose_name=_("Group ID")
            )
    bsdgrp_group = models.CharField(
            unique=True,
            max_length=120,
            verbose_name=_("Group Name")
            )
    bsdgrp_builtin = models.BooleanField(
            default=False,
            editable=False,
            )

    class Meta:
        verbose_name = _("Group")
        verbose_name_plural = _("Groups")

    class FreeAdmin:
        delete_form = "DeleteGroupForm"
        object_filters = {'bsdgrp_builtin__exact': False}
        object_num = -1

        icon_object = u"GroupIcon"
        icon_model = u"GroupsIcon"
        icon_add = u"AddGroupIcon"
        icon_view = u"ViewAllGroupsIcon"

    def __unicode__(self):
        return self.bsdgrp_group

    def delete(self, using=None, reload=True):
        if self.bsdgrp_builtin == True:
            raise ValueError(_("Group %s is built-in and can not be "
                "deleted!") % (self.bsdgrp_group))
        notifier().user_deletegroup(self.bsdgrp_group.__str__())
        super(bsdGroups, self).delete(using)
        if reload:
            notifier().reload("user")


def get_sentinel_group():
    return bsdGroups.objects.get(bsdgrp_group='nobody')


class bsdUsers(Model):
    bsdusr_uid = models.IntegerField(
            unique=True,
            verbose_name=_("User ID")
            )
    bsdusr_username = models.CharField(
            max_length=16,
            unique=True,
            default=_('User &'),
            verbose_name=_("Username")
            )
    bsdusr_unixhash = models.CharField(
            max_length=128,
            blank=True,
            default='*',
            verbose_name=_("Hashed UNIX password")
            )
    bsdusr_smbhash = models.CharField(
            max_length=128,
            blank=True,
            default='*',
            verbose_name=_("Hashed SMB password")
            )
    bsdusr_group = models.ForeignKey(
            bsdGroups,
            on_delete=models.SET(get_sentinel_group),
            verbose_name=_("Primary Group ID")
            )
    bsdusr_home = PathField(
            default="/nonexistent",
            verbose_name=_("Home Directory"),
            includes=["/root", "/nonexistent"],
            )
    bsdusr_shell = models.CharField(
            max_length=120,
            default='/bin/csh',
            verbose_name=_("Shell")
            )
    bsdusr_full_name = models.CharField(
            max_length=120,
            verbose_name=_("Full Name")
            )
    bsdusr_builtin = models.BooleanField(
            default=False,
            editable=False,
            )
    bsdusr_email = models.EmailField(
            verbose_name=_("E-mail"),
            blank=True
            )
    bsdusr_password_disabled = models.BooleanField(
            verbose_name=_("Disable password login"),
            default=False,
            )
    bsdusr_locked = models.BooleanField(
            verbose_name=_("Lock user"),
            default=False,
            )

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    class FreeAdmin:
        create_modelform = "bsdUserCreationForm"
        edit_modelform = "bsdUserChangeForm"

        object_filters = {'bsdusr_builtin__exact': False}
        object_num = -1

        icon_object = u"UserIcon"
        icon_model = u"UsersIcon"
        icon_add = u"AddUserIcon"
        icon_view = u"ViewAllUsersIcon"

    def __unicode__(self):
        return self.bsdusr_username

    def delete(self, using=None, reload=True):
        if self.bsdusr_builtin == True:
            raise ValueError(_("User %s is built-in and can not be "
                "deleted!") % (self.bsdusr_username))
        notifier().user_deleteuser(self.bsdusr_username.__str__())
        try:
            gobj = self.bsdusr_group
            count = bsdGroupMembership.objects.filter(
                bsdgrpmember_group=gobj).count()
            count2 = bsdUsers.objects.filter(bsdusr_group=gobj).exclude(
                id=self.id).count()
            if not gobj.bsdgrp_builtin and count == 0 and count2 == 0:
                gobj.delete(reload=False)
        except:
            pass
        super(bsdUsers, self).delete(using)
        if reload:
            notifier().reload("user")


class bsdGroupMembership(Model):
    bsdgrpmember_group = models.ForeignKey(
        bsdGroups,
        verbose_name=_("Group"),
    )
    bsdgrpmember_user = models.ForeignKey(
        bsdUsers,
        verbose_name=_("User"),
    )
