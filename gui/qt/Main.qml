import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: window
    property string artworkRole: "poster"
    property string artworkGame: ""
    property string chosenArtworkRole: "poster"
    readonly property color brandAccent: "#76b900"
    width: 1280; height: 820; minimumWidth: 760; minimumHeight: 580
    visible: true; title: "rtxForge"
    property string page: forge.startPage
    onPageChanged: { if (page === "settings") forge.refreshSteamProfiles() }
    property var customValues: ({})
    property bool packageTrusted: false
    onClosing: function(close) { if(forge.executing) {close.accepted=false; busyClose.open()} }
    pageStack.initialPage: mainPage
    globalDrawer: Kirigami.GlobalDrawer {
        objectName: "navigationDrawer"
        visible: forge.mode === "new"
        drawerOpen: forge.mode === "new"
        modal: forge.mode !== "new"; handleVisible: false; width: forge.mode === "new" ? 230 : 0
        title: "rtxForge"; titleIcon: forge.brandIcon
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
                    visible: window.page === "library"; Layout.fillWidth: true; Layout.fillHeight: true; spacing: 18
                    RowLayout {
                        Layout.fillWidth: true; spacing: 18
                        Image { source: forge.brandIcon; fillMode: Image.PreserveAspectFit; Layout.preferredWidth: 96; Layout.preferredHeight: 96 }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            QQC2.Label { text: "rtxForge"; font.family: "Bakbak One"; font.pixelSize: 32; color: Kirigami.Theme.textColor }
                            QQC2.Label { text: forge.games.length + " games · " + forge.configuredCount + " configured"; color: Kirigami.Theme.textColor; opacity: 0.8 }
                            QQC2.Label { visible: forge.demo; text: "Preview mode · no game writes"; font: Kirigami.Theme.smallFont; color: Kirigami.Theme.textColor; opacity: 0.7 }
                        }
                        QQC2.Button { text: "Install selected"; icon.name: "download"; enabled: forge.selectedCount > 0 && !forge.busy; palette.button: window.brandAccent; palette.buttonText: "#111111"; onClicked: forge.prepare("install") }
                        QQC2.Button { text: "Restore selected"; icon.name: "edit-undo"; enabled: forge.selectedCount > 0 && !forge.busy; onClicked: forge.prepare("uninstall") }
                    }
                    QQC2.Pane {
                        Layout.fillWidth: true; padding: 16
                        background: Rectangle { radius: Kirigami.Units.cornerRadius; color: Kirigami.Theme.alternateBackgroundColor }
                        contentItem: RowLayout {
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 2
                                QQC2.Label { text: "Features"; font.bold: true }
                                QQC2.Label { text: "Native NVIDIA frame generation and Neural Rendering"; font: Kirigami.Theme.smallFont; color: Kirigami.Theme.textColor; opacity: 0.75; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                            Repeater {
                                model: [{key:"nr-only",caption:"NR only"},{key:"mfg-only",caption:"MFG only"},{key:"nr-mfg",caption:"NR + MFG"}]
                                QQC2.Button { required property var modelData; text: modelData.caption; checkable: true; checked: forge.profile === modelData.key; enabled: !forge.busy; onClicked: forge.setPreference("default_profile",modelData.key) }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Kirigami.SearchField { Layout.fillWidth: true; placeholderText: "Search library"; onTextChanged: forge.setQuery(text) }
                        Repeater {
                            model: [{key:"available",caption:"Available"},{key:"installed",caption:"Installed"},{key:"all",caption:"All"}]
                            QQC2.ToolButton { required property var modelData; text: modelData.caption; checkable: true; checked: forge.filter === modelData.key; onClicked: forge.setFilter(modelData.key) }
                        }
                        Kirigami.Separator { Layout.preferredHeight: 24 }
                        Repeater {
                            model: [{key:"posters",caption:"Posters",icon:"view-list-icons"},{key:"capsules",caption:"Wide capsules",icon:"view-preview"},{key:"list",caption:"List",icon:"view-list-details"}]
                            QQC2.ToolButton { required property var modelData; text: modelData.caption; icon.name: modelData.icon; display: QQC2.AbstractButton.IconOnly; checkable: true; checked: forge.layout === modelData.key; QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered; onClicked: forge.setLayout(modelData.key) }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        QQC2.Label { text: forge.selectedCount + " selected"; font: Kirigami.Theme.smallFont }
                        Item { Layout.fillWidth: true }
                        QQC2.Label { text: "Games across"; font: Kirigami.Theme.smallFont }
                        QQC2.SpinBox { from: 3; to: 9; value: forge.density; onValueModified: forge.setDensity(value) }
                        QQC2.Button { text: "Select all"; icon.name: "edit-select-all"; enabled: !forge.busy; onClicked: forge.selectAll(true) }
                        QQC2.Button { text: "Clear"; enabled: forge.selectedCount > 0 && !forge.busy; onClicked: forge.selectAll(false) }
                    }
                    GridView {
                        id: grid; visible: forge.layout !== "list"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        property int columns: forge.columns(width)
                        cellWidth: width / columns; cellHeight: (cellWidth - 16) * (forge.layout === "capsules" ? 0.47 : 1.5) + 64
                        model: forge.games
                        QQC2.ScrollBar.vertical: QQC2.ScrollBar {}
                        delegate: QQC2.ItemDelegate {
                            id: gameCard; required property var modelData
                            x: 8; width: grid.cellWidth - 16; height: grid.cellHeight - 16; padding: 0
                            hoverEnabled: true; Accessible.name: modelData.name
                            onClicked: forge.select(modelData.game,!modelData.selected)
                            onDoubleClicked: forge.showDetails(modelData.game)
                            Keys.onReturnPressed: forge.showDetails(modelData.game)
                            background: Item {}
                            contentItem: ColumnLayout {
                                spacing: 7
                                Item {
                                    Layout.fillWidth: true; Layout.fillHeight: true
                                    Rectangle {
                                        anchors.fill: parent; radius: 12
                                        Image {
                                            anchors.fill: parent; anchors.margins: 4; asynchronous: false; fillMode: Image.PreserveAspectCrop
                                            source: forge.layout === "capsules" ? (gameCard.modelData.capsule || gameCard.modelData.poster || "") : (gameCard.modelData.poster || "")
                                        }
                                        color: Kirigami.Theme.alternateBackgroundColor
                                        border.width: gameCard.modelData.selected || gameCard.activeFocus ? 3 : 0
                                        border.color: gameCard.activeFocus ? Kirigami.Theme.focusColor : (gameCard.modelData.accent || window.brandAccent)
                                    }
                                    QQC2.CheckBox { anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 8; visible: checked || gameCard.hovered || gameCard.activeFocus; checked: gameCard.modelData.selected; enabled: !forge.busy; Accessible.name: "Select " + gameCard.modelData.name; onClicked: forge.select(gameCard.modelData.game,checked) }
                                }
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 4
                                    QQC2.Label { text: gameCard.modelData.name; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                    QQC2.ToolButton { text: "Game details"; icon.name: "configure"; display: QQC2.AbstractButton.IconOnly; QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered; onClicked: forge.showDetails(gameCard.modelData.game) }
                                }
                                QQC2.Label { text: gameCard.modelData.installed ? (gameCard.modelData.profile || "Configured") : "Available"; font: Kirigami.Theme.smallFont; color: Kirigami.Theme.textColor; opacity: 0.7; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                        }
                    }
                    ListView {
                        visible: forge.layout === "list"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        model: forge.games; spacing: 1
                        QQC2.ScrollBar.vertical: QQC2.ScrollBar {}
                        delegate: QQC2.ItemDelegate {
                            required property var modelData
                            width: ListView.view.width; height: 78; highlighted: modelData.selected
                            onClicked: forge.showDetails(modelData.game)
                            contentItem: RowLayout {
                                spacing: 14
                                QQC2.CheckBox { checked: modelData.selected; Accessible.name: "Select " + modelData.name; onClicked: forge.select(modelData.game,checked) }
                                Image { source: modelData.capsule || modelData.poster || ""; fillMode: Image.PreserveAspectCrop; Layout.preferredWidth: 100; Layout.preferredHeight: 52 }
                                QQC2.Label { text: modelData.name; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                                QQC2.Label { text: modelData.installed ? (modelData.profile || "Configured") : "Available"; font: Kirigami.Theme.smallFont }
                                QQC2.ToolButton { text: "Game details"; icon.name: "arrow-right"; display: QQC2.AbstractButton.IconOnly; onClicked: forge.showDetails(modelData.game) }
                            }
                        }
                    }
                    QQC2.Label { visible: forge.games.length === 0; text: "No games match your filters."; Layout.alignment: Qt.AlignHCenter; Layout.fillHeight: true; verticalAlignment: Text.AlignVCenter }
                }
                ColumnLayout {
                    visible: window.page === "settings"; Layout.fillWidth: true; Layout.fillHeight: true
                    Kirigami.Heading { text: "Settings" }
                    QQC2.Label { text: "Interface" }
                    QQC2.ComboBox { model: ["Classic", "New UI"]; currentIndex: forge.mode === "new" ? 1 : 0; onActivated: forge.setMode(currentIndex ? "new" : "classic") }
                    QQC2.Label { text: "Open to" }
                    QQC2.ComboBox { model: ["Game Library","Home"]; currentIndex: forge.startPage === "home" ? 1 : 0; onActivated: forge.setStart(currentIndex ? "home" : "library") }
                    QQC2.Label { text: "Default graphics profile" }
                    QQC2.ComboBox { model: ["MFG Only","NR Only","NR + MFG"]; currentIndex: ["mfg-only","nr-only","nr-mfg"].indexOf(forge.profile); onActivated: forge.setPreference("default_profile",["mfg-only","nr-only","nr-mfg"][currentIndex]) }
                    QQC2.Label { text: "Steam artwork account" }
                    RowLayout {
                        Layout.fillWidth: true
                        QQC2.ComboBox { Layout.fillWidth: true; model: ["Automatic when unambiguous"].concat(forge.steamProfiles.map(function(p) { return p.label })); currentIndex: forge.steamProfileIndex; displayText: currentIndex < 0 ? "Selected account unavailable — refresh" : currentText; enabled: !forge.busy; onActivated: forge.setSteamProfile(currentIndex) }
                        QQC2.ToolButton { text: "Refresh Steam accounts"; icon.name: "view-refresh"; display: QQC2.AbstractButton.IconOnly; enabled: !forge.busy; onClicked: forge.refreshSteamProfiles(); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
                    }
                    QQC2.Label { text: "Only this local account's artwork is updated. Existing backups are retained."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    QQC2.Button { text: "Sync artwork to Steam"; enabled: !forge.busy; onClicked: forge.syncArtwork("") }
                    QQC2.Button { text: "Add rtxForge to Steam"; enabled: !forge.busy; onClicked: forge.addToSteam() }
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

    QQC2.Dialog {
        id: gameDetails; parent: QQC2.Overlay.overlay; anchors.centerIn: parent; modal: true; objectName: "gameDetailsWindow"; width: Math.min(860,window.width-48); height: Math.min(660,window.height-48); visible: !!forge.details.game; title: forge.details.name || "Game Details"
        onClosed: forge.closeDetails()
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 24; spacing: 16
            Kirigami.Heading { text: forge.details.name || "Game Details" }
            QQC2.Label { text: forge.details.game || ""; wrapMode: Text.Wrap; Layout.fillWidth: true }
            QQC2.Label { text: forge.details.profile || "No managed installation detected" }
            QQC2.Label { text: forge.details.blocked || "Per-game compatibility is checked before applying changes."; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                QQC2.Button { text: "Play"; enabled: !forge.busy; onClicked: forge.playGame(forge.details.game) }
                QQC2.Button { text: "Review install"; enabled: !forge.busy; onClicked: forge.prepareGame(forge.details.game,"install") }
                QQC2.Button { text: "Review repair"; enabled: !forge.busy; onClicked: forge.prepareGame(forge.details.game,"repair") }
                QQC2.Button { text: "Review restore"; enabled: !forge.busy; onClicked: forge.prepareGame(forge.details.game,"uninstall") }
            }
            RowLayout {
                QQC2.Button { text: "Sync artwork to Steam"; enabled: !forge.busy; onClicked: forge.syncArtwork(forge.details.game) }
                QQC2.ComboBox { id: artRole; model: ["Poster", "Wide capsule", "Hero"]; onActivated: window.artworkRole=["poster","capsule","hero"][currentIndex] }
                QQC2.Button { text: "Choose image…"; enabled: !forge.busy; onClicked: { window.artworkGame=forge.details.game; window.chosenArtworkRole=window.artworkRole; artworkChooser.open() } }
                QQC2.Button { text: "Reset artwork"; enabled: !forge.busy; onClicked: forge.resetArtwork(forge.details.game,window.artworkRole) }
            }
            Item { Layout.fillHeight: true }
        }
    }
    FileDialog { id: artworkChooser; title: "Choose game artwork"; nameFilters: ["Images (*.png *.jpg *.jpeg)"]; onAccepted: forge.chooseArtwork(window.artworkGame,window.chosenArtworkRole,selectedFile.toString()) }
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
