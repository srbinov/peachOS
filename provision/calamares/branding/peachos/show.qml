import QtQuick 2.0;
import calamares.slideshow 1.0;

// Text-over-background slides rather than fully pre-baked marketing images (the convention
// most Calamares themes use, e.g. Kubuntu's own show.qml) -- keeps this maintainable without
// needing a full graphic-design pass just to update copy, and reuses real peachOS assets
// (the Nectar wallpaper, the peach mark) already shipped elsewhere in this repo instead of
// inventing new ones.
Presentation
{
    id: presentation

    Timer {
        interval: 8000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Image {
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            source: "slide-bg.png"
        }
        Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.35 }
        Column {
            anchors.centerIn: parent
            width: parent.masterWidth * 0.7
            spacing: 18
            Text {
                width: parent.width
                text: "Welcome to peachOS"
                color: "#FFFFFF"
                font.pixelSize: 42
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
            Text {
                width: parent.width
                text: "A familiar, beautiful desktop, built on real Linux underneath."
                color: "#EDEDED"
                font.pixelSize: 20
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }

    Slide {
        Image {
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            source: "slide-bg.png"
        }
        Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.35 }
        Column {
            anchors.centerIn: parent
            width: parent.masterWidth * 0.7
            spacing: 18
            Text {
                width: parent.width
                text: "Everything You Need, Built In"
                color: "#FFFFFF"
                font.pixelSize: 42
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
            Text {
                width: parent.width
                text: "LibreOffice, a curated app library with real macOS-style icons, and a Control Center that just works -- all ready the moment setup finishes."
                color: "#EDEDED"
                font.pixelSize: 20
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }

    Slide {
        Image {
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            source: "slide-bg.png"
        }
        Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.35 }
        Column {
            anchors.centerIn: parent
            width: parent.masterWidth * 0.7
            spacing: 18
            Text {
                width: parent.width
                text: "Almost There"
                color: "#FFFFFF"
                font.pixelSize: 42
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
            Text {
                width: parent.width
                text: "Sit back while peachOS finishes setting itself up on this machine."
                color: "#EDEDED"
                font.pixelSize: 20
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }
}
