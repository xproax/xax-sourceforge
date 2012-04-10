from subprocess import Popen, PIPE
import os
import platform

transmission_pbi_path = "/usr/pbi/transmission-" + platform.machine()
transmission_etc_path = os.path.join(transmission_pbi_path, "etc")
transmission_mnt_path = os.path.join(transmission_pbi_path, "mnt")
transmission_fcgi_pidfile = "/var/run/transmission_fcgi_server.pid"
transmission_fcgi_wwwdir = os.path.join(transmission_pbi_path, "www")
transmission_control = "/usr/local/etc/rc.d/transmission"

transmission_advanced_vars = {
    'allow': {
        "type": "textbox",
        "opt": "-a",
        },
    "blocklist": {
        "type": "checkbox",
        "on": "-b",
        "off": "-B",
        },
    "logfile": {
        "type": "textbox",
        "opt": "-e",
        },
    "rpc_port": {
        "type": "textbox",
        "opt": "-p",
        },
    "rpc_auth": {
        "type": "checkbox",
        "on": "-t",
        "off": "-T",
        },
    "rpc_username": {
        "type": "textbox",
        "opt": "-u",
        },
    "dht": {
        "type": "checkbox",
        "on": "-o",
        "off": "-O",
        },
    "lpd": {
        "type": "checkbox",
        "on": "-y",
        "off": "-Y",
        },
    "utp": {
        "type": "checkbox",
        "on": "--utp",
        "off": "--no-utp",
        },
    "peer_port": {
        "type": "textbox",
        "opt": "-P",
        },
    "portmap": {
        "type": "checkbox",
        "on": "-m",
        "off": "-M",
        },
    "peerlimit_global": {
        "type": "textbox",
        "opt": "-L",
        },
    "peerlimit_torrent": {
        "type": "textbox",
        "opt": "-l",
        },
    "global_seedratio": {
        "type": "textbox",
        "opt": "-gsr",
        }
}
