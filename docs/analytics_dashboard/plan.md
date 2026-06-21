# Analytics Dashboard Problem Tespitleri ve Duzeltme Plani

Bu plan, mevcut Analytics Dashboard hesaplamalarinda tespit edilen tutarsizliklari ve bunlari duzeltmek icin onerilen adimlari kapsar.

## Tespit Edilen Problemler

### 1. Trend pencereleri bugunun tarihine bagli

Period filtreleri ve Rising Topics hesaplamalari `datetime.utcnow()` uzerinden calisiyor. Veri seti guncel degilse, ornegin en yeni makale aylar once geldiyse, `12m` secenegi bile bos veya anlamsiz gorunebilir.

Etkisi:

- `No rising topics for selected filters.` gorunebilir.
- Son 7/30/90 gun metrikleri veri setinin gercek zaman araligini temsil etmeyebilir.
- Demo veya statik veri setlerinde dashboard oldugundan daha bos gorunur.

Duzeltme fikri:

- Analytics icin `reference_date` belirlenmeli.
- Varsayilan `reference_date`, filtrelenmis veri setindeki en buyuk `Article.publish_date` olabilir.
- Canli sistemde istenirse `now` kullanimi config ile korunabilir.

### 2. Filtreler tum metriklere tutarli uygulanmiyor

Bazi hesaplar secili `source`, `category`, `period` filtrelerini tam kullanmiyor.

Ornekler:

- `risingTopics` secili `period` degerini kullanmiyor; kendi 7/30/90 gun pencerelerini `period="all"` ile hesapliyor.
- `clusterQuality` icindeki `outlierCount`, `outlierRatio`, `clusteredPapers`, `totalPapersWithEmbedding` global veritabanindan geliyor.
- `categoryDistribution`, secili category filtresini bilerek kullanmiyor.
- `sourceDistribution`, source filtresini kullanmiyor.

Etkisi:

- Ekranda "selected filters" ifadesi gecse de bazi sayilar farkli evrenlerden gelebiliyor.
- Kullanici ayni filtreyi degistirdiginde bazi kartlar degisirken bazi kalite sinyalleri degismeyebilir.

Duzeltme fikri:

- Her payload alani icin "filtrelenmis metrik" mi "global metrik" mi oldugu netlestirilmeli.
- UI etiketleri buna gore ayrilmali: `Filtered Cluster Quality` veya `Global Cluster Quality`.
- Backend fonksiyon imzalari filtre tutarliligina gore yeniden duzenlenmeli.

### 3. Cluster siralamasi filtrelenmis sayiya gore yapilmiyor

`_clusters_from_counts()` mevcut cluster kaydi varsa `Cluster.article_count` degerini koruyor. Bu deger tum cluster'in global makale sayisi. Ancak dashboard'da `paper_count` filtrelenmis sayi.

Etkisi:

- `barData`, `pieData`, `clusterTrendData` ve dashboard'daki ilk cluster sirasi filtrelenmis sayiya gore olmayabilir.
- `Cluster Proportions` ilk 8 secimi filtrelenmis en buyuk 8 cluster'i temsil etmeyebilir.
- `All Clusters Overview` progress bar referansi `barData[0]` oldugu icin bazi bar genislikleri teorik olarak %100'u asabilir.

Duzeltme fikri:

- Analytics icinde siralama icin her zaman filtrelenmis `cluster_counts[cluster_id]` kullanilmali.
- Global `Cluster.article_count` sadece metadata veya global kalite metriklerinde kullanilmali.

### 4. Monthly ve cluster trend grafiklerinde eksik aylar sifirlanmiyor

`monthlyData` ve `clusterTrendSeries` yalnizca verisi olan ay satirlarini donuyor.

Etkisi:

- Zaman serisi grafigi eksik aylar yokmus gibi davranabilir.
- 12 aylik period secilse bile 12 ayin tamamini gormek garanti degil.
- Cluster trend cizgilerinde cluster'in veri olmayan aylari sifir olarak degil, eksik nokta olarak kalir.

Duzeltme fikri:

- Period'a gore ay bucket listesi uretilmeli.
- Eksik aylar `0` count ile doldurulmali.
- `all` icin ya tum aylar ya da son N ay gibi acik bir UI davranisi belirlenmeli.

### 5. `all` ve finite period arasinda `publish_date` null davranisi farkli

Finite period secimlerinde `Article.publish_date >= ...` kosulu null tarihli makaleleri dislar. `all` seciminde tarih filtresi olmadigi icin null tarihli makaleler dahil olabilir.

Etkisi:

- `All` secilince toplam makale sayisi sadece tarih araligi genisledigi icin degil, tarihi bos kayitlar dahil oldugu icin de artabilir.
- Publication trend gibi tarih gerektiren grafikler bu makaleleri gostermezken Total Papers gosterir.

