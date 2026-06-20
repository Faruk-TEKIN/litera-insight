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
3. Cache'te `report_snapshots` kaydi varsa onu doner.
4. Cache yoksa `build_analytics_payload()` ile payload hesaplanir ve `report_snapshots` tablosuna yazilir.

Snapshot anahtari su alanlarin hash'inden olusur:

- `source`
- `category`
- `period`

Analytics schema version mevcut kodda `analytics:v5`.

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
Article.categories ILIKE "%<category>%"
```

Bu nedenle kategori filtresi hem birincil kategori alanina hem de metinsel kategori listesine bakar.

### Period filtresi

Gecerli period degerleri:

| UI etiketi | Backend degeri | Hesaplama |
|---|---:|---|
| 1 month | `1m` | son 30 gun |
| 3 months | `3m` | son 90 gun |
| 6 months | `6m` | son 180 gun |
| 12 months | `12m` | son 365 gun |
| All | `all` | tarih filtresi yok |

Period `all` degilse sorguya su kosul eklenir:

```text
Article.publish_date >= datetime.utcnow() - timedelta(days=<period_days>)
```

Onemli davranis: Bu filtre bugunun tarihine gore calisir; veri setindeki en yeni yayin tarihine gore calismaz. `publish_date` bos olan makaleler finite period secimlerinde SQL karsilastirmasina takildigi icin disarida kalir, `all` seciminde ise dahil olabilir.

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
article_query.filter(Article.publish_date >= datetime.utcnow() - timedelta(days=7)).count()
```

Secili `source`, `category` ve `period` filtresine ek olarak son 7 gunde yayinlanmis makale sayisidir. Period `all` olsa bile son 7 gun kosulu ayrica uygulanir.

### PDF Available

Payload'da var, mevcut dashboard ekraninda dogrudan gosterilmiyor.

Backend:

```text
Article.pdf_url IS NOT NULL
veya
Article.metadata_json["has_pdf"] == true
```

Secili filtrelerden gecen makaleler icinde PDF linki veya metadata PDF isareti bulunan makale sayisidir.

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

Onemli davranis: Rising Topics hesaplamasi secili `period` filtresini kullanmaz; kendi 7/30/90 gun pencerelerini `period="all"` baz sorgusu uzerinden hesaplar. `source` ve `category` filtrelerini ise kullanir.

## Cluster Quality

Frontend bolumu: `Cluster Quality`

Backend fonksiyonu: `_cluster_quality()`

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
largestCluster = verilen clusters listesinde article_count degeri en buyuk cluster
clusteredPapers = tum veritabaninda cluster_id IS NOT NULL olan makale sayisi
largestClusterRatio = largestCluster.article_count / clusteredPapers
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
embedding IS NOT NULL olan tum makale sayisi
```

Onemli davranis: Cluster Quality icindeki outlier, embedded ve clustered sayilari `source`, `category` ve `period` filtrelerinden bagimsiz olarak global veritabanindan hesaplanir. Sadece `largestCluster` ve `avgRepresentationScore` icin fonksiyona verilen cluster listesi etkili olur.

## Cluster Trend

Frontend bolumu: `Cluster Trend`

Backend fonksiyonu: `_cluster_trend_data()`

Backend once en buyuk 8 cluster'i secer:

```text
sorted(clusters, key=cluster.article_count, reverse=True)[:8]
```

Sonra secili filtrelerle makaleleri ay bazinda gruplar:

```text
GROUP BY Article.cluster_id, date_trunc("month", Article.publish_date)
COUNT(Article.id)
```

Payload iki formatta doner:

- `clusterTrendData`: Ay bazli genis format; mevcut frontend bunu kullanmiyor.
- `clusterTrendSeries`: Her satir bir `cluster_id + month` kombinasyonu; frontend bunu cizgi grafigine ceviriyor.

Frontend `clusterTrendSeries` listesini `buildTrendChartRows()` ile su formata donusturur:

```text
{
  month: "Jun 26",
  monthKey: "2026-06",
  cluster_<id>: count
}
```

Eksik aylar veya bir cluster'in sayisi olmayan aylar sifirla doldurulmaz.

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

Frontend category dropdown secenekleri `categoryDistribution` payload'indan gelir.

Backend fonksiyonu: `_category_distribution()`

Hesaplama iki asamalidir:

1. Secili `source` ve `period` filtreleriyle en cok gorulen ilk 20 `primary_category` bulunur. Bos/null kategoriler dislanir.
2. Bu 20 kategori icin tekrar sayim yapilir:

```text
Article.primary_category == category
veya
Article.categories ILIKE "%<category>%"
```

Frontend label icin `categoryLabel()` kullanir. Bilinen arXiv kategorileri okunabilir ada cevrilir; bilinmeyenler humanize edilir.

Onemli davranis: `categoryDistribution`, secili category filtresini kullanmaz. Bu, dropdown'in tum kategori seceneklerini gostermesi icin faydali olabilir.

## Source Distribution

Payload'da var, mevcut dashboard ekraninda gosterilmiyor.

Backend:

```text
GROUP BY Article.source
COUNT(Article.id)
```

Bu hesaplama `category` ve `period` filtrelerini kullanir. `source` parametresi hesaba katilmaz; boylece kaynaklar arasi dagilim gorulebilir. Ancak frontend su an source filtresi de source dagilim grafigi de sunmuyor.

## Kullanilmayan veya Bos Payload Alanlari

Mevcut dashboard icin dikkat ceken alanlar:

- `sourceDistribution`: Backend donuyor, frontend gorsellestirmiyor.
- `clusterTrendData`: Backend donuyor, frontend `clusterTrendSeries` kullaniyor.
- `papers`: Analytics payload'inda her zaman bos liste olarak donuyor.
- `pdfAvailable`: Metrics icinde var, frontend kart veya tablo olarak gostermiyor.

