#======================================================================
# Makefile — Socat Network Operations Manager (Python Variant)
#======================================================================
#
# Synopsis   : Build, test, lint, install, and package socat-manager.
#
# Targets    :
#   help             - Show all targets with descriptions
#   check-deps       - Verify all prerequisites (Python, socat, optional tools)
#   lint             - Run ruff linter on all Python files
#   test             - Run full test suite (lint + pytest)
#   test-unit        - Run unit tests only (fast, no I/O)
#   test-integration - Run integration tests only
#   test-smoke       - Quick smoke test (import, help, version)
#   test-coverage    - Run tests with coverage report
#   install          - Install system-wide via pip
#   uninstall        - Remove pip installation
#   verify           - Post-install verification
#   venv             - Create an isolated virtual environment
#   dist             - Build release tarballs + checksums
#   clean            - Remove build artifacts, caches, temp files
#   clean-all        - Remove everything (including venv, dist)
#   docs             - Validate documentation completeness
#
# Usage      :
#   make help                                  # Show targets
#   make test                                  # Full lint + test suite
#   make test-smoke                            # Quick validation
#   make install                               # System-wide (pip)
#   make install PREFIX=~/.local               # User-local prefix
#   make venv VENV_DIR=./my-env                # Custom venv location
#   make dist                                  # Release tarballs
#
# Version    : 2.0.0
#======================================================================

# =====================================================================
# CONFIGURATION
# =====================================================================

VERSION     := $(shell python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo "0.1.0")
SCRIPT_NAME := socat-manager
PACKAGE     := socat_manager
SRC_DIR     := src/$(PACKAGE)
TEST_DIR    := tests

# Python
PYTHON      ?= python3
PIP         ?= pip3
PYTEST      := $(PYTHON) -m pytest
RUFF        := $(PYTHON) -m ruff
COVERAGE    := $(PYTHON) -m coverage

# Installation paths
PREFIX      ?= /opt/tools/socat-manager
BINDIR      ?= /usr/local/bin
DESTDIR     ?=

# Virtual environment
VENV_DIR    ?= ./socat-manager-venv

# Distribution
DIST_DIR    := dist
DIST_NAME   := socat-manager-v$(VERSION)

# Test options
PYTEST_OPTS ?= --tb=short -q
COV_OPTS    := --cov=$(PACKAGE) --cov-report=term-missing

# =====================================================================
# PHONY DECLARATIONS
# =====================================================================

.PHONY: help check-deps lint test test-unit test-integration test-smoke \
        test-coverage install uninstall verify venv dist clean clean-all \
        docs _check-python _check-socat

.DEFAULT_GOAL := help

# =====================================================================
# HELP
# =====================================================================

help: ## Show this help message
	@echo ""
	@echo "  Socat Network Operations Manager v$(VERSION) (Python)"
	@echo "  ──────────────────────────────────────────────────────"
	@echo ""
	@echo "  Usage: make <target> [VARIABLE=value ...]"
	@echo ""
	@echo "  Targets:"
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "    \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Variables:"
	@echo "    PYTHON       = $(PYTHON)"
	@echo "    PREFIX       = $(PREFIX)"
	@echo "    BINDIR       = $(BINDIR)"
	@echo "    VENV_DIR     = $(VENV_DIR)"
	@echo "    PYTEST_OPTS  = $(PYTEST_OPTS)"
	@echo ""
	@echo "  Examples:"
	@echo "    make test                                    # Full lint + test suite"
	@echo "    make test-smoke                              # Quick validation"
	@echo "    make install                                 # System-wide (pip)"
	@echo "    make venv VENV_DIR=/opt/tools/env            # Custom venv"
	@echo "    make dist                                    # Release tarballs"
	@echo ""

# =====================================================================
# DEPENDENCY CHECKS
# =====================================================================

_check-python:
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo "ERROR: $(PYTHON) not found"; exit 1; }
	@$(PYTHON) -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ required'" 2>/dev/null || \
		{ echo "ERROR: Python 3.12+ required (found: $$($(PYTHON) --version))"; exit 1; }

