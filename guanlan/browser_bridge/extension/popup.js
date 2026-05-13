const DAEMON_URL = "http://127.0.0.1:19830";

const daemonStatus = document.getElementById("daemon-status");
const pairingStatus = document.getElementById("pairing-status");
const siteStatus = document.getElementById("site-status");
const pairingCode = document.getElementById("pairing-code");
const savePairingButton = document.getElementById("save-pairing");
const grantButton = document.getElementById("grant-site");
const refreshButton = document.getElementById("refresh");

refreshButton.addEventListener("click", refreshStatus);
savePairingButton.addEventListener("click", savePairingCode);
grantButton.addEventListener("click", grantCurrentSite);

refreshStatus();

async function refreshStatus() {
  grantButton.disabled = true;
  await Promise.all([checkDaemon(), checkPairingState(), checkSitePermission()]);
}

async function checkDaemon() {
  try {
    const response = await fetch(`${DAEMON_URL}/status`);
    const payload = await response.json();
    daemonStatus.textContent = payload && payload.ok ? "Ready" : "Unavailable";
    if (payload && payload.pairing_required) {
      pairingStatus.textContent = payload.extension_paired ? "Paired" : "Needs pair code";
    }
  } catch (_error) {
    daemonStatus.textContent = "Start openguanlan daemon";
  }
}

async function checkPairingState() {
  const response = await chrome.runtime.sendMessage({ type: "openguanlan:get-pairing-state" });
  if (response && response.saved && pairingStatus.textContent === "Checking...") {
    pairingStatus.textContent = "Saved locally";
  }
}

async function checkSitePermission() {
  const tab = await currentTab();
  const origin = originPattern(tab && tab.url);
  if (!origin) {
    siteStatus.textContent = "Not a web page";
    grantButton.disabled = true;
    return;
  }
  const allowed = await chrome.permissions.contains({ origins: [origin] });
  siteStatus.textContent = allowed ? "Granted" : "Needs grant";
  grantButton.disabled = allowed;
}

async function savePairingCode() {
  savePairingButton.disabled = true;
  try {
    await chrome.runtime.sendMessage({
      type: "openguanlan:set-pairing-token",
      token: pairingCode.value || ""
    });
    pairingCode.value = "";
    pairingStatus.textContent = "Saved locally";
  } finally {
    savePairingButton.disabled = false;
  }
}

async function grantCurrentSite() {
  const tab = await currentTab();
  const origin = originPattern(tab && tab.url);
  if (!origin) {
    return;
  }
  const granted = await chrome.permissions.request({ origins: [origin] });
  siteStatus.textContent = granted ? "Granted" : "Not granted";
  grantButton.disabled = granted;
}

async function currentTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs[0] ? tabs[0] : null;
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
