"use strict";

/*
  FloodWatch Map
  -------------------------------------------------------
  Static GitHub Pages version.

  Pipeline:
  1. Read flood headlines from Google News RSS.
  2. Try several browser-friendly RSS gateways.
  3. Keep only genuinely recent articles.
  4. Extract a United States city, county, region, or state.
  5. Geocode city-level locations with Open-Meteo.
  6. Fall back to built-in state coordinates when necessary.
  7. Plot Leaflet markers and refresh every 15 minutes.
*/

const SETTINGS = Object.freeze({
  articleWindowHours: 24,
  refreshIntervalMs: 15 * 60 * 1000,
  feedTimeoutMs: 20000,
  geocodeTimeoutMs: 15000,
  maxArticles: 80,
  maxArticlesToGeocode: 40,
  maxMappedArticles: 30,
  geocodeConcurrency: 3,
  geocodeCacheKey: "floodwatch-geocode-cache-v7",
  geocodeCacheLifetimeMs: 30 * 24 * 60 * 60 * 1000,
  failedGeocodeCacheLifetimeMs: 3 * 60 * 60 * 1000
});

const FEED_QUERY =
  '(flood OR flooding OR "flash flood" OR "flood warning" OR "flood watch" OR "river flooding" OR "coastal flooding" OR inundation OR "high water") when:1d';

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

/*
  Approximate state centers are used only when a headline identifies
  a state but does not provide a reliable city-level location.
*/
const STATE_CENTERS = Object.freeze({
  Alabama: [32.8067, -86.7911],
  Alaska: [61.3707, -152.4044],
  Arizona: [33.7298, -111.4312],
  Arkansas: [34.9697, -92.3731],
  California: [36.1162, -119.6816],
  Colorado: [39.0598, -105.3111],
  Connecticut: [41.5978, -72.7554],
  Delaware: [39.3185, -75.5071],
  "District of Columbia": [38.9072, -77.0369],
  Florida: [27.7663, -81.6868],
  Georgia: [33.0406, -83.6431],
  Hawaii: [21.0943, -157.4983],
  Idaho: [44.2405, -114.4788],
  Illinois: [40.3495, -88.9861],
  Indiana: [39.8494, -86.2583],
  Iowa: [42.0115, -93.2105],
  Kansas: [38.5266, -96.7265],
  Kentucky: [37.6681, -84.6701],
  Louisiana: [31.1695, -91.8678],
  Maine: [44.6939, -69.3819],
  Maryland: [39.0639, -76.8021],
  Massachusetts: [42.2302, -71.5301],
  Michigan: [43.3266, -84.5361],
  Minnesota: [45.6945, -93.9002],
  Mississippi: [32.7416, -89.6787],
  Missouri: [38.4561, -92.2884],
  Montana: [46.9219, -110.4544],
  Nebraska: [41.1254, -98.2681],
  Nevada: [38.3135, -117.0554],
  "New Hampshire": [43.4525, -71.5639],
  "New Jersey": [40.2989, -74.521],
  "New Mexico": [34.8405, -106.2485],
  "New York": [42.1657, -74.9481],
  "North Carolina": [35.6301, -79.8064],
  "North Dakota": [47.5289, -99.784],
  Ohio: [40.3888, -82.7649],
  Oklahoma: [35.5653, -96.9289],
  Oregon: [44.572, -122.0709],
  Pennsylvania: [40.5908, -77.2098],
  "Rhode Island": [41.6809, -71.5118],
  "South Carolina": [33.8569, -80.945],
  "South Dakota": [44.2998, -99.4388],
  Tennessee: [35.7478, -86.6923],
  Texas: [31.0545, -97.5635],
  Utah: [40.15, -111.8624],
  Vermont: [44.0459, -72.7107],
  Virginia: [37.7693, -78.17],
  Washington: [47.4009, -121.4905],
  "West Virginia": [38.4912, -80.9545],
  Wisconsin: [44.2685, -89.6165],
  Wyoming: [42.756, -107.3025]
});

const STATE_NAMES = Object.values(STATE_ABBREVIATIONS).sort(
  (a, b) => b.length - a.length
);

const STATE_ABBREVIATION_PATTERN =
  Object.keys(STATE_ABBREVIATIONS).join("|");

const STATE_NAME_PATTERN =
  STATE_NAMES.map(escapeRegex).join("|");

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

