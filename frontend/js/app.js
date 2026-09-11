const form = document.querySelector("#schedule-form");
const originInput = document.querySelector("#origin");
const destinationInput = document.querySelector("#destination");
const startDateInput = document.querySelector("#start-date");
const weeksInput = document.querySelector("#weeks");
const runButton = document.querySelector("#run-button");
const updateButton = document.querySelector("#update-button");
const statusEl = document.querySelector("#status");
const errorEl = document.querySelector("#error");
const resultsEl = document.querySelector("#results");
const routeTitle = document.querySelector("#route-title");
const resultsCaption = document.querySelector("#results-caption");
const tableHead = document.querySelector("#schedule-table thead");
const tableBody = document.querySelector("#schedule-table tbody");

function isoDate(date) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function todayIso() {
  return isoDate(new Date());
}

function setDefaultSearchWindow() {
  const today = todayIso();
  startDateInput.min = today;
  if (!startDateInput.value || startDateInput.value < today) {
    startDateInput.value = today;
  }
  if (!weeksInput.value) {
    weeksInput.value = "4";
  }
}

function normalizeCode(value) {
  return value.trim().toUpperCase();
}

function setBusy(isBusy, message) {
  runButton.disabled = isBusy;
  updateButton.disabled = isBusy;
  if (isBusy) {
    hide(errorEl);
    show(statusEl, message);
  }
}

function show(element, text) {
  element.hidden = false;
  element.textContent = text;
}

function hide(element) {
  element.hidden = true;
  element.textContent = "";
}

function formatDate(isoDateValue) {
  const date = new Date(`${isoDateValue}T00:00:00`);
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatWeekLabel(isoDateValue) {
  return `Week of ${formatDate(isoDateValue)}`;
}

function addDays(isoDateValue, days) {
  const date = new Date(`${isoDateValue}T00:00:00`);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

function renderSchedule(data) {
  routeTitle.textContent = `${data.origin} → ${data.destination}`;
  const sourceLabel = data.source === "database" ? "database cache" : "FlightsFrom.com";
  const endDate = addDays(data.window_start, data.weeks * 7 - 1);
  resultsCaption.textContent = `${data.flight_count} flights · ${formatDate(data.window_start)} – ${formatDate(
    endDate
  )} · loaded from ${sourceLabel} · updated ${new Date(data.fetched_at).toLocaleString()}`;

  tableHead.innerHTML = "";
  tableBody.innerHTML = "";

  const headerRow = document.createElement("tr");
  const weekdayHeader = document.createElement("th");
  weekdayHeader.textContent = "Weekday";
  headerRow.appendChild(weekdayHeader);
  data.columns.forEach((columnDate) => {
    const th = document.createElement("th");
    th.textContent = formatWeekLabel(columnDate);
    headerRow.appendChild(th);
  });
  tableHead.appendChild(headerRow);

  data.rows.forEach((row) => {
    const tr = document.createElement("tr");
    const weekdayCell = document.createElement("th");
    weekdayCell.className = "weekday";
    weekdayCell.scope = "row";
    weekdayCell.textContent = row.weekday;
    tr.appendChild(weekdayCell);

    row.cells.forEach((cell) => {
      const td = document.createElement("td");
      if (!cell.in_range) {
        td.className = "out-of-range";
      }
      const dateLabel = document.createElement("span");
      dateLabel.className = "cell-date";
      dateLabel.textContent = formatDate(cell.date);
      td.appendChild(dateLabel);

      if (!cell.in_range) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "Outside search window";
        td.appendChild(empty);
      } else if (!cell.flights.length) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "No flights";
        td.appendChild(empty);
      } else {
        const list = document.createElement("div");
        list.className = "flight-list";
        cell.flights.forEach((flight) => {
          const card = document.createElement("article");
          card.className = "flight-card";
          card.innerHTML = `
            <div class="flight-times">${flight.departure_local_time} → ${flight.arrival_local_time}</div>
            <div class="flight-meta">
              <span class="flight-number">${flight.flight_number}</span>
              <span>${flight.airline}</span>
            </div>
            <div class="aircraft">${flight.aircraft}</div>
          `;
          list.appendChild(card);
        });
        td.appendChild(list);
      }
      tr.appendChild(td);
    });
    tableBody.appendChild(tr);
  });

  resultsEl.hidden = false;
}

async function requestSchedule(forceUpdate) {
  setDefaultSearchWindow();
  const origin = normalizeCode(originInput.value);
  const destination = normalizeCode(destinationInput.value);
  const startDate = startDateInput.value;
  const weeks = Number(weeksInput.value);
  originInput.value = origin;
  destinationInput.value = destination;

  if (origin.length !== 3 || destination.length !== 3) {
    hide(statusEl);
    show(errorEl, "Enter 3-letter IATA codes in both fields.");
    return;
  }
  if (!startDate) {
    hide(statusEl);
    show(errorEl, "Choose a start date.");
    return;
  }
  if (!Number.isInteger(weeks) || weeks < 1 || weeks > 8) {
    hide(statusEl);
    show(errorEl, "Length must be between 1 and 8 weeks.");
    return;
  }

  const message = forceUpdate
    ? "Updating from FlightsFrom.com and overwriting the database…"
    : "Checking the database, then fetching from FlightsFrom.com if needed…";
  setBusy(true, message);

  try {
    const response = await fetch(`/api/schedules?force_update=${forceUpdate}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin,
        destination,
        start_date: startDate,
        weeks,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = payload.detail;
      const message = typeof detail === "string" ? detail : "Unable to load schedule.";
      throw new Error(message);
    }
    renderSchedule(payload);
    const sourcePhrase = payload.source === "database" ? "the database" : "FlightsFrom.com";
    show(statusEl, `Showing ${payload.origin} → ${payload.destination} from ${sourcePhrase}.`);
  } catch (error) {
    resultsEl.hidden = true;
    hide(statusEl);
    show(errorEl, error.message);
  } finally {
    setBusy(false);
  }
}

function bindCodeInput(input) {
  input.addEventListener("input", () => {
    input.value = input.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 3);
  });
}

setDefaultSearchWindow();
bindCodeInput(originInput);
bindCodeInput(destinationInput);

form.addEventListener("submit", (event) => {
  event.preventDefault();
  requestSchedule(false);
});

updateButton.addEventListener("click", () => {
  requestSchedule(true);
});
