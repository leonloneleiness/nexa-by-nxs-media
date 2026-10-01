"use strict";

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

async function refresh() {
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  const st = await chrome.runtime.sendMessage({ type: "popup_status" });
  const status = document.getElementById("status");
  status.textContent = "";
  const host = el("div", st.hostConnected ? "ok" : "bad",
    st.hostConnected ? "● Native host: đã kết nối" : "● Native host: chưa kết nối (chạy install_bridge.ps1)");
  const nexa = el("div", st.nexaConnected ? "ok" : "bad",
    st.nexaConnected ? "● NEXA: đang chạy" : "● NEXA: chưa chạy hoặc chưa sẵn sàng");
  status.append(host, nexa, el("div", "", "Trình duyệt: " + st.browser));
  if (!st.hostConnected && st.lastError) status.append(el("div", "bad", st.lastError));

  const list = document.getElementById("tabs");
  list.textContent = "";
  if (!st.tabs.length) list.append(el("div", "tab", "Chưa có tab YouTube nào đang mở."));
  for (const t of st.tabs) {
    const box = el("div", "tab" + (active && active.id === t.tabId ? " current" : ""));
    box.append(el("div", "title", t.title || t.url));
    const info = t.videoId ? (t.paused === true ? "Đang dừng" : t.paused === false ? "Đang phát" : "Chưa rõ") : "Không có video";
    box.append(el("div", "", info + (active && active.id === t.tabId ? " · tab hiện tại" : "")));
    const btn = el("button", "", "Gắn tab này cho NEXA");
    btn.disabled = !t.videoId || !st.nexaConnected;
    btn.addEventListener("click", async () => {
      const res = await chrome.runtime.sendMessage({ type: "popup_bind", tabId: t.tabId });
      document.getElementById("msg").textContent = res.ok ? "Đã gắn tab này cho NEXA (xem thông báo trong ứng dụng)." : ("Lỗi: " + res.error);
    });
    box.append(btn);
    list.append(box);
  }
}

refresh();
