.PHONY: install run dev test clean help venv venv-activate

# Virtual environment settings
VENV_DIR = .venv
PYTHON = $(VENV_DIR)/bin/python
PIP = $(VENV_DIR)/bin/pip
UVICORN = $(VENV_DIR)/bin/uvicorn

# Default target
help:
	@echo "Available commands:"
	@echo "  venv       Create virtual environment"
	@echo "  install    Install dependencies (creates venv if needed)"
	@echo "  run        Run the application"
	@echo "  dev        Run the application in development mode with auto-reload"
	@echo "  test       Test the API endpoints"
	@echo "  clean      Clean cache files and virtual environment"
	@echo "  help       Show this help message"
	@echo ""
	@echo "Setup:"
	@echo "  1. Create .env.local file with: UPSTAGE_API_KEY=your_key_here"
	@echo "  2. Run 'make install' to create venv and install dependencies"
	@echo "  3. Run 'make dev' to start development server"
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

# Test the API endpoints
test:
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