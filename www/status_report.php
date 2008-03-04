#!/usr/local/bin/php
<?php
/*
	status_report.php
	Copyright � 2007-2008 Volker Theile (votdev@gmx.de)
	Copyright � 2007 Dan Merschi (freenas@bcapro.com)
	All rights reserved.

	part of FreeNAS (http://www.freenas.org)
	Copyright (C) 2005-2008 Olivier Cochard <olivier@freenas.org>.
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
require("report.inc");

$pgtitle = array(gettext("Status"), gettext("Email report"));

if(!is_array($config['statusreport']))
	$config['statusreport'] = array();

$pconfig['enable'] = isset($config['statusreport']['enable']);
$pconfig['server'] = $config['statusreport']['server'];
$pconfig['port'] = $config['statusreport']['port'];
$pconfig['auth'] = isset($config['statusreport']['auth']);
$pconfig['security'] = $config['statusreport']['security'];
$pconfig['username'] = $config['statusreport']['username'];
$pconfig['password'] = base64_decode($config['statusreport']['password']);
$pconfig['passwordconf'] = $pconfig['password'];
$pconfig['from'] = $config['statusreport']['from'];
$pconfig['to'] = $config['statusreport']['to'];
$pconfig['subject'] = $config['statusreport']['subject'];
$pconfig['report'] = $config['statusreport']['report'];
$pconfig['minute'] = $config['statusreport']['minute'];
$pconfig['hour'] = $config['statusreport']['hour'];
$pconfig['day'] = $config['statusreport']['day'];
$pconfig['month'] = $config['statusreport']['month'];
$pconfig['weekday'] = $config['statusreport']['weekday'];
$pconfig['all_mins'] = $config['statusreport']['all_mins'];
$pconfig['all_hours'] = $config['statusreport']['all_hours'];
$pconfig['all_days'] = $config['statusreport']['all_days'];
$pconfig['all_months'] = $config['statusreport']['all_months'];
$pconfig['all_weekdays'] = $config['statusreport']['all_weekdays'];

$a_months = explode(" ",gettext("January February March April May June July August September October November December"));
$a_weekdays = explode(" ",gettext("Sunday Monday Tuesday Wednesday Thursday Friday Saturday"));

if($_POST) {
	unset($input_errors);

	$pconfig = $_POST;

	/* Input validation. */
	if($_POST['enable']) {
		$reqdfields = explode(" ", "server port from to security");
		$reqdfieldsn = array(gettext("Server address"), gettext("Server port"), gettext("From e-mail"), gettext("To e-mail"), gettext("Security"));
		$reqdfieldst = explode(" ", "string numeric string string string");

		if ($_POST['auth']) {
			$reqdfields = array_merge($reqdfields,array("username", "password"));
			$reqdfieldsn = array_merge($reqdfieldsn,array(gettext("Username"), gettext("Password")));
			$reqdfieldst = array_merge($reqdfieldst,array("string","string"));
		}

		do_input_validation($_POST, $reqdfields, $reqdfieldsn, &$input_errors);
		do_input_validation_type($_POST, $reqdfields, $reqdfieldsn, $reqdfieldst, &$input_errors);

		// Validate synchronization time
		do_input_validate_synctime($_POST, &$input_errors);
	}

	/* Check for a password mismatch. */
	if ($_POST['auth'] && ($_POST['password'] !== $_POST['passwordconf'])) {
		$input_errors[] = gettext("The passwords do not match.");
	}

	if(!$input_errors) {
		$config['statusreport']['enable'] = $_POST['enable'] ? true : false;
		$config['statusreport']['server'] = $_POST['server'];
		$config['statusreport']['port'] = $_POST['port'];
		$config['statusreport']['auth'] = $_POST['auth'] ? true : false;
		$config['statusreport']['security'] = $_POST['security'];
		$config['statusreport']['username'] = $_POST['username'];
		$config['statusreport']['password'] = base64_encode($_POST['password']);
		$config['statusreport']['from'] = $_POST['from'];
		$config['statusreport']['to'] = $_POST['to'];
		$config['statusreport']['subject'] = $_POST['subject'];
		$config['statusreport']['report'] = $_POST['report'];
		$config['statusreport']['minute'] = $_POST['minute'];
		$config['statusreport']['hour'] = $_POST['hour'];
		$config['statusreport']['day'] = $_POST['day'];
		$config['statusreport']['month'] = $_POST['month'];
		$config['statusreport']['weekday'] = $_POST['weekday'];
		$config['statusreport']['all_mins'] = $_POST['all_mins'];
		$config['statusreport']['all_hours'] = $_POST['all_hours'];
		$config['statusreport']['all_days'] = $_POST['all_days'];
		$config['statusreport']['all_months'] = $_POST['all_months'];
		$config['statusreport']['all_weekdays'] = $_POST['all_weekdays'];

		write_config();

		if (stristr($_POST['Submit'], gettext("Send now"))) {
			// Send an email status report now.
			$retval = @report_send_mail();
			if (0 == $retval)
				$savemsg = gettext("Status report successfully sent.");
			else
				$failmsg = gettext("Failed to send status report. Please check log files.");
		} else {
			// Configure cron job.
			if (!file_exists($d_sysrebootreqd_path)) {
				config_lock();
				$retval = rc_update_service("cron");
				config_unlock();
			}

			$savemsg = get_std_save_message($retval);
		}
	}
}
?>
<?php include("fbegin.inc");?>
<script language="JavaScript">
<!--
function set_selected(name) {
	document.getElementsByName(name)[1].checked = true;
}