/*
  Important:
  L.featureGroup() supports getBounds().
  L.layerGroup() does not.
*/
const markersLayer = L.featureGroup().addTo(map);

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

function splitGoogleNewsTitle(value) {
  const fullTitle = cleanText(value);
  const separatorIndex = fullTitle.lastIndexOf(" - ");

  if (separatorIndex < 1) {
    return {
      title: fullTitle,
      source: ""
    };
  }

  return {
    title: fullTitle.slice(0, separatorIndex).trim(),
    source: fullTitle.slice(separatorIndex + 3).trim()
  };
}

/*
  rss2json normally returns dates as:

  YYYY-MM-DD HH:mm:ss

  without a timezone. Google News publication times are UTC, so this
  version explicitly interprets that date format as UTC.
*/
function parseDate(value) {
  if (!value) {
    return null;
  }

  const text = String(value).trim();
  let date;

  if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$/.test(text)) {
    date = new Date(text.replace(/\s+/, "T") + "Z");
  } else {
    date = new Date(text);
  }

  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date;
}

function buildGoogleNewsRssUrl() {
  /*
    A new cache bucket is generated every 15 minutes. This prevents
    a free RSS gateway from repeatedly returning a previously cached
    search URL.
  */
  const cacheBucket = Math.floor(
    Date.now() / SETTINGS.refreshIntervalMs
  );

  return (
    "https://news.google.com/rss/search?q=" +
    encodeURIComponent(FEED_QUERY) +
    "&hl=en-US" +
    "&gl=US" +
    "&ceid=US:en" +
    "&cachebust=" +
    cacheBucket
  );
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
      headers: {
        Accept: "application/json"
      },
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status} from ${getDomain(url)}`
      );
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
      headers: {
        Accept:
          "application/rss+xml, application/xml, text/xml, text/plain"
      },
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status} from ${getDomain(url)}`
      );
    }

    return await response.text();
  } finally {
    window.clearTimeout(timer);
  }
}

function normalizeArticle(
  rawTitle,
  rawUrl,
  rawDate,
  rawSource
) {
  const titleParts = splitGoogleNewsTitle(rawTitle);
  const url = safeUrl(rawUrl);

  return {
    title: titleParts.title,
    url,
    date: parseDate(rawDate),
    domain:
      cleanText(rawSource) ||
      titleParts.source ||
      getDomain(url)
  };
}

/* -------------------------------------------------------
   RSS FEED PROVIDERS
------------------------------------------------------- */

async function fetchArticlesFromRss2Json(rssUrl) {
  const endpoint =
    "https://api.rss2json.com/v1/api.json?rss_url=" +
    encodeURIComponent(rssUrl);

  const data = await fetchJson(
    endpoint,
    SETTINGS.feedTimeoutMs
  );

  /*
    rss2json can return HTTP 200 while its JSON status says error.
  */
  if (data?.status !== "ok") {
    throw new Error(
      cleanText(data?.message) ||
      "rss2json returned an error."
    );
  }

  const items = Array.isArray(data.items)
    ? data.items
    : [];

  if (!items.length) {
    throw new Error(
      "rss2json returned an empty feed."
    );
  }

  return items.map((item) =>
    normalizeArticle(
      item.title,
      item.link || item.guid,
      item.pubDate,
      item.author
    )
  );
}

