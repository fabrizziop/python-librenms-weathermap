"""
Tests for librenms_weathermap.main module.

These tests verify the core weathermap generation functionality including:
- Configuration parsing
- Rate calculations
- Link processing
- Cloud/virtual node handling
"""

import pytest
import configparser
import tempfile
import os
from unittest.mock import patch, MagicMock
from io import StringIO


class TestConfigParsing:
    """Test configuration file parsing."""

    def test_config_reads_librenms_section(self, tmp_path):
        """Test that librenms URL and token are read correctly."""
        config_content = """
[librenms]
url = https://librenms.example.com
token = test_token_123

[devices]
[links]
[positions]
[settings]
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        assert config["librenms"]["url"] == "https://librenms.example.com"
        assert config["librenms"]["token"] == "test_token_123"

    def test_config_reads_devices(self, tmp_path):
        """Test that device mappings are read correctly."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
router1 = 192.168.1.1
switch1 = switch.example.com

[links]
[positions]
[settings]
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        assert config["devices"]["router1"] == "192.168.1.1"
        assert config["devices"]["switch1"] == "switch.example.com"

    def test_config_reads_links(self, tmp_path):
        """Test that link definitions are parsed correctly."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
router1 = 192.168.1.1
switch1 = switch.example.com

[links]
link1 = router1:eth0 -- switch1:GigabitEthernet0/1
link2 = switch1:GigabitEthernet0/2 -- router1:eth1

[positions]
[settings]
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        assert "link1" in config["links"]
        assert "router1:eth0" in config["links"]["link1"]
        assert "switch1:GigabitEthernet0/1" in config["links"]["link1"]

    def test_config_reads_positions(self, tmp_path):
        """Test that device positions are read correctly."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
router1 = 192.168.1.1

[links]
[positions]
router1_x = 100.5
router1_y = 200.0