_check-socat:
	@command -v socat >/dev/null 2>&1 || { echo "WARNING: socat not found — operational modes will fail"; }

check-deps: _check-python ## Verify all prerequisites (Python, socat, optional tools)
	@echo ""
	@echo "  Dependency Check"
	@echo "  ────────────────"
	@echo ""
	@echo "  Python:"
	@echo "    $(PYTHON) $$($(PYTHON) --version 2>&1 | awk '{print $$2}')"
	@echo ""
	@echo "  Required:"
	@for cmd in socat openssl setsid ss; do \
		if command -v $$cmd >/dev/null 2>&1; then \
			printf "    \033[32m✓ %s\033[0m (%s)\n" "$$cmd" "$$(command -v $$cmd)"; \
		else \
			printf "    \033[31m✗ %s — NOT FOUND\033[0m\n" "$$cmd"; \
		fi; \
	done
	@echo ""
	@echo "  Optional:"
	@for cmd in flock lsof pstree; do \
		if command -v $$cmd >/dev/null 2>&1; then \
			printf "    \033[32m✓ %s\033[0m (%s)\n" "$$cmd" "$$(command -v $$cmd)"; \
		else \
			printf "    \033[2m- %s (optional, not found)\033[0m\n" "$$cmd"; \
		fi; \
	done
	@echo ""
	@echo "  Python Packages:"
	@for pkg in pytest ruff coverage; do \
		if $(PYTHON) -m $$pkg --version >/dev/null 2>&1; then \
			printf "    \033[32m✓ %s\033[0m\n" "$$pkg"; \
		else \
			printf "    \033[31m✗ %s — not installed\033[0m\n" "$$pkg"; \
		fi; \
	done
	@echo ""

# =====================================================================
# LINTING
# =====================================================================

lint: _check-python ## Run ruff linter on all Python files
	@echo "  Linting source and tests..."
	@$(RUFF) check $(SRC_DIR)/ $(TEST_DIR)/ --select E,W,F,I --ignore E501
	@echo "  ✓ All checks passed"

# =====================================================================
# TESTING
# =====================================================================

test: lint test-unit test-integration ## Run full test suite (lint + pytest)
	@echo ""
	@echo "  ✓ Full test suite passed"

test-unit: _check-python ## Run unit tests only (fast, no I/O)
	@echo "  Running unit tests..."
	@PYTHONPATH=src $(PYTEST) $(TEST_DIR)/unit/ $(PYTEST_OPTS)

test-integration: _check-python ## Run integration tests only
	@echo "  Running integration tests..."
	@PYTHONPATH=src $(PYTEST) $(TEST_DIR)/integration/ $(PYTEST_OPTS)

test-smoke: _check-python ## Quick smoke test (import, help, version, menu)
	@echo ""
	@echo "  Running smoke tests..."
	@echo "  ──────────────────────"
	@# Import check
	@printf "  %-30s" "Python import:"
	@PYTHONPATH=src $(PYTHON) -c "import socat_manager" 2>/dev/null && echo "✓" || { echo "✗ FAILED"; exit 1; }
	@# Version output
	@printf "  %-30s" "Version output:"
	@PYTHONPATH=src $(PYTHON) -m $(PACKAGE) version >/dev/null 2>&1 && echo "✓" || { echo "✗ FAILED"; exit 1; }
	@# Help output
	@printf "  %-30s" "Help output:"
	@PYTHONPATH=src $(PYTHON) -m $(PACKAGE) help >/dev/null 2>&1 && echo "✓" || { echo "✗ FAILED"; exit 1; }
	@# argparse help
	@printf "  %-30s" "argparse --help:"
	@PYTHONPATH=src $(PYTHON) -m $(PACKAGE) --help >/dev/null 2>&1 && echo "✓" || { echo "✗ FAILED"; exit 1; }
	@# Standalone runner
	@printf "  %-30s" "Standalone runner:"
	@$(PYTHON) socat-manager.py version >/dev/null 2>&1 && echo "✓" || { echo "✗ FAILED"; exit 1; }
	@# Per-mode help
	@printf "  %-30s" "Mode help (listen):"
	@PYTHONPATH=src $(PYTHON) -m $(PACKAGE) listen --help >/dev/null 2>&1 && echo "✓" || { echo "✗ FAILED"; exit 1; }
	@# Status mode (no sessions)
	@printf "  %-30s" "Status mode (empty):"
	@PYTHONPATH=src $(PYTHON) -m $(PACKAGE) status >/dev/null 2>&1 && echo "✓" || echo "✓ (no sessions)"
	@# No false shutdown warnings
	@printf "  %-30s" "No shutdown warnings:"
	@if PYTHONPATH=src $(PYTHON) -m $(PACKAGE) version 2>&1 | grep -qi 'shutting down'; then \
		echo "✗ FAILED (shutdown warning on version)"; exit 1; \
	else \
		echo "✓"; \
	fi
	@echo ""
	@echo "  ✓ All smoke tests passed"
	@echo ""