function enable_change(enable_change) {
	var endis = !(document.iform.enable.checked || enable_change);
	document.iform.server.disabled = endis;
	document.iform.port.disabled = endis;
	document.iform.auth.disabled = endis;
	document.iform.security.disabled = endis;
	document.iform.username.disabled = endis;
	document.iform.password.disabled = endis;
	document.iform.passwordconf.disabled = endis;
	document.iform.from.disabled = endis;
	document.iform.to.disabled = endis;
	document.iform.subject.disabled = endis;
	document.iform.report_systeminfo.disabled = endis;
	document.iform.report_dmesg.disabled = endis;
	document.iform.report_systemlog.disabled = endis;
	document.iform.report_ftplog.disabled = endis;
	document.iform.report_rsynclog.disabled = endis;
	document.iform.report_sshdlog.disabled = endis;
	document.iform.report_smartdlog.disabled = endis;
	document.iform.report_daemonlog.disabled = endis;
	document.iform.minutes1.disabled = endis;
	document.iform.minutes2.disabled = endis;
	document.iform.minutes3.disabled = endis;
	document.iform.minutes4.disabled = endis;
	document.iform.minutes5.disabled = endis;
	document.iform.hours1.disabled = endis;
	document.iform.hours2.disabled = endis;
	document.iform.days1.disabled = endis;
	document.iform.days2.disabled = endis;
	document.iform.days3.disabled = endis;
	document.iform.months.disabled = endis;
	document.iform.weekdays.disabled = endis;
	document.iform.all_mins1.disabled = endis;
	document.iform.all_mins2.disabled = endis;
	document.iform.all_hours1.disabled = endis;
	document.iform.all_hours2.disabled = endis;
	document.iform.all_days1.disabled = endis;
	document.iform.all_days2.disabled = endis;
	document.iform.all_months1.disabled = endis;
	document.iform.all_months2.disabled = endis;
	document.iform.all_weekdays1.disabled = endis;
	document.iform.all_weekdays2.disabled = endis;
	document.iform.sendnow.disabled = endis;
}

