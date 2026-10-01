import QtQuick
import QtQuick.Controls
import QtWebEngine

// Trang HTML chạy thử hiện NGAY TRONG NEXA (QtWebEngine). console.log / lỗi JavaScript của trang → bảng kết quả.
// Nạp qua Loader: bản dựng không có QtWebEngine thì CodePanel hiện nút "Mở trong trình duyệt" thay thế.
Rectangle {
    id: root
    property url url
    readonly property alias title: web.title
    readonly property alias loading: web.loading
    readonly property alias progress: web.loadProgress
    function reload() { web.reload() }
    function scrollBy(dy) { web.runJavaScript("window.scrollBy(0," + Math.round(dy) + ")") }   // cử chỉ hai ngón
    color: "white"

    WebEngineView {
        id: web
        anchors.fill: parent
        url: root.url
        settings.localContentCanAccessFileUrls: true
        settings.localContentCanAccessRemoteUrls: true      // trang hay dùng font/thư viện từ CDN
        settings.focusOnNavigationEnabled: false             // không giật bàn phím khỏi ô nhập của NEXA
        onJavaScriptConsoleMessage: (level, message, lineNumber, sourceID) =>
            nexaCode.webConsole(level, message, lineNumber, sourceID)
        onNewWindowRequested: (request) => Qt.openUrlExternally(request.requestedUrl)
        onLoadingChanged: (info) => {
            if (info.status === WebEngineView.LoadFailedStatus)
                nexaCode.webConsole(2, "Không tải được trang: " + info.errorString, 0, "")
        }
    }
}
