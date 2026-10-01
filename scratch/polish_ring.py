from pathlib import Path
p = Path("nexa/ui/qml/StatsRing.qml")
s = p.read_text(encoding="utf-8")
old_start = s.index("            var cx = width / 2, cy = height / 2, R = ring.radius, w = Math.max(3, ring.s * 0.011)")
old_end = s.index("    // ---- nhãn số liệu")
new = '''            var cx = width / 2, cy = height / 2, R = ring.radius, w = Math.max(3, ring.s * 0.009)
            var ac = ring.accent
            // vòng nền mảnh nối liền 4 cung
            ctx.lineWidth = 1
            ctx.strokeStyle = Qt.rgba(ac.r, ac.g, ac.b, 0.14)
            ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke()
            ctx.lineCap = "round"
            for (var i = 0; i < ring.gaugeDefs.length; i++) {
                var g = ring.gaugeDefs[i], v = ring.valueOf(g.key)
                var a0 = (g.mid - ring.span / 2) * Math.PI / 180, a1 = (g.mid + ring.span / 2) * Math.PI / 180
                // rãnh
                ctx.lineWidth = w
                ctx.strokeStyle = Qt.rgba(ac.r, ac.g, ac.b, 0.10)
                ctx.beginPath(); ctx.arc(cx, cy, R, a0, a1); ctx.stroke()
                // mức đo + quầng sáng
                if (v > 0.003) {
                    var c = Qt.color(Theme.loadColor(v)), a = a0 + (a1 - a0) * v
                    ctx.lineWidth = w * 2.6
                    ctx.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.12)
                    ctx.beginPath(); ctx.arc(cx, cy, R, a0, a); ctx.stroke()
                    ctx.lineWidth = w
                    ctx.strokeStyle = Qt.rgba(c.r, c.g, c.b, 0.95)
                    ctx.beginPath(); ctx.arc(cx, cy, R, a0, a); ctx.stroke()
                    // chấm đầu mức
                    ctx.fillStyle = "white"
                    ctx.beginPath(); ctx.arc(cx + Math.cos(a) * R, cy + Math.sin(a) * R, w * 0.55, 0, Math.PI * 2); ctx.fill()
                }
            }
        }
    }

'''
s = s[:old_start] + new + s[old_end:]
s = s.replace('font.pixelSize: Math.max(12, ring.s * 0.032); font.bold: true }', 'font.pixelSize: Math.max(13, ring.s * 0.036); font.bold: true }')
p.write_text(s, encoding="utf-8")
print("ok")
