"use strict";

/*
  FloodWatch Map
  -------------------------------------------------------
  Static GitHub Pages compatible version.

  Pipeline:
  1. Fetch recent flood-related news from Google News RSS.
  2. Convert RSS to JSON using rss2json.
  3. Fallback to AllOrigins + XML parsing if needed.
  4. Filter to the last 24 hours.
  5. Extract U.S. locations from headlines.
  6. Geocode those locations.
  7. Plot markers on the map.
  8. Refresh every 15 minutes.
*/

const SETTINGS = {
  articleWindowHours: 24,
  refreshIntervalMs: 15 * 60 * 1000,
  feedTimeoutMs: 20000,
  geocodeTimeoutMs: 15000,
  maxArticles: 60,
  maxArticlesToGeocode: 35,
  maxMappedArticles: 25,
  geocodeConcurrency: 4,
  geocodeCacheKey: "floodwatch-geocode-cache-v5",
  geocodeCacheLifetimeMs: 30 * 24 * 60 * 60 * 1000
};

const FEED_QUERY =
  '("flood" OR "flooding" OR "flash flood" OR "flood warning" OR "flood watch" OR "river flooding" OR "coastal flooding") when:1d';

const GOOGLE_NEWS_RSS_URL =
  "https://news.google.com/rss/search?q=" +
  encodeURIComponent(FEED_QUERY) +
  "&hl=en-US&gl=US&ceid=US:en";

const RSS2JSON_URL =
  "https://api.rss2json.com/v1/api.json?rss_url=" +
  encodeURIComponent(GOOGLE_NEWS_RSS_URL);

const FLOOD_TERMS =
  /\b(flood|flooding|flooded|flash flood|river flooding|coastal flooding|flood warning|flood watch|inundation|high water|levee breach|dam break)\b/i;

const FALSE_POSITIVE_TERMS =
  /\bflood(?:ed|ing)?\s+(?:with|of)\s+(?:calls|comments|complaints|donations|emails|messages|orders|requests|support|tributes|visitors|votes)\b/i;

const HISTORICAL_TERMS =
  /\b(anniversary|archive|archived|flashback|historical|history of|last year|retrospective|years ago)\b/i;

const STATE_ABBREVIATIONS = Object.freeze({
  AL: "Alabama",
  AK: "Alaska",
  AZ: "Arizona",
  AR: "Arkansas",
  CA: "California",
  CO: "Colorado",
  CT: "Connecticut",
  DE: "Delaware",
  DC: "District of Columbia",
  FL: "Florida",
  GA: "Georgia",
  HI: "Hawaii",
  ID: "Idaho",
  IL: "Illinois",
  IN: "Indiana",
  IA: "Iowa",
  KS: "Kansas",
  KY: "Kentucky",
  LA: "Louisiana",
  ME: "Maine",
  MD: "Maryland",
  MA: "Massachusetts",
  MI: "Michigan",
  MN: "Minnesota",
  MS: "Mississippi",
  MO: "Missouri",
  MT: "Montana",
  NE: "Nebraska",
  NV: "Nevada",
  NH: "New Hampshire",
  NJ: "New Jersey",
  NM: "New Mexico",
  NY: "New York",
  NC: "North Carolina",
  ND: "North Dakota",
  OH: "Ohio",
  OK: "Oklahoma",
  OR: "Oregon",
  PA: "Pennsylvania",
  RI: "Rhode Island",
  SC: "South Carolina",
  SD: "South Dakota",
  TN: "Tennessee",
  TX: "Texas",
  UT: "Utah",
  VT: "Vermont",
  VA: "Virginia",
  WA: "Washington",
  WV: "West Virginia",
  WI: "Wisconsin",
  WY: "Wyoming"
});

const STATE_NAMES = Object.values(STATE_ABBREVIATIONS).sort(
  (a, b) => b.length - a.length
);

const STATE_ABBREVIATION_PATTERN = Object.keys(STATE_ABBREVIATIONS).join("|");
const STATE_NAME_PATTERN = STATE_NAMES.map(escapeRegex).join("|");

const mapElement = document.getElementById("map");
const newsList = document.getElementById("news-list");

if (!mapElement) {
  throw new Error('The page must contain an element with id="map".');
}

