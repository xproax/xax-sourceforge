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
import logging
import re
import urllib2

from django.conf import settings
from django.core.urlresolvers import resolve
from django.db import models
from django.forms import ModelForm
from django.http import Http404
from django.utils import simplejson
from django.utils.translation import ugettext_lazy as _

from freeadmin.tree import (tree_roots, TreeRoot, TreeNode, TreeRoots,
    unserialize_tree)
from freenasUI.plugins.models import Plugins

log = logging.getLogger('freeadmin.navtree')


class NavTree(object):

    def __init__(self):
        self._modelforms = {}
        self._options = {}
        self._navs = {}
        self._generated = False

    def isGenerated(self):
        return self._generated

    def _get_module(self, where, name):
        try:
            mod = __import__('%s.%s' % (where, name), globals(), locals(),
                [name], -1)
            return mod
        except ImportError, e:
            return None

    """
    This is used for Menu Item replacement

    Every option added to the tree register its name in a dict
    If the name was already registered before it can be replaced or not

    Return Value: Item has been added to the tree or not
    """
    def register_option(self, opt, parent, replace=False, evaluate=True):

        if evaluate:
            current_parent = parent
            gname = [opt.gname]
            while True:
                if current_parent is not None:
                    gname.insert(0, current_parent.gname)
                    current_parent = current_parent.parent
                else:
                    break
            gname = '.'.join(gname)
            opt._gname = gname
        else:
            gname = opt.gname
            opt._gname = gname

        if gname in self._options and opt.gname is not None:
            if replace is True:
                _opt = self._options[gname]
                _opt.parent.remove_child(_opt)

                opt.attrFrom(_opt)
                parent.append_child(opt)
                self._options[gname] = opt
                return True

        else:
            parent.append_child(opt)
            self._options[gname] = opt
            return True

        return False

    def replace_navs(self, nav):

        if nav._gname is not None and nav._gname in self._navs and \
                hasattr(self._navs[nav._gname], 'append_app') and \
                self._navs[nav._gname].append_app is False:
            if nav._gname in self._options:
                old = self._options[nav._gname]
                self.register_option(self._navs[nav._gname], old.parent, True,
                    evaluate=False)

        for subnav in nav:
            self.replace_navs(subnav)

    def register_option_byname(self, opt, name, replace=False):
        if name in self._options:
            nav = self._options[name]
            return self.register_option(opt, nav, replace)
        return False

    def titlecase(self, s):
        return re.sub(r"[A-Za-z]+('[A-Za-z]+)?",
                      lambda mo: mo.group(0)[0].upper() +
                                 mo.group(0)[1:],
                    s)

    def sort_navoption(self, nav):

        if nav.order_child:

            new = {}
            order = {}
            opts = []
            for opt in nav:
                if opt.order:
                    order[opt.order] = opt
                else:
                    new[opt.name] = opt

            sort = new.keys()
            sort = sorted(sort, cmp=lambda x, y: cmp(x.lower(),
                y.lower()) if x and y else 0)

            for opt in sort:
                opts.append(new[opt])
            nav._children = opts

            # TODO better order based on number attribute
            sort = order.keys()
            sort.sort()
            for key in sort:
                nav.insert_child(0, order[key])

        for opt in nav:
            self.sort_navoption(opt)

    def prepare_modelforms(self):
        """
        This piece of code lookup all ModelForm classes from forms.py
        and record models as a dict key
        """
        self._modelforms.clear()
        for app in settings.INSTALLED_APPS:

            _models = {}
            modforms = self._get_module(app, 'forms')

            if modforms:
                modname = "%s.forms" % app
                for c in dir(modforms):
                    form = getattr(modforms, c)
                    try:
                        subclass = issubclass(form, ModelForm)
                    except TypeError:
                        continue

                    if form.__module__ == modname and subclass:
                        if form._meta.model in _models:
                            if isinstance(_models[form._meta.model], dict):
                                _models[form._meta.model][form.__name__] = form
                            else:
                                tmp = _models[form._meta.model]
                                _models[form._meta.model] = {
                                        tmp.__name__: tmp,
                                        form.__name__: form,
                                }
                        else:
                            _models[form._meta.model] = form
            self._modelforms.update(_models)

    """
    Tree Menu Auto Generate

    Every app listed at INSTALLED_APPS is scanned
    1st - app_name.forms is imported. All its objects/classes are scanned
        looking for ModelForm classes
    2nd - app_name.nav is imported. TreeNode classes are scanned for hard-coded
        menu entries or overwriting
    3rd - app_name.models is imported. models.Model classes are scanned,
        if a related ModelForm is found several entries are Added to the Menu
            - Objects
            - Add (Model)
            - View (Model)
    """
    def generate(self, request=None):

        self._generated = True
        self._options.clear()
        tree_roots.clear()
        for app in settings.INSTALLED_APPS:

            # If the app is listed at settings.BLACKLIST_NAV, skip it!
            if app in getattr(settings, 'BLACKLIST_NAV', []):
                continue

            # Thats the root node for the app tree menu
            nav = TreeRoot(app)
            tree_roots.register(nav)  # We register it to the tree root

            modnav = self._get_module(app, 'nav')
            if hasattr(modnav, 'BLACKLIST'):
                BLACKLIST = modnav.BLACKLIST
            else:
                BLACKLIST = []

            if hasattr(modnav, 'ICON'):
                nav.icon = modnav.ICON

            if hasattr(modnav, 'NAME'):
                nav.name = modnav.NAME
            else:
                nav.name = self.titlecase(app)

            self._navs.clear()
            if modnav:
                modname = "%s.nav" % app
                for c in dir(modnav):
                    navc = getattr(modnav, c)
                    try:
                        subclass = issubclass(navc, TreeNode)
                    except TypeError:
                        continue
                    if navc.__module__ == modname and subclass:
                        obj = navc()
                        obj._gname = obj.gname

                        if obj.append_app:
                            self.register_option(obj, nav, True, evaluate=True)
                        else:
                            self._navs[obj.gname] = obj

            modmodels = self._get_module(app, 'models')
            if modmodels:

                modname = '%s.models' % app
                for c in dir(modmodels):
                    if c in BLACKLIST:
                        continue
                    model = getattr(modmodels, c)
                    try:
                        subclass = issubclass(model, models.Model)
                    except TypeError:
                        continue

                    if not(model.__module__ == modname and subclass \
                            and model in self._modelforms
                          ):
                        continue

                    if model._admin.deletable is False:
                        navopt = TreeNode(str(model._meta.object_name),
                            name=model._meta.verbose_name,
                            model=c, app_name=app, type='dialog')
                        try:
                            navopt.kwargs = {'app': app, 'model': c, 'oid': \
                                model.objects.order_by("-id")[0].id}
                            navopt.view = 'freeadmin_model_edit'
                        except:
                            navopt.view = 'freeadmin_model_add'
                            navopt.kwargs = {'app': app, 'model': c}

                    else:
                        navopt = TreeNode(str(model._meta.object_name))
                        navopt.name = model._meta.verbose_name_plural
                        navopt.model = c
                        navopt.app_name = app
                        navopt.order_child = False

                    for key in model._admin.nav_extra.keys():
                        navopt.__setattr__(key,
                            model._admin.nav_extra.get(key))
                    if model._admin.icon_model is not None:
                        navopt.icon = model._admin.icon_model

                    if model._admin.menu_child_of is not None:
                        reg = self.register_option_byname(navopt,
                                "%s.%s" % (app, model._admin.menu_child_of))
                    else:
                        reg = self.register_option(navopt, nav)

                    if reg and not navopt.type:

                        qs = model.objects.filter(
                            **model._admin.object_filters).order_by('-id')
                        if qs.count() > 0:
                            if model._admin.object_num > 0:
                                qs = qs[:model._admin.object_num]
                            for e in qs:
                                subopt = TreeNode('Edit')
                                subopt.type = 'editobject'
                                subopt.view = u'freeadmin_model_edit'
                                if model._admin.icon_object is not None:
                                    subopt.icon = model._admin.icon_object
                                subopt.model = c
                                subopt.app_name = app
                                subopt.kwargs = {
                                    'app': app,
                                    'model': c,
                                    'oid': e.id,
                                    }
                                try:
                                    subopt.name = unicode(e)
                                except:
                                    subopt.name = 'Object'
                                navopt.append_child(subopt)

                        # Node to add an instance of model
                        subopt = TreeNode('Add')
                        subopt.name = _(u'Add %s') % model._meta.verbose_name
                        subopt.view = u'freeadmin_model_add'
                        subopt.kwargs = {'app': app, 'model': c}
                        subopt.type = 'dialog'
                        if model._admin.icon_add is not None:
                            subopt.icon = model._admin.icon_add
                        subopt.model = c
                        subopt.app_name = app
                        self.register_option(subopt, navopt)

                        # Node to view all instances of model
                        subopt = TreeNode('View')
                        subopt.name = _(u'View %s') % (
                            model._meta.verbose_name_plural,
                            )
                        subopt.view = u'freeadmin_model_datagrid'
                        if model._admin.icon_view is not None:
                            subopt.icon = model._admin.icon_view
                        subopt.model = c
                        subopt.app_name = app
                        subopt.kwargs = {'app': app, 'model': c}
                        subopt.type = 'viewmodel'
                        self.register_option(subopt, navopt)

                        for child in model._admin.menu_children:
                            if child in self._navs:
                                self.register_option(self._navs[child], navopt)

            self.replace_navs(nav)
            self.sort_navoption(nav)

        nav = TreeRoot('display',
            name=_('Display System Processes'),
            action='displayprocs',
            icon='TopIcon')
        tree_roots.register(nav)

        nav = TreeRoot('shell', name=_('Shell'), icon='TopIcon',
            action='shell')
        tree_roots.register(nav)

        nav = TreeRoot('reboot', name=_('Reboot'), action='reboot',
            icon='RebootIcon', type='scary_dialog', view='system_reboot_dialog')
        tree_roots.register(nav)

        nav = TreeRoot('shutdown', name=_('Shutdown'), icon='ShutdownIcon',
            type='scary_dialog', view='system_shutdown_dialog')
        tree_roots.register(nav)

        """
        Plugin nodes
        """
        host = "%s://%s" % ('https' if request.is_secure() else 'http',
            request.get_host(), )
        for plugin in Plugins.objects.filter(plugin_enabled=True):

            try:
                url = "%s/%s/treemenu" % (host, plugin.plugin_view)
                response = urllib2.urlopen(url, None, 1)
                data = response.read()
                if not data:
                    log.warn(_("Empty data returned from %s") % (url,))
                    continue
            except Exception, e:
                log.warn(_("Couldn't retrieve %(url)s: %(error)s") % {
                    'url': url,
                    'error': e,
                    })
                continue

            try:
                data = simplejson.loads(data)

                nodes = unserialize_tree(data)
                for node in nodes:
                    #We have our TreeNode's, find out where to place them

                    found = False
                    if node.append_to:
                        log.debug("Plugin %s requested to be appended to %s",
                            plugin.plugin_name, node.append_to)
                        places = node.append_to.split('.')
                        places.reverse()
                        for root in tree_roots:
                            find = root.find_place(list(places))
                            if find:
                                find.append_child(node)
                                found = True
                                break
                    else:
                        log.debug("Plugin %s didn't request to be appended anywhere specific",
                            plugin.plugin_name)

                    if not found:
                        node.tree_root = 'main'
                        tree_roots.register(node)

            except Exception, e:
                log.warn(_("An error occurred while unserializing from "
                    "%(url)s: %(error)s") % {'url': url, 'error': e})
                continue

    def _build_nav(self):
        navs = []
        for nav in tree_roots['main']:
            nav.option_list = self.build_options(nav)
            nav.get_absolute_url()
            navs.append(nav)
        return navs

    def build_options(self, nav):
        options = []
        for option in nav:
            try:
                option = option()
            except:
                pass
            option.get_absolute_url()
            option.option_list = self.build_options(option)
            options.append(option)
        return options

    def dehydrate(self, o, level, uid, gname=None):

        # info about current node
        my = {
            'id': str(uid.new()),
        }
        my['name'] = unicode(getattr(o, "rename", o.name))
        if o._gname:
            my['gname'] = o._gname
        else:
            my['gname'] = getattr(o, "gname", my['name'])
            if gname:
                my['gname'] = "%s.%s" % (gname, my['gname'])
        if not o.option_list:
            my['type'] = getattr(o, 'type', None)
            my['url'] = o.get_absolute_url()
            if o.append_url:
                my['url'] += o.append_url
        for attr in ('model', 'app_name', 'icon', 'action'):
            if getattr(o, attr):
                my[attr] = getattr(o, attr)

        # this node has no childs
        if not o.option_list:
            return my
        else:
            my['children'] = []

        for i in o.option_list:
            opt = self.dehydrate(i, level + 1, uid, gname=my['gname'])
            my['children'].append(opt)

        return my

    def dijitTree(self):

        class ByRef(object):
            def __init__(self, val):
                self.val = val

            def new(self):
                old = self.val
                self.val += 1
                return old
        items = []
        uid = ByRef(1)
        for n in self._build_nav():
            items.append(self.dehydrate(n, level=0, uid=uid))
        return items

navtree = NavTree()
