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
from django.db.models.base import ModelBase

class FreeAdminWrapper(object):

    create_modelform = None
    edit_modelform = None
    exclude_fields = []
    deletable = True
    menu_child_of = None

    nav_extra = {}

    object_filters = {}
    object_num = -1

    icon_model = None
    icon_object = None
    icon_add = None
    icon_view = None

    composed_fields = []

    extra_js = ''

    def __init__(self, c=None):

        if c is None:
            return None
        obj = c()
        for i in dir(obj):
            if not i.startswith("__"):
                if not hasattr(self, i):
                    raise Exception("The attribute '%s' is a not valid in FreeAdmin" % i)
                self.__setattr__(i, getattr(obj, i))

class FreeAdminBase(ModelBase):
    def __new__(cls, name, bases, attrs):
        new_class = ModelBase.__new__(cls, name, bases, attrs)
        if hasattr(new_class, 'FreeAdmin'):
            new_class.add_to_class('_admin', FreeAdminWrapper(new_class.FreeAdmin))
        else:
            new_class.add_to_class('_admin', FreeAdminWrapper())

        return new_class

class Model(models.Model):
    __metaclass__ = FreeAdminBase

    class Meta:
        abstract = True
