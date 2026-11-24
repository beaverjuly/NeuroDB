// Render the user's eight-page query logic PDF into local explorer images.
// Usage: swift scripts/render_query_diagrams.swift source.pdf web/diagrams
import AppKit
import PDFKit
import Foundation

guard CommandLine.arguments.count == 3 else {
    fatalError("Usage: render_query_diagrams.swift source.pdf output_directory")
}
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let directory = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
guard let document = PDFDocument(url: input), document.pageCount == 8 else {
    fatalError("Expected an eight-page query logic PDF")
}
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
for index in 0..<document.pageCount {
    guard let page = document.page(at: index) else { fatalError("Missing page \(index + 1)") }
    let bounds = page.bounds(for: .mediaBox)
    let width: CGFloat = 1800
    let height = width * bounds.height / bounds.width
    let thumbnail = page.thumbnail(of: NSSize(width: width, height: height), for: .mediaBox)
    guard let tiff = thumbnail.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let png = bitmap.representation(using: .png, properties: [:]) else {
        fatalError("Could not render page \(index + 1)")
    }
    let output = directory.appendingPathComponent("Q\(index + 1).png")
    try png.write(to: output)
    print("Q\(index + 1) \(Int(width))x\(Int(height)) \(png.count) bytes")
    print(page.string ?? "[No extractable text]")
}
