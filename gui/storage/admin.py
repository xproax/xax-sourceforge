from collections import OrderedDict

from django.conf import settings
from django.utils.html import escapejs
from django.utils.translation import ugettext as _

from freenasUI.freeadmin.api.resources import (DiskResource,
    ReplicationResource, ScrubResource, TaskResource, VolumeResource)
from freenasUI.freeadmin.options import BaseFreeAdmin
from freenasUI.freeadmin.site import site
from freenasUI.storage import models


class DiskFAdmin(BaseFreeAdmin):

    exclude_fields = (
        'id',
        'disk_identifier',
        'disk_multipath_name',
        'disk_multipath_member',
        'disk_enabled',
        )
    resource = DiskResource

    def get_actions(self):
        actions = super(DiskFAdmin, self).get_actions()
        del actions['Delete']
        actions['Wipe'] = {
            'button_name': _('Wipe'),
            'on_click': """function() {
                var mybtn = this;
                for (var i in grid.selection) {
                    var data = grid.row(i).data;
                    editObject('Wipe', data._wipe_url, [mybtn,]);
                }
            }""",
        }

        return actions


class VolumeFAdmin(BaseFreeAdmin):

    resource = VolumeResource
    exclude_fields = (
        'id',
        'vol_name',
        'vol_fstype',
        'vol_guid',
        'vol_encrypt',
        'vol_encryptkey',
        )

    def get_datagrid_context(self):
        has_multipath = models.Disk.objects.exclude(
            disk_multipath_name='').exists()
        return {
            'has_multipath': has_multipath,
            }

    def get_datagrid_columns(self):

        columns = []

        columns.append({
            'name': 'name',
            'label': _('Name'),
            'tree': True,
            'sortable': False,
            'shouldExpand': True,
        })

        columns.append({
            'name': 'used',
            'label': _('Used'),
            'sortable': False,
        })

        columns.append({
            'name': 'avail_si',
            'label': _('Available'),
            'sortable': False,
        })

        columns.append({
            'name': 'total_si',
            'label': _('Size'),
            'sortable': False,
        })

        columns.append({
            'name': 'status',
            'label': _('Status'),
            'sortable': False,
        })
        return columns

    def _action_builder(self, name, label=None, url=None, func="editObject",
        icon=None, show=None, fstype="ZFS", decrypted=True, has_enc=False,
        enc_level=None):

        if url is None:
            url = "_%s_url" % (name, )

        if icon is None:
            icon = name

        if show == "ALL":
            hide_cond = "false"
        elif show == "+DATASET":
            hide_cond = "row.data.type != 'dataset' && row.data.type !== undefined"
        elif show == "DATASET":
            hide_cond = "row.data.type != 'dataset'"
        elif show == "ZVOL":
            hide_cond = "row.data.type != 'zvol'"
        else:
            hide_cond = "row.data.type !== undefined"

        if fstype == "ZFS":
            hide_fs = "row.data.vol_fstype !== undefined && row.data.vol_fstype != 'ZFS'"
        else:
            hide_fs = "false"

        if decrypted is True:
            hide_enc = "row.data.vol_fstype !== undefined && row.data.is_decrypted == false"
        else:
            hide_enc = "row.data.vol_encrypt == 0 && row.data.is_decrypted == true"

        if has_enc is True:
            if enc_level is not None:
                hide_hasenc = "row.data.vol_encrypt != %d" % (enc_level, )
            else:
                hide_hasenc = "row.data.vol_encrypt == 0"
        else:
            hide_hasenc = "false"

        on_select_after = """function(evt, actionName, action) {
                for(var i=0;i < evt.rows.length;i++) {
                    var row = evt.rows[i];
                    if((%(hide)s) || (%(hide_fs)s) || (%(hide_enc)s) || (%(hide_hasenc)s)) {
                        query(".grid" + actionName).forEach(function(item, idx) {
                            domStyle.set(item, "display", "none");
                        });
                        break;
                    }
                }
            }""" % {
            'hide': hide_cond,
            'hide_fs': hide_fs,
            'hide_enc': hide_enc,
            'hide_hasenc': hide_hasenc,
            }

        on_click = """function() {
                var mybtn = this;
                for (var i in grid.selection) {
                    var data = grid.row(i).data;
                    %(func)s('%(label)s', data.%(url)s, [mybtn,]);
                }
            }""" % {
                'func': func,
                'label': escapejs(label),
                'url': url,
                }

        data = {
            'button_name': '<img src="%simages/ui/buttons/%s.png" width="18px" height="18px">' % (
                settings.STATIC_URL,
                icon,
                ),
            'tooltip': label,
            'on_select_after': on_select_after,
            'on_click': on_click,
        }

        return data

    def get_actions(self):

        actions = OrderedDict()
        actions['Detach'] = self._action_builder("detach",
            label=_('Detach Volume'),
            func="editScaryObject",
            icon="remove_volume")
        actions['Scrub'] = self._action_builder("scrub", label=_('Scrub Volume'))
        actions['Options'] = self._action_builder("options",
            label=_('Edit ZFS Options'),
            icon="settings")
        actions['NewDataset'] = self._action_builder("add_dataset",
            label=_('Create ZFS Dataset'),
            )
        actions['NewVolume'] = self._action_builder("add_zfs_volume",
            label=_('Create ZFS Volume'),
            )
        actions['ChangePerm'] = self._action_builder("permissions",
            label=_('Change Permissions'),
            show="+DATASET",
            fstype="ALL",
            )
        actions['ManualSnapshot'] = self._action_builder("manual_snapshot",
            label=_('Create Snapshot'),
            icon="create_snapshot",
            show="ALL",
            )
        actions['VolStatus'] = self._action_builder("status",
            label=_('Volume Status'),
            func="viewModel",
            icon="zpool_status",
            fstype="ALL",
            )

        actions['VolCreatePass'] = self._action_builder("create_passphrase",
            label=_('Create Passphrase'),
            icon="key_change",
            has_enc=True,
            enc_level=1,
            )
        actions['VolChangePass'] = self._action_builder("change_passphrase",
            label=_('Change Passphrase'),
            icon="key_change",
            has_enc=True,
            enc_level=2,
            )
        actions['VolDownloadKey'] = self._action_builder("download_key",
            label=_('Download Key'),
            icon="key_download",
            has_enc=True,
            )
        actions['VolReKey'] = self._action_builder("rekey",
            label=_('Encryption Re-key'),
            icon="key_rekey",
            has_enc=True,
            )
        actions['VolAddRecKey'] = self._action_builder("add_reckey",
            label=_('Add recovery key'),
            icon="key_addrecovery",
            has_enc=True,
            )
        actions['VolRemRecKey'] = self._action_builder("rem_reckey",
            label=_('Remove recovery key'),
            icon="key_removerecovery",
            has_enc=True,
            )
        actions['VolUnlock'] = self._action_builder("unlock",
            label=_('Unlock'),
            icon="key_unlock",
            decrypted=False,
            )

        # Dataset actions
        actions['DatasetDelete'] = self._action_builder("dataset_delete",
            label=_('Destroy Dataset'),
            func="editScaryObject",
            icon="remove_dataset",
            show="DATASET",
            )
        actions['DatasetEdit'] = self._action_builder("dataset_edit",
            label=_('Edit ZFS Options'),
            icon="settings",
            show="DATASET",
            )
        actions['DatasetCreate'] = self._action_builder("dataset_create",
            label=_('Create ZFS Dataset'),
            icon="add_dataset",
            show="DATASET",
            )

        # ZVol actions
        actions['ZVolDelete'] = self._action_builder("zvol_delete",
            label=_('Destroy ZFS Volume'),
            func="editScaryObject",
            icon="remove_volume",
            show="ZVOL",
            )

        return actions