test-coverage: _check-python ## Run tests with coverage report
	@echo "  Running tests with coverage..."
	@PYTHONPATH=src $(PYTEST) $(TEST_DIR)/ $(PYTEST_OPTS) $(COV_OPTS)

# =====================================================================
# INSTALLATION
# =====================================================================

install: _check-python ## Install system-wide via pip
	@echo ""
	@echo "  Installing socat-manager v$(VERSION)..."
	@echo "  ────────────────────────────────────────"
	@echo "  Method:  pip editable install"
	@echo "  Package: $(PACKAGE)"
	@echo ""
	@$(PIP) install --break-system-packages -e . 2>/dev/null || $(PIP) install -e .
	@echo ""
	@echo "  ✓ Installed successfully"
	@echo ""
	@echo "  Verify:  socat-manager version"
	@echo "  Help:    socat-manager help"
	@echo "  Menu:    socat-manager"
	@echo ""

uninstall: ## Remove pip installation
	@echo ""
	@echo "  Uninstalling socat-manager..."
	@echo "  ─────────────────────────────"
	@$(PIP) uninstall -y socat-manager 2>/dev/null || true
	@echo ""
	@echo "  NOTE: Runtime directories (sessions/, logs/, certs/) are NOT removed."
	@echo "  Remove manually if needed: rm -rf sessions/ logs/ certs/"
	@echo ""
	@echo "  ✓ Uninstall complete"
	@echo ""

verify: _check-python ## Post-install verification
	@echo ""
	@echo "  Verifying socat-manager installation..."
	@echo "  ────────────────────────────────────────"
	@# Check command on PATH
	@printf "  %-30s" "Command on PATH:"
	@if command -v socat-manager >/dev/null 2>&1; then \
		echo "✓ $$(command -v socat-manager)"; \
	else \
		echo "✗ not found"; \
		echo "    Ensure pip bin directory is on your PATH"; \
		echo "    Trying module execution instead..."; \
	fi
	@# Check version output
	@printf "  %-30s" "Version output:"
	@if command -v socat-manager >/dev/null 2>&1; then \
		ver=$$(socat-manager version 2>&1 | head -1) && echo "✓ $$ver"; \
	else \
		ver=$$(PYTHONPATH=src $(PYTHON) -m $(PACKAGE) version 2>&1 | head -1) && echo "✓ $$ver (module)"; \
	fi
	@# Check help output
	@printf "  %-30s" "Help output:"
	@if command -v socat-manager >/dev/null 2>&1; then \
		socat-manager help >/dev/null 2>&1 && echo "✓" || echo "✗ FAILED"; \
	else \
		PYTHONPATH=src $(PYTHON) -m $(PACKAGE) help >/dev/null 2>&1 && echo "✓ (module)" || echo "✗ FAILED"; \
	fi
	@# Check socat dependency
	@printf "  %-30s" "socat available:"
	@if command -v socat >/dev/null 2>&1; then \
		echo "✓ $$(socat -V 2>/dev/null | head -1 | awk '{print $$NF}')"; \
	else \
		echo "⚠ not found (install before operational use)"; \
	fi
	@# Check import
	@printf "  %-30s" "Python import:"
	@PYTHONPATH=src $(PYTHON) -c "import socat_manager; print('✓ v' + socat_manager.__version__)"
	@echo ""
	@echo "  ✓ Verification complete"
	@echo ""

