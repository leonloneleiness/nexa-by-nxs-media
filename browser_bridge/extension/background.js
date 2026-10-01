// NEXA Bridge — service worker.
// Kết nối Native Messaging tới host "com.nxsmedia.nexa_bridge" (browser_bridge/native_host.py),
// chuyển tiếp lệnh pause/play/state từ NEXA tới đúng tab YouTube và báo trạng thái ngược lại.
"use strict";

const HOST = "com.nxsmedia.nexa_bridge";
const tabState = new Map(); // tabId -> {videoId, title, paused, url}
let port = null;
let nexaConnected = false;
let reconnectTimer = null;
let lastError = "";

function browserName() {
  const brands = ((navigator.userAgentData && navigator.userAgentData.brands) || []).map((b) => b.brand);
  if (brands.some((b) => /Edge/i.test(b))) return "Edge";
  if (brands.some((b) => /Opera/i.test(b))) return "Opera";
  if (brands.some((b) => /Brave/i.test(b))) return "Brave";
  return "Chrome";
}

function post(msg) {
  if (!port) return false;
  try {
    port.postMessage(msg);
    return true;
  } catch (e) {
    return false;
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, 5000);
}

function connect() {
  if (port) return;
  try {
    port = chrome.runtime.connectNative(HOST);
  } catch (e) {
    lastError = String(e);
    port = null;
    scheduleReconnect();
    return;
  }
  port.onMessage.addListener(onNativeMessage);
  port.onDisconnect.addListener(() => {
    lastError = (chrome.runtime.lastError && chrome.runtime.lastError.message) || "Native host đã ngắt";
    port = null;
    nexaConnected = false;
    scheduleReconnect();
  });
  post({ type: "hello", browser: browserName(), version: chrome.runtime.getManifest().version });
}

async function listTabs() {
  const tabs = await chrome.tabs.query({ url: "https://www.youtube.com/*" });
  return tabs.map((t) => {
    const s = tabState.get(t.id) || {};
    return { tabId: t.id, videoId: s.videoId || "", title: s.title || t.title || "", paused: s.paused ?? null, url: t.url || "" };
  });
}

async function sendToTab(tabId, payload) {
  try {
    return await chrome.tabs.sendMessage(tabId, payload);
  } catch (e) {
    return null;
  }
}

async function onNativeMessage(msg) {
  if (!msg || typeof msg !== "object") return;
  if (msg.type === "nexa_status") {
    nexaConnected = !!msg.connected;
    if (nexaConnected) post({ type: "hello", browser: browserName(), version: chrome.runtime.getManifest().version });
    return;
  }
  if (msg.type === "list") {
    post({ type: "tabs", reqId: msg.reqId, tabs: await listTabs() });
    return;
  }
  if (msg.type === "command") {
    const tabId = Number(msg.tabId);
    const action = String(msg.action || "");
    if (!["pause", "play", "state"].includes(action)) {
      post({ type: "result", reqId: msg.reqId, ok: false, error: "bad_action" });
      return;
    }
    const res = await sendToTab(tabId, { type: "nexa_command", action, videoId: String(msg.videoId || "") });
    if (!res) {
      post({ type: "result", reqId: msg.reqId, ok: false, error: "tab_gone" });
      return;
    }
    if (res.state) tabState.set(tabId, res.state);
    post({ type: "result", reqId: msg.reqId, ok: !!res.ok, error: res.error || "", state: res.state || null });
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return false;
  // Tin từ content script (chỉ nhận từ tab YouTube thật).
  if (msg.type === "tab_update" && sender.tab && sender.id === chrome.runtime.id) {
    const url = sender.tab.url || "";
    if (!url.startsWith("https://www.youtube.com/")) return false;
    tabState.set(sender.tab.id, msg.tab);
    post({ type: "tab_update", tab: Object.assign({ tabId: sender.tab.id }, msg.tab) });
    return false;
  }
  // Tin từ popup của chính extension.
  if (sender.id !== chrome.runtime.id || sender.tab) return false;
  if (msg.type === "popup_status") {
    listTabs().then((tabs) =>
      sendResponse({ hostConnected: !!port, nexaConnected, browser: browserName(), lastError, tabs })
    );
    return true;
  }
  if (msg.type === "popup_bind") {
    const tabId = Number(msg.tabId);
    sendToTab(tabId, { type: "nexa_command", action: "state", videoId: "" }).then((res) => {
      if (!res || !res.state || !res.state.videoId) {
        sendResponse({ ok: false, error: "Tab này chưa mở video YouTube." });
        return;
      }
      tabState.set(tabId, res.state);
      const sent = post({ type: "bind", tab: Object.assign({ tabId }, res.state) });
      sendResponse({ ok: sent && nexaConnected, error: sent ? (nexaConnected ? "" : "NEXA chưa chạy.") : "Chưa kết nối native host." });
    });
    return true;
  }
  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabState.delete(tabId)) post({ type: "tab_closed", tabId });
});

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
