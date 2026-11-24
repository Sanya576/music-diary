"""Music Diary — веб-сервис музыкальных рецензий.

Бэкенд на Flask + SQLite. Реализует REST API для CRUD-операций над рецензиями,
поиск, фильтрацию по жанру и сортировку, а также отдаёт статический фронтенд.

Запуск:
    python app.py                # локально (порт 5000 или $PORT)
    gunicorn app:app             # продакшен (Linux)
"""

import os
import sqlite3
import time
import uuid
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Путь к файлу БД. Переопределяется переменной окружения DATABASE_PATH —
# важно на Render/PythonAnywhere/VPS, где нужен постоянный диск.
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "music_diary.db"))

# Абсолютный путь к каталогу со статикой (не зависит от текущей рабочей директории).
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Фиксированный справочник жанров и допустимые типы объектов.
GENRES = ["Рок", "Поп", "Рэп", "Инди", "Электроника", "Джаз", "Метал", "R&B", "Другое"]
ENTITY_TYPES = ["album", "track", "artist"]

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.json.ensure_ascii = False  # чтобы кириллица в JSON оставалась читаемой

# CORS включён для любых источников (локальный Live Server + прод).
CORS(app)


# ---------------------------------------------------------------------------
# Работа с БД
# ---------------------------------------------------------------------------
def _lower_ci(value):
    """Unicode-регистронезависимое приведение к нижнему регистру.

    Встроенная функция LOWER() в SQLite работает только с ASCII, поэтому для
    корректного поиска по кириллице регистрируем собственную.
    """
    return value.lower() if isinstance(value, str) else value


def get_db():
    """Открывает новое соединение с БД (по одному на запрос)."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.create_function("lower_ci", 1, _lower_ci, deterministic=True)
    return conn


def init_db():
    """Создаёт файл БД и таблицу reviews, если их ещё нет."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                artist      TEXT    NOT NULL,
                entity_type TEXT    NOT NULL DEFAULT 'album',
                genre       TEXT    NOT NULL,
                rating      INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                text        TEXT    NOT NULL,
                cover_url   TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                created_ts  INTEGER NOT NULL,
                owner_id    TEXT
            )
            """
        )
        conn.commit()

        # Миграция старых БД: добавить owner_id, если колонки ещё нет.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(reviews)").fetchall()]
        if "owner_id" not in cols:
            conn.execute("ALTER TABLE reviews ADD COLUMN owner_id TEXT")
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def row_to_dict(row, is_owner=False):
    """Преобразует строку БД в единый JSON-объект рецензии (см. ТЗ, п. 2.3).

    Поле `is_owner` показывает, принадлежит ли рецензия текущему клиенту.
    Сам owner_id в ответ не попадает, чтобы его нельзя было подделать.
    """
    return {
        "id": row["id"],
        "title": row["title"],
        "artist": row["artist"],
        "entity_type": row["entity_type"],
        "genre": row["genre"],
        "rating": row["rating"],
        "text": row["text"],
        "cover_url": row["cover_url"],
        "date": row["created_at"],
        "is_owner": bool(is_owner),
    }


def current_client_id():
    """Идентификатор клиента из заголовка X-Client-Id (его генерирует фронтенд)."""
    return (request.headers.get("X-Client-Id") or "").strip()


def is_valid_cover_url(value):
    """Валидация URL обложки: строка, http:// или https://, с хостом."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_payload(data):
    """Серверная валидация для POST и PUT.

    Возвращает словарь ошибок по полям (пустой — если всё корректно).
    """
    fields = {}

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        fields["title"] = "Поле обязательно для заполнения"
    elif len(title.strip()) > 150:
        fields["title"] = "Максимальная длина 150 символов"

    artist = data.get("artist")
    if not isinstance(artist, str) or not artist.strip():
        fields["artist"] = "Поле обязательно для заполнения"
    elif len(artist.strip()) > 150:
        fields["artist"] = "Максимальная длина 150 символов"

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        fields["text"] = "Поле обязательно для заполнения"
    elif len(text.strip()) < 10:
        fields["text"] = "Минимум 10 символов"
    elif len(text.strip()) > 3000:
        fields["text"] = "Максимум 3000 символов"

    if data.get("genre") not in GENRES:
        fields["genre"] = "Недопустимый жанр"

    if data.get("entity_type") not in ENTITY_TYPES:
        fields["entity_type"] = "Недопустимый тип объекта"

    rating = data.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, int) or not (1 <= rating <= 5):
        fields["rating"] = "Оценка должна быть целым числом от 1 до 5"

    if not is_valid_cover_url(data.get("cover_url")):
        fields["cover_url"] = "Некорректный формат URL"

    return fields


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@app.route("/api/reviews", methods=["GET"])
def list_reviews():
    """GET /api/reviews — список рецензий с поиском, фильтром и сортировкой."""
    search = request.args.get("search", "").strip()
    genre = request.args.get("genre", "").strip()
    sort = request.args.get("sort", "date_desc").strip()

    # Белый список сортировок — исключает SQL-инъекцию через параметр sort.
    sort_sql = {
        "date_desc": "created_ts DESC, id DESC",
        "date_asc": "created_ts ASC, id ASC",
        "rating_desc": "rating DESC, created_ts DESC",
        "rating_asc": "rating ASC, created_ts DESC",
    }
    if sort not in sort_sql:
        return jsonify({"error": "Недопустимый параметр sort"}), 400

    where = []
    params = []
    if search:
        like = f"%{search.lower()}%"
        where.append("(lower_ci(title) LIKE ? OR lower_ci(artist) LIKE ?)")
        params.extend([like, like])
    if genre and genre != "all":
        where.append("genre = ?")
        params.append(genre)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    client_id = current_client_id()

    conn = get_db()
    try:
        total_count = conn.execute("SELECT COUNT(*) AS c FROM reviews").fetchone()["c"]
        filtered_count = conn.execute(
            f"SELECT COUNT(*) AS c FROM reviews {where_sql}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM reviews {where_sql} ORDER BY {sort_sql[sort]}", params
        ).fetchall()
    finally:
        conn.close()

    items = [row_to_dict(r, is_owner=(r["owner_id"] == client_id)) for r in rows]
    return jsonify({"total_count": total_count, "filtered_count": filtered_count, "items": items}), 200


