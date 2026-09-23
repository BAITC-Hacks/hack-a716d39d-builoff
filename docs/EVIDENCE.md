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
