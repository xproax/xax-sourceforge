#!/usr/local/bin/php
<?php
/*
	services_samba_share.php
	Copyright � 2006-2007 Volker Theile (votdev@gmx.de)
  All rights reserved.

	part of FreeNAS (http://www.freenas.org)
	Copyright (C) 2005-2007 Olivier Cochard <olivier@freenas.org>.
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

$pgtitle = array(gettext("Services"),gettext("CIFS"),gettext("Shares"));

if(!is_array($config['mounts']['mount']))
	$config['mounts']['mount'] = array();

mount_sort();

$a_mount = &$config['mounts']['mount'];

if($_POST) {
	$pconfig = $_POST;

	if($_POST['apply']) {
		$retval = 0;
		if(!file_exists($d_sysrebootreqd_path)) {
		  config_lock();
			services_samba_configure();
			services_mdnsresponder_configure();
			config_unlock();
		}

		$savemsg = get_std_save_message($retval);

		if(0 == $retval) {
			if(file_exists($d_smbshareconfdirty_path))
				unlink($d_smbshareconfdirty_path);
		}
	}
}
if($_GET['act'] == "ret") {
  header("Location: services_samba_share.php");
  exit;
}
?>
<?php include("fbegin.inc");?>
<table width="100%" border="0" cellpadding="0" cellspacing="0">
  <tr>
    <td class="tabnavtbl">
      <ul id="tabnav">
				<li class="tabinact"><a href="services_samba.php"><?=gettext("Settings");?></a></li>
				<li class="tabact"><a href="services_samba_share.php" style="color:black" title="<?=gettext("Reload page");?>"><?=gettext("Shares");?></a></li>
      </ul>
    </td>
  </tr>
  <tr> 
    <td class="tabcont">
      <form action="services_samba_share.php" method="post">
        <?php if ($savemsg) print_info_box($savemsg); ?>
        <?php if (file_exists($d_smbshareconfdirty_path)): ?><p>
        <?php print_info_box_np(gettext("The shares has been modified.<br>You must apply the changes in order for them to take effect."));?><br>
        <input name="apply" type="submit" class="formbtn" id="apply" value="<?=gettext("Apply changes");?>"></p>
        <?php endif; ?>
        <table width="100%" border="0" cellpadding="0" cellspacing="0">
          <tr>
            <td width="20%" class="listhdrr"><?=gettext("Share Name");?></td>
            <td width="25%" class="listhdrr"><?=gettext("Description");?></td>
            <td width="20%" class="listhdrr"><?=gettext("Browseable");?></td>
            <td width="10%" class="list"></td>
          </tr>
  			  <?php $i = 0; foreach($a_mount as $mountv): ?>
          <tr>
            <td class="listr"><?=htmlspecialchars($mountv['sharename']);?>&nbsp;</td>
            <td class="listr"><?=htmlspecialchars($mountv['desc']);?>&nbsp;</td>
            <td class="listbg"><?=htmlspecialchars((is_array($config['samba']['hidemount']) && in_array($mountv['sharename'],$config['samba']['hidemount']))?gettext("No"):gettext("Yes"));?></td>
            <td valign="middle" nowrap class="list">
              <?php if(isset($config['samba']['enable']))
              echo("<a href='services_samba_share_edit.php?id={$i}'><img src='e.gif' title='" . gettext("Edit share") . "' width='17' height='17' border='0'></a>");
              ?>
            </td>
          </tr>
          <?php $i++; endforeach; ?>
        </table>
      </form>
    </td>
  </tr>
</table>
<?php include("fend.inc"); ?>
