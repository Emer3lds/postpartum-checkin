"use strict";

const $ = (id) => document.getElementById(id);
const SCREENS = ["auth", "setup", "today", "history", "summary"];
let state = null;
let authMode = "login";

// Her words are always inserted as text, never as HTML.
function esc(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

async function api(path, body) {
  const options = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || "Something went wrong. Please try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function show(name) {
  SCREENS.forEach((s) => { $(s).hidden = s !== name; });
  const loggedIn = name !== "auth" && name !== "setup";
  $("tabs").hidden = !loggedIn;
  document.querySelectorAll(".tab[data-tab]").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === name);
  });
  window.scrollTo(0, 0);
}

function showError(id, message) {
  $(id).textContent = message;
  $(id).hidden = !message;
}

function formatDate(iso) {
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

/* ---------- Fixed alert wording ---------- */

const LEVEL_LABEL = { call_911: "Call 911", care_now: "Get care now", check_this: "Check this" };

function urgentFlags(entry) {
  return entry.flags.filter((f) => f.level !== "check_this");
}

function openAlert(entry) {
  const urgent = urgentFlags(entry);
  const is911 = entry.level === "call_911";
  const harm = entry.flags.some((f) => f.sign_id === "harm_thoughts");
  const dialog = $("alert-dialog");

  dialog.className = "sheet urgent";
  dialog.innerHTML = `
    <h2 id="alert-title">${is911 ? "Call 911 now" : "Get medical care right away"}</h2>
    <p>What you wrote may relate to an urgent maternal warning sign. Don't wait. Tell them you gave birth in the last year.</p>
    ${is911 ? `<a class="call danger" href="tel:911">Call 911</a>` : `
      <p>Call your health care provider now. If you can't reach them, go to the emergency room or call 911.</p>
      <a class="call danger" href="tel:911">Call 911</a>`}
    ${harm ? `
      <a class="call" href="tel:988">Call or text 988<small>Suicide &amp; Crisis Lifeline, 24/7</small></a>
      <a class="call" href="tel:18338526262">Call or text 1-833-852-6262<small>National Maternal Mental Health Hotline, 24/7</small></a>` : ""}
    <h3>May relate to</h3>
    ${urgent.map((f) => `<p><strong>${esc(f.name)}</strong></p><p class="quote">${esc(f.quote)}</p>`).join("")}
    <h3>Words you can say</h3>
    <div class="script" id="script-text">${esc(entry.script)}</div>
    <button id="copy-script" class="secondary wide" type="button">Copy these words</button>
    <button id="alert-close" class="secondary wide" type="button">Close</button>`;

  dialog.querySelector("#copy-script").addEventListener("click", async (event) => {
    try {
      await navigator.clipboard.writeText(entry.script);
      event.target.textContent = "Copied";
    } catch {
      event.target.textContent = "Select the words above to copy them";
    }
  });
  dialog.querySelector("#alert-close").addEventListener("click", () => dialog.close());
  dialog.showModal();
}

function renderResult(entry) {
  const box = $("result");
  const parts = [];

  if (entry.ai_status !== "ok") {
    parts.push(`<div class="card urgent">
      <h3>The full check didn't finish</h3>
      <p>Your check-in is saved, but this result used word matching only and can miss signs. Review the warning signs under "Get help now." If something feels wrong, get care.</p>
    </div>`);
  }

  if (urgentFlags(entry).length) {
    parts.push(`<div class="card urgent">
      <h3>${esc(LEVEL_LABEL[entry.level])}</h3>
      <p>What you wrote may relate to an urgent warning sign.</p>
      <button id="reopen-alert" class="primary wide" type="button">See what to do</button>
    </div>`);
  }

  entry.flags.filter((f) => f.level === "check_this").forEach((flag) => {
    const answered = flag.answer
      ? `<p><strong>Your answer: ${esc(flag.answer)}.</strong> This stays in your history. If this feels serious or you're worried, get care now.</p>`
      : `<p><strong>${esc(flag.question || "Is this getting worse?")}</strong></p>
         <div class="answers">
           <button class="secondary" data-sign="${esc(flag.sign_id)}" data-answer="yes" type="button">Yes</button>
           <button class="secondary" data-sign="${esc(flag.sign_id)}" data-answer="no" type="button">No</button>
           <button class="secondary" data-sign="${esc(flag.sign_id)}" data-answer="unsure" type="button">Not sure</button>
         </div>
         <p class="fine">If this feels serious or you're worried, get care now.</p>`;
    parts.push(`<div class="card check">
      <h3>Check this</h3>
      <p class="quote">${esc(flag.quote)}</p>
      <p>This may relate to: ${esc(flag.name)}.</p>
      ${answered}
    </div>`);
  });

  if (!entry.flags.length && entry.ai_status === "ok") {
    parts.push(`<div class="card">
      <h3>Saved</h3>
      <p>We didn't match this entry to a warning sign. This app can miss things and can't tell you that you're okay. If something feels wrong, contact your health care provider.</p>
    </div>`);
  }

  box.innerHTML = parts.join("");
  const reopen = box.querySelector("#reopen-alert");
  if (reopen) reopen.addEventListener("click", () => openAlert(entry));
  box.querySelectorAll("[data-answer]").forEach((button) => {
    button.addEventListener("click", () => answerFollowUp(entry, button.dataset.sign, button.dataset.answer));
  });
}

async function answerFollowUp(entry, signId, answer) {
  try {
    const data = await api(`/api/entries/${entry.id}/follow-up`, { sign_id: signId, answer });
    state = data.state;
    renderAll();
    renderResult(data.entry);
    if (answer === "yes") openAlert(data.entry);
  } catch (error) {
    showError("checkin-error", error.message);
  }
}

/* ---------- Patterns, history, clinician summary ---------- */

function patternCards(patterns) {
  return patterns.map((p) => `<div class="card check">
    <h3>${esc(p.title)}</h3>
    ${p.evidence.map((e) => `<p class="date">${esc(formatDate(e.date))}</p><p class="quote">${esc(e.quote)}</p>`).join("")}
    <p>This keeps coming up. Contact your health care provider about it. If you have a warning sign, get care right away.</p>
  </div>`).join("");
}

function renderHistory() {
  $("patterns-history").innerHTML = patternCards(state.patterns);
  const entries = [...state.entries].reverse();
  $("history-list").innerHTML = entries.length
    ? entries.map((e) => `<div class="card">
        <p class="date">${esc(formatDate(e.created_at))}</p>
        <p>${esc(e.text)}</p>
        ${e.flags.map((f) => `<p><span class="pill ${esc(f.level)}">${esc(LEVEL_LABEL[f.level])}</span> ${esc(f.name)}</p>`).join("")}
      </div>`).join("")
    : `<p class="muted">Your check-ins will appear here.</p>`;
}

function renderSummary() {
  const flagged = state.entries.filter((e) => e.flags.length);
  $("summary-body").innerHTML = `
    <p><strong>Birth date:</strong> ${state.birth_date ? esc(formatDate(state.birth_date)) : "Not given"}
      ${state.weeks_since_birth != null ? `(${state.weeks_since_birth} weeks ago)` : ""}</p>
    <p class="fine">Quotes are the patient's own words. Matches to warning signs were made by software and are not a diagnosis. No clinician has reviewed this tool. Demo only.</p>
    <h3>Things that keep coming up</h3>
    ${state.patterns.length ? patternCards(state.patterns) : `<p class="muted">None found by this tool. It can miss things.</p>`}
    <h3>Possible warning signs</h3>
    ${flagged.length ? `<table>
      <thead><tr><th>Date</th><th>Sign</th><th>Patient's words</th></tr></thead>
      <tbody>${flagged.flatMap((e) => e.flags.map((f) => `<tr>
        <td>${esc(formatDate(e.created_at))}</td>
        <td>${esc(f.name)}${f.answer ? `<br><small>Follow-up answer: ${esc(f.answer)}</small>` : ""}</td>
        <td>${esc(f.quote)}</td></tr>`)).join("")}</tbody>
    </table>` : `<p class="muted">None found by this tool. It can miss things.</p>`}
    <h3>All check-ins</h3>
    ${state.entries.map((e) => `<p class="date">${esc(formatDate(e.created_at))}</p><p>${esc(e.text)}</p>`).join("") || `<p class="muted">No check-ins yet.</p>`}`;
}

function renderAll() {
  $("greeting").textContent = state.weeks_since_birth != null
    ? `Week ${state.weeks_since_birth} after birth. How are you today?`
    : "How are you today?";
  $("help-signs").innerHTML = state.signs.map((s) => `<li>${esc(s.name)}</li>`).join("");
  $("patterns-today").innerHTML = patternCards(state.patterns);
  renderHistory();
  renderSummary();
}

function enterApp(newState) {
  state = newState;
  if (!state.birth_date) {
    show("setup");
    return;
  }
  renderAll();
  show("today");
}

/* ---------- Events ---------- */

$("auth-switch").addEventListener("click", () => {
  authMode = authMode === "login" ? "signup" : "login";
  $("auth-submit").textContent = authMode === "login" ? "Log in" : "Create account";
  $("auth-switch").textContent = authMode === "login" ? "New here? Create an account" : "Have an account? Log in";
  $("password").autocomplete = authMode === "login" ? "current-password" : "new-password";
  showError("auth-error", "");
});

$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("auth-error", "");
  try {
    const data = await api(`/api/${authMode}`, { username: $("username").value, password: $("password").value });
    $("password").value = "";
    enterApp(data);
  } catch (error) {
    showError("auth-error", error.message);
  }
});

