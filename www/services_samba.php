#!/usr/local/bin/php
<?php
/*
	services_samba.php
	part of FreeNAS (http://www.freenas.org)
	Copyright (C) 2005-2008 Olivier Cochard-Labbe <olivier@freenas.org>.
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

$pgtitle = array(gettext("Services"),gettext("CIFS/SMB"),gettext("Settings"));

if (!is_array($config['samba'])) {
	$config['samba'] = array();
}

if(!is_array($config['samba']['auxparam']))
	$config['samba']['auxparam'] = array();

sort($config['samba']['auxparam']);

if (!is_array($config['mounts']['mount']))
	$config['mounts']['mount'] = array();

array_sort_key($config['mounts']['mount'], "devicespecialfile");

$a_mount = &$config['mounts']['mount'];

$pconfig['netbiosname'] = $config['samba']['netbiosname'];
$pconfig['workgroup'] = $config['samba']['workgroup'];
$pconfig['serverdesc'] = $config['samba']['serverdesc'];
$pconfig['security'] = $config['samba']['security'];
$pconfig['localmaster'] = $config['samba']['localmaster'];
$pconfig['winssrv'] = $config['samba']['winssrv'];
$pconfig['timesrv'] = $config['samba']['timesrv'];
$pconfig['unixcharset'] = $config['samba']['unixcharset'];
$pconfig['doscharset'] = $config['samba']['doscharset'];
$pconfig['loglevel'] = $config['samba']['loglevel'];
$pconfig['sndbuf'] = $config['samba']['sndbuf'];
$pconfig['rcvbuf'] = $config['samba']['rcvbuf'];
$pconfig['enable'] = isset($config['samba']['enable']);
$pconfig['largereadwrite'] = isset($config['samba']['largereadwrite']);
$pconfig['easupport'] = isset($config['samba']['easupport']);
$pconfig['storedosattributes'] = isset($config['samba']['storedosattributes']);
$pconfig['createmask'] = $config['samba']['createmask'];
$pconfig['directorymask'] = $config['samba']['directorymask'];
$pconfig['guestaccount'] = $config['samba']['guestaccount'];
$pconfig['nullpasswords'] = isset($config['samba']['nullpasswords']);
if (is_array($config['samba']['auxparam']))
	$pconfig['auxparam'] = implode("\n", $config['samba']['auxparam']);

if ($_POST) {
	unset($input_errors);
	$pconfig = $_POST;

	if ($_POST['enable']) {
		$reqdfields = explode(" ", "security netbiosname workgroup");
		$reqdfieldsn = array(gettext("Authentication"),gettext("NetBIOS name"),gettext("Workgroup"));
		$reqdfieldst = explode(" ", "string domain workgroup");

		do_input_validation($_POST, $reqdfields, $reqdfieldsn, &$input_errors);
		do_input_validation_type($_POST, $reqdfields, $reqdfieldsn, $reqdfieldst, &$input_errors);
	
		// Do additional input type validation.
		$reqdfields = explode(" ", "sndbuf rcvbuf createmask directorymask");
		$reqdfieldsn = array(gettext("Send Buffer Size"),gettext("Receive Buffer Size"),gettext("Create mask"),gettext("Directory mask"));
		$reqdfieldst = explode(" ", "numericint numericint filemode filemode");

		if (!empty($_POST['winssrv'])) {
			$reqdfields = explode(" ", "winssrv");
			$reqdfieldsn = array(gettext("WINS server"));
			$reqdfieldst = explode(" ", "ipaddr");
		}

		do_input_validation_type($_POST, $reqdfields, $reqdfieldsn, $reqdfieldst, &$input_errors);
	}

	if (!$input_errors) {
		$config['samba']['enable'] = $_POST['enable'] ? true : false;
		$config['samba']['netbiosname'] = $_POST['netbiosname'];
		$config['samba']['workgroup'] = $_POST['workgroup'];
		$config['samba']['serverdesc'] = $_POST['serverdesc'];
		$config['samba']['security'] = $_POST['security'];
		$config['samba']['localmaster'] = $_POST['localmaster'];
		$config['samba']['winssrv'] = $_POST['winssrv'];
		$config['samba']['timesrv'] = $_POST['timesrv'];
		$config['samba']['doscharset'] = $_POST['doscharset'];
		$config['samba']['unixcharset'] = $_POST['unixcharset'];
		$config['samba']['loglevel'] = $_POST['loglevel'];
		$config['samba']['sndbuf'] = $_POST['sndbuf'];
		$config['samba']['rcvbuf'] = $_POST['rcvbuf'];
		$config['samba']['largereadwrite'] = $_POST['largereadwrite'] ? true : false;
		$config['samba']['easupport'] = $_POST['easupport'] ? true : false;
		$config['samba']['storedosattributes'] = $_POST['storedosattributes'] ? true : false;
		if (!empty($_POST['createmask']))
			$config['samba']['createmask'] = $_POST['createmask'];
		else
			unset($config['samba']['createmask']);
		if (!empty($_POST['directorymask']))
			$config['samba']['directorymask'] = $_POST['directorymask'];
		else
			unset($config['samba']['directorymask']);
		if (!empty($_POST['guestaccount']))
			$config['samba']['guestaccount'] = $_POST['guestaccount'];
		else
			unset($config['samba']['guestaccount']);
		$config['samba']['nullpasswords'] = $_POST['nullpasswords'] ? true : false;

		# Write additional parameters.
		unset($config['samba']['auxparam']);
		foreach (explode("\n", $_POST['auxparam']) as $auxparam) {
			$auxparam = trim($auxparam, "\t\n\r");
			if (!empty($auxparam))
				$config['samba']['auxparam'][] = $auxparam;
		}

		write_config();

		$retval = 0;
		if (!file_exists($d_sysrebootreqd_path)) {
			config_lock();
			$retval |= rc_update_service("samba");
			$retval |= rc_update_service("mdnsresponder");
			config_unlock();
		}

		$savemsg = get_std_save_message($retval);

		if(0 == $retval) {
			if(file_exists($d_smbconfdirty_path))
				unlink($d_smbconfdirty_path);
			if(file_exists($d_smbshareconfdirty_path))
				unlink($d_smbshareconfdirty_path);
		}
	}
}

if($_GET['act'] === "del") {
	/* Remove entry from auxparam list */
	unset($config['samba']['auxparam'][$_GET['id']]);
	write_config();
	touch($d_smbconfdirty_path);
	header("Location: services_samba.php");
	exit;
}
?>
<?php include("fbegin.inc");?>
<script language="JavaScript">
<!--
function enable_change(enable_change) {
	var endis = !(document.iform.enable.checked || enable_change);
	document.iform.netbiosname.disabled = endis;
	document.iform.workgroup.disabled = endis;
	document.iform.localmaster.disabled = endis;
	document.iform.winssrv.disabled = endis;
	document.iform.timesrv.disabled = endis;
	document.iform.serverdesc.disabled = endis;
	document.iform.doscharset.disabled = endis;
	document.iform.unixcharset.disabled = endis;
	document.iform.loglevel.disabled = endis;
	document.iform.sndbuf.disabled = endis;
	document.iform.rcvbuf.disabled = endis;
	document.iform.security.disabled = endis;
	document.iform.largereadwrite.disabled = endis;
	document.iform.easupport.disabled = endis;
	document.iform.storedosattributes.disabled = endis;
	document.iform.createmask.disabled = endis;
	document.iform.directorymask.disabled = endis;
	document.iform.guestaccount.disabled = endis;
	document.iform.nullpasswords.disabled = endis;
	document.iform.auxparam.disabled = endis;
}

