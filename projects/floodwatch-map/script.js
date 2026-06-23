"use strict";

/*
  FloodWatch Map
  ---------------------------------------------------------
  Static GitHub Pages-compatible implementation.

  Workflow:
  1. Load current flood articles from GDELT using JSONP.
  2. Avoid browser CORS/fetch failures.
  3. Keep articles published during the last 24 hours.
  4. Extract United States locations from headlines.
  5. Geocode locations with Open-Meteo.
  6. Plot locations on a Leaflet map.
  7. Refresh automatically every 15 minutes.
*/

const SETTINGS = {
  articleWindowHours: 24,
  refreshIntervalMs: 15 * 60 * 1000,
  gdeltTimeoutMs: 30000,
  geocodeTimeoutMs: 15000,
  maximumGdeltArticles: 100,
  maximumArticlesToGeocode: 40,
  maximumMappedArticles: 30,
  geocodeConcurrency: 4,
  geocodeCacheKey: "floodwatch-geocode-cache-v4",
  geocodeCacheLifetimeMs: 30 * 24 * 60 * 60 * 1000
};

/* -------------------------------------------------------
   REQUIRED PAGE ELEMENTS
------------------------------------------------------- */

const mapElement = document.getElementById("map");
const newsList = document.getElementById("news-list");

if (!mapElement) {
  throw new Error('The page must contain an element with id="map".');
}

if (!newsList) {
  throw new Error('The page must contain an element with id="news-list".');
}

if (typeof L === "undefined") {
  throw new Error(
    "Leaflet is not loaded. Make sure Leaflet loads before script.js."
  );
}

/* -------------------------------------------------------
   LEAFLET MAP
------------------------------------------------------- */

const map = L.map("map", {
  zoomControl: true,
  minZoom: 3
}).setView([39.8283, -98.5795], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);

/* -------------------------------------------------------
   SEARCH SETTINGS
------------------------------------------------------- */

const FLOOD_QUERY =
  '("flood" OR "flooding" OR "flash flood" OR "flood warning" OR "flood watch" OR "river flooding" OR "coastal flooding") sourcecountry:US';

const FLOOD_TERMS =
  /\b(flood|flooding|flooded|flash flood|river flooding|coastal flooding|flood warning|flood watch|inundation|inundated|high water|levee breach|dam break)\b/i;

const FALSE_POSITIVE_TERMS =
  /\bflood(?:ed|ing)?\s+(?:with|of)\s+(?:calls|comments|complaints|donations|emails|messages|orders|requests|support|tributes|visitors|votes)\b/i;

const HISTORICAL_TERMS =
  /\b(anniversary|archive|archived|flashback|historical|history of|last year|retrospective|years ago)\b/i;

/* -------------------------------------------------------
   UNITED STATES DATA
------------------------------------------------------- */

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
  (stateA, stateB) => stateB.length - stateA.length
);

const STATE_ABBREVIATION_PATTERN =
  Object.keys(STATE_ABBREVIATIONS).join("|");

const STATE_NAME_PATTERN = STATE_NAMES.map(escapeRegex).join("|");

/* -------------------------------------------------------
   APPLICATION STATE
------------------------------------------------------- */

let loading = false;
let lastSuccessfulUpdate = null;

const activeGeocodeRequests = new Map();

/* -------------------------------------------------------
   GENERAL HELPERS
------------------------------------------------------- */

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
  const temporaryElement = document.createElement("div");

  temporaryElement.innerHTML = String(value || "");

  return (temporaryElement.textContent || "")
    .replace(/\s+/g, " ")
    .trim();
}