if (!newsList) {
  throw new Error('The page must contain an element with id="news-list".');
}

if (typeof L === "undefined") {
  throw new Error("Leaflet is not loaded before script.js.");
}

const map = L.map("map", {
  zoomControl: true,
  minZoom: 3
}).setView([39.8283, -98.5795], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);

let loading = false;
let lastSuccessfulUpdate = null;
const activeGeocodeRequests = new Map();

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function cleanText(value) {
  const div = document.createElement("div");
  div.innerHTML = String(value || "");
  return (div.textContent || div.innerText || "")
    .replace(/\s+/g, " ")
    .trim();
}

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol === "http:" || url.protocol === "https:") {
      return url.href;
    }
    return "";
  } catch {
    return "";
  }
}

function getDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return "Unknown source";
  }
}

function stripGoogleNewsSourceSuffix(title) {
  const cleaned = cleanText(title);
  return cleaned.replace(/\s*-\s*[^-]+$/, "").trim();
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

async function fetchJson(url, timeoutMs) {
  const controller = new AbortController();

  const timer = window.setTimeout(() => {
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

async function fetchText(url, timeoutMs) {
  const controller = new AbortController();

  const timer = window.setTimeout(() => {
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.text();
  } finally {
    window.clearTimeout(timer);
  }
}

/* -------------------------------------------------------
   FEED FETCHING
------------------------------------------------------- */

async function fetchArticlesFromRss2Json() {
  const data = await fetchJson(RSS2JSON_URL, SETTINGS.feedTimeoutMs);

  const items = Array.isArray(data?.items) ? data.items : [];

  return items.map((item) => {
    const title = stripGoogleNewsSourceSuffix(item.title || "");
    const url = safeUrl(item.link || "");
    const date = parseDate(item.pubDate);
    const source =
      cleanText(item.author || "") ||
      getDomain(url);

    return {
      title,
      url,
      date,
      domain: source
    };
  });
}

async function fetchArticlesFromAllOriginsXml() {
  const proxyUrl =
    "https://api.allorigins.win/raw?url=" +
    encodeURIComponent(GOOGLE_NEWS_RSS_URL);

  const xmlText = await fetchText(proxyUrl, SETTINGS.feedTimeoutMs);

  const parser = new DOMParser();
  const xml = parser.parseFromString(xmlText, "text/xml");
  const items = Array.from(xml.querySelectorAll("item"));

  return items.map((item) => {
    const title = stripGoogleNewsSourceSuffix(
      item.querySelector("title")?.textContent || ""
    );
    const url = safeUrl(item.querySelector("link")?.textContent || "");
    const date = parseDate(item.querySelector("pubDate")?.textContent || "");
    const source = getDomain(url);

    return {
      title,
      url,
      date,
      domain: source
    };
  });
}

async function fetchFloodArticles() {
  try {
    return await fetchArticlesFromRss2Json();
  } catch (error) {
    console.warn("rss2json failed, trying AllOrigins XML fallback...", error);
    return await fetchArticlesFromAllOriginsXml();
  }
}

/* -------------------------------------------------------
   ARTICLE FILTERING
------------------------------------------------------- */

function isFreshArticle(article, now) {
  if (!article.date) return false;

  const ageMs = now.getTime() - article.date.getTime();
  const maxAgeMs = SETTINGS.articleWindowHours * 60 * 60 * 1000;
  const futureToleranceMs = -15 * 60 * 1000;

  return ageMs >= futureToleranceMs && ageMs <= maxAgeMs;
}

function isHistoricalArticle(article, now) {
  if (HISTORICAL_TERMS.test(article.title)) return true;

  const currentYear = now.getUTCFullYear();
  const matches = `${article.title} ${article.url}`.match(/\b(?:19|20)\d{2}\b/g) || [];

  return matches.some((year) => Number(year) < currentYear);
}

function removeDuplicateArticles(articles) {
  const seenUrls = new Set();
  const seenTitles = new Set();

  return articles.filter((article) => {
    const normalizedUrl = article.url
      .replace(/[?#].*$/, "")
      .replace(/\/$/, "")
      .toLowerCase();

    const normalizedTitle = article.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();

    if (seenUrls.has(normalizedUrl) || seenTitles.has(normalizedTitle)) {
      return false;
    }

    seenUrls.add(normalizedUrl);
    seenTitles.add(normalizedTitle);

    return true;
  });
}

async function getCurrentFloodArticles() {
  const now = new Date();

  const articles = await fetchFloodArticles();

  return removeDuplicateArticles(
    articles
      .filter((article) => article.title && article.url && article.date)
      .filter((article) => isFreshArticle(article, now))
      .filter((article) => !isHistoricalArticle(article, now))
      .filter((article) => FLOOD_TERMS.test(article.title))
      .filter((article) => !FALSE_POSITIVE_TERMS.test(article.title))
      .sort((a, b) => b.date.getTime() - a.date.getTime())
      .slice(0, SETTINGS.maxArticles)
  );
}

/* -------------------------------------------------------
   LOCATION EXTRACTION
------------------------------------------------------- */

function cleanLocationCandidate(value) {
  let location = cleanText(value)
    .replace(/^[\s,;:|–—-]+/, "")
    .replace(/[\s,;:|–—-]+$/, "")
    .replace(/^the\s+/i, "")
    .replace(/[.!?].*$/, "")
    .replace(
      /\b(after|amid|as|because|causing|due|following|forces?|hits?|leaves?|prompts?|strikes?|threatens?|under|when|where|while|with)\b.*$/i,
      ""
    )
    .trim();

  const words = location.split(/\s+/).filter(Boolean);

  if (words.length > 7) {
    location = words.slice(-7).join(" ");
  }

  if (!location || location.length < 2 || location.length > 80) {
    return "";
  }

  if (
    /\b(flood|flooding|warning|watch|storm|rain|weather|residents|officials|people|homes|roads)\b/i.test(
      location
    )
  ) {
    return "";
  }

  return location;
}

function extractLocationCandidates(title) {
  const candidates = [];

  function addCandidate(candidate) {
    const cleaned = cleanLocationCandidate(candidate);

    if (!cleaned) return;

    const exists = candidates.some(
      (value) => value.toLowerCase() === cleaned.toLowerCase()
    );

    if (!exists) {
      candidates.push(cleaned);
    }
  }

  const cityStateAbbreviationRegex = new RegExp(
    `([A-Z][A-Za-z.'’\\-]*(?:\\s+(?:[A-Z][A-Za-z.'’\\-]*|of|the)){0,4}),\\s*(${STATE_ABBREVIATION_PATTERN})\\b`,
    "g"
  );

  for (const match of title.matchAll(cityStateAbbreviationRegex)) {
    const city = match[1];
    const state = STATE_ABBREVIATIONS[match[2]];
    addCandidate(`${city}, ${state}`);
  }

  const cityStateNameRegex = new RegExp(
    `([A-Z][A-Za-z.'’\\-]*(?:\\s+(?:[A-Z][A-Za-z.'’\\-]*|of|the)){0,4}),\\s*(${STATE_NAME_PATTERN})\\b`,
    "gi"
  );

  for (const match of title.matchAll(cityStateNameRegex)) {
    addCandidate(`${match[1]}, ${match[2]}`);
  }

  const prepositionRegex =
    /\b(?:in|near|around|outside|across|throughout|for|along|from)\s+([^:;|–—-]{2,80})/gi;

  for (const match of title.matchAll(prepositionRegex)) {
    addCandidate(match[1]);
  }

  const impactRegex =
    /\b(?:hits?|strikes?|swamps?|inundates?|threatens?|affects?)\s+([A-Z][^:;|–—-]{1,70})/g;

  for (const match of title.matchAll(impactRegex)) {
    addCandidate(match[1]);
  }

  const stateNameRegex = new RegExp(`\\b(${STATE_NAME_PATTERN})\\b`, "gi");

  for (const match of title.matchAll(stateNameRegex)) {
    addCandidate(match[1]);
  }

  return candidates.slice(0, 5);
}

/* -------------------------------------------------------
   GEOCODING CACHE
------------------------------------------------------- */

function readGeocodeCache() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS.geocodeCacheKey) || "{}");
  } catch {
    return {};
  }
}

function getCachedGeocode(query) {
  const cache = readGeocodeCache();
  const entry = cache[query.toLowerCase()];

  if (!entry) return undefined;

  const age = Date.now() - Number(entry.savedAt || 0);

  if (age > SETTINGS.geocodeCacheLifetimeMs) {
    return undefined;
  }

  return entry.value;
}

function saveGeocodeToCache(query, value) {
  try {
    const cache = readGeocodeCache();

    cache[query.toLowerCase()] = {
      savedAt: Date.now(),
      value
    };

    const trimmed = Object.entries(cache)
      .sort((a, b) => Number(b[1].savedAt || 0) - Number(a[1].savedAt || 0))
      .slice(0, 500);

    localStorage.setItem(
      SETTINGS.geocodeCacheKey,
      JSON.stringify(Object.fromEntries(trimmed))
    );
  } catch (error) {
    console.warn("Could not save geocode cache.", error);
  }
}

function isInsideUnitedStates(lat, lon) {
  const continental =
    lat >= 24 && lat <= 50 && lon >= -125 && lon <= -66;

  const alaska =
    lat >= 51 && lat <= 72 && lon >= -170 && lon <= -129;

  const hawaii =
    lat >= 18 && lat <= 23 && lon >= -161 && lon <= -154;

  return continental || alaska || hawaii;
}

/* -------------------------------------------------------
   GEOCODING
------------------------------------------------------- */

async function geocodeLocation(query) {
  const cached = getCachedGeocode(query);

  if (cached !== undefined) {
    return cached;
  }

  const requestKey = query.toLowerCase();

  if (activeGeocodeRequests.has(requestKey)) {
    return activeGeocodeRequests.get(requestKey);
  }

  const promise = (async () => {
    try {
      const params = new URLSearchParams({
        name: query,
        count: "10",
        language: "en",
        format: "json",
        countryCode: "US"
      });

      const url =
        "https://geocoding-api.open-meteo.com/v1/search?" +
        params.toString();

      const data = await fetchJson(url, SETTINGS.geocodeTimeoutMs);

      const results = Array.isArray(data?.results)
        ? data.results.filter(
            (item) => String(item.country_code || "").toUpperCase() === "US"
          )
        : [];

      const queryParts = query
        .toLowerCase()
        .split(",")
        .map((part) => part.trim());

      const requestedPlace = queryParts[0] || "";
      const requestedState = queryParts[1] || "";

      const ranked = results
        .map((item, index) => {
          const resultName = String(item.name || "").toLowerCase();
          const resultState = String(item.admin1 || "").toLowerCase();

          let score = -index;

          if (resultName === requestedPlace) {
            score += 100;
          } else if (
            resultName.includes(requestedPlace) ||
            requestedPlace.includes(resultName)
          ) {
            score += 40;
          }

          if (requestedState && resultState === requestedState) {
            score += 80;
          }

          if (String(item.feature_code || "").startsWith("PPL")) {
            score += 20;
          }

          const population = Number(item.population || 0);
          if (population > 0) {
            score += Math.min(20, Math.log10(population + 1) * 2);
          }

          return { item, score };
        })
        .sort((a, b) => b.score - a.score);

      const best = ranked[0]?.item;

      if (!best) {
        saveGeocodeToCache(query, null);
        return null;
      }

      const latitude = Number(best.latitude);
      const longitude = Number(best.longitude);

      if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude) ||
        !isInsideUnitedStates(latitude, longitude)
      ) {
        saveGeocodeToCache(query, null);
        return null;
      }

      const location = {
        latitude,
        longitude,
        name: cleanText(best.name),
        state: cleanText(best.admin1)
      };

      saveGeocodeToCache(query, location);
      return location;
    } catch (error) {
      console.warn(`Unable to geocode "${query}".`, error);
      return null;
    } finally {
      activeGeocodeRequests.delete(requestKey);
    }
  })();

  activeGeocodeRequests.set(requestKey, promise);
  return promise;
}

async function locateArticle(article) {
  const candidates = extractLocationCandidates(article.title);

  for (const candidate of candidates) {
    const location = await geocodeLocation(candidate);

    if (location) {
      return {
        ...article,
        extractedLocation: candidate,
        location
      };
    }
  }

  return null;
}

async function processWithConcurrency(items, limit, worker) {
  if (!items.length) return [];

  const results = new Array(items.length);
  let nextIndex = 0;

  async function runWorker() {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;

      try {
        results[currentIndex] = await worker(items[currentIndex], currentIndex);
      } catch (error) {
        console.warn("Unable to process article.", error);
        results[currentIndex] = null;
      }
    }
  }

  const workerCount = Math.min(limit, items.length);

  await Promise.all(
    Array.from({ length: workerCount }, () => runWorker())
  );

  return results;
}

