# Third-party notices

AirMirror’s own source code is licensed under the MIT License (see `LICENSE`).
The installer and the frozen application also contain or start the components
below. Full license texts are in the `licenses/` directory.

## UxPlay 1.74

- Project: <https://github.com/FDH2/UxPlay>
- License: GNU General Public License v3.0 (`licenses/GPL-3.0.txt`)
- Role: AirPlay server. AirMirror starts `uxplay.exe` as a **separate process**
  and communicates with it only through command-line arguments, files and its
  standard output. AirMirror itself does not link against UxPlay code.
- Source: `third_party/uxplay/` (UxPlay 1.74 with the AirMirror mDNS patch
  described in `third_party/uxplay/README-AIRMIRROR.md`).

UxPlay’s GPLv3 source is included so that recipients of the installer can
rebuild the exact UxPlay binary that is bundled.

## GStreamer 1.28.9 and plugins

- Project: <https://gstreamer.freedesktop.org/>
- License: GNU Lesser General Public License v2.1 or later
  (`licenses/LGPL-2.1.txt`) for the core libraries; individual plugins may use
  other free licenses.
- Role: media pipeline used by UxPlay. The installer bundles the GStreamer
  runtime DLLs and plugins built by MSYS2 UCRT64.
- Source: <https://gstreamer.freedesktop.org/source/> and the MSYS2 package
  sources.

## pystray 0.19.5

- Project: <https://github.com/moses-palmer/pystray>
- License: GNU Lesser General Public License v3.0
  (`licenses/pystray-COPYING.LGPL.txt`; the additional GNU GPL text is in
  `licenses/pystray-COPYING.txt`).
- Role: Windows system-tray icon and menu.

## Pillow 13.0.0

- Project: <https://python-pillow.org/>
- License: HPND (`licenses/Pillow.txt`).
- Role: icon generation, album-art handling and image scaling.

## Python 3.15

- Project: <https://www.python.org/>
- License: Python Software Foundation License 2.0 (`licenses/Python.txt`).
- Role: runtime bundled by PyInstaller.

## PyInstaller 6.22.3

- Project: <https://pyinstaller.org/>
- License: GNU GPL v2.0 or later with the PyInstaller bootloader exception
  (`licenses/PyInstaller.txt`). The exception allows distributing frozen
  applications under any license.
- Role: creates the standalone `AirMirror.exe` build.

## Inno Setup 6

- Project: <https://jrsoftware.org/isinfo.php>
- License: Inno Setup License (free to use, including commercial use).
- Role: builds the Windows installer. Inno Setup itself is not distributed with
  AirMirror.

## Trademarks

“AirPlay”, “iPhone”, “iPad”, “Mac” and “Apple” are trademarks of Apple Inc.
AirMirror is an independent, unofficial project and is not affiliated with,
endorsed by, or sponsored by Apple Inc.
