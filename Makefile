.PHONY: install run test format lint demo clean setup-db

install:
	poetry install

run:
	poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

demo:
	poetry run streamlit run demo/streamlit_app.py --server.port 8501

test:
	poetry run pytest tests/ -v

format:
	poetry run black app/ demo/ tests/
	poetry run isort app/ demo/ tests/

lint:
	poetry run flake8 app/ demo/ tests/

clean:
	find . -type d -name __pycache__ -delete
	find . -name "*.pyc" -delete

setup-db:
	poetry run python -c "from app.models.database import Base, engine; Base.metadata.create_all(bind=engine)"