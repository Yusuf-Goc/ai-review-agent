# Vestel AI Code Reviewer Agent

Bu proje, Git diff verisini analiz ederek kritik syntax hatasi, mantik hatasi,
guvenlik riski, kaynak/bellek sizintisi ve geriye donuk uyumluluk sorunlarini
raporlamayi hedefleyen bir yapay zeka kod inceleme ajanidir.

Su anki surum GitHub/GitLab entegrasyonu yerine agent cekirdegine odaklanir:
unified diff metnini parse eder, dosya/hunk/satir baglamini korur ve Gemini'ye
semali JSON review istegi gonderir.

## Altyapi ve Bagimliliklar

- **Dil:** Python 3.10+
- **Yapay zeka:** Gemini (`google-genai`)
- **Diff parser:** `unidiff`
- **Konfigurasyon:** `.env` uzerinden `GEMINI_API_KEY` veya `GOOGLE_API_KEY`

## Kurulum

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`.env` dosyasi olusturun:

```bash
GEMINI_API_KEY=your-api-key
```

## Kullanim

Ornek diff ile Gemini review calistirma:

```bash
python3 cli.py --demo
```

Sadece parserin urettigi JSON payload'u gorme:

```bash
python3 cli.py --demo --dump-payload
```

Bir diff dosyasini inceleme:

```bash
python3 cli.py --diff-file changes.diff
```

Commit karsilastirmasi olmadan herhangi bir kod dosyasini inceleme:

```bash
python3 cli.py --code-file sample.py
python3 cli.py --code-file query.sql --language sql
python3 cli.py --code-file main.cpp
python3 cli.py --code-file Program.cs
python3 cli.py --code-file App.java
```

Stdin uzerinden Git diff inceleme:

```bash
git diff | python3 cli.py
```

Stdin uzerinden ham kod inceleme:

```bash
cat query.sql | python3 cli.py --language sql
```

## Test

Yerel testler Gemini'ye baglanmaz; fake client ile agent cekirdeginin dogru
payload urettigini ve JSON kontratini korudugunu kontrol eder.

```bash
python3 -m unittest discover -s tests
```

Gercek Gemini cagrisi icin `.env` dosyasinda API key olmali ve internet erisimi
bulunmalidir:

```bash
python3 cli.py --demo
python3 cli.py --code-file sample.py
```

Gemini `503 UNAVAILABLE` veya `high demand` donerse bu genellikle modelin gecici
yogun oldugu anlamina gelir. Agent gecici hatalarda otomatik tekrar dener.
Tekrar sayisini artirmak icin:

```bash
python3 cli.py --code-file samples/unsafe_query.sql --retries 4 --retry-delay 3
```

Farkli bir model denemek istersen:

```bash
python3 cli.py --code-file samples/unsafe_query.sql --model gemini-2.5-flash
```

## Tasarim Notlari

- Parser yalnizca eklenen satirlari degil, silinen satirlari ve context satirlarini
  da modele verir.
- Commit farki olmadiginda full-code modu dosyanin tamamini satir numaralariyla
  modele gonderir.
- Binary, silinen, eklenen, rename edilen ve degistirilen dosyalar ayri
  `change_type` degeriyle tasinir.
- Kod icindeki prompt benzeri metinler talimat degil veri olarak isaretlenir.
- Modelden yalnizca JSON beklenir; bu yapi ileride GitHub/GitLab yorumlarina
  dogrudan donusturulebilir.
- Buyuk diff'ler icin `--max-review-lines` ile satir limiti uygulanir.
