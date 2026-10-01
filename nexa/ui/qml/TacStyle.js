// Compatibility names for the shared SENTINEL design system.
.pragma library
.import "Theme.js" as Theme
var ice = Theme.accent
var iceDim = Theme.textMuted
var amber = Theme.amber
var hazard = Theme.danger
var ok = Theme.success
var violet = Theme.silver
var text = Theme.textPrimary
var textDim = Theme.textSecondary
var mute = Theme.textMuted
var fill = Theme.panelGlass
var fillDeep = Theme.inputGlass
var line = Theme.border
var mono = Theme.mono
function tacFont(families) { return Theme.font }
function iconFont(families) { return families.indexOf("Segoe Fluent Icons") >= 0 ? "Segoe Fluent Icons" : "Segoe MDL2 Assets" }
function glyph(code) { return String.fromCharCode(code) }