/* -------------------------------------------------------
   SEVERITY + FORMATTING
------------------------------------------------------- */

function getSeverity(title) {
  const lower = title.toLowerCase();

  if (
    /\b(emergency|evacuation|evacuations|deadly|fatal|catastrophic|life-threatening|dam break|levee breach|flash flood warning)\b/i.test(
      lower
    )
  ) {
    return "High";
  }

  if (
    /\b(warning|severe|major|flood watch|river flooding|coastal flooding|road closure|roads closed|state of emergency)\b/i.test(
      lower
    )
  ) {
    return "Moderate";
  }

  return "Low";
}

function getSeverityRank(severity) {
  if (severity === "High") return 3;
  if (severity === "Moderate") return 2;
  return 1;
}

function getMarkerStyle(severity) {
  if (severity === "High") {
    return {
      radius: 9,
      color: "#7f1d1d",
      fillColor: "#dc2626",
      fillOpacity: 0.92,
      weight: 2
    };
  }

  if (severity === "Moderate") {
    return {
      radius: 8,
      color: "#9a3412",
      fillColor: "#f97316",
      fillOpacity: 0.9,
      weight: 2
    };
  }

  return {
    radius: 7,
    color: "#1e3a8a",
    fillColor: "#2563eb",
    fillOpacity: 0.86,
    weight: 2
  };
}

