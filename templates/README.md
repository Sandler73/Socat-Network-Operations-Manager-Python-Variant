# Deployment Templates

Reusable templates for running socat-manager as a managed service. Each is a
starting point: copy it, replace the values marked `CHANGE-ME`, and install it
where your platform expects. None of these files is read by socat-manager
itself.

## Contents

| Path | Purpose |
|------|---------|
| `systemd/socat-manager@.service` | Templated systemd unit for a per-port listener. |
| `logrotate/socat-manager` | logrotate configuration for the runtime `logs/` directory. |
| `socat-profiles/profiles.conf` | Copy-paste `--socat-opts` option strings. |

## systemd

`socat-manager@.service` is a template unit; the instance name is the port:

```bash
sudo cp systemd/socat-manager@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now socat-manager@8080
```

Because socat-manager launches the socat process into its own process group and
returns, the unit is `Type=oneshot` with `RemainAfterExit=yes`: the service
stays active for as long as the listener should exist, and `ExecStop` runs the
protocol-scoped stop. The built-in `--watchdog` (per-crash restart of an
individual socat process) runs only while a socat-manager process is resident,
so it is not used by the oneshot unit; if you need it, run socat-manager in the
foreground under a `Type=simple` unit of your own. Set `User`, `Group`, the
executable path, and `SOCAT_MANAGER_BASE` for your deployment before enabling.

## logrotate

`logrotate/socat-manager` rotates the master, session, error, and capture logs.
Point the path at your runtime `logs/` directory (`SOCAT_MANAGER_BASE/logs`):

```bash
sudo cp logrotate/socat-manager /etc/logrotate.d/socat-manager
sudo logrotate --debug /etc/logrotate.d/socat-manager
```

The glob `*.log` matches every log the tool writes: `socat-manager-<timestamp>.log`,
`session-<sid>.log`, `session-<sid>-error.log`, and `capture-*.log`. The config
uses `copytruncate` because a fresh master log is opened per invocation and
long-lived writers may hold an open handle.

## socat profiles

`socat-profiles/profiles.conf` lists named socat address-option strings ready to
pass to `--socat-opts` on the `listen` and `batch` modes. The file is a
reference, not a config the tool loads — copy a value into your command:

```bash
socat-manager listen --port 8080 --socat-opts "reuseaddr"
socat-manager listen --port 8080 --socat-opts "range=10.0.0.0/8"
```

Every value uses only the characters the option validator permits and passes
validation as written. Consult `man socat` and `man socat-address` for the full
option set and exact semantics.
