// 1. Live search: reload the book cards while the student types
const form = document.getElementById("filters");
const results = document.getElementById("results");
if (form && results) {
  let timer;
  const run = () => {
    const params = new URLSearchParams(new FormData(form));
    fetch("/cards?" + params).then(r => r.text()).then(html => { results.innerHTML = html; });
  };
  form.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 250); });
  form.addEventListener("submit", e => { e.preventDefault(); run(); });
}

// 2. Ask before deleting
document.querySelectorAll("[data-confirm]").forEach(btn =>
  btn.addEventListener("click", e => { if (!confirm(btn.dataset.confirm)) e.preventDefault(); }));

// 3. Exchange listings have no price
const price = document.getElementById("price");
const offers = document.querySelectorAll("input[type=radio][name=offer]");
if (price && offers.length) {
  const sync = () => {
    const exchange = document.querySelector("input[name=offer]:checked").value === "exchange";
    price.disabled = exchange;
    if (exchange) price.value = "";
  };
  offers.forEach(o => o.addEventListener("change", sync));
  sync();
}

// 4. Character counters on text areas
document.querySelectorAll("textarea[maxlength]").forEach(t => {
  const c = document.createElement("small");
  c.className = "count";
  t.after(c);
  const update = () => { c.textContent = t.value.length + "/" + t.maxLength; };
  t.addEventListener("input", update);
  update();
});

// 5. Photo preview before upload
const photo = document.getElementById("photo");
const preview = document.getElementById("preview");
if (photo && preview) {
  photo.addEventListener("change", () => {
    const file = photo.files[0];
    if (file) { preview.src = URL.createObjectURL(file); preview.hidden = false; }
  });
}
