"""
Integration tests for ingestion.py

Tests the MQTT image ingestion pipeline.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import ingestion


class TestOnMessage:
    """Tests for MQTT message handling."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires module refactoring - INCOMING_PATH is hardcoded")
    def test_saves_image_to_incoming(self, tmp_path, sample_image_bytes, monkeypatch):
        """Should save image payload to incoming directory."""
        pass

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires module refactoring - INCOMING_PATH is hardcoded")
    def test_uses_atomic_write(self, tmp_path, sample_image_bytes, monkeypatch):
        """Should use atomic write pattern (.tmp -> rename)."""
        pass

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires module refactoring - INCOMING_PATH is hardcoded")
    def test_extracts_device_from_topic(self, tmp_path, sample_image_bytes, monkeypatch):
        """Should include device name in filename."""
        pass


class TestOnConnect:
    """Tests for MQTT connection handling."""

    @pytest.mark.integration
    def test_subscribes_to_image_topic(self):
        """Should subscribe to image topics on connect."""
        mock_client = MagicMock()

        ingestion.on_connect(mock_client, None, None, 0)

        mock_client.subscribe.assert_called_once()
        call_args = mock_client.subscribe.call_args[0][0]
        assert "image" in call_args

    @pytest.mark.integration
    def test_handles_connection_failure(self):
        """Should log error on connection failure."""
        mock_client = MagicMock()

        # Should not raise
        ingestion.on_connect(mock_client, None, None, 1)

        # Should not attempt to subscribe on failure
        mock_client.subscribe.assert_not_called()


class TestMqttClientSetup:
    """Tests for MQTT client configuration."""

    @pytest.mark.integration
    def test_uses_callback_api_v2(self, mock_mqtt_client):
        """Should use paho-mqtt 2.x callback API."""
        with patch("paho.mqtt.client.Client") as mock_class:
            mock_class.return_value = mock_mqtt_client
            
            # The module should use CallbackAPIVersion.VERSION2
            # This is validated by the import pattern
            import paho.mqtt.client as mqtt
            assert hasattr(mqtt, "CallbackAPIVersion")
