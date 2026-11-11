/* Runs synchronously in <head> before first paint. External (not inline) because the CSP is script-src 'self'.
   Preference is "system" (default), "light" or "dark"; data-theme always holds the resolved value. */
(function () {
  var pref = "system";
  try { var s = localStorage.getItem("sdcv_theme"); if (s === "light" || s === "dark" || s === "system") pref = s; } catch (e) {}
  var dark = matchMedia("(prefers-color-scheme: dark)").matches;
  var root = document.documentElement;
  root.setAttribute("data-theme", pref === "system" ? (dark ? "dark" : "light") : pref);
  root.setAttribute("data-theme-pref", pref);
})();
