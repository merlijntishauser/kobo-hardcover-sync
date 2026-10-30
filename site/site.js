// The site's two small jobs. Without this script the page is complete: the
// download link goes to the latest release and the theme follows the system.
(function () {
  "use strict";
  var REPO = "merlijntishauser/kobo-hardcover-sync";

  // 1. The latest release: its version, date and disk image, from GitHub.
  function release() {
    var link = document.getElementById("dmg");
    var ver = document.getElementById("ver");
    if (!link || !ver || !window.fetch) return;
    fetch("https://api.github.com/repos/" + REPO + "/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (rel) {
        if (!rel || !rel.tag_name) return;
        var version = String(rel.tag_name).replace(/^v/, "");
        var dmg = (rel.assets || []).filter(function (a) { return /\.dmg$/.test(a.name); })[0];
        var when = rel.published_at ? new Date(rel.published_at) : null;
        var date = when ? when.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) : "";
        if (dmg) {
          link.href = dmg.browser_download_url;
          var mb = Math.round(dmg.size / 1048576);
          ver.textContent = "Version " + version + (date ? ", " + date : "") + ". A " + mb + " MB disk image, signed and notarised; macOS 13 or later.";
        } else {
          ver.textContent = "Version " + version + (date ? ", " + date : "") + ", on GitHub.";
        }
      })
      .catch(function () { /* the plain link stands */ });
  }

  // 2. The theme switch in the foot: Light, Auto, Dark, kept in this browser. The app's
  //    pictures follow it too: a <picture> only knows the system's theme by itself.
  function theme() {
    var buttons = document.querySelectorAll("[data-theme-choice]");
    var sources = document.querySelectorAll("picture.app > source");
    function pictures(c) {
      sources.forEach(function (src) { src.media = c === "dark" ? "all" : c === "light" ? "not all" : "(prefers-color-scheme: dark)"; });
    }
    function current() {
      try { return localStorage.getItem("theme") || "auto"; } catch (e) { return "auto"; }
    }
    function show() {
      var c = current();
      buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.themeChoice === c)); });
    }
    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        var c = b.dataset.themeChoice;
        try { if (c === "auto") localStorage.removeItem("theme"); else localStorage.setItem("theme", c); } catch (e) {}
        if (c === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = c;
        pictures(c);
        show();
      });
    });
    pictures(current());
    show();
  }

  release();
  theme();
})();