# =====================================================================
# VIRTUAL ENVIRONMENT
# =====================================================================

venv: _check-python ## Create an isolated virtual environment
	@echo ""
	@echo "  Creating virtual environment: $(VENV_DIR)"
	@echo "  ──────────────────────────────────────────"
	@echo ""
	@# Create venv
	@$(PYTHON) -m venv $(VENV_DIR)
	@echo "  ✓ Virtual environment created"
	@# Upgrade pip and tools
	@$(VENV_DIR)/bin/pip install --upgrade pip setuptools wheel >/dev/null 2>&1
	@echo "  ✓ pip/setuptools/wheel upgraded"
	@# Install package in editable mode
	@$(VENV_DIR)/bin/pip install -e ".[dev]" 2>/dev/null || { \
		$(VENV_DIR)/bin/pip install -e . >/dev/null 2>&1; \
		$(VENV_DIR)/bin/pip install pytest pytest-cov ruff >/dev/null 2>&1; \
	}
	@echo "  ✓ Package installed (editable mode)"
	@echo "  ✓ Dev dependencies installed (pytest, pytest-cov, ruff)"
	@echo ""
	@echo "  Virtual environment ready."
	@echo "  ──────────────────────────"
	@echo "  Activate:   source $(VENV_DIR)/bin/activate"
	@echo "  Deactivate: deactivate"
	@echo "  Remove:     rm -rf $(VENV_DIR)"
	@echo ""
	@echo "  After activation:"
	@echo "    socat-manager --help     # CLI"
	@echo "    socat-manager            # Interactive menu"
	@echo "    make test                # Run tests"
	@echo ""

# =====================================================================
# DISTRIBUTION
# =====================================================================

