const map = L.map("map").setView([39.8283, -98.5795], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const newsList = document.getElementById("news-list");
const markersLayer = L.layerGroup().addTo(map);

const rssFeeds = [
  "https://news.google.com/rss/search?q=flooding+OR+%22flash+flood%22+OR+%22flood+warning%22+United+States&hl=en-US&gl=US&ceid=US:en",
  "https://news.google.com/rss/search?q=%22river+flooding%22+United+States&hl=en-US&gl=US&ceid=US:en",
  "https://news.google.com/rss/search?q=%22coastal+flooding%22+United+States&hl=en-US&gl=US&ceid=US:en"
];

const locationHints = [
  "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
  "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
  "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
  "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
  "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
  "New Hampshire", "New Jersey", "New Mexico", "New York",
  "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
  "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
  "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
  "West Virginia", "Wisconsin", "Wyoming",

  "Houston", "Baton Rouge", "New Orleans", "Miami", "Tampa",
  "Baltimore", "Annapolis", "New York City", "Philadelphia", "Chicago",
  "St. Louis", "Dallas", "Austin", "San Antonio", "Los Angeles",
  "San Diego", "San Francisco", "Sacramento", "Seattle", "Portland",
  "Atlanta", "Charlotte", "Raleigh", "Charleston", "Norfolk",
  "Virginia Beach", "Washington DC", "Nashville", "Memphis",
  "Jackson", "Little Rock", "Oklahoma City", "Tulsa", "Denver",
  "Phoenix", "Las Vegas", "Salt Lake City", "Boise", "Billings",
  "Minneapolis", "Milwaukee", "Detroit", "Cleveland", "Cincinnati",
  "Pittsburgh", "Boston", "Providence", "Hartford", "Newark"
];

const geocodeCache = {};

function cleanText(text) {
  const div = document.createElement("div");
  div.innerHTML = text || "";
  return div.textContent || div.innerText || "";
}

function getSeverity(title, description) {
  const text = `${title} ${description}`.toLowerCase();

  if (
    text.includes("emergency") ||
    text.includes("evacuation") ||
    text.includes("deadly") ||
    text.includes("catastrophic") ||
    text.includes("life-threatening") ||
    text.includes("flash flood warning")
  ) {
    return "High";
  }

  if (
    text.includes("warning") ||
    text.includes("severe") ||
    text.includes("major") ||
    text.includes("flood watch") ||
    text.includes("river flooding") ||
    text.includes("coastal flooding")
  ) {
    return "Moderate";
  }

  return "Low";
}

function getSeverityClass(severity) {
  return severity.toLowerCase();
}

function extractLocation(title, description) {
  const text = `${title} ${description}`.toLowerCase();

  for (const place of locationHints) {
    if (text.includes(place.toLowerCase())) {
      return place;
    }
  }

  return null;
}

async function geocodeLocation(locationName) {
  if (!locationName) return null;

  if (geocodeCache[locationName]) {
    return geocodeCache[locationName];
  }

  const query = encodeURIComponent(`${locationName}, USA`);
  const url = `https://nominatim.openstreetmap.org/search?format=json&q=${query}&limit=1&countrycodes=us`;

  try {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json"
      }
    });

    const data = await response.json();

    if (!data || data.length === 0) {
      return null;
    }

    const result = {
      displayName: data[0].display_name,
      lat: parseFloat(data[0].lat),
      lon: parseFloat(data[0].lon)
    };

    geocodeCache[locationName] = result;
    return result;
  } catch (error) {
    console.error("Geocoding failed:", error);
    return null;
  }
}

async function fetchRSSFeed(feedUrl) {
  const proxyUrl =
    "https://api.allorigins.win/raw?url=" + encodeURIComponent(feedUrl);

  const response = await fetch(proxyUrl);
  const text = await response.text();

  const parser = new DOMParser();
  const xml = parser.parseFromString(text, "application/xml");

  return Array.from(xml.querySelectorAll("item")).map((item) => ({
    title: cleanText(item.querySelector("title")?.textContent || "Flood news update"),
    link: item.querySelector("link")?.textContent || "#",
    pubDate: item.querySelector("pubDate")?.textContent || "",
    description: cleanText(
      item.querySelector("description")?.textContent ||
      "Recent flood-related news item."
    )
  }));
}

async function loadFloodNews() {
  newsList.innerHTML = "<p>Loading live flood news...</p>";
  markersLayer.clearLayers();

  const allItems = [];

  for (const feed of rssFeeds) {
    try {
      const items = await fetchRSSFeed(feed);
      allItems.push(...items);
    } catch (error) {
      console.error("RSS feed failed:", error);
    }
  }

  const uniqueItems = [];
  const seenTitles = new Set();

  allItems.forEach((item) => {
    if (!seenTitles.has(item.title)) {
      seenTitles.add(item.title);
      uniqueItems.push(item);
    }
  });

  const mappedItems = [];

  for (const item of uniqueItems.slice(0, 30)) {
    const locationName = extractLocation(item.title, item.description);

    if (!locationName) continue;

    const geo = await geocodeLocation(locationName);

    if (!geo) continue;

    mappedItems.push({
      ...item,
      location: locationName,
      lat: geo.lat,
      lon: geo.lon,
      severity: getSeverity(item.title, item.description)
    });

    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  newsList.innerHTML = "";

  if (mappedItems.length === 0) {
    newsList.innerHTML =
      "<p>No mappable flood news found right now. The live RSS feed may not contain recognizable city or state names at this moment.</p>";
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
        <a href="${item.link}" target="_blank" rel="noopener noreferrer">Read source</a>
      `);

    const card = document.createElement("div");
    card.className = "news-card";

    card.innerHTML = `
      <span class="badge ${severityClass}">${item.severity}</span>
      <h3>${item.title}</h3>
      <p><strong>Location:</strong> ${item.location}</p>
      <p><strong>Date:</strong> ${item.pubDate}</p>
      <p>${item.description}</p>
      <a href="${item.link}" target="_blank" rel="noopener noreferrer">Read source</a>
    `;

    newsList.appendChild(card);
  });

  const bounds = markersLayer.getBounds();

  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [40, 40] });
  }
}

loadFloodNews();

setInterval(loadFloodNews, 30 * 60 * 1000);
