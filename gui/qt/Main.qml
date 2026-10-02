import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: window
    width: 1280; height: 820; minimumWidth: 800; minimumHeight: 580
    visible: true; title: "rtxForge"
    property string page: forge.startPage
    property var customValues: ({})
    property bool packageTrusted: false
    pageStack.initialPage: mainPage
    globalDrawer: Kirigami.GlobalDrawer {
        visible: forge.mode === "new"
        modal: false; handleVisible: false; width: 230
        title: "rtxForge"; titleIcon: "applications-games"
        actions: [
            Kirigami.Action { text: "Home"; icon.name: "go-home"; onTriggered: window.page = "home" },
            Kirigami.Action { text: "Game Library"; icon.name: "view-grid"; onTriggered: window.page = "library" },
            Kirigami.Action { text: "Forge"; icon.name: "applications-engineering"; onTriggered: { window.page = "packages"; forge.catalog() } }
        ]
    }
    Component {
        id: mainPage
        Kirigami.Page {
            title: window.page === "library" ? "Game Library" : window.page === "packages" ? "Packages" : "Home"
            ColumnLayout {
                anchors.fill: parent; spacing: 16
                RowLayout {
                    Layout.fillWidth: true
                    QQC2.ComboBox { model: ["Classic", "New UI"]; currentIndex: forge.mode === "new" ? 1 : 0; onActivated: forge.setMode(currentIndex ? "new" : "classic") }
                    QQC2.Button { text: "Library"; onClicked: window.page = "library" }
                    QQC2.Button { text: "Packages"; onClicked: {window.page = "packages"; forge.catalog()} }
                    Item { Layout.fillWidth: true }
                    QQC2.BusyIndicator { running: forge.busy; visible: running }
                }
                Kirigami.InlineMessage { Layout.fillWidth: true; visible: forge.message.length > 0; text: forge.message }
                ColumnLayout {
                    visible: window.page === "home"; Layout.fillWidth: true; Layout.fillHeight: true
                    Kirigami.Heading { text: "Get straight to your games"; level: 1 }
                    QQC2.Label { text: forge.games.length + " games in your library" }
                    QQC2.Button { text: "Open Game Library"; onClicked: window.page = "library" }
                    QQC2.Button { text: "Choose a graphics package"; onClicked: {window.page = "packages";forge.catalog()} }
                    RowLayout {
                        QQC2.Label { text: "Open to" }
                        QQC2.ComboBox { model: ["Game Library", "Home"]; currentIndex: forge.startPage === "home" ? 1 : 0; onActivated: forge.setStart(currentIndex ? "home" : "library") }
                    }
                    Item { Layout.fillHeight: true }
                }
                ColumnLayout {
                    visible: window.page === "library"; Layout.fillWidth: true; Layout.fillHeight: true
                    RowLayout {
                        Kirigami.SearchField { id: search; Layout.fillWidth: true; placeholderText: "Search library"; onTextChanged: forge.setQuery(text) }
                        QQC2.ComboBox { model: ["All", "Installed", "Available"]; onActivated: forge.setFilter(["all","installed","available"][currentIndex]) }
                        QQC2.Button { text: "Review Install"; enabled: forge.selectedCount > 0 && !forge.busy; onClicked: forge.prepare("install") }
                        QQC2.Button { text: "Review Restore"; enabled: forge.selectedCount > 0 && !forge.busy; onClicked: forge.prepare("uninstall") }
                    }
                    RowLayout {
                        QQC2.Label { text: forge.selectedCount + " selected" }
                        Item { Layout.fillWidth: true }
                        QQC2.ComboBox { model: ["MFG Only", "NR Only", "NR + MFG"]; onActivated: forge.setPreference("default_profile",["mfg-only","nr-only","nr-mfg"][currentIndex]) }
                    }
                    GridView {
                        id: grid; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        property int columns: forge.columns(width)
                        cellWidth: width / columns; cellHeight: (cellWidth - 16) * 1.5 + 100
                        model: forge.games
                        delegate: QQC2.Frame {
                            required property var modelData
                            width: grid.cellWidth - 16; height: grid.cellHeight - 16
                            ColumnLayout {
                                anchors.fill: parent; spacing: 8
                                Image { source: modelData.poster || ""; fillMode: Image.PreserveAspectCrop; Layout.fillWidth: true; Layout.fillHeight: true; clip: true }
                                QQC2.CheckBox { text: modelData.name; checked: modelData.selected; Layout.fillWidth: true; onClicked: forge.select(modelData.game,checked) }
                                QQC2.Label { text: modelData.installed ? "Using rtxForge" : "Available to review"; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                        }
                    }
                }
                QQC2.ScrollView {
                    visible: window.page === "packages"; Layout.fillWidth: true; Layout.fillHeight: true
                    ColumnLayout {
                        width: parent.width; spacing: 16
                        Kirigami.Heading { text: "Choose your graphics package" }
                        Repeater {
                            model: forge.packages
                            delegate: QQC2.Frame {
                                required property var modelData
                                Layout.fillWidth: true
                                RowLayout {
                                    anchors.fill: parent
                                    ColumnLayout { Layout.fillWidth: true; QQC2.Label { text: modelData.name; font.bold: true } QQC2.Label { text: modelData.summary; wrapMode: Text.Wrap; Layout.fillWidth: true } }
                                    QQC2.Button { text: "Use package"; enabled: modelData.available && !forge.busy; onClicked: forge.usePackage(modelData.id) }
                                }
                            }
                        }
                        QQC2.Button { text: "Add custom package"; onClicked: chooser.open() }
                        QQC2.Label { text: forge.inspection.name || ""; font.bold: true }
                        QQC2.Label { text: forge.inspection.confidence || "" }
                        Repeater {
                            model: forge.inspection.parameters || []
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                QQC2.Label { text: modelData.label; Layout.fillWidth: true }
                                QQC2.TextField { text: modelData.value; onTextChanged: { window.customValues[modelData.key]=text } }
                            }
                        }
                        QQC2.Label { visible: !!forge.inspection.name; text: "Instructions are reference material only. Nothing in the archive is executed."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        QQC2.CheckBox { id: trust; visible: !!forge.inspection.name; checked: window.packageTrusted; onToggled: window.packageTrusted=checked; text: "I trust the source of this package" }
                        QQC2.Button { visible: !!forge.inspection.name; text: "Use reviewed package"; enabled: trust.checked && forge.inspection.family === "dlss-unlocked" && !forge.busy; onClicked: forge.useCustom(JSON.stringify(window.customValues),trust.checked) }

                    }
                }
            }
        }
    }
    FileDialog { id: chooser; title: "Choose custom ZIP package"; nameFilters: ["ZIP archives (*.zip)"]; onAccepted: { window.packageTrusted=false;window.customValues={};forge.inspect(selectedFile.toString()) } }
    QQC2.Dialog {
        id: reviewDialog; title: "Review game changes"; modal: true; anchors.centerIn: parent; width: Math.min(620,window.width-64)
        standardButtons: QQC2.Dialog.Cancel
        onRejected: forge.cancelReview()
        ColumnLayout {
            anchors.fill: parent
            Repeater { model: forge.review.rows || []; delegate: QQC2.Label { required property var modelData; text: modelData.name + " · " + modelData.detail; wrapMode: Text.Wrap; Layout.fillWidth: true } }
            Repeater { model: forge.review.blocked || []; delegate: QQC2.Label { required property var modelData; text: modelData.name + ": " + modelData.reason; wrapMode: Text.Wrap; Layout.fillWidth: true } }
            QQC2.Button { text: forge.review.demo ? "Write-disabled preview" : "Apply reviewed changes"; enabled: !forge.review.demo && !forge.busy; onClicked: {forge.apply();reviewDialog.close()} }
        }
    }
    Connections { target: forge; function onChanged() { if(forge.review.rows && forge.review.rows.length && !reviewDialog.opened) reviewDialog.open() } }
}
