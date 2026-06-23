const map = L.map("map").setView([39.8283, -98.5795], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

const floodNews = [
  {
    title: "Heavy rainfall causes flash flooding in Houston",
    location: "Houston, Texas",
    lat: 29.7604,
    lon: -95.3698,
    severity: "High",
    summary: "Several neighborhoods reported street flooding after intense rainfall.",
    source: "https://www.weather.gov/"
  },
  {
    title: "River levels rise near Baton Rouge",
    location: "Baton Rouge, Louisiana",
    lat: 30.4515,
    lon: -91.1871,
    severity: "Moderate",
    summary: "Officials are monitoring rising river levels after recent storms.",
    source: "https://www.weather.gov/"
  },
  {
    title: "Minor coastal flooding expected in Maryland",
    location: "Baltimore, Maryland",
    lat: 39.2904,
    lon: -76.6122,
    severity: "Low",
    summary: "Tidal flooding may affect low-lying coastal areas.",
    source: "https://www.weather.gov/"
  },
  {
    title: "Flood watch issued for parts of Florida",
    location: "Miami, Florida",
    lat: 25.7617,
    lon: -80.1918,
    severity: "Moderate",
    summary: "A flood watch remains active due to slow-moving thunderstorms.",
    source: "https://www.weather.gov/"
  }
];

function getSeverityClass(severity) {
  return severity.toLowerCase();
}

const newsList = document.getElementById("news-list");

floodNews.forEach((item) => {
  const severityClass = getSeverityClass(item.severity);

  L.marker([item.lat, item.lon])
    .addTo(map)
    .bindPopup(`
      <strong>${item.title}</strong><br>
      ${item.location}<br>
      Severity: ${item.severity}<br>
      <a href="${item.source}" target="_blank">Read source</a>
    `);

  const card = document.createElement("div");
  card.className = "news-card";

  card.innerHTML = `
    <span class="badge ${severityClass}">${item.severity}</span>
    <h3>${item.title}</h3>
    <p><strong>Location:</strong> ${item.location}</p>
    <p>${item.summary}</p>
    <a href="${item.source}" target="_blank">Read source</a>
  `;

  newsList.appendChild(card);
});