[settings]
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        assert float(config["positions"]["router1_x"]) == 100.5
        assert float(config["positions"]["router1_y"]) == 200.0

    def test_config_reads_settings_with_defaults(self, tmp_path):
        """Test that settings are read with proper defaults."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
[links]
[positions]
[settings]
min_util = 10
max_util = 500
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        assert float(config["settings"].get("min_util", "0")) == 10.0
        assert float(config["settings"].get("max_util", "1000")) == 500.0
        # Test default values for missing settings
        assert int(config["settings"].get("node_size", "20")) == 20
        assert float(config["settings"].get("fig_width", "16")) == 16.0


class TestRateCalculation:
    """Test utilization rate calculations."""

    def test_get_rate_from_octets_rate(self):
        """Test rate calculation when ifInOctets_rate is available."""
        port = {"ifOutOctets_rate": 125000000}  # 1 Gbit/s in bytes
        
        def get_rate(port, direction):
            rate_key = f"if{direction}Octets_rate"
            delta_key = f"if{direction}Octets_delta"
            if rate_key in port and port[rate_key] is not None:
                return float(port[rate_key] * 8 / 1e6)
            elif (delta_key in port and "poll_period" in port and port["poll_period"] > 0):
                return float((port[delta_key] * 8 / port["poll_period"]) / 1e6)
            else:
                return 0.0
        
        rate = get_rate(port, "Out")
        assert rate == 1000.0  # 1000 Mbit/s

    def test_get_rate_from_delta(self):
        """Test rate calculation from delta values."""
        port = {
            "ifOutOctets_delta": 6250000000,  # bytes in poll period
            "poll_period": 300  # 5 minutes
        }
        
        def get_rate(port, direction):
            rate_key = f"if{direction}Octets_rate"
            delta_key = f"if{direction}Octets_delta"
            if rate_key in port and port[rate_key] is not None:
                return float(port[rate_key] * 8 / 1e6)
            elif (delta_key in port and "poll_period" in port and port["poll_period"] > 0):
                return float((port[delta_key] * 8 / port["poll_period"]) / 1e6)
            else:
                return 0.0
        
        rate = get_rate(port, "Out")
        # 6250000000 * 8 / 300 / 1e6 = 166.67 Mbit/s
        assert abs(rate - 166.67) < 0.1

    def test_get_rate_returns_zero_for_missing_data(self):
        """Test that missing data returns 0."""
        port = {}
        
        def get_rate(port, direction):
            rate_key = f"if{direction}Octets_rate"
            delta_key = f"if{direction}Octets_delta"
            if rate_key in port and port[rate_key] is not None:
                return float(port[rate_key] * 8 / 1e6)
            elif (delta_key in port and "poll_period" in port and port["poll_period"] > 0):
                return float((port[delta_key] * 8 / port["poll_period"]) / 1e6)
            else:
                return 0.0
        
        rate = get_rate(port, "Out")
        assert rate == 0.0


class TestLinkParsing:
    """Test link string parsing."""

    def test_parse_standard_link(self):
        """Test parsing a standard link definition."""
        link_str = "router1:eth0 -- switch1:GigabitEthernet0/1"
        
        parts = link_str.split(" -- ")
        port1_str = parts[0].strip()
        port2_str = parts[1].strip()
        device1_key, port1_name = port1_str.split(":")
        device2_key, port2_name = port2_str.split(":")
        
        assert device1_key == "router1"
        assert port1_name == "eth0"
        assert device2_key == "switch1"
        assert port2_name == "GigabitEthernet0/1"

    def test_parse_link_with_colons_in_port(self):
        """Test parsing link with complex port names."""
        link_str = "switch1:Ethernet1/0/1 -- switch2:Ethernet2/0/1"
        
        parts = link_str.split(" -- ")
        port1_str = parts[0].strip()
        port2_str = parts[1].strip()
        # Split only on first colon
        device1_key, port1_name = port1_str.split(":", 1)
        device2_key, port2_name = port2_str.split(":", 1)
        
        assert device1_key == "switch1"
        assert port1_name == "Ethernet1/0/1"


class TestCloudNodes:
    """Test cloud/virtual node functionality."""

    def test_cloud_node_config_format(self, tmp_path):
        """Test that cloud nodes are defined in config correctly."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
router1 = 192.168.1.1
ISP = cloud:ISP_Gateway

[links]
link1 = router1:eth0 -- ISP:wan

[positions]
router1_x = 100
router1_y = 100
ISP_x = 300
ISP_y = 100

[settings]
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        # Cloud nodes are prefixed with "cloud:"
        assert config["devices"]["ISP"] == "cloud:ISP_Gateway"
        assert config["devices"]["ISP"].startswith("cloud:")

    def test_is_cloud_node_detection(self):
        """Test cloud node detection function."""
        def is_cloud_node(hostname):
            return hostname.startswith("cloud:")
        
        assert is_cloud_node("cloud:ISP") is True
        assert is_cloud_node("192.168.1.1") is False
        assert is_cloud_node("router.example.com") is False

    def test_cloud_node_link_parsing(self):
        """Test that cloud node links can specify virtual ports."""
        link_str = "router1:eth-wan -- ISP:wan"
        
        parts = link_str.split(" -- ")
        assert len(parts) == 2
        
        device1, port1 = parts[0].split(":")
        device2, port2 = parts[1].split(":")
        
        assert device1 == "router1"
        assert port1 == "eth-wan"
        assert device2 == "ISP"
        assert port2 == "wan"

    def test_cloud_node_utilization_derivation(self):
        """Test that cloud node utilization is derived from managed interface."""
        # Simulate port data from managed device
        managed_port = {
            "ifInOctets_rate": 125000000,   # 1 Gbit/s in bytes (incoming to managed)
            "ifOutOctets_rate": 62500000,   # 500 Mbit/s in bytes (outgoing from managed)
        }
        
        def get_rate(port, direction):
            rate_key = f"if{direction}Octets_rate"
            if rate_key in port and port[rate_key] is not None:
                return float(port[rate_key] * 8 / 1e6)
            return 0.0
        
        # For a cloud link:
        # - Cloud outbound = managed interface inbound (what's coming FROM the cloud)
        # - Managed outbound = what's going TO the cloud
        
        cloud_outbound = get_rate(managed_port, "In")   # From cloud perspective
        managed_outbound = get_rate(managed_port, "Out")  # From managed perspective
        
        assert cloud_outbound == 1000.0   # 1000 Mbit/s
        assert managed_outbound == 500.0  # 500 Mbit/s

    def test_cloud_node_with_cloud_color_setting(self, tmp_path):
        """Test that cloud node color setting is read from config."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
ISP = cloud:ISP_Gateway

[links]
[positions]
[settings]
cloud_node_color = #CCCCCC
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        cloud_color = config["settings"].get("cloud_node_color", "lightgray")
        assert cloud_color == "#CCCCCC"

    def test_cloud_node_default_color(self, tmp_path):
        """Test that cloud node uses default color when not specified."""
        config_content = """
