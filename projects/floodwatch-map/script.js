const map = L.map("map").setView([39.8283, -98.5795], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const newsList = document.getElementById("news-list");
const markersLayer = L.layerGroup().addTo(map);

const GDELT_URL =
  "https://api.gdeltproject.org/api/v2/geo/geo" +
  "?query=" +
  encodeURIComponent("(flood OR flooding OR \"flash flood\" OR \"flood warning\" OR \"flood watch\" OR \"coastal flooding\" OR \"river flooding\") sourcecountry:US") +
  "&mode=PointData" +
  "&format=json" +
  "&maxpoints=250" +
  "&geores=2" +
  "&timespan=24h";

function cleanText(value) {
  if (!value) return "";
  const div = document.createElement("div");
  div.innerHTML = value;
  return div.textContent || div.innerText || "";
}

function getSeverity(text) {
  const lower = cleanText(text).toLowerCase();

  if (
    lower.includes("emergency") ||
    lower.includes("evacuation") ||
    lower.includes("deadly") ||
    lower.includes("catastrophic") ||
    lower.includes("life-threatening") ||
    lower.includes("flash flood warning")
  ) {
    return "High";
  }

  if (
    lower.includes("warning") ||
    lower.includes("severe") ||
    lower.includes("major") ||
    lower.includes("flood watch") ||
    lower.includes("river flooding") ||
    lower.includes("coastal flooding")
  ) {
    return "Moderate";
  }

  return "Low";
}

function getSeverityClass(severity) {
  return severity.toLowerCase();
}

function getArticleUrl(item) {
  if (item.url) return item.url;
  if (item.URL) return item.URL;
  if (item.shareurl) return item.shareurl;
  if (item.articleurl) return item.articleurl;
  return "#";
}

function getTitle(item) {
  return (
    item.title ||
    item.name ||
    item.fullname ||
    item.location ||
    item.html ||
    "Flood-related news location"
  );
}

function getLocationName(item) {
  return (
    item.name ||
    item.location ||
    item.fullname ||
    item.label ||
    item.title ||
    "Mapped location"
  );
}

function getLatitude(item) {
  return Number(
    item.lat ||
    item.latitude ||
    item.Latitude ||
    item.LAT ||
    item.latitudedeg
  );
}

function getLongitude(item) {
  return Number(
    item.lon ||
    item.lng ||
    item.longitude ||
    item.Longitude ||
    item.LON ||
    item.longitudedeg
  );
}

function normalizeGdeltItems(data) {
  if (Array.isArray(data)) return data;

  if (Array.isArray(data.features)) {
    return data.features.map((feature) => {
      const props = feature.properties || {};
      const coords = feature.geometry?.coordinates || [];

      return {
        ...props,
        lon: coords[0],
        lat: coords[1]
      };
    });
  }

  if (Array.isArray(data.results)) return data.results;
  if (Array.isArray(data.locations)) return data.locations;
  if (Array.isArray(data.articles)) return data.articles;

  return [];
}

async function fetchGdeltFloodNews() {
  const response = await fetch(GDELT_URL);

  if (!response.ok) {
    throw new Error(`GDELT request failed with status ${response.status}`);
  }

  const data = await response.json();
  return normalizeGdeltItems(data);
}

function renderFloodNews(items) {
  newsList.innerHTML = "";
  markersLayer.clearLayers();

  const mappedItems = items
    .map((item) => {
      const lat = getLatitude(item);
      const lon = getLongitude(item);

      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        return null;
      }

      const title = cleanText(getTitle(item));
      const location = cleanText(getLocationName(item));
      const url = getArticleUrl(item);
      const severity = getSeverity(`${title} ${location}`);

      return {
        title,
        location,
        url,
        severity,
        lat,
        lon
      };
    })
    .filter(Boolean)
    .slice(0, 100);

  if (mappedItems.length === 0) {
    newsList.innerHTML =
      "<p>No live GDELT flood locations found right now. Try refreshing later.</p>";
    return;
  }

  mappedItems.forEach((item) => {
    const severityClass = getSeverityClass(item.severity);

    L.marker([item.lat, item.lon])
      .addTo(markersLayer)
      .bindPopup(`
        <strong>${item.title}</strong><br>
        ${item.location}<br>
        Severity: ${item.severity}<br>
        ${
          item.url !== "#"
            ? `<a href="${item.url}" target="_blank" rel="noopener noreferrer">Read source</a>`
            : ""
        }
      `);

    const card = document.createElement("div");
    card.className = "news-card";

    card.innerHTML = `
      <span class="badge ${severityClass}">${item.severity}</span>
      <h3>${item.title}</h3>
      <p><strong>Mapped location:</strong> ${item.location}</p>
      ${
        item.url !== "#"
          ? `<a href="${item.url}" target="_blank" rel="noopener noreferrer">Read source</a>`
          : "<p>Source link unavailable from this GDELT point.</p>"
      }
    `;

    newsList.appendChild(card);
  });

  const bounds = markersLayer.getBounds();

  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [40, 40] });
  }
}

async function loadFloodNews() {
  newsList.innerHTML = "<p>Loading live GDELT flood news map...</p>";

  try {
    const items = await fetchGdeltFloodNews();
    renderFloodNews(items);
  } catch (error) {
    console.error(error);

    newsList.innerHTML = `
      <p>Unable to load live GDELT data right now.</p>
      <p>Please refresh the page later.</p>
    `;
  }
}

loadFloodNews();

setInterval(loadFloodNews, 15 * 60 * 1000);
