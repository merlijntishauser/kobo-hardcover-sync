// The site's three small jobs. Without this script the page is complete: the
// download link goes to the latest release, the margin is drawn, the theme
// follows the system.
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

  // 2. The stroke: one continuous line from the end of the Kobo's gauge into the
  //    first mark of the margin. Measured, so it meets both at any width; only on a
  //    desk, where the two stand side by side.
  function stroke() {
    var svg = document.getElementById("stroke");
    var path = document.getElementById("strokepath");
    var gauge = document.getElementById("gauge");
    var mark = document.getElementById("mark-1");
    var hero = svg && svg.parentNode;
    if (!svg || !path || !gauge || !mark || !hero) return;
    function draw() {
      if (window.innerWidth < 1024) { svg.classList.remove("on"); return; }
      svg.removeAttribute("preserveAspectRatio");  // measured from here on, not stretched
      var h = hero.getBoundingClientRect();
      var g = gauge.getBoundingClientRect();
      var m = mark.querySelector(".mk").getBoundingClientRect();
      var x1 = g.right - h.left, y1 = g.bottom - 3 - h.top;
      var x2 = m.left - 10 - h.left, y2 = m.top + m.height / 2 - h.top;  // ends just short of the caret: the mark is the arrowhead
      var dx = Math.max(60, (x2 - x1) * 0.55);
      svg.setAttribute("viewBox", "0 0 " + h.width + " " + h.height);
      path.setAttribute("d", "M" + x1 + " " + y1 + " C " + (x1 + dx) + " " + y1 + ", " + (x2 - dx) + " " + y2 + ", " + x2 + " " + y2);
      var len = path.getTotalLength();
      path.style.setProperty("--len", len);
      svg.classList.add("on");
    }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw); else draw();
    var t;
    window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(draw, 120); });
  }

  // 3. The theme switch in the foot: Light, Auto, Dark, kept in this browser.
  function theme() {
    var buttons = document.querySelectorAll("[data-theme-choice]");
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
        show();
      });
    });
    show();
  }

  release();
  stroke();
  theme();
})();
