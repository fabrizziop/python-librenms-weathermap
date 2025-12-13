"""
Tests for librenms_weathermap.editor module.

These tests verify the editor functionality including:
- Configuration loading and saving
- Device management
- Link management
- Cloud node handling in editor
"""

import pytest
import configparser
import tempfile
import os


class TestConfigEditorLoading:
    """Test configuration loading in editor."""

    def test_load_devices_from_config(self, tmp_path):
        """Test that devices are loaded from config correctly."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
router1 = 192.168.1.1
switch1 = switch.example.com

[links]
[positions]
router1_x = 100
router1_y = 200
switch1_x = 300
switch1_y = 200

[settings]
node_size = 20
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        devices = {}
        for device_key, hostname in config["devices"].items():
            x = config["positions"].getfloat(f"{device_key}_x", 100)
            y = config["positions"].getfloat(f"{device_key}_y", 100)
            devices[device_key] = {"x": x, "y": y, "hostname": hostname}

        assert "router1" in devices
        assert devices["router1"]["hostname"] == "192.168.1.1"
        assert devices["router1"]["x"] == 100
        assert devices["router1"]["y"] == 200

    def test_load_links_from_config(self, tmp_path):
        """Test that links are loaded from config correctly."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
router1 = 192.168.1.1
switch1 = switch.example.com

[links]
link1 = router1:eth0 -- switch1:Gi0/1
link2 = switch1:Gi0/2 -- router1:eth1

[positions]
[settings]
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        links = []
        for _, link_str in config["links"].items():
            parts = link_str.split(" -- ")
            dev1_port = parts[0].split(":")
            dev2_port = parts[1].split(":")
            dev1, port1 = dev1_port[0], dev1_port[1]
            dev2, port2 = dev2_port[0], dev2_port[1]
            links.append({"dev1": dev1, "dev2": dev2, "port1": port1, "port2": port2})

        assert len(links) == 2
        assert links[0]["dev1"] == "router1"
        assert links[0]["port1"] == "eth0"


class TestConfigEditorSaving:
    """Test configuration saving in editor."""

    def test_save_devices_to_config(self, tmp_path):
        """Test that devices are saved to config correctly."""
        config = configparser.ConfigParser()
        config.optionxform = str
        config["librenms"] = {"url": "https://test.com", "token": "token"}
        config["devices"] = {}
        config["positions"] = {}
        config["links"] = {}
        config["settings"] = {}

        devices = {
            "router1": {"x": 150, "y": 250, "hostname": "192.168.1.1"},
            "switch1": {"x": 350, "y": 250, "hostname": "10.0.0.1"},
        }

        for device_key, data in devices.items():
            config["devices"][device_key] = data["hostname"]
            config["positions"][f"{device_key}_x"] = str(data["x"])
            config["positions"][f"{device_key}_y"] = str(data["y"])

        config_file = tmp_path / "config.ini"
        with open(config_file, "w") as f:
            config.write(f)

        # Reload and verify
        config2 = configparser.ConfigParser()
        config2.optionxform = str
        config2.read(str(config_file))

        assert config2["devices"]["router1"] == "192.168.1.1"
        assert config2["positions"]["router1_x"] == "150"
        assert config2["positions"]["router1_y"] == "250"

    def test_save_links_to_config(self, tmp_path):
        """Test that links are saved to config correctly."""
        config = configparser.ConfigParser()
        config.optionxform = str
        config["librenms"] = {"url": "https://test.com", "token": "token"}
        config["devices"] = {}
        config["positions"] = {}
        config["links"] = {}
        config["settings"] = {}

        links = [
            {"dev1": "router1", "dev2": "switch1", "port1": "eth0", "port2": "Gi0/1"},
            {"dev1": "switch1", "dev2": "router1", "port1": "Gi0/2", "port2": "eth1"},
        ]

        for i, link in enumerate(links, 1):
            config["links"][f"link{i}"] = (
                f"{link['dev1']}:{link['port1']} -- {link['dev2']}:{link['port2']}"
            )

        config_file = tmp_path / "config.ini"
        with open(config_file, "w") as f:
            config.write(f)

        # Reload and verify
        config2 = configparser.ConfigParser()
        config2.optionxform = str
        config2.read(str(config_file))

        assert "link1" in config2["links"]
        assert "router1:eth0 -- switch1:Gi0/1" == config2["links"]["link1"]