function firstArrayValue(value) {
  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

async function fetchArticlesFromRssJson(rssUrl) {
  const endpoint =
    "https://rssjson.vercel.app/api?url=" +
    encodeURIComponent(rssUrl);

  const data = await fetchJson(
    endpoint,
    SETTINGS.feedTimeoutMs
  );

  const channel = firstArrayValue(
    data?.rss?.channel
  );

  const items = Array.isArray(channel?.item)
    ? channel.item
    : [];

  if (!items.length) {
    throw new Error(
      "The secondary RSS gateway returned an empty feed."
    );
  }

  return items.map((item) => {
    const sourceNode = firstArrayValue(item.source);

    const source =
      typeof sourceNode === "string"
        ? sourceNode
        : cleanText(
            sourceNode?._ ||
            sourceNode?.$?.url ||
            ""
          );

    return normalizeArticle(
      firstArrayValue(item.title),
      firstArrayValue(item.link),
      firstArrayValue(item.pubDate),
      source ||
        firstArrayValue(item["dc:creator"])
    );
  });
}

async function fetchArticlesFromAllOriginsXml(rssUrl) {
  const endpoint =
    "https://api.allorigins.win/raw?url=" +
    encodeURIComponent(rssUrl);

  const xmlText = await fetchText(
    endpoint,
    SETTINGS.feedTimeoutMs
  );

  const parser = new DOMParser();

  const xml = parser.parseFromString(
    xmlText,
    "text/xml"
  );

  if (xml.querySelector("parsererror")) {
    throw new Error(
      "The RSS XML response could not be parsed."
    );
  }

  const items = Array.from(
    xml.querySelectorAll("item")
  );

  if (!items.length) {
    throw new Error(
      "The XML RSS gateway returned an empty feed."
    );
  }

  return items.map((item) =>
    normalizeArticle(
      item.querySelector("title")?.textContent,
      item.querySelector("link")?.textContent ||
        item.querySelector("guid")?.textContent,
      item.querySelector("pubDate")?.textContent,
      item.querySelector("source")?.textContent
    )
  );
}

async function fetchFloodArticles() {
  const rssUrl = buildGoogleNewsRssUrl();

  const providers = [
    ["rss2json", fetchArticlesFromRss2Json],
    ["rssjson", fetchArticlesFromRssJson],
    ["AllOrigins", fetchArticlesFromAllOriginsXml]
  ];

  const errors = [];

  for (const [name, provider] of providers) {
    try {
      const articles = await provider(rssUrl);
      const now = new Date();

      /*
        Do not accept a provider merely because it returned items.
        At least one result must be a current flood article.
      */
      const hasCurrentFloodArticle =
        articles.some((article) => {
          return (
            article.title &&
            article.url &&
            article.date &&
            isFreshArticle(article, now) &&
            FLOOD_TERMS.test(article.title) &&
            !FALSE_POSITIVE_TERMS.test(article.title)
          );
        });

      if (hasCurrentFloodArticle) {
        console.info(
          `FloodWatch feed loaded through ${name}.`
        );

        return articles;
      }

      errors.push(
        `${name}: no current flood articles were returned.`
      );
    } catch (error) {
      errors.push(
        `${name}: ${error.message || error}`
      );

      console.warn(
        `${name} feed attempt failed.`,
        error
      );
    }
  }

  throw new Error(
    "All live RSS gateways failed. " +
    errors.join(" | ")
  );
}

/* -------------------------------------------------------
   ARTICLE FILTERING
------------------------------------------------------- */

function isFreshArticle(article, now) {
  if (!article.date) {
    return false;
  }

  const ageMs =
    now.getTime() -
    article.date.getTime();

  const maximumAgeMs =
    SETTINGS.articleWindowHours *
    60 *
    60 *
    1000;

  const futureToleranceMs =
    -20 * 60 * 1000;

  return (
    ageMs >= futureToleranceMs &&
    ageMs <= maximumAgeMs
  );
}

function isHistoricalArticle(article, now) {
  if (HISTORICAL_TERMS.test(article.title)) {
    return true;
  }

  const currentYear =
    now.getUTCFullYear();

  const years =
    article.title.match(
      /\b(?:19|20)\d{2}\b/g
    ) || [];

  return years.some(
    (year) => Number(year) < currentYear
  );
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

    if (!normalizedTitle) {
      return false;
    }

    if (
      (
        normalizedUrl &&
        seenUrls.has(normalizedUrl)
      ) ||
      seenTitles.has(normalizedTitle)
    ) {
      return false;
    }

    if (normalizedUrl) {
      seenUrls.add(normalizedUrl);
    }

    seenTitles.add(normalizedTitle);

    return true;
  });
}

async function getCurrentFloodArticles() {
  const now = new Date();

  const articles =
    await fetchFloodArticles();

  return removeDuplicateArticles(
    articles
      .filter((article) => {
        return (
          article.title &&
          article.url &&
          article.date
        );
      })
      .filter((article) => {
        return isFreshArticle(article, now);
      })
      .filter((article) => {
        return !isHistoricalArticle(
          article,
          now
        );
      })
      .filter((article) => {
        return FLOOD_TERMS.test(
          article.title
        );
      })
      .filter((article) => {
        return !FALSE_POSITIVE_TERMS.test(
          article.title
        );
      })
      .sort((a, b) => {
        return (
          b.date.getTime() -
          a.date.getTime()
        );
      })
      .slice(0, SETTINGS.maxArticles)
  );
}

/* -------------------------------------------------------
   LOCATION EXTRACTION
------------------------------------------------------- */

