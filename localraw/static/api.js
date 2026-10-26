const base = "/api/v1";
let csrf = "";
export function setCSRF(value) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}
export async function request(path, options = {}) {
  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(csrf ? { "X-CSRF-Token": csrf } : {}),
    ...options.headers,
  };
  const response = await fetch(base + path, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  if (response.status === 204) return null;
  const value = await response.json();
  if (!response.ok)
    throw new ApiError(
      value.error?.message || "Host request failed.",
      response.status,
      value.error?.code,
    );
  return value;
}
export function sendFile(id, file, onProgress, signal) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    xhr.open("PUT", `${base}/uploads/${encodeURIComponent(id)}/content`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("X-CSRF-Token", csrf);
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded);
    };
    const clean = () => signal.removeEventListener("abort", abort);
    xhr.onload = () => {
      clean();
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else
        reject(
          new ApiError(
            xhr.response?.error?.message || "Upload failed.",
            xhr.status,
          ),
        );
    };
    xhr.onerror = () => {
      clean();
      reject(
        new Error("Connection lost. Keep this browser open during uploads."),
      );
    };
    xhr.onabort = () => {
      clean();
      reject(new DOMException("Upload cancelled.", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) {
      clean();
      reject(new DOMException("Upload cancelled.", "AbortError"));
    } else xhr.send(file);
  });
}
export function attachment(job, resource) {
  return `${base}/jobs/${encodeURIComponent(job)}/${resource}`;
}
