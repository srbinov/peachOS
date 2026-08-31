/* peachOS bottom navigation bar -- Back as a subtle ghost button, Continue as a filled blue
   pill (macOS Setup Assistant convention: both primary actions bottom-right), Cancel as a
   quiet text link bottom-left, About/Debug tucked in the far corner. Real animation via QML
   Behavior on color/scale (hover and press feedback), not just static QSS -- Qt Widgets
   stylesheets can't do that, which is exactly why this panel is QML instead.

   Verified against the real Calamares QML API via the KaOS branding component's own
   calamares-navigation.qml (calamares/calamares-extensions) -- every ViewManager/Branding/
   debug property and method used below (backEnabled, nextEnabled, backAndNextVisible, back(),
   next(), quitEnabled, quitVisible, quitTooltip, quit(), debug.enabled, debug.toggle(),
   Branding.styleString/imagePath/SidebarBackground/SidebarBackgroundCurrent/SidebarText/
   SidebarTextCurrent/ProductLogo) is confirmed against that reference, not invented.
*/
import io.calamares.ui 1.0
import io.calamares.core 1.0

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: navBar
    color: Branding.styleString( Branding.SidebarBackground )
    width: parent.width
    height: 86

    property color accent: Branding.styleString( Branding.SidebarBackgroundCurrent )
    property color textPrimary: Branding.styleString( Branding.SidebarText )
    property color textDim: "#8e8e93"

    Rectangle {
        // Hairline separating the nav bar from the page content above it.
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: "#3a3a3c"
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 28
        anchors.rightMargin: 28
        spacing: 16

        // Cancel -- quiet text link, bottom-left.
        Text {
            id: cancelText
            text: qsTr("Cancel")
            color: mouseCancel.containsMouse ? navBar.textPrimary : navBar.textDim
            font.pointSize: 10
            visible: ViewManager.quitVisible && ( ViewManager.currentStepIndex < ViewManager.rowCount() - 1 )
            enabled: ViewManager.quitEnabled

            Behavior on color { ColorAnimation { duration: 120 } }

            ToolTip {
                visible: mouseCancel.containsMouse
                timeout: 5000
                delay: 600
                text: ViewManager.quitTooltip
            }

            MouseArea {
                id: mouseCancel
                anchors.fill: parent
                anchors.margins: -8
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onClicked: { ViewManager.quit(); }
            }
        }

        // About -- small, quiet, always available.
        Text {
            text: qsTr("About")
            color: mouseAbout.containsMouse ? navBar.textPrimary : navBar.textDim
            font.pointSize: 10

            Behavior on color { ColorAnimation { duration: 120 } }

            MouseArea {
                id: mouseAbout
                anchors.fill: parent
                anchors.margins: -8
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                property variant window
                onClicked: {
                    var component = Qt.createComponent("about.qml");
                    if ( component.status === Component.Ready ) {
                        window = component.createObject();
                        window.show();
                    }
                }
            }
        }

        Text {
            text: qsTr("Debug")
            color: mouseDebug.containsMouse ? navBar.textPrimary : navBar.textDim
            font.pointSize: 10
            visible: debug.enabled

            Behavior on color { ColorAnimation { duration: 120 } }

            MouseArea {
                id: mouseDebug
                anchors.fill: parent
                anchors.margins: -8
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onClicked: debug.toggle()
            }
        }

        Item { Layout.fillWidth: true }

        // Back -- ghost button.
        Rectangle {
            id: backButton
            Layout.preferredWidth: backLabel.implicitWidth + 32
            Layout.preferredHeight: 36
            radius: 8
            color: "transparent"
            border.color: navBar.textDim
            border.width: 1
            visible: ViewManager.backAndNextVisible
            enabled: ViewManager.backEnabled
            opacity: enabled ? 1 : 0.35
            scale: mouseBack.pressed ? 0.96 : 1.0

            Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 150 } }

            Text {
                id: backLabel
                anchors.centerIn: parent
                text: qsTr("Back")
                color: navBar.textPrimary
                font.pointSize: 10
            }

            MouseArea {
                id: mouseBack
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onClicked: { ViewManager.back(); }
            }
        }

        // Continue -- filled blue pill, the primary action.
        Rectangle {
            id: nextButton
            Layout.preferredWidth: nextLabel.implicitWidth + 40
            Layout.preferredHeight: 36
            radius: 8
            color: mouseNext.containsMouse ? Qt.lighter( navBar.accent, 1.12 ) : navBar.accent
            visible: ViewManager.backAndNextVisible
            enabled: ViewManager.nextEnabled
            opacity: enabled ? 1 : 0.35
            scale: mouseNext.pressed ? 0.96 : 1.0

            Behavior on color { ColorAnimation { duration: 120 } }
            Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 150 } }

            Text {
                id: nextLabel
                anchors.centerIn: parent
                text: qsTr("Continue")
                color: "#FFFFFF"
                font.pointSize: 10
                font.bold: true
            }

            MouseArea {
                id: mouseNext
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onClicked: { ViewManager.next(); }
            }
        }
    }
}
