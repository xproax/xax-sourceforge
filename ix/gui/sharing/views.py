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

from freenasUI.sharing.forms import * 
from django.forms.models import modelformset_factory
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.contrib.auth import authenticate, login, logout
from django.template import RequestContext
from django.http import Http404
from django.views.generic.list_detail import object_detail, object_list
from freenasUI.middleware.notifier import notifier
import os, commands


@login_required
def sharing(request, sharetype = None):
    cifs_share = CIFS_ShareForm(request.POST)
    afp_share = AFP_ShareForm(request.POST)
    nfs_share = NFS_ShareForm(request.POST)
    if request.method == 'POST':
        if sharetype == 'cifs':
            cifs_share.save()
        elif sharetype == 'afp':
            afp_share.save()
        elif sharetype == 'nfs':
            nfs_share.save()
        else:
            raise Http404() # TODO: Should be something better
        return HttpResponseRedirect('/sharing/')
    else:
        mountpoint_list = MountPoint.objects.all()
        cifs_share_list = CIFS_Share.objects.all()
        afp_share_list = AFP_Share.objects.all()
        nfs_share_list = NFS_Share.objects.all()
        cifs_share = CIFS_ShareForm()
        afp_share = AFP_ShareForm()
        nfs_share = NFS_ShareForm()
    variables = RequestContext(request, {
        'mountpoint_list': mountpoint_list,
        'cifs_share_list': cifs_share_list,
        'afp_share_list': afp_share_list,
        'nfs_share_list': nfs_share_list,
        'cifs_share': cifs_share,
        'afp_share': afp_share,
        'nfs_share': nfs_share,
        })
    return render_to_response('sharing/index.html', variables)