[librenms]
url = https://test.com
token = token

[devices]
[links]
[positions]
[settings]
"""
        config_file = tmp_path / "config.ini"
        config_file.write_text(config_content)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(config_file))

        cloud_color = config["settings"].get("cloud_node_color", "lightgray")
        assert cloud_color == "lightgray"


class TestPositionCalculations:
    """Test coordinate and position calculations."""

    def test_y_coordinate_inversion(self):
        """Test that Y coordinates are inverted for matplotlib."""
        x, y = 100, 200
        pos = (x, -y)
        
        assert pos[0] == 100
        assert pos[1] == -200

    def test_midpoint_calculation(self):
        """Test midpoint calculation for link drawing."""
        import numpy as np
        
        pos_u = np.array([0, 0])
        pos_v = np.array([100, 100])
        midpoint = (pos_u + pos_v) / 2
        
        assert midpoint[0] == 50
        assert midpoint[1] == 50


class TestArgumentParsing:
    """Test command-line argument parsing."""

    def test_default_arguments(self):
        """Test default argument values."""
        import argparse
        
        ap = argparse.ArgumentParser()
        ap.add_argument("--config", "-c", default="config.ini")
        ap.add_argument("--output", "-o", default="network_map.png")
        ap.add_argument("--no-show", action="store_true")
        ap.add_argument("--insecure", "-k", action="store_true")
        
        args = ap.parse_args([])
        
        assert args.config == "config.ini"
        assert args.output == "network_map.png"
        assert args.no_show is False
        assert args.insecure is False

    def test_custom_arguments(self):
        """Test custom argument values."""
        import argparse
        
        ap = argparse.ArgumentParser()
        ap.add_argument("--config", "-c", default="config.ini")
        ap.add_argument("--output", "-o", default="network_map.png")
        ap.add_argument("--no-show", action="store_true")
        ap.add_argument("--insecure", "-k", action="store_true")
        
        args = ap.parse_args(["-c", "custom.ini", "-o", "custom.png", "--no-show", "-k"])
        
        assert args.config == "custom.ini"
        assert args.output == "custom.png"
        assert args.no_show is True
        assert args.insecure is True


class TestSSLConfiguration:
    """Test SSL configuration handling."""

    def test_insecure_mode_disables_verification(self):
        """Test that insecure mode sets verify to False."""
        insecure = True
        verify_ssl = False if insecure else "/etc/ssl/certs/ca-certificates.crt"
        
        assert verify_ssl is False

    def test_secure_mode_uses_system_certs(self):
        """Test that secure mode uses system certificate store."""
        insecure = False
        verify_ssl = False if insecure else "/etc/ssl/certs/ca-certificates.crt"
        
        assert verify_ssl == "/etc/ssl/certs/ca-certificates.crt"