$("setup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("setup-error", "");
  try {
    enterApp(await api("/api/profile", { birth_date: $("birth-date").value }));
  } catch (error) {
    showError("setup-error", error.message);
  }
});

$("checkin-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  stopListening();
  showError("checkin-error", "");
  const save = $("save");
  save.disabled = true;
  save.textContent = "Checking...";
  try {
    const data = await api("/api/checkin", { text: $("entry").value });
    state = data.state;
    $("entry").value = "";
    renderAll();
    renderResult(data.entry);
    if (urgentFlags(data.entry).length) openAlert(data.entry);
  } catch (error) {
    showError("checkin-error", error.message);
  } finally {
    save.disabled = false;
    save.textContent = "Save check-in";
  }
});

document.querySelectorAll(".tab[data-tab]").forEach((tab) => {
  tab.addEventListener("click", () => show(tab.dataset.tab));
});

$("logout").addEventListener("click", async () => {
  await api("/api/logout", {});
  state = null;
  $("result").innerHTML = "";
  show("auth");
});

$("help-btn").addEventListener("click", () => $("help-dialog").showModal());
$("help-close").addEventListener("click", () => $("help-dialog").close());
$("print").addEventListener("click", () => window.print());

/* ---------- Voice input (Chrome's built-in speech recognition) ---------- */

