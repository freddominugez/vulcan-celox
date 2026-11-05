import AppKit
import UniformTypeIdentifiers

/// The native picker for each use: the folder of a new terminal, the backup folder, or the backup file to restore.
func makePickPanel(purpose: String?) -> NSOpenPanel {
    let panel = NSOpenPanel()
    let choosingFile = purpose == "restore"
    panel.canChooseDirectories = !choosingFile
    panel.canChooseFiles = choosingFile
    panel.canCreateDirectories = !choosingFile
    panel.allowsMultipleSelection = false
    switch purpose {
    case "backup":
        panel.prompt = L("Salvar aqui")
        panel.message = L("Escolha onde salvar os backups, fora da pasta de dados")
    case "restore":
        panel.prompt = L("Escolher backup")
        panel.message = L("Escolha o arquivo .zip do backup")
        panel.allowedContentTypes = [.zip]
    default:
        panel.prompt = L("Abrir terminal aqui")
        panel.message = L("Escolha a pasta onde o terminal vai abrir")
    }
    return panel
}
