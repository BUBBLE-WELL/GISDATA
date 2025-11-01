# Real-Time Dengue Map

This workspace hosts a streaming dengue risk dashboard for GE5219.

## Getting started
1.** just run **  ```docs/A_Real_Time_Dengue_Map.ipynb```

> or

1. Populate `config/api_config.json` with real credentials.
2. Install dependencies via `pip install -r dependencies.txt`.
3. Run `python main.py` to start the development server.
4. Point a browser at `http://localhost:8000` to view the dashboard.


## Key folders
- `data/` — data lake for raw, processed, and aggregated assets
- `scripts/` — ingestion, processing, and analysis pipelines
- `visualization/` — H5 front-end assets for the live map
- `config/` — API keys, app tuning, and connection metadata
- `models/` — analytic weights and saved model artefacts

## References


1. National Environment Agency. (2020). Dengue Clusters (GEOJSON) (2025) [Dataset]. data.gov.sg. Retrieved October 8, 2025 from https://data.gov.sg/datasets/d_dbfabf16158d1b0e1c420627c0819168/view
2. National Environment Agency. (2024). Rainfall across Singapore (2025) [Dataset]. data.gov.sg. Retrieved October 8, 2025 from https://data.gov.sg/datasets/d_6580738cdd7db79374ed3152159fbd69/view
3. National Environment Agency. (2024). Air Temperature across Singapore (2025) [Dataset]. data.gov.sg. Retrieved October 8, 2025 from https://data.gov.sg/datasets/d_66b77726bbae1b33f218db60ff5861f0/view
4. Singapore Department of Statistics. (2024). Resident Population by Planning Area/Subzone of Residence, Ethnic Group and Sex (Census of Population 2020) (2025) [Dataset]. data.gov.sg. Retrieved October 8, 2025 from https://data.gov.sg/datasets/d_e7ae90176a68945837ad67892b898466/view
5. Urban Redevelopment Authority. (2019). Master Plan 2019 Subzone Boundary (No Sea) (GEOJSON) (2024) [Dataset]. data.gov.sg. Retrieved October 9, 2025 from https://data.gov.sg/datasets/d_8594ae9ff96d0c708bc2af633048edfb/view


##  AI Tool Declaration
This Repository used [GPT-5, GPT-5-Codex, Claude Sonnet 3.7, Gemini 2.5 Pro] to [generate ideas, improve coding ]. 