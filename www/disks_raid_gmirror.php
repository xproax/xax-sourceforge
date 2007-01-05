#!/usr/local/bin/php
<?php
/*
	disks_raid_gmirror.php
	part of FreeNAS (http://www.freenas.org)
	Copyright (C) 2005-2006 Olivier Cochard-Labb� <olivier@freenas.org>.
	All rights reserved.
	
	Based on m0n0wall (http://m0n0.ch/wall)
	Copyright (C) 2003-2006 Manuel Kasper <mk@neon1.net>.
	All rights reserved.
	
	Redistribution and use in source and binary forms, with or without
	modification, are permitted provided that the following conditions are met:
	
	1. Redistributions of source code must retain the above copyright notice,
	   this list of conditions and the following disclaimer.
	
	2. Redistributions in binary form must reproduce the above copyright
	   notice, this list of conditions and the following disclaimer in the
	   documentation and/or other materials provided with the distribution.
	
	THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
	INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
	AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
	AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
	OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
	SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
	INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
	CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
	ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
	POSSIBILITY OF SUCH DAMAGE.
*/
require("guiconfig.inc");
require("disks_raid.inc");

$pgtitle = array(_DISKSPHP_NAME, _DISKSRAIDPHP_GMIRROR, _DISKSRAIDPHP_NAMEDESC);

if (!is_array($config['gmirror']['vdisk']))
	$config['gmirror']['vdisk'] = array();

gmirror_sort();
$a_raid = &$config['gmirror']['vdisk'];

if ($_POST) {
	$pconfig = $_POST;

	if ($_POST['apply']) {
		$retval = 0;
		if (!file_exists($d_sysrebootreqd_path))
		{
			config_lock();
			/* reload all components that create raid device */
			disks_raid_gmirror_configure();
			config_unlock();
			write_config();
		}
		$savemsg = get_std_save_message($retval);
		if ($retval == 0) {
			if (file_exists($d_raidconfdirty_path))
				unlink($d_raidconfdirty_path);
		}
	}
}

$raidstatus=get_sraid_disks_list();

if ($_GET['act'] == "del") {
	unset($errormsg);
	if ($a_raid[$_GET['id']]) {
		if(0 == disks_raid_check_mount($a_raid[$_GET['id']])) {
			$raidname=$a_raid[$_GET['id']]['name'];
			disks_raid_gmirror_delete($raidname);
			unset($a_raid[$_GET['id']]);
			write_config();
			touch($d_raidconfdirty_path);
			header("Location: disks_raid_gmirror.php");
			exit;
		} else {
			$errormsg = sprintf( _DISKSRAIDPHP_RAIDVOLUMEMOUNTERROR, "disks_mount.php");
		}
	}
}
?>
<?php include("fbegin.inc"); ?>
<table width="100%" border="0" cellpadding="0" cellspacing="0">
  <tr><td class="tabnavtbl">
  <ul id="tabnav">
	<li class="tabact"><?=_DISKSRAIDPHP_GMIRROR; ?></li>
	<li class="tabinact"><a href="disks_raid_gconcat.php"><?=_DISKSRAIDPHP_GCONCAT; ?></a></li> 
	<li class="tabinact"><a href="disks_raid_gstripe.php"><?=_DISKSRAIDPHP_GSTRIPE; ?> </a></li>
	<li class="tabinact"><a href="disks_raid_graid5.php"><?=_DISKSRAIDPHP_GRAID5; ?></a></li> 
	<li class="tabinact"><a href="disks_raid_gvinum.php"><?=_DISKSRAIDPHP_GVINUM; ?><?=_DISKSRAIDPHP_UNSTABLE ;?> </a></li>
  </ul>
  </td></tr>
  <tr><td class="tabnavtbl">
  <ul id="tabnav">
	<li class="tabact"><?=_DISKSRAIDPHP_MANAGE; ?></li>
	<li class="tabinact"><a href="disks_raid_gmirror_tools.php"><?=_DISKSRAIDPHP_TOOLS; ?></a></li>
	<li class="tabinact"><a href="disks_raid_gmirror_info.php"><?=_DISKSRAIDPHP_INFO; ?></a></li>
  </ul>
  </td></tr>
  
  <tr>
    <td class="tabcont">
<form action="disks_raid_gmirror.php" method="post">
<?php if ($errormsg) print_error_box($errormsg); ?>
<?php if ($savemsg) print_info_box($savemsg); ?>
<?php if (file_exists($d_raidconfdirty_path)): ?><p>
<?php print_info_box_np(_DISKSRAIDPHP_MSGCHANGED);?><br>
<input name="apply" type="submit" class="formbtn" id="apply" value="<?=_APPLY; ?>"></p>
<?php endif; ?>
              <table width="100%" border="0" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="25%" class="listhdrr"><?=_DISKSRAIDPHP_VOLUME; ?></td>
                  <td width="25%" class="listhdrr"><?=_TYPE; ?></td>
                  <td width="20%" class="listhdrr"><?=_SIZE; ?></td>
                  <td width="20%" class="listhdrr"><?=_STATUS; ?></td>
                  <td width="10%" class="list"></td>
				</tr>
			  <?php $i = 0; foreach ($a_raid as $raid): ?>
                <tr>
                  <td class="listlr">
                    <?=htmlspecialchars($raid['name']);?>
                  </td>
                  <td class="listr">
                    <?=htmlspecialchars($raid['type']);?>
                  </td>
                  <td class="listbg">
                  <?php
		    $raidconfiguring=file_exists($d_raidconfdirty_path) && in_array($raid['name']."\n",file($d_raidconfdirty_path));
                    if ($raidconfiguring)
						echo _CONFIGURING;
					else
						{
						$tempo=$raid['name'];						
						echo "{$raidstatus[$tempo]['size']}";
						}?>&nbsp;
                  </td>
                 </td>
                   <td class="listbg">
                   <?php
                    if ($raidconfiguring)
						echo _CONFIGURING;
					else
						{
						echo "{$raidstatus[$tempo]['desc']}";
						}
						?>&nbsp;
                  </td>
                  <td valign="middle" nowrap class="list"> <a href="disks_raid_gmirror_edit.php?id=<?=$i;?>"><img src="e.gif" title="<?=_DISKSRAIDPHP_EDITRAID; ?>" width="17" height="17" border="0"></a>
                     &nbsp;<a href="disks_raid_gmirror.php?act=del&id=<?=$i;?>" onclick="return confirm('<?=_DISKSRAIDPHP_DELCONF ;?>')"><img src="x.gif" title="<?=_DISKSRAIDPHP_DELRAID ;?>" width="17" height="17" border="0"></a></td>
				</tr>
			  <?php $i++; endforeach; ?>
                <tr> 
                  <td class="list" colspan="4"></td>
                  <td class="list"> <a href="disks_raid_gmirror_edit.php"><img src="plus.gif" title="<?=_DISKSRAIDPHP_ADDRAID;?>" width="17" height="17" border="0"></a></td>
				</tr>
              </table>
            </form>
<p><span class="vexpl"><span class="red"><strong><?=_NOTE;?>:</strong></span><br><?=_DISKSRAIDPHP_NOTE;?></p>
</td></tr></table>
<?php include("fend.inc"); ?>
