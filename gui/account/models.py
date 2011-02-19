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
from django.db import models
from freeadmin.models import Model
from django import forms
from freenasUI.choices import UserShell
from django.contrib.auth.models import get_hexdigest
from django.utils.translation import ugettext as _

class bsdGroups(Model):
    bsdgrp_gid = models.IntegerField(
            verbose_name=_("Group ID")
            )
    bsdgrp_group = models.CharField(
            unique = True,
            max_length=120,
            verbose_name=_("Group Name")
            )
    bsdgrp_builtin = models.BooleanField(
            default=False,
            )
    class Meta:
        verbose_name = _("Group")

    class FreeAdmin:
        object_filters = {'bsdgrp_builtin__exact': False}
        object_num = -1

        icon_object = u"GroupIcon"
        icon_model = u"GroupsIcon"
        icon_add = u"AddGroupIcon"

    def __unicode__(self):
        return self.bsdgrp_group

class bsdUsers(Model):
    bsdusr_uid = models.IntegerField(
            max_length=10,
            unique="True",
            verbose_name=_("User ID")
            )
    bsdusr_username = models.CharField(
            max_length=30,
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
            verbose_name=_("Primary Group ID")
            )
    bsdusr_home = models.CharField(
            max_length=120,
            default="/nonexistent",
            verbose_name=_("Home Directory")
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
            )

    class Meta:
        verbose_name = _("User")
    class FreeAdmin:
        create_modelform = "bsdUserCreationForm"
        edit_modelform = "bsdUserChangeForm"

        object_filters = {'bsdusr_builtin__exact': False}
        object_num = -1

        icon_object = u"UserIcon"
        icon_model = u"UsersIcon"
        icon_add = u"AddUserIcon"

    def __unicode__(self):
        return self.bsdusr_username

class bsdGroupMembership(Model):
    bsdgrpmember_group = models.ForeignKey(
        bsdGroups,
        verbose_name=_("Group"),
    )
    bsdgrpmember_user = models.ForeignKey(
        bsdUsers,
        verbose_name=_("User"),
    )
