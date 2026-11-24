# 🎵 Music Diary — веб-сервис музыкальных рецензий

Одностраничное веб-приложение для публикации, просмотра, поиска, фильтрации,
редактирования и удаления рецензий на музыкальные альбомы, треки и исполнителей.

## Стек

| Слой      | Технология                                   |
|-----------|----------------------------------------------|
| Бэкенд    | Python 3, Flask, flask-cors                  |
| БД        | SQLite (локальный файл)                      |
| Фронтенд  | HTML5, CSS3, чистый JavaScript (ES6+, Fetch) |
| Деплой    | Render / PythonAnywhere / VPS                |

## Структура проекта

```
music-diary/
├── app.py                  # Flask-бэкенд + REST API + инициализация БД
├── requirements.txt        # зависимости (gunicorn — только под Linux)
├── Procfile                # команда запуска для Render/Heroku
├── render.yaml             # blueprint для Render
├── .gitignore
├── README.md
└── static/
    ├── index.html          # разметка SPA
    ├── css/style.css       # стили
    ├── js/app.js           # клиентская логика
    └── img/placeholder.svg # заглушка для битых обложек
```

## Локальный запуск

```bash
cd music-diary
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Откройте <http://127.0.0.1:5000>. БД `music_diary.db` создаётся автоматически
при первом запуске (вместе с таблицей `reviews` и демо-данными). Чтобы отключить
демо-данные, замените `SEED_REVIEWS` в `app.py` на `[]`.

> На Windows `gunicorn` не ставится (он нужен только на Linux-сервере), поэтому
> в `requirements.txt` для него указан маркер `sys_platform != "win32"`.

## REST API

База всех запросов: `GET/POST /api/reviews`, `PUT/DELETE /api/reviews/<id>`.

### GET /api/reviews
Необязательные query-параметры (комбинируются):

| Параметр | Описание                                                            |
|----------|---------------------------------------------------------------------|
| `search` | регистронезависимый поиск подстроки по `title` и `artist`           |
| `genre`  | точный фильтр по жанру; пустой или `all` — без фильтра              |
| `sort`   | `date_desc` (по умолч.), `date_asc`, `rating_desc`, `rating_asc`    |

Ответ:

```json
{
  "total_count": 5,
  "filtered_count": 3,
  "items": [ { "id": 12, "title": "Midnights", "artist": "Taylor Swift",
               "entity_type": "album", "genre": "Поп", "rating": 4,
               "text": "…", "cover_url": "https://…", "date": "24.11.2026" } ]
}
```

### POST /api/reviews — 201 Created
Принимает JSON `{ title, artist, entity_type, genre, rating, text, cover_url }`.
`id`, `date` (ДД.ММ.ГГГГ) и `created_ts` генерирует сервер. Возвращает полный
JSON созданной рецензии.

### PUT /api/reviews/<id> — 200 / 400 / 404
Обновляет все поля, кроме даты создания. Возвращает обновлённый объект.

### DELETE /api/reviews/<id> — 200 / 404
Возвращает `{"status": "deleted", "id": <id>}`.

### Валидация (POST и PUT)
При ошибке возвращается `400`:

```json
{ "error": "Validation failed",
  "fields": { "title": "Поле обязательно для заполнения",
              "cover_url": "Некорректный формат URL" } }
```

Правила: `title`/`artist` — 1–150 симв., `text` — 10–3000 симв., `genre` — из
списка, `entity_type` — `album`/`track`/`artist`, `rating` — целое 1–5,
`cover_url` — валидный `http(s)://` URL.

Любая нештатная ошибка перехватывается глобальным обработчиком и возвращает
`{"error": "…"}` вместо «молчаливого» 500. Все SQL-запросы — параметризованные
(без конкатенации), что исключает SQL-инъекции.

## Деплой

### Render (рекомендуется)
1. Залейте проект в репозиторий GitHub/GitLab.
2. Render Dashboard → **New → Web Service** → укажите репозиторий.
3. Build Command: `pip install -r requirements.txt`
   Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
   (или просто используйте приложенный `render.yaml` через **New → Blueprint**).
