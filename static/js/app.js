"use strict";

/* ==========================================================================
   Music Diary — клиентская логика (Vanilla JS + Fetch API)
   ========================================================================== */

/* --------------------------------------------------------------------------
   ЕДИНАЯ КОНФИГУРАЦИЯ.
   Бэкенд отдаётся тем же Flask-сервером, что и фронтенд, поэтому достаточно
   относительного пути. Если фронтенд запускается отдельно (Live Server),
   замените на полный URL, например:
   const API_BASE_URL = "https://music-diary.onrender.com/api/reviews";
   -------------------------------------------------------------------------- */
const API_BASE_URL = "/api/reviews";

const GENRES = ["Рок", "Поп", "Рэп", "Инди", "Электроника", "Джаз", "Метал", "R&B", "Другое"];
const ENTITY_TYPE_LABELS = { album: "Альбом", track: "Трек", artist: "Исполнитель" };
const PLACEHOLDER_IMG = "/static/img/placeholder.svg";
const DEBOUNCE_MS = 350;

/* Уникальный id этого браузера — «владелец» рецензий. Позволяет удалять и
   редактировать только свои рецензии (без полноценной регистрации). */
const CLIENT_ID = getClientId();

function getClientId() {
  const KEY = "md_client_id";
  let id = null;
  try { id = localStorage.getItem(KEY); } catch (_e) { /* localStorage недоступен */ }
  if (!id) {
    id = (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : "md-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    try { localStorage.setItem(KEY, id); } catch (_e) { /* ignore */ }
  }
  return id;
}

/* Текущее состояние фильтров. */
const state = {
  search: "",
  genre: "all",
  sort: "date_desc",
  editingId: null,
};

/* --------------------------------------------------------------------------
   Ссылки на DOM-элементы.
   -------------------------------------------------------------------------- */
const els = {
  counter: document.getElementById("counter"),
  filteredHint: document.getElementById("filteredHint"),

  reviewForm: document.getElementById("reviewForm"),
  formTitle: document.getElementById("formTitle"),
  reviewId: document.getElementById("reviewId"),
  title: document.getElementById("title"),
  titleLabel: document.getElementById("titleLabel"),
  artist: document.getElementById("artist"),
  artistField: document.getElementById("artistField"),
  genre: document.getElementById("genre"),
  rating: document.getElementById("rating"),
  text: document.getElementById("text"),
  coverUrl: document.getElementById("cover_url"),
  submitBtn: document.getElementById("submitBtn"),
  cancelBtn: document.getElementById("cancelBtn"),
  formPanel: document.getElementById("formPanel"),

  search: document.getElementById("search"),
  genreFilter: document.getElementById("genreFilter"),
  sortFilter: document.getElementById("sortFilter"),
  resetFilters: document.getElementById("resetFilters"),

  reviewsList: document.getElementById("reviewsList"),
  loadingState: document.getElementById("loadingState"),
  emptyState: document.getElementById("emptyState"),

  toastContainer: document.getElementById("toastContainer"),
  confirmModal: document.getElementById("confirmModal"),
  confirmDeleteBtn: document.getElementById("confirmDeleteBtn"),
  cancelDeleteBtn: document.getElementById("cancelDeleteBtn"),
};

/* Соответствие поля формы -> элемент ошибки и подсветка. */
const FIELD_ERRORS = {
  title: { errorId: "titleError", input: () => els.title },
  artist: { errorId: "artistError", input: () => els.artist },
  text: { errorId: "textError", input: () => els.text },
  genre: { errorId: "genreError", input: () => els.genre },
  rating: { errorId: "ratingError", input: () => els.rating },
  cover_url: { errorId: "coverUrlError", input: () => els.coverUrl },
};

let deleteTargetId = null;

/* --------------------------------------------------------------------------
   Инициализация.
   -------------------------------------------------------------------------- */
document.addEventListener("DOMContentLoaded", init);

function init() {
  initStarRating();
  bindEvents();
  updateTypeFields();
  fetchReviews();
}

function bindEvents() {
  els.reviewForm.addEventListener("submit", handleSubmit);
  els.cancelBtn.addEventListener("click", exitEditMode);

  // Переключение типа объекта меняет поля формы (для «Исполнителя» — одно поле имени).
  document.querySelectorAll('input[name="entity_type"]').forEach((r) => {
    r.addEventListener("change", updateTypeFields);
  });

  // Поиск с debounce.
  els.search.addEventListener("input", debounce(onSearchInput, DEBOUNCE_MS));

  // Фильтр по жанру и сортировка — сразу.
  els.genreFilter.addEventListener("change", () => {
    state.genre = els.genreFilter.value;
    fetchReviews();
  });
  els.sortFilter.addEventListener("change", () => {
    state.sort = els.sortFilter.value;
    fetchReviews();
  });

  // Сброс фильтров.
  els.resetFilters.addEventListener("click", resetFilters);

  // Модальное окно удаления.
  els.confirmDeleteBtn.addEventListener("click", doDelete);
  els.cancelDeleteBtn.addEventListener("click", closeDeleteModal);
  els.confirmModal.addEventListener("click", (e) => {
    if (e.target === els.confirmModal) closeDeleteModal();
  });
}

/* --------------------------------------------------------------------------
   Взаимодействие с API.
   -------------------------------------------------------------------------- */
async function fetchJSON(url, options = {}) {
  const headers = { "X-Client-Id": CLIENT_ID, ...(options.headers || {}) };
  const opts = { ...options, headers };

  let response;
  try {
    response = await fetch(url, opts);
  } catch (_e) {
    const err = new Error("Не удалось соединиться с сервером. Проверьте подключение.");
    err.isNetwork = true;
    throw err;
  }

  let data = null;
  try {
    data = await response.json();
  } catch (_e) {
    data = null;
  }

  if (!response.ok) {
    const message = (data && data.error) ? data.error : `Ошибка сервера (${response.status})`;
    const err = new Error(message);
    err.status = response.status;
    err.data = data;
    throw err;
  }
  return data;
}

async function fetchReviews() {
  const params = new URLSearchParams();
  if (state.search) params.set("search", state.search);
  if (state.genre && state.genre !== "all") params.set("genre", state.genre);
  if (state.sort) params.set("sort", state.sort);

  const qs = params.toString();
  const url = qs ? `${API_BASE_URL}?${qs}` : API_BASE_URL;

  setLoading(true);
  try {
    const data = await fetchJSON(url);
    renderReviews(data.items);
    setCounter(data.total_count);
    setFilteredHint(data.filtered_count, data.total_count);
  } catch (err) {
    showToast(err.message, "error");
    renderLoadError();
  } finally {
    setLoading(false);
  }
}

/* --------------------------------------------------------------------------
   CRUD-обработчики.
   -------------------------------------------------------------------------- */
async function handleSubmit(e) {
  e.preventDefault();
  clearFieldErrors();

  const formData = collectFormData();
  const clientErrors = validateForm(formData);
  if (Object.keys(clientErrors).length > 0) {
    showFieldErrors(clientErrors);
    return;
  }

  setSubmitLoading(true);
  try {
    if (state.editingId) {
      await fetchJSON(`${API_BASE_URL}/${state.editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      showToast("Изменения сохранены", "success");
      exitEditMode();
    } else {
      await fetchJSON(API_BASE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      showToast("Рецензия сохранена", "success");
      resetForm();
    }
    // Перезапрашиваем ленту — карточки и счётчик обновляются без перезагрузки,
    // с учётом текущей сортировки и фильтров.
    await fetchReviews();
  } catch (err) {
    if (err.data && err.data.fields) showFieldErrors(err.data.fields);
    showToast(err.message, "error");
  } finally {
    setSubmitLoading(false);
  }
}

function startEdit(review) {
  state.editingId = review.id;
  els.reviewId.value = review.id;
  els.title.value = review.title;
  els.artist.value = review.artist;
  setEntityType(review.entity_type);
  els.genre.value = review.genre;
  setRating(review.rating);
  els.text.value = review.text;
  els.coverUrl.value = review.cover_url;

  els.formTitle.textContent = "Редактирование рецензии";
  els.submitBtn.textContent = "Сохранить изменения";
  els.cancelBtn.hidden = false;

  clearFieldErrors();
  els.formPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function exitEditMode() {
  state.editingId = null;
  resetForm();
}

function resetForm() {
  els.reviewForm.reset();
  els.reviewId.value = "";
  setEntityType("album");
  setRating(0);
  clearFieldErrors();
  els.formTitle.textContent = "Новая рецензия";
  els.submitBtn.textContent = "Сохранить";
  els.cancelBtn.hidden = true;
}

function openDeleteModal(review) {
  deleteTargetId = review.id;
  els.confirmModal.hidden = false;
}

function closeDeleteModal() {
  els.confirmModal.hidden = true;
  deleteTargetId = null;
}

async function doDelete() {
  const id = deleteTargetId;
  closeDeleteModal();
  try {
    await fetchJSON(`${API_BASE_URL}/${id}`, { method: "DELETE" });
    showToast("Рецензия удалена", "success");
    await fetchReviews();
  } catch (err) {
    showToast(err.message, "error");
  }
}

/* --------------------------------------------------------------------------
   Рендеринг.
   -------------------------------------------------------------------------- */
function renderReviews(items) {
  els.reviewsList.innerHTML = "";
  els.emptyState.hidden = true;

  if (items.length === 0) {
    els.emptyState.hidden = false;
    const isFiltering = state.search || state.genre !== "all";
    els.emptyState.textContent = isFiltering
      ? "По вашему запросу рецензий не найдено"
      : "Рецензий пока нет — добавьте первую!";
    return;
  }

  items.forEach((review) => els.reviewsList.appendChild(buildCard(review)));
}

function buildCard(review) {
  const card = document.createElement("article");
  card.className = "review-card";
  card.dataset.id = review.id;

  // Обложка с заглушкой при ошибке загрузки.
  const img = document.createElement("img");
  img.className = "review-cover";
  img.alt = `Обложка: ${review.title}`;
  img.loading = "lazy";
  img.src = review.cover_url;
  img.addEventListener("error", () => {
    if (img.getAttribute("src") !== PLACEHOLDER_IMG) img.src = PLACEHOLDER_IMG;
  });

  const body = document.createElement("div");
  body.className = "review-body";

  const title = document.createElement("h3");
  title.className = "review-title";
  title.textContent = review.title;

  const artist = document.createElement("p");
  artist.className = "review-artist";
  artist.textContent = review.artist;

  const meta = document.createElement("div");
  meta.className = "review-meta";

  const typeBadge = document.createElement("span");
  typeBadge.className = "badge badge-type";
  typeBadge.textContent = ENTITY_TYPE_LABELS[review.entity_type] || review.entity_type;

  const genreBadge = document.createElement("span");
  genreBadge.className = "badge badge-genre";
  genreBadge.textContent = review.genre;

  const date = document.createElement("span");
  date.className = "review-date";
  date.textContent = review.date;

  meta.append(typeBadge, genreBadge, buildStars(review.rating), date);

  const text = document.createElement("p");
  text.className = "review-text";
  text.textContent = review.text;

  const actions = document.createElement("div");
  actions.className = "review-actions";

  // Кнопки редактирования/удаления показываем только владельцу рецензии.
  if (review.is_owner) {
    const editBtn = document.createElement("button");
    editBtn.className = "btn btn-ghost btn-sm";
    editBtn.textContent = "Редактировать";
    editBtn.addEventListener("click", () => startEdit(review));

    const delBtn = document.createElement("button");
    delBtn.className = "btn btn-danger btn-sm";
    delBtn.textContent = "Удалить";
    delBtn.addEventListener("click", () => openDeleteModal(review));

    actions.append(editBtn, delBtn);
  } else {
    const hint = document.createElement("span");
    hint.className = "review-actions-hint";
    hint.textContent = "Чужая рецензия";
    actions.append(hint);
  }
  body.append(title);
  // У рецензии на исполнителя название уже является именем — не дублируем строку.
  if (review.entity_type !== "artist") {
    body.append(artist);
  }
  body.append(meta, text, actions);
  card.append(img, body);
  return card;
}

function buildStars(rating) {
  const wrap = document.createElement("span");
  wrap.className = "stars stars-readonly";
  wrap.setAttribute("aria-label", `Оценка ${rating} из 5`);
  for (let i = 1; i <= 5; i++) {
    const star = document.createElement("span");
    star.textContent = "★";
    if (i <= rating) star.classList.add("active");
    wrap.appendChild(star);
  }
  return wrap;
}

function setCounter(total) {
  els.counter.textContent = `Рецензий на сайте: ${total}`;
}

function setFilteredHint(filtered, total) {
  if (filtered !== total) {
    els.filteredHint.textContent = `Показано: ${filtered} из ${total}`;
  } else {
    els.filteredHint.textContent = "";
  }
}

function setLoading(isLoading) {
  els.loadingState.hidden = !isLoading;
}

function renderLoadError() {
  els.reviewsList.innerHTML = "";
  els.emptyState.hidden = false;
  els.emptyState.textContent = "Не удалось загрузить рецензии. Попробуйте обновить страницу.";
}

/* --------------------------------------------------------------------------
   Звёздный рейтинг.
   -------------------------------------------------------------------------- */
function initStarRating() {
  const stars = els.reviewForm.querySelectorAll("#starRating button");
  stars.forEach((star) => {
    star.addEventListener("click", () => setRating(parseInt(star.dataset.value, 10)));
    star.addEventListener("mouseenter", () => highlightStars(parseInt(star.dataset.value, 10)));
  });
  document.getElementById("starRating").addEventListener("mouseleave", () => {
    highlightStars(parseInt(els.rating.value, 10) || 0);
  });
}

function setRating(value) {
  els.rating.value = value;
  highlightStars(value);
  const err = document.getElementById("ratingError");
  if (err) err.textContent = "";
}

function highlightStars(value) {
  document.querySelectorAll("#starRating button").forEach((star) => {
    star.classList.toggle("active", parseInt(star.dataset.value, 10) <= value);
  });
}

function getSelectedEntityType() {
  const checked = document.querySelector('input[name="entity_type"]:checked');
  return checked ? checked.value : "album";
}

function updateTypeFields() {
  const isArtist = getSelectedEntityType() === "artist";
  els.titleLabel.textContent = isArtist ? "Имя исполнителя" : "Название альбома / трека";
  els.title.placeholder = isArtist ? "Например: David Bowie" : "Например: Midnights";
  els.artistField.hidden = isArtist;
}

function setEntityType(value) {
  document.querySelectorAll('input[name="entity_type"]').forEach((r) => {
    r.checked = r.value === value;
  });
  updateTypeFields();
}

/* --------------------------------------------------------------------------
   Валидация формы.
   -------------------------------------------------------------------------- */
function collectFormData() {
  const type = getSelectedEntityType();
  return {
    title: els.title.value,
    // Для рецензии на исполнителя «название» и «исполнитель» — одно и то же имя.
    artist: type === "artist" ? els.title.value : els.artist.value,
    entity_type: type,
    genre: els.genre.value,
    rating: parseInt(els.rating.value, 10) || 0,
    text: els.text.value,
    cover_url: els.coverUrl.value,
  };
}

function validateForm(data) {
  const errors = {};

  if (!data.title.trim()) errors.title = "Поле обязательно для заполнения";
  else if (data.title.trim().length > 150) errors.title = "Максимум 150 символов";

  if (!data.artist.trim()) errors.artist = "Поле обязательно для заполнения";
  else if (data.artist.trim().length > 150) errors.artist = "Максимум 150 символов";

  const text = data.text.trim();
  if (!text) errors.text = "Поле обязательно для заполнения";
  else if (text.length < 10) errors.text = "Минимум 10 символов";
  else if (text.length > 3000) errors.text = "Максимум 3000 символов";

  if (!GENRES.includes(data.genre)) errors.genre = "Выберите жанр из списка";

  if (!data.rating || data.rating < 1 || data.rating > 5) {
    errors.rating = "Поставьте оценку от 1 до 5";
  }

  if (!isValidCoverUrl(data.cover_url)) {
    errors.cover_url = "Введите корректный URL (http:// или https://)";
  }

  return errors;
}

function isValidCoverUrl(value) {
  const v = value.trim();
  if (!v) return false;
  try {
    const url = new URL(v);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (_e) {
    return false;
  }
}

function showFieldErrors(errors) {
  Object.entries(errors).forEach(([field, message]) => {
    const mapping = FIELD_ERRORS[field];
    if (!mapping) return;
    const errorEl = document.getElementById(mapping.errorId);
    if (errorEl) errorEl.textContent = message;
    const input = mapping.input();
    if (input) input.classList.add("invalid");
  });
}

function clearFieldErrors() {
  Object.values(FIELD_ERRORS).forEach((mapping) => {
    const errorEl = document.getElementById(mapping.errorId);
    if (errorEl) errorEl.textContent = "";
    const input = mapping.input();
    if (input) input.classList.remove("invalid");
  });
}

function setSubmitLoading(isLoading) {
  els.submitBtn.disabled = isLoading;
  els.submitBtn.textContent = isLoading
    ? (state.editingId ? "Сохранение…" : "Добавление…")
    : (state.editingId ? "Сохранить изменения" : "Сохранить");
}

/* --------------------------------------------------------------------------
   Фильтры и поиск.
   -------------------------------------------------------------------------- */
function onSearchInput() {
  state.search = els.search.value.trim();
  fetchReviews();
}

function resetFilters() {
  els.search.value = "";
  els.genreFilter.value = "all";
  els.sortFilter.value = "date_desc";
  state.search = "";
  state.genre = "all";
  state.sort = "date_desc";
  fetchReviews();
}

function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/* --------------------------------------------------------------------------
   Уведомления (toast).
   -------------------------------------------------------------------------- */
function showToast(message, type = "success") {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  els.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-hide");
    setTimeout(() => toast.remove(), 350);
  }, 3500);
}
