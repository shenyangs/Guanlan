const DAEMON_URL = "http://127.0.0.1:19830";
const POLL_INTERVAL_MS = 900;
const PAIRING_HEADER = "x-openguanlan-pairing";
const DB_NAME = "openguanlan-bridge";
const DB_STORE = "kv";
const DB_KEY = "pairing-token";

let polling = false;
let lastHelloAt = 0;
const sessionTabs = new Map();

chrome.runtime.onInstalled.addListener(() => {
  pollOnce();
});

chrome.action.onClicked.addListener(() => {
  pollOnce();
});

setInterval(() => {
  pollOnce();
}, POLL_INTERVAL_MS);

pollOnce();

async function pollOnce() {
  if (polling) {
    return;
  }
  polling = true;
  try {
    const pairingToken = await readPairingToken();
    if (!pairingToken) {
      return;
    }
    await maybeHello(pairingToken);
    const response = await fetch(`${DAEMON_URL}/extension/task`, {
      method: "GET",
      headers: { [PAIRING_HEADER]: pairingToken }
    });
    const payload = await response.json();
    const task = payload && payload.task;
    if (task) {
      const result = await runTask(task);
      await postResult(task.id, result, pairingToken);
    }
  } catch (_error) {
    // Daemon is optional; stay quiet until the user runs `openguanlan daemon`.
  } finally {
    polling = false;
  }
}

async function maybeHello(pairingToken) {
  const now = Date.now();
  if (now - lastHelloAt < 5000) {
    return;
  }
  lastHelloAt = now;
  await fetch(`${DAEMON_URL}/extension/hello`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      [PAIRING_HEADER]: pairingToken
    },
    body: JSON.stringify({
      name: "OpenGuanlan Browser Bridge",
      version: chrome.runtime.getManifest().version,
      permissions: ["activeTab", "scripting", "tabs"],
      credential_material_access_allowed: false,
      pairing_state: "paired"
    })
  });
}

async function postResult(taskId, result, pairingToken) {
  await fetch(`${DAEMON_URL}/extension/result`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      [PAIRING_HEADER]: pairingToken
    },
    body: JSON.stringify({ task_id: taskId, result })
  });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.type) {
    return;
  }
  if (message.type === "openguanlan:get-pairing-state") {
    void readPairingToken().then((token) => sendResponse({ saved: Boolean(token) }));
    return true;
  }
  if (message.type === "openguanlan:set-pairing-token") {
    void writePairingToken(String(message.token || "")).then(() => sendResponse({ ok: true }));
    return true;
  }
});

async function runTask(task) {
  try {
    switch (task.action) {
      case "open":
        return ok(await openUrl(task));
      case "read_visible":
        return ok(await readVisible(task));
      case "state":
        return ok(await state(task));
      case "get_text":
      case "get_html":
      case "get_title":
      case "get_url":
      case "get_value":
      case "get_attributes":
        return ok(await getField(task));
      case "find":
        return ok(await find(task));
      case "extract":
        return ok(await extract(task));
      case "frames":
        return ok(await frames(task));
      case "screenshot":
        return ok(await screenshot(task));
      case "wait_text":
        return ok(await waitText(task));
      case "scroll":
        return ok(await scroll(task));
      case "back":
        return ok(await goBack(task));
      case "refresh":
        return ok(await refresh(task));
      case "tab_list":
        return ok(await tabList());
      case "tab_new":
        return ok(await tabNew(task));
      case "tab_select":
        return ok(await tabSelect(task));
      case "bind":
        return ok(await bind(task));
      case "unbind":
        return ok(await unbind(task));
      default:
        return fail("unsupported_action", `Unsupported OpenGuanlan action: ${task.action}`);
    }
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    if (message.startsWith("site_permission_required:")) {
      return fail(
        "site_permission_required",
        "Open the target tab, click the OpenGuanlan extension, and grant this current site before reading visible content."
      );
    }
    return fail("bridge_task_error", message);
  }
}

function ok(data) {
  return { ok: true, status: "ok", data };
}

function fail(code, message) {
  return { ok: false, status: "error", error_code: code, error: message };
}

