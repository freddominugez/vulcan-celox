// Gera o ícone do app (AppIcon.iconset) sem ativos externos: o chevron do prompt girado vira o V de Vulcan,
// com o cursor ao lado, sobre o grafite da interface. Uso: icon <pasta-do-iconset>

import AppKit

let canvas: CGFloat = 1024

func color(_ hex: UInt32, _ alpha: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255, alpha: alpha)
}

func draw(_ ctx: CGContext) {
    let space = CGColorSpace(name: CGColorSpace.sRGB)!
    // coordenadas de desenho de cima para baixo, como numa tela
    ctx.translateBy(x: 0, y: canvas)
    ctx.scaleBy(x: 1, y: -1)

    // corpo no grid de ícones do macOS: 824 px com cantos contínuos
    let body = CGRect(x: 100, y: 100, width: 824, height: 824)
    let shape = CGPath(roundedRect: body, cornerWidth: 186, cornerHeight: 186, transform: nil)

    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: 10), blur: 24, color: color(0x000000, 0.35))
    ctx.addPath(shape)
    ctx.setFillColor(color(0x161618))
    ctx.fillPath()
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(shape)
    ctx.clip()
    let ground = CGGradient(colorsSpace: space, colors: [color(0x2a2a2f), color(0x19191c), color(0x0f0f11)] as CFArray,
                            locations: [0, 0.55, 1])!
    ctx.drawLinearGradient(ground, start: CGPoint(x: 0, y: 100), end: CGPoint(x: 0, y: 924), options: [])
    // brasa baixa atrás do V
    let glow = CGGradient(colorsSpace: space, colors: [color(0xff4f2b, 0.26), color(0xff4f2b, 0)] as CFArray,
                          locations: [0, 1])!
    ctx.drawRadialGradient(glow, startCenter: CGPoint(x: 470, y: 600), startRadius: 0,
                           endCenter: CGPoint(x: 470, y: 600), endRadius: 420, options: [])
    ctx.restoreGState()

    // filete de luz na borda superior
    ctx.saveGState()
    ctx.addPath(CGPath(roundedRect: body.insetBy(dx: 1.5, dy: 1.5), cornerWidth: 184, cornerHeight: 184, transform: nil))
    ctx.setStrokeColor(color(0xffffff, 0.09))
    ctx.setLineWidth(3)
    ctx.strokePath()
    ctx.restoreGState()

    // o V: chevron do prompt girado para baixo
    let v = CGMutablePath()
    v.move(to: CGPoint(x: 290, y: 352))
    v.addLine(to: CGPoint(x: 462, y: 650))
    v.addLine(to: CGPoint(x: 634, y: 352))
    let stroke = v.copy(strokingWithWidth: 104, lineCap: .round, lineJoin: .round, miterLimit: 10)
    ctx.saveGState()
    ctx.addPath(stroke)
    ctx.clip()
    let ember = CGGradient(colorsSpace: space, colors: [color(0xff7a4d), color(0xff4f2b), color(0xd93b1b)] as CFArray,
                           locations: [0, 0.5, 1])!
    ctx.drawLinearGradient(ember, start: CGPoint(x: 0, y: 300), end: CGPoint(x: 0, y: 702), options: [])
    ctx.restoreGState()

    // cursor do terminal na linha de base
    let cursor = CGPath(roundedRect: CGRect(x: 664, y: 646, width: 116, height: 56), cornerWidth: 14, cornerHeight: 14, transform: nil)
    ctx.addPath(cursor)
    ctx.setFillColor(color(0xececef))
    ctx.fillPath()
}

func render(size: Int) -> Data {
    let space = CGColorSpace(name: CGColorSpace.sRGB)!
    let ctx = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0, space: space,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.interpolationQuality = .high
    ctx.setAllowsAntialiasing(true)
    ctx.scaleBy(x: CGFloat(size) / canvas, y: CGFloat(size) / canvas)
    draw(ctx)
    let rep = NSBitmapImageRep(cgImage: ctx.makeImage()!)
    return rep.representation(using: .png, properties: [:])!
}

let args = CommandLine.arguments
guard args.count == 2 else {
    FileHandle.standardError.write("uso: icon <pasta.iconset>\n".data(using: .utf8)!)
    exit(2)
}
let dir = URL(fileURLWithPath: args[1])
try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
for base in [16, 32, 128, 256, 512] {
    try render(size: base).write(to: dir.appendingPathComponent("icon_\(base)x\(base).png"))
    try render(size: base * 2).write(to: dir.appendingPathComponent("icon_\(base)x\(base)@2x.png"))
}
print("iconset: \(dir.path)")
