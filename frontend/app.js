(function () {
  const config = window.SENTINEL_CONFIG || {};
  const storageKey = "sentinel-demo-base-url";
  const tenantStorageKey = "sentinel-demo-active-startup";

  const elements = {
    baseUrl: document.getElementById("baseUrl"),
    saveBaseUrl: document.getElementById("saveBaseUrl"),
    output: document.getElementById("output"),
    statusText: document.getElementById("statusText"),
    statusUrl: document.getElementById("statusUrl"),
    tenantPill: document.getElementById("tenantPill"),
    checkHealth: document.getElementById("checkHealth"),
    clearOutput: document.getElementById("clearOutput"),
    startupForm: document.getElementById("startupForm"),
    verifyForm: document.getElementById("verifyForm"),
    loginForm: document.getElementById("loginForm"),
    sessionForm: document.getElementById("sessionForm"),
    profileForm: document.getElementById("profileForm")
  };

  function field(form, name) {
    return form.elements.namedItem(name);
  }

  function getBaseUrl() {
    return (localStorage.getItem(storageKey) || config.defaultBaseUrl || "").replace(/\/+$/, "");
  }

  function getActiveStartupSlug() {
    return (localStorage.getItem(tenantStorageKey) || "").trim();
  }

  function setActiveStartupSlug(slug) {
    const normalized = (slug || "").trim().toLowerCase();
    if (normalized) {
      localStorage.setItem(tenantStorageKey, normalized);
    } else {
      localStorage.removeItem(tenantStorageKey);
    }
    renderBaseUrl();
  }

  function renderBaseUrl() {
    const baseUrl = getBaseUrl();
    const activeStartup = getActiveStartupSlug();
    elements.baseUrl.value = baseUrl;
    elements.statusUrl.textContent = baseUrl || "Base URL not set";
    elements.tenantPill.textContent = activeStartup
      ? "Active startup: " + activeStartup
      : "Active startup: none";

    if (!field(elements.loginForm, "tenant_slug").value && activeStartup) {
      field(elements.loginForm, "tenant_slug").value = activeStartup;
    }
  }

  function saveBaseUrl() {
    const value = elements.baseUrl.value.trim().replace(/\/+$/, "");
    if (!value) {
      writeOutput({ error: "Enter a valid gateway base URL first." });
      return;
    }
    localStorage.setItem(storageKey, value);
    renderBaseUrl();
    checkHealth();
  }

  function withTenantHeader(options, tenantSlug) {
    const headerName = config.tenantHeaderName || "X-Tenant-Slug";
    const headers = Object.assign({}, options && options.headers ? options.headers : {});
    const slug = (tenantSlug || "").trim().toLowerCase();

    if (slug) {
      headers[headerName] = slug;
    }

    return Object.assign({}, options, { headers });
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
      const isHtml = /<!doctype html>|<html/i.test(text);
      return {
        raw: isHtml ? "Received HTML error page from upstream service." : text,
        isHtml
      };
    }
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function formatOutput(response, path, data) {
    if (data && data.isHtml) {
      return {
        status: response.status,
        ok: response.ok,
        path,
        message:
          "The gateway reached an upstream service that returned an HTML error page. This usually means the upstream service is unavailable or returning a non-API response.",
        hint:
          "Check the Azure containers and gateway routing, then retry the request."
      };
    }

    return {
      status: response.status,
      ok: response.ok,
      path,
      data
    };
  }

  async function request(path, options, tenantSlug) {
    const url = getBaseUrl() + path;
    let response = await fetch(url, withTenantHeader(options, tenantSlug));
    let data = await safeJson(response);

    if ((response.status === 502 || response.status === 503) && data && data.isHtml) {
      writeOutput({
        status: response.status,
        ok: false,
        path,
        message: "Upstream service looks cold. Waiting 8 seconds and retrying once..."
      });
      await sleep(8000);
      response = await fetch(url, withTenantHeader(options, tenantSlug));
      data = await safeJson(response);
    }

    writeOutput(formatOutput(response, path, data));
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

  function fillFounderSession(payload, tenantSlug) {
    if (tenantSlug) {
      setActiveStartupSlug(tenantSlug);
      field(elements.loginForm, "tenant_slug").value = tenantSlug;
    }

    if (payload && payload.access_token) {
      field(elements.sessionForm, "token").value = payload.access_token;
      field(elements.profileForm, "token").value = payload.access_token;
    }

    if (payload && payload.user) {
      field(elements.profileForm, "userId").value = payload.user.id || "";
      field(elements.loginForm, "email").value = payload.user.email || field(elements.loginForm, "email").value;
    }
  }

  async function onStartupCreate(event) {
    event.preventDefault();
    const payload = formJson(elements.startupForm);
    const { data } = await request(config.onboardStartupPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const result = data && data.data ? data.data : data;
    if (result && result.tenant && result.tenant.slug) {
      setActiveStartupSlug(result.tenant.slug);
      field(elements.loginForm, "tenant_slug").value = result.tenant.slug;
    }
    if (result && result.founder) {
      field(elements.loginForm, "email").value = result.founder.email || "";
      field(elements.profileForm, "userId").value = result.founder.id || "";
    }
    if (result && result.verification_token) {
      field(elements.verifyForm, "token").value = result.verification_token;
    }
  }

  async function onVerify(event) {
    event.preventDefault();
    const { data } = await request(config.verifyPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formJson(elements.verifyForm))
    });

    const payload = data && data.data ? data.data : data;
    fillFounderSession(payload, payload && payload.user && payload.user.tenant_slug ? payload.user.tenant_slug : getActiveStartupSlug());
  }

  async function onLogin(event) {
    event.preventDefault();
    const payload = formJson(elements.loginForm);
    const tenantSlug = payload.tenant_slug;
    const { data } = await request(config.loginPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: payload.email,
        password: payload.password
      })
    }, tenantSlug);

    const result = data && data.data ? data.data : data;
    fillFounderSession(result, tenantSlug);
  }

  async function onSession(event) {
    event.preventDefault();
    await request(config.mePath, {
      method: "GET",
      headers: {
        Authorization: "Bearer " + formJson(elements.sessionForm).token
      }
    });
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
    }, getActiveStartupSlug());
  }

  elements.saveBaseUrl.addEventListener("click", saveBaseUrl);
  elements.checkHealth.addEventListener("click", checkHealth);
  elements.clearOutput.addEventListener("click", function () {
    writeOutput("Waiting for a request...");
  });
  elements.startupForm.addEventListener("submit", onStartupCreate);
  elements.verifyForm.addEventListener("submit", onVerify);
  elements.loginForm.addEventListener("submit", onLogin);
  elements.sessionForm.addEventListener("submit", onSession);
  elements.profileForm.addEventListener("submit", onProfile);

  renderBaseUrl();
  checkHealth();
})();
