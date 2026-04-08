const elements = {
  settingsStatus: document.querySelector("#settings-status"),
  reloadButton: document.querySelector("#reload-settings-button"),
  saveButton: document.querySelector("#save-settings-button"),
  testButton: document.querySelector("#test-notification-button"),
  configPath: document.querySelector("#config-path"),
  configSource: document.querySelector("#config-source"),
  settingsNote: document.querySelector("#settings-note"),
  notificationsEnabled: document.querySelector("#notifications-enabled"),
  providerInputs: [...document.querySelectorAll('input[name="push-provider"]')],
  providerCards: [...document.querySelectorAll("[data-provider-card]")],
  providerSections: [...document.querySelectorAll("[data-provider-section]")],
  barkBaseUrl: document.querySelector("#bark-base-url"),
  barkDeviceKey: document.querySelector("#bark-device-key"),
  barkTitlePrefix: document.querySelector("#bark-title-prefix"),
  barkUrl: document.querySelector("#bark-url"),
  barkGroup: document.querySelector("#bark-group"),
  barkIcon: document.querySelector("#bark-icon"),
  barkSound: document.querySelector("#bark-sound"),
  barkCall: document.querySelector("#bark-call"),
  barkCiphertext: document.querySelector("#bark-ciphertext"),
  barkLevel: document.querySelector("#bark-level"),
  serverchanSendKey: document.querySelector("#serverchan-send-key"),
  serverchanChannel: document.querySelector("#serverchan-channel"),
  serverchanNoip: document.querySelector("#serverchan-noip"),
  serverchanTitlePrefix: document.querySelector("#serverchan-title-prefix"),
  testTitle: document.querySelector("#test-title"),
  testSubtitle: document.querySelector("#test-subtitle"),
  testBody: document.querySelector("#test-body"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  seedTestFields();
  void loadSettings();
});

function bindEvents() {
  elements.reloadButton.addEventListener("click", () => {
    void loadSettings();
  });

  elements.saveButton.addEventListener("click", () => {
    void saveSettings();
  });

  elements.testButton.addEventListener("click", () => {
    void sendTestNotification();
  });

  elements.providerInputs.forEach((input) => {
    input.addEventListener("change", () => {
      renderProviderState();
    });
  });
}

function seedTestFields() {
  elements.testTitle.value = "Toyoko Monitor 测试通知";
  elements.testSubtitle.value = "配置页联调";
  elements.testBody.value = "这是一条来自 Toyoko Monitor 配置页的测试推送。";
}

async function loadSettings() {
  setStatus("正在读取配置");
  toggleActionButtons(true);
  try {
    const response = await api("/api/settings/notifications");
    fillForm(response.config);
    elements.configPath.textContent = response.config_path;
    elements.configSource.textContent = formatConfigSource(response.source);
    elements.settingsNote.textContent = buildNote(response);
    renderProviderState();
    setStatus("配置已加载");
  } catch (error) {
    console.error(error);
    setStatus(`配置加载失败: ${error.message}`);
  } finally {
    toggleActionButtons(false);
  }
}

async function saveSettings() {
  setStatus("正在保存配置");
  toggleActionButtons(true);
  try {
    const config = collectConfig();
    const response = await api("/api/settings/notifications", {
      method: "PUT",
      body: JSON.stringify(config),
    });
    fillForm(response.config);
    elements.configPath.textContent = response.config_path;
    elements.configSource.textContent = formatConfigSource(response.source);
    elements.settingsNote.textContent = buildNote(response);
    renderProviderState();
    setStatus("配置已保存");
  } catch (error) {
    console.error(error);
    setStatus(`配置保存失败: ${error.message}`);
  } finally {
    toggleActionButtons(false);
  }
}

