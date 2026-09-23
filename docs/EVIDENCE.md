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

Чистый клон после финального коммита: новый Python 3.9 virtualenv установил
`requirements.txt`; `unittest discover` — **14 tests, OK**; полный расчёт —
`real 2.00`, `elapsed_seconds=1.660`. Проверка артефактов: 2 248 строк узлов,
91 кластер, 20 строк топа, 2 248 узлов и 3 119 рёбер в `graph.json`, максимум
`evidence` 200 символов. `.github/workflows/ci.yml` в клоне отсутствует.

## Iteration 4 · optional структурные проверки

Команда `.venv/bin/python pipeline.py --data data --out out --no-llm`
завершилась за `elapsed_seconds=1.872` и создала прежние три CSV,
`graph.json`, `out/robustness.csv` и `out/completeness.md`. Фактическая
таблица устойчивости из stdout (`share_all_seeds_lost_pct` — от 81 seed):

```text
top_removed components seeds_with_path_before seeds_with_path_after seeds_lost_path share_all_seeds_lost_pct
5           108        23                     21                    2               2.47
10          177        23                     20                    3               3.70
20          240        23                     11                    12              14.81
```

Для каждого удаления роли оставшихся узлов не пересчитывались. Путь направлен,
имеет длину минимум одно ребро; цикл, возвращающийся в исходный seed, тоже
считается. Удалённый seed, имевший путь до удаления, входит в потери.
Компоненты считаются слабо связными, включая изоляты.

В `nodes_roles.csv` флаг `cycle_count > 0` у 303 узлов, `repeat_chain_count > 0`
у 342, `split_tx_count > 0` у 2. Сумма счётчиков циклов по узлам — 7 996
участий; цепочек — 2 208 участий. В `evidence` фактически записано:

```text
gid 100000003016635100: Цикл≤6: 19; Цепь×2: 108; Дробление, tx: 4.
gid 100000008546855100: Цикл≤6: 2; Дробление, tx: 3.
```

Синтетические тесты проверили цикл, цепочку с двумя переводами на каждом ребре,
группу из трёх переводов одному получателю за день от разных отправителей и
отсутствие ложного сигнала при одном переводе на ребре. В выгрузке 417
отдельных переводов на 5 000–6 000 KZT; `out/completeness.md` фиксирует
444 обрыва четвёртого колена и запрос на пятое колено, входящие seed,
период за пределами июля и переводы ниже порога.

Регрессия: `unittest discover -s tests -v` — **17 tests, OK**. Полный запуск:
2 248 узлов, 3 119 рёбер, 4 840 переводов, 81 seed, 91 кластер,
19 изолятов, 444 обрыва, ни одного `terminal` среди обрывов; 20 строк топа,
максимальная длина `evidence` 200. Запуск предыдущего `pipeline.py` из HEAD
в отдельный каталог и сравнение по всем `gid` дали `True` для роли,
`role_score`, `priority_score`, `cluster_id`, а также для `rank/gid/role/score`
в топе. Гипотеза кластера 0 теперь начинается «Признаки группы для проверки:
узлов: 277, 1 seed…».

Для AC-05 локальный HTTP-сервер вернул `200` на `/viewer/` (13 806 байт) и
`/out/graph.json` (2 162 703 байта); тест сверил 2 248 узлов и 3 119
направленных рёбер и корректность ссылок. Интерактивная проверка в браузере
этой итерации **NOT_VERIFIED**: подключённый браузер недоступен; ранее она
прошла в Iteration 2 и 3, код viewer в Iteration 4 не менялся.

## Этап 5 · feature freeze

После явного разрешения пользователя выполнен live-запуск
`.venv/bin/python pipeline.py --data data --out out` с моделью `gpt-6-sol`.
Фактический stdout итогового запуска после исправления формулировок:

```text
nodes=2248 edges=3119 transactions=4840 seeds=81
clusters=91 isolated=19 truncated=444 terminal_truncated=0
wrote: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv, out/graph.json, out/robustness.csv, out/completeness.md
robustness: top_removed components seeds_with_path_before seeds_with_path_after seeds_lost_path share_all_seeds_lost_pct
robustness: 5 108 23 21 2 2.47
robustness: 10 177 23 20 3 3.70
robustness: 20 240 23 11 12 14.81
LLM hypotheses verified: 8/8 multi-seed clusters
Node cards LLM verified: 5/5 priority nodes
elapsed_seconds=20.090
```

В CSV действительно `hypothesis_source=llm_verified` у 8 кластеров из 91,
`node_summary_source=llm_verified` у 5 узлов из 2 248. Пример дословно
из `nodes_roles.csv` для `gid 100000003684369100`:

> Признаки возможного распределения потоков в наблюдаемой части графа.

Другие 83 гипотезы и 2 243 карточки остались детерминированными.
Секретный ключ в EVIDENCE, CSV и логи не копировался.

Исправление формулировок проверено сравнением прежнего результата и
нового по всем `gid`: `gid`, `role`, `role_score`, `cluster_id`,
`priority_score` совпали; `rank/gid/role/priority_score` всех 20 строк
топа тоже совпали. `evidence` не длиннее 200 символов. Дословные
объяснения, экспортированные в `graph.json` для карточек viewer:

