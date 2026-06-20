# Analytics Dashboard Metrik ve Tablo Hesaplama Dokumani

Bu dokuman, mevcut kod tabaninda Analytics Dashboard ekranindaki metriklerin, grafiklerin ve tablolarin nasil uretildigini aciklar.

Ana dosyalar:

- Backend endpoint: `backend/app/api/routes/analytics.py`
- Backend hesaplama ve cache: `backend/app/services/report_snapshot_service.py`
- Frontend ekran: `frontend/src/pages/DashboardPage.tsx`
- Veri modelleri: `database/models/ArticleData.py`, `database/models/ClusterData.py`, `database/models/ReportSnapshot.py`

## Genel Akis

Dashboard acilinca frontend su endpoint'i cagirir:

```text
GET /analytics?period=<period>&category=<category>
```

Frontend su an yalnizca `period` ve `category` gonderir. Backend endpoint'i ayrica `source` ve `force_refresh` parametrelerini de destekler.

Backend akisi:

1. `ReportSnapshotService.get_analytics()` period degerini normalize eder.
2. `analytics_snapshot_key(source, category, period)` ile filtrelere ozel cache anahtari uretir.
3. Cache'te `report_snapshots` kaydi varsa snapshot metadata'sindaki `dataFingerprint` mevcut veri fingerprint'i ile karsilastirilir.
4. Fingerprint eslesirse snapshot doner; eslesmezse veya cache yoksa `build_analytics_payload()` ile payload hesaplanir ve `report_snapshots` tablosuna yazilir.

Snapshot anahtari su alanlarin hash'inden olusur:

- `source`
- `category`
- `period`

Analytics schema version mevcut kodda `analytics:v6`.

## Filtreleme Kurallari

Tum ana makale bazli metrikler `_filtered_articles_query()` uzerinden baslar.

### Source filtresi

`source` doluysa:

```text
Article.source == source
```

Frontend su an source filtresi gondermiyor.

### Category filtresi

`category` doluysa makale su kosullardan biriyle eslesir:

```text
Article.primary_category == category
veya
Article.categories delimiter-aware token eslesmesi
```

Bu nedenle kategori filtresi hem birincil kategori alanina hem de metinsel kategori listesine bakar; metinsel liste eslesmesi substring yerine bosluk, virgul, noktalı virgul, pipe ve newline ayraclarini dikkate alir.

### Period filtresi

Gecerli period degerleri:

| UI etiketi | Backend degeri | Hesaplama |
|---|---:|---|
| 1 month | `1m` | reference ayı |
| 3 months | `3m` | reference ayı dahil 3 calendar month |
| 6 months | `6m` | reference ayı dahil 6 calendar month |
| 12 months | `12m` | reference ayı dahil 12 calendar month |
| All | `all` | tarihli veri setindeki min-max ay araligi |

Analytics kapsaminda `publish_date IS NOT NULL` sarti her zaman uygulanir. `reference_date`, secili `source/category` filtresindeki en buyuk `Article.publish_date` degeridir. Period filtresi su sekilde uygulanir:

```text
period_start <= Article.publish_date <= reference_date
```

`period=all` secilirse `period_start`, filtreli tarihli veri setindeki en eski yayin ayinin baslangicidir.

## Ust Metrik Kartlari

### Total Papers

Frontend:

```text
metrics.totalPapers
```

Backend:

```text
article_query.count()
```

Secili `source`, `category` ve `period` filtrelerinden gecen toplam makale sayisidir.

### Active Clusters

Frontend:

```text
metrics.activeClusters
```

Backend:

```text
distinct Article.cluster_id count, cluster_id IS NOT NULL
```

Secili filtrelerden gecen makaleler icinde en az bir makalesi bulunan farkli cluster sayisidir.

### Active Clusters Alt Etiketi: Clustered

Frontend kart alt etiketi:

```text
metrics.clusteredPapers + " clustered"
```

Backend:

```text
article_query.filter(Article.cluster_id.isnot(None)).count()
```

Secili filtrelerden gecen ve bir cluster'a atanmis makale sayisidir.

### Avg Papers/Cluster

Frontend:

```text
Math.round(metrics.avgPapersPerCluster)
```

Backend:

```text
clustered_papers / active_clusters
```

Cluster'a atanmis makalelerin aktif cluster sayisina bolunmus ortalamasidir. Backend kesirli deger uretir, frontend yuvarlayarak gosterir.

### Weekly Picks

Frontend:

```text
metrics.weeklyPicks
```

Backend:

```text
article_query.filter(Article.publish_date >= reference_date - timedelta(days=7)).count()
```

Secili `source`, `category` ve `period` filtresine ek olarak reference date'e gore son 7 gunde yayinlanmis makale sayisidir. `pdfAvailable` artik analytics payload'inda donmez.

