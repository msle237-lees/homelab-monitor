# Machines Table (with TIMESTAMP)

| Column         | Type    | Notes                                         |
|----------------|---------|-----------------------------------------------|
| MACHINE_ID     | TEXT PK | Unique ID per machine (UUID/hostname)         |
| MACHINE_NAME   | TEXT    | Human-readable name                           |
| CPU_CORES      | INT     | Number of CPU cores                           |
| RAM_USED       | INT     | Bytes used                                    |
| RAM_TOTAL      | INT     | Bytes total                                   |
| STORAGE_USED   | INT     | Bytes used across primary storage             |
| STORAGE_TOTAL  | INT     | Bytes total across primary storage            |
| CPU_TEMPS      | REAL    | Average CPU temp in °C                        |
| NETWORK_USAGE  | INT     | Aggregate network bytes/sec                   |
| TIMESTAMP      | TEXT    | ISO8601 UTC, auto-set at insert/update        |

## Example row

```python
{
"MACHINE_ID": "host-001",
"MACHINE_NAME": "NAS-01",
"CPU_CORES": 16,
"RAM_USED": 8589934592,
"RAM_TOTAL": 34359738368,
"STORAGE_USED": 2147483648000,
"STORAGE_TOTAL": 8589934592000,
"CPU_TEMPS": 52.5,
"NETWORK_USAGE": 12500000,
"TIMESTAMP": "2025-09-25T22:30:12.123Z"
}
```