function authentication_change() {
	switch(document.iform.security.value) {
		case "share":
			showElementById('createmask_tr','show');
			showElementById('directorymask_tr','show');
			showElementById('winssrv_tr','hide');
			break;
		case "domain":
			showElementById('createmask_tr','hide');
			showElementById('directorymask_tr','hide');
			showElementById('winssrv_tr','show');
			break;
		default:
			showElementById('createmask_tr','hide');
			showElementById('directorymask_tr','hide');
			showElementById('winssrv_tr','hide');
			break;
	}
}
//-->
</script>
<table width="100%" border="0" cellpadding="0" cellspacing="0">
  <tr>
    <td class="tabnavtbl">
      <ul id="tabnav">
        <li class="tabact"><a href="services_samba.php" title="<?=gettext("Reload page");?>"><span><?=gettext("Settings");?></span></a></li>
				<li class="tabinact"><a href="services_samba_share.php"><span><?=gettext("Shares");?></span></a></li>
      </ul>
    </td>
  </tr>
  <tr>
    <td class="tabcont">
      <form action="services_samba.php" method="post" name="iform" id="iform">
				<?php if ($input_errors) print_input_errors($input_errors);?>
				<?php if ($savemsg) print_info_box($savemsg);?>
				<?php if (file_exists($d_smbconfdirty_path) || file_exists($d_smbshareconfdirty_path)) print_config_change_box();?>
				<table width="100%" border="0" cellpadding="6" cellspacing="0">
          <tr>
            <td colspan="2" valign="top" class="optsect_t">
    				  <table border="0" cellspacing="0" cellpadding="0" width="100%">
    				    <tr>
                  <td class="optsect_s"><strong>Common Internet File System</strong></td>
    				      <td align="right" class="optsect_s"><input name="enable" type="checkbox" value="yes" <?php if ($pconfig['enable']) echo "checked"; ?> onClick="enable_change(false)"> <strong><?=gettext("Enable") ;?></strong></td>
                </tr>
    				  </table>
            </td>
          </tr>
          <tr>
            <td width="22%" valign="top" class="vncellreq"><?=gettext("Authentication"); ?></td>
            <td width="78%" class="vtable">
              <select name="security" class="formfld" id="security" onchange="authentication_change()">
              <?php $types = explode(",", "Anonymous,Local User,Domain"); $vals = explode(" ", "share user domain");?>
              <?php $j = 0; for ($j = 0; $j < count($vals); $j++): ?>
                <option value="<?=$vals[$j];?>" <?php if ($vals[$j] == $pconfig['security']) echo "selected";?>>
                <?=htmlspecialchars($types[$j]);?>
                </option>
              <?php endfor; ?>
              </select>
            </td>
          </tr>
          <tr>
            <td width="22%" valign="top" class="vncellreq"><?=gettext("NetBIOS name");?></td>
            <td width="78%" class="vtable">
              <input name="netbiosname" type="text" class="formfld" id="netbiosname" size="30" value="<?=htmlspecialchars($pconfig['netbiosname']);?>">
            </td>
          </tr>
          <tr>
            <td width="22%" valign="top" class="vncellreq"><?=gettext("Workgroup") ; ?></td>
            <td width="78%" class="vtable">
              <input name="workgroup" type="text" class="formfld" id="workgroup" size="30" value="<?=htmlspecialchars($pconfig['workgroup']);?>">
              <br/><?=gettext("Workgroup the server will appear to be in when queried by clients (maximum 15 characters).");?>
            </td>
          </tr>
          <tr>
          <tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Description") ;?></td>
            <td width="78%" class="vtable">
              <input name="serverdesc" type="text" class="formfld" id="serverdesc" size="30" value="<?=htmlspecialchars($pconfig['serverdesc']);?>">
              <br><?=gettext("Server description. This can usually be left blank.") ;?>
            </td>
          </tr>
          <tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Dos charset") ; ?></td>
            <td width="78%" class="vtable">
              <select name="doscharset" class="formfld" id="doscharset">
              <?php $types = explode(",", "CP850,CP852,CP437,CP932,CP866,ASCII"); $vals = explode(" ", "CP850 CP852 CP437 CP932 CP866 ASCII");?>
              <?php $j = 0; for ($j = 0; $j < count($vals); $j++): ?>
                <option value="<?=$vals[$j];?>" <?php if ($vals[$j] == $pconfig['doscharset']) echo "selected";?>>
                <?=htmlspecialchars($types[$j]);?>
                </option>
              <?php endfor; ?>
              </select>
            </td>
          </tr>
	        <tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Unix charset") ; ?></td>
            <td width="78%" class="vtable">
              <select name="unixcharset" class="formfld" id="unixcharset">
              <?php $types = explode(",", "UTF-8,iso-8859-1,iso-8859-15,gb2312,EUC-JP,ASCII"); $vals = explode(" ", "UTF-8 iso-8859-1 iso-8859-15 gb2312 EUC-JP ASCII");?>
              <?php $j = 0; for ($j = 0; $j < count($vals); $j++): ?>
                <option value="<?=$vals[$j];?>" <?php if ($vals[$j] == $pconfig['unixcharset']) echo "selected";?>>
                <?=htmlspecialchars($types[$j]);?>
                </option>
              <?php endfor; ?>
              </select>
            </td>
          </tr>
          <tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Log Level") ; ?></td>
            <td width="78%" class="vtable">
              <select name="loglevel" class="formfld" id="loglevel">
              <?php $types = explode(",", "Minimum,Normal,Full,Debug"); $vals = explode(" ", "1 2 3 10");?>
              <?php $j = 0; for ($j = 0; $j < count($vals); $j++): ?>
                <option value="<?=$vals[$j];?>" <?php if ($vals[$j] == $pconfig['loglevel']) echo "selected";?>>
                <?=htmlspecialchars($types[$j]);?>
                </option>
              <?php endfor; ?>
              </select>
            </td>
          </tr>
          <tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Local Master Browser"); ?></td>
            <td width="78%" class="vtable">
              <select name="localmaster" class="formfld" id="localmaster">
              <?php $types = array(gettext("Yes"),gettext("No")); $vals = explode(" ", "yes no");?>
              <?php $j = 0; for ($j = 0; $j < count($vals); $j++): ?>
                <option value="<?=$vals[$j];?>" <?php if ($vals[$j] == $pconfig['localmaster']) echo "selected";?>>
                <?=htmlspecialchars($types[$j]);?>
                </option>
              <?php endfor; ?>
              </select>
              <br><?php echo sprintf(gettext("Allows %s to try and become a local master browser."), get_product_name());?>
            </td>
          </tr>
          <tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Time server"); ?></td>
            <td width="78%" class="vtable">
              <select name="timesrv" class="formfld" id="timesrv">
              <?php $types = array(gettext("Yes"),gettext("No")); $vals = explode(" ", "yes no");?>
              <?php $j = 0; for ($j = 0; $j < count($vals); $j++): ?>
                <option value="<?=$vals[$j];?>" <?php if ($vals[$j] == $pconfig['timesrv']) echo "selected";?>>
                <?=htmlspecialchars($types[$j]);?>
                </option>
              <?php endfor; ?>
              </select>
              <br><?php echo sprintf(gettext("%s advertises itself as a time server to Windows clients."), get_product_name());?>
            </td>
          </tr>
          <tr id="winssrv_tr">
            <td width="22%" valign="top" class="vncell"><?=gettext("WINS server"); ?></td>
            <td width="78%" class="vtable">
              <input name="winssrv" type="text" class="formfld" id="winssrv" size="30" value="<?=htmlspecialchars($pconfig['winssrv']);?>">
              <br/><?=gettext("WINS server IP address (e.g. from MS Active Directory server).");?>
            </td>
  				</tr>
          <tr>
			      <td colspan="2" class="list" height="12"></td>
			    </tr>
			    <tr>
			      <td colspan="2" valign="top" class="listtopic"><?=gettext("Advanced settings");?></td>
			    </tr>
					<tr>
						<td width="22%" valign="top" class="vncell"><?=gettext("Guest account");?></td>
						<td width="78%" class="vtable">
							<input name="guestaccount" type="text" class="formfld" id="guestaccount" size="30" value="<?=htmlspecialchars($pconfig['guestaccount']);?>">
							<br/><?=gettext("Use this option to override the username ('ftp' by default) which will be used for access to services which are specified as guest. Whatever privileges this user has will be available to any client connecting to the guest service. This user must exist in the password file, but does not require a valid login.");?>
						</td>
					</tr>
					<tr id="createmask_tr">
						<td width="22%" valign="top" class="vncell"><?=gettext("Create mask"); ?></td>
						<td width="78%" class="vtable">
							<input name="createmask" type="text" class="formfld" id="createmask" size="30" value="<?=htmlspecialchars($pconfig['createmask']);?>">
							<br><?=gettext("Use this option to override the file creation mask (0666 by default).");?>
						</td>
					</tr>
					<tr id="directorymask_tr">
						<td width="22%" valign="top" class="vncell"><?=gettext("Directory mask"); ?></td>
						<td width="78%" class="vtable">
							<input name="directorymask" type="text" class="formfld" id="directorymask" size="30" value="<?=htmlspecialchars($pconfig['directorymask']);?>">
							<br><?=gettext("Use this option to override the directory creation mask (0777 by default).");?>
						</td>
					</tr>
	        <tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Send Buffer Size"); ?></td>
            <td width="78%" class="vtable">
              <input name="sndbuf" type="text" class="formfld" id="sndbuf" size="30" value="<?=htmlspecialchars($pconfig['sndbuf']);?>">
              <br><?=gettext("Size of send buffer (16384 by default)."); ?>
            </td>
  				</tr>
  				<tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Receive Buffer Size") ; ?></td>
            <td width="78%" class="vtable">
              <input name="rcvbuf" type="text" class="formfld" id="rcvbuf" size="30" value="<?=htmlspecialchars($pconfig['rcvbuf']);?>">
              <br><?=gettext("Size of receive buffer (16384 by default).") ; ?>
            </td>
  				</tr>
  				<tr>
            <td width="22%" valign="top" class="vncell"><?=gettext("Large read/write");?></td>
            <td width="78%" class="vtable">
              <input name="largereadwrite" type="checkbox" id="largereadwrite" value="yes" <?php if ($pconfig['largereadwrite']) echo "checked"; ?>>
              <?=gettext("Enable large read/write");?><span class="vexpl"><br>
              <?=gettext("Use the new 64k streaming read and write varient SMB requests introduced with Windows 2000.");?></span>
            </td>
          </tr>
					<tr>
						<td width="22%" valign="top" class="vncell"><?=gettext("EA support");?></td>
						<td width="78%" class="vtable">
							<input name="easupport" type="checkbox" id="easupport" value="yes" <?php if ($pconfig['easupport']) echo "checked"; ?>>
							<?=gettext("Enable extended attribute support");?><span class="vexpl"><br>
							<?=gettext("Allow clients to attempt to store OS/2 style extended attributes on a share.");?></span>
						</td>
					</tr>
					<tr>
						<td width="22%" valign="top" class="vncell"><?=gettext("Store DOS attributes");?></td>
						<td width="78%" class="vtable">
							<input name="storedosattributes" type="checkbox" id="storedosattributes" value="yes" <?php if ($pconfig['storedosattributes']) echo "checked"; ?>>
							<?=gettext("Enable store DOS attributes");?><span class="vexpl"><br>
							<span class="vexpl"><?=gettext("If this parameter is set, Samba attempts to first read DOS attributes (SYSTEM, HIDDEN, ARCHIVE or READ-ONLY) from a filesystem extended attribute, before mapping DOS attributes to UNIX permission bits. When set, DOS attributes will be stored onto an extended attribute in the UNIX filesystem, associated with the file or directory.");?></span>
						</td>
					</tr>
					<tr>
						<td width="22%" valign="top" class="vncell"><?=gettext("Null passwords");?></td>
						<td width="78%" class="vtable">
							<input name="nullpasswords" type="checkbox" id="nullpasswords" value="yes" <?php if ($pconfig['nullpasswords']) echo "checked"; ?>>
							<?=gettext("Allow client access to accounts that have null passwords.");?>
						</td>
					</tr>
					<?php html_textarea("auxparam", gettext("Auxiliary parameters"), $pconfig['auxparam'], gettext("This parameters will be added to [global] in smb.conf."), false, 65, 5);?>
  				<tr>
            <td width="22%" valign="top">&nbsp;</td>
            <td width="78%">
              <input name="Submit" type="submit" class="formbtn" value="<?=gettext("Save and Restart");?>" onClick="enable_change(true)">
            </td>
          </tr>
					<tr>
						<td width="22%" valign="top">&nbsp;</td>
						<td width="78%"><span class="red"><strong><?=gettext("Note");?>:</strong></span><br><?php echo sprintf( gettext("To increase CIFS performance try the following:<br>- Enable 'Large read/write' switch<br>- Enable '<a href='%s'>Tuning</a>' switch<br>- Increase <a href='%s'>MTU</a>"), "system_advanced.php", "interfaces_lan.php");?></td>
					</tr>
        </table>
      </form>
    </td>
  </tr>
</table>
<script language="JavaScript">
<!--
enable_change(false);
authentication_change();
//-->
</script>
<?php include("fend.inc");?>
