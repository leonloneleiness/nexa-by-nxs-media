import "Theme.js" as Theme
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick3D
import QtQuick3D.Helpers
import Nexa3D 1.0

// Trình xem mô hình 3D của NEXA. Trạng thái (camera đích, hiển thị, tách/lắp…) do Python (ViewerController) quyết
// định; QML chỉ hiển thị và nội suy mượt tới camera đích ở tốc độ khung hình màn hình.
Rectangle {
    id: root
    Connections {
        target: nexa3d
        function onPointerRequested(x, y, at, projectId) {
            if (!root.visible) return
            var hit = view.pick(x * view.width, y * view.height)
            nexa3d.selectPointedPart(hit.objectHit ? hit.objectHit.objectName : "", at, projectId)
            handPointer.x = x * view.width - 7
            handPointer.y = y * view.height - 7
            pointerTimer.restart()
        }
    }
    Rectangle {
        id: handPointer
        parent: view
        width: 14; height: 14; radius: 7
        color: "transparent"; border.color: Theme.accent; border.width: 2
        visible: pointerTimer.running
        z: 100
    }
    Timer { id: pointerTimer; interval: 350 }
    function commandProductPanel(action, panel) { hud.commandProductPanel(action, panel) }
    focus: true
    gradient: Gradient {
        GradientStop { position: 0.0; color: Theme.surface }
        GradientStop { position: 0.6; color: Theme.bg }
        GradientStop { position: 1.0; color: Theme.bg }
    }

    readonly property color cyan: Theme.accent
    readonly property color dim: Theme.textSecondary
    property var mdl: nexa3d.model
    property var vs: nexa3d.viewState
    property var cam: nexa3d.camera
    property var parts: mdl && mdl.parts ? mdl.parts : []
    property string renderMode: vs && vs.render_mode ? vs.render_mode : "normal"
    property real groundY: mdl && mdl.bottom !== undefined ? -mdl.bottom : 0
    property bool showTree: width >= 1000   // hẹp (đang song song với NEXA) → ẩn cây mặc định, nút "Cây bộ phận" bật lại
    // SSAO của Qt Quick 3D làm tối toàn khung ở cảnh tỷ lệ này (đo 2026-09-25) — tắt mặc định
    property bool ssao: false
    property bool vignette: false

    // ---------- camera nội suy ----------
    property real smYaw: 35
    property real smPitch: 20
    property real smZoom: 1
    property real smRadius: 100
    property vector3d smTarget: Qt.vector3d(0, 0, 0)
    readonly property real fov: 38
    property real camDist: smRadius / Math.sin(fov * Math.PI / 360) * 1.05 * smZoom
    property int frames: 0
    property real fpsTime: 0
    property real fps: 0

    // ---------- tách/lắp ----------
    property real explodeT: 0
    property bool exploded: vs && vs.exploded === true
    onExplodedChanged: { explodeAnim.to = exploded ? 1 : 0; explodeAnim.restart() }
    NumberAnimation { id: explodeAnim; target: root; property: "explodeT"; duration: 900; easing.type: Easing.InOutCubic }

    function stageK(order) {
        var orders = mdl && mdl.explode_orders ? mdl.explode_orders : [1]
        var n = Math.max(1, orders.length)
        var idx = Math.max(0, orders.indexOf(order))
        var d = n > 1 ? 0.5 / (n - 1) : 0
        var k = (explodeT - idx * d) / Math.max(0.05, 1 - (n - 1) * d)
        k = Math.max(0, Math.min(1, k))
        return k * k * (3 - 2 * k)
    }
    function explodeOffset(p) {
        if (explodeT <= 0.0001 || !p.explode) return Qt.vector3d(0, 0, 0)
        if (vs && vs.assembled && vs.assembled.indexOf(p.id) >= 0) return Qt.vector3d(0, 0, 0)
        var x = 0, y = 0, z = 0
        for (var i = 0; i < p.explode.length; i++) {
            var c = p.explode[i], k = stageK(c.order)
            x += c.v[0] * k; y += c.v[1] * k; z += c.v[2] * k
        }
        return Qt.vector3d(x, y, z)
    }
    // Khi tách, bộ phận có hướng tháo đi xuống (chân, nắp dưới, bánh…) sẽ chui dưới sàn → nâng cả mô hình (và camera)
    // lên đúng bằng phần bị lún để điểm thấp nhất đang hiển thị luôn nằm trên mặt sàn.
    property real explodeLift: {
        if (explodeT <= 0.0001 || !mdl || mdl.bottom === undefined) return 0
        var lo = 0
        for (var i = 0; i < parts.length; i++) {
            var p = parts[i]
            if (p.min_y === undefined || !partVisible(p.id)) continue
            lo = Math.min(lo, p.min_y + explodeOffset(p).y - mdl.bottom)
        }
        return -lo
    }
    function partVisible(id) {
        if (vs && vs.isolate && vs.isolate.length) return vs.isolate.indexOf(id) >= 0
        return !(vs && vs.visible && vs.visible[id] === false)
    }
    function inFocus(id) { return vs && vs.focus && vs.focus.indexOf(id) >= 0 }
    function partOpacity(id, base) {
        if (renderMode === "wireframe") return 0.12 * base
        if (renderMode === "xray") return (inFocus(id) || (vs && vs.selected === id)) ? base : 0.2
        if (vs && vs.focus && vs.focus.length && !inFocus(id)) return 0.16
        return base
    }
    function partRot(id) {
        var r = vs && vs.part_rot ? vs.part_rot[id] : undefined
        return r ? Qt.vector3d(r[0], r[1], r[2]) : Qt.vector3d(0, 0, 0)
    }

    // ---------- chuyển động (búng tay / nút "Chuyển động") ----------
    // Mỗi bộ phận có chuỗi chuyển động (của nó rồi của tổ tiên) do Python suy ra; ghép thành (R, t) mỗi khung hình.
    property bool animating: vs && vs.animating === true
    property real animRaw: 0
    property real animK: animRaw * animRaw * (3 - 2 * animRaw)
    property real animTau: 0
    function qmul(a, b) {
        return [a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
                a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
                a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
                a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0]]
    }
    function qaxis(a, deg) {
        var h = deg * Math.PI / 360, s = Math.sin(h)
        return [Math.cos(h), a[0] * s, a[1] * s, a[2] * s]
    }
    function qrot(q, v) {
        var x = q[1], y = q[2], z = q[3], w = q[0]
        var tx = 2 * (y * v[2] - z * v[1]), ty = 2 * (z * v[0] - x * v[2]), tz = 2 * (x * v[1] - y * v[0])
        return [v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx)]
    }
    // như QQuaternion::fromEulerAngles (q = yaw · pitch · roll)
    function eulerQ(e) {
        var p = e.x * Math.PI / 360, y = e.y * Math.PI / 360, r = e.z * Math.PI / 360
        var c1 = Math.cos(y), s1 = Math.sin(y), c2 = Math.cos(r), s2 = Math.sin(r), c3 = Math.cos(p), s3 = Math.sin(p)
        return [c1 * c2 * c3 + s1 * s2 * s3, c1 * c2 * s3 + s1 * s2 * c3, s1 * c2 * c3 - c1 * s2 * s3, c1 * s2 * c3 - s1 * c2 * s3]
    }
    function motionXf(ms, tau, k) {
        if (!ms || !ms.length || tau <= 0) return null
        var R = [1, 0, 0, 0], t = [0, 0, 0]
        for (var i = 0; i < ms.length; i++) {
            var m = ms[i], Rm, tm
            if (m.t === "slide") {
                var d = (m.off + m.amp * Math.sin(2 * Math.PI * tau / m.per + m.ph)) * k
                Rm = [1, 0, 0, 0]
                tm = [m.a[0] * d, m.a[1] * d, m.a[2] * d]
            } else {
                var ang = m.t === "spin" ? m.s * tau : (m.off + m.amp * Math.sin(2 * Math.PI * tau / m.per + m.ph)) * k
                Rm = qaxis(m.a, ang)
                var rc = qrot(Rm, m.c)
                tm = [m.c[0] - rc[0], m.c[1] - rc[1], m.c[2] - rc[2]]
            }
            var rt = qrot(Rm, t)
            t = [rt[0] + tm[0], rt[1] + tm[1], rt[2] + tm[2]]
            R = qmul(Rm, R)
        }
        return { q: R, t: t }
    }

    FrameAnimation {
        running: root.visible
        onTriggered: {
            var a = 1 - Math.exp(-frameTime * 14)
            if (root.cam && root.cam.yaw !== undefined) {
                var d = ((root.cam.yaw - root.smYaw + 540) % 360) - 180
                root.smYaw += d * a
                root.smPitch += (root.cam.pitch - root.smPitch) * a
                root.smZoom += (root.cam.zoom - root.smZoom) * a
                root.smRadius += (Math.max(0.01, root.cam.radius) - root.smRadius) * a
                var t = root.cam.target
                root.smTarget = Qt.vector3d(root.smTarget.x + (t[0] - root.smTarget.x) * a,
                                            root.smTarget.y + (t[1] - root.smTarget.y) * a,
                                            root.smTarget.z + (t[2] - root.smTarget.z) * a)
            }
            var tgt = root.animating ? 1 : 0
            if (root.animRaw !== tgt)
                root.animRaw = tgt > root.animRaw ? Math.min(1, root.animRaw + frameTime / 0.8)
                                                  : Math.max(0, root.animRaw - frameTime / 0.8)
            if (root.animRaw > 0) root.animTau += frameTime * root.animK
            root.frames += 1
            root.fpsTime += frameTime
            if (root.fpsTime >= 1.0) {
                root.fps = root.frames / root.fpsTime
                root.frames = 0; root.fpsTime = 0
                nexa3d.reportFps(root.fps)
            }
        }
    }

    // ---------- cảnh 3D ----------
    View3D {
        id: view
        anchors.fill: parent
        anchors.rightMargin: root.showTree ? partPanel.width + 20 : 0   // mô hình nằm giữa vùng nhìn thấy
        camera: camera
        environment: ExtendedSceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: Theme.bg
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            tonemapMode: SceneEnvironment.TonemapModeLinear
            exposure: 1.15
            lightProbe: nexa3d.studioHdr !== "" ? probeTex : null
            probeExposure: 1.25
            aoEnabled: root.ssao
            aoStrength: 60
            aoDistance: 6
            aoSoftness: 40
            vignetteEnabled: root.vignette
            vignetteStrength: 0.35
            vignetteRadius: 0.4
            glowEnabled: false
            glowStrength: 0.9
            glowIntensity: 0.25
            glowBloom: 0.08
        }
        Texture { id: probeTex; source: nexa3d.studioHdr }

        Node {
            id: orbit
            position: Qt.vector3d(root.smTarget.x, root.smTarget.y + root.groundY + root.explodeLift, root.smTarget.z)
            eulerRotation: Qt.vector3d(-root.smPitch, -root.smYaw, 0)
            PerspectiveCamera {
                id: camera
                z: root.camDist
                fieldOfView: root.fov
                clipNear: Math.max(0.05, root.camDist * 0.01)
                clipFar: root.camDist * 30 + 2000
            }
        }
        DirectionalLight {
            eulerRotation: Qt.vector3d(-50, -35, 0)
            brightness: 1.7
            castsShadow: true
            shadowMapQuality: Light.ShadowMapQualityHigh
            shadowFactor: 55
            shadowMapFar: 1200
        }
        DirectionalLight { eulerRotation: Qt.vector3d(-20, 130, 0); brightness: 0.6; color: "#dfebed" }
        DirectionalLight { eulerRotation: Qt.vector3d(-8, 200, 0); brightness: 0.9; color: "#b9e8e4" }

        // sàn nhận bóng + lưới không gian
        Model {
            source: "#Rectangle"
            y: -0.4
            eulerRotation.x: -90
            scale: Qt.vector3d(300, 300, 1)
            receivesShadows: true
            castsShadows: false
            materials: PrincipledMaterial { baseColor: Theme.surfaceDeep; roughness: 0.9; metalness: 0; opacity: 0.95
                                            alphaMode: PrincipledMaterial.Blend }
        }
        InfiniteGrid { gridInterval: 20; visible: root.renderMode !== "xray" }

        Node {
            id: modelRoot
            y: root.groundY + root.explodeLift
            Repeater3D {
                model: root.parts
                delegate: Node {
                    id: partNode
                    required property var modelData
                    readonly property var p: modelData
                    readonly property vector3d off: root.explodeOffset(p)
                    readonly property var mx: root.motionXf(p.motion, root.animTau, root.animK)
                    readonly property var eq: root.eulerQ(root.partRot(p.id))
                    visible: root.partVisible(p.id)
                    pivot: Qt.vector3d(p.pivot[0], p.pivot[1], p.pivot[2])
                    position: {
                        if (!mx) return Qt.vector3d(p.pivot[0] + off.x, p.pivot[1] + off.y, p.pivot[2] + off.z)
                        var rp = root.qrot(mx.q, p.pivot)
                        return Qt.vector3d(rp[0] + mx.t[0] + off.x, rp[1] + mx.t[1] + off.y, rp[2] + mx.t[2] + off.z)
                    }
                    rotation: {
                        var q = mx ? root.qmul(mx.q, eq) : eq
                        return Qt.quaternion(q[0], q[1], q[2], q[3])
                    }
                    Repeater3D {
                        model: partNode.p.prims
                        delegate: Node {
                            id: primNode
                            required property var modelData
                            readonly property var m: modelData.material
                            readonly property bool selected: root.vs && root.vs.selected === partNode.p.id
                            Model {
                                objectName: partNode.p.id
                                pickable: true
                                castsShadows: primNode.m.opacity > 0.9
                                receivesShadows: true
                                geometry: NexaMesh { source: primNode.modelData.key }
                                Texture { id: bcTex; source: primNode.m.baseColorMap; tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat }
                                Texture { id: nTex; source: primNode.m.normalMap; tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat }
                                materials: PrincipledMaterial {
                                    readonly property real op: root.partOpacity(partNode.p.id, primNode.m.opacity)
                                    baseColor: primNode.m.color
                                    metalness: primNode.m.metalness
                                    roughness: primNode.m.roughness
                                    baseColorMap: primNode.m.baseColorMap !== "" ? bcTex : null
                                    normalMap: primNode.m.normalMap !== "" ? nTex : null
                                    normalStrength: primNode.m.normalScale
                                    clearcoatAmount: primNode.m.clearcoat
                                    clearcoatRoughnessAmount: 0.08
                                    emissiveFactor: primNode.selected ? Qt.vector3d(0.02, 0.16, 0.22)
                                                                      : Qt.vector3d(primNode.m.emissive[0], primNode.m.emissive[1], primNode.m.emissive[2])
                                    opacity: op
                                    alphaMode: op < 0.999 ? PrincipledMaterial.Blend : PrincipledMaterial.Opaque
                                    cullMode: op < 0.999 ? Material.NoCulling : Material.BackFaceCulling
                                    depthDrawMode: op < 0.999 ? Material.NeverDepthDraw : Material.OpaqueOnlyDepthDraw
                                }
                            }
                            Model {
                                visible: root.renderMode === "wireframe"
                                geometry: NexaMesh { source: root.renderMode === "wireframe" ? "w" + primNode.modelData.key : "" }
                                materials: PrincipledMaterial { lighting: PrincipledMaterial.NoLighting; baseColor: primNode.selected ? Theme.amber : Theme.accent }
                            }
                        }
                    }
                }
            }
        }
    }

    // ---------- chuột: kéo xoay, lăn thu phóng, nhấp chọn, nhấp đúp xem chi tiết ----------
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        property point last
        property bool dragged: false
        onPressed: (m) => { last = Qt.point(m.x, m.y); dragged = false; root.forceActiveFocus() }
        onPositionChanged: (m) => {
            var dx = m.x - last.x, dy = m.y - last.y
            if (Math.abs(dx) + Math.abs(dy) > 2) dragged = true
            if (dragged) nexa3d.orbit(dx * 0.4, dy * 0.4)
            last = Qt.point(m.x, m.y)
        }
        onClicked: (m) => {
            if (dragged) return
            var r = view.pick(m.x, m.y)
            nexa3d.selectPart(r.objectHit ? r.objectHit.objectName : "")
        }
        onDoubleClicked: (m) => {
            var r = view.pick(m.x, m.y)
            if (r.objectHit) nexa3d.partAction("focus", [r.objectHit.objectName])
        }
        onWheel: (w) => nexa3d.zoomBy(w.angleDelta.y > 0 ? 1.12 : 1 / 1.12)
    }
    Keys.onEscapePressed: nexa3d.closeViewer()

    // ---------- HUD chiến thuật (thanh nhiệm vụ, cảnh báo, la bàn trục, cử chỉ, nạp/lỗi) ----------
    ModelViewerHud {
        id: hud
        anchors.fill: parent
        viewer: root
        rightInset: root.showTree ? partPanel.width + 12 : 0
    }

    ModelPartPanel {
        id: partPanel
        visible: root.showTree
        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.margins: 10; anchors.topMargin: hud.barBottom + 10
        width: 330
    }
}
