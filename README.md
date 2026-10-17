
## SearXNG

Price search needs a local SearXNG with JSON output turned on:

```powershell
Copy-Item searxng/settings.example.yml searxng/settings.yml   # then set a real secret_key
docker compose up -d search
```

`searxng/settings.yml` is gitignored because it holds the secret key.
