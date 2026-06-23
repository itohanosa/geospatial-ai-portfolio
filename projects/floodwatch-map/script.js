"use strict";

/*
  Live U.S. flood-news map

  Workflow:
  1. Retrieve recent flood-related articles from GDELT.
  2. Keep only articles published within the last 24 hours.
  3. Extract United States locations from article headlines.
  4. Geocode the extracted locations.
  5. Display the articles and locations on a Leaflet map.
  6. Refresh automatically every 15 minutes.
*/

const SETTINGS = {
  hours: 24,
  refreshMs: 15 * 60 * 1000,
  maxFeedArticles: 100,
  maxArticlesToGeocode: 35,
  maxMappedArticles: 25,
  geocodeConcurrency: 5,
  requestTimeoutMs: 20000,
  cacheKey: "floodwatch-geocodes-v2",
  cacheLifetimeMs: 30 * 24 * 60 * 60 * 1000
};

if (typeof L === "undefined") {
  throw new Error("Leaflet must be loaded before script.js.");
}

const mapElement = document.getElementById("map");
const newsList = document.getElementById("news-list");

if (!mapElement || !newsList) {
  throw new Error(
    'Your HTML must contain elements with IDs "map" and "news-list".'
  );
}

const map = L.map("map").setView([39.8283, -98.5795], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);

const FLOOD_QUERY =
  '(flood OR flooding OR "flash flood" OR "flood warning" OR "flood watch" OR "coastal flooding" OR "river flooding" OR "high water") sourcecountry:US';

const FLOOD_WORDS =
  /\b(flood|flooding|flooded|flash flood|high water|inundat(?:e|ed|ion)|levee breach|dam break)\b/i;

const FALSE_FLOOD =
  /\bflood(?:ed|ing)?\s+(?:with|of)\s+(?:calls|comments|complaints|donations|emails|messages|orders|requests|support|tributes|visitors|votes)\b/i;

const HISTORICAL_WORDS =
  /\b(anniversary|archive|archived|flashback|historical|history of|last year|retrospective|years ago)\b/i;

const STATE_ABBR_TO_NAME = Object.freeze({
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

const STATE_NAMES = Object.values(STATE_ABBR_TO_NAME).sort(
  (a, b) => b.length - a.length
);

const STATE_ABBRS_PATTERN = Object.keys(STATE_ABBR_TO_NAME).join("|");

const STATE_NAMES_PATTERN = STATE_NAMES.map(escapeRegex).join("|");

const geocodeRequests = new Map();

let loading = false;

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
  const element = document.createElement("div");

  element.innerHTML = String(value || "");

  return (element.textContent || "")
    .replace(/\s+/g, " ")
    .trim();
}

function safeUrl(value) {
  try {
    const url = new URL(value);

    if (url.protocol === "http:" || url.protocol === "https:") {
      return url.href;
    }

    return "";
  } catch {
    return "";
  }
}

function sourceDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Unknown source";
  }
}

function gdeltTimestamp(date) {
  const pad = (number) => String(number).padStart(2, "0");

  return (
    `${date.getUTCFullYear()}` +
    `${pad(date.getUTCMonth() + 1)}` +
    `${pad(date.getUTCDate())}` +
    `${pad(date.getUTCHours())}` +
    `${pad(date.getUTCMinutes())}` +
    `${pad(date.getUTCSeconds())}`
  );
}

function buildGdeltUrl() {
  const end = new Date();

  const start = new Date(
    end.getTime() - SETTINGS.hours * 60 * 60 * 1000
  );

  const params = new URLSearchParams({
    query: FLOOD_QUERY,
    mode: "ArtList",
    format: "json",
    maxrecords: String(SETTINGS.maxFeedArticles),
    sort: "DateDesc",
    STARTDATETIME: gdeltTimestamp(start),
    ENDDATETIME: gdeltTimestamp(end)
  });

  return `https://api.gdeltproject.org/api/v2/doc/doc?${params.toString()}`;
}

async function fetchJson(url) {
  const controller = new AbortController();

  const timer = setTimeout(() => {
    controller.abort();
  }, SETTINGS.requestTimeoutMs);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      cache: "no-store",
      headers: {
        Accept: "application/json"
      }
    });

    if (!response.ok) {
      throw new Error(`Request failed with HTTP ${response.status}`);
    }

    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJsonWithFallback(url) {
  try {
    return await fetchJson(url);
  } catch (directError) {
    console.warn(
      "Direct GDELT request failed. Trying the fallback proxy.",
      directError
    );

    const proxyUrl =
      "https://api.allorigins.win/raw?url=" +
      encodeURIComponent(url);

    return await fetchJson(proxyUrl);
  }
}

