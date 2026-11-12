from nexa.education.simulations import EducationEngine


def test_education_panel_loads_without_qml_errors():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from pathlib import Path
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from nexa.ui.education_bridge import EducationBridge

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("nexaEdu", EducationBridge())
    source = Path(__file__).parents[1] / "nexa" / "ui" / "qml" / "EducationPanel.qml"
    comp = QQmlComponent(engine, QUrl.fromLocalFile(str(source)))
    obj = comp.create()
    app.processEvents()
    assert obj is not None, [e.toString() for e in comp.errors()]
    assert not comp.errors(), [e.toString() for e in comp.errors()]


def test_catalog_contains_stem_and_virtual_lab_lessons():
    catalog = EducationEngine.catalog()
    ids = {x["id"] for x in catalog}
    assert {"bridge_load", "pendulum", "circuit", "ph_scale", "solar", "solar_system"} <= ids


def test_bridge_simulation_records_measurement_and_feedback():
    engine = EducationEngine()
    state = engine.select("bridge_load")
    assert state["lesson"]["title"] == "Cầu chịu tải"
    engine.set_value("load", 90)
    result = engine.run()["result"]
    assert result["unit"] == "đv"
    assert result["feedback"]
    assert engine.snapshot()["history_count"] == 1


def test_simulations_clamp_parameters_and_use_realistic_formulas():
    engine = EducationEngine()
    engine.select("circuit")
    engine.set_value("voltage", 1000)
    engine.set_value("resistance", 10)
    result = engine.run()["result"]
    assert result["value"] == 2.4  # điện áp bị chặn ở 24 V

    engine.select("pendulum")
    result = engine.run()["result"]
    assert 1.9 < result["value"] < 2.1


def test_lesson_protocol_and_series_are_recorded():
    engine = EducationEngine()
    state = engine.select("circuit")
    assert state["step"] == 0 and len(state["steps"]) == 3
    engine.advance_step()
    engine.run()
    state = engine.snapshot()
    assert state["step"] == 1 and state["series"][0]["x"] == 1