function formatLocationName(location) {
  return [location.name, location.state].filter(Boolean).join(", ");
}

function formatDate(date) {
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function formatAge(date) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - date.getTime()) / (60 * 1000))
  );

  if (minutes < 60) {
    const m = Math.max(1, minutes);
    return `${m} minute${m === 1 ? "" : "s"} ago`;
  }

  const hours = Math.floor(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}

/* -------------------------------------------------------
   RENDERING
------------------------------------------------------- */

function renderMarkers(mappedArticles) {
  markersLayer.clearLayers();

  const grouped = new Map();

  mappedArticles.forEach((article) => {
    const key =
      article.location.latitude.toFixed(3) +
      "," +
      article.location.longitude.toFixed(3);

    if (!grouped.has(key)) {
      grouped.set(key, []);
    }

    grouped.get(key).push(article);
  });

  grouped.forEach((articles) => {
    const first = articles[0];

    const topSeverity = articles
      .map((article) => getSeverity(article.title))
      .sort((a, b) => getSeverityRank(b) - getSeverityRank(a))[0];

    const popupItems = articles
      .slice(0, 6)
      .map((article) => {
        return `
          <li style="margin-bottom:8px;">
            <a href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">
              ${escapeHtml(article.title)}
            </a>
          </li>
        `;
      })
      .join("");

    const popupHtml = `
      <div style="min-width:230px;">
        <strong>${escapeHtml(formatLocationName(first.location))}</strong>
        <p style="margin:6px 0;">
          Severity: <strong>${escapeHtml(topSeverity)}</strong>
        </p>
        <ul style="padding-left:18px; margin-bottom:4px;">
          ${popupItems}
        </ul>
      </div>
    `;

    L.circleMarker(
      [first.location.latitude, first.location.longitude],
      getMarkerStyle(topSeverity)
    )
      .addTo(markersLayer)
      .bindPopup(popupHtml);
  });
}

