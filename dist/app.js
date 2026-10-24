"use strict";
const $ = (s) => document.querySelector(s),
  money = (n) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    }).format(n),
  num = (n) => Number(n).toLocaleString("en-US");
const escape = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
let datasets = [],
  current,
  chatReady = false;
function table(headers, rows) {
  return `<table><thead><tr>${headers.map((h) => `<th scope="col">${escape(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${escape(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
function bars(rows, label, value, format = num) {
  const max = Math.max(...rows.map((r) => r[value]), 1);
  return (
    '<div class="bars">' +
    rows
      .map(
        (r) =>
          `<div class="bar-row"><div class="bar-label"><span>${escape(r[label])}</span><strong>${escape(format(r[value]))}</strong></div><div class="bar-track"><div class="bar-fill" style="width:${(r[value] / max) * 100}%"></div></div></div>`,
      )
      .join("") +
    "</div>"
  );
}
function renderChart() {
  let data = current.daily;
  const n = $("#range").value;
  if (n !== "all") data = data.slice(-Number(n));
  const W = 1000,
    H = 255,
    p = { l: 66, r: 16, t: 18, b: 34 };
  const max = Math.max(...data.map((r) => r.revenue)) * 1.1 || 1;
  const x = (i) => p.l + (i / (data.length - 1 || 1)) * (W - p.l - p.r),
    y = (v) => H - p.b - (v / max) * (H - p.t - p.b);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily revenue in USD for ${current.store}"><defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#3d8566" stop-opacity=".20"/><stop offset="100%" stop-color="#3d8566" stop-opacity=".01"/></linearGradient></defs>`;
  for (let i = 0; i <= 4; i++) {
    let v = (max * i) / 4;
    svg += `<line x1="${p.l}" x2="${W - p.r}" y1="${y(v)}" y2="${y(v)}" stroke="#e8eee5"/><text x="${p.l - 12}" y="${y(v) + 4}" text-anchor="end">$${Math.round(v).toLocaleString("en-US")}</text>`;
  }
  let points = data.map((r, i) => `${x(i)},${y(r.revenue)}`).join(" ");
  svg += `<polygon points="${p.l},${H - p.b} ${points} ${x(data.length - 1)},${H - p.b}" fill="url(#area)"/><polyline points="${points}" fill="none" stroke="#398166" stroke-width="1.8"/>`;
  for (let i = 0; i < 5; i++) {
    let k = Math.round((i * (data.length - 1)) / 4);
    svg += `<text x="${x(k)}" y="${H - 8}" text-anchor="${i === 0 ? "start" : i === 4 ? "end" : "middle"}">${data[k].date}</text>`;
  }
  svg += data
    .map(
      (r, i) =>
        `<circle class="point" tabindex="0" cx="${x(i)}" cy="${y(r.revenue)}" r="5" aria-label="${r.date}: ${money(r.revenue)}"><title>${r.date}: ${money(r.revenue)}</title></circle>`,
    )
    .join("");
  $("#revenue-chart").innerHTML = svg + "</svg>";
}
function setTab(id) {
  if (!["overview", "customers", "authors"].includes(id)) return;
  document
    .querySelectorAll(".view")
    .forEach((el) => (el.hidden = el.id !== id));
  document.querySelectorAll(".nav").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === id);
    el.setAttribute("aria-current", el.dataset.tab === id ? "page" : "false");
  });
  $("#page-title").textContent = {
    overview: "Store overview",
    customers: "Customers",
    authors: "Authors",
  }[id];
}
function render() {
  current = datasets.find((d) => d.store === $("#store").value);
  $("#period").textContent =
    `${current.store} · ${current.daily[0].date} — ${current.daily.at(-1).date}`;
  const cards = [
    [
      "Total revenue",
      money(current.revenue_cents / 100),
      `${num(current.order_count)} orders · all dates`,
    ],
    [
      "Unique customers",
      num(current.unique_users),
      "After identity reconciliation",
    ],
    [
      "Author sets",
      num(current.unique_author_sets),
      "Distinct sets in the full catalog",
    ],
    ["Books sold", num(current.sold_books), "Sum of ordered quantities"],
  ];
  $("#metrics").innerHTML = cards
    .map(
      ([label, value, note]) =>
        `<article class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><small>${note}</small></article>`,
    )
    .join("");
  renderChart();
  $("#top-days").innerHTML = current.top_days
    .map(
      (r, i) =>
        `<div class="rank-row"><span class="rank-num">0${i + 1}</span><div>${r.date}<div class="rank-bar"><i style="width:${(r.revenue / current.top_days[0].revenue) * 100}%"></i></div></div><strong class="rank-amount">${money(r.revenue)}</strong></div>`,
    )
    .join("");
  $("#best-buyer").innerHTML = current.best_buyers
    .map(
      (r) =>
        `<div class="big-amount">${money(r.spent)}</div><div class="ids">${escape(JSON.stringify(r.ids))}</div><span class="muted">Customer IDs, including aliases</span>`,
    )
    .join("");
  $("#popular-author").innerHTML = current.popular_authors
    .map(
      (r) =>
        `<div class="author-name">${escape(r.authors)}</div><span class="badge">${num(r.units)} books sold</span>`,
    )
    .join("");
  $("#customer-chart").innerHTML = bars(
    current.customers
      .slice(0, 10)
      .map((r) => ({ ...r, label: JSON.stringify(r.ids) })),
    "label",
    "spent",
    money,
  );
  $("#customer-table").innerHTML = table(
    ["Rank", "Customer IDs / aliases", "Books sold", "Total spending (USD)"],
    current.customers.map((r, i) => [
      i + 1,
      JSON.stringify(r.ids),
      num(r.units),
      money(r.spent),
    ]),
  );
  $("#identity-summary").innerHTML =
    `<div class="big-amount">${num(current.quality.reconciled_profiles)}</div><p>Additional profiles linked to existing customers.</p>`;
  $("#author-chart").innerHTML = bars(
    current.authors.slice(0, 10),
    "authors",
    "units",
  );
  $("#author-table").innerHTML = table(
    ["Rank", "Author set", "Books sold"],
    current.authors.map((r, i) => [i + 1, r.authors, num(r.units)]),
  );
  $("#author-summary").innerHTML =
    `<div class="big-amount">${num(current.unique_author_sets)}</div><p>Distinct sets across ${num(current.quality.input_books)} catalog books.</p>`;
  $("#quality-table").innerHTML = table(
    ["Quality check", "Count"],
    Object.entries(current.quality).map(([k, v]) => [
      k.replaceAll("_", " "),
      num(v),
    ]),
  );
}
$("#store").addEventListener("change", render);
$("#range").addEventListener("change", renderChart);
document
  .querySelectorAll(".nav")
  .forEach((el) => el.addEventListener("click", () => setTab(el.dataset.tab)));
$("#export").addEventListener("click", () => {
  const csv =
    "date,revenue_usd,books_sold,orders\n" +
    current.daily
      .map((r) => [r.date, r.revenue.toFixed(2), r.units, r.orders].join(","))
      .join("\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = current.store + "_daily_revenue.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
function message(text, role) {
  const el = document.createElement("div");
  el.className = "message " + role;
  if (role === "assistant" && window.renderChatMarkdown) {
    window.renderChatMarkdown(el, text);
  } else {
    el.textContent = text;
  }
  $("#chat-messages").append(el);
}
$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!chatReady) return;
  const q = $("#question").value.trim();
  if (!q) return;
  message(q, "user");
  $("#question").value = "";
  $("#ask").disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, store: current.store }),
    });
    const r = await res.json();
    if (!res.ok) throw Error(r.error || "Request failed");
    message(r.answer, "assistant");
    $("#chat-status").textContent = "Groq connected";
    if (r.actions)
      for (const a of r.actions) {
        if (a.store && datasets.some((d) => d.store === a.store)) {
          $("#store").value = a.store;
          render();
        }
        if (a.tab) setTab(a.tab);
      }
  } catch (err) {
    message(err.message, "assistant");
  } finally {
    $("#ask").disabled = false;
  }
});
fetch("data.json")
  .then((r) => {
    if (!r.ok) throw Error("Cannot load data");
    return r.json();
  })
  .then((data) => {
    datasets = data;
    $("#store").innerHTML = data
      .map((d) => `<option>${d.store}</option>`)
      .join("");
    render();
  })
  .catch((err) => {
    $("#error").hidden = false;
    $("#error").textContent = err.message;
  });
fetch("/api/health")
  .then((r) => r.json())
  .then((r) => {
    chatReady = Boolean(r.chat_ready);
    $("#chat-status").textContent = chatReady
      ? "Groq configured"
      : "Not configured";
    $("#question").disabled = !chatReady;
    $("#ask").disabled = !chatReady;
    $("#chat-note").textContent = chatReady
      ? "Questions use the selected store unless another store is specified."
      : "Chat is unavailable until a Groq key is configured on the server.";
  })
  .catch(() => {
    $("#chat-status").textContent = "Static dashboard";
    $("#question").disabled = true;
    $("#ask").disabled = true;
    $("#chat-note").textContent = "Chat is unavailable on this static page.";
  });
