"""Тесты логики Music Diary без установленного Flask.

Запуск (Python 3, стандартная библиотека):
    python -m unittest tests.test_api -v

Стабы `flask` и `flask_cors` позволяют импортировать app.py и проверять
валидацию, SQL-запросы и обработчики на настоящем SQLite.
"""

import os
import re
import sys
import types
import unittest

# Путь к каталогу проекта (на уровень выше tests/).
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ---------------------------------------------------------------------------
# Стабы flask / flask_cors
# ---------------------------------------------------------------------------
class _JSON:
    ensure_ascii = True


class _Logger:
    def exception(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Flask:
    def __init__(self, *a, **k):
        self.static_folder = k.get("static_folder")
        self.json = _JSON()
        self.logger = _Logger()

    def route(self, rule, **k):
        def deco(f):
            return f
        return deco

    def errorhandler(self, code):
        def deco(f):
            return f
        return deco

    def run(self, *a, **k):
        pass


def _jsonify(payload, *a, **k):
    return payload


def _send_from_directory(*a, **k):
    return b""


flask = types.ModuleType("flask")
flask.Flask = _Flask
flask.jsonify = _jsonify
flask.send_from_directory = _send_from_directory
flask.request = None
sys.modules["flask"] = flask

flask_cors = types.ModuleType("flask_cors")
flask_cors.CORS = lambda *a, **k: None
sys.modules["flask_cors"] = flask_cors

# ---------------------------------------------------------------------------
# Временная БД (создаётся до импорта app, т.к. init_db() выполняется при импорте)
# ---------------------------------------------------------------------------
TEST_DB = os.path.join(PROJECT_DIR, "_test_tmp.sqlite")
for suffix in ("", "-journal", "-wal", "-shm"):
    p = TEST_DB + suffix
    if os.path.exists(p):
        os.remove(p)
os.environ["DATABASE_PATH"] = TEST_DB

import app  # noqa: E402  (теперь видит стабы и временную БД)


CID_A = "client-aaaaaaaa"
CID_B = "client-bbbbbbbb"


class FakeRequest:
    def __init__(self, args=None, json_data=None, headers=None):
        self.args = args if args is not None else {}
        self._json = json_data
        self.headers = headers if headers is not None else {}

    def get_json(self, silent=True):
        return self._json


def set_request(args=None, json_data=None, headers=None):
    app.request = FakeRequest(args, json_data, headers)


# Демо-данные для тестов (в самом приложении их больше нет).
SEEDS = [
    ("Группа крови", "Кино", "album", "Рок", 5,
     "Легендарный альбом, определивший звучание целого поколения. Каждая песня — гимн, который не устарел и сегодня.",
     "https://picsum.photos/seed/kino/600/600", "24.11.2026", 1784630400),
    ("Random Access Memories", "Daft Punk", "album", "Электроника", 5,
     "Идеально выверенный нео-диско альбом с живыми музыкантами и безупречным продакшеном.",
     "https://picsum.photos/seed/daftpunk/600/600", "24.11.2026", 1784630401),
    ("Igor", "Tyler, The Creator", "album", "Рэп", 4,
     "Эмоциональный и экспериментальный альбом о расставании, смело ломающий жанровые границы.",
     "https://picsum.photos/seed/igor/600/600", "24.11.2026", 1784630402),
    ("Bohemian Rhapsody", "Queen", "track", "Рок", 5,
     "Эпохальный трек, соединивший рок, оперу и балладу в одной шестиминутной композиции.",
     "https://picsum.photos/seed/queen/600/600", "24.11.2026", 1784630403),
]


def reset_db():
    """Возвращает БД к исходному состоянию (только демо-данные для тестов)."""
    conn = app.get_db()
    try:
        conn.execute("DELETE FROM reviews")
        conn.executemany(
            """
            INSERT INTO reviews
                (title, artist, entity_type, genre, rating, text, cover_url, created_at, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            SEEDS,
        )
        conn.commit()
    finally:
        conn.close()


class ValidationTest(unittest.TestCase):
    def _valid(self):
        return {
            "title": "Midnights",
            "artist": "Taylor Swift",
            "entity_type": "album",
            "genre": "Поп",
            "rating": 4,
            "text": "Атмосферный синти-поп альбом с сильной лирикой.",
            "cover_url": "https://example.com/cover.jpg",
        }

    def test_valid(self):
        self.assertEqual(app.validate_payload(self._valid()), {})

    def test_empty_title(self):
        d = self._valid(); d["title"] = "   "
        self.assertEqual(app.validate_payload(d)["title"], "Поле обязательно для заполнения")

    def test_long_title(self):
        d = self._valid(); d["title"] = "x" * 151
        self.assertEqual(app.validate_payload(d)["title"], "Максимальная длина 150 символов")

    def test_missing_artist(self):
        d = self._valid(); del d["artist"]
        self.assertEqual(app.validate_payload(d)["artist"], "Поле обязательно для заполнения")

    def test_short_text(self):
        d = self._valid(); d["text"] = "коротко"
        self.assertEqual(app.validate_payload(d)["text"], "Минимум 10 символов")

    def test_long_text(self):
        d = self._valid(); d["text"] = "x" * 3001
        self.assertEqual(app.validate_payload(d)["text"], "Максимум 3000 символов")

    def test_bad_genre(self):
        d = self._valid(); d["genre"] = "Шансон"
        self.assertEqual(app.validate_payload(d)["genre"], "Недопустимый жанр")

    def test_bad_entity_type(self):
        d = self._valid(); d["entity_type"] = "single"
        self.assertEqual(app.validate_payload(d)["entity_type"], "Недопустимый тип объекта")

    def test_rating_out_of_range(self):
        d = self._valid(); d["rating"] = 10
        self.assertIn("rating", app.validate_payload(d))

    def test_rating_string_rejected(self):
        d = self._valid(); d["rating"] = "4"
        self.assertIn("rating", app.validate_payload(d))

    def test_rating_float_rejected(self):
        d = self._valid(); d["rating"] = 4.5
        self.assertIn("rating", app.validate_payload(d))

    def test_rating_bool_rejected(self):
        d = self._valid(); d["rating"] = True
        self.assertIn("rating", app.validate_payload(d))

    def test_bad_cover_url(self):
        d = self._valid(); d["cover_url"] = "абракадабра"
        self.assertEqual(app.validate_payload(d)["cover_url"], "Некорректный формат URL")

    def test_cover_url_ftp_rejected(self):
        d = self._valid(); d["cover_url"] = "ftp://example.com/a.jpg"
        self.assertEqual(app.validate_payload(d)["cover_url"], "Некорректный формат URL")


class CoverUrlTest(unittest.TestCase):
    def test_valid_http(self):
        self.assertTrue(app.is_valid_cover_url("http://a.com/x.jpg"))

    def test_valid_https(self):
        self.assertTrue(app.is_valid_cover_url("https://a.com/x.jpg"))

    def test_invalid_empty(self):
        self.assertFalse(app.is_valid_cover_url(""))

    def test_invalid_garbage(self):
        self.assertFalse(app.is_valid_cover_url("not a url"))


class ListReviewsTest(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_default_listing(self):
        set_request(args={})
        data, status = app.list_reviews()
        self.assertEqual(status, 200)
        self.assertEqual(data["total_count"], 4)
        self.assertEqual(data["filtered_count"], 4)
        self.assertEqual(len(data["items"]), 4)
        # По умолчанию — сначала новые.
        self.assertEqual(data["items"][0]["title"], "Bohemian Rhapsody")

    def test_search_cyrillic_case_insensitive(self):
        set_request(args={"search": "кино"})
        data, _ = app.list_reviews()
        self.assertEqual(data["filtered_count"], 1)
        self.assertEqual(data["items"][0]["artist"], "Кино")

    def test_search_latin(self):
        set_request(args={"search": "daft"})
        data, _ = app.list_reviews()
        self.assertEqual(data["filtered_count"], 1)
        self.assertEqual(data["items"][0]["title"], "Random Access Memories")

    def test_search_no_match(self):
        set_request(args={"search": "несуществующее"})
        data, _ = app.list_reviews()
        self.assertEqual(data["filtered_count"], 0)
        self.assertEqual(data["items"], [])

    def test_genre_filter(self):
        set_request(args={"genre": "Рок"})
        data, _ = app.list_reviews()
        self.assertEqual(data["filtered_count"], 2)

    def test_genre_all_is_no_filter(self):
        set_request(args={"genre": "all"})
        data, _ = app.list_reviews()
        self.assertEqual(data["filtered_count"], 4)

    def test_sort_rating_asc(self):
        set_request(args={"sort": "rating_asc"})
        data, _ = app.list_reviews()
        self.assertEqual(data["items"][0]["title"], "Igor")

    def test_sort_rating_desc(self):
        set_request(args={"sort": "rating_desc"})
        data, _ = app.list_reviews()
        self.assertEqual(data["items"][0]["title"], "Bohemian Rhapsody")

    def test_sort_date_asc(self):
        set_request(args={"sort": "date_asc"})
        data, _ = app.list_reviews()
        self.assertEqual(data["items"][0]["title"], "Группа крови")

    def test_invalid_sort_returns_400(self):
        set_request(args={"sort": "bogus"})
        _, status = app.list_reviews()
        self.assertEqual(status, 400)

    def test_combined_search_genre(self):
        set_request(args={"search": "rhapsody", "genre": "Рок"})
        data, _ = app.list_reviews()
        self.assertEqual(data["filtered_count"], 1)


class CreateUpdateDeleteTest(unittest.TestCase):
    def setUp(self):
        reset_db()

    NEW = {
        "title": "Kind of Blue",
        "artist": "Miles Davis",
        "entity_type": "album",
        "genre": "Джаз",
        "rating": 5,
        "text": "Вечная классика модального джаза, обязательная к прослушиванию.",
        "cover_url": "https://example.com/kob.jpg",
    }

    def test_create_returns_201_and_full_object(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        data, status = app.create_review()
        self.assertEqual(status, 201)
        self.assertGreater(data["id"], 0)
        self.assertEqual(data["title"], "Kind of Blue")
        self.assertTrue(re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", data["date"]))
        self.assertNotIn("created_ts", data)  # контракт отдаёт только "date"
        self.assertTrue(data["is_owner"])

        set_request(args={}, headers={"X-Client-Id": CID_A})
        listing, _ = app.list_reviews()
        self.assertEqual(listing["total_count"], 5)

    def test_create_validation_error_400(self):
        bad = dict(self.NEW); bad["rating"] = 10
        set_request(json_data=bad)
        data, status = app.create_review()
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "Validation failed")
        self.assertIn("rating", data["fields"])

    def test_create_invalid_json_400(self):
        set_request(json_data=None)
        data, status = app.create_review()
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "Некорректный формат JSON")

    def test_update_existing(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        created, _ = app.create_review()
        rid = created["id"]

        updated = dict(self.NEW)
        updated["text"] = "Новый текст рецензии с новым содержанием."
        updated["rating"] = 3
        set_request(json_data=updated, headers={"X-Client-Id": CID_A})
        data, status = app.update_review(rid)
        self.assertEqual(status, 200)
        self.assertEqual(data["rating"], 3)
        self.assertEqual(data["text"], updated["text"])
        self.assertEqual(data["date"], created["date"])  # дата не меняется

    def test_update_not_found_404(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        _, status = app.update_review(999999)
        self.assertEqual(status, 404)

    def test_delete_existing_and_not_found(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        created, _ = app.create_review()
        rid = created["id"]

        set_request(headers={"X-Client-Id": CID_A})
        data, status = app.delete_review(rid)
        self.assertEqual(status, 200)
        self.assertEqual(data, {"status": "deleted", "id": rid})

        set_request(headers={"X-Client-Id": CID_A})
        _, status = app.delete_review(rid)
        self.assertEqual(status, 404)

    def test_delete_others_review_403(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        created, _ = app.create_review()
        rid = created["id"]

        set_request(headers={"X-Client-Id": CID_B})
        data, status = app.delete_review(rid)
        self.assertEqual(status, 403)
        self.assertIn("чужую", data["error"])

    def test_update_others_review_403(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        created, _ = app.create_review()
        rid = created["id"]

        updated = dict(self.NEW); updated["rating"] = 1
        set_request(json_data=updated, headers={"X-Client-Id": CID_B})
        _, status = app.update_review(rid)
        self.assertEqual(status, 403)

    def test_delete_without_client_id_403(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        created, _ = app.create_review()
        rid = created["id"]

        set_request()  # без заголовка X-Client-Id
        _, status = app.delete_review(rid)
        self.assertEqual(status, 403)

    def test_is_owner_flag(self):
        set_request(json_data=dict(self.NEW), headers={"X-Client-Id": CID_A})
        created, _ = app.create_review()

        set_request(args={}, headers={"X-Client-Id": CID_A})
        data, _ = app.list_reviews()
        mine = [i for i in data["items"] if i["id"] == created["id"]][0]
        self.assertTrue(mine["is_owner"])

        set_request(args={}, headers={"X-Client-Id": CID_B})
        data, _ = app.list_reviews()
        not_mine = [i for i in data["items"] if i["id"] == created["id"]][0]
        self.assertFalse(not_mine["is_owner"])


def tearDownModule():
    for suffix in ("", "-journal", "-wal", "-shm"):
        p = TEST_DB + suffix
        if os.path.exists(p):
            os.remove(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