function safeUrl(value) {
  try {
    const parsedUrl = new URL(String(value || ""));

    if (
      parsedUrl.protocol === "https:" ||
      parsedUrl.protocol === "http:"
    ) {
      return parsedUrl.href;
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

function createUniqueCallbackName() {
  return (
    "__floodwatchGdeltCallback_" +
    Date.now() +
    "_" +
    Math.random().toString(36).slice(2)
  );
}

/* -------------------------------------------------------
   GDELT JSONP

   JSONP uses a dynamically inserted script element.
   It does not use fetch(), so it avoids the browser
   cross-origin error shown in the screenshot.
------------------------------------------------------- */

function buildGdeltJsonpUrl(callbackName) {
  const parameters = new URLSearchParams({
    query: FLOOD_QUERY,
    mode: "ArtList",
    format: "jsonp",
    callback: callbackName,
    maxrecords: String(SETTINGS.maximumGdeltArticles),
    sort: "DateDesc",
    timespan: `${SETTINGS.articleWindowHours}h`,
    _: String(Date.now())
  });

  return (
    "https://api.gdeltproject.org/api/v2/doc/doc?" +
    parameters.toString()
  );
}

function fetchGdeltWithJsonp() {
  return new Promise((resolve, reject) => {
    const callbackName = createUniqueCallbackName();
    const scriptElement = document.createElement("script");

    let requestCompleted = false;

    const timeout = window.setTimeout(() => {
      if (requestCompleted) {
        return;
      }

      requestCompleted = true;
      cleanup();

      reject(
        new Error(
          "GDELT did not respond within 30 seconds. Please try again shortly."
        )
      );
    }, SETTINGS.gdeltTimeoutMs);

    function cleanup() {
      window.clearTimeout(timeout);

      if (scriptElement.parentNode) {
        scriptElement.parentNode.removeChild(scriptElement);
      }

      try {
        delete window[callbackName];
      } catch {
        window[callbackName] = undefined;
      }
    }

    window[callbackName] = function handleGdeltResponse(data) {
      if (requestCompleted) {
        return;
      }

      requestCompleted = true;
      cleanup();
      resolve(data);
    };

    scriptElement.src = buildGdeltJsonpUrl(callbackName);
    scriptElement.async = true;

    scriptElement.onerror = function handleGdeltError() {
      if (requestCompleted) {
        return;
      }

      requestCompleted = true;
      cleanup();

      reject(
        new Error(
          "The GDELT service could not be reached. This is usually a temporary GDELT connection problem."
        )
      );
    };

    document.head.appendChild(scriptElement);
  });
}

/* -------------------------------------------------------
   ARTICLE DATE PARSING
------------------------------------------------------- */

function parseArticleDate(value) {
  const rawDate = String(value || "").trim();

  if (!rawDate) {
    return null;
  }

  /*
    Common GDELT examples:
    20260623T041500Z
    20260623041500
  */

  const compactMatch = rawDate.match(
    /^(\d{4})(\d{2})(\d{2})T?(\d{2})(\d{2})(\d{2})(?:\.\d+)?Z?$/
  );

  if (compactMatch) {
    return new Date(
      Date.UTC(
        Number(compactMatch[1]),
        Number(compactMatch[2]) - 1,
        Number(compactMatch[3]),
        Number(compactMatch[4]),
        Number(compactMatch[5]),
        Number(compactMatch[6])
      )
    );
  }

  const parsedDate = new Date(rawDate);

  if (Number.isNaN(parsedDate.getTime())) {
    return null;
  }

  return parsedDate;
}

/* -------------------------------------------------------
   NORMALIZE GDELT ARTICLES
------------------------------------------------------- */

function normalizeGdeltArticles(data) {
  let records = [];

  if (Array.isArray(data?.articles)) {
    records = data.articles;
  } else if (Array.isArray(data?.items)) {
    records = data.items;
  } else if (Array.isArray(data)) {
    records = data;
  }

  return records
    .map((record) => {
      const url = safeUrl(
        record.url ||
          record.link ||
          record.external_url ||
          record.articleurl
      );

      const title = cleanText(
        record.title ||
          record.name ||
          record.headline
      );

      const date = parseArticleDate(
        record.seendate ||
          record.date ||
          record.pubDate ||
          record.date_published ||
          record.published
      );

      const domain =
        cleanText(record.domain) ||
        getDomain(url);

      return {
        title,
        url,
        date,
        domain
      };
    })
    .filter((article) => {
      return Boolean(
        article.title &&
          article.url &&
          article.date &&
          !Number.isNaN(article.date.getTime())
      );
    });
}

/* -------------------------------------------------------
   ARTICLE FILTERING
------------------------------------------------------- */

function isArticleFresh(article, currentTime) {
  const ageMilliseconds =
    currentTime.getTime() -
    article.date.getTime();

  const maximumAgeMilliseconds =
    SETTINGS.articleWindowHours *
    60 *
    60 *
    1000;

  const futureDateTolerance =
    -15 * 60 * 1000;

  return (
    ageMilliseconds >= futureDateTolerance &&
    ageMilliseconds <= maximumAgeMilliseconds
  );
}

function isHistoricalArticle(article, currentTime) {
  if (HISTORICAL_TERMS.test(article.title)) {
    return true;
  }

  const currentYear = currentTime.getUTCFullYear();

  const foundYears =
    `${article.title} ${article.url}`.match(/\b(?:19|20)\d{2}\b/g) || [];

  return foundYears.some((year) => {
    return Number(year) < currentYear;
  });
}

function removeDuplicateArticles(articles) {
  const knownUrls = new Set();
  const knownTitles = new Set();

  return articles.filter((article) => {
    const normalizedUrl = article.url
      .replace(/[?#].*$/, "")
      .replace(/\/$/, "")
      .toLowerCase();

    const normalizedTitle = article.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();

    if (
      knownUrls.has(normalizedUrl) ||
      knownTitles.has(normalizedTitle)
    ) {
      return false;
    }

    knownUrls.add(normalizedUrl);
    knownTitles.add(normalizedTitle);

    return true;
  });
}

async function getCurrentFloodArticles() {
  const data = await fetchGdeltWithJsonp();
  const currentTime = new Date();

  return removeDuplicateArticles(
    normalizeGdeltArticles(data)
      .filter((article) => isArticleFresh(article, currentTime))
      .filter((article) => !isHistoricalArticle(article, currentTime))
      .filter((article) => FLOOD_TERMS.test(article.title))
      .filter((article) => !FALSE_POSITIVE_TERMS.test(article.title))
      .sort((articleA, articleB) => {
        return articleB.date.getTime() - articleA.date.getTime();
      })
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

  const locationWords = location
    .split(/\s+/)
    .filter(Boolean);

  if (locationWords.length > 7) {
    location = locationWords.slice(-7).join(" ");
  }

  if (
    !location ||
    location.length < 2 ||
    location.length > 80
  ) {
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
    const cleanedCandidate =
      cleanLocationCandidate(candidate);

    if (!cleanedCandidate) {
      return;
    }

    const duplicate = candidates.some((existingCandidate) => {
      return (
        existingCandidate.toLowerCase() ===
        cleanedCandidate.toLowerCase()
      );
    });

    if (!duplicate) {
      candidates.push(cleanedCandidate);
    }
  }

  /*
    Example:
    Baltimore, MD
    Austin, TX
  */

  const cityStateAbbreviationRegex = new RegExp(
    `([A-Z][A-Za-z.'’\\-]*(?:\\s+(?:[A-Z][A-Za-z.'’\\-]*|of|the)){0,4}),\\s*(${STATE_ABBREVIATION_PATTERN})\\b`,
    "g"
  );

  for (const match of title.matchAll(cityStateAbbreviationRegex)) {
    const city = match[1];
    const state = STATE_ABBREVIATIONS[match[2]];

    addCandidate(`${city}, ${state}`);
  }

  /*
    Example:
    Baltimore, Maryland
    Austin, Texas
  */

  const cityStateNameRegex = new RegExp(
    `([A-Z][A-Za-z.'’\\-]*(?:\\s+(?:[A-Z][A-Za-z.'’\\-]*|of|the)){0,4}),\\s*(${STATE_NAME_PATTERN})\\b`,
    "gi"
  );

  for (const match of title.matchAll(cityStateNameRegex)) {
    addCandidate(`${match[1]}, ${match[2]}`);
  }

  /*
    Example:
    Flooding in Baltimore
    Flood warning near Houston
    High water across Louisiana
  */

  const prepositionLocationRegex =
    /\b(?:in|near|around|outside|across|throughout|for|along|from)\s+([^:;|–—-]{2,80})/gi;

  for (const match of title.matchAll(prepositionLocationRegex)) {
    addCandidate(match[1]);
  }

  /*
    Example:
    Flash flooding hits Houston
    Flooding threatens New Orleans
  */

  const impactLocationRegex =
    /\b(?:hits?|strikes?|swamps?|inundates?|threatens?|affects?)\s+([A-Z][^:;|–—-]{1,70})/g;

  for (const match of title.matchAll(impactLocationRegex)) {
    addCandidate(match[1]);
  }

  /*
    Search for complete state names anywhere in the headline.
  */

  const stateNameRegex = new RegExp(
    `\\b(${STATE_NAME_PATTERN})\\b`,
    "gi"
  );

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
    const cacheText = localStorage.getItem(
      SETTINGS.geocodeCacheKey
    );

    return cacheText ? JSON.parse(cacheText) : {};
  } catch {
    return {};
  }
}

function getCachedGeocode(query) {
  const cache = readGeocodeCache();
  const cacheEntry = cache[query.toLowerCase()];

  if (!cacheEntry) {
    return undefined;
  }

  const cacheAge =
    Date.now() - Number(cacheEntry.savedAt || 0);

  if (cacheAge > SETTINGS.geocodeCacheLifetimeMs) {
    return undefined;
  }

  return cacheEntry.value;
}

function saveGeocodeToCache(query, value) {
  try {
    const cache = readGeocodeCache();

    cache[query.toLowerCase()] = {
      savedAt: Date.now(),
      value
    };

    const trimmedEntries = Object.entries(cache)
      .sort((entryA, entryB) => {
        return (
          Number(entryB[1].savedAt || 0) -
          Number(entryA[1].savedAt || 0)
        );
      })
      .slice(0, 500);

    localStorage.setItem(
      SETTINGS.geocodeCacheKey,
      JSON.stringify(Object.fromEntries(trimmedEntries))
    );
  } catch (error) {
    console.warn("Unable to save geocoding cache.", error);
  }
}

/* -------------------------------------------------------
   UNITED STATES BOUNDARIES
------------------------------------------------------- */

function isInsideUnitedStates(latitude, longitude) {
  const continentalUnitedStates =
    latitude >= 24 &&
    latitude <= 50 &&
    longitude >= -125 &&
    longitude <= -66;

  const alaska =
    latitude >= 51 &&
    latitude <= 72 &&
    longitude >= -170 &&
    longitude <= -129;

  const hawaii =
    latitude >= 18 &&
    latitude <= 23 &&
    longitude >= -161 &&
    longitude <= -154;

  return (
    continentalUnitedStates ||
    alaska ||
    hawaii
  );
}

/* -------------------------------------------------------
   FETCH JSON FOR GEOCODING ONLY
------------------------------------------------------- */

async function fetchJson(url, timeoutMilliseconds) {
  const controller = new AbortController();

  const timeout = window.setTimeout(() => {
    controller.abort();
  }, timeoutMilliseconds);

  try {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(
        `Request returned HTTP ${response.status}.`
      );
    }

    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

/* -------------------------------------------------------
   OPEN-METEO GEOCODING
------------------------------------------------------- */

async function geocodeLocation(query) {
  const cachedResult = getCachedGeocode(query);

  if (cachedResult !== undefined) {
    return cachedResult;
  }

  const requestKey = query.toLowerCase();

  if (activeGeocodeRequests.has(requestKey)) {
    return activeGeocodeRequests.get(requestKey);
  }

  const geocodePromise = (async () => {
    try {
      const parameters = new URLSearchParams({
        name: query,
        count: "10",
        language: "en",
        format: "json",
        countryCode: "US"
      });

      const url =
        "https://geocoding-api.open-meteo.com/v1/search?" +
        parameters.toString();

      const data = await fetchJson(
        url,
        SETTINGS.geocodeTimeoutMs
      );

      const results = Array.isArray(data?.results)
        ? data.results.filter((result) => {
            return (
              String(result.country_code || "").toUpperCase() === "US"
            );
          })
        : [];

      const queryParts = query
        .toLowerCase()
        .split(",")
        .map((part) => part.trim());

      const requestedPlace = queryParts[0] || "";
      const requestedState = queryParts[1] || "";

      const rankedResults = results
        .map((result, originalIndex) => {
          const resultName = String(
            result.name || ""
          ).toLowerCase();

          const resultState = String(
            result.admin1 || ""
          ).toLowerCase();

          let score = -originalIndex;

          if (resultName === requestedPlace) {
            score += 100;
          } else if (
            resultName.includes(requestedPlace) ||
            requestedPlace.includes(resultName)
          ) {
            score += 40;
          }

          if (
            requestedState &&
            resultState === requestedState
          ) {
            score += 80;
          }

          if (
            String(result.feature_code || "").startsWith("PPL")
          ) {
            score += 20;
          }

          const population = Number(result.population || 0);

          if (population > 0) {
            score += Math.min(
              20,
              Math.log10(population + 1) * 2
            );
          }

          return {
            result,
            score
          };
        })
        .sort((resultA, resultB) => {
          return resultB.score - resultA.score;
        });

      const bestResult = rankedResults[0]?.result;

      if (!bestResult) {
        saveGeocodeToCache(query, null);
        return null;
      }

      const latitude = Number(bestResult.latitude);
      const longitude = Number(bestResult.longitude);

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
        name: cleanText(bestResult.name),
        state: cleanText(bestResult.admin1)
      };

      saveGeocodeToCache(query, location);

      return location;
    } catch (error) {
      console.warn(
        `Unable to geocode "${query}".`,
        error
      );

      /*
        A temporary network failure should not be cached,
        because a later refresh may succeed.
      */

      return null;
    } finally {
      activeGeocodeRequests.delete(requestKey);
    }
  })();

  activeGeocodeRequests.set(
    requestKey,
    geocodePromise
  );

  return geocodePromise;
}

/* -------------------------------------------------------
   MATCH ARTICLE TO LOCATION
------------------------------------------------------- */

async function locateArticle(article) {
  const locationCandidates =
    extractLocationCandidates(article.title);

  for (const locationCandidate of locationCandidates) {
    const location =
      await geocodeLocation(locationCandidate);

    if (location) {
      return {
        ...article,
        extractedLocation: locationCandidate,
        location
      };
    }
  }

  return null;
}

/* -------------------------------------------------------
   CONCURRENCY HELPER
------------------------------------------------------- */

async function processWithConcurrency(
  items,
  concurrencyLimit,
  worker
) {
  if (!items.length) {
    return [];
  }

  const results = new Array(items.length);
  let nextIndex = 0;

  async function runWorker() {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;

      try {
        results[currentIndex] = await worker(
          items[currentIndex],
          currentIndex
        );
      } catch (error) {
        console.warn(
          "An article could not be processed.",
          error
        );

        results[currentIndex] = null;
      }
    }
  }

  const numberOfWorkers = Math.min(
    concurrencyLimit,
    items.length
  );

  await Promise.all(
    Array.from(
      { length: numberOfWorkers },
      () => runWorker()
    )
  );

  return results;
}

/* -------------------------------------------------------
   SEVERITY
------------------------------------------------------- */

function getSeverity(title) {
  const normalizedTitle = title.toLowerCase();

  if (
    /\b(emergency|evacuation|evacuations|deadly|fatal|catastrophic|life-threatening|dam break|levee breach|flash flood warning)\b/i.test(
      normalizedTitle
    )
  ) {
    return "High";
  }

  if (
    /\b(warning|severe|major|flood watch|river flooding|coastal flooding|road closure|roads closed|state of emergency)\b/i.test(
      normalizedTitle
    )
  ) {
    return "Moderate";
  }

  return "Low";
}

function getSeverityRank(severity) {
  if (severity === "High") {
    return 3;
  }

  if (severity === "Moderate") {
    return 2;
  }

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

/* -------------------------------------------------------
   DISPLAY HELPERS
------------------------------------------------------- */

function formatLocationName(location) {
  const locationParts = [
    location.name,
    location.state
  ].filter(Boolean);

  return locationParts.join(", ");
}

function formatArticleAge(date) {
  const differenceInMinutes = Math.max(
    0,
    Math.floor(
      (Date.now() - date.getTime()) /
        (60 * 1000)
    )
  );

  if (differenceInMinutes < 60) {
    const minutes = Math.max(1, differenceInMinutes);

    return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }

  const differenceInHours = Math.floor(
    differenceInMinutes / 60
  );

  return `${differenceInHours} hour${
    differenceInHours === 1 ? "" : "s"
  } ago`;
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

/* -------------------------------------------------------
   RENDER MARKERS
------------------------------------------------------- */

function renderMarkers(mappedArticles) {
  markersLayer.clearLayers();

  const articlesByLocation = new Map();

  mappedArticles.forEach((article) => {
    const locationKey =
      article.location.latitude.toFixed(3) +
      "," +
      article.location.longitude.toFixed(3);

    if (!articlesByLocation.has(locationKey)) {
      articlesByLocation.set(locationKey, []);
    }

    articlesByLocation
      .get(locationKey)
      .push(article);
  });

  articlesByLocation.forEach((locationArticles) => {
    const firstArticle = locationArticles[0];

    const highestSeverity = locationArticles
      .map((article) => getSeverity(article.title))
      .sort((severityA, severityB) => {
        return (
          getSeverityRank(severityB) -
          getSeverityRank(severityA)
        );
      })[0];

    const popupArticleLinks = locationArticles
      .slice(0, 6)
      .map((article) => {
        return `
          <li style="margin-bottom: 8px;">
            <a
              href="${escapeHtml(article.url)}"
              target="_blank"
              rel="noopener noreferrer"
            >
              ${escapeHtml(article.title)}
            </a>
          </li>
        `;
      })
      .join("");

    const popupHtml = `
      <div style="min-width: 230px;">
        <strong>
          ${escapeHtml(
            formatLocationName(firstArticle.location)
          )}
        </strong>

        <p style="margin: 6px 0;">
          Severity:
          <strong>${escapeHtml(highestSeverity)}</strong>
        </p>

        <ul style="padding-left: 18px; margin-bottom: 4px;">
          ${popupArticleLinks}
        </ul>
      </div>
    `;

    L.circleMarker(
      [
        firstArticle.location.latitude,
        firstArticle.location.longitude
      ],
      getMarkerStyle(highestSeverity)
    )
      .addTo(markersLayer)
      .bindPopup(popupHtml);
  });
}

/* -------------------------------------------------------
   RENDER NEWS CARDS
------------------------------------------------------- */

function renderNewsCards(
  mappedArticles,
  totalFreshArticles
) {
  newsList.innerHTML = "";

  if (!mappedArticles.length) {
    newsList.innerHTML = `
      <article class="news-card">
        <h3>No mappable flood stories found</h3>

        <p>
          ${totalFreshArticles} current flood-related
          ${
            totalFreshArticles === 1
              ? "article was"
              : "articles were"
          }
          found, but no clear United States location could
          be extracted from the available headlines.
        </p>

        <p>
          The page will check again automatically.
        </p>
      </article>
    `;

    return;
  }

  mappedArticles.forEach((article) => {
    const severity = getSeverity(article.title);
    const card = document.createElement("article");

    card.className = "news-card";

    card.innerHTML = `
      <span class="badge ${severity.toLowerCase()}">
        ${escapeHtml(severity)}
      </span>

      <h3>
        ${escapeHtml(article.title)}
      </h3>

      <p>
        <strong>Mapped location:</strong>
        ${escapeHtml(
          formatLocationName(article.location)
        )}
      </p>

      <p>
        <strong>Source:</strong>
        ${escapeHtml(article.domain)}
        <br>

        <strong>Published:</strong>
        ${escapeHtml(formatDate(article.date))}
        <br>

        <strong>Age:</strong>
        ${escapeHtml(formatArticleAge(article.date))}
      </p>

      <a
        href="${escapeHtml(article.url)}"
        target="_blank"
        rel="noopener noreferrer"
      >
        Read source
      </a>
    `;

    newsList.appendChild(card);
  });

  const updateInformation = document.createElement("p");

  updateInformation.className = "feed-update-information";

  updateInformation.innerHTML = `
    <small>
      Showing ${mappedArticles.length} mapped article${
        mappedArticles.length === 1 ? "" : "s"
      }
      from the last ${SETTINGS.articleWindowHours} hours.
      Last updated:
      ${escapeHtml(
        lastSuccessfulUpdate
          ? formatDate(lastSuccessfulUpdate)
          : "just now"
      )}.
      The feed refreshes every 15 minutes.
    </small>
  `;

  newsList.appendChild(updateInformation);
}

/* -------------------------------------------------------
   RENDER COMPLETE RESULTS
------------------------------------------------------- */

function renderFloodNews(
  mappedArticles,
  totalFreshArticles
) {
  renderMarkers(mappedArticles);
  renderNewsCards(
    mappedArticles,
    totalFreshArticles
  );

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
   LOAD NEWS
------------------------------------------------------- */

async function loadFloodNews() {
  if (loading) {
    return;
  }

  loading = true;

  newsList.innerHTML = `
    <article class="news-card">
      <h3>Loading live flood news</h3>

      <p>
        Searching for current United States flood reports
        from the last ${SETTINGS.articleWindowHours} hours...
      </p>
    </article>
  `;

  try {
    const freshArticles =
      await getCurrentFloodArticles();

    const articlesToGeocode =
      freshArticles.slice(
        0,
        SETTINGS.maximumArticlesToGeocode
      );

    const geocodedResults =
      await processWithConcurrency(
        articlesToGeocode,
        SETTINGS.geocodeConcurrency,
        locateArticle
      );

    const mappedArticles = geocodedResults
      .filter(Boolean)
      .sort((articleA, articleB) => {
        return (
          articleB.date.getTime() -
          articleA.date.getTime()
        );
      })
      .slice(
        0,
        SETTINGS.maximumMappedArticles
      );

    lastSuccessfulUpdate = new Date();

    renderFloodNews(
      mappedArticles,
      freshArticles.length
    );
  } catch (error) {
    console.error(
      "FloodWatch loading error:",
      error
    );

    markersLayer.clearLayers();

    newsList.innerHTML = `
      <article class="news-card">
        <h3>Unable to load the live flood feed</h3>

        <p>
          ${escapeHtml(
            error.message ||
              "The live news service could not be reached."
          )}
        </p>

        <button
          id="retry-flood-news"
          type="button"
          style="
            margin-top: 10px;
            padding: 10px 16px;
            border: 0;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 700;
          "
        >
          Try again
        </button>
      </article>
    `;

    const retryButton = document.getElementById(
      "retry-flood-news"
    );

    if (retryButton) {
      retryButton.addEventListener(
        "click",
        loadFloodNews
      );
    }
  } finally {
    loading = false;
  }
}

/* -------------------------------------------------------
   INITIAL LOAD AND AUTOMATIC REFRESH
------------------------------------------------------- */

loadFloodNews();

window.setInterval(
  loadFloodNews,
  SETTINGS.refreshIntervalMs
);

/*
  Refresh when the user returns to the browser tab,
  provided the last successful update is older than
  the configured refresh interval.
*/

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") {
    return;
  }

  if (!lastSuccessfulUpdate) {
    loadFloodNews();
    return;
  }

  const timeSinceLastUpdate =
    Date.now() -
    lastSuccessfulUpdate.getTime();

  if (
    timeSinceLastUpdate >=
    SETTINGS.refreshIntervalMs
  ) {
    loadFloodNews();
  }
});
