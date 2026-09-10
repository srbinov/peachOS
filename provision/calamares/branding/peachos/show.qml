import QtQuick 2.0;
import calamares.slideshow 1.0;

// Deliberately nothing: a black field with the peachOS Savannah mark and one
// line of text while the install runs. No marketing slides, no wallpaper, no
// timer.
Presentation
{
    id: presentation

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#000000"
        }

        Column {
            anchors.centerIn: parent
            spacing: 22

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "logo.png"
                width: 88
                height: 88
                fillMode: Image.PreserveAspectFit
                smooth: true
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Installing peachOS"
                color: "#f5f5f7"
                font.family: "SF Pro Display"
                font.pixelSize: 22
            }
        }
    }
}
