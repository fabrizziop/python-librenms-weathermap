> Note: quick PoC turned into a tool. Expect a few rough edges.

# LibreNMS Weathermap

Minimal, interactive weathermap generator for LibreNMS with a WYSIWYG editor.

Features
- Split links: each half shows outbound utilization from its node (hue-based scale)
- Multi-link support with curvature and per-end port labels
- Configurable node color/size and output dimensions (width, height, DPI)

Install
```bash

# Quick setup (Linux/Mac)
./setup.sh

# Or manual setup
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Quick start
```bash
cp config.ini.example config.ini

# Edit config.ini with your LibreNMS URL and token
# Then run:

python editor.py         # arrange and save topology
python main.py           # generate network_map.png
```

Minimal config snippet
```ini
[librenms]
url = https://your-librenms-instance.com
token = your_api_token_here

[settings]
min_util = 0
max_util = 1000
node_size = 20
fig_width = 16
fig_height = 12

node_color = lightblue
```

Use `python main.py --config config.ini --output map.png --no-show` to run headless.

For self-signed certificates, add `--insecure` (or `-k`) to disable SSL verification:
```bash
python main.py --insecure
```

The editor also has an "Insecure (Disable SSL)" checkbox in the toolbar for the same purpose.

Troubleshooting
- Install `tkinter` if editor fails to start (OS package manager)
- If API failures: verify LibreNMS URL and token
- If SSL certificate errors: use `--insecure` flag or check certificate configuration
- If labels overlap: reduce `node_size` or increase `fig_width`/`fig_height`

License: MIT (see LICENSE)