async function openUrl(task) {
  const tab = await ensureTab(task, { navigate: true });
  await waitForTabComplete(tab.id, task.timeout_ms || secondsToMs(task.timeout, 30000));
  const fresh = await chrome.tabs.get(tab.id);
  return tabSummary(fresh);
}

async function readVisible(task) {
  const tab = await ensureTab(task, { navigate: true });
  await waitForTabComplete(tab.id, task.timeout_ms || secondsToMs(task.timeout, 30000));
  await ensureSitePermission(tab.url);
  return await runInTab(tab.id, collectVisiblePage, [{
    maxChars: numberOr(task.max_chars, 3000),
    minVisibleItems: numberOr(task.min_visible_items, 0),
    includeItems: true
  }]);
}

async function state(task) {
  const tab = await ensureTab(task, { navigate: false });
  await ensureSitePermission(tab.url);
  return await runInTab(tab.id, collectVisiblePage, [{
    maxChars: numberOr(task.max_chars, 3000),
    minVisibleItems: 0,
    includeItems: Boolean(task.include_items)
  }]);
}

async function getField(task) {
  const tab = await ensureTab(task, { navigate: false });
  if (task.action === "get_title") {
    await ensureSitePermission(tab.url);
    return { value: tab.title || "", title: tab.title || "", url: tab.url || "" };
  }
  if (task.action === "get_url") {
    return { value: tab.url || "", title: tab.title || "", url: tab.url || "" };
  }
  await ensureSitePermission(tab.url);
  return await runInTab(tab.id, getPageField, [{
    action: task.action,
    selector: task.selector || task.target || "",
    maxChars: numberOr(task.max_chars, 3000)
  }]);
}

async function find(task) {
  const tab = await ensureTab(task, { navigate: false });
  await ensureSitePermission(tab.url);
  return await runInTab(tab.id, findElements, [{
    css: task.css || task.selector || "",
    text: task.text || "",
    role: task.role || "",
    name: task.name || "",
    limit: numberOr(task.limit, 20),
    maxChars: numberOr(task.max_chars, 240)
  }]);
}

async function extract(task) {
  const tab = await ensureTab(task, { navigate: false });
  await ensureSitePermission(tab.url);
  return await runInTab(tab.id, extractContent, [{
    selector: task.selector || "",
    chunkSize: numberOr(task.chunk_size, 6000),
    start: numberOr(task.start, 0)
  }]);
}

async function frames(task) {
  const tab = await ensureTab(task, { navigate: false });
  await ensureSitePermission(tab.url);
  return await runInTab(tab.id, listFrames, [{}]);
}

async function screenshot(task) {
  const tab = await ensureTab(task, { navigate: false });
  await ensureSitePermission(tab.url);
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: task.format === "jpeg" ? "jpeg" : "png"
  });
  return {
    url: tab.url || "",
    title: tab.title || "",
    data_url: dataUrl,
    captured_at: Date.now() / 1000,
    visible_page_only: true
  };
}

async function waitText(task) {
  const deadline = Date.now() + (numberOr(task.timeout_ms, 0) || secondsToMs(task.timeout, 10000));
  const expected = String(task.value || "");
  const tab = await ensureTab(task, { navigate: false });
  await ensureSitePermission(tab.url);
  while (Date.now() < deadline) {
    const result = await runInTab(tab.id, pageContainsText, [expected]);
    if (result && result.found) {
      return result;
    }
    await delay(300);
  }
  throw new Error(`timeout waiting for visible text: ${expected}`);
}

async function scroll(task) {
  const tab = await ensureTab(task, { navigate: false });
  await ensureSitePermission(tab.url);
  return await runInTab(tab.id, scrollPage, [{
    direction: task.direction === "up" ? "up" : "down",
    amount: numberOr(task.amount, 800)
  }]);
}

async function goBack(task) {
  const tab = await ensureTab(task, { navigate: false });
  await chrome.tabs.goBack(tab.id);
  await waitForTabComplete(tab.id, task.timeout_ms || secondsToMs(task.timeout, 15000));
  return tabSummary(await chrome.tabs.get(tab.id));
}

