from types import SimpleNamespace as NS

from nexa.ui import device_telemetry as telemetry


def test_optional_sensors_are_not_reported_as_zero(monkeypatch):
    def unavailable(*args):
        raise OSError("unavailable")
    monkeypatch.setattr(telemetry, "wifi_status", lambda: {"available": False, "connected": False, "signal": None, "ssid": ""})
    result = telemetry.sample_device(NS(disk_usage=unavailable, sensors_battery=lambda: None))
    assert result["disk"] is None and result["battery"] is None
    assert result["charging"] is None and result["wifi"]["signal"] is None


def test_device_values_and_independent_battery_failure(monkeypatch):
    monkeypatch.setattr(telemetry, "wifi_status", lambda: {"available": True, "connected": True, "signal": 73, "ssid": "Test Wi-Fi"})
    disk = NS(percent=60, free=40 * 2**30, total=100 * 2**30)
    source = NS(disk_usage=lambda path: disk, sensors_battery=lambda: NS(percent=81, power_plugged=True))
    result = telemetry.sample_device(source)
    assert result["disk"] == 60 and result["disk_free_gb"] == 40
    assert result["disk_total_gb"] == 100 and result["battery"] == 81 and result["charging"] is True
    assert result["wifi"]["signal"] == 73
    def broken_battery():
        raise NotImplementedError
    source.sensors_battery = broken_battery
    result = telemetry.sample_device(source)
    assert result["battery"] is None and result["disk"] == 60


def test_inventory_distinguishes_missing_from_installed(monkeypatch):
    def version(name):
        if name == "PySide6":
            return "6.11.2"
        raise telemetry.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(telemetry.metadata, "version", version)
    rows = telemetry.library_inventory()
    assert rows[0]["version"] == "6.11.2" and rows[0]["installed"]
    assert all(not row["installed"] and row["version"] == "" for row in rows[1:])
    assert all(row["purpose"] for row in rows)
