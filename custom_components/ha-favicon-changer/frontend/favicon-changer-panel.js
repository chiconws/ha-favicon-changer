class HaFaviconChangerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = undefined;
    this._data = undefined;
    this._draftTitle = "";
    this._selectedSource = "preset";
    this._selectedPreset = "";
    this._uploadFile = undefined;
    this._uploadPreviewUrl = undefined;
    this._loading = false;
    this._saving = false;
    this._error = "";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._data && !this._loading) {
      this._load();
    }
  }

  connectedCallback() {
    this._render();
    if (this._hass && !this._data && !this._loading) {
      this._load();
    }
  }

  disconnectedCallback() {
    this._revokeUploadPreview();
  }

  async _load() {
    this._loading = true;
    this._error = "";
    this._render();
    try {
      this._data = await this._hass.callApi("GET", "ha-favicon-changer/config");
      this._draftTitle = this._data.title || "";
      this._selectedSource = this._data.icon_source || "preset";
      this._selectedPreset =
        this._data.icon_preset ||
        (this._data.presets && this._data.presets[0] && this._data.presets[0].id) ||
        "";
    } catch (err) {
      this._error = this._messageFromError(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _messageFromError(err) {
    if (!err) {
      return "Unexpected error.";
    }
    if (typeof err === "string") {
      return err;
    }
    if (err.body && err.body.error) {
      return err.body.error;
    }
    if (err.message) {
      return err.message;
    }
    return "Unexpected error.";
  }

  _escape(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  _titleValue() {
    const input = this.shadowRoot.querySelector("#title");
    return input ? input.value : this._draftTitle;
  }

  _captureTitle() {
    this._draftTitle = this._titleValue();
    return this._draftTitle;
  }

  _refreshPage() {
    window.setTimeout(() => {
      window.location.reload();
    }, 250);
  }

  _selectedPresetData() {
    return (this._data?.presets || []).find((preset) => preset.id === this._selectedPreset);
  }

  _previewUrl() {
    if (this._uploadPreviewUrl) {
      return this._uploadPreviewUrl;
    }
    if (this._selectedSource === "custom") {
      return this._data?.custom_icon_url || "";
    }
    return this._selectedPresetData()?.preview_url || "";
  }

  _previewTitle() {
    if (this._uploadFile) {
      return this._uploadFile.name;
    }
    if (this._selectedSource === "custom") {
      return "Custom upload";
    }
    return this._selectedPresetData()?.name || "Icon preview";
  }

  _selectPreset(presetId) {
    this._captureTitle();
    this._selectedSource = "preset";
    this._selectedPreset = presetId;
    this._clearUploadSelection();
    this._render();
  }

  _selectCustom() {
    this._captureTitle();
    this._selectedSource = "custom";
    this._clearUploadSelection();
    this._render();
  }

  _clearUploadSelection() {
    this._uploadFile = undefined;
    this._revokeUploadPreview();
  }

  _revokeUploadPreview() {
    if (this._uploadPreviewUrl) {
      URL.revokeObjectURL(this._uploadPreviewUrl);
      this._uploadPreviewUrl = undefined;
    }
  }

  _handleFileSelected(event) {
    this._captureTitle();
    const file = event.target.files && event.target.files[0];
    this._error = "";
    this._clearUploadSelection();
    if (!file) {
      this._render();
      return;
    }

    const maxBytes = this._data?.limits?.max_bytes || 1048576;
    const acceptedTypes = this._data?.limits?.accepted_types || [
      "image/gif",
      "image/jpeg",
      "image/png",
      "image/x-icon",
      "image/webp",
    ];
    const acceptedExtensions = this._data?.limits?.accepted_extensions || [
      ".gif",
      ".jpeg",
      ".jpg",
      ".png",
      ".ico",
      ".webp",
    ];
    const filename = file.name.toLowerCase();
    const extensionOk = acceptedExtensions.some((extension) => filename.endsWith(extension));
    const typeOk = !file.type || acceptedTypes.includes(file.type);

    if (!extensionOk || !typeOk) {
      this._error = "Choose a PNG, ICO, WebP, GIF, or JPEG file.";
      event.target.value = "";
      this._render();
      return;
    }
    if (file.size > maxBytes) {
      this._error = "Icon is larger than 1 MiB.";
      event.target.value = "";
      this._render();
      return;
    }

    this._selectedSource = "upload";
    this._uploadFile = file;
    this._uploadPreviewUrl = URL.createObjectURL(file);
    this._render();
  }

  async _applySelection() {
    if (!this._data?.writable || this._saving) {
      return;
    }
    const title = this._captureTitle();
    this._saving = true;
    this._error = "";
    this._render();

    try {
      const source = this._selectedSource === "custom" ? "custom" : "preset";
      const payload = {
        title,
        source,
        icon_preset: source === "preset" ? this._selectedPreset : "",
      };
      this._data = await this._hass.callApi("POST", "ha-favicon-changer/config", payload);
      this._draftTitle = this._data.title || "";
      this._selectedSource = this._data.icon_source || source;
      this._selectedPreset =
        this._data.icon_preset ||
        (this._data.presets && this._data.presets[0] && this._data.presets[0].id) ||
        "";
      this._clearUploadSelection();
      this._refreshPage();
    } catch (err) {
      this._error = this._messageFromError(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }

  async _uploadAndApply() {
    if (!this._uploadFile || !this._data?.writable || this._saving) {
      return;
    }
    const title = this._captureTitle();
    this._saving = true;
    this._error = "";
    this._render();

    const formData = new FormData();
    formData.append("title", title);
    formData.append("file", this._uploadFile, this._uploadFile.name);

    try {
      const response = await this._hass.fetchWithAuth("/api/ha-favicon-changer/upload", {
        method: "POST",
        body: formData,
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.error || "Upload failed.");
      }
      this._data = body;
      this._draftTitle = this._data.title || "";
      this._selectedSource = "custom";
      this._selectedPreset =
        (this._data.presets && this._data.presets[0] && this._data.presets[0].id) || "";
      this._clearUploadSelection();
      this._refreshPage();
    } catch (err) {
      this._error = this._messageFromError(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }

  _renderLoading() {
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <main class="page">
        ${
          this._error
            ? `<div class="error">${this._escape(this._error)}</div>`
            : '<div class="status">Loading Favicon Changer...</div>'
        }
      </main>
    `;
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    if (this._loading || !this._data) {
      this._renderLoading();
      return;
    }

    const presets = this._data.presets || [];
    const previewUrl = this._previewUrl();
    const previewTitle = this._previewTitle();
    const canApplyPreset =
      this._data.writable && this._selectedSource !== "upload" && !this._saving;
    const canUpload = this._data.writable && this._uploadFile && !this._saving;
    const uploadAccept =
      ".png,.ico,.webp,.gif,.jpg,.jpeg,image/png,image/x-icon," +
      "image/vnd.microsoft.icon,image/webp,image/gif,image/jpeg";

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <main class="page">
        <header class="header">
          <div>
            <h1>Favicon Changer</h1>
            <p>Choose the browser and app icon Home Assistant should use.</p>
          </div>
          <button class="primary" id="apply" ${canApplyPreset ? "" : "disabled"}>
            <ha-icon icon="mdi:check"></ha-icon>
            <span>${this._saving ? "Saving" : "Apply"}</span>
          </button>
        </header>

        ${this._error ? `<div class="error">${this._escape(this._error)}</div>` : ""}
        ${
          this._data.writable
            ? ""
            : '<div class="error">Create the integration from Settings before saving changes here.</div>'
        }

        <section class="toolbar">
          <label class="field">
            <span>Page title</span>
            <input id="title" type="text" maxlength="120" value="${this._escape(
              this._draftTitle
            )}">
          </label>
          <label class="file-field">
            <input id="upload" type="file" accept="${uploadAccept}">
            <span class="file-button">
              <ha-icon icon="mdi:upload"></ha-icon>
              <span>Upload</span>
            </span>
          </label>
          <button class="secondary" id="upload-apply" ${canUpload ? "" : "disabled"}>
            <ha-icon icon="mdi:image-check"></ha-icon>
            <span>Use Uploaded Icon</span>
          </button>
        </section>

        <section class="content">
          <div class="grid" role="list">
            ${
              this._data.custom_icon_url
                ? `<button class="preset ${
                    this._selectedSource === "custom" ? "selected" : ""
                  }" data-source="custom" type="button" role="listitem">
                    <img src="${this._escape(this._data.custom_icon_url)}" alt="">
                    <span>Custom upload</span>
                    ${this._data.icon_source === "custom" ? '<b>Active</b>' : ""}
                  </button>`
                : ""
            }
            ${presets
              .map(
                (preset) => `<button class="preset ${
                  this._selectedSource === "preset" && this._selectedPreset === preset.id
                    ? "selected"
                    : ""
                }" data-preset="${this._escape(preset.id)}" type="button" role="listitem">
                  <img src="${this._escape(preset.preview_url)}" alt="">
                  <span>${this._escape(preset.name)}</span>
                  ${preset.active ? "<b>Active</b>" : ""}
                </button>`
              )
              .join("")}
          </div>

          <aside class="preview">
            <div class="preview-box">
              ${previewUrl ? `<img src="${this._escape(previewUrl)}" alt="">` : ""}
            </div>
            <h2>${this._escape(previewTitle)}</h2>
            <p>
              PNG, WebP, GIF, and JPEG uploads must be square and at least 64x64.
              ICO uploads must include a square icon and can be as small as 16x16.
            </p>
          </aside>
        </section>
      </main>
    `;

    this.shadowRoot.querySelector("#apply")?.addEventListener("click", () => {
      this._applySelection();
    });
    this.shadowRoot.querySelector("#title")?.addEventListener("input", () => {
      this._captureTitle();
    });
    this.shadowRoot.querySelector("#upload")?.addEventListener("change", (event) => {
      this._handleFileSelected(event);
    });
    this.shadowRoot.querySelector("#upload-apply")?.addEventListener("click", () => {
      this._uploadAndApply();
    });
    this.shadowRoot.querySelectorAll("[data-preset]").forEach((button) => {
      button.addEventListener("click", () => this._selectPreset(button.dataset.preset));
    });
    this.shadowRoot.querySelector("[data-source='custom']")?.addEventListener("click", () => {
      this._selectCustom();
    });
  }

  _styles() {
    return `
      :host {
        display: block;
        min-height: 100%;
        color: var(--primary-text-color);
        background: var(--primary-background-color);
      }
      * {
        box-sizing: border-box;
      }
      .page {
        width: min(1180px, 100%);
        margin: 0 auto;
        padding: 28px;
      }
      .header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 20px;
      }
      h1,
      h2,
      p {
        margin: 0;
      }
      h1 {
        font-size: 28px;
        font-weight: 500;
        line-height: 1.2;
      }
      h2 {
        font-size: 18px;
        font-weight: 500;
        line-height: 1.3;
      }
      p {
        color: var(--secondary-text-color);
        font-size: 14px;
        line-height: 1.5;
        margin-top: 6px;
      }
      button,
      .file-button {
        border: 0;
        border-radius: 6px;
        min-height: 40px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        font: inherit;
        cursor: pointer;
        transition: background 120ms ease, border-color 120ms ease, transform 120ms ease;
      }
      button:disabled {
        opacity: 0.45;
        cursor: not-allowed;
      }
      button:not(:disabled):active,
      .file-button:active {
        transform: translateY(1px);
      }
      ha-icon {
        width: 20px;
        height: 20px;
      }
      .primary {
        background: var(--primary-color);
        color: var(--text-primary-color);
        padding: 0 18px;
      }
      .secondary,
      .file-button {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        padding: 0 14px;
      }
      .toolbar {
        display: grid;
        grid-template-columns: minmax(220px, 1fr) auto auto;
        gap: 12px;
        align-items: end;
        margin-bottom: 24px;
      }
      .field {
        display: grid;
        gap: 6px;
      }
      .field span {
        font-size: 13px;
        color: var(--secondary-text-color);
      }
      input[type="text"] {
        min-height: 40px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        color: var(--primary-text-color);
        padding: 0 12px;
        font: inherit;
      }
      .file-field input {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip: rect(0 0 0 0);
      }
      .content {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 280px;
        gap: 24px;
        align-items: start;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(128px, 1fr));
        gap: 12px;
      }
      .preset {
        min-height: 138px;
        padding: 14px 12px;
        display: grid;
        justify-items: center;
        align-content: center;
        gap: 10px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        text-align: center;
      }
      .preset:hover,
      .preset.selected {
        border-color: var(--primary-color);
        background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color));
      }
      .preset img {
        width: 56px;
        height: 56px;
        object-fit: contain;
      }
      .preset span {
        min-height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        line-height: 1.25;
        overflow-wrap: anywhere;
      }
      .preset b {
        min-height: 18px;
        color: var(--primary-color);
        font-size: 12px;
        font-weight: 500;
      }
      .preview {
        position: sticky;
        top: 16px;
        display: grid;
        gap: 12px;
        padding: 18px;
        border-radius: 8px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
      }
      .preview-box {
        aspect-ratio: 1;
        display: grid;
        place-items: center;
        border-radius: 8px;
        background:
          linear-gradient(45deg, var(--secondary-background-color) 25%, transparent 25%),
          linear-gradient(-45deg, var(--secondary-background-color) 25%, transparent 25%),
          linear-gradient(45deg, transparent 75%, var(--secondary-background-color) 75%),
          linear-gradient(-45deg, transparent 75%, var(--secondary-background-color) 75%);
        background-size: 22px 22px;
        background-position: 0 0, 0 11px, 11px -11px, -11px 0;
      }
      .preview-box img {
        width: min(70%, 180px);
        height: min(70%, 180px);
        object-fit: contain;
      }
      .error,
      .status {
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 16px;
      }
      .error {
        color: var(--error-color);
        background: color-mix(in srgb, var(--error-color) 12%, var(--card-background-color));
        border: 1px solid color-mix(in srgb, var(--error-color) 40%, var(--divider-color));
      }
      .status {
        color: var(--secondary-text-color);
        background: var(--card-background-color);
        border: 1px solid var(--divider-color);
      }
      @media (max-width: 760px) {
        .page {
          padding: 18px;
        }
        .header,
        .content {
          grid-template-columns: 1fr;
          display: grid;
        }
        .toolbar {
          grid-template-columns: 1fr;
        }
        .primary,
        .secondary,
        .file-button {
          width: 100%;
        }
        .preview {
          position: static;
          order: -1;
        }
      }
    `;
  }
}

customElements.define("ha-favicon-changer-panel", HaFaviconChangerPanel);
