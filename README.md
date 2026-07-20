*This README is auto-generated. Do not edit manually — changes will be overwritten.*

# Platform Share on USA.gov

Monthly desktop and mobile platform usage based on [DAP (Digital Analytics Program)](https://digital.gov/guides/dap/) OS visit data.

See [`analysis/os_filter.json`](analysis/os_filter.json) for which desktop platforms are included and excluded.

**Data range:** 2018-01 to 2026-06

## Desktop platforms

![Desktop platform share over time](assets/desktop-platforms.png)

### Latest month (2026-06)

| Platform | Share |
| --- | ---: |
| WINDOWS | 71.4% |
| MAC | 21.6% |
| LINUX | 5.7% |
| CHROME OS | 1.3% |
| BSD | 0.0% |

## Mobile platforms

![Mobile platform share over time](assets/mobile-platforms.png)

### Latest month (2026-06)

| Platform | Share |
| --- | ---: |
| IOS | 67.9% |
| ANDROID | 32.1% |

## Regenerate locally

```bash
pip install -r requirements.txt
python analysis/generate_readme.py
```