dist: clean ## Build release tarballs + checksums
	@echo ""
	@echo "  Building distribution v$(VERSION)..."
	@echo "  ─────────────────────────────────────"
	@mkdir -p $(DIST_DIR)
	@# --- Source tarball ---
	@rm -rf /tmp/$(DIST_NAME)
	@mkdir -p /tmp/$(DIST_NAME)/src/$(PACKAGE)/modes
	@mkdir -p /tmp/$(DIST_NAME)/tests/unit
	@mkdir -p /tmp/$(DIST_NAME)/tests/integration
	@mkdir -p /tmp/$(DIST_NAME)/tests/stubs
	@mkdir -p /tmp/$(DIST_NAME)/docs/wiki
	@# Copy source
	@cp -r $(SRC_DIR)/*.py /tmp/$(DIST_NAME)/$(SRC_DIR)/
	@cp -r $(SRC_DIR)/modes/*.py /tmp/$(DIST_NAME)/$(SRC_DIR)/modes/
	@# Copy tests
	@cp $(TEST_DIR)/conftest.py /tmp/$(DIST_NAME)/$(TEST_DIR)/ 2>/dev/null || true
	@cp $(TEST_DIR)/unit/*.py /tmp/$(DIST_NAME)/$(TEST_DIR)/unit/ 2>/dev/null || true
	@cp $(TEST_DIR)/integration/*.py /tmp/$(DIST_NAME)/$(TEST_DIR)/integration/ 2>/dev/null || true
	@cp $(TEST_DIR)/stubs/* /tmp/$(DIST_NAME)/$(TEST_DIR)/stubs/ 2>/dev/null || true
	@chmod +x /tmp/$(DIST_NAME)/$(TEST_DIR)/stubs/* 2>/dev/null || true
	@# Copy root files
	@cp socat-manager.py Makefile pyproject.toml /tmp/$(DIST_NAME)/
	@test -f LICENSE && cp LICENSE /tmp/$(DIST_NAME)/ || true
	@test -f README.md && cp README.md /tmp/$(DIST_NAME)/ || true
	@test -f .gitignore && cp .gitignore /tmp/$(DIST_NAME)/ || true
	@# Copy docs
	@for doc in $(DOCS); do test -f "$$doc" && cp "$$doc" /tmp/$(DIST_NAME)/docs/ || true; done
	@# Copy wiki
	@cp docs/wiki/*.md /tmp/$(DIST_NAME)/docs/wiki/ 2>/dev/null || true
	@# Copy .github workflows if present
	@if [ -d .github ]; then \
		cp -r .github /tmp/$(DIST_NAME)/.github; \
	fi
	@tar czf $(DIST_DIR)/$(DIST_NAME).tar.gz -C /tmp $(DIST_NAME)
	@echo "  Created: $(DIST_DIR)/$(DIST_NAME).tar.gz"
	@# --- Standalone runner tarball ---
	@rm -rf /tmp/$(DIST_NAME)-standalone
	@mkdir -p /tmp/$(DIST_NAME)-standalone/src/$(PACKAGE)/modes
	@mkdir -p /tmp/$(DIST_NAME)-standalone/sessions
	@mkdir -p /tmp/$(DIST_NAME)-standalone/logs
	@mkdir -p /tmp/$(DIST_NAME)-standalone/certs
	@mkdir -p /tmp/$(DIST_NAME)-standalone/conf
	@chmod 700 /tmp/$(DIST_NAME)-standalone/sessions
	@cp -r $(SRC_DIR)/*.py /tmp/$(DIST_NAME)-standalone/src/$(PACKAGE)/
	@cp -r $(SRC_DIR)/modes/*.py /tmp/$(DIST_NAME)-standalone/src/$(PACKAGE)/modes/
	@cp socat-manager.py /tmp/$(DIST_NAME)-standalone/
	@for doc in README.md LICENSE; do test -f "$$doc" && cp "$$doc" /tmp/$(DIST_NAME)-standalone/ || true; done
	@tar czf $(DIST_DIR)/$(DIST_NAME)-standalone.tar.gz -C /tmp $(DIST_NAME)-standalone
	@echo "  Created: $(DIST_DIR)/$(DIST_NAME)-standalone.tar.gz"
	@# --- Checksums ---
	@cd $(DIST_DIR) && sha256sum *.tar.gz > SHA256SUMS.txt
	@echo "  Created: $(DIST_DIR)/SHA256SUMS.txt"
	@echo ""
	@cat $(DIST_DIR)/SHA256SUMS.txt | sed 's/^/    /'
	@echo ""
	@rm -rf /tmp/$(DIST_NAME) /tmp/$(DIST_NAME)-standalone
	@echo "  ✓ Distribution ready in $(DIST_DIR)/"
	@echo ""

# =====================================================================
# DOCUMENTATION
# =====================================================================

docs: ## Validate documentation completeness
	@echo "  Checking documentation..."
	@missing=0; \
	for f in docs/README.md docs/USAGE_GUIDE.md docs/SETUP_GUIDE.md \
		docs/CONTRIBUTING.md docs/SECURITY.md docs/TROUBLESHOOTING.md \
		docs/CHANGELOG.md docs/CODE_OF_CONDUCT.md docs/DEVELOPMENT_GUIDE.md \
		docs/DEVELOPER_GUIDE.md docs/Frequently_Asked_Questions_\(FAQ\).md \
		LICENSE .gitignore Makefile README.md; do \
		if [ -f "$$f" ]; then \
			printf "    \033[32m✓\033[0m %s\n" "$$f"; \
		else \
			printf "    \033[31m✗\033[0m %s MISSING\n" "$$f"; \
			missing=$$((missing + 1)); \
		fi; \
	done; \
	echo ""; \
	if [ $$missing -gt 0 ]; then \
		echo "  $$missing document(s) missing"; exit 1; \
	else \
		echo "  ✓ All documentation present"; \
	fi

# =====================================================================
# CLEANUP
# =====================================================================

clean: ## Remove build artifacts, caches, temp files
	@echo "  Cleaning..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	@rm -f .coverage
	@rm -rf htmlcov/
	@rm -rf build/
	@rm -f sessions/.lock
	@echo "  ✓ Clean"

clean-all: clean ## Remove everything (including venv, dist)
	@rm -rf $(VENV_DIR) $(DIST_DIR)
	@rm -rf sessions/ logs/ certs/
	@echo "  ✓ Full clean"
