.PHONY: install run dev test test-unit test-integration test-coverage test-watch clean help venv venv-activate

# Virtual environment settings
VENV_DIR = .venv
PYTHON = $(VENV_DIR)/bin/python
PIP = $(VENV_DIR)/bin/pip
UVICORN = $(VENV_DIR)/bin/uvicorn
PYTEST = $(VENV_DIR)/bin/pytest

# Default target
help:
	@echo "Available commands:"
	@echo "  venv           Create virtual environment"
	@echo "  install        Install dependencies (creates venv if needed)"
	@echo "  run            Run the application"
	@echo "  dev            Run the application in development mode with auto-reload"
	@echo "  test           Run all tests"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-coverage  Run tests with coverage report"
	@echo "  test-watch     Run tests in watch mode"
	@echo "  clean          Clean cache files and virtual environment"
	@echo "  help           Show this help message"
	@echo ""
	@echo "Setup:"
	@echo "  1. Create .env.local file with: UPSTAGE_API_KEY=your_key_here"
	@echo "  2. Run 'make install' to create venv and install dependencies"
	@echo "  3. Run 'make test' to run all tests"
	@echo "  4. Run 'make dev' to start development server"
	@echo ""
	@echo "To activate virtual environment manually:"
	@echo "  source $(VENV_DIR)/bin/activate"

# Create virtual environment
venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV_DIR); \
		echo "Virtual environment created in $(VENV_DIR)/"; \
	else \
		echo "Virtual environment already exists in $(VENV_DIR)/"; \
	fi

# Install dependencies
install: venv
	@echo "Installing dependencies in virtual environment..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Dependencies installed successfully!"

# Run the application
run: install
	$(UVICORN) main:app --host 0.0.0.0 --port 8000

# Run in development mode with auto-reload
dev: install
	$(UVICORN) main:app --host 0.0.0.0 --port 8000 --reload

# Run all tests
test: install
	@echo "Running all tests..."
	$(PYTEST) tests/ -v

# Run unit tests only (CitationManager and extract_search_queries tests)
test-unit: install
	@echo "Running unit tests..."
	$(PYTEST) tests/test_citations.py -v -m "not integration"

# Run integration tests only (SolarAPI integration tests)
test-integration: install
	@echo "Running integration tests..."
	$(PYTEST) tests/test_integration.py -v

# Run tests with coverage report
test-coverage: install
	@echo "Running tests with coverage..."
	$(PYTEST) tests/ --cov=. --cov-report=html --cov-report=term-missing

# Run tests in watch mode (automatically re-run when files change)
test-watch: install
	@echo "Running tests in watch mode..."
	$(PYTEST) tests/ -f

# Test the API endpoints (kept for backward compatibility)
test-api:
	@echo "Testing the API..."
	@echo "Testing root endpoint:"
	curl -s http://localhost:8000/ | python -m json.tool
	@echo "\nTesting weather endpoint for New York:"
	curl -s http://localhost:8000/weather/New%20York | python -m json.tool
	@echo "\nTesting weather endpoint for Tokyo:"
	curl -s http://localhost:8000/weather/Tokyo | python -m json.tool
	@echo "\nTesting health check:"
	curl -s http://localhost:8000/health | python -m json.tool

# Clean cache files
clean:
	@echo "Cleaning cache files and virtual environment..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf $(VENV_DIR)
	@echo "Cleanup completed!" 