"""Manual decoder probe; reads a local video without accessing the POS database.

Run in separate processes for each backend so Qt's cached service selection
cannot affect the comparison. A captured frame verifies decoding, not physical
second-monitor presentation.
"""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--backend", choices=("directshow", "windowsmediafoundation"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--production-window", action="store_true")
    args = parser.parse_args()
    assert args.video.is_file()
    if not args.production_window:
        os.environ["QT_MULTIMEDIA_PREFERRED_PLUGINS"] = args.backend
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt5.QtCore import QTimer, QUrl, qInstallMessageHandler
    from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer, QVideoProbe
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    window = None
    if args.production_window:
        from frontend.desktop.modules.sales_pos.customer_display_window import CustomerDisplayWindow
        window = CustomerDisplayWindow()
        window.render_content("CART", {"TOTAL": "0.00", "ITEMS": []})
        window.render_idle_ad("VIDEO", "Prueba local", "", str(args.video.resolve()), during_sale=True)
        player, widget = window._video_player, window._video_widget
    else:
        player = QMediaPlayer()
        widget = QVideoWidget()
        player.setVideoOutput(widget)
        player.setMuted(True)
    probe = QVideoProbe()
    report = {"backend": args.backend, "frames": 0, "errors": [], "statuses": [],
              "probe_attached": probe.setSource(player), "qt_messages": [],
              "service": player.service().metaObject().className() if player.service() else None}
    qInstallMessageHandler(lambda kind, context, message: report["qt_messages"].append(message))

    def frame_received(frame):
        report["frames"] += 1
        report["frame_size"] = [frame.width(), frame.height()]

    def failed(code):
        report["errors"].append({"code": int(code), "message": player.errorString()})

    probe.videoFrameProbed.connect(frame_received)
    player.error.connect(failed)
    player.mediaStatusChanged.connect(lambda status: report["statuses"].append(int(status)))
    url = QUrl.fromLocalFile(str(args.video.resolve()))
    report["url"] = url.toString()
    if window is None:
        player.setMedia(QMediaContent(url))
        player.play()
    QTimer.singleShot(6000, app.quit)
    app.exec_()
    report.update(position_ms=player.position(), duration_ms=player.duration(),
                  video_available=player.isVideoAvailable(), state=int(player.state()))
    if window is not None:
        report["muted"] = player.isMuted()
        report["playlist_mode"] = int(player.playlist().playbackMode())
        window.render_content("PAYMENT_PENDING", {"TOTAL": "0.00"})
        report["payment_stops_video"] = player.state() == QMediaPlayer.StoppedState
        window.close()
    player.stop()
    player.setMedia(QMediaContent())
    widget.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
