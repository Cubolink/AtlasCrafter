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

  function announce(message) {
    var liveRegion = document.getElementById("marker-workspace-live");
    if (!liveRegion) return;
    liveRegion.textContent = "";
    window.setTimeout(function () {
      liveRegion.textContent = message;
    }, 0);
  }

  function initializeHTMLMarkerPreview() {
    if (window.AtlasCrafterHTMLMarkerPreview) {
      window.AtlasCrafterHTMLMarkerPreview.refresh(document.getElementById("marker-editor"));
    }
  }

  function showSavedState(notice) {
    var button = document.querySelector("#marker-editor [data-marker-save-button]");
    if (!button) return;
    var originalHtml = button.innerHTML;
    var originalClassName = button.className;
    var originalLabel = button.getAttribute("aria-label");

    button.classList.remove("btn-primary");
    button.classList.add("btn-success");
    button.innerHTML = '<span aria-hidden="true">&#10003;</span> Saved';
    button.setAttribute("aria-label", notice.message);
    announce(notice.message);

    window.setTimeout(function () {
      if (!button.isConnected) return;
      button.innerHTML = originalHtml;
      button.className = originalClassName;
      if (originalLabel === null) {
        button.removeAttribute("aria-label");
      } else {
        button.setAttribute("aria-label", originalLabel);
      }
    }, 2000);
  }

  function dismissToast(toast) {
    if (!toast || !toast.isConnected || toast.classList.contains("is-leaving")) return;
    toast.classList.add("is-leaving");
    window.setTimeout(function () {
      if (toast.isConnected) toast.remove();
    }, 160);
  }

  function showToast(notice) {
    var notices = document.getElementById("marker-workspace-notices");
    if (!notices) return;
    var level = notice.level || "info";
    var levelClass = level === "error" ? "marker-workspace-toast-error" :
      level === "warning" ? "marker-workspace-toast-warning" :
      level === "success" ? "marker-workspace-toast-success" : "marker-workspace-toast-info";
    var toast = document.createElement("div");
    toast.className = "marker-workspace-toast " + levelClass;
    toast.setAttribute("role", level === "error" ? "alert" : "status");

    var indicator = document.createElement("span");
    indicator.className = "marker-workspace-toast-indicator";
    indicator.setAttribute("aria-hidden", "true");
    indicator.textContent = level === "success" ? "\u2713" :
      level === "warning" ? "!" : level === "error" ? "\u00d7" : "i";

    var message = document.createElement("span");
    message.className = "min-w-0 flex-1 leading-5";
    message.textContent = notice.message;

    var close = document.createElement("button");
    close.type = "button";
    close.className = "btn btn-ghost btn-xs btn-square -mr-1 -mt-1 shrink-0 text-base-content/50";
    close.setAttribute("aria-label", "Dismiss notification");
    close.textContent = "\u00d7";
    close.addEventListener("click", function () { dismissToast(toast); });

    toast.append(indicator, message, close);
    while (notices.children.length >= 3) notices.firstElementChild.remove();
    notices.appendChild(toast);

    var timeout = level === "error" ? 10000 : level === "warning" ? 7000 : 4000;
    window.setTimeout(function () { dismissToast(toast); }, timeout);
  }

  function showNotice(notice) {
    if (!notice || !notice.message) return;
    if (notice.presentation === "inline-save") {
      showSavedState(notice);
      return;
    }
    showToast(notice);
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
      initializeHTMLMarkerPreview();
    }
    if (options.replacePublicationStatus !== false) {
      replaceFragment("marker-publication-status", payload.publication_status_html);
    }
    if (options.replacePublishAction !== false) {
      replaceFragment("marker-publish-action", payload.publish_action_html);
    }
    if (options.updateJobState !== false) {
      workspace.dataset.activeJobId = payload.active_job_id || "";
    }
    if (!options.preserveEditorUrl) {
      workspace.dataset.editorUrl = payload.editor_url || workspaceUrl;
    }
    showNotice(payload.notice);

    if (options.history === "push" && payload.editor_url) {
      window.history.pushState({}, "", payload.editor_url);
    } else if (options.history === "replace" && payload.editor_url) {
      window.history.replaceState({}, "", payload.editor_url);
    }

    if (options.updateJobState !== false) {
      startPolling(payload.active_job_id);
    }
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
      applyPayload(payload, {
        history: historyMode || false,
        replacePublicationStatus: false,
        replacePublishAction: false,
        updateJobState: false
      });
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
        replacePublishAction: isPublishAction,
        preserveEditorUrl: isPublishAction,
        updateJobState: isPublishAction
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
  initializeHTMLMarkerPreview();
  startPolling(workspace.dataset.activeJobId || null);
})();