4. Для сохранности данных между рестартами подключите **Persistent Disk**
   (Render Dashboard → Disks), смонтируйте его, например, в `/var/data` и задайте
   переменную окружения `DATABASE_PATH=/var/data/music_diary.db`.
   Без диска бесплатный тариф может сбрасывать файловую систему при деплое.

### PythonAnywhere
1. Загрузите файлы, создайте виртуальное окружение и установите `flask` + `flask-cors`.
2. Создайте новое веб-приложение Flask, укажите WSGI-файл, который импортирует
   `app` из `app.py` (например, `from app import app as application`).
3. Настройте Static files: `/static/` → каталог `static`.
4. Данные в `music_diary.db` на PythonAnywhere сохраняются между рестартами
   автоматически (файловая система постоянная).

### VPS (nginx + gunicorn + systemd)
```bash
pip install -r requirements.txt
gunicorn app:app --bind 127.0.0.1:8000 --workers 1
```
и проксируйте через nginx. Файл БД лежит рядом с проектом; для надёжности
настройте периодическое резервное копирование `music_diary.db` (cron).

## Как раздать сайт другим по QR-коду

QR-код — это просто закодированный адрес сайта. Сначала получите адрес, доступный
другим людям, затем превратите его в картинку (см. «Генерация QR» ниже).

### Вариант А — все в одной сети (Wi-Fi)
Подходит, если сканирующие находятся в той же локальной сети (аудитория, дом).

1. Запустите сервер: `python app.py` (он уже слушает `0.0.0.0:5000`).
2. Узнайте IP машины: в PowerShell выполните `ipconfig` и найдите строку
   `IPv4-адрес` (вида `192.168.x.x`).
3. Откройте порт в брандмауэре (PowerShell **от имени администратора**):
   `netsh advfirewall firewall add rule name="MusicDiary5000" dir=in action=allow protocol=TCP localport=5000`
4. Адрес для QR: `http://192.168.x.x:5000`.

### Вариант Б — для всех в интернете (публичный туннель)
Работает из любой сети, в том числе с мобильного интернета.

1. Запустите сервер: `python app.py`.
2. Скачайте `cloudflared` (GitHub → cloudflared → Releases → `cloudflared-windows-amd64.exe`)
   и запустите: `cloudflared.exe tunnel --url http://localhost:5000`.
3. В терминале появится публичный адрес вида `https://xxxx.trycloudflare.com`.
   (Альтернатива — `ngrok http 5000`, потребуется бесплатный аккаунт.)

### Генерация QR
- Скриптом из проекта: `pip install qrcode[pil]`, затем `python qr.py "ВАШ_АДРЕС"`.
- Одной командой без установки:
  `curl.exe -L "https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=ВАШ_АДРЕС" -o qr.png`
- Онлайн: любой генератор QR (например qr-code-generator.com), вставить адрес, скачать PNG.

## Конфигурация

| Переменная       | Назначение                              | По умолчанию                  |
|------------------|-----------------------------------------|-------------------------------|
| `DATABASE_PATH`  | путь к файлу SQLite                     | `./music_diary.db`            |
| `PORT`           | порт (`python app.py`)                  | `5000`                        |
| `FLASK_DEBUG`    | режим отладки (`1`)                     | выключен                      |

URL бэкенда на фронтенде вынесен в единую константу `API_BASE_URL` в начале
`static/js/app.js`.

## Критерии приёмки

- ✅ Лента и счётчик загружаются в Chrome / Firefox / Safari.
- ✅ Клиентская валидация блокирует пустую форму и «абракадабру» в поле URL.
- ✅ Создание/редактирование/удаление происходят без перезагрузки (Fetch + DOM).
- ✅ Данные сохраняются в SQLite и переживают F5 и рестарт сервера.
- ✅ Поиск (с debounce 350 мс), фильтр по жанру и сортировка работают вместе.
- ✅ Некорректный POST напрямую в API возвращает `400` с понятным JSON.
- ✅ Пользовательские тексты вставляются через `textContent` (защита от XSS).
- ✅ Битые обложки заменяются локальной заглушкой через `onerror`.
