// NEXA mirrored-core command center: shared HUD palette.
.pragma library

var bg = "#020811"
var surface = "#081b2a"
var surfaceRaised = "#12364a"
var surfaceDeep = "#04111d"
var border = "#27536a"
var borderStrong = "#4c8ca5"
var textPrimary = "#e0f6ff"
var textSecondary = "#a2c4d4"
var textMuted = "#779eaf"
var accent = "#4ddcf4"
var blue = "#6db5e4"
var silver = "#b5c7f2"
var amber = "#e6b77a"
var success = "#67debe"
var danger = "#ff697f"
var panelGlass = "#d9071726"
var inputGlass = "#e6061523"
var radius = 8
var font = "Segoe UI"
var mono = "Consolas"
var motion = 240

var STATE_COLORS = {
    "INITIALIZING": textMuted,
    "STANDBY": blue,
    "WAKING": textPrimary,
    "LISTENING": accent,
    "THINKING": silver,
    "EXECUTING": blue,
    "SPEAKING": "#b4e9df",
    "CONFIRMING": amber,
    "ERROR": danger
}
function stateColor(state) { return STATE_COLORS[state] || accent }
function loadColor(v) { return v >= 0.85 ? danger : v >= 0.6 ? amber : accent }