async function sendTestNotification() {
  setStatus("正在发送测试推送");
  toggleActionButtons(true);
  try {
    const payload = {
      config: collectConfig(),
      title: elements.testTitle.value.trim(),
      subtitle: elements.testSubtitle.value.trim(),
      body: elements.testBody.value.trim(),
    };
    const response = await api("/api/settings/notifications/test", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStatus(`${formatProviderLabel(response.provider)} 测试已发送`);
  } catch (error) {
    console.error(error);
    setStatus(`测试发送失败: ${error.message}`);
  } finally {
    toggleActionButtons(false);
  }
}

function collectConfig() {
  return {
    enabled: elements.notificationsEnabled.checked,
    provider: getSelectedProvider(),
    bark: {
      base_url: elements.barkBaseUrl.value.trim(),
      device_key: elements.barkDeviceKey.value.trim(),
      title_prefix: elements.barkTitlePrefix.value.trim(),
      url: elements.barkUrl.value.trim(),
      group: elements.barkGroup.value.trim(),
      icon: elements.barkIcon.value.trim(),
      sound: elements.barkSound.value.trim(),
      call: elements.barkCall.checked,
      ciphertext: elements.barkCiphertext.value.trim(),
      level: elements.barkLevel.value || "timeSensitive",
    },
    serverchan: {
      send_key: elements.serverchanSendKey.value.trim(),
      channel: elements.serverchanChannel.value.trim(),
      noip: parseNoipValue(elements.serverchanNoip.value),
      title_prefix: elements.serverchanTitlePrefix.value.trim(),
    },
  };
}

function fillForm(config) {
  elements.notificationsEnabled.checked = Boolean(config.enabled);
  const provider = config.provider || "bark";
  elements.providerInputs.forEach((input) => {
    input.checked = input.value === provider;
  });

  const bark = config.bark || {};
  elements.barkBaseUrl.value = bark.base_url || "";
  elements.barkDeviceKey.value = bark.device_key || "";
  elements.barkTitlePrefix.value = bark.title_prefix || "";
  elements.barkUrl.value = bark.url || "";
  elements.barkGroup.value = bark.group || "";
  elements.barkIcon.value = bark.icon || "";
  elements.barkSound.value = bark.sound || "";
  elements.barkCall.checked = Boolean(bark.call);
  elements.barkCiphertext.value = bark.ciphertext || "";
  elements.barkLevel.value = bark.level || "timeSensitive";

  const serverchan = config.serverchan || {};
  elements.serverchanSendKey.value = serverchan.send_key || "";
  elements.serverchanChannel.value = serverchan.channel || "";
  elements.serverchanNoip.value =
    serverchan.noip === null || typeof serverchan.noip === "undefined" ? "" : String(serverchan.noip);
  elements.serverchanTitlePrefix.value = serverchan.title_prefix || "";
}

function renderProviderState() {
  const selectedProvider = getSelectedProvider();
  elements.providerCards.forEach((card) => {
    card.classList.toggle("is-active", card.dataset.providerCard === selectedProvider);
  });
  elements.providerSections.forEach((section) => {
    section.classList.toggle("is-inactive", section.dataset.providerSection !== selectedProvider);
  });
}

function getSelectedProvider() {
  const selected = elements.providerInputs.find((input) => input.checked);
  return selected ? selected.value : "bark";
}

function parseNoipValue(value) {
  if (value === "") {
    return null;
  }
  return Number(value);
}

function toggleActionButtons(disabled) {
  elements.reloadButton.disabled = disabled;
  elements.saveButton.disabled = disabled;
  elements.testButton.disabled = disabled;
}

function buildNote(response) {
  if (response.source === "legacy_serverchan") {
    return `当前表单是从旧配置 ${response.legacy_source_path} 导入的。点击“保存配置”后会写入新的统一配置文件。`;
  }
  if (response.source === "notification") {
    return "当前使用新的统一推送配置文件；监控通知会按这里保存的最新配置发送。";
  }
  return "当前还没有找到已保存的统一配置文件，表单展示的是默认值。";
}

function formatConfigSource(source) {
  if (source === "legacy_serverchan") {
    return "旧版 Server酱 配置";
  }
  if (source === "notification") {
    return "统一配置文件";
  }
  return "默认值";
}

function formatProviderLabel(provider) {
  return provider === "serverchan" ? "Server酱" : "Bark";
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(extractErrorDetail(payload, response));
  }
  return payload;
}

function extractErrorDetail(payload, response) {
  if (payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  if (payload && Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item.msg || JSON.stringify(item))
      .join("；");
  }
  return response.statusText;
}

function setStatus(text) {
  elements.settingsStatus.textContent = text;
}