function normalizeStateName(value) {
  const text = cleanText(value);

  if (!text) {
    return "";
  }

  const upper = text.toUpperCase();

  if (STATE_ABBREVIATIONS[upper]) {
    return STATE_ABBREVIATIONS[upper];
  }

  return (
    STATE_NAMES.find((state) => {
      return (
        state.toLowerCase() ===
        text.toLowerCase()
      );
    }) || ""
  );
}

function findStateInText(value) {
  const text = cleanText(value);

  for (const state of STATE_NAMES) {
    const pattern = new RegExp(
      `\\b${escapeRegex(state)}\\b`,
      "i"
    );

    if (pattern.test(text)) {
      return state;
    }
  }

  const abbreviationMatch =
    text.match(
      new RegExp(
        `(?:,|\\s)(${STATE_ABBREVIATION_PATTERN})\\b`
      )
    );

  if (!abbreviationMatch) {
    return "";
  }

  return STATE_ABBREVIATIONS[
    abbreviationMatch[1]
  ];
}

function stateFallbackLocation(stateName) {
  const coordinates =
    STATE_CENTERS[stateName];

  if (!coordinates) {
    return null;
  }

  return {
    latitude: coordinates[0],
    longitude: coordinates[1],
    name: stateName,
    state: "",
    precision: "state"
  };
}

function cleanLocationCandidate(value) {
  let location = cleanText(value)
    .replace(
      /^[\s,;:|–—-]+/,
      ""
    )
    .replace(
      /[\s,;:|–—-]+$/,
      ""
    )
    .replace(
      /^the\s+/i,
      ""
    )
    .replace(
      /[.!?].*$/,
      ""
    )
    .replace(
      /\b(after|amid|as|because|causing|due|following|forces?|hits?|leaves?|prompts?|strikes?|threatens?|under|when|where|while|with)\b.*$/i,
      ""
    )
    .replace(
      /\b(?:officials?|residents?|communities|areas?)\s+(?:warn|prepare|brace|evacuate).*$/i,
      ""
    )
    .trim();

  const words = location
    .split(/\s+/)
    .filter(Boolean);

  if (words.length > 8) {
    location = words
      .slice(0, 8)
      .join(" ");
  }

  if (
    !location ||
    location.length < 2 ||
    location.length > 90
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

  function addCandidate(value) {
    const cleaned =
      cleanLocationCandidate(value);

    if (!cleaned) {
      return;
    }

    const alreadyExists =
      candidates.some((candidate) => {
        return (
          candidate.toLowerCase() ===
          cleaned.toLowerCase()
        );
      });

    if (!alreadyExists) {
      candidates.push(cleaned);
    }
  }

  const cityStateAbbreviationRegex =
    new RegExp(
      `([A-Z][A-Za-z.'’\\-]*(?:\\s+(?:[A-Z][A-Za-z.'’\\-]*|of|the)){0,4}),\\s*(${STATE_ABBREVIATION_PATTERN})\\b`,
      "g"
    );

  for (
    const match of
    title.matchAll(
      cityStateAbbreviationRegex
    )
  ) {
    addCandidate(
      `${match[1]}, ${
        STATE_ABBREVIATIONS[match[2]]
      }`
    );
  }

  const cityStateNameRegex =
    new RegExp(
      `([A-Z][A-Za-z.'’\\-]*(?:\\s+(?:[A-Z][A-Za-z.'’\\-]*|of|the)){0,4}),\\s*(${STATE_NAME_PATTERN})\\b`,
      "gi"
    );

  for (
    const match of
    title.matchAll(cityStateNameRegex)
  ) {
    addCandidate(
      `${match[1]}, ${match[2]}`
    );
  }

  const countyRegex =
    new RegExp(
      `([A-Z][A-Za-z.'’\\-]*(?:\\s+[A-Z][A-Za-z.'’\\-]*){0,3}\\s+(?:County|Parish)),?\\s*(?:in\\s+)?(${STATE_NAME_PATTERN}|${STATE_ABBREVIATION_PATTERN})?`,
      "g"
    );

  for (
    const match of
    title.matchAll(countyRegex)
  ) {
    const state =
      normalizeStateName(match[2]);

    addCandidate(
      state
        ? `${match[1]}, ${state}`
        : match[1]
    );
  }

  const regionalStateRegex =
    new RegExp(
      `\\b((?:north|south|east|west|central|northern|southern|eastern|western|coastal|southeast|southwest|northeast|northwest)\\s+(${STATE_NAME_PATTERN}))\\b`,
      "gi"
    );

  for (
    const match of
    title.matchAll(
      regionalStateRegex
    )
  ) {
    addCandidate(match[1]);
  }

  const prepositionRegex =
    /\b(?:in|near|around|outside|across|throughout|for|along|from)\s+([^:;|–—-]{2,80})/gi;

  for (
    const match of
    title.matchAll(prepositionRegex)
  ) {
    addCandidate(match[1]);
  }

  const impactRegex =
    /\b(?:hits?|strikes?|swamps?|inundates?|threatens?|affects?)\s+([A-Z][^:;|–—-]{1,70})/g;

  for (
    const match of
    title.matchAll(impactRegex)
  ) {
    addCandidate(match[1]);
  }

  const stateNameRegex =
    new RegExp(
      `\\b(${STATE_NAME_PATTERN})\\b`,
      "gi"
    );

  for (
    const match of
    title.matchAll(stateNameRegex)
  ) {
    addCandidate(match[1]);
  }

  return candidates.slice(0, 8);
}

/* -------------------------------------------------------
   GEOCODING CACHE
------------------------------------------------------- */

function readGeocodeCache() {
  try {
    const parsed = JSON.parse(
      localStorage.getItem(
        SETTINGS.geocodeCacheKey
      ) || "{}"
    );

    if (
      parsed &&
      typeof parsed === "object"
    ) {
      return parsed;
    }

    return {};
  } catch {
    return {};
  }
}

function getCachedGeocode(query) {
  const cache = readGeocodeCache();

  const entry =
    cache[query.toLowerCase()];

  if (!entry) {
    return undefined;
  }

  const age =
    Date.now() -
    Number(entry.savedAt || 0);

  const lifetime =
    entry.value === null
      ? SETTINGS.failedGeocodeCacheLifetimeMs
      : SETTINGS.geocodeCacheLifetimeMs;

  if (age > lifetime) {
    return undefined;
  }

  return entry.value;
}

function saveGeocodeToCache(
  query,
  value
) {
  try {
    const cache =
      readGeocodeCache();

    cache[query.toLowerCase()] = {
      savedAt: Date.now(),
      value
    };

    const newestEntries =
      Object.entries(cache)
        .sort((a, b) => {
          return (
            Number(
              b[1].savedAt || 0
            ) -
            Number(
              a[1].savedAt || 0
            )
          );
        })
        .slice(0, 500);

    localStorage.setItem(
      SETTINGS.geocodeCacheKey,
      JSON.stringify(
        Object.fromEntries(
          newestEntries
        )
      )
    );
  } catch (error) {
    console.warn(
      "Could not save the geocode cache.",
      error
    );
  }
}

function isInsideUnitedStates(
  latitude,
  longitude
) {
  const continental =
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
    continental ||
    alaska ||
    hawaii
  );
}

