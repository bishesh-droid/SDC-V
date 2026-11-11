/* Runs synchronously in <head> before first paint. External (not inline) because the CSP is script-src 'self'. */
(function () {
  var t = null;
  try { t = localStorage.getItem("sdcv_theme"); } catch (e) {}
  if (t !== "light" && t !== "dark") t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
})();
