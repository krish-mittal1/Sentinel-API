(function () {
  const config = window.SENTINEL_CONFIG || {};
  const storageKey = "sentinel-demo-base-url";

  const elements = {
    baseUrl: document.getElementById("baseUrl"),
    saveBaseUrl: document.getElementById("saveBaseUrl"),
    output: document.getElementById("output"),
    statusText: document.getElementById("statusText"),
    statusUrl: document.getElementById("statusUrl"),
    checkHealth: document.getElementById("checkHealth"),
    clearOutput: document.getElementById("clearOutput"),
    signupForm: document.getElementById("signupForm"),
    verifyForm: document.getElementById("verifyForm"),
    loginForm: document.getElementById("loginForm"),
    profileForm: document.getElementById("profileForm")
  };

  function getBaseUrl() {
    return (
      localStorage.getItem(storageKey) ||
      config.defaultBaseUrl ||
      ""
    ).replace(/\/+$/, "");
  }

  function saveBaseUrl() {
    const value = elements.baseUrl.value.trim().replace(/\/+$/, "");
    if (!value) {
      return writeOutput({ error: "Enter a valid gateway base URL first." });
    }
    localStorage.setItem(storageKey, value);
    renderBaseUrl();
    checkHealth();
  }

  function renderBaseUrl() {
    const baseUrl = getBaseUrl();
    elements.baseUrl.value = baseUrl;
    elements.statusUrl.textContent = baseUrl || "Base URL not set";
  }

  function writeOutput(data) {
    elements.output.textContent =
      typeof data === "string" ? data : JSON.stringify(data, null, 2);
  }

  async function safeJson(response) {
    const text = await response.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch (error) {
      return { raw: text };
    }
  }

  async function request(path, options) {
    const response = await fetch(getBaseUrl() + path, options);
    const data = await safeJson(response);
    writeOutput({
      status: response.status,
      ok: response.ok,
      path,
      data
    });
    return { response, data };
  }

  async function checkHealth() {
    const baseUrl = getBaseUrl();
    if (!baseUrl) {
      elements.statusText.textContent = "Missing base URL";
      elements.statusText.className = "panel__value warn";
      return;
    }

    elements.statusText.textContent = "Checking...";
    elements.statusText.className = "panel__value";

    try {
      const response = await fetch(baseUrl, { method: "GET" });
      if (response.ok) {
        elements.statusText.textContent = "Live";
        elements.statusText.className = "panel__value ok";
      } else {
        elements.statusText.textContent = "Responding with " + response.status;
        elements.statusText.className = "panel__value warn";
      }
    } catch (error) {
      elements.statusText.textContent = "Unavailable";
      elements.statusText.className = "panel__value warn";
    }
  }

  function formJson(form) {
    return Object.fromEntries(new FormData(form).entries());
  }

  async function onSignup(event) {
    event.preventDefault();
    const payload = formJson(elements.signupForm);
    const { data } = await request(config.signupPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (data && data.data && data.data.verification_token) {
      elements.verifyForm.token.value = data.data.verification_token;
    } else if (data && data.verification_token) {
      elements.verifyForm.token.value = data.verification_token;
    }
  }

  async function onVerify(event) {
    event.preventDefault();
    await request(config.verifyPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formJson(elements.verifyForm))
    });
  }

  async function onLogin(event) {
    event.preventDefault();
    const { data } = await request(config.loginPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formJson(elements.loginForm))
    });

    const payload = data && data.data ? data.data : data;
    if (payload && payload.access_token) {
      elements.profileForm.token.value = payload.access_token;
    }
    if (payload && payload.user && payload.user.id) {
      elements.profileForm.userId.value = payload.user.id;
    }
  }

  async function onProfile(event) {
    event.preventDefault();
    const payload = formJson(elements.profileForm);
    const path = config.userPathTemplate.replace("{userId}", payload.userId);

    await request(path, {
      method: "GET",
      headers: {
        Authorization: "Bearer " + payload.token
      }
    });
  }

  elements.saveBaseUrl.addEventListener("click", saveBaseUrl);
  elements.checkHealth.addEventListener("click", checkHealth);
  elements.clearOutput.addEventListener("click", function () {
    writeOutput("Waiting for a request...");
  });
  elements.signupForm.addEventListener("submit", onSignup);
  elements.verifyForm.addEventListener("submit", onVerify);
  elements.loginForm.addEventListener("submit", onLogin);
  elements.profileForm.addEventListener("submit", onProfile);

  renderBaseUrl();
  checkHealth();
})();
