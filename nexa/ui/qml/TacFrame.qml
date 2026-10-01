import QtQuick
import "Theme.js" as Theme

// Retains the original frame API so all workspaces share one surface treatment.
Rectangle {
    id: frame
    property real cut: 8
    property color fill: "transparent"
    property color stroke: Theme.border
    property real strokeW: 1
    radius: Theme.radius
    color: fill
    border.color: stroke
    border.width: strokeW
    Rectangle { x: 1; y: 1; width: Math.max(0, parent.width - 2); height: 1; color: Theme.accent; opacity: 0.10 }
    Rectangle { x: 0; y: 0; width: Math.min(24, parent.width); height: 1; color: frame.stroke; opacity: 0.9 }
    Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    Behavior on color { ColorAnimation { duration: Theme.motion } }
}
