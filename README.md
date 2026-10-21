# MySQL Slow Query Reporter (lite)

English

A free subset of the slow-log tools: the parser and the local fingerprint. You can count statements in a log file. The bilingual ranked report, the field notes, and the default profile are in the full pack.

## Deliverables

- `deliverables/slowlog_parse.py` — parse a slow-query log file
- `deliverables/fingerprint.py` — local grouping key
- `examples/shop-slow.log` — the same fictional sample used by the full pack

## Quick start

From this directory:

```bash
python3 -c "import sys; sys.path.insert(0, 'deliverables'); from slowlog_parse import parse_path; from fingerprint import fingerprint; r = parse_path('examples/shop-slow.log'); print(len(r.entries)); print(fingerprint(r.entries[0].sql))"
```

Requirements: Python 3.11 or newer. No MySQL server and no network.

Full version: GUMROAD_URL

中文

这是慢查询工具的免费子集：解析器和本地指纹。可以统计日志里的语句条数。带排序的中英报告、字段说明和默认配置在完整包里。

## 文件

- `deliverables/slowlog_parse.py` — 解析慢查询日志
- `deliverables/fingerprint.py` — 本地分组键
- `examples/shop-slow.log` — 与完整包相同的虚构样例

在本目录执行上面的 Python 命令即可。需要 Python 3.11 或更新版本。不连接 MySQL，也不访问网络。

Full version: GUMROAD_URL