@app.route("/api/reviews", methods=["POST"])
def create_review():
    """POST /api/reviews — создание новой рецензии."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Некорректный формат JSON"}), 400

    errors = validate_payload(data)
    if errors:
        return jsonify({"error": "Validation failed", "fields": errors}), 400

    now = datetime.now()
    created_at = now.strftime("%d.%m.%Y")
    created_ts = int(time.time())
    # Владелец — клиент из заголовка; если заголовка нет, рецензия «ничья».
    owner_id = current_client_id() or uuid.uuid4().hex

    conn = get_db()
    try:
        cur = conn.execute(
            """
            INSERT INTO reviews
                (title, artist, entity_type, genre, rating, text, cover_url, created_at, created_ts, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["title"].strip(),
                data["artist"].strip(),
                data["entity_type"],
                data["genre"],
                data["rating"],
                data["text"].strip(),
                data["cover_url"].strip(),
                created_at,
                created_ts,
                owner_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM reviews WHERE id = ?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()

    return jsonify(row_to_dict(row, is_owner=True)), 201


@app.route("/api/reviews/<int:review_id>", methods=["PUT"])
def update_review(review_id):
    """PUT /api/reviews/<id> — редактирование существующей рецензии."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Некорректный формат JSON"}), 400

    errors = validate_payload(data)
    if errors:
        return jsonify({"error": "Validation failed", "fields": errors}), 400

    client_id = current_client_id()

    conn = get_db()
    try:
        existing = conn.execute("SELECT id, owner_id FROM reviews WHERE id = ?", (review_id,)).fetchone()
        if existing is None:
            return jsonify({"error": "Рецензия не найдена"}), 404
        if not client_id or existing["owner_id"] != client_id:
            return jsonify({"error": "Нельзя редактировать чужую рецензию"}), 403

        conn.execute(
            """
            UPDATE reviews
            SET title = ?, artist = ?, entity_type = ?, genre = ?,
                rating = ?, text = ?, cover_url = ?
            WHERE id = ?
            """,
            (
                data["title"].strip(),
                data["artist"].strip(),
                data["entity_type"],
                data["genre"],
                data["rating"],
                data["text"].strip(),
                data["cover_url"].strip(),
                review_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    finally:
        conn.close()

    return jsonify(row_to_dict(row, is_owner=True)), 200


@app.route("/api/reviews/<int:review_id>", methods=["DELETE"])
def delete_review(review_id):
    """DELETE /api/reviews/<id> — удаление рецензии."""
    client_id = current_client_id()

    conn = get_db()
    try:
        existing = conn.execute("SELECT id, owner_id FROM reviews WHERE id = ?", (review_id,)).fetchone()
        if existing is None:
            return jsonify({"error": "Рецензия не найдена"}), 404
        if not client_id or existing["owner_id"] != client_id:
            return jsonify({"error": "Нельзя удалить чужую рецензию"}), 403

        conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"status": "deleted", "id": review_id}), 200


# ---------------------------------------------------------------------------
# Фронтенд
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Глобальная обработка ошибок — никаких «молчаливых» 500.
# ---------------------------------------------------------------------------
@app.errorhandler(400)
def bad_request(_e):
    return jsonify({"error": "Некорректный запрос"}), 400


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Ресурс не найден"}), 404


@app.errorhandler(405)
def method_not_allowed(_e):
    return jsonify({"error": "Метод не разрешён"}), 405


@app.errorhandler(Exception)
def handle_unexpected(e):
    app.logger.exception("Unhandled exception: %s", e)
    return jsonify({"error": "Внутренняя ошибка сервера"}), 500


# Инициализация БД при старте (работает и для `python app.py`, и для gunicorn).
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