## Cluster Verisinin Hazirlanmasi

Backend once filtrelenmis makalelerden cluster bazli sayim yapar:

```text
GROUP BY Article.cluster_id
COUNT(Article.id)
```

Sonra `clusters` tablosundan bu cluster id'lerine ait metadata kayitlarini alir. Eger makalede `cluster_id` var ama `clusters` tablosunda karsilik gelen kayit yoksa `_clusters_from_counts()` gecici bir cluster nesnesi olusturur:

```text
cluster_description = "Cluster <id>"
article_count = filtrelenmis makale sayisi
metadata_json = {}
```

Cluster payload alanlari:

| Alan | Kaynak |
|---|---|
| `id` | `Cluster.cluster_id` |
| `name` | `Cluster.cluster_description`, yoksa `Cluster <id>` |
| `keyword` | Cluster aciklamasinin ilk virgullu parcasi, virgül yoksa ilk kelime |
| `description` | `Cluster.cluster_description` |
| `color` | `COLORS[abs(cluster_id) % len(COLORS)]` |
| `paper_count` | Secili filtrelerdeki cluster makale sayisi |
| `created_at` | `Cluster.created_at`, yoksa hesaplama anindaki zaman |
| `metadata` | `Cluster.metadata_json` |
| `representation_score` | Temsilci makale skorlarinin ortalamasi |

### Representation Score

`representation_score`, cluster metadata'sindaki `representative_article_scores` degerlerinden hesaplanir:

```text
sum(scores) / len(scores)
```

Bu skorlar clustering sirasinda uretilir. Clustering kodunda her makalenin embedding'i cluster centroid'ine cosine similarity ile skorlanir ve temsilci makale skorlarina yazilir. Dashboard'daki skor tum cluster makalelerinin ortalamasi degil, metadata'da tutulan temsilci skorlarinin ortalamasidir.

## Rising Topics

Frontend bolumu: `Rising Topics`

Backend fonksiyonu: `_rising_topics()`

Her cluster icin uc pencere hesaplanir:

- 7 gun
- 30 gun
- 90 gun

Her pencere icin iki sayim yapilir:

```text
last_Nd = now - N gun ile now arasi makale sayisi
prev_Nd = now - 2N gun ile now - N gun arasi makale sayisi
```

Acceleration formulu:

```text
(current - previous) / max(previous, 1)
```

Score formulu:

```text
score = 0.5 * acceleration_30d
      + 0.3 * acceleration_90d
      + 0.2 * acceleration_7d
```

Siralamada kullanilan tuple:

```text
(last_30d > 0, score, last_30d, paper_count)
```

Backend ilk 8 konuyu dondurur. Frontend yalnizca ilk 6 konuyu gosterir.

Gosterilen alanlar:

| UI alani | Payload alani |
|---|---|
| konu adi | `name` |
| son 30 gun makale sayisi | `last_30d` |
| Accel 30d | `acceleration_30d` |
| Score | `score` |
| Total | `paper_count` |

Onemli davranis: Rising Topics hesaplamasi secili `period` filtresini kullanmaz; kendi 7/30/90 gun pencerelerini filtreli veri setinin `reference_date` degerine gore hesaplar. `source` ve `category` filtrelerini kullanir.

## Cluster Quality

Frontend bolumu: `Cluster Quality`

Backend fonksiyonu: `_cluster_quality()`

Payload iki ayri kalite alani doner:

- `filteredClusterQuality`: secili `source/category/period` kapsamindaki tarihli makaleler.
- `globalClusterQuality`: tum tarihli makaleler.

### Outlier Ratio

Backend:

```text
outlierCount = embedding IS NOT NULL ve cluster_id IS NULL olan makale sayisi
totalPapersWithEmbedding = embedding IS NOT NULL olan makale sayisi
outlierRatio = outlierCount / totalPapersWithEmbedding
```

Frontend bunu yuzde olarak gosterir. Deger `0.35` ustundeyse uyarili stil kullanir.

### Largest Ratio

Backend:

```text
largestCluster = filtrelenmis cluster count degeri en buyuk cluster
clusteredPapers = ilgili kalite kapsaminda cluster_id IS NOT NULL olan makale sayisi
largestClusterRatio = largestClusterFilteredCount / clusteredPapers
```

Frontend yuzde olarak gosterir. Deger `0.45` ustundeyse uyarili stil kullanir.

### Avg Rep Score

Backend:

```text
secili clusters listesinde representation_score > 0 olan skorlarin ortalamasi
```

Frontend yuzde olarak gosterir. Deger `0.4` altindaysa uyarili stil kullanir.

### Embedded Papers

Backend:

```text
ilgili kalite kapsaminda embedding IS NOT NULL olan makale sayisi
```

Frontend filtered ve global kalite degerlerini ayri bolumlerde gosterir.