```text
gid 100000003684369100 · coordinator · кластер 3 · приоритет 0.779
На координацию указывают 24 плательщика, 62 получателя и путь от 9 исходных клиентов. Связан с 9 другими кластерами. Вход неполон. Участвует в 1 возвратной цепочке и 63 повторяющихся маршрутах.

gid 100000000850297100 · transit · кластер 11 · приоритет 0.263
На транзит указывает передача 100% полученного. Вход — 17 520 KZT, выход — 17 520 KZT. Участвует в 1 возвратной цепочке.

gid 100000004265639100 · peripheral · кластер 1 · приоритет 0.1
Основные пороги ролей не достигнуты: 1 плательщик и 0 получателей. Наблюдаемый вход — 10 000 KZT, выход — 0 KZT. Конечность на четвёртом колене не доказана.
```

Viewer показывает поле `evidence` из этого JSON дословно
([viewer/index.html](../viewer/index.html)). После feature freeze
пользователь прислал четыре снимка открытого локального viewer: поиск
`100000003684369100` показывает координатора, кластер 3, приоритет
0,779 и 24 входящие/62 исходящие связи; `100000000850297100` показывает
транзит, кластер 11, приоритет 0,263 и обе направленные связи;
`100000004265639100` показывает периферию, кластер 1, приоритет 0,100,
одну входящую и отсутствие исходящей связи с оговоркой об обрыве.
Четвёртый снимок показывает сообщение «Узел 999 не найден в
предоставленной сети.» Снимки осмотрены в диалоге; их файлы пока
не помещены в `docs/screenshots/`.

Фактические ошибки на отдельных проверках (`--no-llm`):

```text
empty folder: exit=1
ERROR: V-01: missing /var/folders/ct/n_qzvymd3svdw94z04cc17rh0000gn/T/tmp7znpwfze/empty/nodes.parquet

broken edges.parquet: exit=1
ERROR: V-01: cannot read /var/folders/ct/n_qzvymd3svdw94z04cc17rh0000gn/T/tmp7znpwfze/broken/edges.parquet: Could not open Parquet input source '<Buffer>': Parquet magic bytes not found in footer. Either the file is corrupted or this is not a parquet file.
```

Несогласованный `n_tx` из `test_bad_aggregate_rejected_without_outputs`
вернул `V-03`; папка результата не появилась. Без ключа проверяется ниже
на чистом клоне. Неизвестный `gid` ранее дал в браузере дословно:
«Узел 999999999999999999 не найден в предоставленной сети.» (I2).
Для `gid 999` свежий снимок в диалоге подтвердил дословный ответ:
«Узел 999 не найден в предоставленной сети.»

### Чистый клон и повтор запуска

Клонирован текущий локальный коммит `58821f6` в новую папку
`/private/tmp/graph-money-clean-58821f6`. Источник клонирования был
локальным путём вместо GitHub URL из README; все последующие команды
раздела «Установка и запуск» выполнены буквально: `python3 -m venv .venv`,
`pip install -r requirements.txt`, `cp .env.example .env`, расчёт и
`python3 -m http.server 8000 --bind 127.0.0.1`. Зависимости установились
с кодом 0. Ключ в скопированном `.env` оставлен плейсхолдером. Фактический
stdout расчёта:

```text
nodes=2248 edges=3119 transactions=4840 seeds=81
clusters=91 isolated=19 truncated=444 terminal_truncated=0
wrote: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv, out/graph.json, out/robustness.csv, out/completeness.md
robustness: top_removed components seeds_with_path_before seeds_with_path_after seeds_lost_path share_all_seeds_lost_pct
robustness: 5 108 23 21 2 2.47
robustness: 10 177 23 20 3 3.70
robustness: 20 240 23 11 12 14.81
LLM skipped: OPENAI_API_KEY absent in .env
Node cards LLM skipped: OPENAI_API_KEY absent in .env
elapsed_seconds=5.438
```

`unittest discover -s tests -v` в том же клоне — **17 tests, OK**.
HTTP: `/viewer/` — `200`, 13 806 байт; `/out/graph.json` — `200`,
2 134 959 байт. JSON: 2 248 узлов, 3 119 рёбер. Для трёх `gid` выше
роли и кластеры совпали, число входящих/исходящих рёбер: `24/62`,
`1/1`, `1/0`. `gid 999` в JSON отсутствует. Браузерная проверка
выполнена пользователем на локальном viewer; браузер именно чистого
клона агенту недоступен. Код viewer и данные выходов совпадают.

### Приёмка AC-01–05 на текущем коммите

Проверка выгрузок чистого клона напечатала:

```text
AC-02 2248 2248 True True True 200
AC-03 100000003684369100 coordinator in 24 out 62 reach 9 depth 0 cut False pass 2.2317260830113845
AC-03 100000000850297100 transit in 1 out 1 reach 1 depth 2 cut False pass 1.0
AC-03 100000004265639100 peripheral in 1 out 0 reach 7 depth 4 cut True pass 0.0
AC-04 91 2248 81 91 True
AC-05-data 20 20 True 2248 3119
```

| Критерий | Статус | Основание |
|---|---|---|
| AC-01 | PASS | чистый клон, три CSV одной командой за 5,438 с |
| AC-02 | PASS | 2 248 уникальных `gid`, обязательные поля и диапазоны, максимум `evidence` 200 |
| AC-03 | PASS | три `gid` выше со структурными метриками, порогами и оговоркой об обрыве |
| AC-04 | PASS | 91 кластер покрывает 2 248 узлов и 81 seed, гипотезы заполнены |
| AC-05 | PASS | топ из 20 и направленный JSON проверены; четыре пользовательских скриншота локального viewer подтверждают три поиска и отказ для `999` |

Проверка репозитория: `git check-ignore .DS_Store .env` вывела оба имени;
`.env.example` содержит плейсхолдер `your_key_here`, не содержит строк
формата `sk-…` и не совпадает с live-ключом из локального `.env`.
