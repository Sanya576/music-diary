"""Генератор QR-кода для раздачи адреса сайта Music Diary.

Установка зависимости (один раз):
    pip install qrcode[pil]

Использование:
    python qr.py "http://192.168.1.5:5000"          # адрес -> qr.png
    python qr.py "https://адрес" "имя_файла.png"     # свой файл
"""
import sys


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    out = sys.argv[2] if len(sys.argv) > 2 else "qr.png"

    try:
        import qrcode
    except ImportError:
        print("Не установлена библиотека qrcode. Выполните: pip install qrcode[pil]")
        sys.exit(1)

    img = qrcode.make(url)
    img.save(out)
    print(f"QR-код сохранён: {out}  (адрес: {url})")


if __name__ == "__main__":
    main()
