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

from django.conf.urls.defaults import *
from django.views.generic import list_detail

urlpatterns = patterns('network.views',
    (r'^$', 'network'),
    url(r'^home/$', 'network2', name='network_home'),
    url(r'^lagg/$', 'lagg', name='network_lagg'),
    url(r'^interface/$', 'interface', name='network_interface'),
    url(r'^vlan/$', 'vlan', name='network_vlan'),
    url(r'^static-route/$', 'staticroute', name='network_staticroute'),
    url(r'^lagg/add/$', 'lagg_add', name='network_lagg_add'),
    url(r'lagg/members/(?P<object_id>\d+)/$', 'lagg_members2', name="network_lagg_members"),
    (r'^global/(?P<objtype>\w+)/$', 'network'),
    (r'laggmembers/view/(?P<object_id>\d+)/$', 'lagg_members'),
    url(r'^global-configuration/$', 'globalconf', name='network_globalconf'),
    (r'(?P<objtype>\w+)/view/$', 'network'),
    (r'(?P<objtype>\w+)/edit/(?P<object_id>\d+)/$', 'generic_update'),
    (r'(?P<objtype>\w+)/delete/(?P<object_id>\d+)/$', 'generic_delete'),
    )