class ScrubFAdmin(BaseFreeAdmin):

    icon_model = u"cronJobIcon"
    icon_object = u"cronJobIcon"
    icon_add = u"AddcronJobIcon"
    icon_view = u"ViewcronJobIcon"
    resource = ScrubResource
    exclude_fields = (
        'id',
        )

    def get_datagrid_columns(self):

        columns = []

        columns.append({
            'name': 'scrub_volume',
            'label': _('Volume'),
        })

        columns.append({
            'name': 'scrub_threshold',
            'label': _('Threshold days'),
        })

        columns.append({
            'name': 'scrub_description',
            'label': _('Description'),
        })

        columns.append({
            'name': 'human_minute',
            'label': _('Minute'),
            'sortable': False,
        })

        columns.append({
            'name': 'human_hour',
            'label': _('Hour'),
            'sortable': False,
        })

        columns.append({
            'name': 'human_daymonth',
            'label': _('Day of month'),
            'sortable': False,
        })

        columns.append({
            'name': 'human_month',
            'label': _('Month'),
            'sortable': False,
        })

        columns.append({
            'name': 'human_dayweek',
            'label': _('Day of week'),
            'sortable': False,
        })

        columns.append({
            'name': 'scrub_enabled',
            'label': _('Enabled'),
            'sortable': False,
        })
        return columns


class TaskFAdmin(BaseFreeAdmin):

    icon_model = u"SnapIcon"
    icon_add = u"CreatePeriodicSnapIcon"
    icon_view = u"ViewAllPeriodicSnapIcon"
    icon_object = u"SnapIcon"
    extra_js = u"taskrepeat_checkings();"
    composed_fields = (
        ('Lifetime', ('task_ret_count', 'task_ret_unit')),
        )
    resource = TaskResource
    exclude_fields = (
        'id',
        'task_ret_count',
        'task_ret_unit',
        'task_begin',
        'task_end',
        'task_interval',
        'task_repeat_unit',
        'task_byweekday',
        )

    def get_datagrid_columns(self):
        columns = super(TaskFAdmin, self).get_datagrid_columns()
        columns.insert(2, {
            'name': 'how',
            'label': _('How'),
            'sortable': False,
        })
        columns.insert(3, {
            'name': 'keepfor',
            'label': _('Keep snapshot for'),
            'sortable': False,
        })
        return columns


class ReplicationFAdmin(BaseFreeAdmin):

    resource = ReplicationResource
    exclude_fields = (
        'id',
        'repl_lastsnapshot',
        'repl_remote',
        'repl_userepl',
        'repl_resetonce',
        )

    def get_datagrid_columns(self):
        columns = super(ReplicationFAdmin, self).get_datagrid_columns()
        columns.insert(2, {
            'name': 'ssh_remote_host',
            'label': _('Remote Hostname'),
            'sortable': False,
        })
        return columns


site.register(models.Disk, DiskFAdmin)
site.register(models.Scrub, ScrubFAdmin)
site.register(models.Task, TaskFAdmin)
site.register(models.Volume, VolumeFAdmin)
site.register(models.Replication, ReplicationFAdmin)
