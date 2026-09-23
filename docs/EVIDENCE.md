# Проверки Iteration 1

Среда: Python 3.9.6, зависимости из `requirements.txt`, установленые в новый
virtualenv. Команда: `python pipeline.py --data data --out out`.

Фактический stdout полного запуска:

```text
nodes=2248 edges=3119 transactions=4840 seeds=81
clusters=91 isolated=19 truncated=444 terminal_truncated=0
wrote: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv
elapsed_seconds=1.669
```

Внешний `/usr/bin/time -p` сообщил `real 2.06`, `user 2.90`, `sys 7.56`.
`python -m unittest discover -s tests` в том же окружении: `Ran 3 tests in 7.815s`, `OK`.
Проверены три роли по порогам, покрытие 2 248 `gid`, 19 изолятов, 444 обрыва,
сортировка топа и отказ на испорченном `n_tx` (`V-03`).

Три `gid`, выбранные `random.Random(42).sample(...)`, и их фактические объяснения:

```text
100000002454724100 terminal in=1 out=0 depth=2 seed=0 reach=7 cross=0 pass=0.00 cut=0
100000000850297100 transit in=1 out=1 depth=2 seed=0 reach=1 cross=0 pass=1.00 cut=0
100000004265639100 peripheral in=1 out=0 depth=4 seed=0 reach=7 cross=0 pass=0.00 cut=1
```

Первый удовлетворяет `depth < 4, in_deg > 0, out_deg = 0`; второй имеет
`pass_through = 1.00`; третий исключён из `terminal` из-за обрыва глубины 4.

Первые строки выходных файлов:

```csv
gid,role,role_score,cluster_id,priority_score,evidence,in_deg,out_deg,in_kzt,out_kzt,in_tx,out_tx,pagerank,pass_through,betweenness,n_reaching_seed,n_other_clusters,depth,is_seed,truncated_by_depth
100000000011452100,peripheral,0.2,0,0.3815496719626317,in=3 out=1 depth=1 seed=0 reach=7 cross=1 pass=0.15 cut=0,3,1,110000.0,16685.0,7,2,0.0004768640252326467,0.1516818181818182,4.832977967306326e-06,7,1,1,False,False
100000000018102100,peripheral,0.0,1,0.09558807159439647,in=1 out=0 depth=4 seed=0 reach=7 cross=0 pass=0.00 cut=1,1,0,7000.0,0.0,1,0,0.00032040294724489533,0.0,0.0,7,0,4,False,True
```

```csv
cluster_id,n_nodes,n_seed,sum_kzt_internal,top_gids,hypothesis
0,277,1,31856346.24,"100000002398779100,100000008477350100,100000006866783100,100000000437046100,100000004071080100","Гипотеза для проверки: преобладает роль peripheral; узлов 277, seed 1, внутренний оборот 31856346.24 KZT."
```

```csv
rank,gid,role,priority_score,why
1,100000003684369100,coordinator,0.7792797744338833,in_deg=24 in_kzt=3848436.00 betweenness=0.0033 reaching_seed=9 role=coordinator cut=0
2,100000008165763100,coordinator,0.762565101978809,in_deg=15 in_kzt=1165815.00 betweenness=0.0005 reaching_seed=9 role=coordinator cut=0
```

AC-05 пока закрыт только по CSV: интерфейс и поиск по `gid` запланированы в I2.

## T2.0

После редактуры текстов проверено: `same_gid_role_cluster True`,
`same_scores_after_rounding True`, `same_top_order True`,
`evidence_max_len 191`. Фактический пример обрыва:

> Получает от 1 плательщика (7,0 тыс. KZT), отправляет 0 получателям; достижим от 7 seed; связь с 0 кластерами. Без явной роли. 4-е колено, исходящие не наблюдаются — конечность не доказана.

## Iteration 2

Фактический stdout полного расчёта после добавления `graph.json`:

