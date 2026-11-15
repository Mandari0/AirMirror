# UxPlay source used by AirMirror

This directory contains the UxPlay source tree that AirMirror bundles in its
Windows installer. UxPlay runs as a **separate process**; AirMirror only starts
and stops it and passes command-line options.

- Upstream: <https://github.com/FDH2/UxPlay>
- Version: 1.74 (`UxPlay-master` source archive)
- License: GNU General Public License v3.0 — see [`LICENSE`](LICENSE)

## Local modification

One file is patched for reliable discovery on Windows machines that have VPN,
Hyper-V or other virtual network adapters:

| File | Change |
|---|---|
| `lib/mdnsd/mdnsd.c` | Prefer a real LAN adapter (wired > Wi-Fi), skip VPN/tunnel/Virtual adapters, and allow overriding the advertised IPv4 address with the `UXPLAY_MDNS_ADDR` environment variable. Also logs the chosen address. |

The exact change is in [`mdnsd-windows.patch`](mdnsd-windows.patch). Apply it to a
pristine UxPlay 1.74 tree with:

```sh
patch -p1 < mdnsd-windows.patch
```

## Building the Windows bundle

AirMirror does not compile UxPlay itself. The release bundle is built in an
MSYS2 UCRT64 environment with the UxPlay dependencies and GStreamer installed,
then collected by `build-portable.sh` in the repository root. See the main
[`README.md`](../../README.md) for build steps.
