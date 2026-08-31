/* peachOS top progress bar -- replaces Calamares' classic left-hand step sidebar (the stock
   Ubuntu-installer look) with a slim, centered, animated progress indicator in the style of
   macOS's own Setup Assistant: a row of dots connected by a thin track, the current step
   highlighted in peachOS's blue accent, with a single cross-fading label underneath showing
   just the current step's name (rather than cramming every step's label under every dot).

   Verified against the real Calamares QML API (io.calamares.ui / io.calamares.core) via the
   KaOS branding component's own calamares-sidebar.qml (calamares/calamares-extensions) --
   Branding.styleString / SidebarBackground / SidebarBackgroundCurrent / SidebarText /
   SidebarTextCurrent and ViewManager (usable as a Repeater model, "display" role for step
   names, currentStepIndex, rowCount()) are all real properties confirmed against that
   reference, not invented for this file.
*/
import io.calamares.ui 1.0
import io.calamares.core 1.0

import QtQuick
import QtQuick.Layouts

Rectangle {
    id: topBar
    color: Branding.styleString( Branding.SidebarBackground )
    width: parent.width
    height: 84

    property color accent: Branding.styleString( Branding.SidebarBackgroundCurrent )
    property color dim: "#48484a"

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 20
        spacing: 12

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 0

            Repeater {
                model: ViewManager

                RowLayout {
                    spacing: 0

                    Rectangle {
                        id: dot
                        width: index == ViewManager.currentStepIndex ? 12 : 8
                        height: width
                        radius: width / 2
                        color: index <= ViewManager.currentStepIndex ? topBar.accent : topBar.dim

                        Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                        Behavior on color { ColorAnimation { duration: 220 } }
                    }

                    Rectangle {
                        visible: index < ViewManager.rowCount() - 1
                        Layout.preferredWidth: 40
                        height: 2
                        color: index < ViewManager.currentStepIndex ? topBar.accent : topBar.dim

                        Behavior on color { ColorAnimation { duration: 220 } }
                    }
                }
            }
        }

        // Every step's label is stacked in the same centered spot; only the current step's
        // label is opaque, and Behavior-on-opacity cross-fades between them as
        // currentStepIndex changes -- avoids inventing an unverified "current step" property,
        // reusing only the same Repeater/model/display pattern already confirmed above.
        Item {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 260
            Layout.preferredHeight: 18

            Repeater {
                model: ViewManager

                Text {
                    anchors.centerIn: parent
                    text: display
                    color: Branding.styleString( Branding.SidebarText )
                    font.pointSize: 10
                    font.letterSpacing: 0.3
                    opacity: index == ViewManager.currentStepIndex ? 1 : 0

                    Behavior on opacity { NumberAnimation { duration: 200 } }
                }
            }
        }
    }
}
