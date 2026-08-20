# Clash Node Filter

A Windows desktop GUI for batch-checking Clash/Mihomo subscription nodes by making real HTTP/HTTPS web requests instead of using ping. The project is inspired by [zhsama/clash-speedtest](https://github.com/zhsama/clash-speedtest) and uses a single light desktop window with a compact layout inspired by FlClash.

## Features

- Accepts subscription URLs, Clash/Mihomo YAML, and Base64 node lists; multiple sources can be entered at once.
- Parses nodes and creates proxy connections through a local Mihomo core.
- Tests Cloudflare speed endpoints and selectable web targets for latency, packet loss, download/upload speed, and service availability.
- Overseas web targets support click-to-select multi-selection with `√` / `□` indicators.
- Configurable concurrency, per-stage timeout, maximum latency, and sample sizes.
- Live result table with horizontal scrolling and JSON/CSV export.
- The core listens only on `127.0.0.1:18080`, starts hidden, and does not open a terminal window.
- Windows high-DPI support.

## Screenshot

![Clash Node Filter screenshot](assets/screenshot.png)

## Download

Download the latest `ClashNodeFilter.exe` from the GitHub Releases page and run it directly. Go and Python are not required for the release build.

## Run from source

Requirements: Windows, Python 3.8+, and Go 1.22+.

```powershell
git clone <repository-url>
cd clash-node-filter
python -m pip install -r requirements.txt
.\build.ps1
python .\desktop_app.py
```

To build a distributable GUI directory:

```powershell
.\build_gui.ps1
```

The single-file executable is placed at `dist\Clash节点筛选器.exe`.

## Testing notes

The timeout value applies to one network stage. A node may go through latency, web-target, download, and upload checks, so a complete batch can take longer. A batch-level safety timeout and a “Stop current test” action are included. A failed website may be caused by the node, the target service, DNS, or the local network; one failed service does not necessarily mean the node is unusable.

Only test subscriptions you are authorized to use. Speed tests generate real traffic, so start with smaller sample sizes when appropriate.

## Project layout

- `desktop_app.py`: Tkinter GUI and local API client.
- `backend/`: Mihomo core service, node parsing, web tests, and unlock detectors.
- `build.ps1`: Builds the local test core.
- `build_gui.ps1`: Packages the Windows GUI with PyInstaller.
- `backend/desktop-config.yaml`: Desktop-mode configuration.

## Acknowledgements

Thanks to [zhsama/clash-speedtest](https://github.com/zhsama/clash-speedtest) for the reference implementation and to the [linux.do community](https://linux.do/) for discussion and knowledge sharing.