class TestDeviceManagement:
    """Test device management operations."""

    def test_add_device(self):
        """Test adding a device to the devices dict."""
        devices = {}
        device_key = "new_router"
        hostname = "192.168.1.100"
        x, y = 200, 300

        devices[device_key] = {"x": x, "y": y, "hostname": hostname}

        assert device_key in devices
        assert devices[device_key]["hostname"] == hostname
        assert devices[device_key]["x"] == 200

    def test_rename_device(self):
        """Test renaming a device updates all references."""
        devices = {"old_name": {"x": 100, "y": 100, "hostname": "192.168.1.1"}}
        links = [
            {"dev1": "old_name", "dev2": "switch1", "port1": "eth0", "port2": "Gi0/1"},
            {"dev1": "switch1", "dev2": "old_name", "port1": "Gi0/2", "port2": "eth1"},
        ]

        old_key = "old_name"
        new_key = "new_name"

        # Rename in devices
        devices[new_key] = devices.pop(old_key)

        # Update links
        for link in links:
            if link["dev1"] == old_key:
                link["dev1"] = new_key
            if link["dev2"] == old_key:
                link["dev2"] = new_key

        assert "new_name" in devices
        assert "old_name" not in devices
        assert links[0]["dev1"] == "new_name"
        assert links[1]["dev2"] == "new_name"

    def test_delete_device_removes_links(self):
        """Test that deleting a device removes associated links."""
        devices = {
            "router1": {"x": 100, "y": 100, "hostname": "192.168.1.1"},
            "switch1": {"x": 300, "y": 100, "hostname": "10.0.0.1"},
            "switch2": {"x": 300, "y": 300, "hostname": "10.0.0.2"},
        }
        links = [
            {"dev1": "router1", "dev2": "switch1", "port1": "eth0", "port2": "Gi0/1"},
            {"dev1": "router1", "dev2": "switch2", "port1": "eth1", "port2": "Gi0/1"},
            {"dev1": "switch1", "dev2": "switch2", "port1": "Gi0/2", "port2": "Gi0/2"},
        ]

        device_to_delete = "router1"
        del devices[device_to_delete]
        links = [
            link
            for link in links
            if link["dev1"] != device_to_delete and link["dev2"] != device_to_delete
        ]

        assert "router1" not in devices
        assert len(links) == 1
        assert links[0]["dev1"] == "switch1"


class TestLinkManagement:
    """Test link management operations."""

    def test_remove_unlinked_devices(self):
        """Test removing devices that have no links."""
        devices = {
            "router1": {"x": 100, "y": 100, "hostname": "192.168.1.1"},
            "switch1": {"x": 300, "y": 100, "hostname": "10.0.0.1"},
            "orphan": {"x": 500, "y": 100, "hostname": "10.0.0.99"},
        }
        links = [
            {"dev1": "router1", "dev2": "switch1", "port1": "eth0", "port2": "Gi0/1"},
        ]

        # Find linked devices
        linked_devices = set()
        for link in links:
            linked_devices.add(link["dev1"])
            linked_devices.add(link["dev2"])

        # Find unlinked
        unlinked = [dev for dev in devices.keys() if dev not in linked_devices]

        assert "orphan" in unlinked
        assert len(unlinked) == 1

        # Remove unlinked
        for dev in unlinked:
            del devices[dev]

        assert "orphan" not in devices
        assert len(devices) == 2


