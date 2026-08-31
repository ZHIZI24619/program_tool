from dap_flash_tool.app_settings import AppSettings, AppSettingsStore


def test_settings_round_trip_preserves_algorithm_ram(tmp_path) -> None:
    store = AppSettingsStore(tmp_path / "settings.json")
    expected = AppSettings(
        algorithm_ram_start="0x20000100",
        algorithm_ram_size="0x800",
    )

    store.save(expected)
    loaded = store.load()

    assert loaded.algorithm_ram_start == expected.algorithm_ram_start
    assert loaded.algorithm_ram_size == expected.algorithm_ram_size