Duzeltme fikri:

- Analytics icin tarihli ve tarihsiz makale davranisi netlestirilmeli.
- `totalPapers` icinde tarihsizler dahil olacaksa ayrica `undatedPapers` metriği donmeli.
- Alternatif olarak tum period modlarinda `publish_date IS NOT NULL` sarti standart hale getirilmeli.

### 6. Category eslesmesi metinsel `ILIKE` ile yapiliyor

Kategori filtresi ve kategori dagilimi `Article.categories ILIKE "%<category>%"` kullaniyor.

Etkisi:

- Kategori metni normalize degilse yanlis eslesmeler olabilir.
- Bir makale birden fazla kategoride sayilabilir.
- CategoryDistribution toplam sayilari `totalPapers` ile bire bir toplanabilir bir dagilim olmayabilir.

Duzeltme fikri:

- `categories` alani JSON/array olarak normalize edilmeli veya sorguda delimiter-aware eslesme kullanilmali.
- UI'da bu dagilimin "multi-label category count" oldugu belirtilmeli.

### 7. Representation quality etiketi fazla iddiali

Scatter grafikteki `representation_score`, tum cluster kalitesinin direkt olcumu degil. Metadata'daki temsilci makale skorlarinin ortalamasi.

Etkisi:

- Kullanici bunu cluster'in genel embedding kalitesi gibi yorumlayabilir.
- Secili period veya category filtresine gore yeniden hesaplanmaz.

Duzeltme fikri:

- UI etiketi `Representative Score` gibi daha net hale getirilmeli.
- Alternatif olarak filtrelenmis makaleler uzerinden centroid similarity yeniden hesaplanmali.

### 8. Cache staleness riski var

Analytics snapshot filtre anahtarina gore cache'leniyor. Yeni makale ingest edildiginde veya clustering guncellendiginde ilgili snapshot temizlenmezse eski payload doner.

Etkisi:

- Dashboard yeni veriyi gostermeyebilir.
- Filtre bazli snapshot'lar default refresh disinda stale kalabilir.

Duzeltme fikri:

- Snapshot metadata'sina veri versiyonu veya son makale/clustering timestamp'i eklenmeli.
- Ingestion ve clustering sonrasi ilgili analytics snapshot'lari invalidate edilmeli.
- Kisa TTL veya manuel `force_refresh` UI kontrolu eklenebilir.

### 9. Backend payload'da kullanilmayan alanlar var

Kullanilmayan veya bos alanlar:

- `sourceDistribution`
- `clusterTrendData`
- `papers`
- `pdfAvailable`

Etkisi:

- API contract gereksiz buyuyor.
- Frontend/backend beklentileri belirsizlesiyor.
- Testler kullanilmayan alanlari da contract gibi koruyor.

Duzeltme fikri:

- Kullanilacak alanlar UI'a eklenmeli veya payload'dan kaldirilmali.
- Contract testi alanlari "kullanilan" ve "legacy" olarak ayirmali.

### 10. Zaman ve timezone kullanimi karisik

Kodda `datetime.utcnow()` ve `datetime.now(UTC).replace(tzinfo=None)` beraber kullaniliyor.

Etkisi:

- Naive/aware datetime karisimi ileride DB veya timezone degisikliklerinde hata uretebilir.
- Gun sinirlari kullanici lokasyonuna gore degil UTC'ye gore yorumlanir.

Duzeltme fikri:

- Analytics icin tek bir `utc_now_naive()` veya timezone-aware yardimci fonksiyon secilmeli.
- DB datetime standardi dokumante edilmeli.

## Duzeltme Plani

### Faz 1: Davranis kararlarini netlestir

1. Dashboard'daki her alan icin kapsam belirle:
   - filtrelenmis metrik
   - global kalite sinyali
   - dropdown secenek kaynagi
2. `All` seceneginin zaman serilerinde ne gosterecegine karar ver:
   - tum aylar
   - son 12 ay
   - veri setindeki tum aralik ama bucket limitli
3. Tarihsiz makalelerin analytics'e dahil edilip edilmeyecegini belirle.

Kabul kriteri:

- Her payload alani icin beklenen filtre kapsami yazili hale gelir.
- UI label'lari bu kapsama gore guncellenmeye hazir olur.

### Faz 2: Ortak analytics context olustur

Backend'de tek bir context nesnesi uret:

```text
AnalyticsContext
- source
- category
- period
- reference_date
- period_start
- period_end
- filtered_article_query
```

Yapilacaklar:

