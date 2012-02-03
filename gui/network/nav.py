from freeadmin.tree import TreeNode
from freenasUI.choices import LAGGType
from django.utils.translation import ugettext_lazy as _
import models

NAME = _('Network')
ICON = u'NetworkIcon'
BLACKLIST = ['LAGGInterfaceMembers','Alias']

class NetSummary(TreeNode):

    gname = 'NetworkSummary'
    name = _(u'Network Summary')
    type = 'opennetwork'
    icon = u'SettingsIcon'
    app_name = 'network'

class GlobalConf(TreeNode):

    gname = u'network.GlobalConfiguration'
    name = _(u'Global Configuration')
    type = 'opennetwork'
    model = 'GlobalConfiguration'
    icon = u'SettingsIcon'
    app_name = 'network'
    append_app = False

class Linkss(TreeNode):

    gname = 'LAGGInterfaceMembers'
    model = 'LAGGInterface'
    app_name = 'network'
    name = _(u'Link Aggregations')
    icon = u'LAGGIcon'

    def __init__(self, *args, **kwargs):

        super(Linkss, self).__init__(*args, **kwargs)

        laggadd = TreeNode('Add')
        laggadd.name = _(u'Create Link Aggregation')
        laggadd.view = 'network_lagg_add'
        laggadd.type = 'object'
        laggadd.icon = u'AddLAGGIcon'
        laggadd.model = 'LAGGInterface'
        laggadd.app_name = 'network'

        laggview = TreeNode('View')
        laggview.gname = 'View'
        laggview.name = _(u'View Link Aggregations')
        laggview.type = 'opennetwork'
        laggview.icon = u'ViewAllLAGGsIcon'
        laggview.model = 'LAGGInterface'
        laggview.app_name = 'network'
        self.append_children([laggadd, laggview])

        for value, name in LAGGType:

            laggs = models.LAGGInterface.objects.filter(lagg_protocol__exact=value)
            if laggs.count() > 0:
                nav = TreeNode()
                nav.name = name
                nav.icon = u'LAGGIcon'
                nav._children = []
                self.append_child(nav)

            for lagg in laggs:

                subnav = TreeNode()
                subnav.name = lagg.lagg_interface.int_name
                subnav.icon = u'LAGGIcon'
                subnav._children = []
                nav.append_child(subnav)

                laggm = models.LAGGInterfaceMembers.objects.filter(\
                        lagg_interfacegroup__exact=lagg.id).order_by('lagg_ordernum')
                for member in laggm:
                    subsubnav = TreeNode()
                    subsubnav.name = member.lagg_physnic
                    subsubnav.type = 'editobject'
                    subsubnav.icon = u'LAGGIcon'
                    subsubnav.view = 'freeadmin_model_edit'
                    subsubnav.app_name = 'network'
                    subsubnav.model = 'LAGGInterfaceMembers'+lagg.lagg_interface.int_name
                    subsubnav.kwargs = {'app': 'network', 'model': 'LAGGInterfaceMembers', \
                            'oid': member.id}
                    subsubnav.append_url = '?deletable=false'
                    subsubnav._children = []
                    subnav.append_child(subsubnav)

class ViewInterfaces(TreeNode):

    gname = 'network.Interfaces.View'
    type = 'opennetwork'
    append_app = False

class ViewVLAN(TreeNode):

    gname = 'network.VLAN.View'
    type = 'opennetwork'
    append_app = False

class ViewSR(TreeNode):

    gname = 'network.StaticRoute.View'
    type = 'opennetwork'
    append_app = False
