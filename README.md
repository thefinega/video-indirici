# Video İndirici

Basit, portable Windows arayüzü ile `yt-dlp` üzerinden video veya playlist indirmek için hazırlanmıştır.

## Özellikler

- Türkçe Tkinter arayüzü
- Tek video veya playlist linki
- 480p / 720p / 1080p / 4K kalite seçimi
- İndirme klasörü seçimi
- Varsayılan indirme klasörü: uygulama klasöründeki `indirilenler`
- Tek satırlık ilerleme göstergesi ve playlist sayacı
- `yt-dlp.exe`, `ffmpeg.exe`, `deno.exe` otomatik kontrolü
- Daha önce indirilenleri `indirilenler.txt` arşiviyle atlama
- İsteğe bağlı Firefox çerez desteği
- Harici Python paketi gerektirmez

## Portable Kullanım

Uygulama klasörünü açın ve:

```text
Video Indirici.exe
```

dosyasını çalıştırın.

Şu dosyalar aynı klasörde kalmalıdır:

```text
Video Indirici.exe
yt-dlp.exe
ffmpeg.exe
deno.exe
_internal
README.txt
DISCLAIMER.txt
THIRD_PARTY_NOTICES.txt
```

## Kalite Seçenekleri

Uygulama 480p, 720p, 1080p ve 4K seçenekleri sunar. Seçilen kalite, mümkün olan en yüksek eşleşen çözünürlüğü ister. Kaynak videoda seçilen kalite yoksa `yt-dlp` aynı sınır içinde en uygun alternatifi seçer.

4K videolar platforma göre VP9 veya AV1 formatında gelebilir. Bu yüzden 4K seçeneği, 480p/720p/1080p seçeneklerine göre daha esnek format seçimi kullanır.

## İndirme Klasörü ve İlerleme

Uygulama ilk açılışta indirme klasörünü kendi klasöründeki `indirilenler` klasörü olarak ayarlar. Kullanıcı arayüzden farklı bir klasör seçebilir.

Playlist indirirken ilerleme alanı `Video 3/12` gibi sayaç gösterir. Mevcut videonun yüzde, boyut, hız ve ETA bilgisi aynı satırda güncellenir; tekrar eden yt-dlp progress satırları işlem günlüğünü doldurmaz.

## Firefox Çerezleri

Bazı videolar giriş, yaş doğrulaması veya bot kontrolü nedeniyle tarayıcı çerezlerine ihtiyaç duyabilir. Arayüzde `Firefox çerezlerini kullan` seçilirse `yt-dlp` yerel Firefox profilinden çerez okur. Bu uygulama çerezleri saklamaz, dışarı göndermez ve ayrı bir hesap bilgisi istemez.

## Kaynaktan Çalıştırma

Python 3 ile:

```powershell
python video_indirici.py
```

Temel kontrol:

```powershell
python video_indirici.py --self-test
```

## Paketleme

PyInstaller ile portable onedir build:

```powershell
python -m PyInstaller --noconfirm --clean --onedir --windowed --name "Video Indirici" video_indirici.py
```

Son kullanıcı paketi hazırlanırken `dist\Video Indirici` klasörüne `yt-dlp.exe`, `ffmpeg.exe`, `deno.exe`, `README.txt`, `DISCLAIMER.txt` ve `THIRD_PARTY_NOTICES.txt` eklenir.

## Sorumlu Kullanım

Bu araç yalnızca indirme hakkınız olan içerikler için kullanılmalıdır. Platform kuralları, telif hakları ve bulunduğunuz ülkenin yasaları kullanıcı sorumluluğundadır.
