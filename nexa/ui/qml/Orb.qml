import QtQuick

// Legacy entrypoint retains its audio sampling API and shares the new mirror renderer.
TacticalCore {
    property var bands: outBands.length ? outBands : [0,0,0,0,0,0,0,0]
    readonly property real bass: ((bands[0] || 0) + (bands[1] || 0) + (bands[2] || 0)) / 3
    function bandAt(u) {
        if (!bands.length) return 0;
        var x=Math.max(0,Math.min(1,u))*(bands.length-1), i=Math.floor(x), f=x-i;
        return i>=bands.length-1 ? bands[i] : bands[i]*(1-f)+bands[i+1]*f;
    }
}
