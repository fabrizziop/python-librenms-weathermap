#!/usr/bin/env python3
"""
Package version of `main.py` entry point for the weathermap.
"""

# Reuse the code from top-level main.py; this module can be invoked from CLI as librenms_weathermap.main:main
import argparse
from typing import Any, Dict, List
import urllib3

import requests  # type: ignore
import configparser
import networkx as nx  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import matplotlib.colors as mcolors  # type: ignore
import numpy as np  # type: ignore


def main():
    ap = argparse.ArgumentParser(
        description="Generate LibreNMS weathermap PNG from config.ini"
    )
    ap.add_argument("--config", "-c", default="config.ini", help="Path to config.ini")
    ap.add_argument(
        "--output", "-o", default="network_map.png", help="Output PNG filename"
    )
    ap.add_argument("--no-show", action="store_true", help="Do not call plt.show()")
    ap.add_argument(
        "--insecure", "-k", action="store_true", help="Disable SSL certificate verification"
    )
    args = ap.parse_args()

    # Read config
    config = configparser.ConfigParser()
    config.optionxform = str  # type: ignore  # Preserve case
    read_files = config.read(args.config)
    if not read_files:
        print(
            f"Warning: config file '{args.config}' not found. Create it from config.ini.example and update librenms settings."
        )

    if not config.has_section("librenms"):
        print(
            "Error: missing [librenms] section in config. Please copy config.ini.example to config.ini and set your values."
        )
        return

    librenms_url = config["librenms"].get("url", "").rstrip("/")
    token = config["librenms"].get("token", "")
    if not librenms_url or not token:
        print("Error: librenms.url and librenms.token must be set in config.ini")
        return
    headers = {"X-Auth-Token": token}

    min_util = (
        float(config["settings"].get("min_util", "0"))
        if config.has_section("settings")
        else 0.0
    )
    max_util = (
        float(config["settings"].get("max_util", "1000"))
        if config.has_section("settings")
        else 1000.0
    )
    node_size = (
        int(config["settings"].get("node_size", "20"))
        if config.has_section("settings")
        else 20
    )
    fig_width = (
        float(config["settings"].get("fig_width", "16"))
        if config.has_section("settings")
        else 16
    )
    fig_height = (
        float(config["settings"].get("fig_height", "12"))
        if config.has_section("settings")
        else 12
    )
    dpi = (
        int(config["settings"].get("dpi", "100"))
        if config.has_section("settings")
        else 100
    )
    node_color = (
        config["settings"].get("node_color", "lightblue")
        if config.has_section("settings")
        else "lightblue"
    )

    # Map device keys to hostnames
    if config.has_section("devices"):
        device_to_hostname: Dict[str, str] = {
            key: hostname for key, hostname in config["devices"].items()
        }
    else:
        device_to_hostname = {}

    # Helper function to check if a device is a cloud/virtual node
    def is_cloud_node(hostname: str) -> bool:
        return hostname.startswith("cloud:")

    # Get devices (skip cloud nodes - they don't exist in LibreNMS)
    verify_ssl = False if args.insecure else "/etc/ssl/certs/ca-certificates.crt"
    if args.insecure:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    devices: Dict[str, Any] = {}
    for _, hostname in device_to_hostname.items():
        if is_cloud_node(hostname):
            # Cloud nodes don't need API data - store a placeholder
            devices[hostname] = {"hostname": hostname, "is_cloud": True}
            continue
        try:
            r = requests.get(
                f"{librenms_url}/api/v0/devices/{hostname}", headers=headers, verify=verify_ssl
            )
            r.raise_for_status()
            devices[hostname] = r.json()["devices"][0]
        except requests.RequestException as e:
            print(f"Error fetching device {hostname}: {e}")
            continue

    # Get ports for devices (skip cloud nodes)
    ports: Dict[str, Any] = {}
    for hostname in devices:
        if is_cloud_node(hostname):
            continue
        try:
            r = requests.get(
                f"{librenms_url}/api/v0/devices/{hostname}/ports",
                headers=headers,
                params={
                    "columns": "ifName,ifInOctets_rate,ifOutOctets_rate,ifInOctets_delta,ifOutOctets_delta,poll_period"
                },
                verify=verify_ssl,
            )
            r.raise_for_status()
            for port in r.json()["ports"]:
                ports[f"{hostname}:{port['ifName']}"] = port
        except requests.RequestException as e:
            print(f"Error fetching ports for {hostname}: {e}")
            continue

    # Parse links and compute utilization
    # Utilization helper function defined outside the loop
    def get_rate(port: Dict[str, Any], direction: str) -> float:
        """Calculate rate in Mbit/s from port data."""
        rate_key = f"if{direction}Octets_rate"
        delta_key = f"if{direction}Octets_delta"
        if rate_key in port and port[rate_key] is not None:
            return float(port[rate_key] * 8 / 1e6)
        elif (
            delta_key in port
            and "poll_period" in port
            and port["poll_period"] > 0
        ):
            return float((port[delta_key] * 8 / port["poll_period"]) / 1e6)
        else:
            return 0.0

    links: List[Dict[str, Any]] = []
    if config.has_section("links"):
        for _, link_str in config["links"].items():
            try:
                parts = link_str.split(" -- ")
                port1_str = parts[0].strip()
                port2_str = parts[1].strip()
                device1_key, port1_name = port1_str.split(":", 1)
                device2_key, port2_name = port2_str.split(":", 1)
                hostname1 = device_to_hostname[device1_key]
                hostname2 = device_to_hostname[device2_key]

                # Check if either node is a cloud/virtual node
                is_cloud1 = is_cloud_node(hostname1)
                is_cloud2 = is_cloud_node(hostname2)

                if is_cloud1 and is_cloud2:
                    # Both nodes are cloud - skip (no data to derive)
                    print(f"Warning: Link {link_str} connects two cloud nodes - skipping")
                    continue
                elif is_cloud1:
                    # Node 1 is cloud, derive from node 2's interface
                    port2_key = f"{hostname2}:{port2_name}"
                    if port2_key not in ports:
                        print(f"Error: Port {port2_key} not found for cloud link")
                        continue
                    port2 = ports[port2_key]
                    # Cloud outbound = managed interface inbound
                    # Cloud inbound (managed outbound) = managed interface outbound
                    out_rate1 = get_rate(port2, "In")   # Cloud outbound = managed In
                    out_rate2 = get_rate(port2, "Out")  # Managed outbound
                elif is_cloud2:
                    # Node 2 is cloud, derive from node 1's interface
                    port1_key = f"{hostname1}:{port1_name}"
                    if port1_key not in ports:
                        print(f"Error: Port {port1_key} not found for cloud link")
                        continue
                    port1 = ports[port1_key]
                    # Managed outbound
                    # Cloud outbound = managed interface inbound
                    out_rate1 = get_rate(port1, "Out")  # Managed outbound
                    out_rate2 = get_rate(port1, "In")   # Cloud outbound = managed In
                else:
                    # Normal link between two managed devices
                    port1_key = f"{hostname1}:{port1_name}"
                    port2_key = f"{hostname2}:{port2_name}"
                    if port1_key not in ports:
                        print(f"Error: Port {port1_key} not found")
                        continue
                    if port2_key not in ports:
                        print(f"Error: Port {port2_key} not found")
                        continue
                    port1 = ports[port1_key]
                    port2 = ports[port2_key]
                    out_rate1 = get_rate(port1, "Out")
                    out_rate2 = get_rate(port2, "Out")

                # Store outbound utilization from each node
                links.append(
                    {
                        "u": hostname1,
                        "v": hostname2,
                        "out_util1": out_rate1,  # Outbound from node 1
                        "out_util2": out_rate2,  # Outbound from node 2
                        "port1": port1_name,
                        "port2": port2_name,
                    }
                )
            except KeyError as e:
                print(f"Error parsing link {link_str}: {e}")
                continue

    # Create graph
    G = nx.MultiGraph()  # type: ignore
    pos: Dict[str, tuple[float, float]] = {}
    for device_key, hostname in device_to_hostname.items():
        if config.has_section("positions"):
            x = float(config["positions"].get(f"{device_key}_x", "0"))
            y = float(config["positions"].get(f"{device_key}_y", "0"))
        else:
            x, y = 0.0, 0.0
        # Invert Y to match matplotlib's coordinate system (origin at bottom-left)
        pos[hostname] = (x, -y)
        G.add_node(hostname)  # type: ignore

    for link in links:
        G.add_edge(link["u"], link["v"])  # type: ignore

    # Read cloud node color setting
    cloud_node_color = (
        config["settings"].get("cloud_node_color", "lightgray")
        if config.has_section("settings")
        else "lightgray"
    )

    # Draw
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)  # type: ignore

    # Separate nodes into managed and cloud for different colors
    managed_nodes = [h for h in G.nodes() if not is_cloud_node(h)]  # type: ignore
    cloud_nodes = [h for h in G.nodes() if is_cloud_node(h)]  # type: ignore

    # Draw managed nodes
    if managed_nodes:
        nx.draw_networkx_nodes(G, pos, nodelist=managed_nodes, ax=ax, node_color=node_color, node_size=node_size**2)  # type: ignore

    # Draw cloud nodes with different color
    if cloud_nodes:
        nx.draw_networkx_nodes(G, pos, nodelist=cloud_nodes, ax=ax, node_color=cloud_node_color, node_size=node_size**2)  # type: ignore

    labels = {
        hostname: device_key.upper()
        for device_key, hostname in device_to_hostname.items()
    }
    nx.draw_networkx_labels(G, pos, labels=labels, ax=ax, font_size=10)  # type: ignore

    edges = list(G.edges(keys=True))  # type: ignore
    norm = mcolors.Normalize(vmin=min_util, vmax=max_util)  # type: ignore
    cmap = plt.cm.RdYlGn_r  # type: ignore  # Hue-based: green (low) -> yellow -> red (high)

    # Draw edges split in the middle with different colors for each direction
    # Each half shows the outbound utilization from that node
    for i, (u, v, k) in enumerate(edges):
        link = links[i]
        pos_u = np.array(pos[u])  # type: ignore
        pos_v = np.array(pos[v])  # type: ignore

        # Calculate midpoint
        midpoint = (pos_u + pos_v) / 2  # type: ignore

        # Calculate curvature offset for multiple links
        rad = 0.1 + 0.1 * k
        if rad > 0:
            # Calculate perpendicular offset for curvature
            direction = pos_v - pos_u  # type: ignore
            distance = np.linalg.norm(direction)  # type: ignore
            if distance > 0:
                perpendicular = np.array([-direction[1], direction[0]]) / distance  # type: ignore
                curve_offset = perpendicular * distance * rad  # type: ignore

                # Apply curve to midpoint
                midpoint = midpoint + curve_offset  # type: ignore

        # Get colors for each half
        color1 = cmap(norm(link["out_util1"]))  # type: ignore  # Color from u to midpoint
        color2 = cmap(norm(link["out_util2"]))  # type: ignore  # Color from v to midpoint

        # Draw first half (u to midpoint)
        ax.plot(  # type: ignore
            [pos_u[0], midpoint[0]],
            [pos_u[1], midpoint[1]],
            color=color1,
            linewidth=3,
            solid_capstyle="butt",
            zorder=1,
        )

        # Draw second half (midpoint to v)
        ax.plot(  # type: ignore
            [midpoint[0], pos_v[0]],
            [midpoint[1], pos_v[1]],
            color=color2,
            linewidth=3,
            solid_capstyle="butt",
            zorder=1,
        )

        # Add port labels at each end of the link
        # Calculate direction vector
        direction = pos_v - pos_u  # type: ignore
        distance = np.linalg.norm(direction)  # type: ignore

        if distance > 0:
            # Normalize direction
            dir_norm = direction / distance  # type: ignore

            # Calculate perpendicular for curve offset
            perpendicular = np.array([-dir_norm[1], dir_norm[0]])  # type: ignore

            # Label positions close to nodes (15% along the link)
            label_offset = distance * 0.15  # type: ignore

            # Position for port1 label (near node u)
            label_pos1 = pos_u + dir_norm * label_offset  # type: ignore
            if rad > 0:
                # Apply same curve offset as the line
                label_pos1 = label_pos1 + perpendicular * distance * rad * 0.3  # type: ignore

            # Position for port2 label (near node v)
            label_pos2 = pos_v - dir_norm * label_offset  # type: ignore
            if rad > 0:
                # Apply same curve offset as the line
                label_pos2 = label_pos2 + perpendicular * distance * rad * 0.3  # type: ignore

            # Draw port labels
            ax.text(  # type: ignore
                label_pos1[0],
                label_pos1[1],
                link["port1"],
                fontsize=8,
                ha="center",
                va="center",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor="white",
                    edgecolor="none",
                    alpha=0.7,
                ),
            )
            ax.text(  # type: ignore
                label_pos2[0],
                label_pos2[1],
                link["port2"],
                fontsize=8,
                ha="center",
                va="center",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor="white",
                    edgecolor="none",
                    alpha=0.7,
                ),
            )

    # Add colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)  # type: ignore
    sm.set_array([])  # type: ignore
    cbar = plt.colorbar(sm, ax=ax)  # type: ignore
    cbar.set_label("Utilization (Mbit/s)")  # type: ignore

    plt.title("Network Topology Map")  # type: ignore
    plt.savefig(args.output, dpi=dpi, bbox_inches="tight")  # type: ignore
    print(f"Weathermap written to {args.output}")
    if not args.no_show:
        try:
            plt.show()  # type: ignore
        except Exception:
            pass


if __name__ == "__main__":
    main()
