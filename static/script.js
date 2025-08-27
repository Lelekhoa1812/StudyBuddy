// ────────────────────────────── static/script.js ──────────────────────────────
const log = (msg) => {
    const el = document.getElementById("upload-log");
    el.textContent += msg + "\n";
    el.scrollTop = el.scrollHeight;
  };
  
  // Upload
  document.getElementById("upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const user_id = document.getElementById("user_id").value.trim();
    const files = document.getElementById("files").files;
    if (!user_id || files.length === 0) {
      alert("Provide user id and at least one file.");
      return;
    }
    const fd = new FormData();
    fd.append("user_id", user_id);
    for (let f of files) fd.append("files", f);
  
    log("Uploading " + files.length + " file(s)…");
    const res = await fetch("/upload", { method: "POST", body: fd });
    const data = await res.json();
    log("Upload accepted. Job: " + (data.job_id || "?") + " • status: " + (data.status || "?"));
    log("Processing in the background. You can start chatting meanwhile.");
  });
  
  // Chat
  document.getElementById("ask").addEventListener("click", async () => {
    const user_id = document.getElementById("user_id").value.trim();
    const q = document.getElementById("question").value.trim();
    if (!user_id || !q) return;
    appendMessage("user", q);
    document.getElementById("question").value = "";
  
    const fd = new FormData();
    fd.append("user_id", user_id);
    fd.append("question", q);
    fd.append("k", "6");
  
    try {
      const res = await fetch("/chat", { method: "POST", body: fd });
      const data = await res.json();
      appendMessage("assistant", data.answer || "[no answer]");
      if (data.sources && data.sources.length) {
        appendSources(data.sources);
      }
    } catch (e) {
      appendMessage("assistant", "⚠️ Error contacting server.");
    }
  });
  
  function appendMessage(role, text) {
    const m = document.createElement("div");
    m.className = "msg " + role;
    m.textContent = text;
    document.getElementById("messages").appendChild(m);
    m.scrollIntoView({ behavior: "smooth", block: "end" });
  }
  
  function appendSources(sources) {
    const wrap = document.createElement("div");
    wrap.className = "sources";
    wrap.innerHTML = "<strong>Sources:</strong> " + sources.map(s => {
      const f = s.filename || "unknown";
      const t = s.topic_name ? (" • " + s.topic_name) : "";
      const p = s.page_span ? (" [pp. " + s.page_span.join("-") + "]") : "";
      return `<span class="pill">${f}${t}${p}</span>`;
    }).join(" ");
    document.getElementById("messages").appendChild(wrap);
    wrap.scrollIntoView({ behavior: "smooth", block: "end" });
  }