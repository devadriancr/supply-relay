// Loaded in <head> before the page paints, so a saved theme (or folded sidebar) never flashes.
// No saved theme: the page follows the system (prefers-color-scheme).
(function () {
    try {
        const saved = localStorage.getItem("theme");
        if (saved === "light" || saved === "dark") {
            document.documentElement.dataset.theme = saved;
        }
        if (localStorage.getItem("sidebar") === "collapsed") {
            document.documentElement.dataset.sidebar = "collapsed";
        }
    } catch (e) {
        // Storage blocked: keep following the system
    }
})();