/* -------------------------------------------------------
   GEOCODING
------------------------------------------------------- */

function prepareGeocodeQuery(candidate) {
  const state =
    findStateInText(candidate);

  let place = candidate;

  if (state) {
    const statePattern =
      new RegExp(
        `\\b${escapeRegex(state)}\\b`,
        "ig"
      );

    place = place.replace(
      statePattern,
      ""
    );
  }

  place = place
    .replace(
      /\b(north|south|east|west|central|northern|southern|eastern|western|coastal|southeast|southwest|northeast|northwest)\b/gi,
      ""
    )
    .replace(
      /\b(county|parish|region|area)\b/gi,
      ""
    )
    .replace(
      /^[\s,.-]+|[\s,.-]+$/g,
      ""
    )
    .replace(
      /\s+/g,
      " "
    )
    .trim();

  return {
    place,
    state
  };
}

async function geocodeLocation(candidate) {
  const cached =
    getCachedGeocode(candidate);

  if (cached !== undefined) {
    return cached;
  }

  const requestKey =
    candidate.toLowerCase();

  if (
    activeGeocodeRequests.has(
      requestKey
    )
  ) {
    return activeGeocodeRequests.get(
      requestKey
    );
  }

  const promise = (async () => {
    const {
      place,
      state
    } = prepareGeocodeQuery(
      candidate
    );

    if (!place && state) {
      const fallback =
        stateFallbackLocation(state);

      saveGeocodeToCache(
        candidate,
        fallback
      );

      return fallback;
    }

    try {
      /*
        Send only the actual place name to Open-Meteo.
        The state is used below to score and validate results.
      */
      const params =
        new URLSearchParams({
          name: place || candidate,
          count: "20",
          language: "en",
          format: "json",
          countryCode: "US"
        });

      const endpoint =
        "https://geocoding-api.open-meteo.com/v1/search?" +
        params.toString();

      const data = await fetchJson(
        endpoint,
        SETTINGS.geocodeTimeoutMs
      );

      const results =
        Array.isArray(data?.results)
          ? data.results.filter(
              (item) => {
                return (
                  String(
                    item.country_code ||
                    ""
                  ).toUpperCase() ===
                  "US"
                );
              }
            )
          : [];

      const requestedPlace =
        (place || candidate)
          .toLowerCase();

      const requestedState =
        state.toLowerCase();

      const ranked = results
        .map((item, index) => {
          const resultName =
            String(
              item.name || ""
            ).toLowerCase();

          const resultState =
            String(
              item.admin1 || ""
            ).toLowerCase();

          const resultCounty =
            String(
              item.admin2 || ""
            ).toLowerCase();

          const featureCode =
            String(
              item.feature_code || ""
            );

          let score = -index;

          if (
            resultName ===
            requestedPlace
          ) {
            score += 120;
          } else if (
            resultName.includes(
              requestedPlace
            ) ||
            requestedPlace.includes(
              resultName
            )
          ) {
            score += 55;
          }

          if (
            resultCounty &&
            (
              resultCounty.includes(
                requestedPlace
              ) ||
              requestedPlace.includes(
                resultCounty
              )
            )
          ) {
            score += 35;
          }

          if (
            requestedState &&
            resultState ===
              requestedState
          ) {
            score += 100;
          } else if (
            requestedState
          ) {
            score -= 80;
          }

          if (
            featureCode.startsWith(
              "PPL"
            )
          ) {
            score += 25;
          }

          if (
            featureCode.startsWith(
              "ADM"
            )
          ) {
            score += 10;
          }

          const population =
            Number(
              item.population || 0
            );

          if (population > 0) {
            score += Math.min(
              20,
              Math.log10(
                population + 1
              ) * 2.5
            );
          }

          return {
            item,
            score
          };
        })
        .sort((a, b) => {
          return b.score - a.score;
        });

      const best =
        ranked[0]?.item;

      if (best) {
        const latitude =
          Number(best.latitude);

        const longitude =
          Number(best.longitude);

        if (
          Number.isFinite(
            latitude
          ) &&
          Number.isFinite(
            longitude
          ) &&
          isInsideUnitedStates(
            latitude,
            longitude
          )
        ) {
          const location = {
            latitude,
            longitude,
            name: cleanText(
              best.name
            ),
            state: cleanText(
              best.admin1
            ),
            precision: "place"
          };

          saveGeocodeToCache(
            candidate,
            location
          );

          return location;
        }
      }

      const fallback = state
        ? stateFallbackLocation(
            state
          )
        : null;

      saveGeocodeToCache(
        candidate,
        fallback
      );

      return fallback;
    } catch (error) {
      console.warn(
        `Unable to geocode "${candidate}".`,
        error
      );

      /*
        A temporary geocoding failure should not prevent a state-level
        marker when a state was successfully extracted.
      */
      if (state) {
        return stateFallbackLocation(
          state
        );
      }

      return null;
    } finally {
      activeGeocodeRequests.delete(
        requestKey
      );
    }
  })();

  activeGeocodeRequests.set(
    requestKey,
    promise
  );

  return promise;
}