```text
nodes=2248 edges=3119 transactions=4840 seeds=81
clusters=91 isolated=19 truncated=444 terminal_truncated=0
wrote: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv, out/graph.json
elapsed_seconds=1.691
```

`/usr/bin/time -p`: `real 2.05`, `user 2.74`, `sys 8.24`.
Четыре unit-теста прошли; `graph.json` содержит 2 248 узлов и 3 119
направленных рёбер с существующими `source`/`target`.

В Chrome на `http://127.0.0.1:8000/viewer/` получен результат:

```text
default gid 100000003684369100 · 85 соседей
found 100000003684369100 Координатор gid 100000003684369100 · 85 соседей
found 100000000850297100 Транзит gid 100000000850297100 · 1 соседей
found 100000004265639100 Периферийный gid 100000004265639100 · 1 соседей
missing Узел 999999999999999999 не найден в предоставленной сети.
page_errors 0
```

Для транзитного узла Cytoscape.js сообщил `nodes: 2`, `edges: 2`,
`target-arrow-shape: triangle`; одно из рёбер направлено
`100000000850297100 → 100000006707582100`.

Скриншоты: [обзор координатора](screenshots/viewer.png),
[направление вокруг транзитного узла](screenshots/viewer-transit.png).

## Iteration 3 · T3.1

Временные признаки рассчитаны из `transactions.parquet`: 297 узлов с
исходящими через 1–2 дня после входа, 181 узел с синхронными входами,
258 узлов со всплесками по описанному в README порогу. Тест сверил для
`gid 100000000343175100` исходящий перевод 2026-07-02 после входа
2026-07-01, двух разных плательщиков на 20 000 KZT 2026-07-18 и
семь операций 2026-07-19. Для него рассчитаны 28 быстрых исходящих,
один день синхронных входов и три дня всплесков. Синтетический тест
проверил, что исходящий в тот же день не считается интервалом 1–2 дня.

Роли, кластеры, скоры и порядок топа после T3.1 совпали с I2; самое длинное
`evidence` содержит 200 символов. В Chrome карточка этого `gid` показала
все три сигнала; ошибок JavaScript не было.
[Скриншот карточки](screenshots/viewer-temporal.png).

## Iteration 3 · T3.2

Без `.env` команда завершилась успешно:

```text
nodes=2248 edges=3119 transactions=4840 seeds=81
clusters=91 isolated=19 truncated=444 terminal_truncated=0
wrote: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv, out/graph.json
LLM skipped: OPENAI_API_KEY absent in .env
elapsed_seconds=1.829
```

В `clusters.csv` все 91 строки имеют `hypothesis_source=deterministic`.
Mock-тест передал `OPENAI_MODEL` из временного `.env` в официальный SDK-вызов,
проверил `strict: true`, принятие валидных `gid`/метрик и отклонение
выдуманного `gid` и изменённого числа с возвратом к детерминированному тексту.
Живой OpenAI-вызов: **NOT_VERIFIED**, потому что ключ не предоставлен.

## Iteration 3 · T3.3

После добавления необязательных карточек полный запуск без `.env` вывел:

```text
nodes=2248 edges=3119 transactions=4840 seeds=81
clusters=91 isolated=19 truncated=444 terminal_truncated=0
wrote: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv, out/graph.json
LLM skipped: OPENAI_API_KEY absent in .env
Node cards LLM skipped: OPENAI_API_KEY absent in .env
elapsed_seconds=1.791
```

`/usr/bin/time -p`: `real 2.17`, `user 2.74`, `sys 8.21`.
14 локальных тестов прошли. Mock-тест подтвердил модель из `.env` и строгую
схему; другой тест отклонил чужой `gid` и изменённую входящую сумму.
В Chrome после изменений найдены три `gid`, отсутствующий `gid` показал
понятное сообщение; `page_errors 0`. Живой текст модели: **NOT_VERIFIED**.