1. `reference_date` icin filtrelenmis veri setindeki en buyuk `publish_date` kullan.
2. Period filtrelerini `period_start <= publish_date <= reference_date` olarak uygula.
3. Tum hesap fonksiyonlarina ayni context'i gec.

Kabul kriteri:

- `12m`, `6m`, `3m`, `1m` pencereleri veri seti referans tarihine gore tutarli calisir.
- Future-dated kayitlar istemeden period'a dahil olmaz.

### Faz 3: Filtre tutarliligini duzelt

Yapilacaklar:

1. `risingTopics` icin context `reference_date` kullan.
2. `risingTopics` icinde source/category filtresini koru; period kullanimi icin urun karari uygula.
3. `clusterQuality` icin iki ayri payload uret:
   - `filteredClusterQuality`
   - `globalClusterQuality`
4. UI'da hangi kalite metriğinin global oldugunu acik isimle goster.

Kabul kriteri:

- Category veya period degisince filtrelenmis kalite metrikleri de beklenen sekilde degisir.
- Global metrikler UI'da global olarak etiketlenir.

### Faz 4: Cluster siralamasini filtrelenmis sayiya bagla

Yapilacaklar:

1. `_clusters_from_counts()` siralamasi icin `cluster_counts` degerlerini kullan.
2. `barData`, `pieData`, `clusterTrendData` ve `clusters` ayni filtrelenmis sirayi kullansin.
3. Frontend progress bar referansi `Math.max(...filteredClusters.map(c => c.paper_count))` olsun.

Kabul kriteri:

- Pie chart secili filtrelerde en buyuk 8 cluster'i gosterir.
- Distribution progress bar genisligi %100'u asmaz.

### Faz 5: Zaman serilerini tam bucket'larla uret

Yapilacaklar:

1. Period'a gore ay listesi uret.
2. `monthlyData` icin eksik aylari `0` ile doldur.
3. `clusterTrendSeries` veya frontend chart row'lari icin eksik cluster-ay kombinasyonlarini `0` ile doldur.
4. `all` icin bucket limiti ve label davranisini net uygula.

Kabul kriteri:

- 12 months seciminde 12 ay etiketi gorulur.
- Veri olmayan aylar grafikte sifir olarak gorunur.

### Faz 6: Category/source dagilimlarini temizle

Yapilacaklar:

1. `categoryDistribution` icin isimlendirme karari ver:
   - dropdown options ise `categoryOptions`
   - grafik verisi ise selected filters'a uygun dagilim
2. `sourceDistribution` UI'da gosterilecekse source filtresi davranisi netlestir.
3. Kategori eslesmesini normalize et:
   - mumkunse `metadata_json["categories_list"]` veya normalize tablo kullan
   - degilse delimiter-aware SQL kosulu kullan

Kabul kriteri:

- Category count yorumlanabilir hale gelir.
- SourceDistribution ya UI'da kullanilir ya da contract'tan cikarilir.

### Faz 7: API contract ve testleri guncelle

Eklenmesi gereken testler:

1. `12m` period eski snapshot'a dusmez.
2. Period penceresi `reference_date` ile hesaplanir.
3. Cluster siralamasi filtrelenmis count'a gore yapilir.
4. Monthly data eksik aylari `0` ile doldurur.
5. Filtered ve global cluster quality ayrilir.
6. `all` seciminde tarihsiz makale davranisi beklenen sekildedir.

Kabul kriteri:

- Analytics contract testi sadece gercekten desteklenen alanlari korur.
- Hesaplama testleri fake query yerine mumkunse minimal SQLite/PostgreSQL uyumlu fixture veya servis seviyesi saf fonksiyonlarla yapilir.

### Faz 8: UI metinlerini ve bos durumlari netlestir

Yapilacaklar:

1. `No rising topics for selected filters.` mesaji, veri seti referans tarihine gore anlamli hale getirilmeli.
2. Global metrikler icin `Global` etiketi eklenmeli.
3. `Representative Score` gibi daha kesin chart isimleri kullanilmali.
4. `PDF Available` ve `sourceDistribution` kullanilacaksa yeni kart/grafik eklenmeli.

Kabul kriteri:

- Kullanici hangi metrigin hangi filtre kapsaminda oldugunu ekrana bakarak anlayabilir.
- Bos durumlar veri yoklugu ile hesaplama kapsami farkini ayirir.

## Onerilen Uygulama Sirasi

1. Analytics context ve `reference_date` altyapisini ekle.
2. Cluster siralamasini filtrelenmis count'a gore duzelt.
3. Time series bucket doldurma mantigini ekle.
4. Filtered/global cluster quality ayrimini yap.
5. Category/source dagilim sozlesmesini sadelestir.
6. UI label ve bos durum metinlerini guncelle.
7. Contract ve regresyon testlerini genislet.
