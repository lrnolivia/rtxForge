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
    onClosing: function(close) { if(forge.executing) {close.accepted=false; busyClose.open()} }
    pageStack.initialPage: mainPage
    globalDrawer: Kirigami.GlobalDrawer {
        objectName: "navigationDrawer"
        visible: forge.mode === "new"
        drawerOpen: forge.mode === "new"
        modal: forge.mode !== "new"; handleVisible: false; width: forge.mode === "new" ? 230 : 0
        title: "rtxForge"; titleIcon: "applications-games"
        actions: [
            Kirigami.Action { text: "Home"; icon.name: "go-home"; onTriggered: window.page = "home" },
            Kirigami.Action { text: "Game Library"; icon.name: "view-grid"; onTriggered: window.page = "library" },
            Kirigami.Action { text: "Forge"; icon.name: "applications-engineering"; onTriggered: { window.page = "packages"; forge.catalog() } },
            Kirigami.Action { text: "Settings"; icon.name: "settings-configure"; onTriggered: window.page = "settings" },
            Kirigami.Action { text: "Recovery"; icon.name: "edit-undo"; onTriggered: window.page = "recovery" }
        ]
    }
    Component {
        id: mainPage
        Kirigami.Page {
            title: ({library:"Game Library",packages:"Packages",settings:"Settings",recovery:"Recovery",home:"Home"})[window.page] || "rtxForge"
            ColumnLayout {
                anchors.fill: parent; spacing: 16
                RowLayout {
                    Layout.fillWidth: true
                    QQC2.ComboBox { model: ["Classic", "New UI"]; currentIndex: forge.mode === "new" ? 1 : 0; onActivated: forge.setMode(currentIndex ? "new" : "classic") }
                    QQC2.Button { text: "Library"; onClicked: window.page = "library" }
                    QQC2.Button { text: "Packages"; onClicked: {window.page = "packages"; forge.catalog()} }
                    QQC2.Button { text: "Settings"; onClicked: window.page = "settings" }
                    Item { Layout.fillWidth: true }
                    QQC2.BusyIndicator { running: forge.busy; visible: running }
                    QQC2.Button { text: "Cancel and restore"; visible: forge.executing; onClicked: forge.cancelOperation() }
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
                        QQC2.Button { text: "Select all"; enabled: !forge.busy; onClicked: forge.selectAll(true) }
                        QQC2.Button { text: "Clear"; enabled: !forge.busy; onClicked: forge.selectAll(false) }
                        Item { Layout.fillWidth: true }
                        QQC2.ComboBox { model: ["MFG Only", "NR Only", "NR + MFG"]; onActivated: forge.setPreference("default_profile",["mfg-only","nr-only","nr-mfg"][currentIndex]) }
                    }
                    RowLayout {
                        QQC2.ComboBox { model: ["Poster", "Wide Capsule", "List"]; currentIndex: ["posters","capsules","list"].indexOf(forge.layout); onActivated: forge.setLayout(["posters","capsules","list"][currentIndex]) }
                        QQC2.Label { text: "Games per row" }
                        QQC2.SpinBox { from: 3; to: 9; value: forge.density; onValueModified: forge.setDensity(value) }
                    }
                    GridView {
                        id: grid; visible: forge.layout !== "list"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        property int columns: forge.columns(width)
                        cellWidth: width / columns; cellHeight: (cellWidth - 16) * (forge.layout === "capsules" ? 0.47 : 1.5) + 130
                        model: forge.games
                        delegate: QQC2.Frame {
                            required property var modelData
                            x: 8; width: grid.cellWidth - 16; height: grid.cellHeight - 16
                            ColumnLayout {
                                anchors.fill: parent; spacing: 8
                                Image { source: forge.layout === "capsules" ? (modelData.capsule || modelData.poster || "") : (modelData.poster || ""); fillMode: Image.PreserveAspectCrop; Layout.fillWidth: true; Layout.fillHeight: true; clip: true }
                                QQC2.CheckBox { text: modelData.name; checked: modelData.selected; Layout.fillWidth: true; onClicked: forge.select(modelData.game,checked) }
                                QQC2.Label { text: modelData.installed ? "Using rtxForge" : "Available to review"; elide: Text.ElideRight; Layout.fillWidth: true }
                                QQC2.Button { text: "Details"; Layout.fillWidth: true; onClicked: forge.showDetails(modelData.game) }
                            }
                        }
                    }
                    ListView {
                        visible: forge.layout === "list"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        model: forge.games
                        delegate: QQC2.ItemDelegate {
                            required property var modelData
                            width: ListView.view.width; height: 72
                            contentItem: RowLayout {
                                QQC2.CheckBox { checked: modelData.selected; onClicked: forge.select(modelData.game,checked) }
                                QQC2.Label { text: modelData.name; Layout.fillWidth: true; elide: Text.ElideRight }
                                QQC2.Label { text: modelData.installed ? "Using rtxForge" : "Available" }
                                QQC2.Button { text: "Details"; onClicked: forge.showDetails(modelData.game) }
                            }
                        }
                    }
                }
                ColumnLayout {
                    visible: window.page === "settings"; Layout.fillWidth: true; Layout.fillHeight: true
                    Kirigami.Heading { text: "Settings" }
                    QQC2.Label { text: "Interface" }
                    QQC2.ComboBox { model: ["Classic", "New UI"]; currentIndex: forge.mode === "new" ? 1 : 0; onActivated: forge.setMode(currentIndex ? "new" : "classic") }
                    QQC2.Label { text: "Open to" }
                    QQC2.ComboBox { model: ["Game Library","Home"]; currentIndex: forge.startPage === "home" ? 1 : 0; onActivated: forge.setStart(currentIndex ? "home" : "library") }
                    QQC2.Label { text: "Default graphics profile" }
                    QQC2.ComboBox { model: ["MFG Only","NR Only","NR + MFG"]; onActivated: forge.setPreference("default_profile",["mfg-only","nr-only","nr-mfg"][currentIndex]) }
                    QQC2.Button { text: "Manage graphics packages"; onClicked: {window.page="packages";forge.catalog()} }
                    Item { Layout.fillHeight: true }
                }
                ColumnLayout {
                    visible: window.page === "recovery"; Layout.fillWidth: true; Layout.fillHeight: true
                    Kirigami.Heading { text: "Restore original game files" }
                    QQC2.Label { text: "Select games in your library, then review their recorded restore plan. Only owned changes are restored; unrelated files stay untouched."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    QQC2.Button { text: "Choose games"; onClicked: window.page="library" }
                    QQC2.Button { text: "Review restore for selected games"; enabled: forge.selectedCount>0 && !forge.busy; onClicked: forge.prepare("uninstall") }
                    Item { Layout.fillHeight: true }
                }
                QQC2.ScrollView {
                    id: packageScroll
                    contentWidth: availableWidth
                    visible: window.page === "packages"; Layout.fillWidth: true; Layout.fillHeight: true
                    ColumnLayout {
                        width: packageScroll.availableWidth; spacing: 16
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
                                QQC2.TextField { visible: modelData.key !== "OverrideInterpolationCount"; text: modelData.value; onTextChanged: { window.customValues[modelData.key]=text } }
                                QQC2.ComboBox { visible: modelData.key === "OverrideInterpolationCount"; model: ["Auto","Off","2×","3×","4×","5×","6×"]; currentIndex: ["auto","0","1","2","3","4","5"].indexOf(modelData.value); onActivated: window.customValues[modelData.key]=["auto","0","1","2","3","4","5"][currentIndex] }
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

    QQC2.ApplicationWindow {
        id: gameDetails; objectName: "gameDetailsWindow"; width: 860; height: 600; visible: !!forge.details.game; title: forge.details.name || "Game Details"
        onClosing: forge.closeDetails()
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 24; spacing: 16
            Kirigami.Heading { text: forge.details.name || "Game Details" }
            QQC2.Label { text: forge.details.game || ""; wrapMode: Text.Wrap; Layout.fillWidth: true }
            QQC2.Label { text: forge.details.profile || "No managed installation detected" }
            QQC2.Label { text: forge.details.blocked || "Per-game compatibility is checked before applying changes."; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                QQC2.Button { text: "Review install"; enabled: !forge.busy; onClicked: forge.prepareGame(forge.details.game,"install") }
                QQC2.Button { text: "Review repair"; enabled: !forge.busy; onClicked: forge.prepareGame(forge.details.game,"repair") }
                QQC2.Button { text: "Review restore"; enabled: !forge.busy; onClicked: forge.prepareGame(forge.details.game,"uninstall") }
            }
            Item { Layout.fillHeight: true }
        }
    }
    QQC2.Dialog {
        id: busyClose; title: "Operation in progress"; modal: true; anchors.centerIn: parent; standardButtons: QQC2.Dialog.Ok
        contentItem: QQC2.Label { text: "Wait for completion, or choose Cancel and restore before closing."; wrapMode: Text.Wrap }
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
