import QtQuick
import "Theme.js" as Theme
import "MirrorMesh.js" as MirrorMesh

// Independent orbiting mirror shards; a slow breathing field holds them in a living sphere.
Item {
    id: core
    property string appState: "STANDBY"
    property real micLevel: 0
    property real outLevel: 0
    property var outBands: []
    property string effects: "full"
    property real measuredFps: 0
    readonly property bool idle: appState === "STANDBY" || appState === "INITIALIZING"
    readonly property bool animated: visible && effects !== "minimal"
    readonly property real inputLevel: appState === "SPEAKING" ? outLevel : appState === "LISTENING" || appState === "CONFIRMING" ? micLevel : 0
    property color accent: Theme.stateColor(appState)
    property real level: inputLevel
    property real phase: 0 // elapsed seconds; breathing stays steady across state changes
    property real orbitSpeed: appState === "THINKING" ? 0.36 : appState === "EXECUTING" ? 0.42 : 0.18
    property real orbitPhase: 0
    readonly property real breath: 0.5 - 0.5 * Math.cos(phase * Math.PI * 2 / 5.6)
    Behavior on orbitSpeed { NumberAnimation { duration: 1200 } }
    onPhaseChanged: if (!animated) field.requestPaint()
    onOrbitPhaseChanged: if (!animated) field.requestPaint()
    property int frameCount: 0
    property real frameSeconds: 0
    property real paintSeconds: 0
    Behavior on accent { ColorAnimation { duration: 600 } }
    Behavior on level { NumberAnimation { duration: 100 } }
    onAccentChanged: field.requestPaint()
    onLevelChanged: if (!animated) field.requestPaint()
    onOutBandsChanged: if (!animated) field.requestPaint()
    onAppStateChanged: field.requestPaint()
    onEffectsChanged: field.requestPaint()
    onVisibleChanged: if (visible) field.requestPaint()
    FrameAnimation {
        running: core.animated
        onTriggered: {
            var dt = Math.min(frameTime, 0.1)
            core.phase += dt
            core.orbitPhase += dt * core.orbitSpeed
            core.frameSeconds += dt; core.paintSeconds += dt; core.frameCount++
            if (core.frameSeconds >= 1) {
                core.measuredFps = core.frameCount / core.frameSeconds
                core.frameSeconds = 0; core.frameCount = 0
            }
            if (core.paintSeconds >= 1 / (core.effects === "full" ? 30 : 18)) {
                core.paintSeconds = 0; field.requestPaint()
            }
        }
    }
    Canvas {
        id: field
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"); c.reset()
            var s = Math.min(width, height), x = width / 2, y = height / 2
            if (s <= 0) return
            var r = s * 0.29, t = core.phase, a = core.accent
            function ink(alpha) { return Qt.rgba(a.r, a.g, a.b, alpha) }
            function circle(rad, alpha, line) {
                c.beginPath(); c.arc(x, y, rad, 0, Math.PI * 2)
                c.strokeStyle = ink(alpha); c.lineWidth = line; c.stroke()
            }
            var glow = c.createRadialGradient(x, y, r * 0.3, x, y, s * 0.49)
            glow.addColorStop(0, ink(0.09 + core.breath * 0.07)); glow.addColorStop(0.55, ink(0.045 + core.breath * 0.035 + core.level * 0.06)); glow.addColorStop(1, ink(0))
            c.fillStyle = glow; c.fillRect(0, 0, width, height)
            circle(r * 1.45, 0.12, 1)
            circle(r * 1.35, 0.07, 1)
            // Sparse precision marks around the outer orbit.
            for (var i = 0; i < 72; i++) {
                var angle = i * Math.PI / 36, major = i % 6 === 0
                var ri = r * (major ? 1.42 : 1.44), ro = r * 1.46
                c.beginPath(); c.moveTo(x + Math.cos(angle) * ri, y + Math.sin(angle) * ri)
                c.lineTo(x + Math.cos(angle) * ro, y + Math.sin(angle) * ro)
                c.strokeStyle = ink(major ? 0.48 : 0.16); c.lineWidth = 1; c.stroke()
            }
            // Two deliberately incomplete orbital arcs.
            for (var j = 0; j < 2; j++) {
                var rot = (j ? -t * 0.7 : t) + j * Math.PI
                c.beginPath(); c.arc(x, y, r * (j ? 1.23 : 1.32), rot + 0.2, rot + 1.85)
                c.strokeStyle = ink(j ? 0.42 : 0.75); c.lineWidth = j ? 1 : 1.6; c.stroke()
                var px = x + Math.cos(rot + 1.85) * r * (j ? 1.23 : 1.32)
                var py = y + Math.sin(rot + 1.85) * r * (j ? 1.23 : 1.32)
                c.beginPath(); c.arc(px, py, s * 0.005, 0, Math.PI * 2); c.fillStyle = ink(0.9); c.fill()
            }
            // Every triangle orbits independently. Shrunk local vertices leave real empty space.
            var faces=[], tilt=-0.24+Math.sin(t*0.19)*0.06;
            var cx=Math.cos(tilt), sx=Math.sin(tilt);
            function rotate(p, angle) {
                var ct=Math.cos(angle),st=Math.sin(angle),vx=p[0]*ct+p[2]*st,vz=-p[0]*st+p[2]*ct;
                return [vx,p[1]*cx-vz*sx,p[1]*sx+vz*cx];
            }
            for(var fi=0;fi<MirrorMesh.shards.length;fi++) {
                var shard=MirrorMesh.shards[fi], seed=shard.seed;
                var angular=core.orbitPhase*(0.8+0.22*Math.sin(seed))+0.38;
                var band=core.appState === "SPEAKING" && core.outBands.length ? (core.outBands[fi%core.outBands.length] || 0) : core.level;
                var radius=0.96+core.breath*0.10+Math.sin(seed)*0.065+Math.sin(t*0.85+seed)*0.035+band*0.10;
                // A loose outer population makes the circular flight paths visible at the silhouette.
                if(fi%9===0) radius+=0.17;
                var center=rotate(shard.center,angular), local=[], flutter=Math.sin(t*0.65+seed)*0.65;
                var cf=Math.cos(flutter),sf=Math.sin(flutter);
                for(var pi=0;pi<3;pi++) {
                    var v=shard.local[pi];
                    var offset=rotate([v[0]*cf-v[1]*sf,v[0]*sf+v[1]*cf,v[2]],angular);
                    local.push([center[0]*radius+offset[0],center[1]*radius+offset[1],center[2]*radius+offset[2]]);
                }
                var p=local[0],q=local[1],z=local[2];
                var ux=q[0]-p[0],uy=q[1]-p[1],uz=q[2]-p[2],vx=z[0]-p[0],vy=z[1]-p[1],vz=z[2]-p[2];
                var nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,nn=Math.sqrt(nx*nx+ny*ny+nz*nz);
                nx/=nn; ny/=nn; nz/=nn;
                if(nz<0) {nx=-nx;ny=-ny;nz=-nz;}
                faces.push({p:p,q:q,z:z,n:[nx,ny,nz],depth:center[2],id:fi});
            }
            faces.sort(function(a,b){return a.depth-b.depth});
            function heart() {
                var hr=r*(0.66+core.breath*0.10), light=c.createRadialGradient(x,y,0,x,y,hr);
                light.addColorStop(0,ink(0.32+core.breath*0.18+core.level*0.12));
                light.addColorStop(0.25,ink(0.16+core.breath*0.09));
                light.addColorStop(0.6,ink(0.065)); light.addColorStop(1,ink(0));
                c.fillStyle=light;c.fillRect(x-hr,y-hr,hr*2,hr*2);
            }
            var lit=false;
            for(var ff=0;ff<faces.length;ff++) {
                var tile=faces[ff],n=tile.n;
                if(!lit && tile.depth>=0) {heart();lit=true;}
                var rx=2*n[2]*n[0],ry=2*n[2]*n[1];
                var key=Math.pow(Math.max(0,-n[0]*0.48-n[1]*0.58+n[2]*0.65),10);
                var strip=Math.exp(-Math.pow((rx+0.40)/0.18,2))*Math.exp(-Math.pow((ry+0.30)/0.85,4));
                var edge=Math.pow(1-n[2],3),noise=Math.abs((Math.sin(tile.id*127.1)*43758.5)%1);
                var silver=Math.min(1,0.17+key*0.66+strip*0.74+edge*0.23+noise*0.12);
                var blue=Math.max(0,rx)*0.16,alpha=tile.depth<0 ? 0.20 : 0.65+tile.depth*0.30;
                c.beginPath();c.moveTo(x+tile.p[0]*r,y+tile.p[1]*r);c.lineTo(x+tile.q[0]*r,y+tile.q[1]*r);c.lineTo(x+tile.z[0]*r,y+tile.z[1]*r);c.closePath();
                c.fillStyle=Qt.rgba(Math.min(1,silver*0.86),Math.min(1,silver*0.95+0.08+blue),Math.min(1,silver+0.14+blue),alpha);c.fill();
                c.strokeStyle=ink(tile.depth<0?0.12:0.28+strip*0.35);c.lineWidth=0.55;c.stroke();
            }
            // Actual microphone / output levels modulate the equatorial signal.
            c.beginPath()
            for (var q = 0; q <= 100; q++) {
                var f = q / 100, dx = (f - 0.5) * r * 1.55
                var band = core.appState === "SPEAKING" && core.outBands.length ? (core.outBands[Math.min(core.outBands.length - 1, Math.floor(f * core.outBands.length))] || 0) : core.level
                var amp = Math.sin(f * Math.PI) * r * (0.018 + band * 0.23)
                var dy = Math.sin(f * 32 - t * 7) * amp
                if (q === 0) c.moveTo(x + dx, y + r * 1.16 + dy); else c.lineTo(x + dx, y + r * 1.16 + dy)
            }
            c.strokeStyle = ink(0.9); c.lineWidth = 1.4; c.stroke()
            var light = c.createRadialGradient(x, y, 0, x, y, r * 0.25)
            light.addColorStop(0, ink(0.26 + core.level * 0.25)); light.addColorStop(1, ink(0))
            c.fillStyle = light; c.fillRect(x-r, y-r, r*2, r*2)
        }
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height / 2 + Math.min(parent.width, parent.height) * 0.46
        visible: core.width > 250
        text: "N E X A   /   L I V I N G   C O R E"
        color: Theme.textPrimary; opacity: 0.65
        font.family: Theme.font; font.pixelSize: 9; font.letterSpacing: 1
    }
}
