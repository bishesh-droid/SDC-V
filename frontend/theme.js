/* Theme toggle. Light/dark; an explicit choice is stored and overrides the OS. */
(function () {
  var root = document.documentElement, btn = document.getElementById("theme-toggle");
  if (!btn) return;
  var mq = matchMedia("(prefers-color-scheme: dark)");
  function stored() { try { var v = localStorage.getItem("sdcv_theme"); return v === "light" || v === "dark" ? v : null; } catch (e) { return null; } }
  function apply(t, animate) {
    if (animate) { root.classList.add("theme-anim"); setTimeout(function () { root.classList.remove("theme-anim"); }, 250); }
    root.setAttribute("data-theme", t);
    btn.setAttribute("aria-pressed", String(t === "dark"));
    btn.title = t === "dark" ? "Switch to light theme" : "Switch to dark theme";
  }
  apply(root.getAttribute("data-theme") || (mq.matches ? "dark" : "light"), false);
  btn.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    try { localStorage.setItem("sdcv_theme", next); } catch (e) {}
    apply(next, true);
  });
  var onChange = function () { if (!stored()) apply(mq.matches ? "dark" : "light", true); };
  if (mq.addEventListener) mq.addEventListener("change", onChange);
})();
