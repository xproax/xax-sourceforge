#!/usr/local/bin/php
<?php
/*
	disks_raid_gmirror_edit.php
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

$id = $_GET['id'];
if (isset($_POST['id']))
	$id = $_POST['id'];

$pgtitle = array(gettext("Disks"), gettext("Software RAID"), gettext("RAID1"),isset($id)?gettext("Edit"):gettext("Add"));

if (!is_array($config['disks']['disk']))
	$config['disks']['disk'] = array();

array_sort_key($config['disks']['disk'], "name");

$a_raid = &$config['disks']['disk'];
$all_raid = get_conf_sraid_disks_list();
$a_disk = get_conf_disks_filtered_ex("fstype", "pool");

if (!sizeof($a_disk)) {
	$nodisk_errors[] = gettext("You must add disks first.");
}

if (isset($id) && $a_raid[$id]) {
	$pconfig['name'] = $a_raid[$id]['name'];
	$pconfig['devicespecialfile'] = $a_raid[$id]['devicespecialfile'];
	$pconfig['class'] = $a_raid[$id]['class'];
	$pconfig['balance'] = $a_raid[$id]['balance'];
	$pconfig['device'] = $a_raid[$id]['device'];
}

if ($_POST) {
	unset($input_errors);
	$pconfig = $_POST;

	/* input validation */
	$reqdfields = explode(" ", "name");
	$reqdfieldsn = array(gettext("Raid name"));

	do_input_validation($_POST, $reqdfields, $reqdfieldsn, &$input_errors);

	if (($_POST['name'] && !is_validaliasname($_POST['name']))) {
		$input_errors[] = gettext("The disk name may only consist of the characters a-z, A-Z, 0-9.");
	}

	// Check for duplicate name.
	foreach ($a_raid as $raid) {
		if ($raid['name'] === $_POST['name']) {
			$input_errors[] = gettext("This disk name already exists.");
			break;
		}
	}

	/* check the number of RAID disk for volume */
	if (count($_POST['device']) != 2)
		$input_errors[] = gettext("There must be 2 disks in a RAID 1.");

	if (!$input_errors) {
		$raid = array();
		$raid['name'] = substr($_POST['name'], 0, 15); // Make sure name is only 15 chars long (GEOM limitation).
		$raid['balance'] = $_POST['balance'];
		$raid['class'] = "gmirror";
		$raid['device'] = $_POST['device'];
		$raid['desc'] = "Software gmirror RAID 1";
		$raid['devicespecialfile'] = "/dev/mirror/{$raid['name']}";

		if (isset($id) && $a_raid[$id])
			$a_raid[$id] = $raid;
		else
			$a_raid[] = $raid;

		write_config();

		if ($_POST['init']) {
			// Mark new added RAID to be configured.
			file_put_contents($d_raid_gmirror_confdirty_path, "{$raid[name]}\n", FILE_APPEND | FILE_TEXT);
		} else {
			// Start already configured disks.
			disks_raid_gmirror_start();
		}

		header("Location: disks_raid_gmirror.php");
		exit;
	}
}
?>
<?php include("fbegin.inc"); ?>
<table width="100%" border="0" cellpadding="0" cellspacing="0">
  <tr>
		<td class="tabnavtbl">
		  <ul id="tabnav">
				<li class="tabinact"><a href="disks_raid_gconcat.php"><?=gettext("JBOD"); ?></a></li>
				<li class="tabinact"><a href="disks_raid_gstripe.php"><?=gettext("RAID 0"); ?> </a></li>
				<li class="tabact"><a href="disks_raid_gmirror.php" title="<?=gettext("Reload page");?>" ><?=gettext("RAID 1");?></a></li>
				<li class="tabinact"><a href="disks_raid_graid5.php"><?=gettext("RAID 5"); ?></a></li>
				<li class="tabinact"><a href="disks_raid_gvinum.php"><?=gettext("Geom Vinum"); ?> <?=gettext("(unstable)") ;?> </a></li>
		  </ul>
	  </td>
	</tr>
  <tr>
		<td class="tabnavtbl">
		  <ul id="tabnav">
				<li class="tabact"><a href="disks_raid_gmirror.php" title="<?=gettext("Reload page");?>" ><?=gettext("Manage RAID");?></a></li>
				<li class="tabinact"><a href="disks_raid_gmirror_tools.php"><?=gettext("Tools"); ?></a></li>
				<li class="tabinact"><a href="disks_raid_gmirror_info.php"><?=gettext("Information"); ?></a></li>
		  </ul>
	  </td>
	</tr>
  <tr>
    <td class="tabcont">
			<form action="disks_raid_gmirror_edit.php" method="post" name="iform" id="iform">
				<?php if ($nodisk_errors) print_input_errors($nodisk_errors); ?>
				<?php if ($input_errors) print_input_errors($input_errors); ?>
			  <table width="100%" border="0" cellpadding="6" cellspacing="0">
			    <tr>
			      <td valign="top" class="vncellreq"><?=gettext("Raid name");?></td>
			      <td width="78%" class="vtable">
			        <input name="name" type="text" class="formfld" id="name" size="15" value="<?=htmlspecialchars($pconfig['name']);?>" <?php if (isset($id)) echo "readonly";?>>
			      </td>
			    </tr>
			    <tr>
			      <td width="22%" valign="top" class="vncellreq"><?=gettext("Type"); ?></td>
			      <td width="78%" class="vtable">
			      RAID 1 (<?=gettext("mirroring"); ?>)
			      </td>
			    </tr>
			    <tr>
			      <td width="22%" valign="top" class="vncellreq"><?=gettext("Balance algorithm"); ?></td>
			      <td width="78%" class="vtable">
			        <select name="balance" class="formfld" <?php if(isset($id)) echo "disabled";?>>
			        <?php $balvals = array("round-robin"=>"Round-robin read","split"=>"Split request", "load"=>"Read from lowest load"); ?>
			        <?php foreach ($balvals as $balval => $balname): ?>
			          <option value="<?=$balval;?>" <?php if($pconfig['balance'] == $balval) echo 'selected';?>><?=htmlspecialchars($balname);?></option>
			        <?php endforeach; ?>
			        </select><br>
			        <?=gettext("Select your read balance algorithm.");?></td>
			    </tr>
			    <tr>
			      <td width="22%" valign="top" class="vncellreq"><?=gettext("Members of this volume");?></td>
			      <td width="78%" class="vtable">
			      <?php if (isset($id)) {
			      	foreach ($pconfig['device'] as $devicek => $devicev) {
			      		foreach ($a_disk as $diskv) {
			      			if ($diskv['devicespecialfile'] === $devicev) {
			      				echo "<input name='device[]' id='{$devicek}' type='checkbox' value='{$diskv[devicespecialfile]}' checked disabled>{$diskv[name]} ({$diskv[size]}, {$diskv[desc]})<br>\n";
			      				break;
									}
			      		}
							}
						} else {
			        $i = 0;
			        foreach ($a_disk as $diskv) {
			        	$display = true;
			        	foreach($all_raid as $raid) {
			            if (in_array($diskv['devicespecialfile'], (array)$raid['device'])) {
			              $display = false;
			              break;
			            }
			          }
			          if (true !== $display)
			          	continue;
			          echo "<input name='device[]' id='$i' type='checkbox' value='$diskv[devicespecialfile]'" . ((is_array($pconfig['device']) && in_array($diskv['devicespecialfile'], $pconfig['device']))?" checked":"") . ">$diskv[name] ($diskv[size], $diskv[desc])<br>\n";
			          $i++;
			        }
			        if (0 == $i) echo "&nbsp;";
			      }?>
						</td>
			    </tr>
			    <?php if (!isset($id)):?>
			    <tr>
						<td width="22%" valign="top" class="vncell"><?=gettext("Initialize");?></td>
			      <td width="78%" class="vtable">
							<input name="init" type="checkbox" id="init" value="yes" <?php if (true === $pconfig['init']) echo "checked"; ?>>
							<?=gettext("Create and initialize RAID.");?><br/>
							<span class="vexpl"><?=gettext("This will erase ALL data on the selected disks! Do not use this option if you want to add an already existing RAID again.");?></span>
			      </td>
			    </tr>
					<tr>
						<td width="22%" valign="top">&nbsp;</td>
						<td width="78%">
							<input name="Submit" type="submit" class="formbtn" value="<?=gettext("Add");?>">
						</td>
					</tr>
					<?php endif;?>
			  </table>
			</form>
		</td>
	</tr>
</table>
<?php include("fend.inc");?>
