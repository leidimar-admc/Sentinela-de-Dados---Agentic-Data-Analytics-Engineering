.RECIPEPREFIX = >
.PHONY: setup data build pipeline evals test lint clean

setup:                 ## instala dependencias
> pip install -r requirements.txt

data:                  ## gera os dados simulados da Mar (+ anomalias com ground truth)
> python data/generators/generate_mar.py

build: data            ## roda o data product (dbt: staging -> intermediate -> marts + testes)
> cd transform && dbt build --profiles-dir .

pipeline:              ## roda o loop agentico (detecta -> RCA -> portao humano -> propoe correcao)
> python scripts/run_pipeline.py

evals:                 ## avalia os agentes contra o ground truth (precisao/recall + acerto de RCA)
> python evals/run_evals.py --check

test:                  ## testes unitarios
> pytest -q

lint:
> ruff check .

clean:
> rm -rf data/raw data/*.duckdb data/anomaly_manifest.json transform/target transform/logs transform/dbt_packages