function parseDate(value) {
  const raw = String(value || "").trim();

  const compactDate = raw.match(
    /^(\d{4})(\d{2})(\d{2})T?(\d{2})(\d{2})(\d{2})(?:\.\d+)?Z?$/
  );

  if (compactDate) {
    return new Date(
      Date.UTC(
        Number(compactDate[1]),
        Number(compactDate[2]) - 1,
        Number(compactDate[3]),
        Number(compactDate[4]),
        Number(compactDate[5]),
        Number(compactDate[6])
      )
    );
  }

  const parsedDate = new Date(raw);

  if (Number.isNaN(parsedDate.getTime())) {
    return null;
  }

  return parsedDate;
}

function normalizeArticles(data) {
  let records = [];

  if (Array.isArray(data?.articles)) {
    records = data.articles;
  } else if (Array.isArray(data?.items)) {
    records = data.items;
  }

  return records
    .map((record) => {
      const url = safeUrl(
        record.url ||
          record.external_url ||
          record.link
      );

      const title = cleanText(
        record.title ||
          record.name
      );

      const date = parseDate(
        record.seendate ||
          record.date ||
          record.date_published ||
          record.pubDate
      );

      return {
        title,
        url,
        date,
        domain:
          cleanText(record.domain) ||
          sourceDomain(url)
      };
    })
    .filter((article) => {
      return (
        article.title &&
        article.url &&
        article.date
      );
    });
}

function isFresh(article, now) {
  const ageMilliseconds =
    now.getTime() - article.date.getTime();

  const maximumAge =
    SETTINGS.hours * 60 * 60 * 1000;

  const futureTolerance =
    -10 * 60 * 1000;

  return (
    ageMilliseconds >= futureTolerance &&
    ageMilliseconds <= maximumAge
  );
}

function isHistorical(article, now) {
  const currentYear = now.getUTCFullYear();

  const yearMatches =
    `${article.title} ${article.url}`.match(
      /\b(?:19|20)\d{2}\b/g
    ) || [];

  const containsOldYear = yearMatches.some(
    (year) => Number(year) < currentYear
  );

  const containsHistoricalLanguage =
    HISTORICAL_WORDS.test(article.title);

  return (
    containsOldYear ||
    containsHistoricalLanguage
  );
}

