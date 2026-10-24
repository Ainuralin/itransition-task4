/* Format chat responses and sanitize the resulting HTML. */
(function () {
  "use strict";
  window.renderChatMarkdown = function (element, text) {
    if (!window.marked || !window.DOMPurify) {
      element.textContent = text;
      return;
    }
    const html = window.marked.parse(String(text), { gfm: true, breaks: true });
    element.innerHTML = window.DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        "p",
        "br",
        "strong",
        "em",
        "del",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "code",
        "hr",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "a",
      ],
      ALLOWED_ATTR: ["href", "title", "start"],
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false,
    });
    for (const table of element.querySelectorAll("table")) {
      const wrap = document.createElement("div");
      wrap.className = "chat-table-wrap";
      wrap.tabIndex = 0;
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", "Assistant answer table");
      table.before(wrap);
      wrap.append(table);
      table.querySelectorAll("th").forEach((th) => (th.scope = "col"));
    }
    for (const link of element.querySelectorAll("a[href]")) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
    element.classList.add("markdown-body");
  };
})();
