/* Entry point. Modules register their views with the chrome; the chrome owns the router. */
import { $, $$ } from "./core.js";
import { installTooltips } from "./ui.js";
import { initChrome, show, loadHealth } from "./chrome.js";
import "./home.js";
import "./chat.js";
import "./design.js";
import "./explore.js";
import "./kb.js";
import "./system.js";
import "./history.js";
import "./scope.js";

installTooltips();
initChrome();
document.addEventListener("click", (e) => { const g = e.target.closest("[data-go]"); if (g) show(g.dataset.go); });
loadHealth().then(() => { if (location.hash === "#scope") show("scope", false); });
show((location.hash || "#home").slice(1), false);
