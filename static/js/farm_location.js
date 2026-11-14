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
  button.textContent = "Set from current location";
  var status = document.createElement("span");
  status.className = "muted small location-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  wrap.appendChild(button);
  wrap.appendChild(status);

  // Place the button just before the latitude field's paragraph (Django form.as_p).
  var row = lat.closest("p") || lat.parentNode;
  row.parentNode.insertBefore(wrap, row);

  // Map view
  var mapContainer = document.createElement("div");
  mapContainer.className = "farm-location-map";
  mapContainer.style.height = "300px";
  mapContainer.style.display = "none";
  row.parentNode.insertBefore(mapContainer, row.nextSibling);
  var mapButton = document.createElement("button");
  mapButton.type = "button";
  mapButton.className = "button secondary";
  mapButton.textContent = "Toggle Map View";
  mapButton.setAttribute("aria-expanded", "false");
  row.parentNode.insertBefore(mapButton, row.nextSibling);

  var map = null;
  var marker = null;
  function coordinates() {
    var latitude = Number(lat.value);
    var longitude = Number(lng.value);
    if (lat.value.trim() === "" || lng.value.trim() === "" ||
        !Number.isFinite(latitude) || !Number.isFinite(longitude) ||
        latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
      return null;
    }
    return [latitude, longitude];
  }
  function setCoordinates(latitude, longitude, panMap) {
    lat.value = latitude.toFixed(6);
    lng.value = longitude.toFixed(6);
    lat.dispatchEvent(new Event("change", { bubbles: true }));
    lng.dispatchEvent(new Event("change", { bubbles: true }));
    if (marker) {
      marker.setLatLng([latitude, longitude]);
      if (panMap) { map.setView([latitude, longitude], Math.max(map.getZoom(), 14)); }
    }
  }
  function showMap() {
    mapContainer.style.display = "block";
    mapButton.setAttribute("aria-expanded", "true");
    if (typeof L === "undefined") {
      status.textContent = "The map library did not load. You can still enter coordinates using the map when it is available.";
      return false;
    }
    var current = coordinates();
    var center = current || [0, 0];
    if (!map) {
      map = L.map(mapContainer).setView(center, current ? 14 : 2);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).addTo(map);
      marker = L.marker(center, { draggable: true }).addTo(map);
      marker.on("dragend", function () {
        var position = marker.getLatLng();
        setCoordinates(position.lat, position.lng, false);
      });
      map.on("click", function (event) {
        setCoordinates(event.latlng.lat, event.latlng.lng, false);
      });
    } else if (current) {
      marker.setLatLng(current);
      map.setView(current, Math.max(map.getZoom(), 14));
    }
    window.setTimeout(function () { map.invalidateSize(); }, 0);
    return true;
  }
  mapButton.addEventListener("click", function () {
    if (mapContainer.style.display === "none") {
      showMap();
    } else {
      mapContainer.style.display = "none";
      mapButton.setAttribute("aria-expanded", "false");
    }
  });
  function updateMarkerFromInputs() {
    var current = coordinates();
    if (current && marker) {
      marker.setLatLng(current);
      map.setView(current, Math.max(map.getZoom(), 14));
    }
  }
  lat.addEventListener("change", updateMarkerFromInputs);
  lng.addEventListener("change", updateMarkerFromInputs);

  var MESSAGES = {
    1: "Location permission was denied. Allow location for this site, or type the coordinates.",
    2: "Your location could not be found. Move to an open area and try again.",
    3: "Finding your location took too long. Please try again."
  };

  button.addEventListener("click", function () {
    button.disabled = true;
    status.textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      setCoordinates(pos.coords.latitude, pos.coords.longitude, true);
      if (showMap()) {
        marker.setLatLng([pos.coords.latitude, pos.coords.longitude]);
        map.setView([pos.coords.latitude, pos.coords.longitude], 16);
      }
      var acc = Math.round(pos.coords.accuracy || 0);
      status.textContent = "Location captured" + (acc ? " (accurate to about " + acc + " m)" : "") + ".";
      button.disabled = false;
    }, function (err) {
      status.textContent = MESSAGES[err.code] || "Location is unavailable on this device.";
      button.disabled = false;
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  });
})();