function auth_change() {
	switch(document.iform.auth.checked) {
		case false:
      showElementById('username_tr','hide');
  		showElementById('password_tr','hide');
      break;

    case true:
      showElementById('username_tr','show');
  		showElementById('password_tr','show');
      break;
	}
}
//-->
</script>
<form action="status_report.php" method="post" name="iform" id="iform">
	<table width="100%" border="0" cellpadding="0" cellspacing="0">
	  <tr>
	    <td class="tabcont">
    		<?php if ($input_errors) print_input_errors($input_errors);?>
				<?php if ($savemsg) print_info_box($savemsg);?>
				<?php if ($failmsg) print_error_box($failmsg);?>
			  <table width="100%" border="0" cellpadding="6" cellspacing="0">
			    <tr>
			      <td colspan="2" valign="top" class="optsect_t">
			  		  <table border="0" cellspacing="0" cellpadding="0" width="100%">
			  		  <tr>
			          <td class="optsect_s"><strong><?=gettext("Email report");?></strong></td>
			  			  <td align="right" class="optsect_s"><input name="enable" type="checkbox" value="yes" <?php if ($pconfig['enable']) echo "checked"; ?> onClick="enable_change(false)"> <strong><?=gettext("Enable");?></strong></td>
			        </tr>
			  		  </table>
			      </td>
			    </tr>
			    <tr>
				    <td width="22%" valign="top" class="vncellreq"><?=gettext("Outgoing mail server");?></td>
			      <td width="78%" class="vtable">
			        <input name="server" type="text" class="formfld" id="server" size="40" value="<?=htmlspecialchars($pconfig['server']);?>"><br>
			        <?=gettext("Outgoing SMTP mail server address, e.g. smtp.mycorp.com.");?>
			      </td>
					</tr>
					<tr>
			      <td width="22%" valign="top" class="vncellreq"><?=gettext("Port");?></td>
			      <td width="78%" class="vtable">
			        <input name="port" type="text" class="formfld" id="port" size="10" value="<?=htmlspecialchars($pconfig['port']);?>"><br>
			        <?=gettext("The default SMTP mail server port, e.g. 25 or 587.");?>
			      </td>
			    </tr>
					<tr>
						<td width="22%" valign="top" class="vncellreq"><?=gettext("Security");?></td>
						<td width="78%" class="vtable">
							<select name="security" class="formfld" id="security">
								<?php $types = explode(" ", "None SSL TLS"); $vals = explode(" ", "none ssl tls");?>
								<?php $j = 0; for ($j = 0; $j < count($vals); $j++):?>
								<option value="<?=$vals[$j];?>" <?php if ($vals[$j] == $pconfig['security']) echo "selected";?>><?=htmlspecialchars($types[$j]);?></option>
								<?php endfor;?>
							</select>
						</td>
					</tr>
					<tr>
			      <td width="22%" valign="top" class="vncell"><?=gettext("Authentication");?></td>
			      <td width="78%" class="vtable">
			        <input name="auth" type="checkbox" id="auth" value="yes" <?php if ($pconfig['auth']) echo "checked"; ?> onClick="auth_change()">
			        <span class="vexpl"><?=gettext("Use SMTP authentication.");?></span>
						</td>
			    </tr>
					<tr id="username_tr">
			      <td width="22%" valign="top" class="vncellreq"><?=gettext("Username");?></td>
			      <td width="78%" class="vtable">
			        <input name="username" type="text" class="formfld" id="username" size="40" value="<?=htmlspecialchars($pconfig['username']);?>">
			      </td>
			    </tr>
			    <tr id="password_tr">
			      <td width="22%" valign="top" class="vncellreq"><?=gettext("Password");?></td>
			      <td width="78%" class="vtable">
			        <input name="password" type="password" class="formfld" id="password" size="20" value="<?=htmlspecialchars($pconfig['password']);?>"><br>
			        <input name="passwordconf" type="password" class="formfld" id="passwordconf" size="20" value="<?=htmlspecialchars($pconfig['passwordconf']);?>">&nbsp;(<?=gettext("Confirmation");?>)<br>
			      </td>
					</tr>
					<tr>
						<td width="22%" valign="top" class="vncellreq"><?=gettext("From email");?></td>
						<td width="78%" class="vtable">
							<input name="from" type="text" class="formfld" id="from" size="40" value="<?=htmlspecialchars($pconfig['from']);?>"><br>
							<?=gettext("Your own email address.");?>
						</td>
					</tr>
					<tr>
						<td width="22%" valign="top" class="vncellreq"><?=gettext("To email");?></td>
						<td width="78%" class="vtable">
							<input name="to" type="text" class="formfld" id="to" size="40" value="<?=htmlspecialchars($pconfig['to']);?>"><br>
							<?=gettext("Destination email address.");?>
						</td>
					</tr>
					<tr>
				    <td width="22%" valign="top" class="vncell"><?=gettext("Subject");?></td>
			      <td width="78%" class="vtable">
			        <input name="subject" type="text" class="formfld" id="subject" size="60" value="<?=htmlspecialchars($pconfig['subject']);?>"><br>
			        <?=gettext("The subject of the email.");?>
			      </td>
					</tr>
					<tr>
				    <td width="22%" valign="top" class="vncell"><?=gettext("Reports");?></td>
			      <td width="78%" class="vtable">
			      	<table>
			      		<tr>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_systeminfo" value="systeminfo" <?php if (is_array($pconfig['report']) && in_array("systeminfo", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("System info");?></td>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_dmesg" value="dmesg" <?php if (is_array($pconfig['report']) && in_array("dmesg", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("System message buffer");?></td>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_systemlog" value="systemlog" <?php if (is_array($pconfig['report']) && in_array("systemlog", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("System log");?></td>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_ftplog" value="ftplog" <?php if (is_array($pconfig['report']) && in_array("ftplog", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("FTP log");?></td>
								</tr>
								<tr>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_rsynclog" value="rsynclog" <?php if (is_array($pconfig['report']) && in_array("rsynclog", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("RSYNC log");?></td>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_sshdlog" value="sshdlog" <?php if (is_array($pconfig['report']) && in_array("sshdlog", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("SSHD log");?></td>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_smartdlog" value="smartdlog" <?php if (is_array($pconfig['report']) && in_array("smartdlog", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("S.M.A.R.T. log");?></td>
									<td><input name="report[]" type="checkbox" class="formfld" id="report_daemonlog" value="daemonlog" <?php if (is_array($pconfig['report']) && in_array("daemonlog", $pconfig['report'])):?>checked<?php endif;?>><?=gettext("Daemon log");?></td>
								</tr>
			        </table>
			      </td>
					</tr>
					<tr>
						<td width="22%" valign="top" class="vncellreq"><?=gettext("Polling time");?></td>
						<td width="78%" class="vtable">
							<table width=100% border cellpadding="6" cellspacing="0">
								<tr>
									<td class="optsect_t"><b class="optsect_s"><?=gettext("minutes");?></b></td>
									<td class="optsect_t"><b class="optsect_s"><?=gettext("hours");?></b></td>
									<td class="optsect_t"><b class="optsect_s"><?=gettext("days");?></b></td>
									<td class="optsect_t"><b class="optsect_s"><?=gettext("months");?></b></td>
									<td class="optsect_t"><b class="optsect_s"><?=gettext("week days");?></b></td>
								</tr>
								<tr bgcolor=#cccccc>
									<td valign=top>
										<input type="radio" name="all_mins" id="all_mins1" value="1" <?php if (1 == $pconfig['all_mins']) echo "checked";?>>
										<?=gettext("All");?><br>
										<input type="radio" name="all_mins" id="all_mins2" value="0" <?php if (1 != $pconfig['all_mins']) echo "checked";?>>
										<?=gettext("Selected");?> ..<br>
										<table>
											<tr>
												<td valign=top>
													<select multiple size="12" name="minute[]" id="minutes1" onchange="set_selected('all_mins')">
														<?php for ($i = 0; $i <= 11; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['minute']) && in_array("$i", $pconfig['minute'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
												<td valign=top>
													<select multiple size="12" name="minute[]" id="minutes2" onchange="set_selected('all_mins')">
														<?php for ($i = 12; $i <= 23; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['minute']) && in_array("$i", $pconfig['minute'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
												<td valign=top>
													<select multiple size="12" name="minute[]" id="minutes3" onchange="set_selected('all_mins')">
														<?php for ($i = 24; $i <= 35; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['minute']) && in_array("$i", $pconfig['minute'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
												<td valign=top>
													<select multiple size="12" name="minute[]" id="minutes4" onchange="set_selected('all_mins')">
														<?php for ($i = 36; $i <= 47; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['minute']) && in_array("$i", $pconfig['minute'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
												<td valign=top>
													<select multiple size="12" name="minute[]" id="minutes5" onchange="set_selected('all_mins')">
														<?php for ($i = 48; $i <= 59; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['minute']) && in_array("$i", $pconfig['minute'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
											</tr>
										</table>
										<br>
									</td>
									<td valign=top>
										<input type="radio" name="all_hours" id="all_hours1" value="1" <?php if (1 == $pconfig['all_hours']) echo "checked";?>>
										<?=gettext("All");?><br>
										<input type="radio" name="all_hours" id="all_hours2" value="0" <?php if (1 != $pconfig['all_hours']) echo "checked";?>>
										<?=gettext("Selected");?> ..<br>
										<table>
											<tr>
												<td valign=top>
													<select multiple size="12" name="hour[]" id="hours1" onchange="set_selected('all_hours')">
														<?php for ($i = 0; $i <= 11; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['hour']) && in_array("$i", $pconfig['hour'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
												<td valign=top>
													<select multiple size="12" name="hour[]" id="hours2" onchange="set_selected('all_hours')">
														<?php for ($i = 12; $i <= 23; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['hour']) && in_array("$i", $pconfig['hour'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
											</tr>
										</table>
									</td>
									<td valign=top>
										<input type="radio" name="all_days" id="all_days1" value="1" <?php if (1 == $pconfig['all_days']) echo "checked";?>>
										<?=gettext("All");?><br>
										<input type="radio" name="all_days" id="all_days2" value="0" <?php if (1 != $pconfig['all_days']) echo "checked";?>>
										<?=gettext("Selected");?> ..<br>
										<table>
											<tr>
												<td valign=top>
													<select multiple size="12" name="day[]" id="days1" onchange="set_selected('all_days')">
														<?php for ($i = 1; $i <= 12; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['day']) && in_array("$i", $pconfig['day'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
												<td valign=top>
													<select multiple size="12" name="day[]" id="days2" onchange="set_selected('all_days')">
														<?php for ($i = 13; $i <= 24; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['day']) && in_array("$i", $pconfig['day'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
												<td valign=top>
													<select multiple size="7" name="day[]" id="days3" onchange="set_selected('all_days')">
														<?php for ($i = 25; $i <= 31; $i++):?>
														<option value="<?=$i;?>" <?php if (is_array($pconfig['day']) && in_array("$i", $pconfig['day'])) echo "selected";?>><?=htmlspecialchars($i);?></option>
														<?php endfor;?>
													</select>
												</td>
											</tr>
										</table>
									</td>
									<td valign=top>
										<input type="radio" name="all_months" id="all_months1" value="1" <?php if (1 == $pconfig['all_months']) echo "checked";?>>
										<?=gettext("All");?><br>
										<input type="radio" name="all_months" id="all_months2" value="0" <?php if (1 != $pconfig['all_months']) echo "checked";?>>
										<?=gettext("Selected");?> ..<br>
										<table>
											<tr>
												<td valign=top>
													<select multiple size="12" name="month[]" id="months" onchange="set_selected('all_months')">
														<?php $i = 1; foreach ($a_months as $month):?>
														<option value="<?=$i;?>" <?php if (isset($pconfig['month']) && in_array("$i", $pconfig['month'])) echo "selected";?>><?=htmlspecialchars($month);?></option>
														<?php $i++; endforeach;?>
													</select>
												</td>
											</tr>
										</table>
									</td>
									<td valign=top>
										<input type="radio" name="all_weekdays" id="all_weekdays1" value="1" <?php if (1 == $pconfig['all_weekdays']) echo "checked";?>>
										<?=gettext("All");?><br>
										<input type="radio" name="all_weekdays" id="all_weekdays2" value="0" <?php if (1 != $pconfig['all_weekdays']) echo "checked";?>>
										<?=gettext("Selected");?> ..<br>
										<table>
											<tr>
												<td valign=top>
													<select multiple size="7" name="weekday[]" id="weekdays" onchange="set_selected('all_weekdays')">
														<?php $i = 0; foreach ($a_weekdays as $day):?>
														<option value="<?=$i;?>" <?php if (isset($pconfig['weekday']) && in_array("$i", $pconfig['weekday'])) echo "selected";?>><?=$day;?></option>
														<?php $i++; endforeach;?>
													</select>
												</td>
											</tr>
										</table>
									</td>
								</tr>
								<tr bgcolor=#cccccc>
									<td colspan=5>
										<?=gettext("Note: Ctrl-click (or command-click on the Mac) to select and de-select minutes, hours, days and months.");?>
									</td>
								</tr>
							</table>
						</td>
					</tr>
					<tr>
						<td width="22%" valign="top">&nbsp;</td>
						<td width="78%">
							<input name="Submit" type="submit" class="formbtn" value="<?=gettext("Save and Restart");?>" onClick="enable_change(true)">
							&nbsp;
							<input name="Submit" id="sendnow" type="submit" class="formbtn" value="<?=gettext("Send now");?>">
						</td>
					</tr>
				</table>
			</td>
		</tr>
	</table>
</form>
<script language="JavaScript">
<!--
auth_change();
enable_change(false);
//-->
</script>
<?php include("fend.inc");?>