async function refresh(task) {
  const tab = await ensureTab(task, { navigate: false });
  await chrome.tabs.reload(tab.id);
  await waitForTabComplete(tab.id, task.timeout_ms || secondsToMs(task.timeout, 15000));
  return tabSummary(await chrome.tabs.get(tab.id));
}

async function tabList() {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  return {
    tabs: tabs.map((tab, index) => ({
      index,
      id: String(tab.id),
      url: tab.url || "",
      title: tab.title || "",
      active: Boolean(tab.active)
    }))
  };
}

async function tabNew(task) {
  const tab = await chrome.tabs.create({ url: task.url || task.target || "about:blank", active: true });
  sessionTabs.set(task.session || "guanlan-visible", tab.id);
  await waitForTabComplete(tab.id, task.timeout_ms || secondsToMs(task.timeout, 15000));
  return tabSummary(await chrome.tabs.get(tab.id));
}

async function tabSelect(task) {
  const tabId = Number(task.target || task.tab_id || 0);
  if (!tabId) {
    throw new Error("tab_select requires a tab id target");
  }
  const tab = await chrome.tabs.update(tabId, { active: true });
  sessionTabs.set(task.session || "guanlan-visible", tabId);
  return tabSummary(tab);
}

async function bind(task) {
  const tab = await activeTab();
  sessionTabs.set(task.session || "guanlan-visible", tab.id);
  return { bound: true, session: task.session || "guanlan-visible", tab: tabSummary(tab) };
}

async function unbind(task) {
  sessionTabs.delete(task.session || "guanlan-visible");
  return { unbound: true, session: task.session || "guanlan-visible" };
}

async function ensureTab(task, options) {
  const session = task.session || "guanlan-visible";
  const stored = sessionTabs.get(session);
  if (stored) {
    try {
      const existing = await chrome.tabs.get(stored);
      if (options.navigate && task.url && existing.url !== task.url) {
        const updated = await chrome.tabs.update(existing.id, { url: task.url, active: true });
        return updated;
      }
      return existing;
    } catch (_error) {
      sessionTabs.delete(session);
    }
  }
  if (options.navigate && task.url) {
    const created = await chrome.tabs.create({ url: task.url, active: true });
    sessionTabs.set(session, created.id);
    return created;
  }
  const tab = await activeTab();
  sessionTabs.set(session, tab.id);
  return tab;
}

async function activeTab() {
  const focused = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (focused && focused[0]) {
    return focused[0];
  }
  const current = await chrome.tabs.query({ active: true, currentWindow: true });
  if (current && current[0]) {
    return current[0];
  }
  throw new Error("no active tab");
}

async function waitForTabComplete(tabId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") {
      return;
    }
    await delay(250);
  }
}

async function runInTab(tabId, func, args) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func,
    args
  });
  return results && results[0] ? results[0].result : null;
}

async function ensureSitePermission(url) {
  const origin = originPattern(url);
  if (!origin) {
    return;
  }
  const hasPermission = await chrome.permissions.contains({ origins: [origin] });
  if (!hasPermission) {
    throw new Error(`site_permission_required:${origin}`);
  }
}

function originPattern(url) {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) {
      return "";
    }
    return `${parsed.protocol}//${parsed.host}/*`;
  } catch (_error) {
    return "";
  }
}

