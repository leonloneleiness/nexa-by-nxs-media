import QtQuick
import QtQuick3D

View3D {
    id: scene
    property string lessonId: "bridge_load"
    environment: SceneEnvironment { clearColor: "#08121f"; backgroundMode: SceneEnvironment.Color }
    camera: PerspectiveCamera { position: Qt.vector3d(0, 110, 260); eulerRotation.x: -12; clipFar: 2000 }
    DirectionalLight { eulerRotation.x: -35; eulerRotation.y: -25; brightness: 1.5 }
    PointLight { position: Qt.vector3d(0, 120, 120); brightness: 1200; color: "#8be9fd" }
    Node {
        eulerRotation.y: -18
        Model { source: "#Cube"; scale: Qt.vector3d(2.4, 0.12, 0.42); materials: DefaultMaterial { diffuseColor: "#22d3ee" } }
        Model { source: "#Cube"; position: Qt.vector3d(-105, -38, 0); scale: Qt.vector3d(0.18, 0.8, 0.5); materials: DefaultMaterial { diffuseColor: "#64748b" } }
        Model { source: "#Cube"; position: Qt.vector3d(105, -38, 0); scale: Qt.vector3d(0.18, 0.8, 0.5); materials: DefaultMaterial { diffuseColor: "#64748b" } }
        Model { visible: scene.lessonId === "circuit"; source: "#Sphere"; position: Qt.vector3d(0, 35, 0); scale: Qt.vector3d(0.45, 0.45, 0.45); materials: DefaultMaterial { diffuseColor: "#f59e0b"; emissiveFactor: 0.6 } }
        Model { visible: scene.lessonId === "solar_system"; source: "#Sphere"; position: Qt.vector3d(0, 0, 0); scale: Qt.vector3d(0.7, 0.7, 0.7); materials: DefaultMaterial { diffuseColor: "#fbbf24"; emissiveFactor: 1.0 } }
        Model { visible: scene.lessonId === "solar_system"; source: "#Sphere"; position: Qt.vector3d(70, 0, 0); scale: Qt.vector3d(0.22, 0.22, 0.22); materials: DefaultMaterial { diffuseColor: "#60a5fa" } }
    }
}
