// Shared frontend for the heocr-review mini-site. The same script powers
// both / (dashboard) and /review.html — they share a small amount of logic
// (loading the current reviewer, fetching the active batch) and have their
// own page-specific entry points.

(function () {
  const path = window.location.pathname;
  if (path === "/" || path.endsWith("/index.html")) {
    initDashboard();
  } else if (path.endsWith("/review.html")) {
    initReview();
  }
})();

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} for ${url}`);
  }
  return await response.json();
}

// ----- dashboard -----

async function initDashboard() {
  const reviewerEl = document.getElementById("reviewer-email");
  const startBtn = document.getElementById("start-review");

  try {
    const [me, stats, batch] = await Promise.all([
      fetchJson("/api/me"),
      fetchJson("/api/stats"),
      fetchJson("/api/batch"),
    ]);
    reviewerEl.textContent = me.email;
    renderDashboardStats(stats);

    if (batch && batch.batch_id) {
      startBtn.classList.remove("btn-disabled");
      startBtn.removeAttribute("aria-disabled");
      startBtn.href = "/review.html";
      startBtn.textContent = "Start Review →";
    } else {
      startBtn.textContent = "No batch pending";
    }
  } catch (err) {
    console.error(err);
    reviewerEl.textContent = "error loading";
  }
}

function renderDashboardStats(payload) {
  const stats = payload.stats ?? {};
  const queueDepth = payload.review_queue_depth ?? 0;

  for (const card of document.querySelectorAll(".stat-card[data-key]")) {
    const key = card.dataset.key;
    const valueEl = card.querySelector(".stat-value");
    const row = stats[key];
    if (row && row.value !== undefined && row.value !== null && row.value !== "") {
      valueEl.textContent = row.value;
    } else {
      valueEl.textContent = "—";
    }
  }

  const realSub = document.getElementById("real-items-sub");
  if (realSub) {
    const breakdownRaw = stats["real_items_breakdown"]?.value;
    if (breakdownRaw) {
      try {
        const breakdown = JSON.parse(breakdownRaw);
        realSub.textContent = Object.entries(breakdown)
          .map(([source, count]) => `${source}: ${count}`)
          .join(" · ");
      } catch (_) {
        realSub.textContent = "";
      }
    } else {
      realSub.textContent = "";
    }
  }

  const queueCard = document.getElementById("queue-depth-card");
  if (queueCard) {
    queueCard.querySelector(".stat-value").textContent = String(queueDepth);
  }
}

// ----- review page -----

const DECISION_KEYS = ["approve", "reject", "defer", "needs_legal_review", "needs_privacy_review"];
const DECISION_LABELS = {
  approve: "Approve",
  reject: "Reject",
  defer: "Defer",
  needs_legal_review: "Needs Legal",
  needs_privacy_review: "Needs Privacy",
};

async function initReview() {
  try {
    const batch = await fetchJson("/api/batch");
    if (!batch || !batch.batch_id) {
      document.getElementById("batch-label").textContent = "No active batch";
      document.getElementById("empty-state").hidden = false;
      return;
    }
    document.getElementById("batch-label").textContent = `Batch: ${batch.batch_label ?? batch.batch_id}`;

    const data = await fetchJson(`/api/items?batch_id=${encodeURIComponent(batch.batch_id)}`);
    renderReviewItems(batch, data.items ?? []);
    setupFilterTabs();
    setupKeyboardShortcuts();
  } catch (err) {
    console.error(err);
    document.getElementById("batch-label").textContent = "Failed to load batch";
  }
}

function renderReviewItems(batch, items) {
  const listEl = document.getElementById("review-list");
  const emptyState = document.getElementById("empty-state");
  listEl.innerHTML = "";
  if (emptyState) listEl.appendChild(emptyState);

  for (const item of items) {
    listEl.appendChild(buildItemCard(batch, item));
  }
  updateProgress();
}

function buildItemCard(batch, item) {
  const card = document.createElement("article");
  card.className = "item-card";
  card.dataset.reviewItemId = item.review_item_id;
  card.dataset.decided = item.decided ? "true" : "false";
  if (item.decided) card.classList.add("saved");
  card.tabIndex = 0;

  card.appendChild(buildThumbLink(item));

  const meta = document.createElement("div");
  meta.className = "item-meta";

  const title = document.createElement("div");
  title.className = "title";
  title.textContent = item.title ?? item.item_id;
  meta.appendChild(title);

  const ids = document.createElement("div");
  ids.className = "muted";
  ids.textContent = `${item.item_id} · ${item.source_id}`;
  meta.appendChild(ids);

  meta.appendChild(buildChips(item.review_reasons ?? []));
  meta.appendChild(buildSuggestedRow(item));
  meta.appendChild(buildDecisionRow(card));
  meta.appendChild(buildRationaleRow(card));
  meta.appendChild(buildNotesRow());
  meta.appendChild(buildSaveRow(batch, card));

  card.appendChild(meta);

  if (item.decided && item.decision) {
    applySavedDecision(card, item.decision);
  }

  return card;
}

function buildThumbLink(item) {
  const thumbLink = document.createElement("a");
  thumbLink.className = "thumb-link";
  thumbLink.href = `/api/image?id=${encodeURIComponent(item.review_item_id)}&kind=full`;
  thumbLink.target = "_blank";
  thumbLink.rel = "noopener";

  if (item.has_preview) {
    const img = document.createElement("img");
    img.loading = "lazy";
    img.src = `/api/image?id=${encodeURIComponent(item.review_item_id)}&kind=preview`;
    img.alt = item.title ?? item.item_id;
    thumbLink.appendChild(img);
  } else {
    const placeholder = document.createElement("div");
    placeholder.className = "thumb-placeholder";
    placeholder.textContent = `(no preview · ${item.source_id})`;
    thumbLink.appendChild(placeholder);
  }
  return thumbLink;
}

function buildChips(reasons) {
  const chips = document.createElement("div");
  chips.className = "chips";
  for (const reason of reasons) {
    const chip = document.createElement("span");
    chip.className = "chip";
    if (reason.startsWith("privacy:")) chip.classList.add("privacy");
    else if (reason.startsWith("policy:")) chip.classList.add("policy");
    else if (reason.startsWith("classification:")) chip.classList.add("classification");
    chip.textContent = reason;
    chips.appendChild(chip);
  }
  return chips;
}

function buildSuggestedRow(item) {
  const suggested = document.createElement("div");
  suggested.className = "suggested";
  suggested.appendChild(document.createTextNode("hocrgen suggests: "));
  const strong = document.createElement("strong");
  strong.textContent = item.suggested_decision ?? "—";
  suggested.appendChild(strong);
  const flag = document.createElement("span");
  flag.className = "privacy-badge";
  flag.textContent = `privacy: ${item.privacy_flag}`;
  suggested.appendChild(flag);
  return suggested;
}

function buildDecisionRow(card) {
  const decisionRow = document.createElement("div");
  decisionRow.className = "decision-row";
  for (const key of DECISION_KEYS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "decision-btn";
    btn.dataset.decision = key;
    btn.textContent = DECISION_LABELS[key];
    btn.addEventListener("click", () => toggleDecision(card, key));
    decisionRow.appendChild(btn);
  }
  return decisionRow;
}

function buildRationaleRow(card) {
  const row = document.createElement("div");
  row.className = "field-row";
  const label = document.createElement("label");
  label.textContent = "Rationale (required)";
  const area = document.createElement("textarea");
  area.className = "rationale";
  area.rows = 2;
  area.addEventListener("input", () => refreshSaveState(card));
  row.appendChild(label);
  row.appendChild(area);
  return row;
}

function buildNotesRow() {
  const row = document.createElement("div");
  row.className = "field-row";
  const label = document.createElement("label");
  label.textContent = "Notes (optional)";
  const area = document.createElement("textarea");
  area.className = "notes";
  area.rows = 2;
  row.appendChild(label);
  row.appendChild(area);
  return row;
}

function buildSaveRow(batch, card) {
  const saveRow = document.createElement("div");
  saveRow.className = "save-row";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "save-btn";
  saveBtn.disabled = true;
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", () => saveDecision(batch, card));
  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "edit-btn";
  editBtn.textContent = "Edit decision";
  editBtn.hidden = true;
  editBtn.addEventListener("click", () => enterEditMode(card));
  const status = document.createElement("span");
  status.className = "save-status";
  saveRow.appendChild(saveBtn);
  saveRow.appendChild(editBtn);
  saveRow.appendChild(status);
  return saveRow;
}

function toggleDecision(card, key) {
  if (card.classList.contains("saved")) return;
  const current = card.dataset.decision;
  card.dataset.decision = current === key ? "" : key;
  for (const btn of card.querySelectorAll(".decision-btn")) {
    btn.classList.toggle("active", btn.dataset.decision === card.dataset.decision);
  }
  refreshSaveState(card);
}

function refreshSaveState(card) {
  if (card.classList.contains("saved")) return;
  const decision = card.dataset.decision;
  const rationale = card.querySelector(".rationale").value.trim();
  const saveBtn = card.querySelector(".save-btn");
  const rationaleLabel = card.querySelector(".field-row label");
  saveBtn.disabled = !(decision && rationale.length > 0);
  if (rationaleLabel) {
    rationaleLabel.classList.toggle("required-missing", Boolean(decision) && rationale.length === 0);
  }
}

async function saveDecision(batch, card) {
  const decision = card.dataset.decision;
  const rationale = card.querySelector(".rationale").value.trim();
  const notes = card.querySelector(".notes").value.trim() || null;
  const status = card.querySelector(".save-status");
  if (!decision || !rationale) return;

  status.textContent = "Saving…";
  status.style.color = "var(--fg-muted)";
  try {
    await fetchJson("/api/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        review_item_id: card.dataset.reviewItemId,
        batch_id: batch.batch_id,
        decision,
        rationale,
        notes,
      }),
    });
    status.textContent = "✓ Saved";
    status.style.color = "var(--green)";
    card.classList.add("saved");
    card.dataset.decided = "true";
    disableCardEditing(card);
    updateProgress();
  } catch (err) {
    status.textContent = `Save failed: ${err.message}`;
    status.style.color = "var(--red)";
  }
}

function applySavedDecision(card, decision) {
  card.dataset.decision = decision.decision;
  card.querySelector(".rationale").value = decision.rationale ?? "";
  card.querySelector(".notes").value = decision.notes ?? "";
  for (const btn of card.querySelectorAll(".decision-btn")) {
    btn.classList.toggle("active", btn.dataset.decision === decision.decision);
  }
  const status = card.querySelector(".save-status");
  status.textContent = "✓ Saved";
  status.style.color = "var(--green)";
  disableCardEditing(card);
}

function disableCardEditing(card) {
  for (const btn of card.querySelectorAll(".decision-btn")) {
    btn.disabled = true;
  }
  card.querySelector(".save-btn").disabled = true;
  card.querySelector(".save-btn").hidden = true;
  const editBtn = card.querySelector(".edit-btn");
  if (editBtn) editBtn.hidden = false;
}

function enterEditMode(card) {
  card.classList.remove("saved");
  card.dataset.decided = "false";
  for (const btn of card.querySelectorAll(".decision-btn")) {
    btn.disabled = false;
  }
  const saveBtn = card.querySelector(".save-btn");
  saveBtn.hidden = false;
  const editBtn = card.querySelector(".edit-btn");
  if (editBtn) editBtn.hidden = true;
  const status = card.querySelector(".save-status");
  if (status) status.textContent = "";
  refreshSaveState(card);
  updateProgress();
}

function updateProgress() {
  const cards = document.querySelectorAll(".item-card");
  const decided = document.querySelectorAll('.item-card[data-decided="true"]').length;
  const progress = document.getElementById("progress");
  if (progress) progress.textContent = `${decided} / ${cards.length} decided`;
}

function setupFilterTabs() {
  const tabs = document.querySelectorAll(".filter-tab");
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      for (const t of tabs) t.classList.remove("active");
      tab.classList.add("active");
      const filter = tab.dataset.filter;
      for (const card of document.querySelectorAll(".item-card")) {
        const decided = card.dataset.decided === "true";
        let visible = true;
        if (filter === "undecided") visible = !decided;
        else if (filter === "decided") visible = decided;
        card.style.display = visible ? "" : "none";
      }
    });
  }
}

function setupKeyboardShortcuts() {
  const keyToDecision = { "1": "approve", "2": "reject", "3": "defer", "4": "needs_legal_review", "5": "needs_privacy_review" };
  document.addEventListener("keydown", (event) => {
    const active = document.activeElement;
    if (active && (active.tagName === "TEXTAREA" || active.tagName === "INPUT")) return;

    const focusedCard = active && active.closest ? active.closest(".item-card") : null;

    if (event.key === "j" || event.key === "k") {
      event.preventDefault();
      const cards = Array.from(document.querySelectorAll('.item-card[data-decided="false"]'));
      if (cards.length === 0) return;
      const currentIndex = focusedCard ? cards.indexOf(focusedCard) : -1;
      const nextIndex = event.key === "j"
        ? Math.min(cards.length - 1, currentIndex + 1)
        : Math.max(0, currentIndex - 1);
      const target = cards[nextIndex >= 0 ? nextIndex : 0];
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.focus();
      }
      return;
    }

    if (focusedCard && keyToDecision[event.key]) {
      event.preventDefault();
      toggleDecision(focusedCard, keyToDecision[event.key]);
      return;
    }

    if (event.key === "Enter" && focusedCard) {
      const saveBtn = focusedCard.querySelector(".save-btn");
      if (saveBtn && !saveBtn.disabled && !saveBtn.hidden) {
        event.preventDefault();
        saveBtn.click();
      }
    }
  });
}