function uniqueArticles(articles) {
  const existingUrls = new Set();
  const existingTitles = new Set();

  return articles.filter((article) => {
    const normalizedUrl = article.url
      .replace(/[?#].*$/, "")
      .replace(/\/$/, "");

    const normalizedTitle = article.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();

    if (
      existingUrls.has(normalizedUrl) ||
      existingTitles.has(normalizedTitle)
    ) {
      return false;
    }

    existingUrls.add(normalizedUrl);
    existingTitles.add(normalizedTitle);

    return true;
  });
}

async function getCurrentArticles() {
  const now = new Date();

  const data = await fetchJsonWithFallback(
    buildGdeltUrl()
  );

  return uniqueArticles(
    normalizeArticles(data)
      .filter((article) => isFresh(article, now))
      .filter((article) => !isHistorical(article, now))
      .filter((article) => {
        return (
          FLOOD_WORDS.test(article.title) &&
          !FALSE_FLOOD.test(article.title)
        );
      })
      .sort((articleA, articleB) => {
        return articleB.date - articleA.date;
      })
  );
}

function cleanLocation(value) {
  let location = cleanText(value)
    .replace(
      /^[\s,;:|–—-]+|[\s,;:|–—-]+$/g,
      ""
    )
    .replace(/^the\s+/i, "")
    .replace(
      /\b(after|amid|as|because|causing|due|following|forces?|hits?|leaves?|prompts?|strikes?|threatens?|under|when|where|while|with)\b.*$/i,
      ""
    )
    .replace(/[.!?].*$/, "")
    .trim();

  const words = location
    .split(/\s+/)
    .filter(Boolean);

  if (words.length > 6) {
    location = words.slice(-6).join(" ");
  }

  if (
    !location ||
    location.length < 2 ||
    location.length > 70
  ) {
    return "";
  }

  if (
    /\b(flood|flooding|warning|watch|storm|rain|weather)\b/i.test(
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
    const location = cleanLocation(value);

    if (!location) {
      return;
    }

    const alreadyExists = candidates.some(
      (existingLocation) =>
        existingLocation.toLowerCase() ===
        location.toLowerCase()
    );

    if (!alreadyExists) {
      candidates.push(location);
    }
  }

  const cityAndStateAbbreviation = new RegExp(
    `([A-Z][A-Za-z.'’\\-]*(?:\\s+(?:[A-Z][A-Za-z.'’\\-]*|of|the)){0,3}),\\s*(${STATE_ABBRS_PATTERN})\\b`,
    "g"
  );

  for (
    const match of title.matchAll(
      cityAndStateAbbreviation
    )
  ) {
    const city = match[1];
    const stateName =
      STATE_ABBR_TO_NAME[match[2]];

    addCandidate(`${city}, ${stateName}`);
  }

  const locationAfterPreposition =
    /\b(?:in|near|around|outside|across|throughout|for|along|from)\s+([^:;|–—-]{2,75})/gi;

  for (
    const match of title.matchAll(
      locationAfterPreposition
    )
  ) {
    addCandidate(match[1]);
  }

  const locationAfterImpactVerb =
    /\b(?:hits?|strikes?|swamps?|inundates?|threatens?)\s+([A-Z][^:;|–—-]{1,60})/g;

  for (
    const match of title.matchAll(
      locationAfterImpactVerb
    )
  ) {
    addCandidate(match[1]);
  }

  const stateNamePattern = new RegExp(
    `\\b(${STATE_NAMES_PATTERN})\\b`,
    "gi"
  );

  for (
    const match of title.matchAll(
      stateNamePattern
    )
  ) {
    addCandidate(match[1]);
  }

  return candidates.slice(0, 4);
}

function readCache() {
  try {
    return (
      JSON.parse(
        localStorage.getItem(
          SETTINGS.cacheKey
        ) || "{}"
      ) || {}
    );
  } catch {
    return {};
  }
}

function cachedGeocode(query) {
  const cache = readCache();

  const entry =
    cache[query.toLowerCase()];

  if (!entry) {
    return undefined;
  }

  const cacheAge =
    Date.now() - entry.savedAt;

  if (
    cacheAge >
    SETTINGS.cacheLifetimeMs
  ) {
    return undefined;
  }

  return entry.value;
}

function storeGeocode(query, value) {
  try {
    const cache = readCache();

    cache[query.toLowerCase()] = {
      savedAt: Date.now(),
      value
    };

    const newestEntries = Object.entries(cache)
      .sort(
        (entryA, entryB) =>
          entryB[1].savedAt -
          entryA[1].savedAt
      )
      .slice(0, 400);

    localStorage.setItem(
      SETTINGS.cacheKey,
      JSON.stringify(
        Object.fromEntries(newestEntries)
      )
    );
  } catch (error) {
    console.warn(
      "The geocoding cache could not be saved.",
      error
    );
  }
}

function isInUnitedStates(lat, lon) {
  const continentalUnitedStates =
    lat >= 24 &&
    lat <= 50 &&
    lon >= -125 &&
    lon <= -66;

  const alaska =
    lat >= 51 &&
    lat <= 72 &&
    lon >= -170 &&
    lon <= -129;

  const hawaii =
    lat >= 18 &&
    lat <= 23 &&
    lon >= -161 &&
    lon <= -154;

  return (
    continentalUnitedStates ||
    alaska ||
    hawaii
  );
}

async function geocode(query) {
  const cachedResult =
    cachedGeocode(query);

  if (cachedResult !== undefined) {
    return cachedResult;
  }

  const requestKey =
    query.toLowerCase();

  if (
    geocodeRequests.has(requestKey)
  ) {
    return geocodeRequests.get(
      requestKey
    );
  }

  const request = (async () => {
    try {
      const parameters =
        new URLSearchParams({
          name: query,
          count: "10",
          language: "en",
          format: "json",
          countryCode: "US"
        });

      const data = await fetchJson(
        `https://geocoding-api.open-meteo.com/v1/search?${parameters.toString()}`
      );

      const results = (
        data.results || []
      ).filter((result) => {
        return (
          String(
            result.country_code
          ).toUpperCase() === "US"
        );
      });

      const queryParts = query
        .toLowerCase()
        .split(",")
        .map((part) => part.trim());

      const queryPlace =
        queryParts[0] || "";

      const queryState =
        queryParts[1] || "";

      const rankedResult = results
        .map((item, index) => {
          const resultName = String(
            item.name || ""
          ).toLowerCase();

          const resultState = String(
            item.admin1 || ""
          ).toLowerCase();

          let score = -index;

          if (
            resultName === queryPlace
          ) {
            score += 100;
          } else if (
            resultName.includes(
              queryPlace
            ) ||
            queryPlace.includes(
              resultName
            )
          ) {
            score += 40;
          }

          if (
            queryState &&
            resultState === queryState
          ) {
            score += 80;
          }

          if (
            /^PPL/.test(
              String(
                item.feature_code || ""
              )
            )
          ) {
            score += 20;
          }

          score += Math.min(
            15,
            Math.log10(
              Number(
                item.population || 0
              ) + 1
            ) * 2
          );

          return {
            item,
            score
          };
        })
        .sort(
          (resultA, resultB) =>
            resultB.score -
            resultA.score
        )[0]?.item;

      const location = rankedResult
        ? {
            lat: Number(
              rankedResult.latitude
            ),
            lon: Number(
              rankedResult.longitude
            ),
            name: cleanText(
              rankedResult.name
            ),
            state: cleanText(
              rankedResult.admin1
            )
          }
        : null;

      const validLocation =
        location &&
        isInUnitedStates(
          location.lat,
          location.lon
        )
          ? location
          : null;

      storeGeocode(
        query,
        validLocation
      );

      return validLocation;
    } catch (error) {
      console.warn(
        `Geocoding failed for "${query}".`,
        error
      );

      return null;
    } finally {
      geocodeRequests.delete(
        requestKey
      );
    }
  })();

  geocodeRequests.set(
    requestKey,
    request
  );

  return request;
}

async function locateArticle(article) {
  const candidates =
    extractLocationCandidates(
      article.title
    );

  for (const candidate of candidates) {
    const location =
      await geocode(candidate);

    if (location) {
      return {
        ...article,
        location
      };
    }
  }

  return null;
}

async function withConcurrency(
  items,
  limit,
  worker
) {
  const results =
    new Array(items.length);

  let currentIndex = 0;

  async function runWorker() {
    while (
      currentIndex < items.length
    ) {
      const itemIndex =
        currentIndex++;

      results[itemIndex] =
        await worker(
          items[itemIndex]
        );
    }
  }

  const workerCount = Math.min(
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

function getSeverity(title) {
  const text =
    title.toLowerCase();

  if (
    /(emergency|evacuation|deadly|catastrophic|life-threatening|dam break|levee breach|flash flood warning)/.test(
      text
    )
  ) {
    return "High";
  }

  if (
    /(warning|severe|major|flood watch|river flooding|coastal flooding|road closure)/.test(
      text
    )
  ) {
    return "Moderate";
  }

  return "Low";
}

function markerStyle(severity) {
  if (severity === "High") {
    return {
      radius: 9,
      color: "#8b0000",
      fillColor: "#dc2626",
      fillOpacity: 0.9,
      weight: 2
    };
  }

  if (severity === "Moderate") {
    return {
      radius: 8,
      color: "#9a3412",
      fillColor: "#f97316",
      fillOpacity: 0.88,
      weight: 2
    };
  }

  return {
    radius: 7,
    color: "#1e3a8a",
    fillColor: "#3b82f6",
    fillOpacity: 0.85,
    weight: 2
  };
}

function articleAge(date) {
  const ageInMinutes = Math.max(
    0,
    Math.floor(
      (Date.now() -
        date.getTime()) /
        60000
    )
  );

  if (ageInMinutes < 60) {
    return (
      `${Math.max(
        1,
        ageInMinutes
      )} minute` +
      `${ageInMinutes === 1 ? "" : "s"} ago`
    );
  }

  const ageInHours =
    Math.floor(
      ageInMinutes / 60
    );

  return (
    `${ageInHours} hour` +
    `${ageInHours === 1 ? "" : "s"} ago`
  );
}

function locationName(location) {
  return [
    location.name,
    location.state
  ]
    .filter(Boolean)
    .join(", ");
}

function renderFloodNews(
  mappedArticles,
  freshArticleCount
) {
  newsList.innerHTML = "";

  markersLayer.clearLayers();

  if (!mappedArticles.length) {
    newsList.innerHTML = `
      <div class="news-card">
        <h3>No mappable current flood headlines</h3>
        <p>
          ${freshArticleCount} fresh flood-related
          ${
            freshArticleCount === 1
              ? "article was"
              : "articles were"
          }
          found, but no clear United States location
          could be extracted from the headlines.
        </p>
      </div>
    `;

    map.setView(
      [39.8283, -98.5795],
      4
    );

    return;
  }

  const locationGroups =
    new Map();

  mappedArticles.forEach(
    (article) => {
      const locationKey =
        `${article.location.lat.toFixed(3)},` +
        `${article.location.lon.toFixed(3)}`;

      if (
        !locationGroups.has(
          locationKey
        )
      ) {
        locationGroups.set(
          locationKey,
          []
        );
      }

      locationGroups
        .get(locationKey)
        .push(article);
    }
  );

  locationGroups.forEach(
    (articles) => {
      const firstArticle =
        articles[0];

      const severityLevels =
        articles.map((article) =>
          getSeverity(
            article.title
          )
        );

      let highestSeverity = "Low";

      if (
        severityLevels.includes(
          "High"
        )
      ) {
        highestSeverity = "High";
      } else if (
        severityLevels.includes(
          "Moderate"
        )
      ) {
        highestSeverity =
          "Moderate";
      }

      const popupArticles = articles
        .slice(0, 5)
        .map((article) => {
          return `
            <li>
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

      L.circleMarker(
        [
          firstArticle.location.lat,
          firstArticle.location.lon
        ],
        markerStyle(highestSeverity)
      )
        .addTo(markersLayer)
        .bindPopup(`
          <strong>
            ${escapeHtml(
              locationName(
                firstArticle.location
              )
            )}
          </strong>
          <br>
          Severity:
          ${escapeHtml(
            highestSeverity
          )}
          <ul style="padding-left: 18px;">
            ${popupArticles}
          </ul>
        `);
    }
  );

  mappedArticles.forEach(
    (article) => {
      const severity =
        getSeverity(
          article.title
        );

      const card =
        document.createElement(
          "article"
        );

      card.className =
        "news-card";

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
            locationName(
              article.location
            )
          )}
        </p>

        <p>
          <strong>Source:</strong>
          ${escapeHtml(article.domain)}
          <br>

          <strong>Published:</strong>
          ${escapeHtml(
            article.date.toLocaleString()
          )}
          (${escapeHtml(
            articleAge(article.date)
          )})
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

  const attributionNote =
    document.createElement("p");

  attributionNote.innerHTML = `
    <small>
      News data: GDELT.
      Geocoding: Open-Meteo.
      Map: OpenStreetMap contributors.
    </small>
  `;

  newsList.appendChild(
    attributionNote
  );

  const bounds =
    markersLayer.getBounds();

  if (bounds.isValid()) {
    map.fitBounds(bounds, {
      padding: [40, 40],
      maxZoom: 8
    });
  }
}

async function loadFloodNews() {
  if (loading) {
    return;
  }

  loading = true;

  newsList.innerHTML = `
    <p>
      Loading live United States flood articles
      from the last ${SETTINGS.hours} hours...
    </p>
  `;

  try {
    const freshArticles =
      await getCurrentArticles();

    const articlesToLocate =
      freshArticles.slice(
        0,
        SETTINGS.maxArticlesToGeocode
      );

    const locatedArticles =
      await withConcurrency(
        articlesToLocate,
        SETTINGS.geocodeConcurrency,
        locateArticle
      );

    const mappedArticles =
      locatedArticles
        .filter(Boolean)
        .sort(
          (articleA, articleB) =>
            articleB.date -
            articleA.date
        )
        .slice(
          0,
          SETTINGS.maxMappedArticles
        );

    renderFloodNews(
      mappedArticles,
      freshArticles.length
    );
  } catch (error) {
    console.error(
      "Flood news loading error:",
      error
    );

    newsList.innerHTML = `
      <div class="news-card">
        <h3>
          Unable to load the live flood feed
        </h3>

        <p>
          ${escapeHtml(
            error.message ||
              "Please refresh the page and try again."
          )}
        </p>
      </div>
    `;
  } finally {
    loading = false;
  }
}

loadFloodNews();

setInterval(
  loadFloodNews,
  SETTINGS.refreshMs
);
