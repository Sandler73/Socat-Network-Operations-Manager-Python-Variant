# Configuration Examples

This directory holds example configuration files for `batch` mode. Each is a
plain port list consumed with `socat-manager batch --file <path>`.

## File format

A batch configuration file is a simple port list:

- One port per line.
- Lines beginning with `#` are comments.
- Blank lines are ignored.
- Inline comments are **not** supported — a port must be alone on its line. A
  line such as `8080  # proxy` is treated as an invalid port and skipped with a
  warning. Put the comment on its own line above the port instead.
- Any line that is not a valid port (1–65535) is skipped with a warning rather
  than aborting the run.
- Ports are deduplicated and sorted before listeners are started, and each port
  becomes an independent session.

## Provided examples

| File | Contents |
|------|----------|
| `ports.conf.example` | A general starting point mixing commented privileged ports and active high ports. |
| `web-services.conf.example` | Common web and application/development server ports. |
| `database-services.conf.example` | Common database service ports (for observing client connection attempts). |
| `high-ports.conf.example` | High and ephemeral-range ports that bind without root. |

## Usage

```bash
# Start listeners for every active port in a file
socat-manager batch --file conf/web-services.conf.example

# Same, on UDP instead of the default tcp4
socat-manager batch --file conf/high-ports.conf.example --proto udp4

# The equivalent inline forms, without a file
socat-manager batch --ports 8080,8081,8443
socat-manager batch --range 10000-10002
```

Ports below 1024 require root or `sudo` to bind. Copy an example to a name of
your choice and edit it; files ending in `.conf` (rather than `.conf.example`)
are ignored by version control so local, deployment-specific lists are not
committed by accident.
