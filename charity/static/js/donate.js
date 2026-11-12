// Scripts for the Donate page and its pay pages only, so other pages don't download them (page
// weight budgets in lighthouserc.json). Loaded after charity.js by their templates.

// One try too many (#226): what's left of the wait, counted down in minutes and seconds from what
// the server said as the page was made. Each second is hidden from screen readers; the end is
// said once, by the status line. Without JavaScript, the words give the minutes.
document.querySelectorAll("[data-countdown]").forEach((countdown) => {
    const end = Date.now() + Number(countdown.dataset.countdown) * 1000;
    const left = countdown.querySelector("[data-countdown-left]");
    const time = countdown.querySelector("[data-countdown-time]");
    const done = countdown.querySelector("[data-countdown-done]");
    let timer;
    const show = () => {
        const seconds = Math.max(0, Math.ceil((end - Date.now()) / 1000));
        if (seconds === 0) {
            clearInterval(timer);
            left.hidden = true;
            done.textContent = done.dataset.doneText;
            return;
        }
        time.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    };
    show();
    countdown.hidden = false;
    timer = setInterval(show, 1000);
});

// Tell your friends (#100): the phone's own share sheet, so every app the supporter has
// (WhatsApp, Viber, Messenger, Instagram) is there. Shown only where the browser has one (most
// phones, few desktops); without it, the WhatsApp, Facebook and Copy link options are the way.
document.querySelectorAll("button[data-share]").forEach((button) => {
    const shared = {
        title: button.dataset.shareTitle,
        text: button.dataset.shareText,
        url: button.dataset.shareUrl,
    };
    if (!navigator.share || (navigator.canShare && !navigator.canShare(shared))) return;
    button.hidden = false;
    button.addEventListener("click", async () => {
        try {
            await navigator.share(shared);
        } catch {
            // Closed without sharing, or the browser said no: the other options are still there.
        }
    });
});

// Paying with a provider that takes a posted form (eSewa): the page holds the form the server
// signed, and this sends it at once. Not when the page is reached with Back or Forward, so the
// payer can leave it; and without JavaScript, they press its button.
const providerForm = document.querySelector("form[data-auto-submit]");
if (providerForm) {
    const [navigation] = performance.getEntriesByType("navigation");
    if (navigation?.type !== "back_forward") {
        providerForm.submit();
    }
    // Back from a provider that takes its form only once (eSewa), restored from the browser's
    // cache: fetched again instead, so the server sends the payer to the pay page rather than
    // offer a form the provider would refuse.
    if (providerForm.hasAttribute("data-sent-once")) {
        window.addEventListener("pageshow", (event) => {
            if (event.persisted) window.location.reload();
        });
    }
}