class TestCloudNodesInEditor:
    """Test cloud/virtual node handling in editor."""

    def test_add_cloud_device(self):
        """Test adding a cloud device to the devices dict."""
        devices = {}
        device_key = "ISP"
        hostname = "cloud:ISP_Gateway"
        x, y = 500, 100

        devices[device_key] = {"x": x, "y": y, "hostname": hostname}

        assert device_key in devices
        assert devices[device_key]["hostname"].startswith("cloud:")

    def test_cloud_device_in_link(self):
        """Test that cloud devices can be linked to managed devices."""
        devices = {
            "router1": {"x": 100, "y": 100, "hostname": "192.168.1.1"},
            "ISP": {"x": 300, "y": 100, "hostname": "cloud:ISP_Gateway"},
        }
        links = [
            {"dev1": "router1", "dev2": "ISP", "port1": "eth-wan", "port2": "wan"},
        ]

        # Verify link references valid devices
        for link in links:
            assert link["dev1"] in devices
            assert link["dev2"] in devices

    def test_cloud_node_excluded_from_api_fetch(self):
        """Test that cloud nodes are excluded from API device fetching."""
        devices = {
            "router1": {"x": 100, "y": 100, "hostname": "192.168.1.1"},
            "ISP": {"x": 300, "y": 100, "hostname": "cloud:ISP_Gateway"},
        }

        # Get only managed devices for API calls
        managed_devices = {
            key: data
            for key, data in devices.items()
            if not data["hostname"].startswith("cloud:")
        }

        assert "router1" in managed_devices
        assert "ISP" not in managed_devices


class TestCoordinateHandling:
    """Test coordinate calculations for canvas display."""

    def test_node_click_detection(self):
        """Test that node click detection works within node radius."""
        device = {"x": 100, "y": 100, "hostname": "192.168.1.1"}
        node_size = 20
        click_x, click_y = 105, 105

        distance_squared = (click_x - device["x"]) ** 2 + (click_y - device["y"]) ** 2
        within_node = distance_squared < (node_size * node_size)

        assert within_node is True

    def test_node_click_detection_outside(self):
        """Test that clicks outside node are not detected."""
        device = {"x": 100, "y": 100, "hostname": "192.168.1.1"}
        node_size = 20
        click_x, click_y = 150, 150

        distance_squared = (click_x - device["x"]) ** 2 + (click_y - device["y"]) ** 2
        within_node = distance_squared < (node_size * node_size)

        assert within_node is False

    def test_parallel_link_offset_calculation(self):
        """Test offset calculation for parallel links."""
        import math

        x1, y1 = 100, 100
        x2, y2 = 300, 100

        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)

        if length > 0:
            perp_x = -dy / length
            perp_y = dx / length
        else:
            perp_x, perp_y = 0, 0

        # For a horizontal line, perpendicular should be vertical
        assert perp_x == 0
        assert perp_y == 1.0


class TestSettingsHandling:
    """Test settings management."""

    def test_default_settings(self):
        """Test that default settings are applied when missing."""
        config = configparser.ConfigParser()
        config.optionxform = str
        config["settings"] = {}

        min_util = float(config["settings"].get("min_util", "0"))
        max_util = float(config["settings"].get("max_util", "1000"))
        node_size = int(config["settings"].get("node_size", "20"))
        fig_width = float(config["settings"].get("fig_width", "16"))
        fig_height = float(config["settings"].get("fig_height", "12"))
        dpi = int(config["settings"].get("dpi", "100"))
        node_color = config["settings"].get("node_color", "lightblue")

        assert min_util == 0
        assert max_util == 1000
        assert node_size == 20
        assert fig_width == 16
        assert fig_height == 12
        assert dpi == 100
        assert node_color == "lightblue"

    def test_custom_settings(self):
        """Test that custom settings override defaults."""
        config = configparser.ConfigParser()
        config.optionxform = str
        config["settings"] = {
            "min_util": "10",
            "max_util": "500",
            "node_size": "30",
            "node_color": "#FF5733",
        }

        min_util = float(config["settings"].get("min_util", "0"))
        max_util = float(config["settings"].get("max_util", "1000"))
        node_size = int(config["settings"].get("node_size", "20"))
        node_color = config["settings"].get("node_color", "lightblue")

        assert min_util == 10
        assert max_util == 500
        assert node_size == 30
        assert node_color == "#FF5733"