function renderNewsCards(mappedArticles, totalFreshArticles) {
  newsList.innerHTML = "";

  if (!mappedArticles.length) {
    newsList.innerHTML = `
      <article class="news-card">
        <h3>No mappable flood stories found</h3>
        <p>
          ${totalFreshArticles} current flood-related ${
      totalFreshArticles === 1 ? "article was" : "articles were"
    } found, but no clear U.S. location could be extracted from the available headlines.
        </p>
        <p>The page will check again automatically.</p>
      </article>
    `;
    return;
  }

  mappedArticles.forEach((article) => {
    const severity = getSeverity(article.title);
    const card = document.createElement("article");

    card.className = "news-card";

    card.innerHTML = `
      <span class="badge ${severity.toLowerCase()}">${escapeHtml(severity)}</span>
      <h3>${escapeHtml(article.title)}</h3>
      <p>
        <strong>Mapped location:</strong>
        ${escapeHtml(formatLocationName(article.location))}
      </p>
      <p>
        <strong>Source:</strong>
        ${escapeHtml(article.domain)}
        <br>
        <strong>Published:</strong>
        ${escapeHtml(formatDate(article.date))}
        <br>
        <strong>Age:</strong>
        ${escapeHtml(formatAge(article.date))}
      </p>
      <a href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">
        Read source
      </a>
    `;

    newsList.appendChild(card);
  });

  const updateInfo = document.createElement("p");
  updateInfo.className = "feed-update-information";
  updateInfo.innerHTML = `
    <small>
      Showing ${mappedArticles.length} mapped article${
    mappedArticles.length === 1 ? "" : "s"
  } from the last ${SETTINGS.articleWindowHours} hours.
      Last updated: ${escapeHtml(
        lastSuccessfulUpdate ? formatDate(lastSuccessfulUpdate) : "just now"
      )}.
      The feed refreshes every 15 minutes.
    </small>
  `;

  newsList.appendChild(updateInfo);
}