async function locateArticle(article) {
  const candidates =
    extractLocationCandidates(
      article.title
    );

  for (
    const candidate of
    candidates
  ) {
    const location =
      await geocodeLocation(
        candidate
      );

    if (location) {
      return {
        ...article,
        extractedLocation:
          candidate,
        location
      };
    }
  }

  return null;
}

async function processWithConcurrency(
  items,
  limit,
  worker
) {
  if (!items.length) {
    return [];
  }

  const results =
    new Array(items.length);

  let nextIndex = 0;

  async function runWorker() {
    while (
      nextIndex < items.length
    ) {
      const currentIndex =
        nextIndex;

      nextIndex += 1;

      try {
        results[currentIndex] =
          await worker(
            items[currentIndex],
            currentIndex
          );
      } catch (error) {
        console.warn(
          "Unable to process an article.",
          error
        );

        results[currentIndex] =
          null;
      }
    }
  }

  const workerCount =
    Math.min(
      limit,
      items.length
    );

  await Promise.all(
    Array.from(
      {
        length: workerCount
      },
      () => runWorker()
    )
  );

  return results;
}

/* -------------------------------------------------------
   SEVERITY AND DATE FORMATTING
------------------------------------------------------- */

function getSeverity(title) {
  if (
    /\b(emergency|evacuation|evacuations|deadly|fatal|catastrophic|life-threatening|dam break|levee breach|flash flood warning)\b/i.test(
      title
    )
  ) {
    return "High";
  }

  if (
    /\b(warning|severe|major|flood watch|river flooding|coastal flooding|road closure|roads closed|state of emergency)\b/i.test(
      title
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
      color: "#dc2626",
      fillColor: "#dc2626",
      fillOpacity: 0.92,
      weight: 2
    };
  }

  if (severity === "Moderate") {
    return {
      radius: 8,
      color: "#f97316",
      fillColor: "#f97316",
      fillOpacity: 0.9,
      weight: 2
    };
  }

  return {
    radius: 7,
    color: "#22c55e",
    fillColor: "#22c55e",
    fillOpacity: 0.86,
    weight: 2
  };
}