function tabSummary(tab) {
  return {
    id: String(tab.id),
    url: tab.url || "",
    title: tab.title || "",
    active: Boolean(tab.active),
    status: tab.status || ""
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function secondsToMs(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed * 1000) : fallback;
}

function collectVisiblePage(options) {
  const maxChars = Math.max(Number(options.maxChars || 3000), 1);
  const includeItems = Boolean(options.includeItems);
  const minVisibleItems = Math.max(Number(options.minVisibleItems || 0), 0);
  const text = visibleText(document.body || document.documentElement).slice(0, maxChars);
  const items = includeItems ? collectVisibleItems(Math.max(minVisibleItems, 20), 240) : [];
  return {
    url: location.href,
    title: document.title || "",
    visible_text: text,
    items,
    collected_count: items.length,
    partial_reason: minVisibleItems && items.length < minVisibleItems ? "visible_item_count_below_requested_min" : "",
    captured_at: Date.now() / 1000
  };
}

function getPageField(options) {
  const selector = String(options.selector || "");
  const maxChars = Math.max(Number(options.maxChars || 3000), 1);
  const target = selector ? document.querySelector(selector) : document.body || document.documentElement;
  if (!target) {
    return { value: "", matches_n: 0, match_level: "not_found" };
  }
  if (options.action === "get_html") {
    return { value: sanitizedHtml(target).slice(0, maxChars), matches_n: 1, match_level: "exact" };
  }
  if (options.action === "get_value") {
    if (isSensitiveField(target)) {
      return { value: "", matches_n: 1, match_level: "exact", skipped_reason: "sensitive_field_not_read" };
    }
    return { value: String(target.value || target.getAttribute("value") || ""), matches_n: 1, match_level: "exact" };
  }
  if (options.action === "get_attributes") {
    return { value: safeAttrs(target), matches_n: 1, match_level: "exact" };
  }
  return { value: visibleText(target).slice(0, maxChars), matches_n: 1, match_level: "exact" };
}

function findElements(options) {
  const limit = Math.max(Number(options.limit || 20), 1);
  const maxChars = Math.max(Number(options.maxChars || 240), 20);
  let nodes = [];
  if (options.css) {
    nodes = Array.from(document.querySelectorAll(String(options.css)));
  } else {
    nodes = Array.from(document.querySelectorAll("a,button,input,textarea,select,[role],article,main,h1,h2,h3,p,li"));
  }
  const textNeedle = String(options.text || "").toLowerCase();
  const roleNeedle = String(options.role || "").toLowerCase();
  const nameNeedle = String(options.name || "").toLowerCase();
  const matches = [];
  for (const node of nodes) {
    const text = visibleText(node);
    const role = inferredRole(node);
    const name = accessibleName(node, text);
    if (textNeedle && !text.toLowerCase().includes(textNeedle)) {
      continue;
    }
    if (roleNeedle && role.toLowerCase() !== roleNeedle) {
      continue;
    }
    if (nameNeedle && !name.toLowerCase().includes(nameNeedle)) {
      continue;
    }
    matches.push({
      nth: matches.length,
      tag: node.tagName.toLowerCase(),
      role,
      name: name.slice(0, maxChars),
      text: text.slice(0, maxChars),
      attrs: safeAttrs(node),
      visible: isVisible(node)
    });
    if (matches.length >= limit) {
      break;
    }
  }
  return { matches, matches_n: matches.length, url: location.href, title: document.title || "" };
}

function extractContent(options) {
  const selector = String(options.selector || "");
  const chunkSize = Math.max(Number(options.chunkSize || 6000), 1);
  const start = Math.max(Number(options.start || 0), 0);
  const target = selector
    ? document.querySelector(selector)
    : document.querySelector("main") || document.querySelector("article") || document.body || document.documentElement;
  const content = target ? visibleText(target) : "";
  const end = Math.min(start + chunkSize, content.length);
  return {
    url: location.href,
    title: document.title || "",
    selector: selector || "main|article|body",
    total_chars: content.length,
    chunk_size: chunkSize,
    start,
    end,
    next_start_char: end < content.length ? end : null,
    content: content.slice(start, end)
  };
}

function listFrames() {
  const frames = Array.from(document.querySelectorAll("iframe,frame")).map((frame, index) => ({
    index,
    src: frame.getAttribute("src") || "",
    title: frame.getAttribute("title") || "",
    name: frame.getAttribute("name") || "",
    id: frame.id || ""
  }));
  return { url: location.href, title: document.title || "", frames };
}

function pageContainsText(expected) {
  const text = visibleText(document.body || document.documentElement);
  return { found: text.includes(expected), value: expected, url: location.href, title: document.title || "" };
}

function scrollPage(options) {
  const amount = Math.max(Number(options.amount || 800), 1);
  const delta = options.direction === "up" ? -amount : amount;
  window.scrollBy({ top: delta, left: 0, behavior: "instant" });
  return {
    url: location.href,
    title: document.title || "",
    scroll_y: window.scrollY,
    scroll_height: document.documentElement.scrollHeight,
    viewport_height: window.innerHeight
  };
}

function collectVisibleItems(limit, maxChars) {
  const nodes = Array.from(document.querySelectorAll("article,li,[role='article'],[role='listitem'],h1,h2,h3,p,a"));
  const items = [];
  for (const node of nodes) {
    if (!isVisible(node)) {
      continue;
    }
    const text = visibleText(node);
    if (!text || text.length < 2) {
      continue;
    }
    items.push({
      tag: node.tagName.toLowerCase(),
      role: inferredRole(node),
      text: text.slice(0, maxChars),
      href: firstHref(node)
    });
    if (items.length >= limit) {
      break;
    }
  }
  return items;
}

function firstHref(node) {
  if (node && node.href) {
    return String(node.href);
  }
  const link = node && node.querySelector ? node.querySelector("a[href]") : null;
  return link && link.href ? String(link.href) : "";
}

function visibleText(node) {
  if (!node) {
    return "";
  }
  return String(node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
}

function isVisible(node) {
  if (!node || !node.getBoundingClientRect) {
    return false;
  }
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function inferredRole(node) {
  const explicit = node.getAttribute && node.getAttribute("role");
  if (explicit) {
    return explicit;
  }
  const tag = node.tagName ? node.tagName.toLowerCase() : "";
  if (tag === "a") return "link";
  if (tag === "button") return "button";
  if (["input", "textarea", "select"].includes(tag)) return "form";
  if (tag === "article") return "article";
  if (/^h[1-6]$/.test(tag)) return "heading";
  return "";
}

function accessibleName(node, fallbackText) {
  return String(
    node.getAttribute && (
      node.getAttribute("aria-label") ||
      node.getAttribute("title") ||
      node.getAttribute("alt") ||
      node.getAttribute("placeholder")
    ) || fallbackText || ""
  );
}

function isSensitiveField(node) {
  const tag = node && node.tagName ? node.tagName.toLowerCase() : "";
  if (tag !== "input") {
    return false;
  }
  const type = String(node.getAttribute("type") || "text").toLowerCase();
  const autocomplete = String(node.getAttribute("autocomplete") || "").toLowerCase();
  return type === "password" || type === "hidden" || autocomplete.includes("password");
}

function sanitizedHtml(node) {
  const clone = node.cloneNode(true);
  for (const tag of Array.from(clone.querySelectorAll("script,style,noscript"))) {
    tag.remove();
  }
  sanitizeElement(clone);
  for (const element of Array.from(clone.querySelectorAll("*"))) {
    sanitizeElement(element);
  }
  return String(clone.outerHTML || clone.innerHTML || "");
}

function sanitizeElement(element) {
  for (const attr of Array.from(element.attributes || [])) {
    if (/token|cookie|session|auth|password|secret|csrf/i.test(attr.name)) {
      element.removeAttribute(attr.name);
    }
  }
  const tag = element.tagName ? element.tagName.toLowerCase() : "";
  if (tag === "input") {
    const type = String(element.getAttribute("type") || "text").toLowerCase();
    if (type === "password" || type === "hidden") {
      element.setAttribute("value", "");
      element.setAttribute("data-openguanlan-redacted", "sensitive-field");
    }
  }
}

function safeAttrs(node) {
  const attrs = {};
  for (const name of ["id", "class", "role", "aria-label", "title", "href", "placeholder", "type"]) {
    const value = node.getAttribute && node.getAttribute(name);
    if (value) {
      attrs[name] = String(value).slice(0, 240);
    }
  }
  return attrs;
}

function openPairingDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(DB_STORE)) {
        db.createObjectStore(DB_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readPairingToken() {
  const db = await openPairingDb();
  return await new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readonly");
    const store = tx.objectStore(DB_STORE);
    const request = store.get(DB_KEY);
    request.onsuccess = () => resolve(String(request.result || "").trim());
    request.onerror = () => reject(request.error);
  });
}

async function writePairingToken(token) {
  const db = await openPairingDb();
  return await new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readwrite");
    const store = tx.objectStore(DB_STORE);
    const value = String(token || "").trim();
    const request = value ? store.put(value, DB_KEY) : store.delete(DB_KEY);
    request.onsuccess = () => resolve(true);
    request.onerror = () => reject(request.error);
  });
}
