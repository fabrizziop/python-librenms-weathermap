> Note: quick PoC turned into a tool. Expect a few rough edges.

# LibreNMS Weathermap

Minimal, interactive weathermap generator for LibreNMS with a WYSIWYG editor.

Features
- Split links: each half shows outbound utilization from its node (hue-based scale)
- Multi-link support with curvature and per-end port labels
- Configurable node color/size and output dimensions (width, height, DPI)
- Cloud/virtual nodes for unmanaged devices (ISP gateways, external networks)
- Pseudo nodes for one-to-many link scenarios (aggregating traffic from multiple sources)

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
cloud_node_color = lightgray
pseudo_node_color = lightyellow

# Dead link detection (optional)
show_dead_links = true
dead_link_color = black
```

Use `python main.py --config config.ini --output map.png --no-show` to run headless.

For self-signed certificates, add `--insecure` (or `-k`) to disable SSL verification:
```bash
python main.py --insecure
```

The editor also has an "Insecure (Disable SSL)" checkbox in the toolbar for the same purpose.

Cloud Nodes (Unmanaged Devices)
-------------------------------
Cloud nodes represent devices outside your LibreNMS monitoring (e.g., ISP routers, external gateways).
Utilization data is derived from the managed device's interface connected to the cloud.

To add a cloud node:
1. In the editor, click "Add Cloud Node" and give it a name (e.g., "ISP")
2. Click "Add Cloud Link" to connect a managed device to the cloud node
3. Select the managed device, its interface, and a virtual port name for the cloud side

In config.ini, cloud nodes use the `cloud:` prefix:
```ini
[devices]
router1 = 192.168.1.1
ISP = cloud:ISP_Gateway

[links]
link1 = router1:eth-wan -- ISP:wan
```

The link utilization is derived from the managed device's interface:
- Cloud outbound (towards your network) = managed interface inbound
- Managed outbound (towards cloud) = managed interface outbound

Pseudo Nodes (One-to-Many Links)
--------------------------------
Pseudo nodes act as junction points for scenarios where multiple managed devices connect to a single 
external point (e.g., multiple internal routers connecting to a single ISP port).

Use case: Your ISP provides a single uplink, but multiple internal routers share that connection.
Instead of creating multiple cloud nodes, create a single pseudo node that aggregates the traffic.

To add a pseudo node:
1. In the editor, click "Add Pseudo Node" and give it a name (e.g., "ISP_Junction")
2. Click "Add Pseudo Link" to connect managed devices to the pseudo node
3. Repeat for each managed device connecting to this junction point

In config.ini, pseudo nodes use the `pseudo:` prefix:
```ini
[devices]
router1 = 192.168.1.1
router2 = 192.168.1.2
router3 = 192.168.1.3
ISP_Junction = pseudo:ISP_Access_Point

[links]
link1 = router1:eth-wan -- ISP_Junction:virt-port1
link2 = router2:eth-wan -- ISP_Junction:virt-port2
link3 = router3:eth-wan -- ISP_Junction:virt-port3
```

Traffic aggregation:
- Pseudo node inbound = sum of all connected managed interfaces' outbound
- Pseudo node outbound = sum of all connected managed interfaces' inbound
- Each link segment shows the traffic specific to that connection

Testing
-------
Run the test suite:
```bash
# Install test dependencies
pip install pytest

# Run tests
pytest tests/ -v
```

Troubleshooting
- Install `tkinter` if editor fails to start (OS package manager)
- If API failures: verify LibreNMS URL and token
- If SSL certificate errors: use `--insecure` flag or check certificate configuration
- If labels overlap: reduce `node_size` or increase `fig_width`/`fig_height`

License: MIT (see LICENSE)