function formatLocationName(location) {
  return [
    location.name,
    location.state
  ]
    .filter(Boolean)
    .join(", ");
}

function formatDate(date) {
  return date.toLocaleString(
    undefined,
    {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }
  );
}

function formatAge(date) {
  const minutes = Math.max(
    0,
    Math.floor(
      (
        Date.now() -
        date.getTime()
      ) /
      60000
    )
  );

  if (minutes < 60) {
    const value =
      Math.max(1, minutes);

    return `${value} minute${
      value === 1 ? "" : "s"
    } ago`;
  }

  const hours =
    Math.floor(minutes / 60);

  return `${hours} hour${
    hours === 1 ? "" : "s"
  } ago`;
}

/* -------------------------------------------------------
   MAP MARKERS
------------------------------------------------------- */

function renderMarkers(
  mappedArticles
) {
  markersLayer.clearLayers();

  const grouped = new Map();

  mappedArticles.forEach(
    (article) => {
      const key =
        article.location.latitude.toFixed(
          3
        ) +
        "," +
        article.location.longitude.toFixed(
          3
        );

      if (!grouped.has(key)) {
        grouped.set(key, []);
      }

      grouped
        .get(key)
        .push(article);
    }
  );

  grouped.forEach((articles) => {
    const first = articles[0];

    const topSeverity =
      articles
        .map((article) => {
          return getSeverity(
            article.title
          );
        })
        .sort((a, b) => {
          return (
            getSeverityRank(b) -
            getSeverityRank(a)
          );
        })[0];

    const popupItems =
      articles
        .slice(0, 6)
        .map((article) => {
          return `
            <li style="margin-bottom:8px;">
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

    const precisionText =
      first.location.precision ===
      "state"
        ? "Approximate state-level location"
        : "Headline location";

    const popupHtml = `
      <div style="min-width:230px;">
        <strong>
          ${escapeHtml(
            formatLocationName(
              first.location
            )
          )}
        </strong>

        <p style="margin:6px 0;">
          Severity:
          <strong>
            ${escapeHtml(topSeverity)}
          </strong>
          <br>
          <small>
            ${escapeHtml(
              precisionText
            )}
          </small>
        </p>

        <ul style="padding-left:18px; margin-bottom:4px;">
          ${popupItems}
        </ul>
      </div>
    `;

    L.circleMarker(
      [
        first.location.latitude,
        first.location.longitude
      ],
      getMarkerStyle(topSeverity)
    )
      .addTo(markersLayer)
      .bindPopup(popupHtml);
  });
}

/* -------------------------------------------------------
   NEWS CARDS
------------------------------------------------------- */

function renderNewsCards(
  mappedArticles,
  totalFreshArticles
) {
  newsList.innerHTML = "";

  if (!mappedArticles.length) {
    newsList.innerHTML = `
      <article class="news-card">
        <h3>
          No mappable flood stories found
        </h3>

        <p>
          ${totalFreshArticles}
          current flood-related
          ${
            totalFreshArticles === 1
              ? "article was"
              : "articles were"
          }
          found, but no reliable United States
          location was present in the headlines.
        </p>

        <p>
          The page will check again automatically.
        </p>
      </article>
    `;

    return;
  }

  mappedArticles.forEach(
    (article) => {
      const severity =
        getSeverity(article.title);

      const card =
        document.createElement(
          "article"
        );

      card.className =
        "news-card";

      const locationNote =
        article.location.precision ===
        "state"
          ? "Approximate state-level marker"
          : "Headline-derived marker";

      card.innerHTML = `
        <span class="badge ${severity.toLowerCase()}">
          ${escapeHtml(severity)}
        </span>

        <h3>
          ${escapeHtml(article.title)}
        </h3>

        <p>
          <strong>
            Mapped location:
          </strong>

          ${escapeHtml(
            formatLocationName(
              article.location
            )
          )}

          <br>

          <small>
            ${escapeHtml(
              locationNote
            )}
          </small>
        </p>

        <p>
          <strong>
            Source:
          </strong>

          ${escapeHtml(article.domain)}

          <br>

          <strong>
            Published:
          </strong>

          ${escapeHtml(
            formatDate(article.date)
          )}

          <br>

          <strong>
            Age:
          </strong>

          ${escapeHtml(
            formatAge(article.date)
          )}
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
    }
  );

  const updateInfo =
    document.createElement("p");

  updateInfo.className =
    "feed-update-information";

  updateInfo.innerHTML = `
    <small>
      Showing
      ${mappedArticles.length}
      mapped article${
        mappedArticles.length === 1
          ? ""
          : "s"
      }
      from the last
      ${SETTINGS.articleWindowHours}
      hours.

      Last updated:
      ${escapeHtml(
        lastSuccessfulUpdate
          ? formatDate(
              lastSuccessfulUpdate
            )
          : "just now"
      )}.

      The feed refreshes every 15 minutes.
    </small>
  `;

  newsList.appendChild(updateInfo);
}

function renderFloodNews(
  mappedArticles,
  totalFreshArticles
) {
  renderMarkers(mappedArticles);

  renderNewsCards(
    mappedArticles,
    totalFreshArticles
  );

  const bounds =
    markersLayer.getBounds();

  if (bounds.isValid()) {
    map.fitBounds(bounds, {
      padding: [40, 40],
      maxZoom: 8
    });
  } else {
    map.setView(
      [39.8283, -98.5795],
      4
    );
  }

  window.setTimeout(() => {
    map.invalidateSize();
  }, 0);
}

/* -------------------------------------------------------
   MAIN LOADER
------------------------------------------------------- */

async function loadFloodNews() {
  if (loading) {
    return;
  }

  loading = true;

  newsList.innerHTML = `
    <article class="news-card">
      <h3>
        Loading live flood news
      </h3>

      <p>
        Searching for current United States
        flood reports from the last
        ${SETTINGS.articleWindowHours}
        hours...
      </p>
    </article>
  `;

  try {
    const freshArticles =
      await getCurrentFloodArticles();

    const articlesToGeocode =
      freshArticles.slice(
        0,
        SETTINGS.maxArticlesToGeocode
      );

    const locatedResults =
      await processWithConcurrency(
        articlesToGeocode,
        SETTINGS.geocodeConcurrency,
        locateArticle
      );

    const mappedArticles =
      locatedResults
        .filter(Boolean)
        .sort((a, b) => {
          return (
            b.date.getTime() -
            a.date.getTime()
          );
        })
        .slice(
          0,
          SETTINGS.maxMappedArticles
        );

    lastSuccessfulUpdate =
      new Date();

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
        <h3>
          Unable to load the live flood feed
        </h3>

        <p>
          ${escapeHtml(
            error?.message ||
            "The live news service could not be reached."
          )}
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

    document
      .getElementById(
        "retry-flood-news"
      )
      ?.addEventListener(
        "click",
        loadFloodNews
      );
  } finally {
    loading = false;
  }
}

/* -------------------------------------------------------
   STARTUP
------------------------------------------------------- */

loadFloodNews();

window.setInterval(
  loadFloodNews,
  SETTINGS.refreshIntervalMs
);

document.addEventListener(
  "visibilitychange",
  () => {
    if (
      document.visibilityState !==
      "visible"
    ) {
      return;
    }

    if (!lastSuccessfulUpdate) {
      loadFloodNews();
      return;
    }

    const age =
      Date.now() -
      lastSuccessfulUpdate.getTime();

    if (
      age >=
      SETTINGS.refreshIntervalMs
    ) {
      loadFloodNews();
    }
  }
);
