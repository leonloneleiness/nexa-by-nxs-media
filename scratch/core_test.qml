import QtQuick
import QtQuick.Controls
import "file:///C:/Users/ASUS/Desktop/NEXA/nexa/ui/qml"
ApplicationWindow { width: 1400; height: 480; visible: true; color: "#03080f"
  Row { Repeater { model: ["STANDBY","LISTENING","THINKING","SPEAKING"]
     TacticalCore { required property string modelData; width: 350; height: 470; appState: modelData; micLevel: 0.6; outLevel: 0.6
                    outBands: [0.9,0.7,0.6,0.5,0.4,0.3,0.2,0.1] } } } }