## Cluster Trend

Frontend bolumu: `Cluster Trend`

Backend fonksiyonu: `_cluster_trend_series()`

Backend once en buyuk 8 cluster'i secer:

```text
sorted(clusters, key=filtered_cluster_count, reverse=True)[:8]
```

Sonra secili filtrelerle makaleleri ay bazinda gruplar:

```text
GROUP BY Article.cluster_id, date_trunc("month", Article.publish_date)
COUNT(Article.id)
```

Payload `clusterTrendSeries` formatinda doner. Her satir bir `cluster_id + month` kombinasyonudur; frontend bunu cizgi grafigine cevirir.

Frontend `clusterTrendSeries` listesini `buildTrendChartRows()` ile su formata donusturur:

```text
{
  month: "Jun 26",
  monthKey: "2026-06",
  cluster_<id>: count
}
```

Eksik aylar ve bir cluster'in sayisi olmayan aylar `0` ile doldurulur.

## Cluster Proportions

Frontend bolumu: `Cluster Proportions`

Backend payload'i: `pieData`

Backend:

```text
pieData = barData[:8]
```

Her dilim:

| Alan | Anlam |
|---|---|
| `name` | Cluster adi |
| `value` | Secili filtrelerdeki makale sayisi |
| `color` | Cluster rengi |

Pie chart, secili filtrelerdeki ilk 8 cluster'in goreli buyuklugunu gosterir.

## Cluster Size vs. Representation Quality

Frontend bolumu: `Cluster Size vs. Representation Quality`

Backend payload'i: `scatterData`

Her cluster icin:

| Grafik ekseni | Payload | Hesaplama |
|---|---|---|
| X | `x` | Secili filtrelerdeki cluster makale sayisi |
| Y | `y` | `representation_score * 100` |
| Z | `z` | Bubble buyuklugu icin makale sayisi |
| Renk | `color` | Cluster rengi |

Bu grafik cluster buyuklugu ile temsilci skorunun birlikte okunmasi icin uretilir.

## Publication Trend

Frontend bolumu: `Publication Trend`

Backend fonksiyonu: `_monthly_data()`

Backend secili filtrelerden gecen makaleleri yayin ayina gore gruplar:

```text
GROUP BY date_trunc("month", Article.publish_date)
COUNT(Article.id)
```

Sonra sirali aylardan son 12 satiri doner:

```text
monthly_rows[-12:]
```

Payload satiri:

```text
{
  month: "Jun 26",
  count: 123,
  publications: 123
}
```

Frontend `publications` alanini area chart olarak gosterir. Eksik aylar sifirla doldurulmaz.

## All Clusters Overview

Frontend bolumu: `All Clusters Overview`

Kaynak payload:

1. `data.clusters` varsa onu kullanir.
2. `data.clusters` bos ise `barData` uzerinden fallback cluster listesi olusturur.

Tablo kolonlari:

| Kolon | Hesaplama |
|---|---|
| Cluster | `cluster.name` ve renk noktasi |
| Keyword | `cluster.keyword` |
| Papers | `cluster.paper_count` |
| Share | `cluster.paper_count / totalPapers * 100` |
| Distribution | `cluster.paper_count / topClusterPaperCount * 100` genisliginde progress bar |
| Action | Chat ekranina cluster analizi prompt'u ile gider |

Arama:

```text
cluster.name + cluster.keyword icinde metin arar
```

Siralama:

- `papers`: `paper_count` azalan
- `name`: cluster adi alfabetik

Action butonu chat state'ine su prompt'u yollar:

```text
Analyze the "<cluster name>" research cluster and suggest representative papers, methods, and open questions.
```

## Category Filter Secenekleri

Frontend category dropdown secenekleri `categoryOptions` payload'indan gelir.

Backend fonksiyonu: `_category_options()`

Hesaplama iki asamalidir:

1. Secili `source` ve `period` filtreleriyle en cok gorulen ilk 20 `primary_category` bulunur. Bos/null kategoriler dislanir.
2. Bu 20 kategori icin tekrar sayim yapilir:

```text
Article.primary_category == category
veya
Article.categories delimiter-aware token eslesmesi
```

Frontend label icin `categoryLabel()` kullanir. Bilinen arXiv kategorileri okunabilir ada cevrilir; bilinmeyenler humanize edilir.

Onemli davranis: `categoryOptions`, secili category filtresini kullanmaz. Bu, dropdown'in tum kategori seceneklerini gostermesi icin faydalidir.

## Kaldirilan Legacy Payload Alanlari

`analytics:v6` payload'inda su eski alanlar artik donmez:

- `sourceDistribution`
- `categoryDistribution`
- `clusterTrendData`
- `papers`
- `clusterQuality`
- `metrics.pdfAvailable`
