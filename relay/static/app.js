// Forms marked with data-confirm (removing a vendor) ask first in a modal
const confirmDialog = document.querySelector("[data-confirm-dialog]");
let pendingForm = null;

document.addEventListener("submit", (event) => {
    const form = event.target;
    const message = form.dataset.confirm;
    if (!message) return;

    // Very old browsers without <dialog>: the browser's own question
    if (!confirmDialog || typeof confirmDialog.showModal !== "function") {
        if (!window.confirm(message)) event.preventDefault();
        return;
    }

    event.preventDefault();
    pendingForm = form;
    confirmDialog.querySelector("[data-confirm-message]").textContent = message;
    confirmDialog.returnValue = "";
    confirmDialog.showModal(); // Escape and "Cancelar" close it without removing
});

confirmDialog?.addEventListener("close", () => {
    if (confirmDialog.returnValue === "confirm" && pendingForm) {
        pendingForm.submit(); // submit() skips the submit event, so it doesn't ask again
    }
    pendingForm = null;
});

// A click on the dark backdrop (outside the box) also cancels
confirmDialog?.addEventListener("click", (event) => {
    if (event.target === confirmDialog) confirmDialog.close("cancel");
});

// Light / dark mode switch, remembered in this browser
document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-theme-toggle]")) return;

    const root = document.documentElement;
    const current = root.dataset.theme
        || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";

    root.dataset.theme = next;
    try {
        localStorage.setItem("theme", next);
    } catch (e) {
        // Storage blocked: the choice lasts until the page reloads
    }
});

// Floating notifications close on their own; errors stay a little longer so they can be read
function closeToast(toast) {
    toast.classList.add("is-leaving");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
    setTimeout(() => toast.remove(), 400); // in case animations are off
}

document.querySelectorAll("[data-toast]").forEach((toast) => {
    let timer;
    const start = () => {
        timer = setTimeout(() => closeToast(toast), toast.classList.contains("toast-error") ? 10000 : 6000);
    };
    // Pauses while the pointer is over it, so it doesn't vanish while being read
    toast.addEventListener("mouseenter", () => clearTimeout(timer));
    toast.addEventListener("mouseleave", start);
    // Same for the keyboard (WCAG 2.2.1)
    toast.addEventListener("focusin", () => clearTimeout(timer));
    toast.addEventListener("focusout", start);
    start();
});

document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-toast-close]");
    if (button) closeToast(button.closest("[data-toast]"));
});

// Selects marked with data-autosubmit (language) apply as soon as they change
document.addEventListener("change", (event) => {
    if (event.target.matches("[data-autosubmit]")) {
        event.target.form.submit();
    }
});

// Advanced options of the schedule form: their fields only take part while the box is checked
function syncOption(option) {
    const on = option.querySelector(".check input").checked;
    option.querySelectorAll(".inline-fields :is(input, select)").forEach((field) => { field.disabled = !on; });
}
document.querySelectorAll("[data-option]").forEach(syncOption);
document.addEventListener("change", (event) => {
    const option = event.target.closest("[data-option]");
    if (option && event.target.matches(".check input")) syncOption(option);
});

// Sidebar (like TailAdmin): on wide screens the button folds it to icons and the choice is
// remembered; on narrow screens it slides in over the page and closes on the backdrop or Escape
const DESKTOP = window.matchMedia("(min-width: 1280px)");

document.addEventListener("click", (event) => {
    const root = document.documentElement;

    if (event.target.closest("[data-sidebar-toggle]")) {
        if (DESKTOP.matches) {
            const collapsed = root.dataset.sidebar !== "collapsed";
            if (collapsed) root.dataset.sidebar = "collapsed";
            else delete root.dataset.sidebar;
            try {
                localStorage.setItem("sidebar", collapsed ? "collapsed" : "expanded");
            } catch (e) {
                // Storage blocked: the choice lasts until the page reloads
            }
        } else {
            root.classList.toggle("sidebar-open");
        }
        return;
    }

    if (event.target.closest("[data-sidebar-close]")) {
        root.classList.remove("sidebar-open");
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.documentElement.classList.remove("sidebar-open");
    document.documentElement.classList.add("tooltips-off"); // back on with the next pointer move or Tab
});
["pointermove", "focusin"].forEach((type) =>
    document.addEventListener(type, () => document.documentElement.classList.remove("tooltips-off")));

// While a send runs the page reloads to show progress, but not while someone is typing,
// tabbing or answering the confirmation, so it never steals their place (WCAG 2.2.1)
if (document.body.hasAttribute("data-auto-refresh")) {
    setInterval(() => {
        const busy = document.activeElement !== document.body || document.querySelector("dialog[open]");
        if (!busy) location.reload();
    }, 5000);
}
