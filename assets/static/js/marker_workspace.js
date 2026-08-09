(function () {
  "use strict";

  var workspace = document.getElementById("marker-workspace");
  if (!workspace || typeof window.fetch !== "function") return;

  var pollTimer = null;
  var requestSequence = 0;
  var workspaceUrl = workspace.dataset.workspaceUrl;
  var statusUrl = workspace.dataset.statusUrl;

  function requestHeaders() {
    return {
      "Accept": "application/json",
      "X-Requested-With": "XMLHttpRequest"
    };
  }

  function replaceFragment(id, html) {
    if (!html) return;
    var current = document.getElementById(id);
    if (!current) return;
    var template = document.createElement("template");
    template.innerHTML = html.trim();
    var replacement = template.content.firstElementChild;
    if (replacement) current.replaceWith(replacement);
  }

  function captureMarkerBrowserState() {
    var browser = document.getElementById("marker-browser");
    if (!browser) return null;
    var scrollRegion = browser.querySelector("[data-marker-browser-scroll]");
    var closedSets = Array.from(browser.querySelectorAll("details[data-marker-set-id]:not([open])"))
      .map(function (details) { return details.dataset.markerSetId; });
    return {
      scrollTop: scrollRegion ? scrollRegion.scrollTop : 0,
      closedSets: closedSets
    };
  }

  function restoreMarkerBrowserState(state) {
    if (!state) return;
    var browser = document.getElementById("marker-browser");
    if (!browser) return;
    state.closedSets.forEach(function (setId) {
      var details = browser.querySelector('details[data-marker-set-id="' + setId + '"]');
      if (details) details.open = false;
    });
    var scrollRegion = browser.querySelector("[data-marker-browser-scroll]");
    if (scrollRegion) scrollRegion.scrollTop = state.scrollTop;
  }

  function showNotice(notice) {
    if (!notice || !notice.message) return;
    var notices = document.getElementById("marker-workspace-notices");
    if (!notices) return;
    var alert = document.createElement("div");
    var level = notice.level || "info";
    var alertClass = level === "error" ? "alert-error" :
      level === "warning" ? "alert-warning" :
      level === "success" ? "alert-success" : "alert-info";
    alert.className = "alert " + alertClass + " py-3";
    alert.textContent = notice.message;
    notices.replaceChildren(alert);
    window.setTimeout(function () {
      if (alert.isConnected) alert.remove();
    }, 6000);
  }

  function showRequestError(message) {
    showNotice({
      level: "error",
      message: message || "The marker workspace could not be updated. Try again."
    });
  }

  function applyPayload(payload, options) {
    options = options || {};
    if (options.replaceBrowser !== false) {
      var browserState = captureMarkerBrowserState();
      replaceFragment("marker-browser", payload.marker_browser_html);
      restoreMarkerBrowserState(browserState);
    }
    if (options.replaceEditor !== false) {
      replaceFragment("marker-editor", payload.marker_editor_html);
    }
    replaceFragment("marker-publication-status", payload.publication_status_html);
    replaceFragment("marker-publish-action", payload.publish_action_html);
    workspace.dataset.activeJobId = payload.active_job_id || "";
    if (!options.preserveEditorUrl) {
      workspace.dataset.editorUrl = payload.editor_url || workspaceUrl;
    }
    showNotice(payload.notice);

    if (options.history === "push" && payload.editor_url) {
      window.history.pushState({}, "", payload.editor_url);
    } else if (options.history === "replace" && payload.editor_url) {
      window.history.replaceState({}, "", payload.editor_url);
    }

    startPolling(payload.active_job_id);
  }

  async function fetchPayload(url, options) {
    options = options || {};
    var response = await window.fetch(url, {
      method: options.method || "GET",
      body: options.body || null,
      credentials: "same-origin",
      headers: requestHeaders()
    });
    var contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("The server returned an unexpected response.");
    }
    var payload = await response.json();
    if (!response.ok && response.status !== 422) {
      throw new Error(payload.error || "The marker request failed.");
    }
    return payload;
  }

  async function loadEditor(url, historyMode) {
    var sequence = ++requestSequence;
    workspace.setAttribute("aria-busy", "true");
    try {
      var payload = await fetchPayload(url);
      if (sequence !== requestSequence) return;
      applyPayload(payload, { history: historyMode || false });
    } catch (error) {
      showRequestError(error.message);
    } finally {
      if (sequence === requestSequence) workspace.removeAttribute("aria-busy");
    }
  }

  async function submitWorkspaceForm(form, submitter) {
    var confirmMessage = form.dataset.confirm;
    if (confirmMessage && !window.confirm(confirmMessage)) return;

    var formData = new FormData(form);
    if (submitter && submitter.name) {
      formData.set(submitter.name, submitter.value);
    }
    var isPublishAction = form.id === "marker-publish-action";
    if (submitter) submitter.disabled = true;
    workspace.setAttribute("aria-busy", "true");

    try {
      var payload = await fetchPayload(form.action, {
        method: (form.method || "POST").toUpperCase(),
        body: formData
      });
      applyPayload(payload, {
        history: isPublishAction ? false : "replace",
        replaceBrowser: !isPublishAction,
        replaceEditor: !isPublishAction,
        preserveEditorUrl: isPublishAction
      });
    } catch (error) {
      if (submitter) submitter.disabled = false;
      showRequestError(error.message);
    } finally {
      workspace.removeAttribute("aria-busy");
    }
  }

  function currentEditorUrl() {
    return workspace.dataset.editorUrl || window.location.pathname + window.location.search;
  }

  function refreshPublishedMap() {
    var frame = document.getElementById("published-map-frame");
    if (frame) frame.src = frame.src;
  }

  function startPolling(jobId) {
    if (pollTimer) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
    if (!jobId) return;

    pollTimer = window.setTimeout(async function poll() {
      try {
        var response = await window.fetch(statusUrl, {
          credentials: "same-origin",
          headers: { "Accept": "application/json" }
        });
        if (!response.ok) throw new Error("Status request failed.");
        var status = await response.json();
        var job = status.job;
        if (status.has_active_job && job && String(job.id) === String(jobId)) {
          pollTimer = window.setTimeout(poll, 2000);
          return;
        }
        var payload = await fetchPayload(currentEditorUrl());
        applyPayload(payload, { history: false });
        refreshPublishedMap();
      } catch (error) {
        pollTimer = window.setTimeout(poll, 3000);
      }
    }, 2000);
  }

  workspace.addEventListener("click", function (event) {
    var link = event.target.closest("[data-marker-editor-link]");
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    loadEditor(link.href, "push");
  });

  workspace.addEventListener("submit", function (event) {
    var form = event.target.closest("form[data-marker-workspace-form]");
    if (!form) return;
    event.preventDefault();
    submitWorkspaceForm(form, event.submitter);
  });

  window.addEventListener("popstate", function () {
    loadEditor(window.location.href, false);
  });

  workspace.dataset.editorUrl = window.location.pathname + window.location.search + window.location.hash;
  startPolling(workspace.dataset.activeJobId || null);
})();
