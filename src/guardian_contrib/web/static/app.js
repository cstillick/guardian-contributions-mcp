// Public Ledger — table sort / filter / row navigation (no framework).
(function () {
  // Clickable rows on any table (dashboard + flags).
  document.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr[data-href]");
    if (tr) location.href = tr.dataset.href;
  });

  const table = document.getElementById("ledger");
  if (!table) return;
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const filterInput = document.getElementById("filter");
  let activeDist = "*";

  function applyFilter() {
    const q = (filterInput && filterInput.value || "").trim().toLowerCase();
    let shown = 0;
    rows.forEach((r) => {
      const okDist = activeDist === "*" || r.dataset.dist === activeDist;
      const okText = !q || r.dataset.cand.includes(q) || r.dataset.dist.toLowerCase().includes(q);
      const vis = okDist && okText;
      r.style.display = vis ? "" : "none";
      if (vis) shown++;
    });
  }

  document.querySelectorAll(".chip[data-dist]").forEach((ch) => {
    ch.addEventListener("click", () => {
      document.querySelectorAll(".chip[data-dist]").forEach((c) => c.classList.remove("on"));
      ch.classList.add("on");
      activeDist = ch.dataset.dist;
      applyFilter();
    });
  });
  if (filterInput) filterInput.addEventListener("input", applyFilter);

  let sortKey = null, sortDir = 1;
  table.querySelectorAll("th[data-key]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key, type = th.dataset.type;
      if (sortKey === key) sortDir *= -1; else { sortKey = key; sortDir = 1; }
      table.querySelectorAll("th .ar").forEach((a) => a.remove());
      const ar = document.createElement("span");
      ar.className = "ar";
      ar.textContent = sortDir > 0 ? "▲" : "▼";
      th.appendChild(ar);
      rows.slice().sort((a, b) => {
        let av = a.dataset[key], bv = b.dataset[key];
        if (type === "num") return ((+av) - (+bv)) * sortDir;
        return String(av).localeCompare(String(bv)) * sortDir;
      }).forEach((r) => tbody.appendChild(r));
    });
  });

  applyFilter();
})();
