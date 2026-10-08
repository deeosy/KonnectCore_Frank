/* One-click farm location (Kennedy feedback p.3).
 * Adds a "Use my location" button to forms that have latitude/longitude fields
 * and fills them from the device GPS. Manual entry always remains possible.
 * Loaded as an external file, so it is allowed by the CSP (script-src 'self').
 * Browsers only allow geolocation on HTTPS or localhost.
 */
(function () {
  "use strict";
  var lat = document.getElementById("id_latitude") || document.getElementById("id_farm-latitude");
  var lng = document.getElementById("id_longitude") || document.getElementById("id_farm-longitude");
  if (!lat || !lng || !("geolocation" in navigator)) { return; }

  var wrap = document.createElement("p");
  wrap.className = "location-finder";
  var button = document.createElement("button");
  button.type = "button";
  button.className = "button secondary";
  button.textContent = "Use my location";
  var status = document.createElement("span");
  status.className = "muted small location-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  wrap.appendChild(button);
  wrap.appendChild(status);

  // Place the button just before the latitude field's paragraph (Django form.as_p).
  var row = lat.closest("p") || lat.parentNode;
  row.parentNode.insertBefore(wrap, row);

  var MESSAGES = {
    1: "Location permission was denied. Allow location for this site, or type the coordinates.",
    2: "Your location could not be found. Move to an open area and try again.",
    3: "Finding your location took too long. Please try again."
  };

  button.addEventListener("click", function () {
    button.disabled = true;
    status.textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      lat.value = pos.coords.latitude.toFixed(6);
      lng.value = pos.coords.longitude.toFixed(6);
      lat.dispatchEvent(new Event("change", { bubbles: true }));
      lng.dispatchEvent(new Event("change", { bubbles: true }));
      var acc = Math.round(pos.coords.accuracy || 0);
      status.textContent = "Location captured" + (acc ? " (accurate to about " + acc + " m)" : "") + ".";
      button.disabled = false;
    }, function (err) {
      status.textContent = MESSAGES[err.code] || "Location is unavailable on this device.";
      button.disabled = false;
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  });
})();