const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;

function stopListening() {
  if (recognizer) recognizer.stop();
}

if (!Speech) {
  $("mic").hidden = true;
  $("mic-note").textContent = "Voice input isn't available in this browser. Chrome supports it.";
  $("mic-note").hidden = false;
} else {
  $("mic").addEventListener("click", () => {
    if (recognizer) {
      stopListening();
      return;
    }
    const base = $("entry").value.trim();
    recognizer = new Speech();
    recognizer.continuous = true;
    recognizer.interimResults = true;
    recognizer.lang = "en-US";
    recognizer.onresult = (event) => {
      const heard = Array.from(event.results).map((r) => r[0].transcript).join(" ");
      $("entry").value = [base, heard.trim()].filter(Boolean).join(" ");
    };
    recognizer.onerror = (event) => {
      $("mic-note").textContent = event.error === "not-allowed"
        ? "Please allow microphone access, or type your check-in."
        : "Voice input stopped. You can try again or type your check-in.";
      $("mic-note").hidden = false;
    };
    recognizer.onend = () => {
      recognizer = null;
      $("mic").setAttribute("aria-pressed", "false");
      $("mic").textContent = "Speak";
    };
    recognizer.start();
    $("mic").setAttribute("aria-pressed", "true");
    $("mic").textContent = "Stop";
    $("mic-note").hidden = true;
  });
}

/* ---------- Start ---------- */

api("/api/state").then(enterApp).catch(() => show("auth"));
