import pandas as pd

logs = pd.read_json("logs/api.jsonl", lines=True)
requests = logs[logs["status"].notna()].copy()
requests["route"] = requests["path"].str.replace(r"/\d+", "/{id}", regex=True)

print("Lines by level:")
print(logs["level"].value_counts().to_string(), "\n")

print("Slowest routes, 95th percentile (ms):")
print(
    requests.groupby("route")["duration_ms"]
    .quantile(0.95)
    .round(1)
    .sort_values(ascending=False)
    .to_string(),
    "\n",
)

print("Errors:")
print(
    logs.loc[logs["level"] == "ERROR", ["time", "run_id", "message"]].to_string(
        index=False
    )
)
