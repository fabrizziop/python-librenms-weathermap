#!/usr/bin/env python3
"""
LibreNMS Weathermap Interactive Editor

This is a WYSIWYG editor for creating and managing weathermap configurations.
It provides a visual canvas for placing devices and creating links between them.

Features:
    - Visual device placement with drag-and-drop
    - Bulk device and link discovery from LibreNMS
    - Subnet-based automatic link detection
    - Zoom and pan capabilities
    - Right-click context menu for device management
    - Settings dialog for all configuration options

Usage:
    python -m librenms_weathermap.editor

Requirements:
    - tkinter (usually included with Python)
    - config.ini file (created automatically if missing)
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
import configparser
import os
from typing import Any, Dict, List
import urllib3

import requests  # type: ignore


class ConfigEditor:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LibreNMS Weathermap Config Editor")  # type: ignore
        self.config = configparser.ConfigParser()
        self.config.optionxform = str  # type: ignore
        self.filename = "config.ini"
        self.devices: Dict[str, Any] = {}
        self.links: List[Dict[str, str]] = []
        self.scale = 1.0
        self.fetched_devices: Dict[str, Any] = {}
        self.insecure_var = tk.BooleanVar(value=False)  # type: ignore
        self.load_config()

        # Canvas for drawing
        self.canvas = tk.Canvas(root, width=1200, height=800, bg="white")  # type: ignore
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)  # type: ignore

        # Toolbar
        toolbar = tk.Frame(root)  # type: ignore
        toolbar.pack(side=tk.RIGHT, fill=tk.Y)  # type: ignore

        tk.Checkbutton(toolbar, text="Insecure (Disable SSL)", variable=self.insecure_var).pack(
            fill=tk.X, anchor=tk.W
        )
        tk.Button(toolbar, text="Fetch Devices", command=self.fetch_devices).pack(
            fill=tk.X
        )
        tk.Button(toolbar, text="Add Device", command=self.add_device).pack(fill=tk.X)
        tk.Button(toolbar, text="Add Cloud Node", command=self.add_cloud_node).pack(fill=tk.X)
        tk.Button(toolbar, text="Add Link", command=self.add_link).pack(fill=tk.X)
        tk.Button(toolbar, text="Add Cloud Link", command=self.add_cloud_link).pack(fill=tk.X)
        tk.Button(toolbar, text="Bulk Add", command=self.bulk_add).pack(fill=tk.X)
        tk.Button(
            toolbar, text="Remove Unlinked", command=self.remove_unlinked_devices
        ).pack(fill=tk.X)
        tk.Button(toolbar, text="Zoom In", command=self.zoom_in).pack(fill=tk.X)
        tk.Button(toolbar, text="Zoom Out", command=self.zoom_out).pack(fill=tk.X)
        tk.Button(toolbar, text="Settings", command=self.open_settings).pack(fill=tk.X)
        tk.Button(toolbar, text="Save", command=self.save_config).pack(fill=tk.X)
        tk.Button(toolbar, text="Load", command=self.load_config).pack(fill=tk.X)

        self.selected_device = None
        self.pan_start = None
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Button-2>", self.on_middle_click)
        self.canvas.bind("<B2-Motion>", self.on_pan)

        self.draw_network()

    def load_config(self) -> None:
        if os.path.exists(self.filename):
            self.config.read(self.filename)
            # Ensure required sections exist
            for sec in ["librenms", "devices", "links", "positions", "settings"]:
                if not self.config.has_section(sec):
                    self.config[sec] = {}  # type: ignore
            # Load devices
            for device_key, hostname in self.config["devices"].items():
                x = self.config["positions"].getfloat(f"{device_key}_x", 100)
                y = self.config["positions"].getfloat(f"{device_key}_y", 100)
                self.devices[device_key] = {"x": x, "y": y, "hostname": hostname}
            # Load links
            for _, link_str in self.config["links"].items():
                parts = link_str.split(" -- ")
                dev1_port = parts[0].split(":")
                dev2_port = parts[1].split(":")
                dev1, port1 = dev1_port[0], dev1_port[1]
                dev2, port2 = dev2_port[0], dev2_port[1]
                self.links.append(
                    {"dev1": dev1, "dev2": dev2, "port1": port1, "port2": port2}
                )
        else:
            # Default config
            self.config["librenms"] = {
                "url": "https://your-librenms-instance.com",
                "token": "your_api_token_here",
            }
            self.config["devices"] = {}
            self.config["links"] = {}
            self.config["positions"] = {}
            self.config["settings"] = {"min_util": "0", "max_util": "1000"}

    def save_config(self) -> None:
        # Clear existing devices and positions sections
        self.config["devices"] = {}  # type: ignore
        self.config["positions"] = {}  # type: ignore

        for device_key, data in self.devices.items():
            self.config["devices"][device_key] = data["hostname"]
            self.config["positions"][f"{device_key}_x"] = str(data["x"])
            self.config["positions"][f"{device_key}_y"] = str(data["y"])

        # Clear existing links and add current
        self.config["links"] = {}
        for i, link in enumerate(self.links, 1):
            self.config["links"][f"link{i}"] = (
                f"{link['dev1']}:{link['port1']} -- {link['dev2']}:{link['port2']}"
            )

        with open(self.filename, "w") as f:
            self.config.write(f)
        messagebox.showinfo("Saved", "Configuration saved to config.ini")

    def fetch_devices(self) -> None:
        try:
            url = self.config["librenms"].get("url", "")
            token = self.config["librenms"].get("token", "")
            if not url or not token:
                messagebox.showerror("Error", "Set URL and Token in Settings first")
                return
            headers = {"X-Auth-Token": token}
            verify_ssl = False if self.insecure_var.get() else "/etc/ssl/certs/ca-certificates.crt"
            if self.insecure_var.get():
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = requests.get(f"{url}/api/v0/devices", headers=headers, verify=verify_ssl)
            r.raise_for_status()
            devices = r.json()["devices"]
            self.fetched_devices = {}
            for d in devices:
                hostname = d["hostname"]
                sysname = d.get("sysName", hostname).upper()
                self.fetched_devices[hostname] = {"sysName": sysname, **d}
            messagebox.showinfo(
                "Fetched", f"Fetched {len(devices)} devices from LibreNMS"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch devices: {e}")

    def is_cloud_node(self, hostname: str) -> bool:
        """Check if a hostname represents a cloud/virtual node."""
        return hostname.startswith("cloud:")

    def add_cloud_node(self) -> None:
        """Add a cloud/virtual node (unmanaged device like ISP gateway)."""
        cloud_name = simpledialog.askstring(
            "Cloud Node Name",
            "Enter a name for the cloud node (e.g., ISP, Internet, WAN):",
            initialvalue="ISP"
        )
        if not cloud_name:
            return

        # Sanitize name for use as device key
        device_key = cloud_name.replace(" ", "_")

        if device_key in self.devices:
            messagebox.showerror("Error", f"Device {device_key} already exists")
            return

        x = simpledialog.askinteger(
            "X Position", "Enter X position:", initialvalue=100
        )
        y = simpledialog.askinteger(
            "Y Position", "Enter Y position:", initialvalue=100
        )

        if x is not None and y is not None:
            # Cloud nodes use "cloud:" prefix in hostname
            self.devices[device_key] = {"x": x, "y": y, "hostname": f"cloud:{cloud_name}"}
            self.draw_network()
            messagebox.showinfo("Success", f"Added cloud node '{device_key}'")

    def add_device(self) -> None:
        if not self.fetched_devices:
            messagebox.showerror("Error", "Fetch devices first")  # type: ignore
            return
        # Show list of sysNames
        select_win = tk.Toplevel(self.root)  # type: ignore
        select_win.title("Select Device")  # type: ignore
        listbox = tk.Listbox(select_win, height=20, width=50)  # type: ignore
        hostname_to_sysname: Dict[str, str] = {}
        for hostname, data in self.fetched_devices.items():
            sysname = data["sysName"]
            listbox.insert(tk.END, sysname)
            hostname_to_sysname[sysname] = hostname
        listbox.pack()

        def select():
            selection = listbox.curselection()
            if selection:
                sysname = listbox.get(selection[0])
                hostname = hostname_to_sysname[sysname]
                device_key = simpledialog.askstring(
                    "Device Key", "Enter device key (name):", initialvalue=sysname
                )
                if device_key:
                    x = simpledialog.askinteger(
                        "X Position", "Enter X position:", initialvalue=100
                    )
                    y = simpledialog.askinteger(
                        "Y Position", "Enter Y position:", initialvalue=100
                    )
                    self.devices[device_key] = {"x": x, "y": y, "hostname": hostname}
                    self.draw_network()
            select_win.destroy()

        tk.Button(select_win, text="Select", command=select).pack()

    def add_link(self) -> None:
        if not self.devices:
            messagebox.showerror("Error", "Add devices first")  # type: ignore
            return
        existing_hostnames = {data["hostname"] for data in self.devices.values()}
        available_devices = {
            h: self.fetched_devices[h]
            for h in existing_hostnames
            if h in self.fetched_devices
        }
        if not available_devices:
            messagebox.showerror("Error", "No devices in layout match fetched data")
            return
        # Select device1
        select_win1 = tk.Toplevel(self.root)
        select_win1.title("Select First Device")
        listbox1 = tk.Listbox(select_win1, height=20, width=50)
        hostname_to_sysname = {h: d["sysName"] for h, d in available_devices.items()}
        for sysname in sorted(hostname_to_sysname.values()):
            listbox1.insert(tk.END, sysname)
        listbox1.pack()
        dev1_var = [None]

        def select_dev1():
            selection = listbox1.curselection()
            if selection:
                sysname = listbox1.get(selection[0])
                dev1_var[0] = [
                    h for h, s in hostname_to_sysname.items() if s == sysname
                ][0]
            select_win1.destroy()

        tk.Button(select_win1, text="Select", command=select_dev1).pack()
        self.root.wait_window(select_win1)
        if not dev1_var[0]:
            return
        hostname1 = dev1_var[0]

        # Select device2
        select_win2 = tk.Toplevel(self.root)
        select_win2.title("Select Second Device")
        listbox2 = tk.Listbox(select_win2, height=20, width=50)
        for sysname in sorted(hostname_to_sysname.values()):
            if hostname_to_sysname.get(hostname1) != sysname:
                listbox2.insert(tk.END, sysname)
        listbox2.pack()
        dev2_var = [None]

        def select_dev2():
            selection = listbox2.curselection()
            if selection:
                sysname = listbox2.get(selection[0])
                dev2_var[0] = [
                    h for h, s in hostname_to_sysname.items() if s == sysname
                ][0]
            select_win2.destroy()

        tk.Button(select_win2, text="Select", command=select_dev2).pack()
        self.root.wait_window(select_win2)
        if not dev2_var[0]:
            return
        hostname2 = dev2_var[0]

        # Find device keys
        dev1_key = None
        dev2_key = None
        for key, data in self.devices.items():
            if data["hostname"] == hostname1:
                dev1_key = key
            if data["hostname"] == hostname2:
                dev2_key = key
        if not dev1_key or not dev2_key:
            messagebox.showerror("Error", "Devices not added to config")
            return

        # Fetch ports for dev1
        try:
            url = self.config["librenms"]["url"]
            token = self.config["librenms"]["token"]
            headers = {"X-Auth-Token": token}
            verify_ssl = False if self.insecure_var.get() else "/etc/ssl/certs/ca-certificates.crt"
            r = requests.get(
                f"{url}/api/v0/devices/{hostname1}/ports",
                headers=headers,
                params={"columns": "ifName"},
                verify=verify_ssl,
            )
            r.raise_for_status()
            ports1: List[str] = [p["ifName"] for p in r.json()["ports"]]
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch ports for {hostname1}: {e}")
            return

        # Select port1
        select_win3 = tk.Toplevel(self.root)
        select_win3.title(f"Select Port for {hostname1}")
        listbox3 = tk.Listbox(select_win3, height=20, width=50)
        for port in sorted(ports1):
            listbox3.insert(tk.END, port)
        listbox3.pack()
        port1_var = [None]

        def select_port1():
            selection = listbox3.curselection()
            if selection:
                port1_var[0] = listbox3.get(selection[0])
            select_win3.destroy()

        tk.Button(select_win3, text="Select", command=select_port1).pack()
        self.root.wait_window(select_win3)
        if not port1_var[0]:
            return
        port1 = port1_var[0]

        # Fetch ports for dev2
        try:
            r = requests.get(
                f"{url}/api/v0/devices/{hostname2}/ports",
                headers=headers,
                params={"columns": "ifName"},
                verify=verify_ssl,
            )
            r.raise_for_status()
            ports2: List[str] = [p["ifName"] for p in r.json()["ports"]]
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch ports for {hostname2}: {e}")
            return

        # Select port2
        select_win4 = tk.Toplevel(self.root)
        select_win4.title(f"Select Port for {hostname2}")
        listbox4 = tk.Listbox(select_win4, height=20, width=50)
        for port in sorted(ports2):
            listbox4.insert(tk.END, port)
        listbox4.pack()
        port2_var = [None]

        def select_port2():
            selection = listbox4.curselection()
            if selection:
                port2_var[0] = listbox4.get(selection[0])
            select_win4.destroy()

        tk.Button(select_win4, text="Select", command=select_port2).pack()
        self.root.wait_window(select_win4)
        if not port2_var[0]:
            return
        port2 = port2_var[0]

        # Add link
        self.links.append(
            {"dev1": dev1_key, "dev2": dev2_key, "port1": port1, "port2": port2}
        )
        self.draw_network()

    def add_cloud_link(self) -> None:
        """Add a link between a managed device and a cloud node."""
        if not self.devices:
            messagebox.showerror("Error", "Add devices first")  # type: ignore
            return

        # Separate cloud and managed devices
        cloud_devices = {
            key: data for key, data in self.devices.items()
            if self.is_cloud_node(data["hostname"])
        }
        managed_devices = {
            key: data for key, data in self.devices.items()
            if not self.is_cloud_node(data["hostname"])
        }

        if not cloud_devices:
            messagebox.showerror("Error", "No cloud nodes found. Add a cloud node first.")
            return
        if not managed_devices:
            messagebox.showerror("Error", "No managed devices found. Add a device first.")
            return

        # Select the managed device first
        select_win1 = tk.Toplevel(self.root)
        select_win1.title("Select Managed Device")
        listbox1 = tk.Listbox(select_win1, height=20, width=50)
        for key in sorted(managed_devices.keys()):
            listbox1.insert(tk.END, key)
        listbox1.pack()
        managed_dev_var = [None]

        def select_managed():
            selection = listbox1.curselection()
            if selection:
                managed_dev_var[0] = listbox1.get(selection[0])
            select_win1.destroy()

        tk.Button(select_win1, text="Select", command=select_managed).pack()
        self.root.wait_window(select_win1)
        if not managed_dev_var[0]:
            return
        managed_key = managed_dev_var[0]
        managed_hostname = managed_devices[managed_key]["hostname"]

        # Select the cloud node
        select_win2 = tk.Toplevel(self.root)
        select_win2.title("Select Cloud Node")
        listbox2 = tk.Listbox(select_win2, height=20, width=50)
        for key in sorted(cloud_devices.keys()):
            listbox2.insert(tk.END, key)
        listbox2.pack()
        cloud_dev_var = [None]

        def select_cloud():
            selection = listbox2.curselection()
            if selection:
                cloud_dev_var[0] = listbox2.get(selection[0])
            select_win2.destroy()

        tk.Button(select_win2, text="Select", command=select_cloud).pack()
        self.root.wait_window(select_win2)
        if not cloud_dev_var[0]:
            return
        cloud_key = cloud_dev_var[0]

        # Fetch ports for managed device
        try:
            url = self.config["librenms"]["url"]
            token = self.config["librenms"]["token"]
            headers = {"X-Auth-Token": token}
            verify_ssl = False if self.insecure_var.get() else "/etc/ssl/certs/ca-certificates.crt"
            if self.insecure_var.get():
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = requests.get(
                f"{url}/api/v0/devices/{managed_hostname}/ports",
                headers=headers,
                params={"columns": "ifName"},
                verify=verify_ssl,
            )
            r.raise_for_status()
            ports: List[str] = [p["ifName"] for p in r.json()["ports"]]
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch ports for {managed_hostname}: {e}")
            return

        # Select port on managed device
        select_win3 = tk.Toplevel(self.root)
        select_win3.title(f"Select Port on {managed_key}")
        listbox3 = tk.Listbox(select_win3, height=20, width=50)
        for port in sorted(ports):
            listbox3.insert(tk.END, port)
        listbox3.pack()
        port_var = [None]

        def select_port():
            selection = listbox3.curselection()
            if selection:
                port_var[0] = listbox3.get(selection[0])
            select_win3.destroy()

        tk.Button(select_win3, text="Select", command=select_port).pack()
        self.root.wait_window(select_win3)
        if not port_var[0]:
            return
        managed_port = port_var[0]

        # Ask for virtual port name on cloud side
        cloud_port = simpledialog.askstring(
            "Cloud Port Name",
            f"Enter a name for the virtual port on {cloud_key}:",
            initialvalue="wan"
        )
        if not cloud_port:
            return

        # Add link (managed device first, cloud second)
        self.links.append({
            "dev1": managed_key,
            "dev2": cloud_key,
            "port1": managed_port,
            "port2": cloud_port
        })
        self.draw_network()
        messagebox.showinfo("Success", f"Added link: {managed_key}:{managed_port} -- {cloud_key}:{cloud_port}")

    def bulk_add(self) -> None:
        if not self.fetched_devices:
            messagebox.showerror("Error", "Fetch devices first")  # type: ignore
            return
        try:
            url = self.config["librenms"]["url"]
            token = self.config["librenms"]["token"]
            headers = {"X-Auth-Token": token}
        except KeyError:
            messagebox.showerror("Error", "Set URL and Token in Settings first")  # type: ignore
            return

        # Ask for max prefix
        max_prefix = simpledialog.askinteger(
            "Max Prefix",
            "Enter maximum prefix length for subnet matching (default 30):",
            initialvalue=30,
        )
        if max_prefix is None:
            return

        # Add all devices in a grid
        cols = 10
        x_start, y_start = 100, 100
        spacing = 150
        row, col = 0, 0
        for hostname, data in self.fetched_devices.items():
            sysname = data["sysName"]
            device_key = sysname
            x = x_start + col * spacing
            y = y_start + row * spacing
            self.devices[device_key] = {"x": x, "y": y, "hostname": hostname}
            col += 1
            if col >= cols:
                col = 0
                row += 1

        # Collect IP addresses and port mappings
        ip_list = []  # list of (ip, hostname, port_id, prefix)
        port_id_to_name = {}
        from collections import defaultdict
        import ipaddress

        subnet_to_ips = defaultdict(list)

        verify_ssl = False if self.insecure_var.get() else "/etc/ssl/certs/ca-certificates.crt"
        if self.insecure_var.get():
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        for hostname in self.fetched_devices:
            try:
                # Fetch IPs
                r = requests.get(f"{url}/api/v0/devices/{hostname}/ip", headers=headers, verify=verify_ssl)
                r.raise_for_status()
                addresses = r.json()["addresses"]
                for addr in addresses:
                    if "ipv4_address" in addr:
                        ip = addr["ipv4_address"]
                        port_id = addr["port_id"]
                        prefix = addr["ipv4_prefixlen"]
                        ip_list.append((ip, hostname, port_id, prefix))
                        network = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
                        subnet_key = (network.network_address, prefix)
                        subnet_to_ips[subnet_key].append(ip)
                # Fetch ports for name mapping
                r = requests.get(
                    f"{url}/api/v0/devices/{hostname}/ports?columns=port_id,ifName",
                    headers=headers,
                    verify=verify_ssl,
                )
                r.raise_for_status()
                ports = r.json()["ports"]
                for port in ports:
                    port_id_to_name[port["port_id"]] = port["ifName"]
            except Exception as e:
                print(f"Error fetching data for {hostname}: {e}")
                continue

        # Find links from subnets with exactly 2 IPs and prefix <= max_prefix
        link_candidates = []
        for subnet_key, ips in subnet_to_ips.items():
            network_addr, prefix = subnet_key
            if len(ips) == 2 and prefix <= max_prefix:
                ip1, ip2 = ips
                # Find the details
                data1 = next((h, p, pr) for i, h, p, pr in ip_list if i == ip1)
                data2 = next((h, p, pr) for i, h, p, pr in ip_list if i == ip2)
                host1, pid1, prefix1 = data1
                host2, pid2, prefix2 = data2
                if host1 in self.fetched_devices and host2 in self.fetched_devices:
                    port1 = port_id_to_name.get(pid1, "unknown")
                    port2 = port_id_to_name.get(pid2, "unknown")
                    dev1_key = self.fetched_devices[host1]["sysName"]
                    dev2_key = self.fetched_devices[host2]["sysName"]
                    link_candidates.append(
                        {
                            "dev1": dev1_key,
                            "dev2": dev2_key,
                            "port1": port1,
                            "port2": port2,
                        }
                    )

        # Add all found links
        added_links = set()
        for link in link_candidates:
            link_key = (link["dev1"], link["dev2"], link["port1"], link["port2"])
            if link_key not in added_links:
                self.links.append(link)
                added_links.add(link_key)

        self.draw_network()
        messagebox.showinfo(
            "Bulk Add", f"Added {len(self.devices)} devices and {len(self.links)} links"
        )

    def remove_unlinked_devices(self) -> None:
        # Find all devices that are referenced in links
        linked_devices: set[str] = set()
        for link in self.links:
            linked_devices.add(link["dev1"])
            linked_devices.add(link["dev2"])

        # Find devices with no links
        unlinked = [dev for dev in self.devices.keys() if dev not in linked_devices]

        if not unlinked:
            messagebox.showinfo("Remove Unlinked", "No unlinked devices found")
            return

        # Confirm deletion
        response = messagebox.askyesno(
            "Remove Unlinked", f"Found {len(unlinked)} unlinked devices. Remove them?"
        )
        if response:
            for dev in unlinked:
                del self.devices[dev]
            self.draw_network()
            messagebox.showinfo(
                "Remove Unlinked", f"Removed {len(unlinked)} unlinked devices"
            )

    def draw_network(self) -> None:
        self.canvas.delete("all")  # type: ignore

        # Draw grid and coordinates
        canvas_width = self.canvas.winfo_width()  # type: ignore
        canvas_height = self.canvas.winfo_height()  # type: ignore
        grid_spacing = 100

        # Draw vertical grid lines
        for x in range(0, canvas_width, grid_spacing):
            self.canvas.create_line(
                x, 0, x, canvas_height, fill="lightgray", dash=(2, 4)
            )
            self.canvas.create_text(x, 10, text=str(x), fill="gray", font=("Arial", 8))

        # Draw horizontal grid lines
        for y in range(0, canvas_height, grid_spacing):
            self.canvas.create_line(
                0, y, canvas_width, y, fill="lightgray", dash=(2, 4)
            )
            self.canvas.create_text(10, y, text=str(y), fill="gray", font=("Arial", 8))

        node_size = int(self.config["settings"].get("node_size", 20))
        node_color = self.config["settings"].get("node_color", "lightblue")
        cloud_node_color = self.config["settings"].get("cloud_node_color", "lightgray")
        # In matplotlib, node_size is area (radius^2), so we need to adjust for canvas display
        # Using a scale factor to approximate the visual size
        canvas_radius = node_size / 2.5  # Scale factor to match matplotlib's appearance
        for device_key, data in self.devices.items():
            x, y = data["x"], data["y"]
            # Use different color for cloud nodes
            fill_color = cloud_node_color if self.is_cloud_node(data["hostname"]) else node_color
            self.canvas.create_oval(
                x - canvas_radius,
                y - canvas_radius,
                x + canvas_radius,
                y + canvas_radius,
                fill=fill_color,
            )
            self.canvas.create_text(x, y, text=device_key)

        # Group links by device pair to handle multiple links
        from collections import defaultdict
        import math

        link_groups = defaultdict(list)
        for link in self.links:
            dev1, dev2 = link["dev1"], link["dev2"]
            # Use sorted tuple as key to group bidirectional links
            pair_key = tuple(sorted([dev1, dev2]))
            link_groups[pair_key].append(link)

        for pair_key, links in link_groups.items():
            # Get positions
            dev1 = links[0]["dev1"]
            dev2 = links[0]["dev2"]
            x1, y1 = self.devices[dev1]["x"], self.devices[dev1]["y"]
            x2, y2 = self.devices[dev2]["x"], self.devices[dev2]["y"]

            # Calculate perpendicular offset direction
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy)
            if length > 0:
                perp_x = -dy / length
                perp_y = dx / length
            else:
                perp_x, perp_y = 0, 0

            # Draw multiple links with offset
            num_links = len(links)
            spacing = 15  # pixels between parallel lines
            for i, link in enumerate(links):
                # Calculate offset for this link
                offset = (i - (num_links - 1) / 2) * spacing

                # Offset start and end points
                ox1 = x1 + perp_x * offset
                oy1 = y1 + perp_y * offset
                ox2 = x2 + perp_x * offset
                oy2 = y2 + perp_y * offset

                # Draw line
                self.canvas.create_line(ox1, oy1, ox2, oy2, fill="black", width=2)

                # Add port labels at midpoint with offset
                port1, port2 = link["port1"], link["port2"]
                mx = (ox1 + ox2) / 2
                my = (oy1 + oy2) / 2
                self.canvas.create_text(
                    mx, my - 10, text=f"{port1} - {port2}", font=("Arial", 8)
                )

    def on_canvas_click(self, event: Any) -> None:
        self.selected_device = None
        node_size = int(self.config["settings"].get("node_size", 20))
        for device_key, data in self.devices.items():
            x, y = data["x"], data["y"]
            # Check distance in canvas coordinates
            distance_squared = (event.x - x) ** 2 + (event.y - y) ** 2
            if distance_squared < (node_size * node_size):
                self.selected_device = device_key
                break

    def on_drag(self, event: Any) -> None:
        if self.selected_device:
            self.devices[self.selected_device]["x"] = event.x  # type: ignore
            self.devices[self.selected_device]["y"] = event.y  # type: ignore
            self.draw_network()

    def on_right_click(self, event: Any) -> None:
        # Find which device was clicked
        clicked_device = None
        node_size = int(self.config["settings"].get("node_size", 20))
        for device_key, data in self.devices.items():
            x, y = data["x"], data["y"]
            distance_squared = (event.x - x) ** 2 + (event.y - y) ** 2
            if distance_squared < (node_size * node_size):
                clicked_device = device_key
                break

        if clicked_device:
            # Create context menu
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(
                label="Rename", command=lambda: self.rename_device(clicked_device)
            )
            menu.add_command(
                label="Delete", command=lambda: self.delete_device(clicked_device)
            )
            menu.tk_popup(event.x_root, event.y_root, 0)
            # Release the grab after the menu is done
            menu.bind("<FocusOut>", lambda e: menu.unpost())

    def rename_device(self, old_key: str) -> None:
        new_key = simpledialog.askstring(
            "Rename Device", f"Enter new name for {old_key}:", initialvalue=old_key
        )
        if new_key and new_key != old_key:
            if new_key in self.devices:
                messagebox.showerror("Error", f"Device {new_key} already exists")
                return
            # Rename in devices dict
            self.devices[new_key] = self.devices.pop(old_key)
            # Update all links
            for link in self.links:
                if link["dev1"] == old_key:
                    link["dev1"] = new_key
                if link["dev2"] == old_key:
                    link["dev2"] = new_key
            self.draw_network()

    def delete_device(self, device_key: str) -> None:
        response = messagebox.askyesno(
            "Delete Device", f"Delete device {device_key} and all its links?"
        )  # type: ignore
        if response:
            # Remove device
            del self.devices[device_key]
            # Remove all links involving this device
            self.links = [
                link
                for link in self.links
                if link["dev1"] != device_key and link["dev2"] != device_key
            ]
            self.draw_network()

    def on_middle_click(self, event: Any) -> None:
        self.pan_start = (event.x, event.y)  # type: ignore

    def on_pan(self, event: Any) -> None:
        if self.pan_start:
            dx = event.x - self.pan_start[0]  # type: ignore
            dy = event.y - self.pan_start[1]  # type: ignore
            # Move all devices
            for device_key, data in self.devices.items():
                data["x"] += dx
                data["y"] += dy
            self.pan_start = (event.x, event.y)
            self.draw_network()

    def zoom_in(self) -> None:
        self.scale *= 1.2
        cx = self.canvas.winfo_width() / 2  # type: ignore
        cy = self.canvas.winfo_height() / 2  # type: ignore
        # Scale device positions
        for device_key, data in self.devices.items():
            data["x"] = cx + (data["x"] - cx) * 1.2
            data["y"] = cy + (data["y"] - cy) * 1.2
        self.draw_network()

    def zoom_out(self) -> None:
        self.scale /= 1.2
        cx = self.canvas.winfo_width() / 2  # type: ignore
        cy = self.canvas.winfo_height() / 2  # type: ignore
        # Scale device positions
        for device_key, data in self.devices.items():
            data["x"] = cx + (data["x"] - cx) / 1.2
            data["y"] = cy + (data["y"] - cy) / 1.2
        self.draw_network()

    def open_settings(self) -> None:
        settings_win = tk.Toplevel(self.root)  # type: ignore
        settings_win.title("Settings")  # type: ignore

        tk.Label(settings_win, text="LibreNMS URL:").grid(row=0, column=0, sticky="e")
        url_var = tk.StringVar(value=self.config["librenms"].get("url", ""))
        tk.Entry(settings_win, textvariable=url_var, width=50).grid(row=0, column=1)

        tk.Label(settings_win, text="Token:").grid(row=1, column=0, sticky="e")
        token_var = tk.StringVar(value=self.config["librenms"].get("token", ""))
        tk.Entry(settings_win, textvariable=token_var, width=50, show="*").grid(
            row=1, column=1
        )

        tk.Label(settings_win, text="Min Util:").grid(row=2, column=0, sticky="e")
        min_var = tk.StringVar(value=self.config["settings"].get("min_util", "0"))
        tk.Entry(settings_win, textvariable=min_var, width=50).grid(row=2, column=1)

        tk.Label(settings_win, text="Max Util:").grid(row=3, column=0, sticky="e")
        max_var = tk.StringVar(value=self.config["settings"].get("max_util", "1000"))
        tk.Entry(settings_win, textvariable=max_var, width=50).grid(row=3, column=1)

        tk.Label(settings_win, text="Node Size:").grid(row=4, column=0, sticky="e")
        node_var = tk.StringVar(value=self.config["settings"].get("node_size", "20"))
        tk.Entry(settings_win, textvariable=node_var, width=50).grid(row=4, column=1)

        tk.Label(settings_win, text="Figure Width (inches):").grid(
            row=5, column=0, sticky="e"
        )
        fig_width_var = tk.StringVar(
            value=self.config["settings"].get("fig_width", "16")
        )
        tk.Entry(settings_win, textvariable=fig_width_var, width=50).grid(
            row=5, column=1
        )

        tk.Label(settings_win, text="Figure Height (inches):").grid(
            row=6, column=0, sticky="e"
        )
        fig_height_var = tk.StringVar(
            value=self.config["settings"].get("fig_height", "12")
        )
        tk.Entry(settings_win, textvariable=fig_height_var, width=50).grid(
            row=6, column=1
        )

        tk.Label(settings_win, text="DPI:").grid(row=7, column=0, sticky="e")
        dpi_var = tk.StringVar(value=self.config["settings"].get("dpi", "100"))
        tk.Entry(settings_win, textvariable=dpi_var, width=50).grid(row=7, column=1)

        tk.Label(settings_win, text="Node Color:").grid(row=8, column=0, sticky="e")
        node_color_var = tk.StringVar(
            value=self.config["settings"].get("node_color", "lightblue")
        )
        tk.Entry(settings_win, textvariable=node_color_var, width=50).grid(
            row=8, column=1
        )

        tk.Label(settings_win, text="Cloud Node Color:").grid(row=9, column=0, sticky="e")
        cloud_node_color_var = tk.StringVar(
            value=self.config["settings"].get("cloud_node_color", "lightgray")
        )
        tk.Entry(settings_win, textvariable=cloud_node_color_var, width=50).grid(
            row=9, column=1
        )

        def save():
            self.config["librenms"]["url"] = url_var.get()
            self.config["librenms"]["token"] = token_var.get()
            self.config["settings"]["min_util"] = min_var.get()
            self.config["settings"]["max_util"] = max_var.get()
            self.config["settings"]["node_size"] = node_var.get()
            self.config["settings"]["fig_width"] = fig_width_var.get()
            self.config["settings"]["fig_height"] = fig_height_var.get()
            self.config["settings"]["dpi"] = dpi_var.get()
            self.config["settings"]["node_color"] = node_color_var.get()
            self.config["settings"]["cloud_node_color"] = cloud_node_color_var.get()
            settings_win.destroy()

        tk.Button(settings_win, text="Save", command=save).grid(
            row=10, column=0, pady=10
        )
        tk.Button(settings_win, text="Cancel", command=settings_win.destroy).grid(
            row=10, column=1, pady=10
        )

    def mainloop(self) -> None:
        self.root.mainloop()  # type: ignore


def main() -> None:
    root = tk.Tk()
    editor = ConfigEditor(root)
    editor.mainloop()


if __name__ == "__main__":
    main()
