(function () {
    function getCopyText(trigger) {
        if (!trigger) {
            return "";
        }

        var inline = trigger.getAttribute("data-copy-text");
        if (inline) {
            return inline;
        }

        var selector = trigger.getAttribute("data-copy-target");
        if (!selector) {
            return "";
        }

        var target = document.querySelector(selector);
        if (!target) {
            return "";
        }

        if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") {
            return target.value || "";
        }

        return target.textContent || "";
    }

    function fallbackCopy(text) {
        var textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        textarea.style.pointerEvents = "none";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();

        var ok = false;
        try {
            ok = document.execCommand("copy");
        } catch (err) {
            ok = false;
        }

        document.body.removeChild(textarea);
        return ok;
    }

    function ensureToastStack() {
        var stack = document.getElementById("staff-toast-stack");
        if (stack) {
            return stack;
        }

        stack = document.createElement("div");
        stack.id = "staff-toast-stack";
        stack.className = "toast-stack";
        document.body.appendChild(stack);
        return stack;
    }

    function showToast(message) {
        var stack = ensureToastStack();
        var toast = document.createElement("div");
        toast.className = "toast";
        toast.textContent = message;
        stack.appendChild(toast);

        window.setTimeout(function () {
            toast.style.opacity = "0";
            toast.style.transition = "opacity 180ms ease";
            window.setTimeout(function () {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 190);
        }, 1400);
    }

    function copyText(text) {
        if (!text) {
            return Promise.resolve(false);
        }

        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text).then(
                function () {
                    return true;
                },
                function () {
                    return fallbackCopy(text);
                }
            );
        }

        return Promise.resolve(fallbackCopy(text));
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest("[data-copy]");
        if (!trigger) {
            return;
        }

        event.preventDefault();
        var text = getCopyText(trigger);
        copyText(text).then(function (ok) {
            if (ok) {
                showToast("متن کپی شد");
            } else {
                showToast("کپی انجام نشد");
            }
        });
    });
})();
