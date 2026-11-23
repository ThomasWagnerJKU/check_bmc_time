# check_bmc_time

A Nagios/Icinga plugin that checks whether the clock of a BMC (IPMI baseboard management
controller: Supermicro IPMI, Dell iDRAC, HPE iLO, ...) is right. Python 3 with the standard
library only, plus FreeIPMI.

The BMC's system event log (SEL) is where you look after a crash, a power loss or a hardware
fault. Its timestamps come from the BMC's own clock, which often drifts or was never set,
because BMCs don't always use NTP and reset their clock after a complete power loss. A SEL entry
"2026-09-14 07:48 AC power on" is useless if the event actually happened on 2026-11-23 03:36.
This plugin makes such a clock visible before you need the log.

## How it works

The plugin reads the SEL time out of band with FreeIPMI (`bmc-device --get-sel-time`) and
compares it with the clock of the monitoring server, which should be NTP synchronised.

BMCs keep their clock either in UTC or in local time, and IPMI has no way to say which. The
plugin computes the offset both ways and uses the smaller one; the output says which matched
(`(UTC)` or `(local time)`). The SEL time has a resolution of one second, so offsets below
2 s count as "in sync".

## Usage

```sh
check_bmc_time -H bmc.example.com -U monitor -f /etc/nagios/bmc.secret
check_bmc_time -H bmc.example.com -U monitor -f /etc/nagios/bmc.secret -w 60 -c 300 --extra '-W authcap'
```

```
BMC TIME OK - BMC clock 2026-11-23 18:23:49 (UTC) in sync | offset=-1s;-60:60;-300:300;;
BMC TIME OK - BMC clock 2026-11-23 19:23:57 (local time) in sync | offset=0s;-60:60;-300:300;;
BMC TIME CRITICAL - BMC clock 2026-09-14 07:48:29 (UTC) 69d 19h 48m behind | offset=-6032880s;-60:60;-300:300;;
```

| Option | Meaning | Default |
|---|---|---|
| `-H`, `--host` | BMC host name or address | (required) |
| `-U`, `--user` | IPMI user | (required) |
| `-f`, `--password-file` | file whose first line is the IPMI password (recommended) | |
| `-P`, `--password` | IPMI password on the command line | |
| `-L`, `--privilege` | IPMI privilege level | `user` |
| `-w`, `--warning` | offset in seconds (either direction) for WARNING | `60` |
| `-c`, `--critical` | offset in seconds (either direction) for CRITICAL | `300` |
| `--extra` | further FreeIPMI options, see below | |
| `--bmc-device` | path of `bmc-device` | searched in `PATH` and the sbin directories |
| `-t`, `--timeout` | seconds | `40` |
| `-V`, `--version` | show the version | |

The perfdata `offset` is the BMC clock minus the server clock: negative means the BMC is
behind. Its thresholds are ranges (`-60:60`), because the offset may be negative.

### Credentials

A user with privilege level *user* is enough. Prefer `-f`: an option like `-P` can be read by
every local user in the process list while the plugin runs. The plugin itself never passes the
credentials to `bmc-device` on the command line; it writes them into a temporary FreeIPMI
configuration file (mode 0600) that is removed afterwards. Only a user name or password that
contains blanks, `#` or `\` (which `freeipmi.conf` cannot hold) falls back to `-u`/`-p`.

### Vendor workarounds

Some BMCs need FreeIPMI workarounds, passed with `--extra`:

| BMC | `--extra` |
|---|---|
| some Supermicro BMCs (X10/X11): "password invalid" although it is right | `'-W authcap'` |
| Dell iDRAC 7/8 | `'-D LAN_2_0'` |

`bmc-device --help` lists all workarounds.

## Installation

Requirements: Python ≥ 3.7 and FreeIPMI (`freeipmi-tools` on Debian/Ubuntu, `freeipmi` on
openSUSE/Fedora).

```sh
install -m 0755 check_bmc_time /usr/lib/nagios/plugins/
install -m 0644 completions/check_bmc_time /usr/share/bash-completion/completions/
```

Naemon/Nagios example:

```
define command {
  command_name   check_bmc_time
  command_line   $USER1$/check_bmc_time -H $HOSTADDRESS$ -U $ARG1$ -f $ARG2$ $ARG3$
}
define service {
  service_description   BMC Clock
  host_name             bmc-server1
  use                   generic-service
  check_command         check_bmc_time!monitor!/etc/naemon/bmc.secret!-w 60 -c 300
  check_interval        60
}
```

## Tests

```sh
python3 -m unittest discover -s tests
```

The tests use a fake `bmc-device`, no BMC is needed.

## License

GPL-2.0-or-later, see [LICENSE](LICENSE).
