/* Super Admin: generate an organisation slug from its name.
 * Adds a "Generate from name" button next to the Slug field on the Create organisation form.
 * Mirrors Django's slugify; the server still checks uniqueness and fills a blank slug itself.
 * Loaded as an external file, so it is allowed by the CSP (script-src 'self').
 */
(function () {
  "use strict";
  var name = document.getElementById("id_name");
  var slug = document.getElementById("id_slug");
  if (!name || !slug) { return; }
  var maxLength = parseInt(slug.getAttribute("maxlength"), 10) || 50;

  function slugify(value) {
    return (value || "")
      .normalize("NFKD")
      .replace(/[^\x00-\x7F]/g, "")
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .trim()
      .replace(/[-\s]+/g, "-")
      .replace(/^[-_]+|[-_]+$/g, "")
      .slice(0, maxLength)
      .replace(/-+$/, "");
  }

  var button = document.createElement("button");
  button.type = "button";
  button.className = "button secondary";
  button.textContent = "Generate from name";
  var status = document.createElement("span");
  status.className = "muted small";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  var wrap = document.createElement("p");
  wrap.className = "slug-generator";
  wrap.appendChild(button);
  wrap.appendChild(status);

  // Place the button just after the slug field's paragraph (Django form.as_p).
  var row = slug.closest("p") || slug.parentNode;
  row.parentNode.insertBefore(wrap, row.nextSibling);

  button.addEventListener("click", function () {
    var value = slugify(name.value);
    if (!value) {
      status.textContent = "Enter the organisation name first.";
      name.focus();
      return;
    }
    slug.value = value;
    slug.dispatchEvent(new Event("change", { bubbles: true }));
    status.textContent = "Slug set to " + value + ".";
  });
})();
