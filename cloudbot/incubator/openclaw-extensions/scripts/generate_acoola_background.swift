import AppKit
import Foundation

let fm = FileManager.default
let cwd = URL(fileURLWithPath: fm.currentDirectoryPath)
let inputURL = cwd.appendingPathComponent("dark_final.png")
let outputURL = cwd.appendingPathComponent("acoola_background_premium_v2.png")

guard let inputImage = NSImage(contentsOf: inputURL) else {
    fputs("Failed to load input image: \(inputURL.path)\n", stderr)
    exit(1)
}

let width = 1920
let height = 1080
let size = NSSize(width: width, height: height)

guard let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: width,
    pixelsHigh: height,
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
) else {
    fputs("Failed to create bitmap\n", stderr)
    exit(1)
}

NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)

let canvas = NSRect(x: 0, y: 0, width: width, height: height)
inputImage.draw(in: canvas)

func fillRect(_ rect: NSRect, _ color: NSColor) {
    color.setFill()
    rect.fill()
}

func strokeRect(_ rect: NSRect, _ color: NSColor, _ lineWidth: CGFloat) {
    let path = NSBezierPath(rect: rect)
    path.lineWidth = lineWidth
    color.setStroke()
    path.stroke()
}

func drawText(_ text: String, _ rect: NSRect, font: NSFont, color: NSColor, alignment: NSTextAlignment = .left) {
    let style = NSMutableParagraphStyle()
    style.alignment = alignment
    let attrs: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: color,
        .paragraphStyle: style
    ]
    (text as NSString).draw(in: rect, withAttributes: attrs)
}

// Global dark premium overlays
fillRect(NSRect(x: 0, y: 0, width: width, height: height), NSColor(calibratedRed: 0.03, green: 0.07, blue: 0.12, alpha: 0.34))
fillRect(NSRect(x: 0, y: height - 120, width: width, height: 120), NSColor(calibratedRed: 0.02, green: 0.05, blue: 0.10, alpha: 0.44))
fillRect(NSRect(x: 0, y: 0, width: width, height: 120), NSColor(calibratedRed: 0.02, green: 0.05, blue: 0.10, alpha: 0.44))

// Left and right informational panels
fillRect(NSRect(x: 110, y: 640, width: 700, height: 320), NSColor(calibratedRed: 0.07, green: 0.14, blue: 0.24, alpha: 0.30))
fillRect(NSRect(x: 1220, y: 620, width: 590, height: 340), NSColor(calibratedRed: 0.08, green: 0.16, blue: 0.28, alpha: 0.28))
strokeRect(NSRect(x: 1240, y: 640, width: 550, height: 300), NSColor(calibratedRed: 0.52, green: 0.72, blue: 1.0, alpha: 0.26), 2)

// Outer premium frame
strokeRect(NSRect(x: 90, y: 80, width: 1740, height: 920), NSColor(calibratedRed: 0.47, green: 0.68, blue: 0.98, alpha: 0.20), 2)

// Left headline block
let bold72 = NSFont(name: "Arial-BoldMT", size: 72) ?? NSFont.boldSystemFont(ofSize: 72)
let regular40 = NSFont(name: "ArialMT", size: 40) ?? NSFont.systemFont(ofSize: 40)
let bold52 = NSFont(name: "Arial-BoldMT", size: 52) ?? NSFont.boldSystemFont(ofSize: 52)
let regular28 = NSFont(name: "ArialMT", size: 28) ?? NSFont.systemFont(ofSize: 28)
let serif116 = NSFont(name: "TimesNewRomanPSMT", size: 116) ?? NSFont.systemFont(ofSize: 116)
let bold24 = NSFont(name: "Arial-BoldMT", size: 24) ?? NSFont.boldSystemFont(ofSize: 24)

// Text in top-left
fillRect(NSRect(x: 140, y: 648, width: 380, height: 2), NSColor(calibratedWhite: 0.9, alpha: 0.7))
drawText("Acoola Team", NSRect(x: 138, y: 810, width: 700, height: 120), font: bold72, color: NSColor(calibratedWhite: 1.0, alpha: 0.97))
drawText("Digital meetings backdrop", NSRect(x: 142, y: 742, width: 700, height: 80), font: regular40, color: NSColor(calibratedWhite: 1.0, alpha: 0.64))

// Top-right brand marker
drawText("ACOOLA TEAM", NSRect(x: 1360, y: 850, width: 420, height: 80), font: bold52, color: NSColor(calibratedWhite: 1.0, alpha: 0.90), alignment: .right)
drawText("Premium online presence", NSRect(x: 1360, y: 800, width: 420, height: 60), font: regular28, color: NSColor(calibratedWhite: 1.0, alpha: 0.58), alignment: .right)

// Vertical accent on the left
let letters = ["A", "C", "O", "O", "L", "A"]
var y: CGFloat = 480
for l in letters {
    drawText(l, NSRect(x: 58, y: y, width: 40, height: 34), font: bold24, color: NSColor(calibratedRed: 0.86, green: 0.92, blue: 1.0, alpha: 0.46))
    y += 54
}

// Big subtle bottom watermark
drawText("ACOOLA TEAM DIGITAL STUDIO", NSRect(x: 110, y: 70, width: 1700, height: 130), font: serif116, color: NSColor(calibratedWhite: 1.0, alpha: 0.12))

NSGraphicsContext.restoreGraphicsState()

guard let pngData = rep.representation(using: .png, properties: [:]) else {
    fputs("Failed to encode PNG\n", stderr)
    exit(1)
}

do {
    try pngData.write(to: outputURL)
    print("Generated: \(outputURL.path)")
} catch {
    fputs("Failed to write output: \(error)\n", stderr)
    exit(1)
}
