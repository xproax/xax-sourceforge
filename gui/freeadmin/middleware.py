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
from cStringIO import StringIO

import base64
import datetime
import json
import os
import re
import sys
import cProfile
import oauth2 as oauth

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, UNUSABLE_PASSWORD
from django.contrib.auth import login, get_backends
from django.contrib.sites.models import Site
from django.http import HttpResponse
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.translation import ugettext as _

from freenasUI import settings as mysettings
from freenasUI.freeadmin.views import JsonResponse
from freenasUI.middleware.exceptions import MiddlewareError
from freenasUI.services.exceptions import ServiceFailed
from freenasUI.services.models import RPCToken
from freenasUI.system.models import Settings

from syslog import syslog, LOG_DEBUG

COMMENT_SYNTAX = (
    (re.compile(r'^application/(.*\+)?xml|text/html$', re.I), '<!--', '-->'),
    (re.compile(r'^application/j(avascript|son)$',     re.I), '/*',   '*/'),
    )


def public(f):
    f.__is_public = True
    return f


def http_auth_basic(func):

    def view(request, *args, **kwargs):
        authorized = False
        try:
            params = None
            syslog(LOG_DEBUG, "+-----------------------------------------------+")
            for key in request.REQUEST:
                syslog(LOG_DEBUG, "key: %s, val: %s" % (key, request.REQUEST[key]))
            

            for key in request.REQUEST:
                try:
                    params = json.loads(key)
                    break

                except:
                    params = None

            key = request.REQUEST.get("oauth_consumer_key", None)
            host = "%s://%s" % ('https' if request.is_secure() else 'http', request.get_host(),)
            uurl = host + request.path

            oreq = oauth.Request(request.method, uurl, request.REQUEST, '', False)
            server = oauth.Server()
 
            cons = oauth.Consumer(key, settings.OAUTH_PARTNERS[key])
            server.add_signature_method(oauth.SignatureMethod_HMAC_SHA1())

            try:
                server.verify_request(oreq, cons, None)
                authorized = True

            except oauth.Error, e:
                syslog(LOG_DEBUG, "auth error = %s" % e)
                authorized = False

            except KeyError, e:
                syslog(LOG_DEBUG, "auth error = %s" % e)
                authorized = False

            if not authorized:
                return HttpResponse(json.dumps({
                    'jsonrpc': params.get('jsonrpc'),
                    'error': {
                        'code': '500',
                        'message': 'Not authenticated',
                        },
                    'id': params.get('id'),
                }))

            syslog(LOG_DEBUG, "AUTHORIZED = %s" % authorized)

            if request.method == "POST":
                data = json.loads(request.POST.keys()[0])
                method = data.get("method")

                if method in (
                    'plugins.is_authenticated',
                    'auth.getToken',
                    ):
                    authorized = True

            if authorized:
                syslog(LOG_DEBUG, "FUNC = %s" % func)
                return func(request, *args, **kwargs)

        except Exception, e:
            syslog(LOG_DEBUG, "AUTHORIZATION ERROR: %s" % e)
            pass

        # FIXME: better error handling
        return HttpResponse(json.dumps({
            'jsonrpc': data.get("jsonrpc"),
            'error': {
                'code': '500',
                'message': 'Not authenticated',
                },
            'id': data.get("id"),
        }))

    return view


class RequireLoginMiddleware(object):
    """
    Middleware component that makes every view be login_required
    unless its decorated with @public
    """
    def process_view(self, request, view_func, view_args, view_kwargs):

        # Bypass this middleware in case URLCONF is different
        # This is required so django tests can run
        if settings.ROOT_URLCONF != mysettings.ROOT_URLCONF:
                    return None

        if not request.user.is_authenticated():
            user = User.objects.filter(is_superuser=True,
                password=UNUSABLE_PASSWORD)
            if user.exists():
                user = user[0]
                backend = get_backends()[0]
                user.backend = "%s.%s" % (backend.__module__,
                    backend.__class__.__name__)
                login(request, user)

        if request.path == settings.LOGIN_URL:
            return None
        if hasattr(view_func, '__is_public'):
            return None

        # JSON-RPC calls are authenticated through HTTP Basic
        if request.path.startswith('/plugins/json/'):
            return http_auth_basic(view_func)(request, *view_args, **view_kwargs)

        return login_required(view_func)(request, *view_args, **view_kwargs)


class LocaleMiddleware(object):

    def process_request(self, request):
        if request.method == 'GET' and 'lang' in request.GET:
            language = request.GET['lang']
        else:
            #FIXME we could avoid this db hit using a cache,
            # invalidated when settings are edited
            language = Settings.objects.order_by('-id')[0].stg_language

        for lang in settings.LANGUAGES:
            if lang[0] == language:
                translation.activate(language)

    def process_response(self, request, response):
        patch_vary_headers(response, ('Accept-Language',))
        if 'Content-Language' not in response:
            response['Content-Language'] = translation.get_language()
        translation.deactivate()
        return response


class CatchError(object):

    def process_response(self, request, response):
        if sys.exc_type and sys.exc_type in (MiddlewareError, ServiceFailed):
            excp = sys.exc_info()[1]
            kwargs = {
                'error': True,
                'message': _("Error: %s") % unicode(excp.value),
                }
            if not request.is_ajax():
                kwargs['enclosed'] = True
            return JsonResponse(**kwargs)
        return response


class ProfileMiddleware(object):
    """
    Based on
    http://www.no-ack.org/2010/12/yet-another-profiling-middleware-for.html

    Changed to cProfile, instead of hotshot
    """
    def process_view(self, request, callback, args, kwargs):
        self.profiler = cProfile.Profile()
        return self.profiler.runcall(callback, request, *args, **kwargs)

    def process_response(self, request, response):

        if not hasattr(self, "profiler"):
            return response
        self.profiler.create_stats()
        out = StringIO()
        old_stdout, sys.stdout = sys.stdout, out
        self.profiler.print_stats(1)
        sys.stdout = old_stdout

        # If we have got a 3xx status code, further
        # action needs to be taken by the user agent
        # in order to fulfill the request. So don't
        # attach any stats to the content, because of
        # the content is supposed to be empty and is
        # ignored by the user agent.
        if response.status_code // 100 == 3:
            return response

        # Detect the appropriate syntax based on the
        # Content-Type header.
        for regex, begin_comment, end_comment in COMMENT_SYNTAX:
            if regex.match(response['Content-Type'].split(';')[0].strip()):
                break
        else:
            # If the given Content-Type is not
            # supported, don't attach any stats to
            # the content and return the unchanged
            # response.
            return response

        # The response can hold an iterator, that
        # is executed when the content property
        # is accessed. So we also have to profile
        # the call of the content property.
        content = out.getvalue()

        # Construct an HTML/XML or Javascript comment, with
        # the formatted stats, written to the StringIO object
        # and attach it to the content of the response.
        comment = '\n%s\n\n%s\n\n%s\n' % (begin_comment, out.getvalue(),
            end_comment)
        response.content += comment

        # If the Content-Length header is given, add the
        # number of bytes we have added to it. If the
        # Content-Length header is ommited or incorrect,
        # it remains so in order to don't change the
        # behaviour of the web server or user agent.
        if response.has_header('Content-Length'):
            response['Content-Length'] = int(response['Content-Length']) + \
                len(comment)

        return response