function renderFloodNews(mappedArticles, totalFreshArticles) {
  renderMarkers(mappedArticles);
  renderNewsCards(mappedArticles, totalFreshArticles);

  const bounds = markersLayer.getBounds();

  if (bounds.isValid()) {
    map.fitBounds(bounds, {
      padding: [40, 40],
      maxZoom: 8
    });
  } else {
    map.setView([39.8283, -98.5795], 4);
  }
}

/* -------------------------------------------------------
   MAIN LOADER
------------------------------------------------------- */

async function loadFloodNews() {
  if (loading) return;

  loading = true;

  newsList.innerHTML = `
    <article class="news-card">
      <h3>Loading live flood news</h3>
      <p>
        Searching for current United States flood reports from the last
        ${SETTINGS.articleWindowHours} hours...
      </p>
    </article>
  `;

  try {
    const freshArticles = await getCurrentFloodArticles();

    const articlesToGeocode = freshArticles.slice(
      0,
      SETTINGS.maxArticlesToGeocode
    );

    const results = await processWithConcurrency(
      articlesToGeocode,
      SETTINGS.geocodeConcurrency,
      locateArticle
    );

    const mappedArticles = results
      .filter(Boolean)
      .sort((a, b) => b.date.getTime() - a.date.getTime())
      .slice(0, SETTINGS.maxMappedArticles);

    lastSuccessfulUpdate = new Date();

    renderFloodNews(mappedArticles, freshArticles.length);
  } catch (error) {
    console.error("FloodWatch loading error:", error);

    markersLayer.clearLayers();

    newsList.innerHTML = `
      <article class="news-card">
        <h3>Unable to load the live flood feed</h3>
        <p>
          ${
            escapeHtml(error.message) ||
            "The live news service could not be reached."
          }
        </p>
        <button
          id="retry-flood-news"
          type="button"
          style="
            margin-top:10px;
            padding:10px 16px;
            border:0;
            border-radius:8px;
            cursor:pointer;
            font-weight:700;
          "
        >
          Try again
        </button>
      </article>
    `;

    const retryButton = document.getElementById("retry-flood-news");
    if (retryButton) {
      retryButton.addEventListener("click", loadFloodNews);
    }
  } finally {
    loading = false;
  }
}

/* -------------------------------------------------------
   STARTUP
------------------------------------------------------- */

loadFloodNews();

window.setInterval(loadFloodNews, SETTINGS.refreshIntervalMs);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;

  if (!lastSuccessfulUpdate) {
    loadFloodNews();
    return;
  }

  const age = Date.now() - lastSuccessfulUpdate.getTime();

  if (age >= SETTINGS.refreshIntervalMs) {
    loadFloodNews();
  }
});
