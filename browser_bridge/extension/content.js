// NEXA Bridge — content script chạy trên https://www.youtube.com/*
// Chỉ đọc trạng thái phần tử <video> chính và gọi pause()/play() khi nhận lệnh từ background.
// Không đọc cookie, không gửi nội dung trang đi đâu ngoài videoId/tiêu đề/trạng thái phát.
(() => {
  "use strict";

  function currentVideoId() {
    try {
      const u = new URL(location.href);
      if (u.pathname === "/watch") return u.searchParams.get("v") || "";
      const m = u.pathname.match(/^\/(shorts|live)\/([\w-]{6,})/);
      return m ? m[2] : "";
    } catch (e) {
      return "";
    }
  }

  function mainVideo() {
    return (
      document.querySelector("#movie_player video.html5-main-video") ||
      document.querySelector("video.html5-main-video") ||
      document.querySelector("#movie_player video")
    );
  }

  function snapshot() {
    const v = mainVideo();
    return {
      videoId: currentVideoId(),
      title: (document.title || "").replace(/\s*-\s*YouTube\s*$/, ""),
      paused: v ? v.paused : null,
      hasVideo: !!v,
      url: location.href,
    };
  }

  let lastSig = "";
  function report(force) {
    const s = snapshot();
    const sig = JSON.stringify([s.videoId, s.paused, s.title]);
    if (!force && sig === lastSig) return;
    lastSig = sig;
    try {
      chrome.runtime.sendMessage({ type: "tab_update", tab: s }).catch(() => {});
    } catch (e) {
      // Extension vừa được tải lại: context cũ không còn hiệu lực.
    }
  }

  document.addEventListener("play", () => report(false), true);
  document.addEventListener("pause", () => report(false), true);
  window.addEventListener("yt-navigate-finish", () => setTimeout(() => report(true), 300));
  setInterval(() => report(false), 2000);

  function reply(sendResponse, ok, error) {
    sendResponse({ ok, error: error || "", state: snapshot() });
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== "nexa_command") return false;
    const s = snapshot();
    const v = mainVideo();
    if (!s.videoId || !v) {
      reply(sendResponse, false, "no_video");
      return false;
    }
    if (msg.videoId && msg.videoId !== s.videoId) {
      reply(sendResponse, false, "video_changed");
      return false;
    }
    if (msg.action === "state") {
      reply(sendResponse, true);
      return false;
    }
    if (msg.action === "pause") {
      if (!v.paused) v.pause();
      setTimeout(() => reply(sendResponse, v.paused, v.paused ? "" : "not_paused"), 150);
      return true;
    }
    if (msg.action === "play") {
      if (!v.paused) {
        reply(sendResponse, true);
        return false;
      }
      Promise.resolve(v.play())
        .then(() => setTimeout(() => reply(sendResponse, !v.paused, v.paused ? "not_playing" : ""), 150))
        .catch((err) => reply(sendResponse, false, (err && err.name) || "play_failed"));
      return true;
    }
    reply(sendResponse, false, "bad_action");
    return false;
  });

  report(true);
})();
